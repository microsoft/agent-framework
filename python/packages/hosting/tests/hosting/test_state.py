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
    InMemoryCheckpointStorage,
    Message,
    ResponseStream,
    Workflow,
)

from agent_framework_hosting import AgentState, CheckpointStore, SessionStore, WorkflowState


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


class TestSessionStore:
    async def test_get_returns_none_for_missing_id(self) -> None:
        store = SessionStore()

        assert await store.get("session-1") is None

    async def test_set_then_get_returns_stored_session(self) -> None:
        store = SessionStore()
        session = AgentSession(session_id="session-1")

        await store.set("session-1", session)

        assert await store.get("session-1") is session

    async def test_set_can_store_same_session_under_additional_id(self) -> None:
        store = SessionStore()
        session = AgentSession(session_id="resp_1")

        await store.set("resp_1", session)
        await store.set("resp_2", session)

        assert await store.get("resp_1") is session
        assert await store.get("resp_2") is session

    async def test_set_replaces_existing_entry(self) -> None:
        store = SessionStore()
        first = AgentSession(session_id="session-1")
        second = AgentSession(session_id="session-1")

        await store.set("session-1", first)
        await store.set("session-1", second)

        assert await store.get("session-1") is second

    async def test_delete_forgets_session(self) -> None:
        store = SessionStore()
        await store.set("session-1", AgentSession(session_id="session-1"))

        await store.delete("session-1")

        assert await store.get("session-1") is None

    async def test_delete_missing_id_is_a_no_op(self) -> None:
        store = SessionStore()

        await store.delete("never-stored")

    async def test_empty_session_id_raises(self) -> None:
        store = SessionStore()
        session = AgentSession(session_id="session-1")

        with pytest.raises(ValueError, match="session_id"):
            await store.get("")
        with pytest.raises(ValueError, match="session_id"):
            await store.set("", session)
        with pytest.raises(ValueError, match="session_id"):
            await store.delete("")


class TestCheckpointStore:
    async def test_get_returns_none_for_missing_id(self) -> None:
        store = CheckpointStore()

        assert await store.get("session-1") is None

    async def test_set_then_get_returns_stored_storage(self) -> None:
        store = CheckpointStore()
        storage = InMemoryCheckpointStorage()

        await store.set("session-1", storage)

        assert await store.get("session-1") is storage

    async def test_delete_forgets_storage(self) -> None:
        store = CheckpointStore()
        await store.set("session-1", InMemoryCheckpointStorage())

        await store.delete("session-1")

        assert await store.get("session-1") is None

    async def test_empty_session_id_raises(self) -> None:
        store = CheckpointStore()
        storage = InMemoryCheckpointStorage()

        with pytest.raises(ValueError, match="session_id"):
            await store.get("")
        with pytest.raises(ValueError, match="session_id"):
            await store.set("", storage)
        with pytest.raises(ValueError, match="session_id"):
            await store.delete("")


class TestAgentState:
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

        assert first is second
        assert first.session_id == "session-1"
        assert len(agent.created_sessions) == 1

    async def test_get_or_create_session_reuses_a_session_set_on_the_state(self) -> None:
        agent = _FakeAgent()
        state = AgentState(agent)
        pre_existing = AgentSession(session_id="session-1")
        await state.set_session("session-1", pre_existing)

        session = await state.get_or_create_session("session-1")

        assert session is pre_existing
        assert len(agent.created_sessions) == 0


class TestWorkflowState:
    def test_default_checkpoint_store_is_fresh_in_memory_store(self) -> None:
        workflow = _workflow_fixture("build_echo_workflow")()
        state: WorkflowState[Workflow] = WorkflowState(workflow)

        assert state.target is workflow
        assert isinstance(state.checkpoint_store, CheckpointStore)

    def test_accepts_checkpoint_store_instance(self) -> None:
        workflow = _workflow_fixture("build_echo_workflow")()
        store = CheckpointStore()
        state: WorkflowState[Workflow] = WorkflowState(workflow, checkpoint_store=store)

        assert state.checkpoint_store is store

    async def test_workflow_target_resolved_from_factory(self) -> None:
        build_echo_workflow = _workflow_fixture("build_echo_workflow")

        state: WorkflowState[Workflow] = WorkflowState(build_echo_workflow)

        target = await state.get_target()
        assert isinstance(target, Workflow)

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

    async def test_get_or_create_checkpoint_storage_creates_and_stores_once(self) -> None:
        workflow = _workflow_fixture("build_echo_workflow")()
        state: WorkflowState[Workflow] = WorkflowState(workflow)

        first = await state.get_or_create_checkpoint_storage("session-1")
        second = await state.get_or_create_checkpoint_storage("session-1")

        assert first is second
        assert isinstance(first, InMemoryCheckpointStorage)

    async def test_get_or_create_checkpoint_storage_reuses_storage_set_on_the_state(self) -> None:
        workflow = _workflow_fixture("build_echo_workflow")()
        state: WorkflowState[Workflow] = WorkflowState(workflow)
        pre_existing = InMemoryCheckpointStorage()
        await state.set_checkpoint_storage("session-1", pre_existing)

        storage = await state.get_or_create_checkpoint_storage("session-1")

        assert storage is pre_existing
