# Copyright (c) Microsoft. All rights reserved.

"""Reasoning display observer for showing thinking content."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape

from .base import ConsoleObserver

if TYPE_CHECKING:
    from agent_framework import Agent, Content

    from ..state_driver import IUXStateDriver


class ReasoningDisplayObserver(ConsoleObserver):
    """Displays reasoning/thinking content from the agent.

    Some models (like o1) provide reasoning steps that show their
    internal thought process. This observer displays them with a 💭 prefix
    in a dimmed style.
    """

    async def on_content(
        self,
        ux: IUXStateDriver,
        content: Content,
        agent: Agent,
        session: Any,
    ) -> None:
        """Display reasoning content.

        Args:
            ux: The UX state driver for UI updates.
            content: The content item to check for reasoning.
            agent: The AI agent.
            session: The agent session.
        """
        reasoning_text = self._extract_reasoning(content)
        if reasoning_text:
            # Display reasoning in dim style to differentiate from main output
            ux.append_info_line(f"💭 {escape(reasoning_text)}", "dim")

    def _extract_reasoning(self, content: Content) -> str | None:
        """Extract reasoning text from content.

        Args:
            content: The content item to extract reasoning from.

        Returns:
            The reasoning text, or None if no reasoning is present.
        """
        # Check for reasoning content type
        if hasattr(content, "type") and content.type in {"text_reasoning", "reasoning"}:
            if hasattr(content, "text"):
                return content.text
            content_attr = getattr(content, "content", None)
            if content_attr:
                return str(content_attr)

        # Check for reasoning attribute
        reasoning = getattr(content, "reasoning", None)
        if reasoning is not None:
            if isinstance(reasoning, str):
                return reasoning
            if hasattr(reasoning, "text"):
                return reasoning.text

        # Check for thinking attribute (alternative name)
        thinking = getattr(content, "thinking", None)
        if thinking is not None:
            if isinstance(thinking, str):
                return thinking
            if hasattr(thinking, "text"):
                return thinking.text

        return None
