# Copyright (c) Microsoft. All rights reserved.

"""Utility functions for AG-UI integration."""

from __future__ import annotations

import copy
import json
import uuid
from collections.abc import Callable, MutableMapping, Sequence
from typing import Any

from agent_framework import AgentResponseUpdate, ChatResponseUpdate, FunctionTool
from agent_framework import _mcp as _core_mcp  # pyright: ignore[reportPrivateUsage]
from agent_framework._serialization import make_json_safe  # pyright: ignore[reportPrivateUsage]

# AG-UI supports older core releases that predate this marker; those versions retain the existing fallback behavior.
_MCP_TOOL_RESULT_HOST_PAYLOAD_KEY = getattr(
    _core_mcp,
    "_MCP_TOOL_RESULT_HOST_PAYLOAD_KEY",
    "_mcp_tool_result_host_payload",
)
_AGUI_TOOL_RESULT_MODEL_CONTENT_KEY = "_agentFrameworkModelContent"
_AGUI_MCP_TOOL_RESULT_KEY = "_agentFrameworkMcpResult"
_AGUI_HOST_PAYLOAD_OMITTED_KEY = "_agentFrameworkHostPayloadOmitted"
DEFAULT_MAX_HOST_PAYLOAD_HISTORY_SIZE_BYTES = 8 * 1024 * 1024

# Role mapping constants
AGUI_TO_FRAMEWORK_ROLE: dict[str, str] = {
    "user": "user",
    "assistant": "assistant",
    "system": "system",
}

FRAMEWORK_TO_AGUI_ROLE: dict[str, str] = {
    "user": "user",
    "assistant": "assistant",
    "system": "system",
}

ALLOWED_AGUI_ROLES: set[str] = {"user", "assistant", "system", "tool", "reasoning"}


def generate_event_id() -> str:
    """Generate a unique event ID."""
    return str(uuid.uuid4())


def safe_json_parse(value: Any) -> dict[str, Any] | None:
    """Safely parse a value as JSON dict.

    Args:
        value: String or dict to parse

    Returns:
        Parsed dict or None if parsing fails
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


def _extract_tool_result_marker_values(content: Any, key: str) -> list[Any]:
    """Extract marker values from outer and inner tool-result content."""
    values: list[Any] = []

    outer_properties = getattr(content, "additional_properties", None) or {}
    if key in outer_properties:
        values.append(outer_properties[key])

    for item in getattr(content, "items", None) or ():
        item_properties = getattr(item, "additional_properties", None) or {}
        if key in item_properties:
            values.append(item_properties[key])

    return values


def _extract_mcp_tool_result_host_payload(content: Any) -> tuple[bool, Any]:
    """Return whether a core-preserved MCP Host payload exists and its value."""
    values = _extract_tool_result_marker_values(content, _MCP_TOOL_RESULT_HOST_PAYLOAD_KEY)
    return (True, values[-1]) if values else (False, None)


def _model_content_from_mcp_host_payload(payload: Any) -> str:
    """Recover safe content-only text when an MCP snapshot loses its model-content sidecar."""
    if not isinstance(payload, dict):
        return "Tool result unavailable."
    if payload.get("isError") is True:
        return "Error: Function failed."
    content = payload.get("content")
    if not isinstance(content, list):
        return "Tool result unavailable."

    text_parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            text_parts.append(item["text"])
            continue
        resource = item.get("resource")
        if item.get("type") == "resource" and isinstance(resource, dict) and isinstance(resource.get("text"), str):
            text_parts.append(resource["text"])
    return "\n".join(text_parts) if text_parts else "null"


def _model_items_for_agui_replay(content: Any, model_result: str) -> list[dict[str, Any]]:
    """Serialize model-facing items without repeating the MCP Host payload marker."""
    items = getattr(content, "items", None) or ()
    if not items:
        return [{"type": "text", "text": model_result}]

    serialized_items: list[dict[str, Any]] = []
    for item in items:
        serialized = item.to_dict()
        additional_properties = serialized.get("additional_properties")
        if isinstance(additional_properties, dict):
            additional_properties.pop(_MCP_TOOL_RESULT_HOST_PAYLOAD_KEY, None)
            if not additional_properties:
                serialized.pop("additional_properties", None)
        serialized_items.append(serialized)
    return serialized_items


def _model_text_from_replay_items(message: dict[str, Any]) -> str:
    serialized_items = message.get(_AGUI_TOOL_RESULT_MODEL_CONTENT_KEY)
    if not isinstance(serialized_items, list):
        return ""
    return "\n".join(
        item["text"]
        for item in serialized_items
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
    )


def _bound_host_payload_history(
    messages: list[dict[str, Any]],
    *,
    max_size_bytes: int,
) -> list[dict[str, Any]]:
    """Retain the newest MCP Host payloads within one aggregate history budget."""
    if max_size_bytes < 0:
        raise ValueError("max_size_bytes must be non-negative.")

    retained_size = 0
    omit_indices: set[int] = set()
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get(_AGUI_MCP_TOOL_RESULT_KEY) is not True:
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        content_size = len(content.encode("utf-8"))
        if retained_size + content_size > max_size_bytes:
            omit_indices.add(index)
        else:
            retained_size += content_size

    if not omit_indices:
        return messages

    bounded_messages: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if index not in omit_indices:
            bounded_messages.append(message)
            continue
        bounded_message = message.copy()
        bounded_message["content"] = _model_text_from_replay_items(message)
        bounded_message[_AGUI_HOST_PAYLOAD_OMITTED_KEY] = True
        bounded_messages.append(bounded_message)
    return bounded_messages


def _stringify_tool_result(raw_result: Any) -> str:
    """Serialize a tool result for an AG-UI tool message."""
    return raw_result if isinstance(raw_result, str) else json.dumps(make_json_safe(raw_result))


def canonical_function_arguments(function_call: Any) -> str | None:
    """Return a stable representation of function-call arguments."""
    if function_call is None:
        return None

    try:
        parsed_arguments = function_call.parse_arguments()
    except Exception:
        parsed_arguments = getattr(function_call, "arguments", None)

    if parsed_arguments is None:
        parsed_arguments = {}

    return json.dumps(make_json_safe(parsed_arguments), sort_keys=True, separators=(",", ":"))


def _function_call_server_label(function_call: Any) -> str | None:
    """Return a normalized hosted-tool server label."""
    if function_call is None:
        return None
    server_label = getattr(function_call, "additional_properties", {}).get("server_label")
    return server_label if isinstance(server_label, str) and server_label else None


def _approval_interrupt_id(content: Any) -> str | None:
    """Return the canonical client and lifecycle identity for an approval request."""
    function_call = getattr(content, "function_call", None)
    if function_call is None:
        return None
    request_id = getattr(content, "id", None)
    if _function_call_server_label(function_call) is not None:
        return request_id if isinstance(request_id, str) and request_id else None
    occurrence_id = getattr(function_call, "id", None)
    if isinstance(occurrence_id, str) and occurrence_id:
        return occurrence_id
    call_id = getattr(function_call, "call_id", None)
    if isinstance(call_id, str) and call_id:
        return call_id
    return request_id if isinstance(request_id, str) and request_id else None


def get_role_value(message: Any) -> str:
    """Extract role string from a message object.

    Handles both enum roles (with .value) and string roles.

    Args:
        message: Message object with role attribute

    Returns:
        Role as lowercase string, or empty string if not found
    """
    role = getattr(message, "role", None)
    if role is None:
        return ""
    if hasattr(role, "value"):
        return str(role.value)
    return str(role)


def normalize_agui_role(raw_role: Any) -> str:
    """Normalize an AG-UI role to a standard role string.

    Args:
        raw_role: Raw role value from AG-UI message

    Returns:
        Normalized role string (user, assistant, system, tool, or reasoning)
    """
    if not isinstance(raw_role, str):
        return "user"
    role = raw_role.lower()
    if role == "developer":
        return "system"
    if role in ALLOWED_AGUI_ROLES:
        return role
    return "user"


def extract_state_from_tool_args(
    args: dict[str, Any] | None,
    tool_arg_name: str,
) -> Any:
    """Extract state value from tool arguments based on config.

    Args:
        args: Parsed tool arguments dict
        tool_arg_name: Name of the argument to extract, or "*" for entire args

    Returns:
        Extracted state value, or None if not found
    """
    if not args:
        return None
    if tool_arg_name == "*":
        return args
    return args.get(tool_arg_name)


def merge_state(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merge state updates.

    Args:
        current: Current state dictionary
        update: Update to apply

    Returns:
        Merged state
    """
    result = copy.deepcopy(current)
    result.update(update)
    return result


def convert_agui_tools_to_agent_framework(
    agui_tools: list[dict[str, Any]] | None,
) -> list[FunctionTool] | None:
    """Convert AG-UI tool definitions to Agent Framework FunctionTool declarations.

    Creates declaration-only FunctionTool instances (no executable implementation).
    These are used to tell the LLM about available tools. The actual execution
    happens on the client side via function invocation mixin.

    CRITICAL: These tools MUST have func=None so that declaration_only returns True.
    This prevents the server from trying to execute client-side tools.

    Args:
        agui_tools: List of AG-UI tool definitions with name, description, parameters

    Returns:
        List of FunctionTool declarations, or None if no tools provided
    """
    if not agui_tools:
        return None

    result: list[FunctionTool] = []
    for tool_def in agui_tools:
        # Create declaration-only FunctionTool (func=None means no implementation)
        # When func=None, the declaration_only property returns True,
        # which tells the function invocation mixin to return the function call
        # without executing it (so it can be sent back to the client)
        func: FunctionTool = FunctionTool(
            name=tool_def.get("name", ""),
            description=tool_def.get("description", ""),
            func=None,  # CRITICAL: Makes declaration_only=True
            input_model=tool_def.get("parameters", {}),
        )
        result.append(func)

    return result


def convert_tools_to_agui_format(
    tools: (
        FunctionTool
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[FunctionTool | Callable[..., Any] | MutableMapping[str, Any]]
        | None
    ),
) -> list[dict[str, Any]] | None:
    """Convert tools to AG-UI format.

    This sends only the metadata (name, description, JSON schema) to the server.
    The actual executable implementation stays on the client side.
    The function invocation mixin handles client-side execution when
    the server requests a function.

    Args:
        tools: Tools to convert (single tool or sequence of tools)

    Returns:
        List of tool specifications in AG-UI format, or None if no tools provided
    """
    if not tools:
        return None

    # Normalize to list
    if not isinstance(tools, list):
        tool_list: list[FunctionTool | Callable[..., Any] | MutableMapping[str, Any]] = [tools]  # type: ignore[list-item]
    else:
        tool_list = tools  # type: ignore[assignment]

    results: list[dict[str, Any]] = []

    for tool_item in tool_list:
        if isinstance(tool_item, dict):
            # Already in dict format, pass through
            results.append(tool_item)  # type: ignore[arg-type]
        elif isinstance(tool_item, FunctionTool):
            # Convert FunctionTool to AG-UI tool format
            results.append(
                {
                    "name": tool_item.name,
                    "description": tool_item.description,
                    "parameters": tool_item.parameters(),
                }
            )
        elif callable(tool_item):
            # Convert callable to FunctionTool first, then to AG-UI format
            from agent_framework import tool

            ai_func = tool(tool_item)
            results.append(
                {
                    "name": ai_func.name,
                    "description": ai_func.description,
                    "parameters": ai_func.parameters(),
                }
            )
        # Note: dict-based hosted tools (CodeInterpreter, WebSearch, etc.) are passed through
        # as-is in the first branch. Non-FunctionTool, non-dict items are skipped.

    return results if results else None


def get_conversation_id_from_update(update: AgentResponseUpdate) -> str | None:
    """Extract conversation ID from AgentResponseUpdate metadata.

    Args:
        update: AgentRunResponseUpdate instance
    Returns:
        Conversation ID if present, else None

    """
    if isinstance(update.raw_representation, ChatResponseUpdate):
        return update.raw_representation.conversation_id
    return None
