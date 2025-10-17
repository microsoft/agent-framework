# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

import uuid
from collections.abc import Iterable, MutableMapping
from typing import Any

from agent_framework import ChatMessage

from ._client import PurviewClient
from ._models import (
    Activity,
    ActivityMetadata,
    ContentActivitiesRequest,
    ContentToProcess,
    DeviceMetadata,
    DlpAction,
    DlpActionInfo,
    IntegratedAppMetadata,
    OperatingSystemSpecifications,
    PolicyLocation,
    ProcessContentRequest,
    ProcessContentResponse,
    ProcessConversationMetadata,
    ProcessingError,
    ProtectedAppMetadata,
    ProtectionScopesRequest,
    ProtectionScopesResponse,
    PurviewTextContent,
    RestrictionAction,
    translate_activity,
)
from ._settings import PurviewSettings


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

    def __init__(self, client: PurviewClient, settings: PurviewSettings):
        self._client = client
        self._settings = settings

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
                process_inline=True if self._settings.process_inline else None,
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
        ps_resp = await self._client.get_protection_scopes(ps_req)
        should_process, dlp_actions = self._check_applicable_scopes(pc_request, ps_resp)

        if should_process:
            pc_resp = await self._client.process_content(pc_request)
            pc_resp.policy_actions = self._combine_policy_actions(pc_resp.policy_actions, dlp_actions)
            return pc_resp
        ca_req = ContentActivitiesRequest(
            user_id=pc_request.user_id,
            tenant_id=pc_request.tenant_id,
            content_to_process=pc_request.content_to_process,
            correlation_id=pc_request.correlation_id,
        )
        ca_resp = await self._client.send_content_activities(ca_req)
        if ca_resp.error:
            return ProcessContentResponse(processing_errors=[ProcessingError(message=str(ca_resp.error))])
        return ProcessContentResponse()

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
    ) -> tuple[bool, list[DlpActionInfo]]:
        req_activity = translate_activity(pc_request.content_to_process.activity_metadata.activity)
        location = pc_request.content_to_process.protected_app_metadata.application_location
        should_process: bool = False
        dlp_actions: list[DlpActionInfo] = []
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
                if scope.policy_actions:
                    dlp_actions.extend(scope.policy_actions)
        return should_process, dlp_actions
