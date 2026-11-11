# Copyright (c) Microsoft. All rights reserved.

"""Read-only approval validation before the Responses SDK opens a stream."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any, cast

from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    read_request_id,
    reset_request_context,
    set_request_context,
)
from azure.ai.agentserver.core.platform_headers import FOUNDRY_CALL_ID, USER_ID
from azure.ai.agentserver.responses import (
    FoundryApiError,
    PlatformContext,
    ResponseContext,
)
from azure.ai.agentserver.responses._egress import strip_internal_metadata
from azure.ai.agentserver.responses.hosting import ResponsesAgentServerHost
from azure.ai.agentserver.responses.hosting._endpoint_handler import _ResponseEndpointHandler  # pyright: ignore[reportPrivateUsage]
from azure.ai.agentserver.responses.hosting._request_parsing import (
    _prevalidate_identity_payload,  # pyright: ignore[reportPrivateUsage]
    _resolve_conversation_id,  # pyright: ignore[reportPrivateUsage]
    _resolve_identity_fields,  # pyright: ignore[reportPrivateUsage]
    _resolve_session_id,  # pyright: ignore[reportPrivateUsage]
)
from azure.ai.agentserver.responses.hosting._validation import (
    ERROR_SOURCE_PLATFORM,
    error_response,
    is_platform_error,
    parse_and_validate_create_response,
)
from azure.ai.agentserver.responses.models import CreateResponse
from azure.ai.agentserver.responses.models._helpers import get_input_expanded, to_output_item
from azure.ai.agentserver.responses.models.runtime import ResponseModeFlags
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from ._approvals import _InvalidApproval  # pyright: ignore[reportPrivateUsage]
from ._scope import FoundryRequestScope
from ._workflow_state import FoundryWorkflowBindingStore

logger = logging.getLogger(__name__)


_Preflight = Callable[[CreateResponse, ResponseContext, FoundryAgentRequestContext], Awaitable[None]]


def _create_route_path(prefix: str) -> str:
    normalized = prefix.strip()
    if normalized and not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return f"{normalized.rstrip('/')}/responses"


def bind_approval_preflight(host: ResponsesAgentServerHost, *, prefix: str, preflight: _Preflight) -> None:
    """Wrap only SDK create; delegate malformed requests and draining to the SDK."""
    for index, route in enumerate(host.router.routes):
        if (
            not isinstance(route, Route)
            or route.path != _create_route_path(prefix)
            or route.name != "create_response"
            or "POST" not in (route.methods or ())
        ):
            continue
        handler = cast(Callable[[Request], Awaitable[Response]], route.endpoint)
        endpoint = getattr(handler, "__self__", None)
        if not isinstance(endpoint, _ResponseEndpointHandler):
            raise RuntimeError("The Responses SDK create endpoint is unavailable for approval preflight.")

        async def checked_create(
            request: Request,
            *,
            endpoint: _ResponseEndpointHandler = endpoint,
            handler: Callable[[Request], Awaitable[Response]] = handler,
        ) -> Response:
            if endpoint._is_draining:  # pyright: ignore[reportPrivateUsage]
                return await handler(request)

            # The SDK mutates the cached JSON when stripping internal metadata.
            # Inspect a copy so its own validation receives the original request.
            try:
                payload = deepcopy(await request.json())
                strip_internal_metadata(payload)
                _prevalidate_identity_payload(payload)
                parsed = parse_and_validate_create_response(
                    payload,
                    options=endpoint._runtime_options,  # pyright: ignore[reportPrivateUsage]
                )
                response_id, agent_reference = _resolve_identity_fields(parsed, request_headers=request.headers)
                session_id = _resolve_session_id(
                    parsed,
                    payload,
                    env_session_id=host.config.session_id or "",
                    agent_reference=agent_reference,
                )
            except (TypeError, ValueError, KeyError, AttributeError):
                return await handler(request)

            platform = PlatformContext(
                user_id_key=request.headers.get(USER_ID),
                call_id=request.headers.get(FOUNDRY_CALL_ID),
            )
            platform_context = FoundryAgentRequestContext(
                user_id=platform.user_id_key or None,
                call_id=platform.call_id or None,
                session_id=session_id,
            )
            previous = parsed.get("previous_response_id")
            previous = previous if isinstance(previous, str) and previous else None
            conversation_id = _resolve_conversation_id(parsed)
            input_items = [
                output
                for item in get_input_expanded(parsed)
                if (output := to_output_item(item, response_id)) is not None
            ]
            context = ResponseContext(
                response_id=response_id,
                request=parsed,
                mode_flags=ResponseModeFlags(
                    stream=bool(parsed.get("stream")),
                    store=parsed.get("store") is not False,
                    background=bool(parsed.get("background")),
                ),
                provider=endpoint._provider,  # pyright: ignore[reportPrivateUsage]
                input_items=input_items,
                previous_response_id=previous,
                conversation_id=conversation_id,
                platform_context=platform,
                session_id=session_id,
            )
            headers = endpoint._session_headers(session_id)  # pyright: ignore[reportPrivateUsage]
            request_id = read_request_id(request.scope)
            token = set_request_context(platform_context)
            try:
                await preflight(parsed, context, platform_context)
            except _InvalidApproval as exc:
                return error_response(exc, headers, request_id=request_id)
            except Exception as exc:
                logger.error("Responses approval preflight failed (%s).", type(exc).__name__)
                # A backend may raise ValueError; it is not an invalid request.
                error = RuntimeError("Responses approval preflight failed; inspect the host logs.")
                source = ERROR_SOURCE_PLATFORM if is_platform_error(exc) or isinstance(exc, FoundryApiError) else None
                return error_response(error, headers, request_id=request_id, error_source=source)
            finally:
                reset_request_context(token)
            return await handler(request)

        host.router.routes[index] = Route(
            route.path,
            endpoint=checked_create,
            methods=list(route.methods or ()),
            name=route.name,
            include_in_schema=route.include_in_schema,
        )
        return
    raise RuntimeError("The Responses SDK create route is unavailable for approval preflight.")


def approval_controls(items: list[Mapping[str, Any]]) -> list[str]:
    """Extract validated MCP decisions without applying generic reply rules."""
    ids: list[str] = []
    for item in items:
        if item.get("type") != "mcp_approval_response":
            continue
        wire_id, decision = item.get("approval_request_id"), item.get("approve")
        if not isinstance(wire_id, str) or not wire_id or type(decision) is not bool:
            raise _InvalidApproval("An approval reply requires its exact ID and a boolean decision.")
        ids.append(wire_id)
    return ids


def has_unresolved_input(request: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> bool:
    """Detect input references the SDK silently omitted during resolution."""
    return len(get_input_expanded(cast(CreateResponse, request))) != len(items)


async def preflight_workflow_approvals(
    request: CreateResponse,
    context: ResponseContext,
    platform_context: FoundryAgentRequestContext,
    host: ResponsesAgentServerHost,
) -> None:
    """Check a native MCP batch against its exact completed checkpoint pair."""
    items = [cast(Mapping[str, Any], item) for item in await context.get_input_items()]
    ids = approval_controls(items)
    previous = request.get("previous_response_id")
    previous = previous if isinstance(previous, str) and previous else None
    if previous is None and context.conversation_id is None:
        if ids:
            raise _InvalidApproval("The approval has no pending workflow checkpoint.")
        return
    scope = FoundryRequestScope.from_context(host.config, platform_context, local_session_id=context.response_id)
    storage = FoundryWorkflowBindingStore(scope)
    record = None
    if previous is not None:
        record, _ = await storage.get_response(previous)
        if record is not None and record.status == "completed" and record.binding.conversation_id is None:
            head, _ = await storage.get_head(record.binding.lineage_id, None)
        else:
            head = None
    else:
        head, _ = await storage.get_head(context.response_id, context.conversation_id)
        if head is not None and head.binding is not None:
            record, _ = await storage.get_response(head.binding.response_id)

    if (
        record is None
        or record.status != "completed"
        or record.snapshot is None
        or head is None
        or head.blocked
        or head.response_id is not None
        or head.binding != record.binding
    ):
        if ids:
            raise _InvalidApproval("The approval is unavailable in the current workflow checkpoint.")
        return
    aliases = record.approvals or {}
    output = record.snapshot.get("output")
    if not isinstance(output, list):
        raise RuntimeError("The workflow approval snapshot has invalid output.")
    approval_ids: set[str] = set()
    for raw_item in cast(list[Any], output):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, Any], raw_item)
        wire_id = item.get("id")
        if item.get("type") == "mcp_approval_request" and isinstance(wire_id, str) and wire_id in aliases:
            approval_ids.add(wire_id)
    if not approval_ids:
        if ids:
            raise _InvalidApproval("The workflow has no pending MCP approval batch.")
        return
    if request.get("store") is False:
        raise _InvalidApproval("Approval continuation requires store=true.")
    if has_unresolved_input(request, items):
        raise _InvalidApproval("Pending workflow approvals cannot include unresolved input references.")
    controls: list[str] = []
    for item in items:
        item_type = item.get("type")
        if item_type == "mcp_approval_response":
            wire_id = item.get("approval_request_id")
            if wire_id not in approval_ids:
                raise _InvalidApproval("An approval reply must match this exact pending checkpoint.")
        elif item_type in ("function_call_output", "computer_call_output"):
            wire_id = item.get("call_id")
            if not isinstance(wire_id, str) or wire_id not in aliases or wire_id in approval_ids:
                raise _InvalidApproval("A reply must match this exact pending checkpoint.")
        else:
            raise _InvalidApproval("Pending workflow approvals cannot be mixed with new input.")
        controls.append(cast(str, wire_id))
    if len(controls) != len(set(controls)) or set(controls) != set(aliases):
        raise _InvalidApproval("Answer exactly the complete pending workflow request batch.")
