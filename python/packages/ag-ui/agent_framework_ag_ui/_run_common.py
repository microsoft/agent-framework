# Copyright (c) Microsoft. All rights reserved.

"""Shared AG-UI run helpers used by agent and workflow runners."""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from ag_ui.core import (
    BaseEvent,
    CustomEvent,
    Interrupt,
    ReasoningEncryptedValueEvent,
    ReasoningEndEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    ReasoningStartEvent,
    RunFinishedEvent,
    RunFinishedInterruptOutcome,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from agent_framework import Content

from ._orchestration._predictive_state import PredictiveStateHandler
from ._state import TOOL_RESULT_DISPLAY_KEY, TOOL_RESULT_STATE_KEY
from ._utils import generate_event_id, make_json_safe, normalize_agui_role

logger = logging.getLogger(__name__)

# Sentinel for an unset display_result; distinguishes "caller didn't pass" from None/{}/"".
_UNSET = object()


def _has_only_tool_calls(contents: list[Any]) -> bool:
    """Check if contents have only tool calls (no text)."""
    has_tool_call = any(getattr(c, "type", None) == "function_call" for c in contents)
    has_text = any(getattr(c, "type", None) == "text" and getattr(c, "text", None) for c in contents)
    return has_tool_call and not has_text


def _normalize_resume_interrupts(resume_payload: Any) -> list[dict[str, Any]]:
    """Normalize resume payload to a list of interrupt responses."""
    if resume_payload is None:
        return []

    if isinstance(resume_payload, list):
        candidates = resume_payload
    elif isinstance(resume_payload, dict):
        resume_dict = cast(dict[str, Any], resume_payload)
        if isinstance(resume_dict.get("interrupts"), list):
            candidates = cast(list[Any], resume_dict["interrupts"])
        elif isinstance(resume_dict.get("interrupt"), list):
            candidates = cast(list[Any], resume_dict["interrupt"])
        else:
            candidates = [resume_dict]
    else:
        return []

    normalized: list[dict[str, Any]] = []
    for item in candidates:
        model_dump = getattr(item, "model_dump", None)
        if callable(model_dump):
            item = model_dump(by_alias=True, exclude_none=True)
        if not isinstance(item, dict):
            continue
        item_dict = cast(dict[str, Any], item)
        interrupt_id = (
            item_dict.get("id")
            or item_dict.get("interruptId")
            or item_dict.get("interrupt_id")
            or item_dict.get("toolCallId")
        )
        if not interrupt_id:
            continue

        if "payload" in item_dict:
            value = item_dict.get("payload")
        elif "value" in item_dict:
            value = item_dict.get("value")
        elif "response" in item_dict:
            value = item_dict.get("response")
        else:
            value = {
                k: v
                for k, v in item_dict.items()
                if k not in {"id", "interruptId", "interrupt_id", "toolCallId", "type", "status"}
            }

        normalized_entry = {"id": str(interrupt_id), "value": value}
        status = item_dict.get("status")
        if isinstance(status, str) and status:
            normalized_entry["status"] = status
        normalized.append(normalized_entry)

    return normalized


def _extract_resume_payload(input_data: dict[str, Any]) -> Any:
    """Extract resume payload from standard and forwarded-props request locations."""
    resume_payload = input_data.get("resume")
    if resume_payload is not None:
        return resume_payload

    forwarded_props = input_data.get("forwarded_props") or input_data.get("forwardedProps")
    if not isinstance(forwarded_props, dict):
        return None

    forwarded_props_dict = cast(dict[str, Any], forwarded_props)
    command = forwarded_props_dict.get("command")
    if isinstance(command, dict):
        command_dict = cast(dict[str, Any], command)
        if command_dict.get("resume") is not None:
            return command_dict.get("resume")

    return forwarded_props_dict.get("resume")


def _strict_resume_entries(resume_payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Parse resume entries for pending interrupt contract validation."""
    if isinstance(resume_payload, list):
        candidates = resume_payload
    elif isinstance(resume_payload, dict):
        resume_dict = cast(dict[str, Any], resume_payload)
        if isinstance(resume_dict.get("interrupts"), list):
            candidates = cast(list[Any], resume_dict["interrupts"])
        elif isinstance(resume_dict.get("interrupt"), list):
            candidates = cast(list[Any], resume_dict["interrupt"])
        else:
            candidates = [resume_dict]
    else:
        return [], "Resume payload must be a list of entries or an object containing interrupt entries."

    if not candidates:
        return [], "Resume payload must include at least one interrupt entry."

    entries: list[dict[str, Any]] = []
    for item in candidates:
        model_dump = getattr(item, "model_dump", None)
        if callable(model_dump):
            item = model_dump(by_alias=True, exclude_none=True)
        if not isinstance(item, dict):
            return [], "Each resume entry must be an object."

        item_dict = cast(dict[str, Any], item)
        interrupt_id = (
            item_dict.get("interruptId")
            or item_dict.get("interrupt_id")
            or item_dict.get("id")
            or item_dict.get("toolCallId")
        )
        if not interrupt_id:
            return [], "Each resume entry must include interruptId."

        status = item_dict.get("status") or "resolved"
        if status not in {"resolved", "cancelled"}:
            return [], f"Unsupported resume status '{status}'."

        if "payload" in item_dict:
            payload = item_dict.get("payload")
        elif "value" in item_dict:
            payload = item_dict.get("value")
        elif "response" in item_dict:
            payload = item_dict.get("response")
        else:
            payload = {
                key: value
                for key, value in item_dict.items()
                if key not in {"id", "interruptId", "interrupt_id", "toolCallId", "type", "status"}
            }

        entries.append({"interrupt_id": str(interrupt_id), "status": str(status), "payload": payload})

    return entries, None


def _resume_contract_error(
    resume_payload: Any,
    pending_interrupt_ids: set[str],
    *,
    required_code: str,
    invalid_code: str,
    unknown_code: str,
    missing_code: str,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Validate that resume entries address every pending interrupt exactly once."""
    if not pending_interrupt_ids:
        entries, error = _strict_resume_entries(resume_payload)
        return entries, error, invalid_code if error else None

    if resume_payload is None:
        return [], "Pending interrupts require a resume entry for every interruptId.", required_code

    entries, error = _strict_resume_entries(resume_payload)
    if error is not None:
        return [], error, invalid_code

    seen: set[str] = set()
    for entry in entries:
        interrupt_id = str(entry["interrupt_id"])
        if interrupt_id in seen:
            return [], f"Resume includes duplicate interruptId '{interrupt_id}'.", invalid_code
        seen.add(interrupt_id)

    unknown = seen - pending_interrupt_ids
    if unknown:
        interrupt_id = sorted(unknown)[0]
        return [], f"No pending interrupt found for resume interruptId '{interrupt_id}'.", unknown_code

    missing = pending_interrupt_ids - seen
    if missing:
        interrupt_id = sorted(missing)[0]
        return [], f"Resume omitted pending interruptId '{interrupt_id}'.", missing_code

    return entries, None, None


def _canonical_interrupt_message(value: Any) -> str | None:
    """Extract a human-readable message from legacy interruption metadata."""
    if isinstance(value, str):
        return value
    if not isinstance(value, Mapping):
        return None
    value_mapping = cast(Mapping[str, Any], value)
    for key in ("message", "prompt", "question", "data"):
        message = value_mapping.get(key)
        if isinstance(message, str) and message:
            return message
    return None


def _canonical_interrupt_tool_call_id(interrupt: Mapping[str, Any], value: Any) -> str | None:
    """Extract a tool call id from canonical fields or legacy interruption metadata."""
    direct_tool_call_id = interrupt.get("toolCallId") or interrupt.get("tool_call_id")
    if direct_tool_call_id:
        return str(direct_tool_call_id)

    if not isinstance(value, Mapping):
        return None
    value_mapping = cast(Mapping[str, Any], value)
    function_call = value_mapping.get("function_call") or value_mapping.get("functionCall")
    if not isinstance(function_call, Mapping):
        return None
    function_call_mapping = cast(Mapping[str, Any], function_call)
    tool_call_id = function_call_mapping.get("call_id") or function_call_mapping.get("callId")
    return str(tool_call_id) if tool_call_id else None


def _canonical_interrupt_reason(interrupt: Mapping[str, Any], value: Any) -> str:
    """Infer the canonical AG-UI interrupt reason from existing interruption metadata."""
    reason = interrupt.get("reason")
    if isinstance(reason, str) and reason:
        return reason
    if isinstance(value, Mapping):
        value_mapping = cast(Mapping[str, Any], value)
        if value_mapping.get("type") == "function_approval_request" or value_mapping.get("function_call"):
            return "tool_call"
    return "input_required"


def _canonical_interrupt_metadata(interrupt: Mapping[str, Any], value: Any) -> dict[str, Any] | None:
    """Move framework-specific legacy interruption details under metadata."""
    raw_metadata = interrupt.get("metadata")
    metadata = dict(cast(Mapping[str, Any], raw_metadata)) if isinstance(raw_metadata, Mapping) else {}
    if "value" in interrupt:
        raw_agent_framework = metadata.get("agent_framework")
        agent_framework = (
            dict(cast(Mapping[str, Any], raw_agent_framework)) if isinstance(raw_agent_framework, Mapping) else {}
        )
        agent_framework.setdefault("value", make_json_safe(value))
        metadata["agent_framework"] = agent_framework
    return metadata or None


def _canonical_interrupt(interrupt: Mapping[str, Any]) -> Interrupt | None:
    """Convert a legacy or protocol-compatible interrupt mapping into an AG-UI Interrupt."""
    interrupt_id = interrupt.get("id") or interrupt.get("interruptId")
    if not interrupt_id:
        return None

    value = interrupt.get("value")
    interrupt_data: dict[str, Any] = {
        "id": str(interrupt_id),
        "reason": _canonical_interrupt_reason(interrupt, value),
    }

    message = interrupt.get("message") or _canonical_interrupt_message(value)
    if isinstance(message, str) and message:
        interrupt_data["message"] = message

    tool_call_id = _canonical_interrupt_tool_call_id(interrupt, value)
    if tool_call_id:
        interrupt_data["toolCallId"] = tool_call_id

    response_schema = interrupt.get("responseSchema") or interrupt.get("response_schema")
    if isinstance(response_schema, Mapping):
        interrupt_data["responseSchema"] = dict(cast(Mapping[str, Any], response_schema))

    expires_at = interrupt.get("expiresAt") or interrupt.get("expires_at")
    if isinstance(expires_at, str) and expires_at:
        interrupt_data["expiresAt"] = expires_at

    metadata = _canonical_interrupt_metadata(interrupt, value)
    if metadata is not None:
        interrupt_data["metadata"] = metadata

    return Interrupt.model_validate(interrupt_data)


def _json_schema_for_value(value: Any) -> dict[str, Any]:
    """Infer a lightweight JSON schema for an already-serialized value."""
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        return {"type": "array"}
    if isinstance(value, Mapping):
        return {"type": "object", "additionalProperties": True}
    return {}


def _approval_response_schema(arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the response schema generic AG-UI clients use to render approval input."""
    properties: dict[str, Any] = {
        "accepted": {
            "type": "boolean",
            "description": "Whether the requested tool call is approved.",
        }
    }
    if arguments:
        for name, value in arguments.items():
            argument_schema = _json_schema_for_value(value)
            argument_schema["description"] = f"Optional edited value for the '{name}' tool argument."
            properties[str(name)] = argument_schema

    return {
        "type": "object",
        "properties": properties,
        "required": ["accepted"],
        "additionalProperties": False,
    }


def _approval_steps_response_schema() -> dict[str, Any]:
    """Build the response schema for step-based confirmation prompts."""
    return {
        "type": "object",
        "properties": {
            "accepted": {
                "type": "boolean",
                "description": "Whether the proposed tool changes are approved.",
            },
            "steps": {
                "type": "array",
                "description": "The approved and rejected steps.",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "status": {"type": "string", "enum": ["enabled", "disabled"]},
                    },
                    "required": ["description", "status"],
                    "additionalProperties": True,
                },
            },
        },
        "required": ["accepted"],
        "additionalProperties": False,
    }


def _function_call_interrupt_metadata(function_call: Content) -> dict[str, Any]:
    """Build Agent Framework metadata for a tool-bound approval interrupt."""
    parsed_arguments = make_json_safe(function_call.parse_arguments())
    return {
        "type": "function_approval_request",
        "function_call": {
            "call_id": function_call.call_id,
            "name": function_call.name,
            "arguments": parsed_arguments,
        },
    }


def _approval_interrupt_for_function_call(
    *,
    interrupt_id: str,
    function_call: Content,
    message: str | None = None,
    response_schema: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    tool_call_id: str | None = None,
) -> dict[str, Any]:
    """Build a canonical AG-UI interrupt descriptor for a tool approval pause."""
    function_metadata = _function_call_interrupt_metadata(function_call)
    parsed_arguments = function_metadata["function_call"]["arguments"]
    argument_mapping = cast(Mapping[str, Any], parsed_arguments) if isinstance(parsed_arguments, Mapping) else {}
    interrupt_message = message or f"Approve running {function_call.name or 'this tool'}?"
    agent_framework_metadata = {**function_metadata, "value": function_metadata}
    if metadata:
        agent_framework_metadata.update(dict(metadata))
    return {
        "id": interrupt_id,
        "reason": "tool_call",
        "message": interrupt_message,
        "toolCallId": tool_call_id or function_call.call_id,
        "responseSchema": dict(response_schema or _approval_response_schema(argument_mapping)),
        "metadata": {"agent_framework": agent_framework_metadata},
    }


def _build_run_finished_event(
    run_id: str, thread_id: str, interrupts: list[dict[str, Any]] | None = None
) -> RunFinishedEvent:
    """Create a RUN_FINISHED event, optionally carrying interrupt metadata."""
    if interrupts:
        canonical_interrupts = [
            canonical for interrupt in interrupts if (canonical := _canonical_interrupt(interrupt)) is not None
        ]
        if canonical_interrupts:
            return RunFinishedEvent(
                run_id=run_id,
                thread_id=thread_id,
                outcome=RunFinishedInterruptOutcome(interrupts=canonical_interrupts),
            )
        logger.warning(
            "run %s: %d interrupt(s) present but none carried an id/interruptId; "
            "emitting RUN_FINISHED with no interrupt outcome",
            run_id,
            len(interrupts),
        )
    return RunFinishedEvent(run_id=run_id, thread_id=thread_id)


@dataclass
class FlowState:
    """Minimal explicit state for a single AG-UI run."""

    message_id: str | None = None
    tool_call_id: str | None = None
    tool_call_name: str | None = None
    waiting_for_approval: bool = False
    current_state: dict[str, Any] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
    accumulated_text: str = ""
    pending_tool_calls: list[dict[str, Any]] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    tool_calls_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
    tool_results: list[dict[str, Any]] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    tool_calls_ended: set[str] = field(default_factory=set)  # pyright: ignore[reportUnknownVariableType]
    interrupts: list[dict[str, Any]] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    reasoning_messages: list[dict[str, Any]] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    accumulated_reasoning: dict[str, str] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
    reasoning_message_id: str | None = None
    # Ordered text/tool_calls/reasoning segment boundaries in the order the
    # model emitted them, so MESSAGES_SNAPSHOT can preserve that order
    # (issue #7223) instead of the fixed tool-calls -> results -> text layout.
    snapshot_segments: list[dict[str, Any]] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]

    def get_tool_name(self, call_id: str | None) -> str | None:
        """Get tool name by call ID."""
        if not call_id or call_id not in self.tool_calls_by_id:
            return None
        name = self.tool_calls_by_id[call_id]["function"].get("name")
        return str(name) if name else None

    def get_pending_without_end(self) -> list[dict[str, Any]]:
        """Get tool calls that started but never received an end event (declaration-only)."""
        return [tc for tc in self.pending_tool_calls if tc.get("id") not in self.tool_calls_ended]


def _open_text_segment(flow: FlowState, message_id: str) -> dict[str, Any]:
    """Start a new snapshot text segment for a freshly opened text message."""
    segment = {"kind": "text", "id": message_id, "text": ""}
    flow.snapshot_segments.append(segment)
    return segment


def _text_segment_for(flow: FlowState, message_id: str) -> dict[str, Any] | None:
    """Find the text segment belonging to the given message id."""
    for segment in reversed(flow.snapshot_segments):
        if segment["kind"] == "text" and segment["id"] == message_id:
            return segment
    return None


def _track_tool_call_segment(flow: FlowState, tool_call_id: str) -> None:
    """Record a tool call in the current tool segment, opening one if needed."""
    if flow.snapshot_segments and flow.snapshot_segments[-1]["kind"] == "tool_calls":
        flow.snapshot_segments[-1]["call_ids"].append(tool_call_id)
    else:
        flow.snapshot_segments.append({"kind": "tool_calls", "call_ids": [tool_call_id]})


def _track_reasoning_segment(flow: FlowState, message_id: str) -> None:
    """Record where a reasoning block sits in the snapshot emission order."""
    for segment in flow.snapshot_segments:
        if segment["kind"] == "reasoning" and segment["id"] == message_id:
            return
    flow.snapshot_segments.append({"kind": "reasoning", "id": message_id})


def _emit_text(content: Content, flow: FlowState, skip_text: bool = False) -> list[BaseEvent]:
    """Emit TextMessage events for TextContent."""
    if not content.text:
        return []

    if skip_text or flow.waiting_for_approval:
        return []

    events: list[BaseEvent] = []
    if not flow.message_id:
        flow.message_id = generate_event_id()
        flow.accumulated_text = ""
        _open_text_segment(flow, flow.message_id)
        events.append(TextMessageStartEvent(message_id=flow.message_id, role="assistant"))
    elif flow.accumulated_text and content.text == flow.accumulated_text:
        # Guard against full-message replay chunks that can appear after streaming deltas.
        logger.debug("Skipping duplicate full-text delta for message_id=%s", flow.message_id)
        return []

    events.append(TextMessageContentEvent(message_id=flow.message_id, delta=content.text))
    flow.accumulated_text += content.text
    segment = _text_segment_for(flow, flow.message_id)
    if segment is not None:
        segment["text"] = flow.accumulated_text
    return events


def _emit_tool_call(
    content: Content,
    flow: FlowState,
    predictive_handler: PredictiveStateHandler | None = None,
) -> list[BaseEvent]:
    """Emit ToolCall events for FunctionCallContent."""
    events: list[BaseEvent] = []

    tool_call_id = content.call_id or flow.tool_call_id or generate_event_id()

    if content.name and tool_call_id != flow.tool_call_id:
        flow.tool_call_id = tool_call_id
        flow.tool_call_name = content.name
        if predictive_handler:
            predictive_handler.reset_streaming()

        events.append(
            ToolCallStartEvent(
                tool_call_id=tool_call_id,
                tool_call_name=content.name,
                parent_message_id=flow.message_id,
            )
        )

        tool_entry = {
            "id": tool_call_id,
            "type": "function",
            "function": {"name": content.name, "arguments": ""},
        }
        flow.pending_tool_calls.append(tool_entry)
        flow.tool_calls_by_id[tool_call_id] = tool_entry
        _track_tool_call_segment(flow, tool_call_id)

    elif tool_call_id:
        flow.tool_call_id = tool_call_id

    if content.arguments:
        delta = (
            content.arguments if isinstance(content.arguments, str) else json.dumps(make_json_safe(content.arguments))
        )

        if tool_call_id in flow.tool_calls_by_id:
            accumulated = flow.tool_calls_by_id[tool_call_id]["function"]["arguments"]
            # Guard against full-argument replay: if the accumulated arguments
            # already equal the incoming delta, this is a non-delta replay of
            # the complete arguments string (some providers send the full
            # arguments again after streaming deltas). Skip the event emission
            # and accumulation to prevent doubling in MESSAGES_SNAPSHOT.
            # This mirrors the early-return behaviour of _emit_text().
            # (Fixes #4194)
            if accumulated and delta == accumulated:
                logger.debug(
                    "Skipping duplicate full-arguments replay for tool_call_id=%s",
                    tool_call_id,
                )
                return events

        events.append(ToolCallArgsEvent(tool_call_id=tool_call_id, delta=delta))

        if tool_call_id in flow.tool_calls_by_id:
            flow.tool_calls_by_id[tool_call_id]["function"]["arguments"] += delta

        if predictive_handler and flow.tool_call_name:
            delta_events = predictive_handler.emit_streaming_deltas(flow.tool_call_name, delta)
            events.extend(delta_events)

    return events


def _extract_tool_result_marker_values(content: Content, key: str) -> list[Any]:
    """Extract marker values from outer and inner tool-result content."""
    values: list[Any] = []

    outer_ap = getattr(content, "additional_properties", None) or {}
    if key in outer_ap:
        values.append(outer_ap[key])

    for item in content.items or ():
        item_ap = getattr(item, "additional_properties", None) or {}
        if key in item_ap:
            values.append(item_ap[key])

    return values


def _extract_tool_result_state(content: Content) -> dict[str, Any] | None:
    """Extract a deterministic AG-UI state update from a tool-result ``Content``.

    Tools using :func:`agent_framework_ag_ui.state_update` carry the state
    payload in ``additional_properties[TOOL_RESULT_STATE_KEY]`` on the inner
    text item produced by ``parse_result``. We also check the outer
    function_result content's ``additional_properties`` for robustness.

    If multiple items carry state, they are merged in order so later items
    override earlier ones (plain ``dict.update`` semantics).

    Returns:
        The merged state dict to apply, or ``None`` if no state update is
        present.
    """
    merged: dict[str, Any] | None = None

    for item_state in _extract_tool_result_marker_values(content, TOOL_RESULT_STATE_KEY):
        if isinstance(item_state, dict):
            if merged is None:
                merged = dict(item_state)
            else:
                merged.update(item_state)

    return merged


def _extract_tool_result_display(content: Content) -> Any:  # noqa: ANN401
    """Extract a UI-only AG-UI tool result display payload, if present."""
    display_values = _extract_tool_result_marker_values(content, TOOL_RESULT_DISPLAY_KEY)
    return display_values[-1] if display_values else _UNSET


def _stringify_tool_result(raw_result: Any) -> str:  # noqa: ANN401
    return raw_result if isinstance(raw_result, str) else json.dumps(make_json_safe(raw_result))


def _resolve_ui_payload(llm_str: str, display_result: Any) -> str:  # noqa: ANN401
    """Pick the UI-bound string: the serialized display payload when set, else the LLM string."""
    return llm_str if display_result is _UNSET else _stringify_tool_result(display_result)


def _emit_tool_result_common(
    call_id: str,
    raw_result: Any,
    flow: FlowState,
    predictive_handler: PredictiveStateHandler | None = None,
    *,
    state_update: Mapping[str, Any] | None = None,
    display_result: Any = _UNSET,  # noqa: ANN401
) -> list[BaseEvent]:
    """Shared helper for emitting ToolCallEnd + ToolCallResult events and performing FlowState cleanup.

    Both ``_emit_tool_result`` (standard function results) and ``_emit_mcp_tool_result``
    (MCP server tool results) delegate to this function.

    Args:
        call_id: Tool call identifier.
        raw_result: The stringified tool result content sent back to the LLM.
        flow: Current ``FlowState``.
        predictive_handler: Optional predictive state handler driven by
            ``predict_state_config``.
        state_update: Optional deterministic state snapshot produced by a tool
            returning :func:`agent_framework_ag_ui.state_update`. When present,
            it is merged into ``flow.current_state`` and a ``StateSnapshotEvent``
            is emitted after the ``ToolCallResult`` event. When both
            ``predictive_handler`` and ``state_update`` are active, predictive
            updates are applied first, then the deterministic merge, and a
            single coalesced ``StateSnapshotEvent`` is emitted.
    """
    events: list[BaseEvent] = []

    events.append(ToolCallEndEvent(tool_call_id=call_id))
    flow.tool_calls_ended.add(call_id)

    result_content = _stringify_tool_result(raw_result)
    ui_result_content = _resolve_ui_payload(result_content, display_result)
    message_id = generate_event_id()
    events.append(
        ToolCallResultEvent(
            message_id=message_id,
            tool_call_id=call_id,
            content=ui_result_content,
            role="tool",
        )
    )

    flow.tool_results.append(
        {
            "id": message_id,
            "role": "tool",
            "toolCallId": call_id,
            "content": result_content,
        }
    )

    if predictive_handler:
        predictive_handler.apply_pending_updates()

    if state_update:
        flow.current_state.update(state_update)
        logger.debug(
            "Emitted deterministic tool-result StateSnapshotEvent for call_id=%s (keys=%s)",
            call_id,
            list(state_update.keys()),
        )

    # Emit a single coalesced snapshot when either mechanism updated state.
    if (predictive_handler or state_update) and flow.current_state:
        events.append(StateSnapshotEvent(snapshot=flow.current_state))

    flow.tool_call_id = None
    flow.tool_call_name = None

    if flow.message_id:
        logger.debug("Closing text message: message_id=%s", flow.message_id)
        events.append(TextMessageEndEvent(message_id=flow.message_id))
    flow.message_id = None
    flow.accumulated_text = ""

    return events


def _emit_tool_result(
    content: Content,
    flow: FlowState,
    predictive_handler: PredictiveStateHandler | None = None,
) -> list[BaseEvent]:
    """Emit ToolCallResult events for function_result content."""
    if not content.call_id:
        return []
    raw_result = content.result if content.result is not None else ""
    state_update = _extract_tool_result_state(content)
    display_result = _extract_tool_result_display(content)
    return _emit_tool_result_common(
        content.call_id,
        raw_result,
        flow,
        predictive_handler,
        state_update=state_update,
        display_result=display_result,
    )


def _emit_approval_request(
    content: Content,
    flow: FlowState,
    predictive_handler: PredictiveStateHandler | None = None,
    require_confirmation: bool = True,
) -> list[BaseEvent]:
    """Emit events for function approval request."""
    events: list[BaseEvent] = []

    func_call = content.function_call
    if not func_call:
        logger.warning("Approval request content missing function_call, skipping")
        return events

    func_name = func_call.name or ""
    func_call_id = func_call.call_id

    if predictive_handler and func_name:
        parsed_args = func_call.parse_arguments()
        result = predictive_handler.extract_state_value(func_name, parsed_args)
        if result:
            state_key, state_value = result
            flow.current_state[state_key] = state_value
            events.append(StateSnapshotEvent(snapshot=flow.current_state))

    if func_call_id:
        events.append(ToolCallEndEvent(tool_call_id=func_call_id))
        flow.tool_calls_ended.add(func_call_id)

    events.append(
        CustomEvent(
            name="function_approval_request",
            value={
                "id": content.id,
                "function_call": {
                    "call_id": func_call_id,
                    "name": func_name,
                    "arguments": make_json_safe(func_call.parse_arguments()),
                },
            },
        )
    )
    interrupt_id = func_call_id or content.id
    if interrupt_id:
        flow.interrupts.append(
            _approval_interrupt_for_function_call(
                interrupt_id=str(interrupt_id),
                function_call=func_call,
            )
        )

    if require_confirmation:
        confirm_id = generate_event_id()
        events.append(
            ToolCallStartEvent(
                tool_call_id=confirm_id,
                tool_call_name="confirm_changes",
                parent_message_id=flow.message_id,
            )
        )
        args: dict[str, Any] = {
            "function_name": func_name,
            "function_call_id": func_call_id,
            "function_arguments": make_json_safe(func_call.parse_arguments()) or {},
            "steps": [{"description": f"Execute {func_name}", "status": "enabled"}],
        }
        args_json = json.dumps(args)
        events.append(ToolCallArgsEvent(tool_call_id=confirm_id, delta=args_json))
        events.append(ToolCallEndEvent(tool_call_id=confirm_id))

        confirm_entry = {
            "id": confirm_id,
            "type": "function",
            "function": {"name": "confirm_changes", "arguments": args_json},
        }
        flow.pending_tool_calls.append(confirm_entry)
        flow.tool_calls_by_id[confirm_id] = confirm_entry
        flow.tool_calls_ended.add(confirm_id)
        _track_tool_call_segment(flow, confirm_id)

    flow.waiting_for_approval = True
    return events


def _emit_usage(content: Content) -> list[BaseEvent]:
    """Emit usage details as a protocol-level custom event."""
    usage_details = make_json_safe(content.usage_details or {})
    return [CustomEvent(name="usage", value=usage_details)]


def _emit_oauth_consent(content: Content) -> list[BaseEvent]:
    """Emit an OAuth consent request as a custom event so frontends can render a consent link."""
    return (
        [CustomEvent(name="oauth_consent_request", value={"consent_link": content.consent_link})]
        if content.consent_link
        else []
    )


def _emit_mcp_tool_call(content: Content, flow: FlowState) -> list[BaseEvent]:
    """Emit ToolCall start/args events for MCP server tool call content.

    MCP tool calls arrive as complete items (not streamed deltas), so we emit a
    ``ToolCallStartEvent`` (and, when arguments are present, a ``ToolCallArgsEvent``)
    immediately. This maps MCP-specific fields (tool_name, server_name) to the
    same AG-UI ToolCall* events used by regular function calls, making MCP tool
    execution visible to AG-UI consumers. Completion/end events are handled
    separately by ``_emit_mcp_tool_result``.
    """
    events: list[BaseEvent] = []

    tool_call_id = content.call_id or generate_event_id()
    tool_name = content.tool_name or "mcp_tool"

    display_name = tool_name

    events.append(
        ToolCallStartEvent(
            tool_call_id=tool_call_id,
            tool_call_name=display_name,
            parent_message_id=flow.message_id,
        )
    )

    # Serialize arguments
    args_str = ""
    if content.arguments:
        args_str = (
            content.arguments if isinstance(content.arguments, str) else json.dumps(make_json_safe(content.arguments))
        )
        events.append(ToolCallArgsEvent(tool_call_id=tool_call_id, delta=args_str))

    # Track in flow state for MESSAGES_SNAPSHOT
    tool_entry = {
        "id": tool_call_id,
        "type": "function",
        "function": {"name": display_name, "arguments": args_str},
    }
    flow.pending_tool_calls.append(tool_entry)
    flow.tool_calls_by_id[tool_call_id] = tool_entry
    _track_tool_call_segment(flow, tool_call_id)

    return events


def _emit_mcp_tool_result(
    content: Content, flow: FlowState, predictive_handler: PredictiveStateHandler | None = None
) -> list[BaseEvent]:
    """Emit ToolCallResult events for MCP server tool result content.

    Delegates to the shared _emit_tool_result_common helper using content.output
    (the MCP-specific result field) instead of content.result.
    """
    if not content.call_id:
        logger.warning("MCP tool result content missing call_id, skipping")
        return []
    raw_output = content.output if content.output is not None else ""
    state_update = _extract_tool_result_state(content)
    display_result = _extract_tool_result_display(content)
    return _emit_tool_result_common(
        content.call_id,
        raw_output,
        flow,
        predictive_handler,
        state_update=state_update,
        display_result=display_result,
    )


def _close_reasoning_block(flow: FlowState) -> list[BaseEvent]:
    """Close an open reasoning block, emitting end events.

    Should be called when the reasoning block is complete -- e.g. when
    non-reasoning content arrives or at end of a run.
    """
    if not flow.reasoning_message_id:
        return []
    message_id = flow.reasoning_message_id
    flow.reasoning_message_id = None
    return [
        ReasoningMessageEndEvent(message_id=message_id),
        ReasoningEndEvent(message_id=message_id),
    ]


def _emit_text_reasoning(content: Content, flow: FlowState | None = None) -> list[BaseEvent]:
    """Emit AG-UI reasoning events for text_reasoning content.

    Uses the protocol-defined reasoning event types so that AG-UI consumers
    such as CopilotKit can render reasoning natively.

    When *flow* is provided the function follows the streaming pattern: it
    emits ``ReasoningStartEvent`` / ``ReasoningMessageStartEvent`` only on
    the first delta for a given ``message_id`` and just
    ``ReasoningMessageContentEvent`` for subsequent deltas.  The matching
    ``ReasoningMessageEndEvent`` / ``ReasoningEndEvent`` are deferred until
    ``_close_reasoning_block`` is called (e.g. when non-reasoning content
    arrives or at end-of-run).

    Without *flow* (backward-compat) the full Start→Content→End sequence is
    emitted for every call.

    Only ``content.text`` is used for the visible reasoning message. If
    ``content.protected_data`` is present it is emitted as a
    ``ReasoningEncryptedValueEvent`` so that consumers can persist encrypted
    reasoning for state continuity without conflating it with display text.

    When *flow* is provided the reasoning message is persisted into
    ``flow.reasoning_messages`` so that ``_build_messages_snapshot`` can
    include it in the final ``MESSAGES_SNAPSHOT``.
    """
    text = content.text or ""
    if not text and content.protected_data is None:
        return []

    if content.id:
        message_id = content.id
    elif flow is not None and flow.reasoning_message_id:
        message_id = flow.reasoning_message_id
    else:
        message_id = generate_event_id()

    events: list[BaseEvent] = []

    if flow is not None:
        # Streaming mode: track open reasoning block in flow state.
        if flow.reasoning_message_id != message_id:
            # Close any previously open reasoning block (different message_id).
            events.extend(_close_reasoning_block(flow))
            # Open new reasoning block.
            events.append(ReasoningStartEvent(message_id=message_id))
            events.append(ReasoningMessageStartEvent(message_id=message_id, role="reasoning"))
            flow.reasoning_message_id = message_id

        if text:
            events.append(ReasoningMessageContentEvent(message_id=message_id, delta=text))

        if content.protected_data is not None:
            events.append(
                ReasoningEncryptedValueEvent(
                    subtype="message",
                    entity_id=message_id,
                    encrypted_value=content.protected_data,
                )
            )
    else:
        # No flow -- backward-compatible full sequence per call.
        events.append(ReasoningStartEvent(message_id=message_id))
        events.append(ReasoningMessageStartEvent(message_id=message_id, role="reasoning"))

        if text:
            events.append(ReasoningMessageContentEvent(message_id=message_id, delta=text))

        events.append(ReasoningMessageEndEvent(message_id=message_id))

        if content.protected_data is not None:
            events.append(
                ReasoningEncryptedValueEvent(
                    subtype="message",
                    entity_id=message_id,
                    encrypted_value=content.protected_data,
                )
            )

        events.append(ReasoningEndEvent(message_id=message_id))

    # Persist reasoning into flow state for MESSAGES_SNAPSHOT.
    # Accumulate reasoning text per message_id, similar to flow.accumulated_text,
    # so that incremental deltas build the full reasoning string.
    if flow is not None:
        if text:
            previous_text = flow.accumulated_reasoning.get(message_id, "")
            flow.accumulated_reasoning[message_id] = previous_text + text
        full_text = flow.accumulated_reasoning.get(message_id, text or "")

        # Update existing reasoning entry for this message_id if present; otherwise append a new one.
        existing_entry: dict[str, Any] | None = None
        for entry in flow.reasoning_messages:
            if isinstance(entry, dict) and entry.get("id") == message_id:
                existing_entry = entry
                break

        if existing_entry is None:
            reasoning_entry: dict[str, Any] = {
                "id": message_id,
                "role": "reasoning",
                "content": full_text,
            }
            if content.protected_data is not None:
                reasoning_entry["encryptedValue"] = content.protected_data
            flow.reasoning_messages.append(reasoning_entry)
            _track_reasoning_segment(flow, message_id)
        else:
            existing_entry["content"] = full_text
            if content.protected_data is not None:
                existing_entry["encryptedValue"] = content.protected_data

    return events


def _emit_content(
    content: Any,
    flow: FlowState,
    predictive_handler: PredictiveStateHandler | None = None,
    skip_text: bool = False,
    require_confirmation: bool = True,
) -> list[BaseEvent]:
    """Emit appropriate events for any content type."""
    content_type = getattr(content, "type", None)

    # Close open reasoning block when switching to non-reasoning content.
    if content_type != "text_reasoning":
        events = _close_reasoning_block(flow)
    else:
        events = []

    if content_type == "text":
        return events + _emit_text(content, flow, skip_text)
    if content_type == "function_call":
        return events + _emit_tool_call(content, flow, predictive_handler)
    if content_type == "function_result":
        return events + _emit_tool_result(content, flow, predictive_handler)
    if content_type == "function_approval_request":
        return events + _emit_approval_request(content, flow, predictive_handler, require_confirmation)
    if content_type == "usage":
        return events + _emit_usage(content)
    if content_type == "oauth_consent_request":
        return events + _emit_oauth_consent(content)
    if content_type == "mcp_server_tool_call":
        return events + _emit_mcp_tool_call(content, flow)
    if content_type == "mcp_server_tool_result":
        return events + _emit_mcp_tool_result(content, flow, predictive_handler)
    if content_type == "text_reasoning":
        return _emit_text_reasoning(content, flow)
    logger.debug("Skipping unsupported content type in AG-UI emitter: %s", content_type)
    return events


def _canonical_snapshot_message(message: dict[str, Any]) -> dict[str, Any]:
    """Normalize an AG-UI message for identity comparison without generated ids."""
    from ._message_adapters import agui_messages_to_snapshot_format

    normalized_message = agui_messages_to_snapshot_format([copy.deepcopy(message)])[0]
    normalized_message.pop("id", None)
    return cast(dict[str, Any], make_json_safe(normalized_message))


def _snapshot_messages_match(stored_message: dict[str, Any], incoming_message: dict[str, Any]) -> bool:
    """Return whether an incoming message already represents the stored snapshot message."""
    stored_id = stored_message.get("id")
    incoming_id = incoming_message.get("id")
    if stored_id and incoming_id:
        return str(stored_id) == str(incoming_id)
    return _canonical_snapshot_message(stored_message) == _canonical_snapshot_message(incoming_message)


def _latest_user_message_index(messages: list[dict[str, Any]]) -> int | None:
    """Find the newest incoming user message index."""
    for index in range(len(messages) - 1, -1, -1):
        if normalize_agui_role(messages[index].get("role", "user")) == "user":
            return index
    return None


def _known_tool_call_ids(
    stored_messages: list[dict[str, Any]],
    stored_interrupt: list[dict[str, Any]] | None,
) -> set[str]:
    """Collect tool call ids the backend previously issued for this thread."""
    known_ids: set[str] = set()
    for message in stored_messages:
        tool_calls = message.get("tool_calls") or message.get("toolCalls") or []
        if not isinstance(tool_calls, list):
            continue
        for tool_call in cast(list[Any], tool_calls):
            if isinstance(tool_call, dict):
                tool_call_id = cast(dict[str, Any], tool_call).get("id")
                if tool_call_id:
                    known_ids.add(str(tool_call_id))
    for interrupt in stored_interrupt or []:
        interrupt_id = interrupt.get("id")
        if interrupt_id:
            known_ids.add(str(interrupt_id))
        canonical_tool_call_id = interrupt.get("toolCallId") or interrupt.get("tool_call_id")
        if canonical_tool_call_id:
            known_ids.add(str(canonical_tool_call_id))
    return known_ids


def _filter_untrusted_suffix(
    incoming_suffix: list[dict[str, Any]],
    *,
    stored_messages: list[dict[str, Any]],
    stored_interrupt: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Drop client-forged non-user messages before promoting them to stored history.

    Only the user's own turns and tool results answering backend-issued tool calls
    (including pending interrupts) may extend the authoritative thread history.
    """
    known_ids: set[str] | None = None
    filtered: list[dict[str, Any]] = []
    for message in incoming_suffix:
        raw_role = str(message.get("role", "")).lower()
        if raw_role == "user":
            filtered.append(message)
            continue
        if raw_role == "tool":
            tool_call_id = message.get("toolCallId") or message.get("tool_call_id") or message.get("actionExecutionId")
            if known_ids is None:
                known_ids = _known_tool_call_ids(stored_messages, stored_interrupt)
            if tool_call_id and str(tool_call_id) in known_ids:
                filtered.append(message)
                continue
        logger.warning(
            "Dropping client-supplied %r message from the incoming thread suffix; "
            "only user turns and tool results for backend-issued tool calls extend stored history.",
            raw_role or "unknown",
        )
    return filtered


def _reconstruct_messages_from_thread_snapshot(
    *,
    stored_messages: list[dict[str, Any]],
    incoming_messages: list[dict[str, Any]],
    stored_interrupt: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Combine backend-owned prior history with the request-owned new user turn."""
    if not stored_messages or not incoming_messages:
        return incoming_messages

    incoming_suffix: list[dict[str, Any]]
    if len(incoming_messages) >= len(stored_messages) and all(
        _snapshot_messages_match(stored_message, incoming_message)
        for stored_message, incoming_message in zip(stored_messages, incoming_messages)
    ):
        incoming_suffix = incoming_messages[len(stored_messages) :]
    else:
        latest_user_index = _latest_user_message_index(incoming_messages)
        if latest_user_index is None:
            return incoming_messages
        incoming_suffix = incoming_messages[latest_user_index:]

    incoming_suffix = _filter_untrusted_suffix(
        incoming_suffix,
        stored_messages=stored_messages,
        stored_interrupt=stored_interrupt,
    )

    return [copy.deepcopy(message) for message in stored_messages] + [
        copy.deepcopy(message) for message in incoming_suffix
    ]
