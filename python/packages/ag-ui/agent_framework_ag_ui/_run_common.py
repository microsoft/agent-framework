# Copyright (c) Microsoft. All rights reserved.

"""Shared AG-UI run helpers used by agent and workflow runners."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, cast

from ag_ui.core import (
    BaseEvent,
    CustomEvent,
    ReasoningEncryptedValueEvent,
    ReasoningEndEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    ReasoningStartEvent,
    RunFinishedEvent,
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
from ._utils import generate_event_id, make_json_safe

logger = logging.getLogger(__name__)


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
        if not isinstance(item, dict):
            continue
        item_dict = cast(dict[str, Any], item)
        interrupt_id = item_dict.get("id") or item_dict.get("interruptId") or item_dict.get("toolCallId")
        if not interrupt_id:
            continue

        if "value" in item_dict:
            value = item_dict.get("value")
        elif "response" in item_dict:
            value = item_dict.get("response")
        else:
            value = {k: v for k, v in item_dict.items() if k not in {"id", "interruptId", "toolCallId", "type"}}

        normalized.append({"id": str(interrupt_id), "value": value})

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


def _build_run_finished_event(
    run_id: str, thread_id: str, interrupts: list[dict[str, Any]] | None = None
) -> RunFinishedEvent:
    """Create a RUN_FINISHED event, optionally carrying interrupt metadata."""
    if interrupts:
        return RunFinishedEvent(run_id=run_id, thread_id=thread_id, interrupt=interrupts)  # type: ignore[call-arg]
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

    def get_tool_name(self, call_id: str | None) -> str | None:
        """Get tool name by call ID."""
        if not call_id or call_id not in self.tool_calls_by_id:
            return None
        name = self.tool_calls_by_id[call_id]["function"].get("name")
        return str(name) if name else None

    def get_pending_without_end(self) -> list[dict[str, Any]]:
        """Get tool calls that started but never received an end event (declaration-only)."""
        return [tc for tc in self.pending_tool_calls if tc.get("id") not in self.tool_calls_ended]


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
        events.append(TextMessageStartEvent(message_id=flow.message_id, role="assistant"))
    elif flow.accumulated_text and content.text == flow.accumulated_text:
        # Guard against full-message replay chunks that can appear after streaming deltas.
        logger.debug("Skipping duplicate full-text delta for message_id=%s", flow.message_id)
        return []

    events.append(TextMessageContentEvent(message_id=flow.message_id, delta=content.text))
    flow.accumulated_text += content.text
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


def _emit_tool_result_common(
    call_id: str,
    raw_result: Any,
    flow: FlowState,
    predictive_handler: PredictiveStateHandler | None = None,
) -> list[BaseEvent]:
    """Shared helper for emitting ToolCallEnd + ToolCallResult events and performing FlowState cleanup.

    Both ``_emit_tool_result`` (standard function results) and ``_emit_mcp_tool_result``
    (MCP server tool results) delegate to this function.
    """
    events: list[BaseEvent] = []

    events.append(ToolCallEndEvent(tool_call_id=call_id))
    flow.tool_calls_ended.add(call_id)

    result_content = raw_result if isinstance(raw_result, str) else json.dumps(make_json_safe(raw_result))
    message_id = generate_event_id()
    events.append(
        ToolCallResultEvent(
            message_id=message_id,
            tool_call_id=call_id,
            content=result_content,
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
        if flow.current_state:
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
    return _emit_tool_result_common(content.call_id, raw_result, flow, predictive_handler)


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
            {
                "id": str(interrupt_id),
                "value": {
                    "type": "function_approval_request",
                    "function_call": {
                        "call_id": func_call_id,
                        "name": func_name,
                        "arguments": make_json_safe(func_call.parse_arguments()),
                    },
                },
            }
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
    return _emit_tool_result_common(content.call_id, raw_output, flow, predictive_handler)


def _emit_text_reasoning(content: Content, flow: FlowState | None = None) -> list[BaseEvent]:
    """Emit AG-UI reasoning events for text_reasoning content.

    Uses the protocol-defined reasoning event types so that AG-UI consumers
    such as CopilotKit can render reasoning natively.

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

    message_id = content.id or generate_event_id()

    events: list[BaseEvent] = [
        ReasoningStartEvent(message_id=message_id),
        ReasoningMessageStartEvent(message_id=message_id, role="assistant"),
    ]

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
    if content_type == "text":
        return _emit_text(content, flow, skip_text)
    if content_type == "function_call":
        return _emit_tool_call(content, flow, predictive_handler)
    if content_type == "function_result":
        return _emit_tool_result(content, flow, predictive_handler)
    if content_type == "function_approval_request":
        return _emit_approval_request(content, flow, predictive_handler, require_confirmation)
    if content_type == "usage":
        return _emit_usage(content)
    if content_type == "oauth_consent_request":
        return _emit_oauth_consent(content)
    if content_type == "mcp_server_tool_call":
        return _emit_mcp_tool_call(content, flow)
    if content_type == "mcp_server_tool_result":
        return _emit_mcp_tool_result(content, flow, predictive_handler)
    if content_type == "text_reasoning":
        return _emit_text_reasoning(content, flow)
    logger.debug("Skipping unsupported content type in AG-UI emitter: %s", content_type)
    return []
