# Copyright (c) Microsoft. All rights reserved.

"""Shared helpers for the BackgroundAgentsProvider tests."""

from __future__ import annotations

import asyncio
from typing import Any

from agent_framework import AgentResponse, AgentSession, Message, ServiceSessionId


class ScriptedAgent:
    """Agent stub whose N-th run returns ``responses[N]`` and can optionally wait on a gate or fail.

    Set ``gates[N]`` to an :class:`asyncio.Event` to hold the N-th run until the event is set, and list
    N in ``fail_runs`` to make the N-th run raise ``RuntimeError``.
    """

    def __init__(self, name: str, responses: list[str], *, fail_runs: set[int] | None = None) -> None:
        self.id = f"agent-{name}"
        self.name = name
        self.description: str | None = None
        self.responses = responses
        self.fail_runs = fail_runs or set()
        self.gates: dict[int, asyncio.Event] = {}
        self.runs = 0

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(
        self,
        service_session_id: str | ServiceSessionId,
        *,
        session_id: str | None = None,
    ) -> AgentSession:
        return AgentSession(service_session_id=service_session_id, session_id=session_id)

    async def run(
        self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any
    ) -> AgentResponse[Any]:
        index = self.runs
        self.runs += 1
        gate = self.gates.get(index)
        if gate is not None:
            await gate.wait()
        if index in self.fail_runs:
            raise RuntimeError(f"run {index} failed")
        return AgentResponse(messages=[Message(role="assistant", contents=[self.responses[index]])])


def task_record(session: AgentSession, task_id: int, *, source_id: str = "background_agents") -> dict[str, Any]:
    """Return the persisted task record for ``task_id`` from the provider's session state."""
    return next(t for t in session.state[source_id]["tasks"] if t["id"] == task_id)
