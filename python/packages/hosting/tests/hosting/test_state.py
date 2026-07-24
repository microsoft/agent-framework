# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
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
    SessionStore,
    Workflow,
)

import agent_framework_hosting
from agent_framework_hosting import AgentState, WorkflowState


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

    def get_session(self, service_session_id: Any, *, session_id: str | None = None) -> AgentSession:
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


class TestAgentState:
    def test_session_store_is_owned_by_core(self) -> None:
        assert "SessionStore" not in agent_framework_hosting.__all__
        assert not hasattr(agent_framework_hosting, "SessionStore")

    def test_default_session_store_is_fresh_in_memory_store(self) -> None:
        agent = _FakeAgent()
        state = AgentState(agent)

        assert state.target is agent
        assert isinstance(state.session_store, SessionStore)

    def test_accepts_session_store_instance(self) -> None:
        store = SessionStore()
        state = AgentState(_FakeAgent(), session_store=store)

        assert state.session_store is store

    async def test_callable_target_cached_by_default(self) -> None:
        calls = 0

        def create_agent() -> _FakeAgent:
            nonlocal calls
            calls += 1
            return _FakeAgent()

        state = AgentState(create_agent)

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

        state = AgentState(create_agent, cache_target=False)

        first = await state.get_target()
        second = await state.get_target()

        assert first is not second
        assert calls == 2

    async def test_async_callable_target(self) -> None:
        async def create_agent() -> _FakeAgent:
            return _FakeAgent()

        state = AgentState(create_agent)

        assert isinstance(await state.get_target(), _FakeAgent)

    async def test_bare_awaitable_target_is_awaited_once_for_concurrent_callers(self) -> None:
        calls = 0

        async def create_agent() -> _FakeAgent:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return _FakeAgent()

        state = AgentState(create_agent())

        first, second = await asyncio.gather(state.get_target(), state.get_target())

        assert first is second
        assert calls == 1

    def test_cache_target_false_rejects_bare_awaitable(self) -> None:
        async def create_agent() -> _FakeAgent:
            return _FakeAgent()

        coro = create_agent()
        try:
            with pytest.raises(ValueError, match="cache_target=False"):
                AgentState(coro, cache_target=False)
        finally:
            coro.close()

    async def test_get_or_create_session_creates_and_stores_once(self) -> None:
        agent = _FakeAgent()
        state = AgentState(agent)

        first = await state.get_or_create_session("session-1")
        second = await state.get_or_create_session("session-1")

        assert first is not second
        assert first.session_id == "session-1"
        assert second.session_id == "session-1"
        assert len(agent.created_sessions) == 1

    @pytest.mark.parametrize("session_id", ["two words", "tenant/user", "tenant:conversation", "' OR 1=1 --"])
    async def test_get_or_create_session_rejects_invalid_store_id(self, session_id: str) -> None:
        agent = _FakeAgent()
        state = AgentState(agent)

        with pytest.raises(ValueError, match="ASCII letters"):
            await state.get_or_create_session(session_id)

        assert agent.created_sessions == []

    async def test_get_or_create_session_creates_once_for_concurrent_callers(self) -> None:
        class _YieldingSessionStore(SessionStore):
            async def get(self, session_id: str) -> AgentSession | None:
                await asyncio.sleep(0)
                return await super().get(session_id)

            async def set(self, session_id: str, session: AgentSession) -> None:
                await asyncio.sleep(0)
                await super().set(session_id, session)

        agent = _FakeAgent()
        state = AgentState(agent, session_store=_YieldingSessionStore())

        sessions = await asyncio.gather(*(state.get_or_create_session("session-1") for _ in range(20)))

        assert len({id(session) for session in sessions}) == len(sessions)
        assert all(session.session_id == "session-1" for session in sessions)
        assert len(agent.created_sessions) == 1

    async def test_get_or_create_session_reuses_a_session_set_on_the_state(self) -> None:
        agent = _FakeAgent()
        state = AgentState(agent)
        pre_existing = AgentSession(session_id="session-1")
        await state.set_session("session-1", pre_existing)

        session = await state.get_or_create_session("session-1")

        assert session is not pre_existing
        assert session.session_id == pre_existing.session_id
        assert len(agent.created_sessions) == 0


class TestWorkflowState:
    def test_accepts_workflow_target_instance(self) -> None:
        workflow = _workflow_fixture("build_echo_workflow")()
        state: WorkflowState[Workflow] = WorkflowState(workflow)

        assert state.target is workflow

    async def test_workflow_target_resolved_from_factory(self) -> None:
        build_echo_workflow = _workflow_fixture("build_echo_workflow")

        state: WorkflowState[Workflow] = WorkflowState(build_echo_workflow)

        target = await state.get_target()
        assert isinstance(target, Workflow)

    async def test_bare_awaitable_workflow_target_is_awaited_once_for_concurrent_callers(self) -> None:
        calls = 0

        async def create_workflow() -> Workflow:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return _workflow_fixture("build_echo_workflow")()

        state: WorkflowState[Workflow] = WorkflowState(create_workflow())

        first, second = await asyncio.gather(state.get_target(), state.get_target())

        assert first is second
        assert calls == 1

    async def test_accepts_workflow_builder_instance_directly(self) -> None:
        """A ``WorkflowBuilder`` is not itself callable or awaitable; the state must
        recognize its `build()` method and call it, not cache the raw builder."""
        builder = _workflow_fixture("echo_workflow_builder")()

        state: WorkflowState[Workflow] = WorkflowState(builder)

        target = await state.get_target()
        assert isinstance(target, Workflow)
        assert state.target is target

    async def test_workflow_builder_is_built_once_and_cached_by_default(self) -> None:
        builder = _workflow_fixture("echo_workflow_builder")()
        state: WorkflowState[Workflow] = WorkflowState(builder)

        first = await state.get_target()
        second = await state.get_target()

        assert first is second

    async def test_workflow_builder_returns_fresh_targets_when_cache_disabled(self) -> None:
        builder = _workflow_fixture("echo_workflow_builder")()
        state: WorkflowState[Workflow] = WorkflowState(builder, cache_target=False)

        first = await state.get_target()
        second = await state.get_target()

        assert first is not second

    async def test_accepts_orchestration_style_builder_without_importing_orchestrations(self) -> None:
        """``SupportsBuild`` is structural: any object with a zero-arg ``build() -> Workflow``
        is accepted, matching ``agent_framework_orchestrations``' builders without this
        package depending on that one."""
        workflow = _workflow_fixture("build_echo_workflow")()

        class _FakeOrchestrationBuilder:
            def build(self) -> Workflow:
                return workflow

        state: WorkflowState[Workflow] = WorkflowState(_FakeOrchestrationBuilder())

        assert await state.get_target() is workflow
