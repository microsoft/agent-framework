# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import binascii
import json
import logging
import re
import time
import uuid
from collections.abc import Iterable, MutableMapping
from copy import copy
from typing import Any

from agent_framework import Content, Message

from ._cache import CacheProvider, InMemoryCacheProvider, create_protection_scopes_cache_key
from ._client import PurviewClient
from ._exceptions import PurviewPaymentRequiredError
from ._models import (
    Activity,
    ActivityMetadata,
    ContentActivitiesRequest,
    ContentBase,
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
    PurviewBinaryContent,
    PurviewTextContent,
    RestrictionAction,
    translate_activity,
)
from ._settings import PurviewSettings

logger = logging.getLogger("agent_framework.purview")


def _is_valid_guid(value: str | None) -> bool:
    """Check if a string is a valid GUID/UUID format using uuid module."""
    if not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


# RFC 2397: data:[<mediatype>][;base64],<data>, where <mediatype> may be followed by any number of
# ";parameter=value" segments (for example "data:text/plain;charset=utf-8;base64,..."). The optional
# parameters have to be matched explicitly, otherwise a parameterised media type fails to decode and
# its payload would be submitted as a base64 string that no classifier can read.
_DATA_URI_PATTERN = re.compile(
    r"^data:(?P<media_type>[^;,]*)(?:;[^;,]+)*?;base64,(?P<base64_data>.*)$",
    re.DOTALL | re.IGNORECASE,
)

# Content types that carry no user data and therefore have nothing for DLP to classify.
# Every other content type must reach Purview; see _map_content.
_NON_EVALUATED_CONTENT_TYPES = frozenset({"usage"})


def _serialize_for_evaluation(value: Any) -> str:
    """Render an arbitrary content value as text so Purview can classify it."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _decode_data_uri(uri: str | None) -> bytes | None:
    """Return the raw bytes behind a base64 data URI, or None if it is not one."""
    if not uri:
        return None
    match = _DATA_URI_PATTERN.match(uri)
    if not match:
        return None
    try:
        return base64.b64decode(match.group("base64_data"), validate=True)
    except (binascii.Error, ValueError):
        return None


def _map_content(content: Content) -> ContentBase | None:
    """Map a single message content item onto the Purview content type that fits it.

    Returns None only for content that carries no user data at all. Anything else is
    mapped to a real content entry: a message must never reach the model with part of
    its payload unevaluated.
    """
    content_type = content.type

    if content_type in _NON_EVALUATED_CONTENT_TYPES:
        return None

    # Empty data is skipped because the Graph APIs do not support it. A request with
    # empty data cannot violate content policies because it contains no content.
    if content_type in ("text", "text_reasoning"):
        if not content.text:
            return None
        return PurviewTextContent(data=content.text)

    if content_type == "data":
        uri = getattr(content, "uri", None)
        if not uri:
            return None
        raw_data = _decode_data_uri(uri)
        if raw_data is not None:
            if not raw_data:
                return None
            return PurviewBinaryContent(data=raw_data)
        # Not a base64 data URI after all: evaluate the serialized form rather than drop it.
        return PurviewTextContent(data=_serialize_for_evaluation(content.to_dict()))

    # Everything else - uri, function_call, function_result and any content type added after this
    # code was written - is serialized whole. Serializing the entire item rather than picking out
    # named fields keeps additional_properties, which is a data channel in its own right, under
    # evaluation. Skipping a content type would be a policy bypass.
    return PurviewTextContent(data=_serialize_for_evaluation(content.to_dict()))


def _map_message_contents(message: Message) -> list[ContentBase]:
    """Map every non-empty content item of a message to Purview content entries."""
    return [purview_content for content in message.contents if (purview_content := _map_content(content))]


def _is_blocking_action(action_info: DlpActionInfo) -> bool:
    """Whether a policy action means the content must not be released.

    ``restrictAccess`` is not blocking on its own: it carries a separate ``restrictionAction`` that
    selects the enforcement mode, which may be audit, warn or allow as well as block. Only an explicit
    block mode withholds the content.
    """
    return action_info.action == DlpAction.BLOCK_ACCESS or action_info.restriction_action == RestrictionAction.BLOCK


def _blocking_actions(dlp_actions: list[DlpActionInfo]) -> list[DlpActionInfo | MutableMapping[str, Any]]:
    """Filter policy actions down to the ones that block."""
    return [action_info for action_info in dlp_actions if _is_blocking_action(action_info)]


def _normalize_location_value(data_type: str, value: str) -> str:
    """Normalize a policy location value for comparison, according to its location type.

    Application ids (GUIDs) and domain names are case-insensitive, so those fold whole. URL values are
    not. Only the scheme and the host are case-insensitive; the userinfo, path, query and fragment are
    all case-sensitive, so folding a URL whole would let a scope for ``contoso.com/public`` match a
    request for ``contoso.com/Public``. Location types that are not recognised fold whole, which matches
    more scopes rather than fewer.
    """
    if data_type.split(".")[-1].casefold().endswith("url"):
        scheme, separator, remainder = value.partition("://")
        if not separator:
            scheme, separator, remainder = "", "", value
        # The authority ends at the first path, query or fragment delimiter, whichever comes first.
        delimiter = re.search(r"[/?#]", remainder)
        authority_end = delimiter.start() if delimiter else len(remainder)
        authority, tail = remainder[:authority_end], remainder[authority_end:]
        # Credentials are case-sensitive, so only the host half of the authority folds.
        userinfo, at_sign, host = authority.rpartition("@")
        return f"{scheme.casefold()}{separator}{userinfo}{at_sign}{host.casefold()}{tail}"
    return value.casefold()


class ScopedContentProcessor:
    """Combine protection scopes, process content, and content activities logic."""

    def __init__(self, client: PurviewClient, settings: PurviewSettings, cache_provider: CacheProvider | None = None):
        self._client = client
        self._settings = settings
        cache_ttl = settings.get("cache_ttl_seconds")
        max_cache = settings.get("max_cache_size_bytes")
        self._cache: CacheProvider = cache_provider or InMemoryCacheProvider(
            default_ttl_seconds=cache_ttl if cache_ttl is not None else 14400,
            max_size_bytes=max_cache if max_cache is not None else 200 * 1024 * 1024,
        )
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def process_messages(
        self,
        messages: Iterable[Message],
        activity: Activity,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """Process messages for policy evaluation.

        Args:
            messages: The messages to process
            activity: The activity type (e.g., UPLOAD_TEXT)
            session_id: Optional session/conversation id. Else, a new GUID is generated.
            user_id: Optional user_id to use for all messages. If provided, this is the fallback.

        Returns:
            A tuple of (should_block: bool, resolved_user_id: str | None).
            The resolved_user_id can be stored and passed back when processing the response
            to ensure the same user context is maintained throughout the request/response cycle.
        """
        pc_requests, resolved_user_id = await self._map_messages(messages, activity, session_id, user_id)
        should_block = False
        for req in pc_requests:
            resp = await self._process_with_scopes(req)
            if resp.policy_actions:
                for act in resp.policy_actions:
                    if _is_blocking_action(act):
                        should_block = True
                        break
            if should_block:
                break
        return should_block, resolved_user_id

    async def _map_messages(
        self,
        messages: Iterable[Message],
        activity: Activity,
        session_id: str | None = None,
        provided_user_id: str | None = None,
    ) -> tuple[list[ProcessContentRequest], str | None]:
        """Map messages to ProcessContentRequests.

        Args:
            messages: The messages to map
            activity: The activity type
            session_id: Optional session/conversation id to use for correlation
            provided_user_id: Optional user_id to use. If provided, this is the fallback.

        Returns:
            A tuple of (requests, resolved_user_id)
        """
        results: list[ProcessContentRequest] = []
        token_info = await self._client.get_user_info_from_token(tenant_id=self._settings.get("tenant_id"))

        tenant_id = (token_info or {}).get("tenant_id") or self._settings.get("tenant_id")
        if not tenant_id or not _is_valid_guid(tenant_id):
            raise ValueError("Tenant id required or must be inferable from credential")

        resolved_user_id = (token_info or {}).get("user_id")
        resolved_author_name = None
        if not resolved_user_id:
            resolved_user_id = provided_user_id if provided_user_id and _is_valid_guid(provided_user_id) else None

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

        # Fail closed: without a resolvable user identity no policy can be evaluated,
        # so the content must not be allowed through unevaluated.
        if not resolved_user_id or not _is_valid_guid(resolved_user_id):
            raise ValueError(
                "No user id provided or inferred for Purview request. Please provide an Entra user id in each "
                "message, pass a user id to the processor, or configure the credential to authenticate to an "
                "Entra user."
            )

        for m in messages:
            message_id = m.message_id or str(uuid.uuid4())
            correlation_id = (session_id or str(uuid.uuid4())) + "@AF"
            # This would be c# ticks equivalent and needs to fit inside c# long
            base_sequence_number = time.time_ns() // 100 + 621355968000000000
            mapped_contents = _map_message_contents(m)
            activity_meta = ActivityMetadata(activity=activity)

            purview_app_location = self._settings.get("purview_app_location")
            if purview_app_location:
                policy_location = PolicyLocation(
                    data_type=purview_app_location.get_policy_location()["@odata.type"],
                    value=purview_app_location.location_value,
                )
            elif token_info and token_info.get("client_id"):
                policy_location = PolicyLocation(
                    data_type="microsoft.graph.policyLocationApplication",
                    value=token_info["client_id"],
                )
            else:
                raise ValueError("App location not provided or inferable")

            app_name = self._settings.get("app_name") or "Unknown"
            protected_app = ProtectedAppMetadata(
                name=app_name,
                version=self._settings.get("app_version", "Unknown"),
                application_location=policy_location,
            )
            integrated_app = IntegratedAppMetadata(name=app_name, version=self._settings.get("app_version", "Unknown"))
            device_meta = DeviceMetadata(
                operating_system_specifications=OperatingSystemSpecifications(
                    operating_system_platform="Unknown", operating_system_version="Unknown"
                )
            )

            for index, purview_content in enumerate(mapped_contents):
                content_entry = ProcessConversationMetadata(
                    identifier=message_id if index == 0 else f"{message_id}-{index}",
                    content=purview_content,
                    name=f"Agent Framework Message {message_id}",
                    is_truncated=False,
                    correlation_id=correlation_id,
                    sequence_number=base_sequence_number + index,
                )
                ctp = ContentToProcess(
                    content_entry=content_entry,
                    activity_metadata=activity_meta,
                    device_metadata=device_meta,
                    integrated_app_metadata=integrated_app,
                    protected_app_metadata=protected_app,
                )
                req = ProcessContentRequest(
                    content_to_process=ctp,
                    user_id=resolved_user_id,  # Use the resolved user_id for all messages
                    tenant_id=tenant_id,
                    correlation_id=correlation_id,
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

        if cached_ps_resp is not None and isinstance(cached_ps_resp, ProtectionScopesResponse):
            return await self._process_with_cached_scopes(pc_request, cached_ps_resp, cache_key)

        pc_request.process_inline = True
        # The background refresh gets its own copy: the foreground call mutates
        # process_inline and scope_identifier on this request while that task runs.
        task = asyncio.create_task(self._refresh_protection_scopes_background(ps_req, cache_key, copy(pc_request)))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return await self._call_process_content(pc_request, cache_key, dlp_actions=[])

    async def _process_with_cached_scopes(
        self,
        pc_request: ProcessContentRequest,
        ps_resp: ProtectionScopesResponse,
        cache_key: str,
    ) -> ProcessContentResponse:
        if ps_resp.scope_identifier:
            pc_request.scope_identifier = ps_resp.scope_identifier

        should_process, dlp_actions, execution_mode = self._check_applicable_scopes(pc_request, ps_resp)

        if should_process:
            # Only an explicitly offline scope may skip inline evaluation. executionMode is an
            # evolvable enum, so any unrecognised value must fail closed and be evaluated inline.
            evaluate_offline = execution_mode == ExecutionMode.EVALUATE_OFFLINE
            pc_request.process_inline = not evaluate_offline

            # If execution mode is offline, queue the PC request in background
            if evaluate_offline:
                task = asyncio.create_task(self._process_content_background(pc_request, cache_key))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
                # Offline evaluation is asynchronous, but an explicit block action already known
                # from the cached scopes must still be enforced rather than discarded.
                return ProcessContentResponse(
                    id="204",
                    correlation_id=pc_request.correlation_id,
                    policy_actions=_blocking_actions(dlp_actions) or None,
                )

            return await self._call_process_content(pc_request, cache_key, dlp_actions=dlp_actions)

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

    async def _call_process_content(
        self,
        pc_request: ProcessContentRequest,
        cache_key: str,
        dlp_actions: list[DlpActionInfo],
    ) -> ProcessContentResponse:
        pc_resp = await self._client.process_content(pc_request)

        if pc_request.scope_identifier and pc_resp.protection_scope_state == ProtectionScopeState.MODIFIED:
            await self._cache.remove(cache_key)

        if dlp_actions:
            pc_resp.policy_actions = self._combine_policy_actions(pc_resp.policy_actions, dlp_actions)
        return pc_resp

    async def _refresh_protection_scopes_background(
        self, ps_req: ProtectionScopesRequest, cache_key: str, pc_request: ProcessContentRequest
    ) -> None:
        """Fetch protection scopes and warm the cache without blocking the foreground call."""
        ttl = self._settings.get("cache_ttl_seconds")
        ttl_seconds = ttl if ttl is not None else 14400
        try:
            ps_resp = await self._client.get_protection_scopes(ps_req)
            await self._cache.set(cache_key, ps_resp, ttl_seconds=ttl_seconds)
            should_process, _, _ = self._check_applicable_scopes(pc_request, ps_resp)
            if not should_process:
                ca_req = ContentActivitiesRequest(
                    user_id=pc_request.user_id,
                    tenant_id=pc_request.tenant_id,
                    content_to_process=pc_request.content_to_process,
                    correlation_id=pc_request.correlation_id,
                )
                await self._send_content_activities_background(ca_req)
        except PurviewPaymentRequiredError as ex:
            tenant_payment_cache_key = f"purview:payment_required:{ps_req.tenant_id}"
            await self._cache.set(tenant_payment_cache_key, ex, ttl_seconds=ttl_seconds)
            logger.warning("Background protection scopes refresh failed with payment required: %s", ex)
        except Exception as ex:
            logger.warning("Background protection scopes refresh failed: %s", ex)

    async def _process_content_background(self, pc_request: ProcessContentRequest, cache_key: str) -> None:
        """Process content in background for offline execution mode."""
        try:
            pc_resp = await self._client.process_content(pc_request)

            # If protection scopes changed, invalidate cache and retry once.
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
        combined: dict[tuple[DlpAction | None, RestrictionAction | None], DlpActionInfo] = {}
        for action_info in (existing or []) + new_actions:
            combined.setdefault((action_info.action, action_info.restriction_action), action_info)
        return list(combined.values())

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
                        and isinstance(loc.value, str)
                        and isinstance(location.value, str)
                        and _normalize_location_value(location.data_type, loc.value)
                        == _normalize_location_value(location.data_type, location.value)
                    ):
                        location_match = True
                        break
            if activity_match and location_match:
                should_process = True

                # Only an explicitly offline scope may skip inline evaluation. execution_mode is an
                # evolvable enum, so any unrecognised value is upgraded to inline (fail closed).
                if scope.execution_mode != ExecutionMode.EVALUATE_OFFLINE:
                    execution_mode = ExecutionMode.EVALUATE_INLINE

                if scope.policy_actions:
                    dlp_actions.extend(scope.policy_actions)
        return should_process, dlp_actions, execution_mode
