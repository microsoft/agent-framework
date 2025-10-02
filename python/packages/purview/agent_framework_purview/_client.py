# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

import base64
import json
from typing import Any, TypeVar

import httpx
from agent_framework import AGENT_FRAMEWORK_USER_AGENT, get_logger
from agent_framework.observability import get_tracer
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential
from pydantic import BaseModel

from ._exceptions import (
    PurviewAuthenticationError,
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

TResp = TypeVar("TResp", bound=BaseModel)


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
        # Async credential path
        if isinstance(cred, AsyncTokenCredential):  # type: ignore[arg-type]
            token = await cred.get_token(*scopes, tenant_id=tenant_id)
        else:
            # Sync credential path executed in a thread executor
            import asyncio

            loop = asyncio.get_running_loop()
            token = await loop.run_in_executor(
                None,
                lambda: cred.get_token(*scopes, tenant_id=tenant_id),  # type: ignore[misc]
            )
        return token.token

    @staticmethod
    def _extract_token_info(token: str) -> dict[str, Any]:
        # JWT second segment
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("Invalid JWT token format")
        payload = parts[1]
        rem = len(payload) % 4
        if rem:
            payload += "=" * (4 - rem)
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded.decode("utf-8"))
        # Map to similar structure used in .NET
        return {
            "user_id": data.get("oid") if data.get("idtyp") == "user" else None,
            "tenant_id": data.get("tid"),
            "client_id": data.get("appid"),
        }

    async def get_user_info_from_token(self, *, tenant_id: str | None = None) -> dict[str, Any]:
        token = await self._get_token(tenant_id=tenant_id)
        return self._extract_token_info(token)

    async def process_content(self, request: ProcessContentRequest) -> ProcessContentResponse:
        tracer = get_tracer()
        with tracer.start_as_current_span("purview.process_content"):
            token = await self._get_token(tenant_id=request.tenant_id)
            url = f"{self._graph_uri}/users/{request.user_id}/dataSecurityAndGovernance/processContent"
            return await self._post(url, request, ProcessContentResponse, token)

    async def get_protection_scopes(self, request: ProtectionScopesRequest) -> ProtectionScopesResponse:
        tracer = get_tracer()
        with tracer.start_as_current_span("purview.get_protection_scopes"):
            token = await self._get_token()
            url = f"{self._graph_uri}/users/{request.user_id}/dataSecurityAndGovernance/protectionScopes/compute"
            return await self._post(url, request, ProtectionScopesResponse, token)

    async def send_content_activities(self, request: ContentActivitiesRequest) -> ContentActivitiesResponse:
        tracer = get_tracer()
        with tracer.start_as_current_span("purview.send_content_activities"):
            token = await self._get_token()
            url = f"{self._graph_uri}/users/{request.user_id}/dataSecurityAndGovernance/activities/contentActivities"
            return await self._post(url, request, ContentActivitiesResponse, token)

    async def _post(self, url: str, model: Any, response_type: type[TResp], token: str) -> TResp:
        payload = model.model_dump(by_alias=True, exclude_none=True, mode="json")
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": AGENT_FRAMEWORK_USER_AGENT,
            "Content-Type": "application/json",
        }
        resp = await self._client.post(url, json=payload, headers=headers)
        if resp.status_code in (401, 403):
            raise PurviewAuthenticationError(f"Auth failure {resp.status_code}: {resp.text}")
        if resp.status_code == 429:
            raise PurviewRateLimitError(f"Rate limited {resp.status_code}: {resp.text}")
        if resp.status_code not in (200, 201, 202):
            raise PurviewRequestError(f"Purview request failed {resp.status_code}: {resp.text}")
        try:
            data = resp.json()
        except ValueError:
            data = {}
        try:
            return response_type.model_validate(data)  # type: ignore[no-any-return]
        except Exception as ex:  # pragma: no cover
            raise PurviewServiceError(f"Failed to deserialize Purview response: {ex}") from ex
