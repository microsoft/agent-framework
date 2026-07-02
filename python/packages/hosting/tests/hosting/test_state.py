# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any

import pytest
from agent_framework import AgentResponse, AgentSession, Message

from agent_framework_hosting import AgentFrameworkState, SessionStore


class _FakeAgent:
    """Minimal agent target for state tests."""

    id = "fake-agent"
    name = "Fake Agent"
    description = "Fake agent for tests"

    def __init__(self) -> None:
        self.created_sessions: list[AgentSession] = []

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        session = AgentSession(session_id=session_id)
        self.created_sessions.append(session)
        return session

    def get_session(self, service_session_id: str, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id, service_session_id=service_session_id)

    async def run(self, messages: Any = None, **_: Any) -> AgentResponse:
        return AgentResponse(messages=Message(role="assistant", contents=["ok"]))


class TestSessionStore:
    async def test_get_reuses_session_for_same_id(self) -> None:
        agent = _FakeAgent()
        store = SessionStore(agent)

        first = await store.get("session-1")
        second = await store.get("session-1")

        assert first is second
        assert first.session_id == "session-1"
        assert len(agent.created_sessions) == 1

    async def test_reset_forgets_session(self) -> None:
        agent = _FakeAgent()
        store = SessionStore(agent)

        first = await store.get("session-1")
        await store.reset("session-1")
        second = await store.get("session-1")

        assert first is not second
        assert len(agent.created_sessions) == 2

    async def test_empty_session_id_raises(self) -> None:
        store = SessionStore(_FakeAgent())

        with pytest.raises(ValueError, match="session_id"):
            await store.get("")
        with pytest.raises(ValueError, match="session_id"):
            await store.reset("")


class TestAgentFrameworkState:
    def test_default_session_store_for_agent(self) -> None:
        agent = _FakeAgent()
        state = AgentFrameworkState(agent)

        assert state.target is agent
        assert isinstance(state.session_store, SessionStore)

    def test_accepts_session_store_instance(self) -> None:
        agent = _FakeAgent()
        store = SessionStore(agent)
        state = AgentFrameworkState(agent, session_store=store)

        assert state.target is agent
        assert state.session_store is store

    def test_accepts_session_store_factory(self) -> None:
        agent = _FakeAgent()

        def factory(target: Any) -> SessionStore:
            return SessionStore(target)

        state = AgentFrameworkState(agent, session_store=factory)

        assert isinstance(state.session_store, SessionStore)

    async def test_callable_target_cached_by_default(self) -> None:
        calls = 0

        def create_agent() -> _FakeAgent:
            nonlocal calls
            calls += 1
            return _FakeAgent()

        state = AgentFrameworkState(create_agent)

        first = await state.get_target()
        second = await state.get_target()

        assert first is second
        assert calls == 1

    async def test_callable_target_cache_can_be_disabled(self) -> None:
        calls = 0

        def create_agent() -> _FakeAgent:
            nonlocal calls
            calls += 1
            return _FakeAgent()

        state = AgentFrameworkState(create_agent, cache_target=False)

        first = await state.get_target()
        second = await state.get_target()

        assert first is not second
        assert calls == 2

    async def test_async_callable_target(self) -> None:
        async def create_agent() -> _FakeAgent:
            return _FakeAgent()

        state = AgentFrameworkState(create_agent)

        assert isinstance(await state.get_target(), _FakeAgent)

    async def test_get_session_resolves_target_and_store(self) -> None:
        state = AgentFrameworkState(lambda: _FakeAgent())

        session = await state.get_session("session-1")

        assert session.session_id == "session-1"
