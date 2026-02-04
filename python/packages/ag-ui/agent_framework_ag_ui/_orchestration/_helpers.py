# Copyright (c) Microsoft. All rights reserved.

"""Helper functions for orchestration logic.

Most orchestration helpers have been moved inline to _run.py.
This module retains utilities that may be useful for testing or extensions.
"""

import json
import logging
from typing import Any

from agent_framework import (
    ChatMessage,
    Content,
)

from .._utils import get_role_value

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
            if content.type == "function_call" and content.call_id:
                pending_ids.add(str(content.call_id))
            elif content.type == "function_result" and content.call_id:
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
        if content.type == "text" and content.text.startswith("Current state of the application:"):  # type: ignore[union-attr]
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


def build_safe_metadata(thread_metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Build metadata dict with truncated string values for Azure compatibility.

    Azure has a 512 character limit per metadata value.

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


def latest_approval_response(messages: list[ChatMessage]) -> Content | None:
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
        if content.type == "function_approval_response":
            return content
    return None


def approval_steps(approval: Content) -> list[Any]:
    """Extract steps from an approval response.

    Args:
        approval: Approval response content

    Returns:
        List of steps, or empty list if none
    """
    state_args = approval.additional_properties.get("ag_ui_state_args", None)
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
    approval: Content,
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
