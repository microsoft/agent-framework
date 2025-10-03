# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

import uuid
from collections.abc import Iterable

from agent_framework import ChatMessage

from agent_framework_purview.models.simples import OperatingSystemSpecifications

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
            meta = ProcessConversationMetadata(  # type: ignore[call-arg]
                **{
                    "@odata.type": "microsoft.graph.processConversationMetadata",
                    "identifier": message_id,
                    "content": content,
                    "isTruncated": False,
                    "name": f"Agent Framework Message {message_id}",
                    "correlationId": str(uuid.uuid4()),
                }
            )
            activity_meta = ActivityMetadata(activity=activity)

            if self._settings.purview_app_location:
                policy_location = PolicyLocation(**{
                    "@odata.type": self._settings.purview_app_location.get_policy_location()["@odata.type"],
                    "value": self._settings.purview_app_location.location_value,
                })
            elif token_info and token_info.get("client_id"):
                policy_location = PolicyLocation(**{
                    "@odata.type": "microsoft.graph.policyLocationApplication",
                    "value": token_info["client_id"],
                })
            else:
                raise ValueError("App location not provided or inferable")

            protected_app = ProtectedAppMetadata(
                name=self._settings.app_name,
                version="1.0",
                applicationLocation=policy_location,
            )  # type: ignore[call-arg]
            integrated_app = IntegratedAppMetadata(name=self._settings.app_name, version="1.0")
            device_meta = DeviceMetadata(
                operatingSystemSpecifications=OperatingSystemSpecifications(
                    operatingSystemPlatform="Unknown", operatingSystemVersion="Unknown"
                )
            )  # type: ignore[call-arg]

            user_id = self._settings.default_user_id or (token_info or {}).get("user_id")
            # Only use author_name if it's a valid GUID format
            if m.author_name and _is_valid_guid(m.author_name):
                user_id = m.author_name
            if not user_id or not _is_valid_guid(user_id):
                raise ValueError("User id required or inferable from message author/credential")

            ctp = ContentToProcess(**{
                "contentEntries": [meta],
                "activityMetadata": activity_meta,
                "deviceMetadata": device_meta,
                "integratedAppMetadata": integrated_app,
                "protectedAppMetadata": protected_app,
            })  # type: ignore[call-arg]
            req = ProcessContentRequest(**{
                "contentToProcess": ctp,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "correlation_id": meta.correlation_id,
                "process_inline": True if self._settings.process_inline else None,
            })  # type: ignore[call-arg]
            results.append(req)
        return results

    async def _process_with_scopes(self, pc_request: ProcessContentRequest) -> ProcessContentResponse:
        ps_req = ProtectionScopesRequest(
            user_id=pc_request.user_id,
            tenant_id=pc_request.tenant_id,
            activities=translate_activity(pc_request.content_to_process.activity_metadata.activity),
            locations=[pc_request.content_to_process.protected_app_metadata.application_location],
            deviceMetadata=pc_request.content_to_process.device_metadata,
            integratedAppMetadata=pc_request.content_to_process.integrated_app_metadata,
            correlation_id=pc_request.correlation_id,
        )  # type: ignore[call-arg]
        ps_resp = await self._client.get_protection_scopes(ps_req)
        should_process, dlp_actions = self._check_applicable_scopes(pc_request, ps_resp)

        if should_process:
            pc_resp = await self._client.process_content(pc_request)
            pc_resp.policy_actions = self._combine_policy_actions(pc_resp.policy_actions, dlp_actions)
            return pc_resp
        ca_req = ContentActivitiesRequest(**{
            "userId": pc_request.user_id,
            "tenant_id": pc_request.tenant_id,
            "contentMetadata": pc_request.content_to_process,
            "correlation_id": pc_request.correlation_id,
        })  # type: ignore[call-arg]
        ca_resp = await self._client.send_content_activities(ca_req)
        if ca_resp.error:
            return ProcessContentResponse(**{"processingErrors": [ProcessingError(message=str(ca_resp.error))]})  # type: ignore[call-arg]
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
            activity_match = bool(scope.activities and (scope.activities & req_activity) == req_activity)
            location_match = False
            for loc in scope.locations or []:
                location_match = bool(
                    loc.data_type
                    and location.data_type
                    and loc.data_type.lower().endswith(location.data_type.split(".")[-1].lower())
                    and loc.value == location.value
                )
            if activity_match and location_match:
                should_process = True
                if scope.policy_actions:
                    dlp_actions.extend(scope.policy_actions)
        return should_process, dlp_actions
