# Copyright (c) Microsoft. All rights reserved.

"""Mode command handler — /mode to show or switch agent mode."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import CommandHandler

if TYPE_CHECKING:
    from agent_framework import AgentModeProvider, AgentSession

    from ..state_driver import IUXStateDriver


class ModeCommandHandler(CommandHandler):
    """Handle the /mode command to display or switch the current agent mode."""

    def __init__(
        self,
        mode_provider: AgentModeProvider | None,
        mode_colors: dict[str, str] | None = None,
    ) -> None:
        """Initialize with mode provider and color mapping.

        Args:
            mode_provider: The mode provider, or None if not available.
            mode_colors: Optional mapping of mode names to Rich color strings.
        """
        self._mode_provider = mode_provider
        self._mode_colors = mode_colors or {}

    def get_help_text(self) -> str | None:
        """Return help text, or None if mode provider is unavailable."""
        if self._mode_provider is None:
            return None
        return "/mode [plan|execute] (show or switch mode)"

    async def try_handle(
        self,
        user_input: str,
        session: AgentSession,
        ux: IUXStateDriver,
    ) -> bool:
        """Handle /mode [name] command."""
        stripped = user_input.strip()
        lower = stripped.lower()

        if not (lower == "/mode" or lower.startswith("/mode ")):
            return False

        if self._mode_provider is None:
            ux.append_info_line("AgentModeProvider is not available.")
            return True

        parts = stripped.split(None, 1)
        if len(parts) < 2:
            # Show current mode
            from agent_framework import get_agent_mode

            current = get_agent_mode(
                session,
                source_id=self._mode_provider.source_id,
                default_mode=self._mode_provider.default_mode,
                available_modes=self._mode_provider.available_modes,
            )
            ux.append_info_line(f"Current mode: {current}")
            return True

        # Switch mode
        new_mode = parts[1].strip()
        try:
            from agent_framework import set_agent_mode

            normalized = set_agent_mode(
                session,
                new_mode,
                source_id=self._mode_provider.source_id,
                available_modes=self._mode_provider.available_modes,
            )
            color = self._mode_colors.get(normalized)
            ux.set_mode(normalized, color)
            ux.append_info_line(
                f"Switched to {normalized} mode.",
                color=color,
            )
        except ValueError as ex:
            ux.append_info_line(str(ex), color="red")

        return True
