# Copyright (c) Microsoft. All rights reserved.

"""Utility functions for AG-UI integration."""

import copy
import uuid
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from agent_framework import AIFunction, ToolProtocol


def generate_event_id() -> str:
    """Generate a unique event ID."""
    return str(uuid.uuid4())


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
        return asdict(obj)  # type: ignore[arg-type]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # type: ignore[no-any-return]
    if hasattr(obj, "dict"):
        return obj.dict()  # type: ignore[no-any-return]
    if hasattr(obj, "__dict__"):
        return {key: make_json_safe(value) for key, value in vars(obj).items()}  # type: ignore[misc]
    if isinstance(obj, (list, tuple)):
        return [make_json_safe(item) for item in obj]  # type: ignore[misc]
    if isinstance(obj, dict):
        return {key: make_json_safe(value) for key, value in obj.items()}  # type: ignore[misc]
    return str(obj)


def convert_agui_tools_to_agent_framework(
    agui_tools: list[dict[str, Any]] | None,
) -> list[AIFunction[Any, Any]] | None:
    """Convert AG-UI tool definitions to Agent Framework AIFunction declarations.

    Creates declaration-only AIFunction instances (no executable implementation).
    These are used to tell the LLM about available tools. The actual execution
    happens on the client side via @use_function_invocation.

    CRITICAL: These tools MUST have func=None so that declaration_only returns True.
    This prevents the server from trying to execute client-side tools.

    Args:
        agui_tools: List of AG-UI tool definitions with name, description, parameters

    Returns:
        List of AIFunction declarations, or None if no tools provided
    """
    if not agui_tools:
        return None

    result: list[AIFunction[Any, Any]] = []
    for tool_def in agui_tools:
        # Create declaration-only AIFunction (func=None means no implementation)
        # When func=None, the declaration_only property returns True,
        # which tells @use_function_invocation to return the function call
        # without executing it (so it can be sent back to the client)
        func: AIFunction[Any, Any] = AIFunction(
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

    for tool in tool_list:
        if isinstance(tool, dict):
            # Already in dict format, pass through
            results.append(tool)  # type: ignore[arg-type]
        elif isinstance(tool, AIFunction):
            # Convert AIFunction to AG-UI tool format
            results.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters(),
                }
            )
        elif callable(tool):
            # Convert callable to AIFunction first, then to AG-UI format
            from agent_framework import ai_function

            ai_func = ai_function(tool)
            results.append(
                {
                    "name": ai_func.name,
                    "description": ai_func.description,
                    "parameters": ai_func.parameters(),
                }
            )
        elif isinstance(tool, ToolProtocol):
            # Handle other ToolProtocol implementations
            # For now, we'll skip non-AIFunction tools as they may not have
            # the parameters() method. This matches .NET behavior which only
            # converts AIFunctionDeclaration instances.
            continue

    return results if results else None
