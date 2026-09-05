# Copyright (c) Microsoft. All rights reserved.

"""Native AG-UI orchestration for MAF Workflow streams."""

from __future__ import annotations

import inspect
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from functools import partial
from types import UnionType
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from ag_ui.core import (
    ActivitySnapshotEvent,
    BaseEvent,
    CustomEvent,
    RunErrorEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageEndEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    CheckpointStorage,
    Content,
    Message,
    Workflow,
    WorkflowRunState,
)
from agent_framework._workflows._typing_utils import (  # pyright: ignore[reportPrivateUsage]
    is_instance_of,
    try_coerce_to_type,
)
from agent_framework.observability import (
    _use_telemetry_conversation_id,  # pyright: ignore[reportPrivateUsage]
)

from ._message_adapters import normalize_agui_input_messages
from ._run_common import (
    FlowState,
    _approval_interrupt_for_function_call,  # pyright: ignore[reportPrivateUsage]
    _approval_response_schema,  # pyright: ignore[reportPrivateUsage]
    _build_run_finished_event,
    _close_reasoning_block,
    _emit_content,
    _extract_resume_payload,
    _iterate_with_context,
    _normalize_resume_interrupts,
    _resume_contract_error,
)
from ._utils import canonical_function_arguments, generate_event_id, make_json_safe

logger = logging.getLogger(__name__)


_TERMINAL_STATES: set[str] = {
    WorkflowRunState.IDLE.value,
    WorkflowRunState.IDLE_WITH_PENDING_REQUESTS.value,
    WorkflowRunState.CANCELLED.value,
}

_WORKFLOW_EVENT_BASE_FIELDS: set[str] = {
    "type",
    "data",
    "origin",
    "state",
    "details",
    "executor_id",
    "_request_id",
    "_source_executor_id",
    "_request_type",
    "_response_type",
    "iteration",
}

_INTERRUPT_CARD_EVENT_NAME = "WorkflowInterruptEvent"
# Tool content admitted from streaming updates regardless of role. Approval requests are
# deliberately excluded: workflow approvals resume through request_info pending state, and an
# approval interrupt emitted from streamed content would have no pending request to resume against.
_TOOL_CONTENT_TYPES = {"function_call", "function_result", "mcp_server_tool_call", "mcp_server_tool_result"}


def _json_schema_for_response_type(response_type: Any) -> dict[str, Any] | None:
    """Build a lightweight response schema for a workflow request_info response type."""
    if response_type is None:
        return None

    target_type = get_origin(response_type) or response_type
    if target_type is Any:
        return {"description": "Resolved workflow response payload."}
    if target_type is dict:
        return {"type": "object", "additionalProperties": True}
    if target_type is list:
        item_types = get_args(response_type)
        schema: dict[str, Any] = {"type": "array"}
        if item_types:
            item_schema = _json_schema_for_response_type(item_types[0])
            if item_schema is not None:
                schema["items"] = item_schema
        return schema
    if target_type is str:
        return {"type": "string"}
    if target_type is bool:
        return {"type": "boolean"}
    if target_type is int:
        return {"type": "integer"}
    if target_type is float:
        return {"type": "number"}
    if target_type in {Message, Content}:
        return {"type": "object", "additionalProperties": True}
    return {"description": f"Resolved workflow response payload for {getattr(target_type, '__name__', target_type)}."}


def _workflow_interrupt_value(request_data: Any) -> Any:
    """Normalize workflow request data into legacy metadata value form."""
    safe_request_data = make_json_safe(request_data)
    if isinstance(safe_request_data, dict):
        return safe_request_data
    return {"data": safe_request_data}


def _workflow_interrupt_metadata(request_payload: dict[str, Any], value: Any) -> dict[str, Any]:
    """Build Agent Framework metadata for workflow request_info interrupts."""
    agent_framework_metadata = {
        key: make_json_safe(value)
        for key, value in {
            "type": "workflow_request_info",
            "request_id": request_payload.get("request_id"),
            "source_executor_id": request_payload.get("source_executor_id"),
            "request_type": request_payload.get("request_type"),
            "response_type": request_payload.get("response_type"),
            "data": request_payload.get("data"),
            "value": value,
        }.items()
        if value is not None
    }
    return {"agent_framework": agent_framework_metadata}


async def _pending_request_events(workflow: Workflow) -> dict[str, Any]:
    """Best-effort retrieval of pending request_info events from workflow context."""
    runner_context = getattr(workflow, "_runner_context", None)
    if runner_context is None:
        return {}

    get_pending = getattr(runner_context, "get_pending_request_info_events", None)
    if get_pending is None:
        return {}

    try:
        pending = await get_pending()
    except Exception:  # pragma: no cover - defensive for internal API drift
        logger.warning("Could not read pending workflow requests", exc_info=True)
        return {}

    if isinstance(pending, dict):
        return cast(dict[str, Any], pending)
    return {}


async def _pending_request_events_from_checkpoint(
    checkpoint_id: str,
    checkpoint_storage: CheckpointStorage,
) -> dict[str, Any]:
    """Read pending request_info events from a persisted checkpoint without restoring it.

    Resume responses are coerced against the requests that were pending when the
    checkpoint was written. On a cold checkpoint resume those requests are not yet live
    on the workflow instance, so the coercion cannot see them. Reading
    ``pending_request_info_events`` straight from the persisted ``WorkflowCheckpoint``
    exposes them without running any executor ``on_checkpoint_restore`` hook; the single
    ``workflow.run(checkpoint_id=...)`` then performs the one real restore, so the
    restore -- and every custom restore hook -- runs exactly once per resume.
    """
    try:
        checkpoint = await checkpoint_storage.load(checkpoint_id)
    except Exception:
        logger.warning(
            "Could not load checkpoint for resume-response coercion; the core run will surface any error.",
            exc_info=True,
        )
        return {}
    return dict(checkpoint.pending_request_info_events)


def _interrupt_entry_for_request_event(request_event: Any) -> dict[str, Any] | None:
    """Build AG-UI interrupt payload from a workflow request_info event."""
    request_payload = _request_payload_from_request_event(request_event)
    if request_payload is None:
        return None

    value = _workflow_interrupt_value(request_payload.get("data"))
    request_data = getattr(request_event, "data", None)
    if (
        isinstance(request_data, Content)
        and request_data.type == "function_approval_request"
        and request_data.function_call is not None
    ):
        workflow_metadata = _workflow_interrupt_metadata(request_payload, value)["agent_framework"]
        workflow_metadata.pop("type", None)
        response_schema = (
            _approval_response_schema()
            if request_data.function_call.additional_properties.get("server_label")
            else None
        )
        return _approval_interrupt_for_function_call(
            interrupt_id=str(request_payload["request_id"]),
            function_call=request_data.function_call,
            metadata=workflow_metadata,
            response_schema=response_schema,
        )

    entry: dict[str, Any] = {
        "id": str(request_payload["request_id"]),
        "reason": "input_required",
        "value": value,
        "metadata": _workflow_interrupt_metadata(request_payload, value),
    }
    response_schema = _json_schema_for_response_type(getattr(request_event, "response_type", None))
    if response_schema is not None:
        entry["responseSchema"] = response_schema
    return entry


def _interrupts_from_pending_requests(pending_events: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert pending workflow request events into AG-UI interrupt descriptors."""
    interrupts: list[dict[str, Any]] = []
    for request_event in pending_events.values():
        entry = _interrupt_entry_for_request_event(request_event)
        if entry is not None:
            interrupts.append(entry)
    return interrupts


def _request_payload_from_request_event(request_event: Any) -> dict[str, Any] | None:
    """Build the normalized request_info payload from a workflow request event."""
    request_id = getattr(request_event, "request_id", None)
    if not request_id:
        return None

    request_type = getattr(request_event, "request_type", None)
    response_type = getattr(request_event, "response_type", None)
    request_data = make_json_safe(getattr(request_event, "data", None))
    return {
        "request_id": request_id,
        "source_executor_id": getattr(request_event, "source_executor_id", None),
        "request_type": getattr(request_type, "__name__", str(request_type) if request_type else None),
        "response_type": getattr(response_type, "__name__", str(response_type) if response_type else None),
        "data": request_data,
    }


def _extract_responses_from_messages(messages: list[Message]) -> dict[str, Any]:
    """Extract request-info responses from incoming messages.

    Handles both ``function_result`` content (keyed by ``call_id``) and
    ``function_approval_response`` content (keyed by ``id``), so that
    approval decisions sent via messages are forwarded into the workflow
    responses map.
    """
    responses: dict[str, Any] = {}
    for message in messages:
        for content in message.contents:
            if content.type == "function_result" and content.call_id:
                value = _coerce_json_value(content.result)
                responses[str(content.call_id)] = value
            elif content.type == "function_approval_response" and getattr(content, "id", None):
                approval_value: dict[str, Any] = {
                    "approved": getattr(content, "approved", False),
                    "id": str(content.id),
                }
                func_call = getattr(content, "function_call", None)
                if func_call is not None:
                    approval_value["function_call"] = make_json_safe(func_call.to_dict())
                responses[str(content.id)] = approval_value
    return responses


def _resume_to_workflow_responses(resume_payload: Any) -> dict[str, Any]:
    """Convert AG-UI resume payloads into workflow responses."""
    responses: dict[str, Any] = {}
    for interrupt in _normalize_resume_interrupts(resume_payload):
        if interrupt.get("status") not in {None, "resolved"}:
            continue
        value = _coerce_json_value(interrupt.get("value"))
        responses[str(interrupt["id"])] = value
    return responses


def _merge_workflow_response_sources(
    resume_responses: dict[str, Any],
    message_responses: dict[str, Any],
) -> dict[str, Any]:
    """Merge workflow response sources with explicit resume payloads taking precedence."""
    if not resume_responses:
        return dict(message_responses)

    responses = dict(message_responses)
    responses.update(resume_responses)
    return responses


def _resume_entries_to_workflow_responses(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert validated resume entries into workflow responses."""
    responses: dict[str, Any] = {}
    for entry in entries:
        if entry.get("status") == "resolved":
            responses[str(entry["interrupt_id"])] = _coerce_json_value(entry.get("payload"))
    return responses


def _pending_workflow_interrupt_ids(pending_events: dict[str, Any]) -> set[str]:
    """Return canonical interrupt ids for pending workflow request_info events."""
    pending_ids: set[str] = set()
    for request_id, request_event in pending_events.items():
        pending_id = getattr(request_event, "request_id", None) or request_id
        if pending_id:
            pending_ids.add(str(pending_id))
    return pending_ids


def _resume_error_for_pending_workflow_requests(
    resume_entries: list[dict[str, Any]],
) -> RunErrorEvent | None:
    """Return a workflow resume error for unsupported canonical resume entries."""
    for entry in resume_entries:
        interrupt_id = str(entry["interrupt_id"])
        status = entry.get("status")
        if status not in {None, "resolved", "cancelled"}:
            return RunErrorEvent(
                message=f"Unsupported workflow resume status '{status}' for interruptId '{interrupt_id}'.",
                code="WORKFLOW_RESUME_INVALID",
            )
    return None


def _coerce_json_value(value: Any) -> Any:
    """Parse JSON strings when possible; otherwise return the original value."""
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped:
        return value

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _response_type_name(request_event: Any) -> str:
    """Return a stable string name for a request's expected response type."""
    response_type = getattr(request_event, "response_type", None)
    if response_type is None:
        return "unknown"
    return getattr(response_type, "__name__", str(response_type))


def _coerce_content(value: Any) -> Content | None:
    """Best-effort conversion of JSON-like payloads into Content."""
    if isinstance(value, Content):
        return value

    candidate = _coerce_json_value(value)
    if not isinstance(candidate, dict):
        return None

    content_payload = dict(candidate)
    if "type" not in content_payload and {"approved", "id", "function_call"}.issubset(content_payload):
        content_payload["type"] = "function_approval_response"

    try:
        return Content.from_dict(content_payload)
    except Exception:
        return None


def _coerce_message_content(content_payload: Any) -> Content | None:
    """Best-effort conversion of AG-UI message content items into Content."""
    if isinstance(content_payload, Content):
        return content_payload
    if isinstance(content_payload, str):
        return Content.from_text(text=content_payload)
    if isinstance(content_payload, dict):
        content_dict = dict(content_payload)
        if content_dict.get("type") == "text":
            if isinstance(content_dict.get("text"), str):
                return Content.from_text(text=cast(str, content_dict["text"]))
            if isinstance(content_dict.get("content"), str):
                return Content.from_text(text=cast(str, content_dict["content"]))
        try:
            return Content.from_dict(content_dict)
        except Exception:
            return None
    return None


def _coerce_message(value: Any) -> Message | None:
    """Best-effort conversion of JSON-like payloads into Message."""
    if isinstance(value, Message):
        return value

    candidate = _coerce_json_value(value)
    if isinstance(candidate, str):
        return Message(role="user", contents=[Content.from_text(text=candidate)])
    if not isinstance(candidate, dict):
        return None

    role = str(candidate.get("role") or "user")
    author_name = candidate.get("author_name") or candidate.get("authorName")
    message_id = candidate.get("message_id") or candidate.get("messageId")

    contents_payload = candidate.get("contents")
    if contents_payload is None and "content" in candidate:
        contents_payload = candidate.get("content")

    normalized_contents: list[Content] = []
    if isinstance(contents_payload, list):
        for item in contents_payload:
            parsed_content = _coerce_message_content(item)
            if parsed_content is None:
                return None
            normalized_contents.append(parsed_content)
    elif contents_payload is not None:
        parsed_content = _coerce_message_content(contents_payload)
        if parsed_content is None:
            return None
        normalized_contents.append(parsed_content)
    else:
        normalized_contents.append(Content.from_text(text=""))

    return Message(
        role=role,
        contents=normalized_contents,
        author_name=str(author_name) if isinstance(author_name, str) else None,
        message_id=str(message_id) if isinstance(message_id, str) else None,
    )


def _approval_argument_value_matches(original_value: Any, edited_value: Any) -> bool:
    """Return whether an edited approval argument preserves its JSON value type."""
    if isinstance(original_value, bool):
        return isinstance(edited_value, bool)
    if isinstance(original_value, int) and not isinstance(original_value, bool):
        return isinstance(edited_value, int) and not isinstance(edited_value, bool)
    if isinstance(original_value, float):
        return isinstance(edited_value, (int, float)) and not isinstance(edited_value, bool)
    if isinstance(original_value, str):
        return isinstance(edited_value, str)
    if isinstance(original_value, list):
        return isinstance(edited_value, list)
    if isinstance(original_value, dict):
        return isinstance(edited_value, dict)
    return True


def _coerce_compact_approval_response(request_data: Content, candidate: dict[str, Any]) -> Content | None:
    """Reconstruct a workflow approval response from client-owned decision fields."""
    if {"type", "id", "function_call"}.intersection(candidate):
        return None

    approved = candidate.get("approved", candidate.get("accepted"))
    if not isinstance(approved, bool):
        return None

    direct_edited_arguments = {
        key: value for key, value in candidate.items() if key not in {"approved", "accepted", "editedArgs"}
    }
    standard_edited_arguments = candidate.get("editedArgs")
    if request_data.function_call is None:
        return None
    if (
        direct_edited_arguments or standard_edited_arguments is not None
    ) and request_data.function_call.additional_properties.get("server_label"):
        return None

    original_arguments = request_data.function_call.parse_arguments() or {}
    if standard_edited_arguments is not None:
        if not isinstance(standard_edited_arguments, dict) or direct_edited_arguments:
            return None
        edited_arguments = cast(dict[str, Any], standard_edited_arguments)
        if set(edited_arguments) != set(original_arguments):
            return None
        final_arguments = dict(edited_arguments)
    else:
        edited_arguments = direct_edited_arguments
        if not set(edited_arguments).issubset(original_arguments):
            return None
        final_arguments = {**original_arguments, **edited_arguments}

    if any(
        not _approval_argument_value_matches(original_arguments[name], edited_arguments[name])
        for name in edited_arguments
    ):
        return None
    if not edited_arguments:
        return request_data.to_function_approval_response(approved)

    edited_function_call = Content.from_function_call(
        call_id=request_data.function_call.call_id or "",
        name=request_data.function_call.name or "",
        arguments=final_arguments,
        informational_only=request_data.function_call.informational_only,
        annotations=request_data.function_call.annotations,
        additional_properties=request_data.function_call.additional_properties,
        raw_representation=request_data.function_call.raw_representation,
    )
    response = request_data.to_function_approval_response(approved)
    response.function_call = edited_function_call
    return response


def _without_optional(annotation: Any) -> Any:
    """Unwrap ``X | None`` so optional fields normalize like their plain counterpart."""
    if get_origin(annotation) not in (Union, UnionType):
        return annotation
    members = [member for member in get_args(annotation) if member is not type(None)]
    return members[0] if len(members) == 1 else annotation


def _normalize_agui_message_fields(response_type: Any, candidate: Any) -> Any:
    """Convert AG-UI message payloads for fields the response type declares as Message.

    Core coercion only understands the canonical ``contents`` form, so AG-UI wire shapes
    (``{"role": ..., "content": ...}`` and bare strings) are translated here.
    """
    if not isinstance(candidate, dict):
        return candidate

    try:
        field_types = get_type_hints(response_type)
    except Exception:
        return candidate

    normalized = dict(cast(dict[str, Any], candidate))
    for name, annotation in field_types.items():
        if name not in normalized:
            continue
        annotation = _without_optional(annotation)
        target_type = get_origin(annotation) or annotation
        if target_type is Message:
            message = _coerce_message(normalized[name])
            if message is not None:
                normalized[name] = message
        elif target_type is list and get_args(annotation)[:1] == (Message,):
            items = normalized[name]
            if not isinstance(items, list):
                continue
            messages = [_coerce_message(item) for item in cast(list[Any], items)]
            if all(message is not None for message in messages):
                normalized[name] = messages
    return normalized


def _coerce_response_for_request(request_event: Any, value: Any) -> Any | None:
    """Coerce a candidate value into the request's expected response type."""
    response_type = getattr(request_event, "response_type", None)
    candidate = _coerce_json_value(value)

    if response_type is None:
        return candidate

    target_type = get_origin(response_type) or response_type
    if target_type is Any:
        return candidate
    if target_type is dict:
        return candidate if isinstance(candidate, dict) else None
    if target_type is list:
        if not isinstance(candidate, list):
            return None
        item_types = get_args(response_type)
        if not item_types:
            return candidate
        item_type = get_origin(item_types[0]) or item_types[0]
        if item_type is Message:
            converted_messages: list[Message] = []
            for item in candidate:
                message = _coerce_message(item)
                if message is None:
                    return None
                converted_messages.append(message)
            return converted_messages
        if item_type is Content:
            converted_contents: list[Content] = []
            for item in candidate:
                content = _coerce_content(item)
                if content is None:
                    return None
                converted_contents.append(content)
            return converted_contents
        return candidate
    if target_type is str:
        if isinstance(value, str):
            return value
        if isinstance(candidate, str):
            return candidate
        return json.dumps(make_json_safe(candidate))
    if target_type is Message:
        return _coerce_message(candidate)
    if target_type is Content:
        request_data = getattr(request_event, "data", None)
        if (
            isinstance(request_data, Content)
            and request_data.type == "function_approval_request"
            and isinstance(candidate, dict)
        ):
            compact_response = _coerce_compact_approval_response(request_data, cast(dict[str, Any], candidate))
            if compact_response is not None:
                return compact_response
        return _coerce_content(candidate)
    if target_type is bool:
        return candidate if isinstance(candidate, bool) else None
    if target_type is int:
        return candidate if isinstance(candidate, int) and not isinstance(candidate, bool) else None
    if target_type is float:
        return candidate if isinstance(candidate, (int, float)) and not isinstance(candidate, bool) else None
    if isinstance(target_type, type):
        coerced = try_coerce_to_type(_normalize_agui_message_fields(response_type, candidate), response_type)
        return coerced if is_instance_of(coerced, response_type) else None

    # Unknown typing metadata: preserve value as-is.
    return candidate


def _is_compact_approval_response_payload(value: Any) -> bool:
    """Return whether a value contains only client-owned approval decision fields."""
    candidate = _coerce_json_value(value)
    return isinstance(candidate, dict) and not {"type", "id", "function_call"}.intersection(
        cast(dict[str, Any], candidate)
    )


def _approval_response_matches_request(
    request_id: str,
    request_event: Any,
    response: Any,
    *,
    allow_edited_arguments: bool = False,
) -> bool:
    """Check whether an approval response matches the pending approval request."""
    request_data = getattr(request_event, "data", None)
    if not isinstance(request_data, Content) or request_data.type != "function_approval_request":
        return True

    if not isinstance(response, Content) or response.type != "function_approval_response":
        return False

    if str(getattr(response, "id", "")) != request_id:
        return False

    request_call = getattr(request_data, "function_call", None)
    response_call = getattr(response, "function_call", None)
    if request_call is None or response_call is None:
        return False

    if getattr(response_call, "name", None) != getattr(request_call, "name", None):
        return False

    if allow_edited_arguments:
        return True
    return canonical_function_arguments(response_call) == canonical_function_arguments(request_call)


def _single_pending_response_from_value(pending_events: dict[str, Any], value: Any) -> dict[str, Any]:
    """Map a scalar resume payload to the single pending request (if unambiguous)."""
    if value is None or len(pending_events) != 1:
        return {}

    request_event = next(iter(pending_events.values()))
    request_id = getattr(request_event, "request_id", None)
    if not request_id:
        return {}

    coerced_value = _coerce_response_for_request(request_event, value)
    if coerced_value is None:
        logger.info(
            "Ignoring pending request response for request_id=%s: expected %s",
            request_id,
            _response_type_name(request_event),
        )
        return {}

    if not _approval_response_matches_request(
        str(request_id),
        request_event,
        coerced_value,
        allow_edited_arguments=_is_compact_approval_response_payload(value),
    ):
        logger.info(
            "Ignoring pending request response for request_id=%s: approval response does not match pending request",
            request_id,
        )
        return {}

    return {str(request_id): coerced_value}


def _coerce_responses_for_pending_requests(
    responses: dict[str, Any],
    pending_events: dict[str, Any],
) -> dict[str, Any]:
    """Coerce resume responses to the expected types for known pending requests."""
    if not responses or not pending_events:
        return responses

    normalized: dict[str, Any] = {}
    pending_by_id: dict[str, Any] = {}
    for request_id, event in pending_events.items():
        pending_by_id[str(request_id)] = event
        event_request_id = getattr(event, "request_id", None)
        if event_request_id:
            pending_by_id[str(event_request_id)] = event

    for request_id, value in responses.items():
        request_key = str(request_id)
        request_event = pending_by_id.get(request_key)
        if request_event is None:
            normalized[request_key] = value
            continue

        coerced_value = _coerce_response_for_request(request_event, value)
        if coerced_value is None:
            logger.info(
                "Ignoring resume response for request_id=%s: expected %s",
                request_key,
                _response_type_name(request_event),
            )
            continue
        if not _approval_response_matches_request(
            request_key,
            request_event,
            coerced_value,
            allow_edited_arguments=_is_compact_approval_response_payload(value),
        ):
            logger.info(
                "Ignoring resume response for request_id=%s: approval response does not match pending request",
                request_key,
            )
            continue
        normalized[request_key] = coerced_value
    return normalized


def _coerce_responses_for_pending_requests_strict(
    responses: dict[str, Any],
    pending_events: dict[str, Any],
) -> tuple[dict[str, Any], RunErrorEvent | None]:
    """Coerce resume responses or return RUN_ERROR for invalid pending response payloads."""
    if not responses or not pending_events:
        return responses, None

    normalized: dict[str, Any] = {}
    pending_by_id: dict[str, Any] = {}
    for request_id, event in pending_events.items():
        pending_by_id[str(request_id)] = event
        event_request_id = getattr(event, "request_id", None)
        if event_request_id:
            pending_by_id[str(event_request_id)] = event

    for request_id, value in responses.items():
        request_key = str(request_id)
        request_event = pending_by_id.get(request_key)
        if request_event is None:
            normalized[request_key] = value
            continue

        coerced_value = _coerce_response_for_request(request_event, value)
        if coerced_value is None:
            return (
                {},
                RunErrorEvent(
                    message=(
                        f"Workflow resume for interruptId '{request_key}' does not match expected "
                        f"response type {_response_type_name(request_event)}."
                    ),
                    code="WORKFLOW_RESUME_INVALID_RESPONSE",
                ),
            )
        if not _approval_response_matches_request(
            request_key,
            request_event,
            coerced_value,
            allow_edited_arguments=_is_compact_approval_response_payload(value),
        ):
            return (
                {},
                RunErrorEvent(
                    message=f"Workflow resume for interruptId '{request_key}' does not match pending approval request.",
                    code="WORKFLOW_RESUME_INVALID_RESPONSE",
                ),
            )
        normalized[request_key] = coerced_value
    return normalized, None


def _latest_user_text(messages: list[Message]) -> str | None:
    """Get the most recent user text message, if present."""
    for message in reversed(messages):
        role_field = message.role
        if isinstance(role_field, str):
            role = role_field
        else:
            role = str(getattr(role_field, "value", role_field))
        if role != "user":
            continue
        for content in reversed(message.contents):
            if content.type != "text":
                continue
            text_value = getattr(content, "text", None)
            if isinstance(text_value, str) and text_value.strip():
                return text_value
    return None


def _workflow_interrupt_event_value(request_payload: dict[str, Any]) -> str | None:
    """Build a string payload for interrupt-card custom events."""
    request_data = request_payload.get("data")
    if request_data is None:
        return None
    if isinstance(request_data, str):
        return request_data
    return json.dumps(make_json_safe(request_data))


def _message_role_value(message: Message) -> str:
    """Normalize Message.role to its string value."""
    role = message.role
    if isinstance(role, str):
        return role
    return str(getattr(role, "value", role))


def _latest_assistant_contents(messages: list[Message]) -> list[Content] | None:
    """Return contents from the most recent assistant message."""
    for message in reversed(messages):
        if _message_role_value(message) != "assistant":
            continue
        contents = list(message.contents or [])
        if contents:
            return contents
    return None


def _unemitted_exposed_function_results(response: AgentResponse, flow: FlowState) -> list[Content]:
    """Return finalized function results that complete calls exposed during this run."""
    exposed_call_ids = set(flow.tool_calls_by_id)
    emitted_call_ids = {
        str(result["toolCallId"]) for result in flow.tool_results if isinstance(result.get("toolCallId"), str)
    }
    latest_assistant_result_ids = {
        str(content.call_id)
        for content in _latest_assistant_contents(list(response.messages or [])) or []
        if content.type == "function_result" and content.call_id
    }
    results: list[Content] = []
    for message in response.messages or []:
        for content in message.contents or []:
            call_id = content.call_id
            if (
                content.type != "function_result"
                or not call_id
                or call_id not in exposed_call_ids
                or call_id in emitted_call_ids
                or call_id in latest_assistant_result_ids
            ):
                continue
            results.append(content)
            emitted_call_ids.add(call_id)
    return results


def _text_from_contents(contents: list[Content]) -> str | None:
    """Return normalized assistant text from a content list when present."""
    text_parts: list[str] = []
    for content in contents:
        if content.type != "text":
            continue
        text_value = getattr(content, "text", None)
        if not isinstance(text_value, str):
            continue
        if not text_value:
            continue
        text_parts.append(text_value)
    if not text_parts:
        return None
    return "".join(text_parts).strip() or None


def _workflow_payload_to_contents(payload: Any) -> list[Content] | None:
    """Best-effort conversion from workflow payloads to chat content fragments."""
    if payload is None:
        return None
    if isinstance(payload, Content):
        return [payload]
    if isinstance(payload, str):
        return [Content.from_text(text=payload)]
    if isinstance(payload, Message):
        if _message_role_value(payload) != "assistant":
            return None
        return list(payload.contents or [])
    if isinstance(payload, AgentResponseUpdate):
        contents = list(payload.contents or [])
        role_field = payload.role
        if role_field is None:
            # ``role`` is optional and streamed continuation chunks routinely omit it.
            # Keep their text -- previously dropped, so role-less text surfaced as a
            # CUSTOM workflow_output instead of reasoning/assistant text -- alongside tool
            # content. Approval requests stay excluded (see _TOOL_CONTENT_TYPES): a
            # role-less approval interrupt from streamed content has no pending request to
            # resume against.
            role_less_contents = [
                content for content in contents if content.type == "text" or content.type in _TOOL_CONTENT_TYPES
            ]
            return role_less_contents or None
        if isinstance(role_field, str):
            role = role_field
        else:
            role = str(getattr(role_field, "value", role_field))
        if role == "assistant":
            return contents
        tool_contents = [content for content in contents if content.type in _TOOL_CONTENT_TYPES]
        return tool_contents or None
    if isinstance(payload, AgentResponse):
        return _latest_assistant_contents(list(payload.messages or []))
    if isinstance(payload, list):
        if payload and all(isinstance(item, Message) for item in payload):
            return _latest_assistant_contents(cast(list[Message], payload))
        contents: list[Content] = []
        for item in payload:
            item_contents = _workflow_payload_to_contents(item)
            if item_contents is None:
                return None
            contents.extend(item_contents)
        return contents if contents else None
    return None


def _as_reasoning_content(content: Content) -> Content:
    """Re-tag plain text content as ``text_reasoning``.

    Intermediate workflow output should surface as AG-UI reasoning (a collapsible
    "thinking" block) rather than a final assistant message. Only ``text`` content
    is converted; tool calls, results, and other content types pass through
    unchanged so they still emit as their native AG-UI events.
    """
    if content.type != "text":
        return content
    return Content.from_text_reasoning(
        id=content.id,
        text=content.text,
        # Carry encrypted reasoning metadata through unchanged: _emit_text_reasoning
        # turns protected_data into a ReasoningEncryptedValueEvent and an
        # ``encryptedValue`` on the snapshot entry, so dropping it here would break
        # reasoning state continuity for intermediate content that carries it.
        protected_data=content.protected_data,
        annotations=content.annotations,
        additional_properties=content.additional_properties or None,
        raw_representation=content.raw_representation,
    )


def _event_name(event: Any) -> str:
    event_type = getattr(event, "type", None)
    if isinstance(event_type, str) and event_type:
        return event_type
    return type(event).__name__


def _custom_event_value(event: Any) -> Any:
    if getattr(event, "data", None) is not None:
        return make_json_safe(getattr(event, "data"))

    event_dict = cast(dict[str, Any], getattr(event, "__dict__", {}) or {})
    custom_fields = {
        key: make_json_safe(value)
        for key, value in event_dict.items()
        if key not in _WORKFLOW_EVENT_BASE_FIELDS and not key.startswith("_")
    }
    return custom_fields if custom_fields else None


def _details_message(details: Any) -> str:
    if details is None:
        return "Workflow execution failed."
    if hasattr(details, "message"):
        message = getattr(details, "message")
        if isinstance(message, str) and message:
            return message
    return str(details)


def _details_code(details: Any) -> str | None:
    if details is None:
        return None
    if hasattr(details, "error_type"):
        error_type = getattr(details, "error_type")
        if isinstance(error_type, str) and error_type:
            return error_type
    return None


async def run_workflow_stream(
    input_data: dict[str, Any],
    workflow: Workflow,
    *,
    checkpoint_storage: CheckpointStorage | None = None,
    checkpoint_id: str | None = None,
) -> AsyncGenerator[BaseEvent]:
    """Run a Workflow and emit AG-UI protocol events.

    Args:
        input_data: Normalized AG-UI request payload (a ``RunAgentInput`` dump).
        workflow: The core ``Workflow`` instance to execute.
        checkpoint_storage: Optional checkpoint storage forwarded to the core
            workflow. When provided, the workflow creates a checkpoint at the end
            of each superstep, mirroring ``Workflow.run(checkpoint_storage=...)``.
        checkpoint_id: Optional checkpoint id to resume from. When provided the run
            restores the persisted workflow state instead of starting a fresh turn,
            mirroring ``Workflow.run(checkpoint_id=...)``. Any incoming messages are
            treated as request-info responses (or ignored) rather than a new
            start-executor message, so resume stays consistent with the core API.
    """
    supplied_thread_id = input_data.get("thread_id") or input_data.get("threadId")
    thread_id = supplied_thread_id or str(uuid.uuid4())
    run_id = input_data.get("run_id") or input_data.get("runId") or str(uuid.uuid4())
    available_interrupts = input_data.get("available_interrupts") or input_data.get("availableInterrupts")
    if available_interrupts:
        logger.debug("Received available interrupts metadata: %s", available_interrupts)

    raw_messages = list(cast(list[dict[str, Any]], input_data.get("messages", []) or []))
    messages, _ = normalize_agui_input_messages(raw_messages, sanitize_tool_history=False)

    flow = FlowState()
    interrupts: list[dict[str, Any]] = []
    run_started_emitted = False
    terminal_emitted = False
    run_error_emitted = False
    last_assistant_text: str | None = None

    resume_payload = _extract_resume_payload(input_data)

    # A checkpoint resume that carries an explicit resume payload targets the requests
    # that were pending when the checkpoint was written; those only reappear on the live
    # instance once the checkpoint is restored, so coerce against the checkpoint's
    # persisted pending set instead. Only do so when a resume payload is present, so a
    # pure checkpoint restore still surfaces its pending interrupts instead of tripping
    # the "resume required" contract.
    if checkpoint_id is not None and resume_payload is not None:
        if checkpoint_storage is None:
            raise ValueError("Resuming a checkpoint with an AG-UI resume payload requires checkpoint_storage.")
        pending_before_run = await _pending_request_events_from_checkpoint(checkpoint_id, checkpoint_storage)
    else:
        pending_before_run = await _pending_request_events(workflow)
    pending_interrupt_ids = _pending_workflow_interrupt_ids(pending_before_run)
    resume_entries: list[dict[str, Any]] = []
    cancelled_request_ids: set[str] = set()
    if pending_interrupt_ids:
        resume_entries, contract_error, contract_code = _resume_contract_error(
            resume_payload,
            pending_interrupt_ids,
            required_code="WORKFLOW_RESUME_REQUIRED",
            invalid_code="WORKFLOW_RESUME_INVALID",
            unknown_code="WORKFLOW_RESUME_NOT_FOUND",
            missing_code="WORKFLOW_RESUME_MISSING_INTERRUPT",
        )
        if contract_error is not None and contract_code is not None:
            yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
            yield RunErrorEvent(message=contract_error, code=contract_code)
            return
        resume_error = _resume_error_for_pending_workflow_requests(resume_entries)
        if resume_error is not None:
            yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
            yield resume_error
            return
        cancelled_request_ids = {
            str(entry["interrupt_id"]) for entry in resume_entries if entry.get("status") == "cancelled"
        }

    resume_responses = (
        _resume_entries_to_workflow_responses(resume_entries)
        if pending_interrupt_ids
        else _resume_to_workflow_responses(resume_payload)
    )
    message_responses = {
        request_id: value
        for request_id, value in _extract_responses_from_messages(messages).items()
        if request_id in pending_interrupt_ids
    }
    responses = _merge_workflow_response_sources(resume_responses, message_responses)
    responses, response_error = _coerce_responses_for_pending_requests_strict(responses, pending_before_run)
    if response_error is not None:
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        yield response_error
        return
    if cancelled_request_ids:
        await workflow.cancel_pending_requests(
            cancelled_request_ids,
            checkpoint_id=checkpoint_id,
            checkpoint_storage=checkpoint_storage,
        )
        checkpoint_id = None
        pending_before_run = {
            request_id: request_event
            for request_id, request_event in pending_before_run.items()
            if str(getattr(request_event, "request_id", None) or request_id) not in cancelled_request_ids
        }
    pending_interrupts = _interrupts_from_pending_requests(pending_before_run)

    # A checkpoint resume must always reach ``workflow.run(checkpoint_id=...)`` so the
    # core restores persisted state and re-emits any pending requests from the
    # checkpoint. ``pending_before_run`` reflects the live (pre-restore) instance, so
    # short-circuiting on it here would skip the restore entirely.
    if checkpoint_id is None and not responses and pending_before_run:
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        for request_event in pending_before_run.values():
            request_payload = _request_payload_from_request_event(request_event)
            if request_payload is None:
                continue
            request_id = str(request_payload["request_id"])
            yield ToolCallStartEvent(tool_call_id=request_id, tool_call_name="request_info")
            yield ToolCallArgsEvent(tool_call_id=request_id, delta=json.dumps(request_payload))
            yield ToolCallEndEvent(tool_call_id=request_id)
            yield CustomEvent(name="request_info", value=request_payload)
            interrupt_event_value = _workflow_interrupt_event_value(request_payload)
            if interrupt_event_value is not None:
                yield CustomEvent(name=_INTERRUPT_CARD_EVENT_NAME, value=interrupt_event_value)
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id, interrupts=pending_interrupts)
        return

    if checkpoint_id is None and not responses and not messages:
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id, interrupts=pending_interrupts)
        return

    def _drain_open_message() -> list[TextMessageEndEvent]:
        """Close any open assistant text message and clear flow state."""
        if not flow.message_id:
            return []
        current_message_id = flow.message_id
        flow.message_id = None
        flow.accumulated_text = ""
        return [TextMessageEndEvent(message_id=current_message_id)]

    def _drain_open_blocks() -> list[BaseEvent]:
        """Close any open reasoning block and assistant text message.

        Emitted before content that must not sit inside an open block: a terminal event
        (RUN_FINISHED / RUN_ERROR, which must be the final events in the stream) or a
        request_info tool call (non-reasoning message content). Otherwise the block's
        REASONING_* / TEXT_MESSAGE_* end events would be flushed only by the post-loop
        cleanup -- after the terminal event, or after the tool call. Both inner helpers
        are no-ops when their block is not open, so this is always safe to call (a later
        cleanup pass then simply does nothing).
        """
        events: list[BaseEvent] = []
        events.extend(_close_reasoning_block(flow))
        events.extend(_drain_open_message())
        return events

    fwd_kwargs: dict[str, Any] = {}
    if "forwarded_props" in input_data:
        forwarded_props = input_data["forwarded_props"]
        fwd_kwargs["function_invocation_kwargs"] = {"forwarded_props": forwarded_props}
    elif "forwardedProps" in input_data:
        forwarded_props = input_data["forwardedProps"]
        fwd_kwargs["function_invocation_kwargs"] = {"forwarded_props": forwarded_props}

    # Only pass function_invocation_kwargs if the workflow.run signature accepts it
    if fwd_kwargs:
        try:
            sig = inspect.signature(workflow.run)
            params = sig.parameters
            accepts_fwd = "function_invocation_kwargs" in params or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
        except (ValueError, TypeError):
            accepts_fwd = False
        if not accepts_fwd:
            logger.debug("workflow.run() does not accept function_invocation_kwargs; dropping forwarded_props")
            fwd_kwargs = {}

    # When checkpointing is not in play, keep the exact legacy call shape so duck-typed
    # workflows with narrower ``run`` signatures keep working. Otherwise forward the
    # checkpoint arguments as-is (``None`` included) and let core validate conflicts.
    checkpoint_kwargs: dict[str, Any] = {}
    if checkpoint_storage is not None or checkpoint_id is not None:
        checkpoint_kwargs = {"checkpoint_storage": checkpoint_storage, "checkpoint_id": checkpoint_id}

    try:
        telemetry_conversation_id = str(supplied_thread_id) if supplied_thread_id is not None else None
        telemetry_context = partial(_use_telemetry_conversation_id, telemetry_conversation_id)
        with telemetry_context():
            if responses or checkpoint_id is not None:
                # ``message`` is mutually exclusive with both ``responses`` and
                # ``checkpoint_id`` in the core API; ``responses`` + ``checkpoint_id``
                # restores the checkpoint and delivers the responses in a single call.
                event_stream = workflow.run(stream=True, responses=responses or None, **checkpoint_kwargs, **fwd_kwargs)
            else:
                event_stream = workflow.run(message=messages, stream=True, **checkpoint_kwargs, **fwd_kwargs)

        async for event in _iterate_with_context(event_stream, telemetry_context):
            event_type = getattr(event, "type", None)

            if event_type == "started":
                if not run_started_emitted:
                    yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
                    run_started_emitted = True
                continue

            if not run_started_emitted:
                yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
                run_started_emitted = True

            if event_type == "failed":
                # Close any open reasoning block / text message so RUN_ERROR stays the
                # last event a client receives for this run.
                for end_event in _drain_open_blocks():
                    yield end_event
                details = getattr(event, "details", None)
                yield RunErrorEvent(message=_details_message(details), code=_details_code(details))
                run_error_emitted = True
                terminal_emitted = True
                continue

            if event_type == "status":
                state = getattr(event, "state", None)
                if isinstance(state, str):
                    state_value = state
                else:
                    state_value = str(getattr(state, "value", state))
                if state_value in _TERMINAL_STATES and not terminal_emitted:
                    # Close any open reasoning block and assistant text message before the
                    # terminal event so RUN_FINISHED is always the last emitted event.
                    for end_event in _drain_open_blocks():
                        yield end_event
                    if not interrupts:
                        interrupts.extend(_interrupts_from_pending_requests(await _pending_request_events(workflow)))
                    yield _build_run_finished_event(run_id=run_id, thread_id=thread_id, interrupts=interrupts)
                    terminal_emitted = True
                elif state_value not in _TERMINAL_STATES:
                    yield CustomEvent(name="status", value={"state": state_value})
                continue

            if event_type == "superstep_started":
                for end_event in _drain_open_message():
                    yield end_event
                iteration = getattr(event, "iteration", None)
                yield StepStartedEvent(step_name=f"superstep:{iteration}")
                continue

            if event_type == "superstep_completed":
                iteration = getattr(event, "iteration", None)
                yield StepFinishedEvent(step_name=f"superstep:{iteration}")
                continue

            if event_type in {"executor_invoked", "executor_completed", "executor_failed"}:
                executor_id = getattr(event, "executor_id", None)
                status = {
                    "executor_invoked": "in_progress",
                    "executor_completed": "completed",
                    "executor_failed": "failed",
                }[event_type]
                if isinstance(executor_id, str) and executor_id:
                    if event_type == "executor_invoked":
                        for end_event in _drain_open_message():
                            yield end_event
                        yield StepStartedEvent(step_name=executor_id)
                    else:
                        yield StepFinishedEvent(step_name=executor_id)
                executor_payload: dict[str, Any] = {
                    "executor_id": executor_id,
                    "status": status,
                }
                if event_type == "executor_failed":
                    executor_payload["details"] = make_json_safe(getattr(event, "details", None))
                else:
                    executor_payload["data"] = make_json_safe(getattr(event, "data", None))

                yield ActivitySnapshotEvent(
                    message_id=f"executor:{executor_id}" if executor_id else generate_event_id(),
                    activity_type="executor",
                    content=executor_payload,
                )
                continue

            if event_type == "request_info":
                # A request_info emits a tool call (non-reasoning message content), so any
                # open reasoning block / text message must be closed first -- otherwise the
                # tool call would sit inside an unclosed reasoning block.
                for end_event in _drain_open_blocks():
                    yield end_event
                request_payload = _request_payload_from_request_event(event)
                if request_payload is None:
                    continue
                request_id = request_payload["request_id"]
                interrupt_entry = _interrupt_entry_for_request_event(event)
                if interrupt_entry is not None:
                    interrupts.append(interrupt_entry)
                args_delta = json.dumps(request_payload)

                yield ToolCallStartEvent(tool_call_id=str(request_id), tool_call_name="request_info")
                yield ToolCallArgsEvent(tool_call_id=str(request_id), delta=args_delta)
                yield ToolCallEndEvent(tool_call_id=str(request_id))
                yield CustomEvent(name="request_info", value=request_payload)
                interrupt_event_value = _workflow_interrupt_event_value(request_payload)
                if interrupt_event_value is not None:
                    yield CustomEvent(name=_INTERRUPT_CARD_EVENT_NAME, value=interrupt_event_value)
                continue

            if event_type in {"output", "intermediate", "data"}:
                # "intermediate" (and its deprecated alias "data") carry non-terminal
                # output. Their text is surfaced as AG-UI reasoning so consumers render
                # it as a collapsible "thinking" block instead of a final assistant
                # message. "output" keeps the terminal-message behavior.
                is_intermediate = event_type in {"intermediate", "data"}
                output_payload = getattr(event, "data", None)
                if isinstance(output_payload, BaseEvent):
                    yield output_payload
                    continue
                if (
                    isinstance(output_payload, list)
                    and output_payload
                    and all(isinstance(item, BaseEvent) for item in output_payload)
                ):
                    for item in output_payload:
                        yield item
                    continue
                if isinstance(output_payload, AgentResponse):
                    for result in _unemitted_exposed_function_results(output_payload, flow):
                        for out_event in _emit_content(result, flow, predictive_handler=None, skip_text=False):
                            yield out_event
                contents = _workflow_payload_to_contents(output_payload)
                if contents:
                    if is_intermediate:
                        # Reasoning is a separate channel from the final assistant
                        # message, so the last_assistant_text dedup does not apply.
                        for content in contents:
                            reasoning_content = _as_reasoning_content(content)
                            for out_event in _emit_content(
                                reasoning_content, flow, predictive_handler=None, skip_text=False
                            ):
                                yield out_event
                    else:
                        output_text = _text_from_contents(contents)
                        skip_text = bool(output_text and output_text == last_assistant_text)
                        for content in contents:
                            for out_event in _emit_content(content, flow, predictive_handler=None, skip_text=skip_text):
                                yield out_event
                        if flow.message_id and flow.accumulated_text:
                            last_assistant_text = flow.accumulated_text.strip() or last_assistant_text
                        elif output_text:
                            last_assistant_text = output_text
                else:
                    yield CustomEvent(name="workflow_output", value=make_json_safe(output_payload))
                continue

            # Fall back to custom events for diagnostics, orchestration events, and custom workflow events.
            yield CustomEvent(name=_event_name(event), value=_custom_event_value(event))

    except Exception as exc:
        logger.exception("Workflow AG-UI stream failed: %s", exc)
        if not run_started_emitted:
            yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
            run_started_emitted = True
        # Close any open reasoning block / text message so RUN_ERROR stays the final event.
        for end_event in _drain_open_blocks():
            yield end_event
        if not run_error_emitted:
            yield RunErrorEvent(message=str(exc), code=type(exc).__name__)
            run_error_emitted = True
        terminal_emitted = True

    for reasoning_evt in _close_reasoning_block(flow):
        yield reasoning_evt

    for end_event in _drain_open_message():
        yield end_event

    if not run_started_emitted:
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)

    if not terminal_emitted and not run_error_emitted:
        if not interrupts:
            interrupts.extend(_interrupts_from_pending_requests(await _pending_request_events(workflow)))
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id, interrupts=interrupts)
