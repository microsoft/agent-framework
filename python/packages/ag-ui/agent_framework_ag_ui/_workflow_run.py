# Copyright (c) Microsoft. All rights reserved.

"""Native AG-UI orchestration for MAF Workflow streams."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast, get_args, get_origin

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
from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message, Workflow, WorkflowRunState

from ._message_adapters import normalize_agui_input_messages
from ._run_common import (
    FlowState,
    _build_run_finished_event,
    _emit_content,
    _extract_resume_payload,
    _normalize_resume_interrupts,
)
from ._utils import generate_event_id, make_json_safe

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


def _interrupt_entry_for_request_event(request_event: Any) -> dict[str, Any] | None:
    """Build AG-UI interrupt payload from a workflow request_info event."""
    request_id = getattr(request_event, "request_id", None)
    if request_id is None:
        return None
    request_data = make_json_safe(getattr(request_event, "data", None))
    if isinstance(request_data, dict):
        value: Any = request_data
    else:
        value = {"data": request_data}
    return {"id": str(request_id), "value": value}


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
    """Extract request-info responses from incoming tool/function-result messages."""
    responses: dict[str, Any] = {}
    for message in messages:
        for content in message.contents:
            if content.type != "function_result" or not content.call_id:
                continue
            value = _coerce_json_value(content.result)
            responses[str(content.call_id)] = value
    return responses


def _resume_to_workflow_responses(resume_payload: Any) -> dict[str, Any]:
    """Convert AG-UI resume payloads into workflow responses."""
    responses: dict[str, Any] = {}
    for interrupt in _normalize_resume_interrupts(resume_payload):
        value = _coerce_json_value(interrupt.get("value"))
        responses[str(interrupt["id"])] = value
    return responses


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
        return _coerce_content(candidate)
    if target_type is bool:
        return candidate if isinstance(candidate, bool) else None
    if target_type is int:
        return candidate if isinstance(candidate, int) and not isinstance(candidate, bool) else None
    if target_type is float:
        return candidate if isinstance(candidate, (int, float)) and not isinstance(candidate, bool) else None
    if isinstance(target_type, type):
        return candidate if isinstance(candidate, target_type) else None

    # Unknown typing metadata: preserve value as-is.
    return candidate


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

    return {str(request_id): coerced_value}


def _coerce_responses_for_pending_requests(
    responses: dict[str, Any],
    pending_events: dict[str, Any],
) -> dict[str, Any]:
    """Coerce resume responses to the expected types for known pending requests."""
    if not responses or not pending_events:
        return responses

    normalized: dict[str, Any] = {}
    pending_by_id = {str(request_id): event for request_id, event in pending_events.items()}

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
        normalized[request_key] = coerced_value
    return normalized


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
        role_field = payload.role
        if role_field is None:
            return None
        if isinstance(role_field, str):
            role = role_field
        else:
            role = str(getattr(role_field, "value", role_field))
        if role != "assistant":
            return None
        return list(payload.contents or [])
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
) -> AsyncGenerator[BaseEvent]:
    """Run a Workflow and emit AG-UI protocol events."""
    thread_id = input_data.get("thread_id") or input_data.get("threadId") or str(uuid.uuid4())
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
    responses = _resume_to_workflow_responses(resume_payload)
    responses.update(_extract_responses_from_messages(messages))
    pending_before_run = await _pending_request_events(workflow)
    responses = _coerce_responses_for_pending_requests(responses, pending_before_run)
    pending_interrupts = _interrupts_from_pending_requests(pending_before_run)
    if not responses and pending_before_run:
        responses.update(_single_pending_response_from_value(pending_before_run, resume_payload))
    if not responses and pending_before_run:
        responses.update(_single_pending_response_from_value(pending_before_run, _latest_user_text(messages)))

    if not responses and pending_before_run:
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

    if not responses and not messages:
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

    try:
        if responses:
            event_stream = workflow.run(responses=responses, stream=True)
        else:
            event_stream = workflow.run(message=messages, stream=True)

        async for event in event_stream:
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
                for end_event in _drain_open_message():
                    yield end_event
                request_payload = _request_payload_from_request_event(event)
                if request_payload is None:
                    continue
                request_id = request_payload["request_id"]
                request_data = request_payload.get("data")
                if isinstance(request_data, dict):
                    interrupt_value: Any = request_data
                else:
                    interrupt_value = {"data": request_data}
                interrupts.append({"id": str(request_id), "value": interrupt_value})
                args_delta = json.dumps(request_payload)

                yield ToolCallStartEvent(tool_call_id=str(request_id), tool_call_name="request_info")
                yield ToolCallArgsEvent(tool_call_id=str(request_id), delta=args_delta)
                yield ToolCallEndEvent(tool_call_id=str(request_id))
                yield CustomEvent(name="request_info", value=request_payload)
                interrupt_event_value = _workflow_interrupt_event_value(request_payload)
                if interrupt_event_value is not None:
                    yield CustomEvent(name=_INTERRUPT_CARD_EVENT_NAME, value=interrupt_event_value)
                continue

            if event_type in {"output", "data"}:
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
                contents = _workflow_payload_to_contents(output_payload)
                if contents:
                    output_text = _text_from_contents(contents)
                    if output_text and output_text == last_assistant_text:
                        continue
                    for content in contents:
                        for out_event in _emit_content(content, flow, predictive_handler=None, skip_text=False):
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
        if not run_error_emitted:
            yield RunErrorEvent(message=str(exc), code=type(exc).__name__)
            run_error_emitted = True
        terminal_emitted = True

    for end_event in _drain_open_message():
        yield end_event

    if not run_started_emitted:
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)

    if not terminal_emitted and not run_error_emitted:
        if not interrupts:
            interrupts.extend(_interrupts_from_pending_requests(await _pending_request_events(workflow)))
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id, interrupts=interrupts)
