# Copyright (c) Microsoft. All rights reserved.

"""Request factory lifetime and workflow persistence for the text-only host."""

import asyncio
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import (
    Agent,
    AgentExecutor,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Executor,
    FunctionalWorkflowAgent,
    InMemoryCheckpointStorage,
    Message,
    ResponseStream,
    RunContext,
    SessionStore,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowCheckpointException,
    WorkflowContext,
    WorkflowEvent,
    handler,
    response_handler,
    step,
    workflow,
)
from anyio import CancelScope, create_task_group
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    get_request_context,
    reset_request_context,
    set_request_context,
)
from starlette.requests import Request
from starlette.responses import StreamingResponse
from typing_extensions import AsyncGenerator, Never, Self

from agent_framework_foundry_hosting import InvocationsHostServer


@contextmanager
def _context(user: str | None = "user", session: str = "session") -> Iterator[None]:
    token = set_request_context(FoundryAgentRequestContext(user_id=user, session_id=session))
    try:
        yield
    finally:
        reset_request_context(token)


def _request(message: str = "hello", *, stream: bool = False) -> Request:
    request = MagicMock(spec=Request)
    request.json = AsyncMock(return_value={"message": message, "stream": stream})
    return request


async def _invoke(
    server: InvocationsHostServer,
    message: str = "hello",
    *,
    stream: bool = False,
    user: str | None = "user",
    session: str = "session",
) -> str:
    with _context(user, session):
        response = await server._handle_invoke(_request(message, stream=stream))
        if isinstance(response, StreamingResponse):
            chunks = [chunk async for chunk in response.body_iterator]
            return "".join(chunk if isinstance(chunk, str) else bytes(chunk).decode() for chunk in chunks)
        return bytes(response.body).decode()


class _OwnedAgent:
    def __init__(self, events: list[str], *, fail: bool = False, wait: asyncio.Event | None = None) -> None:
        self.id = "ordinary"
        self.name: str | None = "ordinary"
        self.description: str | None = None
        self.events = events
        self.fail = fail
        self.wait = wait
        self.owner: asyncio.Task[Any] | None = None
        self.calls: list[Any] = []
        self.session: AgentSession | None = None

    async def __aenter__(self) -> "_OwnedAgent":
        self.owner = asyncio.current_task()
        self.events.append("enter")
        return self

    async def __aexit__(self, *args: Any) -> None:
        assert asyncio.current_task() is self.owner
        await asyncio.sleep(0)
        self.events.append("exit")

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(self, service_session_id: Any, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id, service_session_id=service_session_id)

    def run(self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any) -> Any:
        self.calls.append(messages)
        self.session = session

        async def updates() -> AsyncGenerator[AgentResponseUpdate]:
            try:
                self.events.append("run")
                yield AgentResponseUpdate(contents=[Content.from_text("a")])
                if self.wait is not None:
                    await self.wait.wait()
                if self.fail:
                    raise RuntimeError("run failed")
                yield AgentResponseUpdate(contents=[Content.from_text("")])
                yield AgentResponseUpdate(contents=[Content.from_text("b")])
            finally:
                await asyncio.sleep(0)
                self.events.append("iterator closed")

        async def response() -> AgentResponse:
            self.events.append("run")
            if self.wait is not None:
                await self.wait.wait()
            if self.fail:
                raise RuntimeError("run failed")
            return AgentResponse(messages=[Message("assistant", ["ab"])])

        return ResponseStream(updates(), finalizer=AgentResponse.from_updates) if stream else response()


class _Stores:
    def __init__(self) -> None:
        self.checkpoints: dict[str, InMemoryCheckpointStorage] = {}
        self.sessions = SessionStore()
        self.checkpoint_provider = MagicMock()
        self.checkpoint_provider.get_store.side_effect = self._checkpoint_store
        self.session_provider = MagicMock()
        self.session_provider.get_store.return_value = self.sessions

    def _checkpoint_store(self, *, context_id: str, **kwargs: Any) -> InMemoryCheckpointStorage:
        assert get_request_context().session_id is not None
        assert context_id.startswith("~invocations-")
        assert "/" not in context_id and "\\" not in context_id
        return self.checkpoints.setdefault(context_id, InMemoryCheckpointStorage())

    def server(self, factory: Callable[..., Any]) -> InvocationsHostServer:
        return InvocationsHostServer(
            agent_factory=factory,
            checkpoint_store_provider=self.checkpoint_provider,
            agent_session_store_provider=self.session_provider,
        )


class _Counter(Executor):
    def __init__(self) -> None:
        super().__init__(id="counter")
        self.count = 0

    @handler
    async def count_message(self, messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
        self.count += 1
        # Include the outer provider history, not just executor checkpoint state.
        await ctx.yield_output(f"{self.count}:{'|'.join(message.text for message in messages)}")

    async def on_checkpoint_save(self) -> dict[str, Any]:
        return {"count": self.count}

    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        self.count = state["count"]


def _graph(name: str = "counter") -> WorkflowAgent:
    return WorkflowBuilder(name=name, start_executor=_Counter()).build().as_agent()


@workflow(name="functional")
async def _functional(messages: Any) -> str:
    return str(messages)


@workflow(name="functional-pending")
async def _functional_pending(messages: Any, ctx: RunContext) -> str:
    await ctx.request_info("approve?", response_type=str)
    return str(messages)


class _Pending(Executor):
    @handler
    async def ask(self, messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
        await ctx.request_info("approve?", response_type=str)

    @response_handler
    async def answer(self, original_request: str, response: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(response)


def _pending_graph() -> WorkflowAgent:
    return WorkflowBuilder(name="pending", start_executor=_Pending(id="pending")).build().as_agent()


@pytest.mark.parametrize("factory", [_graph, lambda: _functional.build().as_agent()])
def test_direct_workflow_instances_and_subclasses_require_factory(factory: Callable[..., Any]) -> None:
    agent = factory()
    with pytest.raises(TypeError, match="agent_factory"):
        InvocationsHostServer(agent)
    subclass: Any = type("CustomWorkflowAgent", (type(agent),), {})
    underlying = agent.workflow if isinstance(agent, WorkflowAgent) else agent._workflow
    with pytest.raises(TypeError, match="agent_factory"):
        InvocationsHostServer(subclass(underlying))


def test_factory_source_validation_and_no_startup_call() -> None:
    factory = MagicMock()
    with pytest.raises(ValueError, match="exactly one"):
        InvocationsHostServer()
    with pytest.raises(ValueError, match="exactly one"):
        InvocationsHostServer(_OwnedAgent([]), agent_factory=factory)
    with pytest.raises(TypeError, match="callable"):
        InvocationsHostServer(agent_factory=cast(Any, 42))
    InvocationsHostServer(agent_factory=factory)
    factory.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("awaitable", [False, True])
async def test_factory_once_per_request_inside_context_preserves_text(stream: bool, awaitable: bool) -> None:
    events: list[str] = []
    agents: list[_OwnedAgent] = []

    def factory() -> Any:
        assert get_request_context().user_id == "user"
        agent = _OwnedAgent(events)
        agents.append(agent)

        async def create() -> _OwnedAgent:
            return agent

        return create() if awaitable else agent

    server = InvocationsHostServer(agent_factory=factory)
    assert await _invoke(server, stream=stream) == "ab"
    assert await _invoke(server, "second", stream=stream) == "ab"
    assert len(agents) == 2
    assert agents[0].session is agents[1].session
    assert agents[0].calls == ["hello" if stream else ["hello"]]
    assert events == (["enter", "run", "iterator closed", "exit"] if stream else ["enter", "run", "exit"]) * 2
    assert server._agent is None
    assert not server._scope_locks._entries


@pytest.mark.parametrize("stream", [False, True])
async def test_async_factory_failure_and_invalid_result_release_lock(stream: bool) -> None:
    calls = 0

    async def factory() -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("construction failed")
        return object()

    server = InvocationsHostServer(agent_factory=factory)
    with pytest.raises(RuntimeError, match="construction failed"):
        await _invoke(server, stream=stream)
    with pytest.raises(TypeError, match="agent_factory must return"):
        await _invoke(server, stream=stream)
    assert calls == 2
    assert not server._scope_locks._entries


@pytest.mark.parametrize("stream", [False, True])
async def test_run_failure_closes_owner_and_iterator(stream: bool) -> None:
    events: list[str] = []
    server = InvocationsHostServer(agent_factory=lambda: _OwnedAgent(events, fail=True))
    with pytest.raises(RuntimeError, match="run failed"):
        await _invoke(server, stream=stream)
    assert events == (["enter", "run", "iterator closed", "exit"] if stream else ["enter", "run", "exit"])
    assert not server._scope_locks._entries


async def test_stream_factory_and_resources_belong_to_asgi_consumer_task() -> None:
    events: list[str] = []
    creation_task: asyncio.Task[Any] | None = None

    def factory() -> _OwnedAgent:
        nonlocal creation_task
        creation_task = asyncio.current_task()
        return _OwnedAgent(events)

    server = InvocationsHostServer(agent_factory=factory)
    with _context():
        response = await server._handle_invoke(_request(stream=True))
        assert creation_task is None
        assert isinstance(response, StreamingResponse)
        body: list[bytes] = []

        async def send(message: Any) -> None:
            if message["type"] == "http.response.body":
                body.append(message["body"])

        consumer = asyncio.create_task(response.stream_response(send))
        await consumer
    assert creation_task is consumer
    assert b"".join(body) == b"ab"
    assert events == ["enter", "run", "iterator closed", "exit"]


@pytest.mark.parametrize("disconnect", [False, True])
async def test_stream_disconnect_or_cancellation_closes_suspended_iterator(disconnect: bool) -> None:
    events: list[str] = []
    sent = asyncio.Event()
    server = InvocationsHostServer(agent_factory=lambda: _OwnedAgent(events))
    with _context():
        response = await server._handle_invoke(_request(stream=True))
        assert isinstance(response, StreamingResponse)

        async def send(message: Any) -> None:
            if message["type"] == "http.response.body":
                sent.set()
                if disconnect:
                    raise OSError("disconnected")
                await asyncio.Event().wait()

        consumer = asyncio.create_task(response.stream_response(send))
        await sent.wait()
        if not disconnect:
            consumer.cancel()
        with pytest.raises(OSError if disconnect else asyncio.CancelledError):
            await consumer
    assert events == ["enter", "run", "iterator closed", "exit"]
    assert not server._scope_locks._entries


async def test_cancelled_factory_construction_releases_scope() -> None:
    started = asyncio.Event()

    async def factory() -> _OwnedAgent:
        started.set()
        await asyncio.Event().wait()
        return _OwnedAgent([])

    server = InvocationsHostServer(agent_factory=factory)
    task = asyncio.create_task(_invoke(server))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not server._scope_locks._entries


async def test_same_scope_serializes_stream_through_cleanup_and_cancelled_waiters() -> None:
    events: list[str] = []
    release = asyncio.Event()
    first_chunk = asyncio.Event()
    created = 0

    def factory() -> _OwnedAgent:
        nonlocal created
        created += 1
        return _OwnedAgent(events)

    server = InvocationsHostServer(agent_factory=factory)
    with _context():
        response = await server._handle_invoke(_request(stream=True))
        assert isinstance(response, StreamingResponse)

        async def send(message: Any) -> None:
            if message["type"] == "http.response.body" and message.get("body"):
                first_chunk.set()
                await release.wait()

        consumer = asyncio.create_task(response.stream_response(send))
        await first_chunk.wait()
        cancelled = asyncio.create_task(_invoke(server))
        waiting = asyncio.create_task(_invoke(server))
        await asyncio.sleep(0)
        assert created == 1
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert len(server._scope_locks._entries) == 1
        assert await _invoke(server, session="independent") == "ab"
        assert created == 2
        release.set()
        await consumer
        assert await waiting == "ab"
    assert created == 3
    assert events == ["enter", "run", "enter", "run", "exit", "iterator closed", "exit", "enter", "run", "exit"]
    assert not server._scope_locks._entries


@pytest.mark.parametrize("stream", [False, True])
async def test_graph_checkpoint_and_outer_history_survive_new_host(stream: bool) -> None:
    stores = _Stores()
    assert await _invoke(stores.server(_graph), "first", stream=stream) == "1:first"
    second = await _invoke(stores.server(_graph), "second", stream=stream)
    assert second == "2:first|1:first|second"
    assert len(stores.checkpoints) == 1


@pytest.mark.parametrize("stream", [False, True])
async def test_graph_scopes_isolate_users_sessions_and_unsafe_identifiers(stream: bool) -> None:
    stores = _Stores()
    server = stores.server(_graph)
    scopes = [
        ("user", "../session"),
        ("another-user", "../session"),
        ("user", r"..\session"),
        ("a:b", "c"),
        ("b", "c:a"),
        ("USER", "../session"),
    ]
    for user, session in scopes:
        assert await _invoke(server, user, stream=stream, user=user, session=session) == f"1:{user}"
    assert len(stores.checkpoints) == len(scopes)
    for user, session in scopes:
        assert (await _invoke(server, "next", stream=stream, user=user, session=session)).startswith("2:")
    assert not server._sessions


@pytest.mark.parametrize("same_wrapper", [False, True])
@pytest.mark.parametrize("functional", [False, True])
async def test_reused_workflow_or_wrapper_is_rejected(same_wrapper: bool, functional: bool) -> None:
    stores = _Stores()
    agent = _functional.build().as_agent() if functional else _graph()
    underlying = agent.workflow if isinstance(agent, WorkflowAgent) else agent._workflow
    server = stores.server(lambda: agent if same_wrapper else underlying.as_agent())
    await _invoke(server)
    with pytest.raises(RuntimeError, match="reused a workflow"):
        await _invoke(server, session="other")
    assert not server._scope_locks._entries


@pytest.mark.parametrize("damage", ["checkpoint", "session", "name", "kind"])
async def test_missing_or_incompatible_continuation_never_restarts(damage: str) -> None:
    stores = _Stores()
    await _invoke(stores.server(_graph))
    storage_id, storage = next(iter(stores.checkpoints.items()))
    if damage == "checkpoint":
        for checkpoint in await storage.list_checkpoints(workflow_name="counter"):
            await storage.delete(checkpoint.checkpoint_id)
    elif damage == "session":
        await stores.sessions.delete(storage_id)

    def factory() -> WorkflowAgent | FunctionalWorkflowAgent:
        if damage == "kind":
            return _functional.build().as_agent()
        return _graph("different" if damage == "name" else "counter")

    with pytest.raises(RuntimeError, match="missing|does not match"):
        await _invoke(stores.server(factory), "next")


@pytest.mark.parametrize("stream", [False, True])
async def test_graph_pending_request_cannot_be_answered_with_plain_text(stream: bool) -> None:
    stores = _Stores()
    server = stores.server(_pending_graph)
    with pytest.raises(RuntimeError, match="plain text cannot answer"):
        await _invoke(server, stream=stream)
    with pytest.raises(RuntimeError, match="plain text cannot answer"):
        await _invoke(stores.server(_pending_graph), "approved", stream=stream)
    with pytest.raises(RuntimeError, match="plain text cannot answer"):
        await _invoke(server, "approved", stream=stream, user="other")
    assert len(stores.checkpoints) == 2


@pytest.mark.parametrize("stream", [False, True])
async def test_functional_clean_completion_starts_new_message(stream: bool) -> None:
    stores = _Stores()

    def factory() -> FunctionalWorkflowAgent:
        return _functional.build().as_agent()

    assert await _invoke(stores.server(factory), "first", stream=stream) == ("first" if stream else "['first']")
    storage = next(iter(stores.checkpoints.values()))
    checkpoint = await storage.get_latest(workflow_name="functional")
    assert checkpoint is not None
    # A completed functional checkpoint can retain old pending events. Only the
    # host's completion record distinguishes it from interrupted work.
    checkpoint.pending_request_info_events["old"] = WorkflowEvent.request_info(
        request_id="old", source_executor_id="functional", request_data="old", response_type=str
    )
    await storage.save(checkpoint)
    assert await _invoke(stores.server(factory), "next", stream=stream) == ("next" if stream else "['next']")


@pytest.mark.parametrize("stream", [False, True])
async def test_functional_pending_continuation_is_explicitly_unsupported(stream: bool) -> None:
    stores = _Stores()

    def factory() -> FunctionalWorkflowAgent:
        return _functional_pending.build().as_agent()

    with pytest.raises(RuntimeError, match="plain text cannot answer"):
        await _invoke(stores.server(factory), stream=stream)
    with pytest.raises(RuntimeError, match="pending or interrupted functional"):
        await _invoke(stores.server(factory), "approved", stream=stream)


async def test_functional_interrupted_continuation_does_not_restart() -> None:
    stores = _Stores()
    calls = 0

    @workflow(name="interrupted")
    async def interrupted(messages: Any) -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("interrupted")

    def factory() -> FunctionalWorkflowAgent:
        return interrupted.build().as_agent()

    with pytest.raises(RuntimeError, match="interrupted"):
        await _invoke(stores.server(factory))
    with pytest.raises(RuntimeError, match="missing its required checkpoint"):
        await _invoke(stores.server(factory))
    assert calls == 1


async def test_session_save_failure_closes_workflow_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class OwnedWorkflow(WorkflowAgent):
        async def __aenter__(self) -> Self:
            events.append("enter")
            return self

        async def __aexit__(self, *args: Any) -> None:
            events.append("exit")

    stores = _Stores()
    monkeypatch.setattr(stores.sessions, "set", AsyncMock(side_effect=[None, RuntimeError("save failed")]))
    server = stores.server(lambda: OwnedWorkflow(_graph().workflow))
    with pytest.raises(RuntimeError, match="save failed"):
        await _invoke(server)
    assert events == ["enter", "exit"]
    assert not server._scope_locks._entries


@pytest.mark.parametrize("cancel", [False, True])
async def test_anyio_resource_scopes_exit_in_consumer_task_and_correct_order(cancel: bool) -> None:
    events: list[str] = []
    sent = asyncio.Event()

    class TaskGroupAgent(_OwnedAgent):
        async def __aenter__(self) -> Self:
            await super().__aenter__()
            self.group = create_task_group()
            await self.group.__aenter__()
            return self

        async def __aexit__(self, *args: Any) -> None:
            await self.group.__aexit__(*args)
            await super().__aexit__(*args)

    server = InvocationsHostServer(agent_factory=lambda: TaskGroupAgent(events))
    with _context():
        response = await server._handle_invoke(_request(stream=True))
        assert isinstance(response, StreamingResponse)
        scope = CancelScope()

        async def send(message: Any) -> None:
            if message["type"] == "http.response.body" and message.get("body"):
                sent.set()
                if cancel:
                    await asyncio.Event().wait()

        async def consume() -> None:
            with scope:
                await response.stream_response(send)

        consumer = asyncio.create_task(consume())
        await sent.wait()
        if cancel:
            scope.cancel()
        await consumer
    assert events == ["enter", "run", "iterator closed", "exit"]
    assert not server._scope_locks._entries


class _TranscriptClient(BaseChatClient):
    def __init__(self, transcripts: list[list[str]]) -> None:
        super().__init__()
        self.transcripts = transcripts

    def _inner_get_response(
        self, *, messages: Sequence[Message], stream: bool, options: Mapping[str, Any], **kwargs: Any
    ) -> Any:
        self.transcripts.append([message.text for message in messages])

        async def updates() -> AsyncGenerator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text("recorded")])

        async def response() -> ChatResponse:
            return ChatResponse(messages=[Message("assistant", ["recorded"])])

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates) if stream else response()


@pytest.mark.parametrize("stream", [False, True])
async def test_real_agent_executor_transcript_is_isolated_and_restored(stream: bool) -> None:
    stores = _Stores()
    transcripts: list[list[str]] = []

    def factory() -> WorkflowAgent:
        agent = Agent(client=_TranscriptClient(transcripts), name="inner")
        executor = AgentExecutor(agent, id="inner")
        return WorkflowBuilder(name="transcript", start_executor=executor).build().as_agent()

    assert await _invoke(stores.server(factory), "private-first", stream=stream) == "recorded"
    assert await _invoke(stores.server(factory), "unrelated", stream=stream, user="other") == "recorded"
    assert transcripts[-1] == ["unrelated"]
    assert await _invoke(stores.server(factory), "private-next", stream=stream) == "recorded"
    assert "private-first" in transcripts[-1]
    assert "private-next" in transcripts[-1]
    assert "unrelated" not in transcripts[-1]


@pytest.mark.parametrize("stream", [False, True])
async def test_functional_interruption_with_checkpoint_rejects_new_message(stream: bool) -> None:
    stores = _Stores()
    calls = 0

    @step
    async def saved_step() -> str:
        return "saved"

    @workflow(name="interrupted-after-step")
    async def interrupted(messages: Any) -> str:
        nonlocal calls
        calls += 1
        await saved_step()
        raise RuntimeError("failed after checkpoint")

    def factory() -> FunctionalWorkflowAgent:
        return interrupted.build().as_agent()

    with pytest.raises(RuntimeError, match="failed after checkpoint"):
        await _invoke(stores.server(factory), stream=stream)
    with pytest.raises(RuntimeError, match="pending or interrupted functional"):
        await _invoke(stores.server(factory), "next", stream=stream)
    assert calls == 1


@pytest.mark.parametrize("stream", [False, True])
async def test_cancellation_during_run_closes_resources(stream: bool) -> None:
    events: list[str] = []
    server = InvocationsHostServer(agent_factory=lambda: _OwnedAgent(events, wait=asyncio.Event()))
    task = asyncio.create_task(_invoke(server, stream=stream))
    await asyncio.sleep(0)
    assert events == ["enter", "run"]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events == (["enter", "run", "iterator closed", "exit"] if stream else ["enter", "run", "exit"])
    assert not server._scope_locks._entries


async def test_invalid_request_does_not_construct_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = MagicMock()
    server = InvocationsHostServer(agent_factory=factory)
    with _context():
        request = _request()
        monkeypatch.setattr(request, "json", AsyncMock(return_value={}))
        response = await server._handle_invoke(request)
        assert response.status_code == 400
    with _context():
        server.config.is_hosted = True
        with _context(user=None):
            response = await server._handle_invoke(_request())
        assert response.status_code == 500
    factory.assert_not_called()


async def test_checkpoint_failure_closes_workflow_owner_and_preserves_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class OwnedWorkflow(WorkflowAgent):
        async def __aenter__(self) -> Self:
            events.append("enter")
            return self

        async def __aexit__(self, *args: Any) -> None:
            events.append("exit")

    stores = _Stores()
    storage = InMemoryCheckpointStorage()
    monkeypatch.setattr(storage, "save", AsyncMock(side_effect=RuntimeError("checkpoint failed")))
    stores.checkpoint_provider.get_store.side_effect = None
    stores.checkpoint_provider.get_store.return_value = storage
    server = stores.server(lambda: OwnedWorkflow(_graph().workflow))
    with pytest.raises(RuntimeError, match="checkpoint failed"):
        await _invoke(server)
    with pytest.raises(RuntimeError, match="missing its required checkpoint"):
        await _invoke(server)
    assert events == ["enter", "exit", "enter", "exit"]
    assert not server._scope_locks._entries


@pytest.mark.parametrize("stream", [False, True])
async def test_checkpoint_preparation_failure_rejects_older_checkpoint_and_fresh_host_retry(stream: bool) -> None:
    stores = _Stores()
    calls: list[str] = []
    snapshots: list[int] = []
    agents: list[WorkflowAgent] = []

    class FailingCheckpoint(_Counter):
        @handler
        async def count_message(self, messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
            calls.extend(message.text for message in messages)
            await super().count_message(messages, ctx)

        async def on_checkpoint_save(self) -> dict[str, Any]:
            snapshots.append(self.count)
            if self.count:
                raise RuntimeError("executor checkpoint preparation failed")
            return await super().on_checkpoint_save()

    def factory() -> WorkflowAgent:
        agent = WorkflowBuilder(name="checkpoint-preparation", start_executor=FailingCheckpoint()).build().as_agent()
        agents.append(agent)
        return agent

    first = stores.server(factory)
    with pytest.raises(WorkflowCheckpointException, match="Executor counter on_checkpoint_save failed"):
        await _invoke(first, stream=stream)
    storage_id, storage = next(iter(stores.checkpoints.items()))
    checkpoint = await storage.get_latest(workflow_name="checkpoint-preparation")
    assert checkpoint is not None
    assert checkpoint.iteration_count == 0
    assert 0 in snapshots and 1 in snapshots
    session = await stores.sessions.get(storage_id)
    assert session is not None
    assert session.state["_foundry_invocations_workflow"]["checkpoint_failed"] is True

    second = stores.server(factory)
    with pytest.raises(RuntimeError, match="incomplete checkpoint persistence"):
        await _invoke(second, "must-not-run", stream=stream)
    assert calls == ["hello"]
    assert len(agents) == 2
    assert agents[0] is not agents[1]
    assert agents[0].workflow is not agents[1].workflow
    assert not first._scope_locks._entries
    assert not second._scope_locks._entries
