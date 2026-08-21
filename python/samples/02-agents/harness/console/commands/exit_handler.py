# Copyright (c) Microsoft. All rights reserved.

"""Exit command handler — /exit to quit the console."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import CommandHandler

if TYPE_CHECKING:
    from agent_framework import AgentSession

    from ..state_driver import IUXStateDriver


class ExitCommandHandler(CommandHandler):
    """Handle the /exit command to shut down the console application."""

    def get_help_text(self) -> str | None:
        """Return help text for the exit command."""
        return "/exit (quit)"

    async def try_handle(
        self,
        user_input: str,
        session: AgentSession,
        ux: IUXStateDriver,
    ) -> bool:
        """Handle /exit by requesting shutdown."""
        if user_input.strip().lower() != "/exit":
            return False

        ux.request_shutdown()
        return True
