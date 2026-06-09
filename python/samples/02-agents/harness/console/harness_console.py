# Copyright (c) Microsoft. All rights reserved.

"""Main entry point for the harness console.

Provides the top-level run_agent_async() function that creates and runs
the Textual-based harness console application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .app import HarnessApp
from .observers import build_default_observers

if TYPE_CHECKING:
    from agent_framework import Agent, AgentSession

    from .commands import CommandHandler
    from .observers.base import ConsoleObserver


async def run_agent_async(
    agent: Agent,
    *,
    session: AgentSession | None = None,
    observers: list[ConsoleObserver] | None = None,
    command_handlers: list[CommandHandler] | None = None,
    mode_colors: dict[str, str] | None = None,
    initial_mode: str | None = None,
    placeholder: str = "Type a message and press Enter...",
    title: str = "Harness Console",
    max_context_window_tokens: int | None = None,
    max_output_tokens: int | None = None,
) -> None:
    """Run the harness console with the given agent.

    This is the main entry point for the harness console. Creates a Textual
    application with the configured observers and runs it until the user exits.

    Args:
        agent: The agent to run conversations with.
        session: Optional agent session for conversation history.
        observers: List of console observers. If None, uses defaults.
        command_handlers: List of command handlers. If None, auto-detected from agent.
        mode_colors: Mapping of mode names to Rich color strings.
        initial_mode: Initial agent mode text.
        placeholder: Input placeholder text.
        title: Application title.
        max_context_window_tokens: Optional max context window size for usage display.
        max_output_tokens: Optional max output tokens for usage display.

    Example:
        .. code-block:: python

            from agent_framework import Agent
            from agent_framework.openai import OpenAIChatClient
            from console import run_agent_async

            agent = Agent(
                client=OpenAIChatClient(),
                instructions="You are helpful.",
            )

            await run_agent_async(agent)
    """
    resolved_observers = observers or build_default_observers()
    resolved_mode_colors = mode_colors or {
        "plan": "cyan",
        "execute": "green",
    }
    resolved_session = session or agent.create_session()

    app = HarnessApp(
        agent=agent,
        observers=resolved_observers,
        session=resolved_session,
        mode_colors=resolved_mode_colors,
        initial_mode=initial_mode,
        placeholder=placeholder,
        title=title,
        max_context_window_tokens=max_context_window_tokens,
        max_output_tokens=max_output_tokens,
        command_handlers=command_handlers,
    )

    await app.run_async()
