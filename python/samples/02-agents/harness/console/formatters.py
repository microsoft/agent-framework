# Copyright (c) Microsoft. All rights reserved.

"""Tool call formatters for displaying function calls in the harness console.

This module provides formatters that convert raw function call content into
human-readable display strings. Each formatter handles specific tool patterns
(e.g., web_search, todos_*, etc.) and the FallbackToolFormatter provides
generic formatting for any unmatched tools.

Usage:
    from harness.console.formatters import build_default_formatters, format_tool_call
    from agent_framework import Content

    call = Content.from_function_call(
        call_id="call_1",
        name="web_search",
        arguments={"query": "Python async"}
    )
    formatters = build_default_formatters()
    result = format_tool_call(formatters, call)  # "web_search (Python async)"
"""

from __future__ import annotations

import contextlib
import json
from abc import ABC, abstractmethod
from typing import Any

from agent_framework import Content

# region Helper Functions


def get_argument_value(call: Content, param_name: str) -> Any:
    """Extract an argument value from a function call.

    Handles both dict and JSON string arguments.

    Args:
        call: The function call content.
        param_name: The parameter name to extract.

    Returns:
        The argument value, or None if not found.
    """
    if call.arguments is None:
        return None

    if isinstance(call.arguments, str):
        # arguments is a JSON string, parse it
        try:
            args_dict = json.loads(call.arguments)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(args_dict, dict):
            return None
    elif isinstance(call.arguments, dict):
        args_dict = call.arguments
    else:
        return None

    return args_dict.get(param_name)


def as_int_list(value: Any) -> list[int] | None:
    """Convert a value to a list of integers, or None if not possible.

    Args:
        value: The value to convert (should be a list).

    Returns:
        A list of integers, or None if conversion fails.
    """
    if not isinstance(value, list):
        return None

    result: list[int] = []
    for item in value:
        if isinstance(item, int):
            result.append(item)
        else:
            with contextlib.suppress(ValueError, TypeError):
                result.append(int(item))

    return result if result else None


def as_dict_list(value: Any) -> list[dict[str, Any]] | None:
    """Convert a value to a list of dicts, or None if not possible.

    Args:
        value: The value to convert (should be a list).

    Returns:
        A list of dicts, or None if value is not a list of dicts.
    """
    if not isinstance(value, list):
        return None

    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            result.append(item)

    return result if result else None


def truncate(text: str, max_length: int) -> str:
    """Truncate a string to the specified maximum length, appending an ellipsis if truncated.

    Args:
        text: The text to truncate.
        max_length: The maximum length.

    Returns:
        The truncated string.
    """
    return text if len(text) <= max_length else text[:max_length] + "…"


# endregion

# region Base Class


class ToolCallFormatter(ABC):
    """Base class for tool call formatters that produce human-readable display strings
    for function call content items shown in the console.
    """

    @abstractmethod
    def can_format(self, call: Content) -> bool:
        """Return True if this formatter can handle the given function call.

        Args:
            call: The function call content to check.

        Returns:
            True if this formatter should be used; otherwise False.
        """
        ...

    @abstractmethod
    def format_detail(self, call: Content) -> str | None:
        """Return the detail portion of the formatted output for the given tool call,
        or None if only the tool name should be displayed.

        Args:
            call: The function call content to format.

        Returns:
            A detail string to append after the tool name, or None.
        """
        ...


# endregion

# region Concrete Formatters


class FallbackToolFormatter(ToolCallFormatter):
    """Catch-all formatter that handles any tool not matched by a more specific formatter.

    Displays a generic summary of the tool's arguments. This formatter should always be
    placed last in the formatter list.
    """

    def can_format(self, call: Content) -> bool:
        """Always returns True - this formatter matches everything."""
        return True

    def format_detail(self, call: Content) -> str | None:
        """Format arguments as generic (key: value, ...) pairs."""
        if call.arguments is None:
            return None

        # Parse arguments
        if isinstance(call.arguments, str):
            try:
                args_dict = json.loads(call.arguments)
            except (json.JSONDecodeError, TypeError):
                return None
        elif isinstance(call.arguments, dict):
            args_dict = call.arguments
        else:
            return None

        if not args_dict:
            return None

        # Build argument list
        parts: list[str] = []
        for key, value in args_dict.items():
            if value is None:
                continue

            # Convert value to string
            if isinstance(value, bool):
                str_value = "true" if value else "false"
            elif isinstance(value, (int, float)):
                str_value = str(value)
            elif isinstance(value, str):
                str_value = value
            else:
                # Complex types - skip for now
                continue

            parts.append(f"{key}: {truncate(str_value, 40)}")

        return f"({', '.join(parts)})" if parts else None


class WebSearchToolFormatter(ToolCallFormatter):
    """Formats web_search tool calls, showing the search query."""

    def can_format(self, call: Content) -> bool:
        """Match web_search tool calls."""
        return call.name == "web_search"

    def format_detail(self, call: Content) -> str | None:
        """Extract and format the query parameter."""
        value = get_argument_value(call, "query")
        return f"({value})" if value else None


class TodoToolFormatter(ToolCallFormatter):
    """Formats todos_* tool calls with tree-view output for added items
    and structured output for complete/remove operations.
    """

    def can_format(self, call: Content) -> bool:
        """Match todos_* tool calls."""
        return call.name is not None and call.name.startswith("todos_")

    def format_detail(self, call: Content) -> str | None:
        """Format based on the specific todos operation."""
        if call.name == "todos_add":
            return self._format_add_todos(call)
        if call.name == "todos_complete":
            return self._format_complete_todos(call)
        if call.name == "todos_remove":
            return self._format_id_list(call, "ids", "Remove")
        return None

    def _format_add_todos(self, call: Content) -> str | None:
        """Format todos_add with tree view of titles."""
        todos = as_dict_list(get_argument_value(call, "todos"))
        if not todos:
            return None

        titles: list[str] = []
        for todo in todos:
            title = todo.get("title")
            if title and isinstance(title, str):
                titles.append(title)

        if not titles:
            return None

        # Build tree view
        count = len(titles)
        plural = "s" if count != 1 else ""
        lines = [f"({count} item{plural})"]
        for i, title in enumerate(titles):
            connector = "├─" if i < count - 1 else "└─"
            lines.append(f"\n   {connector} {title}")

        return "".join(lines)

    def _format_complete_todos(self, call: Content) -> str | None:
        """Format todos_complete with tree view of IDs and reasons."""
        items = as_dict_list(get_argument_value(call, "items"))
        if not items:
            return None

        entries: list[tuple[int, str | None]] = []
        for item in items:
            todo_id = item.get("id")
            if not isinstance(todo_id, int):
                continue

            reason = item.get("reason")
            reason_str = str(reason) if reason is not None and not isinstance(reason, str) else reason
            entries.append((todo_id, reason_str))

        if not entries:
            return None

        # Build tree view
        lines: list[str] = []
        for i, (todo_id, reason) in enumerate(entries):
            connector = "├─" if i < len(entries) - 1 else "└─"
            line = f"\n   {connector} Complete #{todo_id}"
            if reason:
                line += f" — {truncate(reason, 80)}"
            lines.append(line)

        return "".join(lines)

    def _format_id_list(self, call: Content, param_name: str, verb: str) -> str | None:
        """Format a list of IDs with a verb (e.g., Remove #1, Remove #2)."""
        ids = as_int_list(get_argument_value(call, param_name))
        if not ids:
            return None

        lines: list[str] = []
        for i, todo_id in enumerate(ids):
            connector = "├─" if i < len(ids) - 1 else "└─"
            lines.append(f"\n   {connector} {verb} #{todo_id}")

        return "".join(lines)


class ModeToolFormatter(ToolCallFormatter):
    """Formats AgentMode_* tool calls, showing the target mode for Set operations."""

    def can_format(self, call: Content) -> bool:
        """Match AgentMode_* tool calls."""
        return call.name is not None and call.name.startswith("AgentMode_")

    def format_detail(self, call: Content) -> str | None:
        """Format based on the specific AgentMode operation."""
        if call.name == "AgentMode_Set":
            value = get_argument_value(call, "mode")
            return f"({value})" if value else None
        return None


class BackgroundAgentToolFormatter(ToolCallFormatter):
    """Formats BackgroundAgents_* tool calls with human-readable details
    for task start, continue, wait, and result retrieval operations.
    """

    def can_format(self, call: Content) -> bool:
        """Match BackgroundAgents_* tool calls."""
        return call.name is not None and call.name.startswith("BackgroundAgents_")

    def format_detail(self, call: Content) -> str | None:
        """Format based on the specific BackgroundAgents operation."""
        if call.name == "BackgroundAgents_StartTask":
            return self._format_start_background_task(call)
        if call.name == "BackgroundAgents_WaitForFirstCompletion":
            return self._format_id_list(call, "taskIds", "Wait for")
        if call.name == "BackgroundAgents_GetTaskResults":
            return self._format_single_id(call, "taskId")
        if call.name == "BackgroundAgents_ContinueTask":
            return self._format_continue_task(call)
        if call.name == "BackgroundAgents_ClearCompletedTask":
            return self._format_single_id(call, "taskId")
        return None

    def _format_start_background_task(self, call: Content) -> str | None:
        """Format StartTask with agent name and description."""
        agent_name = get_argument_value(call, "agentName")
        description = get_argument_value(call, "description")

        if agent_name is None and description is None:
            return None

        lines: list[str] = []

        if agent_name is not None and description is not None:
            lines.append(f"\n   ├─ Agent: {agent_name}")
            lines.append(f'\n   └─ "{truncate(description, 80)}"')
        elif agent_name is not None:
            lines.append(f"\n   └─ Agent: {agent_name}")
        else:
            lines.append(f'\n   └─ "{truncate(description, 80)}"')  # type: ignore[arg-type]

        return "".join(lines)

    def _format_id_list(self, call: Content, param_name: str, verb: str) -> str | None:
        """Format a list of task IDs with a verb."""
        ids = as_int_list(get_argument_value(call, param_name))
        if not ids:
            return None

        lines: list[str] = []
        for i, task_id in enumerate(ids):
            connector = "├─" if i < len(ids) - 1 else "└─"
            lines.append(f"\n   {connector} {verb} #{task_id}")

        return "".join(lines)

    def _format_single_id(self, call: Content, param_name: str) -> str | None:
        """Format a single task ID in parentheses."""
        task_id = get_argument_value(call, param_name)
        if isinstance(task_id, int):
            return f"(task #{task_id})"
        return None

    def _format_continue_task(self, call: Content) -> str | None:
        """Format ContinueTask with task ID and optional text."""
        task_id = get_argument_value(call, "taskId")
        text = get_argument_value(call, "text")

        if not isinstance(task_id, int):
            return None

        if text:
            lines = [
                f"\n   ├─ Task #{task_id}",
                f'\n   └─ "{truncate(text, 80)}"',
            ]
            return "".join(lines)

        return f"\n   └─ Task #{task_id}"


class FileMemoryToolFormatter(ToolCallFormatter):
    """Formats FileMemory_* tool calls, showing file names and search patterns
    with tree-view corners for save operations.
    """

    def can_format(self, call: Content) -> bool:
        """Match FileMemory_* tool calls."""
        return call.name is not None and call.name.startswith("FileMemory_")

    def format_detail(self, call: Content) -> str | None:
        """Format based on the specific FileMemory operation."""
        if call.name == "FileMemory_SaveFile":
            return self._format_save_file(call)
        if call.name in ("FileMemory_ReadFile", "FileMemory_DeleteFile"):
            value = get_argument_value(call, "fileName")
            return f"({value})" if value else None
        if call.name == "FileMemory_SearchFiles":
            return self._format_search_files(call)
        return None

    def _format_save_file(self, call: Content) -> str | None:
        """Format SaveFile with file name and description indicator."""
        file_name = get_argument_value(call, "fileName")
        description = get_argument_value(call, "description")

        if not file_name:
            return None

        if description:
            return f"\n   └─ {file_name} (with description)"
        return f"\n   └─ {file_name}"

    def _format_search_files(self, call: Content) -> str | None:
        """Format SearchFiles with regex pattern and optional file pattern."""
        pattern = get_argument_value(call, "regexPattern")
        file_pattern = get_argument_value(call, "filePattern")

        if not pattern:
            return None

        if file_pattern:
            return f"(/{pattern}/ in {file_pattern})"
        return f"(/{pattern}/)"


# endregion

# region Public API Functions


def format_tool_call(formatters: list[ToolCallFormatter], call: Content) -> str:
    """Format a tool call using the first matching formatter from the provided list.

    Returns "{toolName} {detail}" when a formatter produces detail,
    or just "{toolName}" otherwise.

    Args:
        formatters: List of formatters to try in order.
        call: The function call content to format.

    Returns:
        Formatted string representation of the tool call.
    """
    for formatter in formatters:
        if formatter.can_format(call):
            detail = formatter.format_detail(call)
            tool_name = call.name or "Unknown"
            return f"{tool_name} {detail}" if detail is not None else tool_name

    return call.name or "Unknown"


def build_default_formatters() -> list[ToolCallFormatter]:
    """Create the default list of tool call formatters.

    The FallbackToolFormatter is always last. Users can call this function
    and combine the result with their own formatters.

    Returns:
        A list of all built-in tool call formatters.
    """
    return [
        TodoToolFormatter(),
        ModeToolFormatter(),
        BackgroundAgentToolFormatter(),
        FileMemoryToolFormatter(),
        WebSearchToolFormatter(),
        FallbackToolFormatter(),
    ]


# endregion
