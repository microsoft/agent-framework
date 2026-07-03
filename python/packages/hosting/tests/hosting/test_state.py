# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator, Awaitable, Mapping
from typing import Any, Literal, overload

import pytest
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    Content,
    Message,
    ResponseStream,
    Workflow,
)

from agent_framework_hosting import AgentFrameworkState, SessionStore


def _workflow_fixture(name: str) -> Any:
    """Load a fixture from ``_workflow_fixtures.py`` via the ``conftest``-registered alias.

    Mirrors ``test_host.py``'s helper: the local ``conftest.py`` registers
    ``_workflow_fixtures.py`` under the collision-proof name
    ``hosting_workflow_fixtures`` so it stays importable in both
    package-local and aggregate pytest runs.
    """
    return getattr(importlib.import_module("hosting_workflow_fixtures"), name)


class _FakeAgent:
    """Minimal agent target for state tests.

    Declares ``run`` with the same two overloads as ``SupportsAgentRun`` (one
    per ``stream`` value) so it satisfies the protocol under static type
    checking, not just at runtime.
    """

    id: str = "fake-agent"
    name: str | None = "Fake Agent"
    description: str | None = "Fake agent for tests"

    def __init__(self) -> None:
        self.created_sessions: list[AgentSession] = []

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        session = AgentSession(session_id=session_id)
        self.created_sessions.append(session)
        return session

    def get_session(self, service_session_id: str, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id, service_session_id=service_session_id)

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        if stream:

            async def _stream() -> AsyncIterator[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=[Content.from_text(text="ok")], role="assistant")

            return ResponseStream(_stream(), finalizer=lambda updates: AgentResponse.from_updates(updates))

        async def _get_response() -> AgentResponse[Any]:
            return AgentResponse(messages=Message(role="assistant", contents=[Content.from_text(text="ok")]))

        return _get_response()


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

    async def test_put_aliases_new_id_to_existing_session(self) -> None:
        agent = _FakeAgent()
        store = SessionStore(agent)

        session = await store.get("resp_1")
        aliased = await store.get("resp_1", alias="resp_2")

        assert aliased is session
        assert await store.get("resp_2") is session
        # Aliasing did not create a second session via the agent.
        assert len(agent.created_sessions) == 1

    async def test_alias_equal_to_session_id_is_a_no_op(self) -> None:
        agent = _FakeAgent()
        store = SessionStore(agent)

        session = await store.get("resp_1", alias="resp_1")

        assert session.session_id == "resp_1"
        assert len(agent.created_sessions) == 1

    async def test_put_empty_session_id_raises(self) -> None:
        store = SessionStore(_FakeAgent())

        with pytest.raises(ValueError, match="session_id"):
            await store.get("", alias="resp_2")


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

    async def test_reset_session_forgets_session(self) -> None:
        agent = _FakeAgent()
        state = AgentFrameworkState(agent)

        first = await state.get_session("session-1")
        await state.reset_session("session-1")
        second = await state.get_session("session-1")

        assert first is not second
        assert len(agent.created_sessions) == 2

    def test_session_store_for_non_agent_target_raises_type_error(self) -> None:
        workflow = _workflow_fixture("build_echo_workflow")()

        with pytest.raises(TypeError, match="session_store requires an agent target"):
            AgentFrameworkState(workflow, session_store=SessionStore)

    async def test_workflow_target_has_no_default_session_store(self) -> None:
        workflow: Workflow = _workflow_fixture("build_echo_workflow")()
        state = AgentFrameworkState(workflow)

        assert await state.get_target() is workflow
        assert state.session_store is None
        with pytest.raises(TypeError, match="session_store requires an agent target"):
            await state.get_session_store()

    async def test_workflow_target_resolved_from_factory(self) -> None:
        build_echo_workflow = _workflow_fixture("build_echo_workflow")

        state = AgentFrameworkState(build_echo_workflow)

        target = await state.get_target()
        assert isinstance(target, Workflow)
