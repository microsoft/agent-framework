# Copyright (c) Microsoft. All rights reserved.

"""Session command handler — /session-export and /session-import."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .base import CommandHandler

if TYPE_CHECKING:
    from agent_framework import AgentSession

    from ..state_driver import IUXStateDriver


class SessionCommandHandler(CommandHandler):
    """Handle /session-export and /session-import commands."""

    def get_help_text(self) -> str | None:
        """Return help text for session commands."""
        return "/session-export <file> | /session-import <file>"

    async def try_handle(
        self,
        user_input: str,
        session: AgentSession,
        ux: IUXStateDriver,
    ) -> bool:
        """Handle session export/import commands."""
        stripped = user_input.strip()
        command = stripped.split(None, 1)[0].lower() if stripped else ""

        if command == "/session-export":
            await self._handle_export(stripped, session, ux)
            return True

        if command == "/session-import":
            await self._handle_import(stripped, ux)
            return True

        return False

    async def _handle_export(
        self,
        user_input: str,
        session: AgentSession,
        ux: IUXStateDriver,
    ) -> None:
        """Export the current session to a JSON file."""
        parts = user_input.split(None, 1)
        if len(parts) < 2:
            ux.append_info_line("Usage: /session-export <filename>")
            return

        filename = parts[1].strip()
        try:
            serialized = session.to_dict()
            json_str = json.dumps(serialized, indent=2)
            self._write_file(filename, json_str)
            ux.append_info_line(f"Session exported to {filename}")
        except Exception as ex:
            ux.append_info_line(
                f"Failed to export session to {filename}: {ex}",
                color="red",
            )

    async def _handle_import(
        self,
        user_input: str,
        ux: IUXStateDriver,
    ) -> None:
        """Import a session from a JSON file."""
        parts = user_input.split(None, 1)
        if len(parts) < 2:
            ux.append_info_line("Usage: /session-import <filename>")
            return

        filename = parts[1].strip()
        try:
            from agent_framework import AgentSession

            json_str = self._read_file(filename)
            data = json.loads(json_str)
            new_session = AgentSession.from_dict(data)
            ux.replace_session(new_session)
            ux.append_info_line(f"Session imported from {filename}")
        except FileNotFoundError:
            ux.append_info_line(f"File not found: {filename}", color="red")
        except Exception as ex:
            ux.append_info_line(
                f"Failed to import session from {filename}: {ex}",
                color="red",
            )

    @staticmethod
    def _write_file(filename: str, content: str) -> None:
        """Write content to a file (sync helper to satisfy ASYNC230)."""
        with open(filename, "w", encoding="utf-8") as f:  # noqa: ASYNC230
            f.write(content)

    @staticmethod
    def _read_file(filename: str) -> str:
        """Read content from a file (sync helper to satisfy ASYNC230)."""
        with open(filename, encoding="utf-8") as f:  # noqa: ASYNC230
            return f.read()
