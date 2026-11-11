# Copyright (c) Microsoft. All rights reserved.

"""Durable session-store boundaries for hosted approval regression tests."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from agent_framework import AgentSession, Content, SessionStore

from agent_framework_foundry_hosting._approvals import SessionApprovalState


class SqliteSessionStore(SessionStore):
    """Persist sessions in a real database shared by independent processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.write_count = 0
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS sessions (key TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def _read(self, session_id: str) -> AgentSession | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT payload FROM sessions WHERE key = ?", (session_id,)).fetchone()
        return AgentSession.from_dict(json.loads(row[0])) if row else None

    async def get(self, session_id: str) -> AgentSession | None:
        return await asyncio.to_thread(self._read, session_id)

    def _write(self, session_id: str, payload: str) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET payload = excluded.payload",
                (session_id, payload),
            )

    async def set(self, session_id: str, session: AgentSession) -> None:
        await asyncio.to_thread(self._write, session_id, json.dumps(session.to_dict()))
        self.write_count += 1

    async def delete(self, session_id: str) -> None:
        await asyncio.to_thread(self._delete, session_id)

    def _delete(self, session_id: str) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DELETE FROM sessions WHERE key = ?", (session_id,))


def approval_request(index: int = 0) -> Content:
    call = Content.from_function_call(
        call_id=f"call-{index}",
        name="protected",
        arguments={"index": index},
        hosted=True,
        additional_properties={"provider": {"type": "message", "opaque_id": "original"}},
    )
    return Content.from_function_approval_request(f"approval-{index}", call)


async def pending_session(store: SqliteSessionStore, count: int = 2) -> AgentSession:
    session = AgentSession(session_id="original-session")
    state = SessionApprovalState(session)
    for index in range(count):
        await state.save_approval_request(f"wire-{index}", approval_request(index))
    await store.set("response-alias", session)
    await store.set("conversation-alias", session)
    return session
