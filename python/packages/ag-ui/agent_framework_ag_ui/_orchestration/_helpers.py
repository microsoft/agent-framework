# Copyright (c) Microsoft. All rights reserved.

"""Helper functions for orchestration logic."""

import json
import logging
from typing import TYPE_CHECKING, Any

from ag_ui.core import StateSnapshotEvent
from agent_framework import (
    ChatMessage,
    FunctionApprovalResponseContent,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
)

from .._utils import get_role_value, safe_json_parse

if TYPE_CHECKING:
    from .._events import AgentFrameworkEventBridge
    from ._state_manager import StateManager

logger = logging.getLogger(__name__)


def pending_tool_call_ids(messages: list[ChatMessage]) -> set[str]:
    """Get IDs of tool calls without corresponding results.

    Args:
        messages: List of messages to scan

    Returns:
        Set of pending tool call IDs
    """
    pending_ids: set[str] = set()
    resolved_ids: set[str] = set()
    for msg in messages:
        for content in msg.contents:
            if isinstance(content, FunctionCallContent) and content.call_id:
                pending_ids.add(str(content.call_id))
            elif isinstance(content, FunctionResultContent) and content.call_id:
                resolved_ids.add(str(content.call_id))
    return pending_ids - resolved_ids


def is_state_context_message(message: ChatMessage) -> bool:
    """Check if a message is a state context system message.

    Args:
        message: Message to check

    Returns:
        True if this is a state context message
    """
    if get_role_value(message) != "system":
        return False
    for content in message.contents:
        if isinstance(content, TextContent) and content.text.startswith("Current state of the application:"):
            return True
    return False


def ensure_tool_call_entry(
    tool_call_id: str,
    tool_calls_by_id: dict[str, dict[str, Any]],
    pending_tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Get or create a tool call entry in the tracking dicts.

    Args:
        tool_call_id: The tool call ID
        tool_calls_by_id: Dict mapping IDs to tool call entries
        pending_tool_calls: List of pending tool calls

    Returns:
        The tool call entry dict
    """
    entry = tool_calls_by_id.get(tool_call_id)
    if entry is None:
        entry = {
            "id": tool_call_id,
            "type": "function",
            "function": {
                "name": "",
                "arguments": "",
            },
        }
        tool_calls_by_id[tool_call_id] = entry
        pending_tool_calls.append(entry)
    return entry


def tool_name_for_call_id(
    tool_calls_by_id: dict[str, dict[str, Any]],
    tool_call_id: str,
) -> str | None:
    """Get the tool name for a given call ID.

    Args:
        tool_calls_by_id: Dict mapping IDs to tool call entries
        tool_call_id: The tool call ID to look up

    Returns:
        Tool name or None if not found
    """
    entry = tool_calls_by_id.get(tool_call_id)
    if not entry:
        return None
    function = entry.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    return str(name) if name else None


def tool_calls_match_state(
    provider_messages: list[ChatMessage],
    state_manager: "StateManager",
) -> bool:
    """Check if tool calls in messages match current state.

    Args:
        provider_messages: Messages to check
        state_manager: State manager with config and current state

    Returns:
        True if tool calls match state configuration
    """
    if not state_manager.predict_state_config or not state_manager.current_state:
        return False

    for state_key, config in state_manager.predict_state_config.items():
        tool_name = config["tool"]
        tool_arg_name = config["tool_argument"]
        tool_args: dict[str, Any] | None = None

        for msg in reversed(provider_messages):
            if get_role_value(msg) != "assistant":
                continue
            for content in msg.contents:
                if isinstance(content, FunctionCallContent) and content.name == tool_name:
                    tool_args = safe_json_parse(content.arguments)
                    break
            if tool_args is not None:
                break

        if not tool_args:
            return False

        if tool_arg_name == "*":
            state_value = tool_args
        elif tool_arg_name in tool_args:
            state_value = tool_args[tool_arg_name]
        else:
            return False

        if state_manager.current_state.get(state_key) != state_value:
            return False

    return True


def schema_has_steps(schema: Any) -> bool:
    """Check if a schema has a steps array property.

    Args:
        schema: JSON schema to check

    Returns:
        True if schema has steps array
    """
    if not isinstance(schema, dict):
        return False
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return False
    steps_schema = properties.get("steps")
    if not isinstance(steps_schema, dict):
        return False
    return steps_schema.get("type") == "array"


def select_approval_tool_name(client_tools: list[Any] | None) -> str | None:
    """Select appropriate approval tool from client tools.

    Args:
        client_tools: List of client tool definitions

    Returns:
        Name of approval tool, or None if not found
    """
    if not client_tools:
        return None
    for tool in client_tools:
        tool_name = getattr(tool, "name", None)
        if not tool_name:
            continue
        params_fn = getattr(tool, "parameters", None)
        if not callable(params_fn):
            continue
        schema = params_fn()
        if schema_has_steps(schema):
            return str(tool_name)
    return None


def select_messages_to_run(
    provider_messages: list[ChatMessage],
    state_manager: "StateManager",
) -> list[ChatMessage]:
    """Select and prepare messages for agent execution.

    Injects state context message when appropriate.

    Args:
        provider_messages: Original messages from client
        state_manager: State manager instance

    Returns:
        Messages ready for agent execution
    """
    if not provider_messages:
        return []

    is_new_user_turn = get_role_value(provider_messages[-1]) == "user"
    conversation_has_tool_calls = tool_calls_match_state(provider_messages, state_manager)
    state_context_msg = state_manager.state_context_message(
        is_new_user_turn=is_new_user_turn, conversation_has_tool_calls=conversation_has_tool_calls
    )
    if not state_context_msg:
        return list(provider_messages)

    messages_to_run = [msg for msg in provider_messages if not is_state_context_message(msg)]
    if pending_tool_call_ids(messages_to_run):
        return messages_to_run

    insert_index = len(messages_to_run) - 1 if is_new_user_turn else len(messages_to_run)
    if insert_index < 0:
        insert_index = 0
    messages_to_run.insert(insert_index, state_context_msg)
    return messages_to_run


def build_safe_metadata(thread_metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Build metadata dict with truncated string values.

    Args:
        thread_metadata: Raw metadata dict

    Returns:
        Metadata with string values truncated to 512 chars
    """
    if not thread_metadata:
        return {}
    safe_metadata: dict[str, Any] = {}
    for key, value in thread_metadata.items():
        value_str = value if isinstance(value, str) else json.dumps(value)
        if len(value_str) > 512:
            value_str = value_str[:512]
        safe_metadata[key] = value_str
    return safe_metadata


def collect_approved_state_snapshots(
    provider_messages: list[ChatMessage],
    predict_state_config: dict[str, dict[str, str]] | None,
    current_state: dict[str, Any],
    event_bridge: "AgentFrameworkEventBridge",
) -> list[StateSnapshotEvent]:
    """Collect state snapshots from approved function calls.

    Args:
        provider_messages: Messages containing approvals
        predict_state_config: Predictive state configuration
        current_state: Current state dict (will be mutated)
        event_bridge: Event bridge for creating events

    Returns:
        List of state snapshot events
    """
    if not predict_state_config:
        return []

    events: list[StateSnapshotEvent] = []
    for msg in provider_messages:
        if get_role_value(msg) != "user":
            continue
        for content in msg.contents:
            if type(content) is FunctionApprovalResponseContent:
                if not content.function_call or not content.approved:
                    continue
                parsed_args = content.function_call.parse_arguments()
                state_args = None
                if content.additional_properties:
                    state_args = content.additional_properties.get("ag_ui_state_args")
                if not isinstance(state_args, dict):
                    state_args = parsed_args
                if not state_args:
                    continue
                for state_key, config in predict_state_config.items():
                    if config["tool"] != content.function_call.name:
                        continue
                    tool_arg_name = config["tool_argument"]
                    if tool_arg_name == "*":
                        state_value = state_args
                    elif isinstance(state_args, dict) and tool_arg_name in state_args:
                        state_value = state_args[tool_arg_name]
                    else:
                        continue
                    current_state[state_key] = state_value
                    event_bridge.current_state[state_key] = state_value
                    logger.info(
                        f"Emitting StateSnapshotEvent for approved state key '{state_key}' "
                        f"with {len(state_value) if isinstance(state_value, list) else 'N/A'} items"
                    )
                    events.append(StateSnapshotEvent(snapshot=current_state))
                    break
    return events


def latest_approval_response(messages: list[ChatMessage]) -> FunctionApprovalResponseContent | None:
    """Get the latest approval response from messages.

    Args:
        messages: Messages to search

    Returns:
        Latest approval response or None
    """
    if not messages:
        return None
    last_message = messages[-1]
    for content in last_message.contents:
        if type(content) is FunctionApprovalResponseContent:
            return content
    return None


def approval_steps(approval: FunctionApprovalResponseContent) -> list[Any]:
    """Extract steps from an approval response.

    Args:
        approval: Approval response content

    Returns:
        List of steps, or empty list if none
    """
    state_args: Any | None = None
    if approval.additional_properties:
        state_args = approval.additional_properties.get("ag_ui_state_args")
    if isinstance(state_args, dict):
        steps = state_args.get("steps")
        if isinstance(steps, list):
            return steps

    if approval.function_call:
        parsed_args = approval.function_call.parse_arguments()
        if isinstance(parsed_args, dict):
            steps = parsed_args.get("steps")
            if isinstance(steps, list):
                return steps

    return []


def is_step_based_approval(
    approval: FunctionApprovalResponseContent,
    predict_state_config: dict[str, dict[str, str]] | None,
) -> bool:
    """Check if an approval is step-based.

    Args:
        approval: Approval response to check
        predict_state_config: Predictive state configuration

    Returns:
        True if this is a step-based approval
    """
    steps = approval_steps(approval)
    if steps:
        return True
    if not approval.function_call:
        return False
    if not predict_state_config:
        return False
    tool_name = approval.function_call.name
    for config in predict_state_config.values():
        if config.get("tool") == tool_name and config.get("tool_argument") == "steps":
            return True
    return False
