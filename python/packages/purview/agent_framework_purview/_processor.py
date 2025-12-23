# Copyright (c) Microsoft. All rights reserved.

import asyncio
import uuid
from collections.abc import Iterable, MutableMapping
from typing import Any

from agent_framework import ChatMessage
from agent_framework._logging import get_logger

from ._cache import CacheProvider, InMemoryCacheProvider, create_protection_scopes_cache_key
from ._client import PurviewClient
from ._exceptions import PurviewPaymentRequiredError
from ._models import (
    Activity,
    ActivityMetadata,
    ContentActivitiesRequest,
    ContentToProcess,
    DeviceMetadata,
    DlpAction,
    DlpActionInfo,
    ExecutionMode,
    IntegratedAppMetadata,
    OperatingSystemSpecifications,
    PolicyLocation,
    ProcessContentRequest,
    ProcessContentResponse,
    ProcessConversationMetadata,
    ProtectedAppMetadata,
    ProtectionScopesRequest,
    ProtectionScopesResponse,
    ProtectionScopeState,
    PurviewTextContent,
    RestrictionAction,
    translate_activity,
)
from ._settings import PurviewSettings

logger = get_logger("agent_framework.purview")


def _is_valid_guid(value: str | None) -> bool:
    """Check if a string is a valid GUID/UUID format using uuid module."""
    if not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


class ScopedContentProcessor:
    """Combine protection scopes, process content, and content activities logic."""

    def __init__(self, client: PurviewClient, settings: PurviewSettings, cache_provider: CacheProvider | None = None):
        self._client = client
        self._settings = settings
        self._cache: CacheProvider = cache_provider or InMemoryCacheProvider(
            default_ttl_seconds=settings.cache_ttl_seconds, max_size_bytes=settings.max_cache_size_bytes
        )
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def process_messages(
        self, messages: Iterable[ChatMessage], activity: Activity, user_id: str | None = None
    ) -> tuple[bool, str | None]:
        """Process messages for policy evaluation.

        Args:
            messages: The messages to process
            activity: The activity type (e.g., UPLOAD_TEXT)
            user_id: Optional user_id to use for all messages. If provided, this is the fallback.

        Returns:
            A tuple of (should_block: bool, resolved_user_id: str | None).
            The resolved_user_id can be stored and passed back when processing the response
            to ensure the same user context is maintained throughout the request/response cycle.
        """
        pc_requests, resolved_user_id = await self._map_messages(messages, activity, user_id)
        should_block = False
        for req in pc_requests:
            resp = await self._process_with_scopes(req)
            if resp.policy_actions:
                for act in resp.policy_actions:
                    if act.action == DlpAction.BLOCK_ACCESS or act.restriction_action == RestrictionAction.BLOCK:
                        should_block = True
                        break
            if should_block:
                break
        return should_block, resolved_user_id

    async def _map_messages(
        self, messages: Iterable[ChatMessage], activity: Activity, provided_user_id: str | None = None
    ) -> tuple[list[ProcessContentRequest], str | None]:
        """Map messages to ProcessContentRequests.

        Args:
            messages: The messages to map
            activity: The activity type
            provided_user_id: Optional user_id to use. If provided, this is the fallback.

        Returns:
            A tuple of (requests, resolved_user_id)
        """
        results: list[ProcessContentRequest] = []
        token_info = None

        if not (self._settings.tenant_id and self._settings.purview_app_location):
            token_info = await self._client.get_user_info_from_token(tenant_id=self._settings.tenant_id)

        tenant_id = (token_info or {}).get("tenant_id") or self._settings.tenant_id
        if not tenant_id or not _is_valid_guid(tenant_id):
            raise ValueError("Tenant id required or must be inferable from credential")

        resolved_user_id = (token_info or {}).get("user_id")
        resolved_author_name = None
        if not resolved_user_id:
            for m in messages:
                if m.additional_properties:
                    potential_user_id = m.additional_properties.get("user_id")
                    if _is_valid_guid(potential_user_id):
                        resolved_user_id = potential_user_id
                        break
                if m.author_name and _is_valid_guid(m.author_name) and not resolved_author_name:
                    resolved_author_name = m.author_name

        if not resolved_user_id and resolved_author_name:
            resolved_user_id = resolved_author_name

        if not resolved_user_id:
            resolved_user_id = provided_user_id if provided_user_id and _is_valid_guid(provided_user_id) else None

        # Return empty results if user_id is empty
        if not resolved_user_id or not _is_valid_guid(resolved_user_id):
            return results, None

        for m in messages:
            message_id = m.message_id or str(uuid.uuid4())
            content = PurviewTextContent(data=m.text or "")
            meta = ProcessConversationMetadata(
                identifier=message_id,
                content=content,
                name=f"Agent Framework Message {message_id}",
                is_truncated=False,
                correlation_id=str(uuid.uuid4()),
            )
            activity_meta = ActivityMetadata(activity=activity)

            if self._settings.purview_app_location:
                policy_location = PolicyLocation(
                    data_type=self._settings.purview_app_location.get_policy_location()["@odata.type"],
                    value=self._settings.purview_app_location.location_value,
                )
            elif token_info and token_info.get("client_id"):
                policy_location = PolicyLocation(
                    data_type="microsoft.graph.policyLocationApplication",
                    value=token_info["client_id"],
                )
            else:
                raise ValueError("App location not provided or inferable")

            protected_app = ProtectedAppMetadata(
                name=self._settings.app_name,
                version="1.0",
                application_location=policy_location,
            )
            integrated_app = IntegratedAppMetadata(name=self._settings.app_name, version="1.0")
            device_meta = DeviceMetadata(
                operating_system_specifications=OperatingSystemSpecifications(
                    operating_system_platform="Unknown", operating_system_version="Unknown"
                )
            )

            ctp = ContentToProcess(
                content_entries=[meta],
                activity_metadata=activity_meta,
                device_metadata=device_meta,
                integrated_app_metadata=integrated_app,
                protected_app_metadata=protected_app,
            )
            req = ProcessContentRequest(
                content_to_process=ctp,
                user_id=resolved_user_id,  # Use the resolved user_id for all messages
                tenant_id=tenant_id,
                correlation_id=meta.correlation_id,
                process_inline=None,  # Will be set based on execution mode
            )
            results.append(req)
        return results, resolved_user_id

    async def _process_with_scopes(self, pc_request: ProcessContentRequest) -> ProcessContentResponse:
        app_location = pc_request.content_to_process.protected_app_metadata.application_location
        locations: list[PolicyLocation | MutableMapping[str, Any]] = [app_location] if app_location is not None else []

        ps_req = ProtectionScopesRequest(
            user_id=pc_request.user_id,
            tenant_id=pc_request.tenant_id,
            activities=translate_activity(pc_request.content_to_process.activity_metadata.activity),
            locations=locations,
            device_metadata=pc_request.content_to_process.device_metadata,
            integrated_app_metadata=pc_request.content_to_process.integrated_app_metadata,
            correlation_id=pc_request.correlation_id,
        )

        # Check for tenant-level 402 exception cache first
        tenant_payment_cache_key = f"purview:payment_required:{pc_request.tenant_id}"
        cached_payment_exception = await self._cache.get(tenant_payment_cache_key)
        if isinstance(cached_payment_exception, PurviewPaymentRequiredError):
            raise cached_payment_exception

        cache_key = create_protection_scopes_cache_key(ps_req)
        cached_ps_resp = await self._cache.get(cache_key)

        if cached_ps_resp is not None:
            if isinstance(cached_ps_resp, ProtectionScopesResponse):
                ps_resp = cached_ps_resp
        else:
            try:
                ps_resp = await self._client.get_protection_scopes(ps_req)
                await self._cache.set(cache_key, ps_resp, ttl_seconds=self._settings.cache_ttl_seconds)
            except PurviewPaymentRequiredError as ex:
                # Cache the exception at tenant level so all subsequent requests for this tenant fail fast
                await self._cache.set(tenant_payment_cache_key, ex, ttl_seconds=self._settings.cache_ttl_seconds)
                raise

        if ps_resp.scope_identifier:
            pc_request.scope_identifier = ps_resp.scope_identifier

        should_process, dlp_actions, execution_mode = self._check_applicable_scopes(pc_request, ps_resp)

        if should_process:
            # Set process_inline based on execution mode
            pc_request.process_inline = execution_mode == ExecutionMode.EVALUATE_INLINE

            # If execution mode is offline, queue the PC request in background
            if execution_mode != ExecutionMode.EVALUATE_INLINE:
                task = asyncio.create_task(self._process_content_background(pc_request, cache_key))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
                return ProcessContentResponse(id="204", correlation_id=pc_request.correlation_id)

            pc_resp = await self._client.process_content(pc_request)

            if pc_request.scope_identifier and pc_resp.protection_scope_state == ProtectionScopeState.MODIFIED:
                await self._cache.remove(cache_key)

            pc_resp.policy_actions = self._combine_policy_actions(pc_resp.policy_actions, dlp_actions)
            return pc_resp

        # No applicable scopes - send content activities in background
        ca_req = ContentActivitiesRequest(
            user_id=pc_request.user_id,
            tenant_id=pc_request.tenant_id,
            content_to_process=pc_request.content_to_process,
            correlation_id=pc_request.correlation_id,
        )

        task = asyncio.create_task(self._send_content_activities_background(ca_req))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        # Respond with HttpStatusCode 204(No Content)
        return ProcessContentResponse(id="204", correlation_id=pc_request.correlation_id)

    async def _process_content_background(self, pc_request: ProcessContentRequest, cache_key: str) -> None:
        """Process content in background for offline execution mode."""
        try:
            pc_resp = await self._client.process_content(pc_request)

            # If protection scope state is modified, make another PC request and invalidate cache
            if pc_request.scope_identifier and pc_resp.protection_scope_state == ProtectionScopeState.MODIFIED:
                await self._cache.remove(cache_key)
                await self._client.process_content(pc_request)
        except Exception as ex:
            # Log errors but don't propagate since this is fire-and-forget
            logger.warning(f"Background process content request failed: {ex}")

    async def _send_content_activities_background(self, ca_req: ContentActivitiesRequest) -> None:
        """Send content activities in background without blocking."""
        try:
            await self._client.send_content_activities(ca_req)
        except Exception as ex:
            # Log errors but don't propagate since this is fire-and-forget
            logger.warning(f"Background content activities request failed: {ex}")

    @staticmethod
    def _combine_policy_actions(
        existing: list[DlpActionInfo] | None, new_actions: list[DlpActionInfo]
    ) -> list[DlpActionInfo]:
        by_key: dict[str, DlpActionInfo] = {}
        for a in existing or []:
            if a.action:
                by_key[a.action] = a
        for a in new_actions:
            if a.action:
                by_key[a.action] = a
        return list(by_key.values())

    @staticmethod
    def _check_applicable_scopes(
        pc_request: ProcessContentRequest, ps_response: ProtectionScopesResponse
    ) -> tuple[bool, list[DlpActionInfo], ExecutionMode]:
        """Check if any scopes are applicable to the request.

        Args:
            pc_request: The process content request
            ps_response: The protection scopes response

        Returns:
            A tuple of (should_process, dlp_actions, execution_mode)
        """
        req_activity = translate_activity(pc_request.content_to_process.activity_metadata.activity)
        location = pc_request.content_to_process.protected_app_metadata.application_location
        should_process: bool = False
        dlp_actions: list[DlpActionInfo] = []
        execution_mode: ExecutionMode = ExecutionMode.EVALUATE_OFFLINE  # Default to offline

        for scope in ps_response.scopes or []:
            # Check if all activities in req_activity are present in scope.activities using bitwise flags.
            activity_match = bool(scope.activities and (scope.activities & req_activity) == req_activity)
            location_match = False
            if location is not None:
                for loc in scope.locations or []:
                    if (
                        loc.data_type
                        and location.data_type
                        and loc.data_type.lower().endswith(location.data_type.split(".")[-1].lower())
                        and loc.value == location.value
                    ):
                        location_match = True
                        break
            if activity_match and location_match:
                should_process = True

                # If any scope has EvaluateInline, upgrade to inline mode
                if scope.execution_mode == ExecutionMode.EVALUATE_INLINE:
                    execution_mode = ExecutionMode.EVALUATE_INLINE

                if scope.policy_actions:
                    dlp_actions.extend(scope.policy_actions)
        return should_process, dlp_actions, execution_mode
