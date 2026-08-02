# Copyright (c) Microsoft. All rights reserved.

"""Command handler package for the harness console.

Provides slash-command handling (e.g., /exit, /mode, /todos, /session-export)
that intercepts user input before it reaches the agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import CommandHandler
from .exit_handler import ExitCommandHandler
from .mode_handler import ModeCommandHandler
from .session_handler import SessionCommandHandler
from .todo_handler import TodoCommandHandler

if TYPE_CHECKING:
    from agent_framework import Agent

__all__ = [
    "CommandHandler",
    "ExitCommandHandler",
    "ModeCommandHandler",
    "SessionCommandHandler",
    "TodoCommandHandler",
    "build_default_command_handlers",
]


def build_default_command_handlers(
    agent: Agent,
    *,
    mode_colors: dict[str, str] | None = None,
) -> list[CommandHandler]:
    """Build the default set of command handlers by inspecting the agent.

    Auto-detects TodoProvider and AgentModeProvider from the agent's
    context_providers list.

    Args:
        agent: The agent to inspect for providers.
        mode_colors: Optional mapping of mode names to Rich color strings.

    Returns:
        List of command handlers in evaluation order.
    """
    from agent_framework import AgentModeProvider, TodoProvider

    todo_provider: TodoProvider | None = None
    mode_provider: AgentModeProvider | None = None

    for provider in getattr(agent, "context_providers", []):
        if isinstance(provider, TodoProvider) and todo_provider is None:
            todo_provider = provider
        elif isinstance(provider, AgentModeProvider) and mode_provider is None:
            mode_provider = provider

    return [
        ExitCommandHandler(),
        TodoCommandHandler(todo_provider),
        ModeCommandHandler(mode_provider, mode_colors),
        SessionCommandHandler(),
    ]
