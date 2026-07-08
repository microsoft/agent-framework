# Copyright (c) Microsoft. All rights reserved.

"""Base class for console observers.

Observers participate in the agent streaming lifecycle, displaying events
and optionally returning follow-up actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_framework import Agent, Content, Message

    from ..app_state import FollowUpAction
    from ..state_driver import IUXStateDriver


class ConsoleObserver:
    """Base class for console observers.

    Observers participate in the agent streaming lifecycle, displaying
    events (tool calls, errors, reasoning, etc.) and optionally returning
    follow-up actions (questions, approval requests).

    All methods have default no-op implementations, so subclasses only
    override the methods they need.
    """

    def configure_run_options(
        self,
        options: dict[str, Any],
        agent: Agent,
        session: Any,
    ) -> None:
        """Configure run options before agent invocation.

        Override to set options such as response_format, max_tokens, etc.

        Args:
            options: Dictionary of chat options to modify.
            agent: The AI agent.
            session: The agent session.
        """
        pass

    async def on_response_update(
        self,
        ux: IUXStateDriver,
        update: Message,
        agent: Agent,
        session: Any,
    ) -> None:
        """Called for each response update chunk.

        Override to inspect update-level metadata or handle provider-specific
        events in the raw representation.

        Args:
            ux: The UX state driver for UI updates.
            update: The message update chunk.
            agent: The AI agent.
            session: The agent session.
        """
        pass

    async def on_content(
        self,
        ux: IUXStateDriver,
        content: Content,
        agent: Agent,
        session: Any,
    ) -> None:
        """Called for each content item in the response.

        Override to handle specific content types (function calls, errors, etc.).

        Args:
            ux: The UX state driver for UI updates.
            content: The content item from the response.
            agent: The AI agent.
            session: The agent session.
        """
        pass

    async def on_text(
        self,
        ux: IUXStateDriver,
        text: str,
        agent: Agent,
        session: Any,
    ) -> None:
        """Called for each text chunk in the response.

        Override to accumulate and display streaming text.

        Args:
            ux: The UX state driver for UI updates.
            text: The text chunk.
            agent: The AI agent.
            session: The agent session.
        """
        pass

    async def on_stream_complete(
        self,
        ux: IUXStateDriver,
        agent: Agent,
        session: Any,
    ) -> list[FollowUpAction] | None:
        """Called when streaming completes.

        Override to return follow-up actions (questions to ask the user,
        messages to inject into the next turn, etc.).

        Args:
            ux: The UX state driver for UI updates.
            agent: The AI agent.
            session: The agent session.

        Returns:
            Optional list of follow-up actions to queue, or None.
        """
        return None
