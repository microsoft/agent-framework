# Copyright (c) Microsoft. All rights reserved.

"""Tool call display observer using formatters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..formatters import build_default_formatters, format_tool_call
from .base import ConsoleObserver

if TYPE_CHECKING:
    from agent_framework import Agent, Content

    from ..formatters import ToolCallFormatter
    from ..state_driver import IUXStateDriver


class ToolCallDisplayObserver(ConsoleObserver):
    """Displays tool call notifications using formatters.

    Shows tool calls with a 🔧 prefix and uses the formatter system to
    display them in a user-friendly format.
    """

    def __init__(self, formatters: list[ToolCallFormatter] | None = None) -> None:
        """Initialize the tool call display observer.

        Args:
            formatters: Optional list of tool formatters. If None, uses
                default formatters from build_default_formatters().
        """
        self._formatters = formatters or build_default_formatters()

    async def on_content(
        self,
        ux: IUXStateDriver,
        content: Content,
        agent: Agent,
        session: Any,
    ) -> None:
        """Display function call content.

        Args:
            ux: The UX state driver for UI updates.
            content: The content item to check for function calls.
            agent: The AI agent.
            session: The agent session.
        """
        # Check if this is a function call content type
        if content.type == "function_call":
            formatted = format_tool_call(self._formatters, content)
            ux.append_info_line(f"🔧 {formatted}", "yellow")
