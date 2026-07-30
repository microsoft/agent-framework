# Copyright (c) Microsoft. All rights reserved.

"""Abstract base class for console command handlers.

Command handlers intercept user input starting with '/' and execute
local commands before input reaches the agent. They are checked in order;
the first handler that accepts the input prevents further handlers from
being checked.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_framework import AgentSession

    from ..state_driver import IUXStateDriver


class CommandHandler(ABC):
    """Base class for console command handlers.

    Subclasses implement get_help_text() for the mode bar and
    try_handle() to intercept matching commands.
    """

    @abstractmethod
    def get_help_text(self) -> str | None:
        """Get the help text for this command.

        Displayed in the mode-and-help bar. Return None if the
        command is not currently available.

        Returns:
            Help text like '/todos (show todo list)', or None.
        """
        ...

    @abstractmethod
    async def try_handle(
        self,
        user_input: str,
        session: AgentSession,
        ux: IUXStateDriver,
    ) -> bool:
        """Attempt to handle the given user input.

        Args:
            user_input: The raw user input string.
            session: The current agent session.
            ux: The UX state driver for rendering output.

        Returns:
            True if this handler handled the input; False otherwise.
        """
        ...
