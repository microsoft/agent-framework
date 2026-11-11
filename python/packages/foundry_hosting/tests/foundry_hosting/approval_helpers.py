# Copyright (c) Microsoft. All rights reserved.

"""Durable conditional-store boundaries for hosted approval regression tests."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from agent_framework import AgentSession, Content, SessionStore

from agent_framework_foundry_hosting._approvals import SessionApprovalState


class SqliteSessionStore(SessionStore):
    """Use actual database conditional writes shared by independent processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.write_count = 0
        self.error_after_commit: BaseException | None = None
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sessions "
                "(key TEXT PRIMARY KEY, payload TEXT NOT NULL, revision TEXT NOT NULL)"
            )

    def _read(self, session_id: str) -> tuple[AgentSession | None, str | None]:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT payload, revision FROM sessions WHERE key = ?", (session_id,)).fetchone()
        return (AgentSession.from_dict(json.loads(row[0])), row[1]) if row else (None, None)

    async def get_with_revision(self, session_id: str) -> tuple[AgentSession | None, str | None]:
        return await asyncio.to_thread(self._read, session_id)

    async def get(self, session_id: str) -> AgentSession | None:
        session, _ = await self.get_with_revision(session_id)
        return session

    def _write(self, session_id: str, payload: str, expected_revision: str | None) -> str:
        revision = str(uuid4())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            if expected_revision is None:
                try:
                    connection.execute("INSERT INTO sessions VALUES (?, ?, ?)", (session_id, payload, revision))
                except sqlite3.IntegrityError as exc:
                    raise RuntimeError("Session revision conflict.") from exc
            else:
                result = connection.execute(
                    "UPDATE sessions SET payload = ?, revision = ? WHERE key = ? AND revision = ?",
                    (payload, revision, session_id, expected_revision),
                )
                if result.rowcount != 1:
                    raise RuntimeError("Session revision conflict.")
        return revision

    async def compare_and_set(self, session_id: str, session: AgentSession, *, expected_revision: str | None) -> str:
        revision = await asyncio.to_thread(self._write, session_id, json.dumps(session.to_dict()), expected_revision)
        self.write_count += 1
        if self.error_after_commit is not None:
            raise self.error_after_commit
        return revision

    async def set(self, session_id: str, session: AgentSession) -> None:
        _, revision = await self.get_with_revision(session_id)
        await self.compare_and_set(session_id, session, expected_revision=revision)

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
    state = SessionApprovalState(session, store, response_id="owner-response")
    for index in range(count):
        await state.save_approval_request(f"wire-{index}", approval_request(index))
    await state.seal()
    await store.set("response-alias", session)
    await store.set("conversation-alias", session)
    return session


async def claim_stored_batch(path: str) -> None:
    store = SqliteSessionStore(Path(path))
    session = await store.get("response-alias")
    assert session is not None
    state = SessionApprovalState(session, store)
    token = await state.preflight(["wire-0", "wire-1"])
    assert token is not None
    print("ready", flush=True)  # noqa: T201 - subprocess barrier protocol
    await asyncio.to_thread(sys.stdin.readline)
    try:
        await state.claim(token, response_id=str(uuid4()))
    except RuntimeError:
        print("conflict", flush=True)  # noqa: T201 - subprocess result protocol
    else:
        print("claimed", flush=True)  # noqa: T201 - subprocess result protocol


async def race_claims_in_processes(path: Path) -> list[str]:
    script = (
        "import asyncio,sys; "
        "sys.path.insert(0,sys.argv[1]); "
        "from approval_helpers import claim_stored_batch; "
        "asyncio.run(claim_stored_batch(sys.argv[2]))"
    )
    processes = [
        await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            str(Path(__file__).parent),
            str(path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        for _ in range(2)
    ]
    try:
        for process in processes:
            assert process.stdout is not None
            assert await asyncio.wait_for(process.stdout.readline(), 30) == b"ready\n"
        results = await asyncio.gather(*(process.communicate(b"go\n") for process in processes))
        for process, (_, error) in zip(processes, results, strict=True):
            assert process.returncode == 0, error.decode()
        return sorted(output.decode().strip() for output, _ in results)
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
                await process.wait()
