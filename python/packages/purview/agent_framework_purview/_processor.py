# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

import uuid
from collections.abc import Iterable

from agent_framework import ChatMessage

from ._models import OperatingSystemSpecifications

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

    async def process_messages(self, messages: Iterable[ChatMessage], activity: Activity) -> bool:
        pc_requests = await self._map_messages(messages, activity)
        for req in pc_requests:
            resp = await self._process_with_scopes(req)
            if resp.policy_actions:
                for act in resp.policy_actions:
                    if act.action == DlpAction.BLOCK_ACCESS or act.restriction_action == RestrictionAction.BLOCK:
                        return True
        return False

    async def _map_messages(self, messages: Iterable[ChatMessage], activity: Activity) -> list[ProcessContentRequest]:
        results: list[ProcessContentRequest] = []
        token_info = None

        if not (self._settings.tenant_id and self._settings.default_user_id and self._settings.purview_app_location):
            # attempt inference
            token_info = await self._client.get_user_info_from_token(tenant_id=self._settings.tenant_id)

        tenant_id = self._settings.tenant_id or (token_info or {}).get("tenant_id")
        if not tenant_id or not _is_valid_guid(tenant_id):
            raise ValueError("Tenant id required or must be inferable from credential")

        for m in messages:
            message_id = m.message_id or str(uuid.uuid4())
            content = PurviewTextContent(data=m.text or "")  # alias field 'data'
            # Use internal parameter names (not aliases) for direct instantiation
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

            user_id = self._settings.default_user_id or (token_info or {}).get("user_id")
            # Only use author_name if it's a valid GUID format
            if m.author_name and _is_valid_guid(m.author_name):
                user_id = m.author_name
            if not user_id or not _is_valid_guid(user_id):
                raise ValueError("User id required or inferable from message author/credential")

            ctp = ContentToProcess(
                content_entries=[meta],
                activity_metadata=activity_meta,
                device_metadata=device_meta,
                integrated_app_metadata=integrated_app,
                protected_app_metadata=protected_app,
            )
            req = ProcessContentRequest(
                content_to_process=ctp,
                user_id=user_id,
                tenant_id=tenant_id,
                correlation_id=meta.correlation_id,
                process_inline=True if self._settings.process_inline else None,
            )
            results.append(req)
        return results

    async def _process_with_scopes(self, pc_request: ProcessContentRequest) -> ProcessContentResponse:
        ps_req = ProtectionScopesRequest(
            user_id=pc_request.user_id,
            tenant_id=pc_request.tenant_id,
            activities=translate_activity(pc_request.content_to_process.activity_metadata.activity),
            locations=[pc_request.content_to_process.protected_app_metadata.application_location],
            device_metadata=pc_request.content_to_process.device_metadata,
            integrated_app_metadata=pc_request.content_to_process.integrated_app_metadata,
            correlation_id=pc_request.correlation_id,
        )
        ps_resp = await self._client.get_protection_scopes(ps_req)
        should_process, dlp_actions = self._check_applicable_scopes(pc_request, ps_resp)

        if should_process and False:
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
