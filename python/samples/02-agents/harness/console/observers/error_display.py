# Copyright (c) Microsoft. All rights reserved.

"""Error display observer for showing errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ConsoleObserver

if TYPE_CHECKING:
    from agent_framework import Agent, Content

    from ..state_driver import IUXStateDriver


class ErrorDisplayObserver(ConsoleObserver):
    """Displays error content from the agent response.

    Shows errors with an ❌ prefix in red to make them easily visible.
    """

    async def on_content(
        self,
        ux: IUXStateDriver,
        content: Content,
        agent: Agent,
        session: Any,
    ) -> None:
        """Display error content.

        Args:
            ux: The UX state driver for UI updates.
            content: The content item to check for errors.
            agent: The AI agent.
            session: The agent session.
        """
        # Check if this is an error content type
        # The exact content type check depends on the agent framework's Content class
        if hasattr(content, "type") and content.type == "error":
            error_text = self._format_error(content)
            ux.append_info_line(error_text, "red")
        elif getattr(content, "error", None):
            error_text = f"❌ Error: {content.error}"  # type: ignore[reportAttributeAccessIssue]
            ux.append_info_line(error_text, "red")

    def _format_error(self, content: Content) -> str:
        """Format error content for display.

        Args:
            content: The error content.

        Returns:
            Formatted error string.
        """
        error_text = "❌ Error"

        # Try to extract error message
        if hasattr(content, "message"):
            error_text += f": {content.message}"
        elif hasattr(content, "text"):
            error_text += f": {content.text}"

        # Try to add error code if available
        if hasattr(content, "error_code") and content.error_code:
            error_text += f" (code: {content.error_code})"

        # Try to add details if available
        if hasattr(content, "details") and getattr(content, "details", None):
            error_text += f" — {content.details}"  # type: ignore[reportAttributeAccessIssue]

        return error_text
