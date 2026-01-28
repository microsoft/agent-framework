# Copyright (c) Microsoft. All rights reserved.

"""Utility functions for AG-UI integration."""

import copy
import json
import uuid
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from agent_framework import AgentResponseUpdate, ChatResponseUpdate, FunctionTool, Role, ToolProtocol

# Role mapping constants
AGUI_TO_FRAMEWORK_ROLE: dict[str, Role] = {
    "user": Role.USER,
    "assistant": Role.ASSISTANT,
    "system": Role.SYSTEM,
}

FRAMEWORK_TO_AGUI_ROLE: dict[Role, str] = {
    Role.USER: "user",
    Role.ASSISTANT: "assistant",
    Role.SYSTEM: "system",
}

ALLOWED_AGUI_ROLES: set[str] = {"user", "assistant", "system", "tool"}


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
        Normalized role string (user, assistant, system, or tool)
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


def make_json_safe(obj: Any) -> Any:  # noqa: ANN401
    """Make an object JSON serializable.

    Args:
        obj: Object to make JSON safe

    Returns:
        JSON-serializable version of the object
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if is_dataclass(obj):
        # asdict may return nested non-dataclass objects, so recursively make them safe
        return make_json_safe(asdict(obj))  # type: ignore[arg-type]
    if hasattr(obj, "model_dump"):
        return make_json_safe(obj.model_dump())  # type: ignore[no-any-return]
    if hasattr(obj, "to_dict"):
        return make_json_safe(obj.to_dict())  # type: ignore[no-any-return]
    if hasattr(obj, "dict"):
        return make_json_safe(obj.dict())  # type: ignore[no-any-return]
    if hasattr(obj, "__dict__"):
        return {key: make_json_safe(value) for key, value in vars(obj).items()}  # type: ignore[misc]
    if isinstance(obj, (list, tuple)):
        return [make_json_safe(item) for item in obj]  # type: ignore[misc]
    if isinstance(obj, dict):
        return {key: make_json_safe(value) for key, value in obj.items()}  # type: ignore[misc]
    return str(obj)


def convert_agui_tools_to_agent_framework(
    agui_tools: list[dict[str, Any]] | None,
) -> list[FunctionTool[Any, Any]] | None:
    """Convert AG-UI tool definitions to Agent Framework FunctionTool declarations.

    Creates declaration-only FunctionTool instances (no executable implementation).
    These are used to tell the LLM about available tools. The actual execution
    happens on the client side via @use_function_invocation.

    CRITICAL: These tools MUST have func=None so that declaration_only returns True.
    This prevents the server from trying to execute client-side tools.

    Args:
        agui_tools: List of AG-UI tool definitions with name, description, parameters

    Returns:
        List of FunctionTool declarations, or None if no tools provided
    """
    if not agui_tools:
        return None

    result: list[FunctionTool[Any, Any]] = []
    for tool_def in agui_tools:
        # Create declaration-only FunctionTool (func=None means no implementation)
        # When func=None, the declaration_only property returns True,
        # which tells @use_function_invocation to return the function call
        # without executing it (so it can be sent back to the client)
        func: FunctionTool[Any, Any] = FunctionTool(
            name=tool_def.get("name", ""),
            description=tool_def.get("description", ""),
            func=None,  # CRITICAL: Makes declaration_only=True
            input_model=tool_def.get("parameters", {}),
        )
        result.append(func)

    return result


def convert_tools_to_agui_format(
    tools: (
        ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None
    ),
) -> list[dict[str, Any]] | None:
    """Convert tools to AG-UI format.

    This sends only the metadata (name, description, JSON schema) to the server.
    The actual executable implementation stays on the client side.
    The @use_function_invocation decorator handles client-side execution when
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
        tool_list: list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]] = [tools]  # type: ignore[list-item]
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
        elif isinstance(tool_item, ToolProtocol):
            # Handle other ToolProtocol implementations
            # For now, we'll skip non-FunctionTool instances as they may not have
            # the parameters() method. This matches .NET behavior which only
            # converts FunctionToolDeclaration instances.
            continue

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
