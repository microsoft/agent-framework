# Copyright (c) Microsoft. All rights reserved.

"""Usage display observer for token usage statistics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ConsoleObserver

if TYPE_CHECKING:
    from agent_framework import Agent

    from ..state_driver import IUXStateDriver


class UsageDisplayObserver(ConsoleObserver):
    """Displays token usage as a proportion of the context window.

    Shows current token usage as reported by the API immediately when
    usage information becomes available (via Content items or the final response).
    The display shows input/output/total relative to configured budgets.
    """

    async def on_content(
        self,
        ux: IUXStateDriver,
        content: Any,
        agent: Agent,
        session: Any,
    ) -> None:
        """Update usage display immediately when usage content arrives.

        Args:
            ux: The UX state driver for UI updates.
            content: A content item from the response.
            agent: The AI agent.
            session: The agent session.
        """
        if getattr(content, "type", None) == "usage":
            usage_details = getattr(content, "usage_details", None)
            if isinstance(usage_details, dict):
                # Pass through to state driver — the runner handles formatting
                ux.set_usage_text(self._format_from_details(usage_details))

    @staticmethod
    def _format_from_details(usage: dict) -> str:
        """Format usage details dict into display text.

        This is a fallback formatter for when usage arrives as Content
        before the runner's final response processing.
        """
        input_tokens = usage.get("input_token_count", 0) or 0
        output_tokens = usage.get("output_token_count", 0) or 0
        total_tokens = usage.get("total_token_count", 0) or input_tokens + output_tokens
        return f"📊 Tokens — input: {input_tokens:,} | output: {output_tokens:,} | total: {total_tokens:,}"
