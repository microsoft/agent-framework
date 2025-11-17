# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

import base64
import inspect
import json
from typing import Any, cast
from uuid import uuid4

import httpx
from agent_framework import AGENT_FRAMEWORK_USER_AGENT
from agent_framework._logging import get_logger
from agent_framework.observability import get_tracer
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential
from opentelemetry import trace

from ._exceptions import (
    PurviewAuthenticationError,
    PurviewPaymentRequiredError,
    PurviewRateLimitError,
    PurviewRequestError,
    PurviewServiceError,
)
from ._models import (
    ContentActivitiesRequest,
    ContentActivitiesResponse,
    ProcessContentRequest,
    ProcessContentResponse,
    ProtectionScopesRequest,
    ProtectionScopesResponse,
)
from ._settings import PurviewSettings

logger = get_logger("agent_framework.purview")


class PurviewClient:
    """Async client for calling Graph Purview endpoints.

    Supports both synchronous TokenCredential and asynchronous AsyncTokenCredential implementations.
    A sync credential will be invoked in a thread to avoid blocking the event loop.
    """

    def __init__(
        self,
        credential: TokenCredential | AsyncTokenCredential,
        settings: PurviewSettings,
        *,
        timeout: float | None = 10.0,
    ):
        self._credential: TokenCredential | AsyncTokenCredential = credential
        self._settings = settings
        self._graph_uri = settings.graph_base_uri.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_token(self, *, tenant_id: str | None = None) -> str:
        """Acquire an access token using either async or sync credential."""
        scopes = self._settings.get_scopes()
        cred = self._credential
        token = cred.get_token(*scopes, tenant_id=tenant_id)
        token = await token if inspect.isawaitable(token) else token
        return token.token

    @staticmethod
    def _extract_token_info(token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("Invalid JWT token format")
        payload = parts[1]
        rem = len(payload) % 4
        if rem:
            payload += "=" * (4 - rem)
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded.decode("utf-8"))
        return {
            "user_id": data.get("oid") if data.get("idtyp") == "user" else None,
            "tenant_id": data.get("tid"),
            "client_id": data.get("appid"),
        }

    async def get_user_info_from_token(self, *, tenant_id: str | None = None) -> dict[str, Any]:
        token = await self._get_token(tenant_id=tenant_id)
        return self._extract_token_info(token)

    async def process_content(self, request: ProcessContentRequest) -> ProcessContentResponse:
        with get_tracer().start_as_current_span("purview.process_content"):
            token = await self._get_token(tenant_id=request.tenant_id)
            url = f"{self._graph_uri}/users/{request.user_id}/dataSecurityAndGovernance/processContent"
            headers = {}
            # Add If-None-Match header if scope_identifier is present
            if hasattr(request, "scope_identifier") and request.scope_identifier:
                headers["If-None-Match"] = request.scope_identifier
            # Add Prefer: evaluateInline header if process_inline is True
            if hasattr(request, "process_inline") and request.process_inline:
                headers["Prefer"] = "evaluateInline"

            response = await self._post(
                url, request, ProcessContentResponse, token, headers=headers, return_response=True
            )

            if isinstance(response, tuple) and len(response) == 2:
                response_obj, _ = response
                return cast(ProcessContentResponse, response_obj)

            return cast(ProcessContentResponse, response)

    async def get_protection_scopes(self, request: ProtectionScopesRequest) -> ProtectionScopesResponse:
        with get_tracer().start_as_current_span("purview.get_protection_scopes"):
            token = await self._get_token()
            url = f"{self._graph_uri}/users/{request.user_id}/dataSecurityAndGovernance/protectionScopes/compute"
            response = await self._post(url, request, ProtectionScopesResponse, token, return_response=True)

            # Extract etag from response headers
            if isinstance(response, tuple) and len(response) == 2:
                response_obj, headers = response
                if "etag" in headers:
                    etag_value = headers["etag"].strip('"')
                    response_obj.scope_identifier = etag_value
                return cast(ProtectionScopesResponse, response_obj)

            return cast(ProtectionScopesResponse, response)

    async def send_content_activities(self, request: ContentActivitiesRequest) -> ContentActivitiesResponse:
        with get_tracer().start_as_current_span("purview.send_content_activities"):
            token = await self._get_token()
            url = f"{self._graph_uri}/users/{request.user_id}/dataSecurityAndGovernance/activities/contentActivities"
            return cast(ContentActivitiesResponse, await self._post(url, request, ContentActivitiesResponse, token))

    async def _post(
        self,
        url: str,
        model: Any,
        response_type: type[Any],
        token: str,
        headers: dict[str, str] | None = None,
        return_response: bool = False,
    ) -> Any:
        if hasattr(model, "correlation_id") and not model.correlation_id:
            model.correlation_id = str(uuid4())

        correlation_id = getattr(model, "correlation_id", None)
        if correlation_id:
            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("correlation_id", correlation_id)
            logger.info(f"Purview request to {url} with correlation_id: {correlation_id}")

        payload = model.model_dump(by_alias=True, exclude_none=True, mode="json")
        request_headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": AGENT_FRAMEWORK_USER_AGENT,
            "Content-Type": "application/json",
        }
        if correlation_id:
            request_headers["client-request-id"] = correlation_id

        if headers:
            request_headers.update(headers)
        resp = await self._client.post(url, json=payload, headers=request_headers)

        if resp.status_code in (401, 403):
            raise PurviewAuthenticationError(f"Auth failure {resp.status_code}: {resp.text}")
        if resp.status_code == 402:
            if self._settings.ignore_payment_required:
                return response_type()  # type: ignore[call-arg, no-any-return]
            raise PurviewPaymentRequiredError(f"Payment required {resp.status_code}: {resp.text}")
        if resp.status_code == 429:
            raise PurviewRateLimitError(f"Rate limited {resp.status_code}: {resp.text}")
        if resp.status_code not in (200, 201, 202):
            raise PurviewRequestError(f"Purview request failed {resp.status_code}: {resp.text}")
        try:
            data = resp.json()
        except ValueError:
            data = {}

        try:
            # Prefer pydantic-style model_validate if present, else fall back to constructor.
            if hasattr(response_type, "model_validate"):
                response_obj = response_type.model_validate(data)  # type: ignore[no-any-return]
            else:
                response_obj = response_type(**data)  # type: ignore[call-arg, no-any-return]

            # Extract correlation_id from response headers if response object supports it
            if "client-request-id" in resp.headers and hasattr(response_obj, "correlation_id"):
                response_obj.correlation_id = resp.headers["client-request-id"]
                logger.info(f"Purview response from {url} with correlation_id: {response_obj.correlation_id}")

            if return_response:
                return (response_obj, resp.headers)
            return response_obj
        except Exception as ex:
            raise PurviewServiceError(f"Failed to deserialize Purview response: {ex}") from ex
