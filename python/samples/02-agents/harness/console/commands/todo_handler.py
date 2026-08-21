# Copyright (c) Microsoft. All rights reserved.

"""Todo command handler — /todos to display the todo list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import CommandHandler

if TYPE_CHECKING:
    from agent_framework import AgentSession, TodoProvider

    from ..state_driver import IUXStateDriver


class TodoCommandHandler(CommandHandler):
    """Handle the /todos command to display the current todo list."""

    def __init__(self, todo_provider: TodoProvider | None) -> None:
        """Initialize with the todo provider.

        Args:
            todo_provider: The todo provider, or None if not available.
        """
        self._todo_provider = todo_provider

    def get_help_text(self) -> str | None:
        """Return help text, or None if todo provider is unavailable."""
        if self._todo_provider is None:
            return None
        return "/todos (show todo list)"

    async def try_handle(
        self,
        user_input: str,
        session: AgentSession,
        ux: IUXStateDriver,
    ) -> bool:
        """Handle /todos by displaying the todo list."""
        if user_input.strip().lower() != "/todos":
            return False

        if self._todo_provider is None:
            ux.append_info_line("TodoProvider is not available.")
            return True

        todos = await self._todo_provider.store.load_items(session, source_id=self._todo_provider.source_id)

        if not todos:
            ux.append_info_line("No todos yet.")
            return True

        ux.append_info_line("── Todo List ──")
        for item in todos:
            status = "✓" if item.is_complete else "○"
            color = "dim" if item.is_complete else None
            description = f" — {item.description}" if item.description else ""
            ux.append_info_line(
                f"[{status}] #{item.id} {item.title}{description}",
                color=color,
            )

        return True
