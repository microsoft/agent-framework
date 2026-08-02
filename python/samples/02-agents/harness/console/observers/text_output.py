# Copyright (c) Microsoft. All rights reserved.

"""Text output observer for streaming agent text."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape

from .base import ConsoleObserver

if TYPE_CHECKING:
    from agent_framework import Agent

    from ..state_driver import IUXStateDriver


class TextOutputObserver(ConsoleObserver):
    """Displays streaming text output from the agent.

    Writes text chunks incrementally to the UX state driver as they arrive,
    allowing real-time display during streaming.
    """

    async def on_text(
        self,
        ux: IUXStateDriver,
        text: str,
        agent: Agent,
        session: Any,
    ) -> None:
        """Write each text chunk directly to the UX driver.

        Args:
            ux: The UX state driver for UI updates.
            text: The text chunk to display.
            agent: The AI agent.
            session: The agent session.
        """
        ux.write_text(escape(text))

    async def on_stream_complete(
        self,
        ux: IUXStateDriver,
        agent: Agent,
        session: Any,
    ) -> list | None:
        """No-op on stream complete (state managed by UX driver).

        Args:
            ux: The UX state driver for UI updates.
            agent: The AI agent.
            session: The agent session.

        Returns:
            None (no follow-up actions).
        """
        return None
