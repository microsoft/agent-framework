# Copyright (c) Microsoft. All rights reserved.

"""Request-owned Responses agents, resources, and durable workflow continuation."""

import asyncio
import copy
import gc
import weakref
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator, Mapping, Sequence
from contextlib import aclosing, contextmanager
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
    InMemoryHistoryProvider,
    Message,
    ResponseStream,
    RunContext,
    SessionStore,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
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
from azure.ai.agentserver.responses import ResponseContext, ResponsesServerOptions
from azure.ai.agentserver.responses.models import CreateResponse
from azure.ai.agentserver.responses.streaming._checkpoint import ResponseCheckpointEvent
from typing_extensions import Never, Self

from agent_framework_foundry_hosting import ResponsesHostServer
from agent_framework_foundry_hosting._agent_factory import close_run_iterator


@contextmanager
def _platform(user: str = "alice") -> Iterator[None]:
    token = set_request_context(FoundryAgentRequestContext(user_id=user, session_id="platform-session"))
    try:
        yield
    finally:
        reset_request_context(token)


def _context(
    text: str = "hello",
    *,
    response: str = "response-1",
    conversation: str | None = "conversation",
    items: list[Any] | None = None,
    history: list[Any] | None = None,
) -> ResponseContext:
    context = ResponseContext(response_id=response, conversation_id=conversation, mode_flags=MagicMock())
    context.get_input_items = AsyncMock(  # type: ignore[method-assign]
        return_value=items
        if items is not None
        else [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}]
    )
    context.get_history = AsyncMock(return_value=history or [])  # type: ignore[method-assign]
    return context


def _request(previous: str | None = None) -> CreateResponse:
    request = CreateResponse(model="test-model", input="input resolved by context", stream=True)
    if previous is not None:
        request["previous_response_id"] = previous
    return request


async def _collect(
    server: ResponsesHostServer,
    context: ResponseContext | None = None,
    *,
    user: str = "alice",
    previous: str | None = None,
) -> list[Any]:
    with _platform(user):
        return [
            event async for event in server._handle_response(_request(previous), context or _context(), asyncio.Event())
        ]


def _types(events: list[Any]) -> list[str]:
    return [event["type"] for event in events if isinstance(event, Mapping)]


def _text(events: list[Any]) -> str:
    return "".join(
        event["delta"]
        for event in events
        if isinstance(event, Mapping) and event.get("type") == "response.output_text.delta"
    )


def _failure(events: list[Any]) -> str:
    assert _types(events)[-1] == "response.failed", events
    assert _types(events).count("response.failed") == 1
    assert "response.completed" not in _types(events)
    return events[-1]["response"]["error"]["message"]


class _ApprovalStore:
    def __init__(self) -> None:
        self.requests: dict[str, Content] = {}

    async def save_approval_request(self, request_id: str, content: Content) -> None:
        self.requests[request_id] = content

    async def load_approval_request(self, request_id: str) -> Content | None:
        return self.requests.get(request_id)


class _Stores:
    def __init__(self) -> None:
        self.sessions: dict[str | None, SessionStore] = {}
        self.checkpoints: dict[tuple[str | None, str], InMemoryCheckpointStorage] = {}
        self.approvals: dict[str | None, _ApprovalStore] = {}
        self.session_provider = MagicMock()
        self.session_provider.get_store.side_effect = self._sessions
        self.checkpoint_provider = MagicMock()
        self.checkpoint_provider.get_store.side_effect = self._checkpoints
        self.approval_provider = MagicMock()
        self.approval_provider.get_store.side_effect = self._approvals

    def _sessions(self, *, platform_context: FoundryAgentRequestContext, **kwargs: Any) -> SessionStore:
        assert get_request_context().user_id == platform_context.user_id
        return self.sessions.setdefault(platform_context.user_id, SessionStore())

    def _checkpoints(
        self, *, platform_context: FoundryAgentRequestContext, context_id: str, **kwargs: Any
    ) -> InMemoryCheckpointStorage:
        assert get_request_context().user_id == platform_context.user_id
        return self.checkpoints.setdefault((platform_context.user_id, context_id), InMemoryCheckpointStorage())

    def _approvals(self, *, platform_context: FoundryAgentRequestContext, **kwargs: Any) -> _ApprovalStore:
        assert get_request_context().user_id == platform_context.user_id
        return self.approvals.setdefault(platform_context.user_id, _ApprovalStore())

    def server(self, factory: Callable[..., Any], **kwargs: Any) -> ResponsesHostServer:
        return ResponsesHostServer(
            agent_factory=factory,
            history_source="agent",
            checkpoint_store_provider=self.checkpoint_provider,
            agent_session_store_provider=self.session_provider,
            function_approval_store_provider=self.approval_provider,
            **kwargs,
        )


class _OwnedAgent:
    id = "ordinary"
    name: str | None = "ordinary"
    description: str | None = "Request resource test agent"

    def __init__(self, events: list[str], *, wait: asyncio.Event | None = None, fail: bool = False) -> None:
        self.events = events
        self.wait = wait
        self.fail = fail
        self.owner: asyncio.Task[Any] | None = None
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
        assert stream
        self.session = session

        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            try:
                self.events.append("run")
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text("first")])
                if self.wait is not None:
                    await self.wait.wait()
                if self.fail:
                    raise RuntimeError("model failed")
                yield AgentResponseUpdate(role="assistant", contents=[Content.from_text("second")])
            finally:
                await asyncio.sleep(0)
                self.events.append("iterator closed")

        return ResponseStream(updates(), finalizer=AgentResponse.from_updates)


class _Counter(Executor):
    def __init__(self) -> None:
        super().__init__(id="counter")
        self.count = 0

    @handler
    async def count_message(self, messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
        self.count += 1
        await ctx.yield_output(f"{self.count}:{'|'.join(message.text for message in messages)}")

    async def on_checkpoint_save(self) -> dict[str, Any]:
        return {"count": self.count}

    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        self.count = state["count"]


def _graph(name: str = "counter", *, history: bool = False) -> WorkflowAgent:
    providers = [InMemoryHistoryProvider(source_id="outer-history")] if history else []
    return WorkflowBuilder(name=name, start_executor=_Counter()).build().as_agent(context_providers=providers)


@pytest.mark.parametrize("functional", [False, True])
@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("stage", ["preset", "session_load", "input", "checkpoint_lookup", "attempt_save"])
async def test_cancelled_workflow_preparation_preserves_session_and_next_request(
    functional: bool, completed: bool, stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _cancel_workflow_preparation(functional, completed, stage, False, monkeypatch)


@pytest.mark.parametrize("functional", [False, True])
@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("stage", ["session_load", "input", "checkpoint_lookup", "attempt_save"])
async def test_task_cancelled_workflow_preparation_preserves_session_and_next_request(
    functional: bool, completed: bool, stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _cancel_workflow_preparation(functional, completed, stage, True, monkeypatch)


@pytest.mark.parametrize("functional", [False, True])
@pytest.mark.parametrize("cancel_task", [False, True])
async def test_cancelled_workflow_attempt_save_removes_unstarted_response_branch(
    functional: bool, cancel_task: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _cancel_workflow_preparation(functional, True, "attempt_save", cancel_task, monkeypatch, chain=True)


async def _cancel_workflow_preparation(
    functional: bool,
    completed: bool,
    stage: str,
    cancel_task: bool,
    monkeypatch: pytest.MonkeyPatch,
    *,
    chain: bool = False,
) -> None:
    stores = _Stores()
    factory = (lambda: _functional.build().as_agent()) if functional else _graph
    stores.sessions["alice"] = SessionStore()
    sessions = stores.sessions["alice"]
    storage = InMemoryCheckpointStorage()
    conversation = None if chain else "conversation"
    saved_id = "initial" if chain else "conversation"
    previous_id = "initial" if chain else None
    stores.checkpoints[("alice", saved_id)] = storage
    if completed:
        initial = await _collect(
            stores.server(factory), _context("before", response="initial", conversation=conversation)
        )
        assert _types(initial)[-1] == "response.completed"
    previous = await sessions.get(saved_id)
    previous_snapshot = previous.to_dict() if previous is not None else None
    checkpoint_ids = await storage.list_checkpoint_ids(workflow_name="functional" if functional else "counter")
    context = _context("cancelled", response="cancelled", conversation=conversation)
    cancellation_signal = asyncio.Event()
    cancelled = False
    consumer: asyncio.Task[list[Any]] | None = None

    async def consume() -> list[Any]:
        with _platform():
            return [
                event
                async for event in stores.server(factory)._handle_response(
                    _request(previous_id), context, cancellation_signal
                )
            ]

    with monkeypatch.context() as patch:
        if stage == "preset":
            cancellation_signal.set()
        else:
            target, method = {
                "session_load": (sessions, "get"),
                "input": (context, "get_input_items"),
                "checkpoint_lookup": (storage, "get_latest"),
                "attempt_save": (sessions, "set"),
            }[stage]
            original = getattr(target, method)

            async def cancel_after_preparation(*args: Any, **kwargs: Any) -> Any:
                nonlocal cancelled
                result = await original(*args, **kwargs)
                if not cancelled:
                    cancelled = True
                    if cancel_task:
                        assert consumer is not None
                        consumer.cancel()
                    else:
                        cancellation_signal.set()
                    await asyncio.sleep(0)
                return result

            patch.setattr(target, method, cancel_after_preparation)
        consumer = asyncio.create_task(consume())
        if cancel_task:
            with pytest.raises(asyncio.CancelledError):
                await consumer
        else:
            events = await consumer
            assert not _text(events)
            assert _types(events)[-1] == "response.completed"
    current = await sessions.get(saved_id)
    assert (current.to_dict() if current is not None else None) == previous_snapshot
    assert await storage.list_checkpoint_ids(workflow_name="functional" if functional else "counter") == checkpoint_ids
    if chain:
        assert await sessions.get("cancelled") is None

    following = await _collect(
        stores.server(factory), _context("next", response="following", conversation=conversation), previous=previous_id
    )
    assert _types(following)[-1] == "response.completed", following
    assert _text(following) == ("next" if functional else f"{2 if completed else 1}:next")


@pytest.mark.parametrize("functional", [False, True])
async def test_cancelled_workflow_execution_without_checkpoint_preserves_incomplete_attempt(
    functional: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    stores = _Stores()
    storage = InMemoryCheckpointStorage()
    stores.checkpoints[("alice", "conversation")] = storage
    started = asyncio.Event()
    release = asyncio.Event()
    cancellation_signal = asyncio.Event()
    calls: list[str] = []

    @workflow(name="interrupted")
    async def interrupted(messages: list[Message]) -> str:
        calls.append(messages[0].text)
        started.set()
        await release.wait()
        return messages[0].text

    factory = (lambda: interrupted.build().as_agent()) if functional else _graph

    async def consume() -> list[Any]:
        with _platform():
            return [
                event
                async for event in stores.server(factory)._handle_response(
                    _request(), _context("original"), cancellation_signal
                )
            ]

    with monkeypatch.context() as patch:
        if not functional:
            original_save = storage.save

            async def blocked_checkpoint(checkpoint: Any) -> str:
                started.set()
                await release.wait()
                return await original_save(checkpoint)

            patch.setattr(storage, "save", blocked_checkpoint)
        consumer = asyncio.create_task(consume())
        await asyncio.wait_for(started.wait(), 2)
        cancellation_signal.set()
        await asyncio.wait_for(consumer, 2)

    session = await stores.sessions["alice"].get("conversation")
    assert session is not None
    assert session.state["_foundry_responses_workflow"]["completed"] is False
    assert not await storage.list_checkpoint_ids(workflow_name="interrupted" if functional else "counter")
    following = await _collect(stores.server(factory), _context("next", response="next"))
    assert "missing its required workflow checkpoint" in _failure(following)
    if functional:
        assert calls == ["original"]
    else:
        context = _context("original")
        context.is_recovery = True
        recovered = await _collect(
            stores.server(factory, options=ResponsesServerOptions(resilient_background=True)), context
        )
        assert _types(recovered)[-1] == "response.completed"
        assert _text(recovered) == "1:original"


@workflow(name="functional")
async def _functional(messages: list[Message]) -> str:
    return "|".join(message.text for message in messages)


@workflow(name="functional-pending-string")
async def _pending_string(messages: list[Message], ctx: RunContext) -> str:
    answer = await ctx.request_info("answer?", response_type=str)
    return f"{messages[0].text}:{answer}"


@workflow(name="functional-pending-bool")
async def _pending_bool(messages: list[Message], ctx: RunContext) -> str:
    answer = await ctx.request_info("approve?", response_type=bool)
    return f"{messages[0].text}:{answer}"


class _Pending(Executor):
    @handler
    async def ask(self, messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
        await ctx.request_info(messages[0].text, response_type=str)

    @response_handler
    async def answer(self, original_request: str, response: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(f"{original_request}:{response}")


def _pending_graph() -> WorkflowAgent:
    return WorkflowBuilder(name="pending", start_executor=_Pending(id="pending")).build().as_agent()


def test_constructor_validates_exactly_one_callable_without_constructing() -> None:
    factory = MagicMock()
    with pytest.raises(ValueError, match="exactly one"):
        ResponsesHostServer()
    with pytest.raises(ValueError, match="exactly one"):
        ResponsesHostServer(_OwnedAgent([]), agent_factory=factory)
    with pytest.raises(TypeError, match="callable"):
        ResponsesHostServer(agent_factory=cast(Any, 42))
    server = _Stores().server(factory)
    factory.assert_not_called()
    assert server._agent is None


def test_constructor_rejects_coroutine_object_instead_of_factory() -> None:
    async def factory() -> _OwnedAgent:
        return _OwnedAgent([])

    coroutine = factory()
    try:
        with pytest.raises(TypeError, match="callable"):
            ResponsesHostServer(agent_factory=cast(Any, coroutine))
    finally:
        coroutine.close()


@pytest.mark.parametrize("functional", [False, True])
@pytest.mark.parametrize("subclass", [False, True])
def test_direct_workflow_instances_require_factory(functional: bool, subclass: bool) -> None:
    agent = _functional.build().as_agent() if functional else _graph()
    if subclass:
        underlying = agent._workflow if isinstance(agent, FunctionalWorkflowAgent) else agent.workflow
        agent = type("CustomWorkflow", (type(agent),), {})(underlying)
    with pytest.raises(TypeError, match="agent_factory"):
        ResponsesHostServer(agent)


@pytest.mark.parametrize("kind", ["sync", "async", "awaitable-object"])
async def test_factory_runs_once_per_request_not_startup_and_never_sets_instance_agent(kind: str) -> None:
    events: list[str] = []
    agents: list[_OwnedAgent] = []

    def create() -> _OwnedAgent:
        assert get_request_context().user_id == "alice"
        agent = _OwnedAgent(events)
        agents.append(agent)
        return agent

    async def create_async() -> _OwnedAgent:
        return create()

    class AwaitableFactory:
        def __call__(self) -> Any:
            return create_async()

    factories: dict[str, Callable[..., Any]] = {
        "sync": create,
        "async": create_async,
        "awaitable-object": AwaitableFactory(),
    }
    server = _Stores().server(factories[kind])
    assert not agents
    for response in ("one", "two"):
        result = await _collect(server, _context(response=response))
        assert _text(result) == "firstsecond"
        assert _types(result)[-1] == "response.completed"
        assert server._agent is None
        assert server._agent_stack is None
    await server._cleanup_agent()
    assert len(agents) == 2
    assert events == ["enter", "run", "iterator closed", "exit"] * 2
    assert not server._scope_locks._entries


@pytest.mark.parametrize("kind", ["invalid", "exception", "async-exception"])
async def test_factory_failure_is_not_retried_and_releases_lock(kind: str) -> None:
    calls = 0

    def factory() -> Any:
        nonlocal calls
        calls += 1
        if kind == "invalid":
            return object()
        if kind == "exception":
            raise RuntimeError("factory failed")

        async def failed() -> Any:
            raise RuntimeError("factory failed")

        return failed()

    server = _Stores().server(factory)
    message = _failure(await _collect(server))
    assert ("SupportsAgentRun" if kind == "invalid" else "factory failed") in message
    assert calls == 1
    assert server._agent is None
    assert not server._scope_locks._entries


async def test_cancelled_factory_is_not_retried_and_releases_lock() -> None:
    entered = asyncio.Event()
    calls = 0

    async def factory() -> Any:
        nonlocal calls
        calls += 1
        entered.set()
        await asyncio.Event().wait()

    server = _Stores().server(factory)
    consumer = asyncio.create_task(_collect(server))
    await asyncio.wait_for(entered.wait(), 2)
    consumer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer
    assert calls == 1
    assert not server._scope_locks._entries


@pytest.mark.parametrize("functional", [False, True])
@pytest.mark.parametrize("same_wrapper", [False, True])
async def test_reusing_workflow_wrapper_or_underlying_workflow_fails(functional: bool, same_wrapper: bool) -> None:
    agent = _functional.build().as_agent() if functional else _graph()
    underlying = agent._workflow if isinstance(agent, FunctionalWorkflowAgent) else agent.workflow
    server = _Stores().server(lambda: agent if same_wrapper else underlying.as_agent())
    assert _types(await _collect(server))[-1] == "response.completed"
    assert "reused" in _failure(await _collect(server, _context(response="two")))
    assert not server._scope_locks._entries


@pytest.mark.parametrize("functional", [False, True])
async def test_completed_workflows_are_not_retained_by_factory_resolver(functional: bool) -> None:
    refs: list[weakref.ReferenceType[Any]] = []

    def factory() -> Any:
        agent = _functional.build().as_agent() if functional else _graph()
        underlying = agent._workflow if isinstance(agent, FunctionalWorkflowAgent) else agent.workflow
        refs.extend([weakref.ref(agent), weakref.ref(underlying)])
        return agent

    server = _Stores().server(factory)
    assert _types(await _collect(server))[-1] == "response.completed"
    await asyncio.sleep(0)
    gc.collect()
    assert all(reference() is None for reference in refs)
    assert server._agent_resolver is not None
    assert not server._agent_resolver._seen


@pytest.mark.parametrize("finish", ["complete", "close", "cancel-signal", "model-error"])
async def test_resources_stay_open_through_output_and_close_exactly_once(finish: str) -> None:
    events: list[str] = []
    server = _Stores().server(
        lambda: _OwnedAgent(
            events, wait=asyncio.Event() if finish in ("close", "cancel-signal") else None, fail=finish == "model-error"
        )
    )
    cancellation = asyncio.Event()
    emitted: list[Any] = []
    with _platform():
        stream = cast(AsyncGenerator[Any, None], server._handle_response(_request(), _context(), cancellation))
        async with aclosing(stream):
            async for event in stream:
                emitted.append(event)
                kind = event.get("type") if isinstance(event, Mapping) else None
                if kind == "response.output_text.delta":
                    assert "enter" in events and "exit" not in events
                    if finish == "close":
                        break
                    if finish == "cancel-signal":
                        cancellation.set()
                if kind in ("response.completed", "response.failed"):
                    assert events[-1] == "exit"
    assert events == ["enter", "run", "iterator closed", "exit"]
    assert not server._scope_locks._entries
    if finish == "model-error":
        assert "model failed" in _failure(emitted)


@pytest.mark.parametrize("model_failure", [False, True])
async def test_session_persistence_failure_closes_resources_and_reports_both_errors(
    model_failure: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    stores = _Stores()
    sessions = SessionStore()
    monkeypatch.setattr(sessions, "set", AsyncMock(side_effect=RuntimeError("session save failed")))
    stores.sessions["alice"] = sessions
    server = stores.server(lambda: _OwnedAgent(events, fail=model_failure))
    message = _failure(await _collect(server))
    assert "session save failed" in message
    if model_failure:
        assert "model failed" in message
    assert events == ["enter", "run", "iterator closed", "exit"]
    assert not server._scope_locks._entries


@pytest.mark.parametrize("cancel", [False, True])
async def test_nested_task_affine_resources_close_in_consumer_task_under_anyio_cancellation(
    cancel: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    sent = asyncio.Event()
    scope = CancelScope()
    stores = _Stores()
    sessions = SessionStore()
    save = sessions.set

    async def persist(session_id: str, session: AgentSession) -> None:
        await asyncio.sleep(0)
        await save(session_id, session)
        events.append("saved")

    monkeypatch.setattr(sessions, "set", AsyncMock(side_effect=persist))
    stores.sessions["alice"] = sessions

    class NestedAgent(_OwnedAgent):
        async def __aenter__(self) -> Self:
            await super().__aenter__()
            self.group = create_task_group()
            await self.group.__aenter__()
            return self

        async def __aexit__(self, *args: Any) -> None:
            await self.group.__aexit__(*args)
            await super().__aexit__(*args)

    server = stores.server(lambda: NestedAgent(events))

    async def consume() -> None:
        with _platform(), scope:
            stream = cast(AsyncGenerator[Any, None], server._handle_response(_request(), _context(), asyncio.Event()))
            async with aclosing(stream):
                async for event in stream:
                    if isinstance(event, Mapping) and event.get("type") == "response.output_text.delta":
                        sent.set()
                        if cancel:
                            await asyncio.Event().wait()

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(sent.wait(), 2)
    if cancel:
        scope.cancel()
    await asyncio.wait_for(consumer, 2)
    assert events == ["enter", "run", "iterator closed", "saved", "exit"]
    assert not server._scope_locks._entries


async def test_scope_lock_covers_last_output_cleanup_and_removes_cancelled_waiters() -> None:
    events: list[str] = []
    exiting = asyncio.Event()
    release = asyncio.Event()
    constructed = 0

    class SlowExit(_OwnedAgent):
        async def __aexit__(self, *args: Any) -> None:
            exiting.set()
            await release.wait()
            await super().__aexit__(*args)

    def factory() -> _OwnedAgent:
        nonlocal constructed
        constructed += 1
        return SlowExit(events) if constructed == 1 else _OwnedAgent(events)

    server = _Stores().server(factory)
    first = asyncio.create_task(_collect(server))
    await asyncio.wait_for(exiting.wait(), 2)
    second = asyncio.create_task(_collect(server, _context(response="two")))
    cancelled = asyncio.create_task(_collect(server, _context(response="three")))
    await asyncio.sleep(0)
    assert constructed == 1
    assert not first.done()
    assert next(iter(server._scope_locks._entries.values())).users == 3
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert next(iter(server._scope_locks._entries.values())).users == 2
    release.set()
    results = await asyncio.wait_for(asyncio.gather(first, second), 2)
    assert all(_types(result)[-1] == "response.completed" for result in results)
    assert constructed == 2
    assert not server._scope_locks._entries


@pytest.mark.parametrize("other_user,other_scope", [("bob", "conversation"), ("alice", "other")])
async def test_distinct_users_or_conversations_can_overlap(other_user: str, other_scope: str) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    def factory() -> _OwnedAgent:
        nonlocal calls
        calls += 1
        if calls == 2:
            started.set()
        return _OwnedAgent([], wait=release)

    server = _Stores().server(factory)
    first = asyncio.create_task(_collect(server))
    second = asyncio.create_task(_collect(server, _context(conversation=other_scope), user=other_user))
    try:
        await asyncio.wait_for(started.wait(), 2)
    finally:
        release.set()
        results = await asyncio.gather(first, second)
    assert all(_types(result)[-1] == "response.completed" for result in results)
    assert not server._scope_locks._entries


@pytest.mark.parametrize("chain", [False, True])
@pytest.mark.parametrize("history", [False, True])
async def test_graph_state_and_explicit_outer_history_survive_new_hosts(chain: bool, history: bool) -> None:
    stores = _Stores()
    conversation = None if chain else "conversation"
    first = await _collect(stores.server(lambda: _graph(history=history)), _context("first", conversation=conversation))
    assert _text(first) == "1:first"
    second = await _collect(
        stores.server(lambda: _graph(history=history)),
        _context("second", response="response-2", conversation=conversation),
        previous="response-1" if chain else None,
    )
    assert _types(second)[-1] == "response.completed"
    assert _text(second) == ("2:first|1:first|second" if history else "2:second")
    assert ("alice", "response-2" if chain else "conversation") in stores.checkpoints


async def test_graph_stable_name_must_match_saved_marker_from_previous_host() -> None:
    stores = _Stores()
    assert _text(await _collect(stores.server(lambda: _graph("stable")))) == "1:hello"
    result = await _collect(stores.server(lambda: _graph("new-random-name")), _context("next", response="two"))
    assert "name or kind" in _failure(result)
    assert not _text(result)


async def test_graph_with_outer_history_requires_saved_session_alongside_checkpoint() -> None:
    stores = _Stores()
    assert _text(await _collect(stores.server(lambda: _graph(history=True)))) == "1:hello"
    stores.sessions.clear()
    result = await _collect(stores.server(lambda: _graph(history=True)), _context("next", response="two"))
    assert "missing its required outer agent session" in _failure(result)
    assert not _text(result)


class _TranscriptClient(BaseChatClient):
    def __init__(self, transcripts: list[list[str]]) -> None:
        super().__init__()
        self.transcripts = transcripts

    def _inner_get_response(
        self, *, messages: Sequence[Message], stream: bool, options: Mapping[str, Any], **kwargs: Any
    ) -> Any:
        assert stream
        self.transcripts.append([message.text for message in messages])

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text("recorded")])

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates)


@pytest.mark.parametrize("chain", [False, True])
async def test_agent_executor_transcript_isolates_users_scopes_and_continues_across_hosts(chain: bool) -> None:
    stores = _Stores()
    transcripts: list[list[str]] = []

    def factory() -> WorkflowAgent:
        agent = Agent(client=_TranscriptClient(transcripts), name="inner")
        inner = AgentExecutor(agent, id="inner")
        return WorkflowBuilder(name="transcript", start_executor=inner).build().as_agent()

    conversation = None if chain else "conversation"
    assert _text(await _collect(stores.server(factory), _context("private", conversation=conversation))) == "recorded"
    await _collect(stores.server(factory), _context("bob-only", conversation=conversation), user="bob")
    assert transcripts[-1] == ["bob-only"]
    await _collect(stores.server(factory), _context("other-scope", conversation="other"))
    assert transcripts[-1] == ["other-scope"]
    continued = await _collect(
        stores.server(factory),
        _context("next", response="response-2", conversation=conversation),
        previous="response-1" if chain else None,
    )
    assert _text(continued) == "recorded"
    assert transcripts[-1] == ["private", "recorded", "next"]


@pytest.mark.parametrize("functional", [False, True])
@pytest.mark.parametrize("damage", ["name", "checkpoint", "marker", "history"])
async def test_missing_or_incompatible_workflow_state_does_not_restart(functional: bool, damage: str) -> None:
    stores = _Stores()
    factory = (lambda: _functional.build().as_agent()) if functional else _graph
    assert _types(await _collect(stores.server(factory)))[-1] == "response.completed"
    session = await stores.sessions["alice"].get("conversation")
    assert session is not None
    if damage == "name":
        session.state["_foundry_responses_workflow"]["name"] = "different-name"
    elif damage == "marker":
        session.state.pop("_foundry_responses_workflow")
    else:
        stores.checkpoints.clear()
    await stores.sessions["alice"].set("conversation", session)
    context = _context("next", response="two", history=[{"type": "message"}] if damage == "history" else None)
    message = _failure(await _collect(stores.server(factory), context))
    assert ("name or kind" if damage in ("name", "marker") else "missing its required workflow checkpoint") in message


async def test_functional_resilient_background_is_explicitly_rejected_without_running() -> None:
    calls: list[str] = []

    @workflow(name="not-recoverable")
    async def functional(messages: Any) -> str:
        calls.append("run")
        return "unexpected"

    server = _Stores().server(
        lambda: functional.build().as_agent(), options=ResponsesServerOptions(resilient_background=True)
    )
    assert "buffered step output" in _failure(await _collect(server))
    assert not calls
    assert not server._scope_locks._entries


@pytest.mark.parametrize("chain", [False, True])
async def test_completed_functional_workflow_starts_fresh_input_not_cached_previous_input(chain: bool) -> None:
    stores = _Stores()
    calls: list[str] = []

    @step
    async def record(text: str) -> str:
        calls.append(text)
        return text

    @workflow(name="fresh-functional")
    async def functional(messages: list[Message]) -> str:
        return await record(messages[0].text)

    conversation = None if chain else "conversation"
    assert (
        _text(
            await _collect(
                stores.server(lambda: functional.build().as_agent()), _context("first", conversation=conversation)
            )
        )
        == "first"
    )
    assert (
        _text(
            await _collect(
                stores.server(lambda: functional.build().as_agent()),
                _context("second", response="two", conversation=conversation),
                previous="response-1" if chain else None,
            )
        )
        == "second"
    )
    assert calls == ["first", "second"]


@pytest.mark.parametrize("kind", ["graph", "functional-string", "functional-bool"])
@pytest.mark.parametrize("chain", [False, True])
async def test_authorized_pending_response_resumes_matching_checkpoint(kind: str, chain: bool) -> None:
    stores = _Stores()
    factory = {
        "graph": _pending_graph,
        "functional-string": lambda: _pending_string.build().as_agent(),
        "functional-bool": lambda: _pending_bool.build().as_agent(),
    }[kind]
    conversation = None if chain else "conversation"
    first = await _collect(stores.server(factory), _context("private", conversation=conversation))
    assert _types(first)[-1] == "response.completed"
    checkpoint = await stores.checkpoints[("alice", conversation or "response-1")].get_latest(
        workflow_name={
            "graph": "pending",
            "functional-string": "functional-pending-string",
            "functional-bool": "functional-pending-bool",
        }[kind]
    )
    assert checkpoint is not None
    request_id = next(iter(checkpoint.pending_request_info_events))
    approval_id = None
    if kind == "functional-bool":
        approval_id = next(iter(stores.approvals["alice"].requests))
        assert stores.approvals["alice"].requests[approval_id].id == request_id
    item = (
        {"type": "mcp_approval_response", "approval_request_id": approval_id, "approve": True}
        if kind == "functional-bool"
        else {"type": "function_call_output", "call_id": request_id, "output": "accepted"}
    )
    resumed = await _collect(
        stores.server(factory),
        _context(response="two", conversation=conversation, items=[item]),
        previous="response-1" if chain else None,
    )
    assert _types(resumed)[-1] == "response.completed", resumed
    assert _text(resumed) == ("private:True" if kind == "functional-bool" else "private:accepted")


@pytest.mark.parametrize("kind", ["text", "wrong-id", "approval-for-string", "cross-user"])
async def test_functional_pending_response_requires_authorized_matching_type_and_user(kind: str) -> None:
    stores = _Stores()

    def factory() -> FunctionalWorkflowAgent:
        return _pending_string.build().as_agent()

    assert _types(await _collect(stores.server(factory)))[-1] == "response.completed"
    checkpoint = await stores.checkpoints[("alice", "conversation")].get_latest(
        workflow_name="functional-pending-string"
    )
    assert checkpoint is not None
    request_id = next(iter(checkpoint.pending_request_info_events))
    if kind == "approval-for-string":
        approval_id = next(iter(stores.approvals["alice"].requests))
        items = [{"type": "mcp_approval_response", "approval_request_id": approval_id, "approve": True}]
    elif kind == "text":
        items = None
    else:
        items = [
            {
                "type": "function_call_output",
                "call_id": "wrong" if kind == "wrong-id" else request_id,
                "output": "stolen",
            }
        ]
    rejected = await _collect(
        stores.server(factory),
        _context("plain text", response="two", items=items),
        user="bob" if kind == "cross-user" else "alice",
    )
    if kind != "cross-user":
        assert "pending functional workflow request" in _failure(rejected)
    assert "hello:stolen" not in _text(rejected)
    approved = await _collect(
        stores.server(factory),
        _context(response="three", items=[{"type": "function_call_output", "call_id": request_id, "output": "owner"}]),
    )
    assert _text(approved) == "hello:owner"


async def test_graph_recovery_without_checkpoint_replays_original_input() -> None:
    stores = _Stores()
    context = _context("original")
    context.is_recovery = True
    server = stores.server(_graph, options=ResponsesServerOptions(resilient_background=True))
    events = await _collect(server, context)
    assert _types(events)[-1] == "response.completed"
    assert _text(events) == "1:original"


@pytest.mark.parametrize("functional", [False, True])
async def test_workflow_final_session_save_failure_closes_request_resources(
    functional: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    stores = _Stores()
    sessions = SessionStore()
    save = AsyncMock(side_effect=[None, RuntimeError("workflow session save failed")])
    monkeypatch.setattr(sessions, "set", save)
    stores.sessions["alice"] = sessions

    class OwnedGraph(WorkflowAgent):
        async def __aenter__(self) -> Self:
            events.append("enter")
            return self

        async def __aexit__(self, *args: Any) -> None:
            await asyncio.sleep(0)
            events.append("exit")

    class OwnedFunctional(FunctionalWorkflowAgent):
        async def __aenter__(self) -> Self:
            events.append("enter")
            return self

        async def __aexit__(self, *args: Any) -> None:
            await asyncio.sleep(0)
            events.append("exit")

    server = stores.server(
        lambda: OwnedFunctional(_functional.build()) if functional else OwnedGraph(_graph().workflow)
    )
    assert "workflow session save failed" in _failure(await _collect(server))
    assert events == ["enter", "exit"]
    assert save.await_count == 2
    assert not server._scope_locks._entries


async def test_resource_exit_failure_replaces_success_with_failure() -> None:
    events: list[str] = []

    class FailingExit(_OwnedAgent):
        async def __aexit__(self, *args: Any) -> None:
            await super().__aexit__(*args)
            raise RuntimeError("resource exit failed")

    server = _Stores().server(lambda: FailingExit(events))
    result = await _collect(server)
    assert _text(result) == "firstsecond"
    assert "resource exit failed" in _failure(result)
    assert events == ["enter", "run", "iterator closed", "exit"]
    assert not server._scope_locks._entries


async def test_cancelling_streaming_task_persists_session_and_closes_iterator(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    emitted = asyncio.Event()
    stores = _Stores()
    sessions = SessionStore()
    save = AsyncMock(wraps=sessions.set)
    monkeypatch.setattr(sessions, "set", save)
    stores.sessions["alice"] = sessions
    server = stores.server(lambda: _OwnedAgent(events, wait=asyncio.Event()))

    async def consume() -> None:
        with _platform():
            stream = cast(AsyncGenerator[Any, None], server._handle_response(_request(), _context(), asyncio.Event()))
            async with aclosing(stream):
                async for event in stream:
                    if isinstance(event, Mapping) and event.get("type") == "response.output_text.delta":
                        emitted.set()

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(emitted.wait(), 2)
    consumer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer
    assert events == ["enter", "run", "iterator closed", "exit"]
    save.assert_awaited_once()
    assert await sessions.get("conversation") is not None
    assert not server._scope_locks._entries


async def test_anyio_cancellation_finishes_blocked_iterator_cleanup_before_owner_exit() -> None:
    events: list[str] = []
    blocked = asyncio.Event()
    scope = CancelScope()

    class TaskGroupAgent(_OwnedAgent):
        async def __aenter__(self) -> Self:
            await super().__aenter__()
            self.group = create_task_group()
            await self.group.__aenter__()
            return self

        async def __aexit__(self, *args: Any) -> None:
            await self.group.__aexit__(*args)
            await super().__aexit__(*args)

        def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
            assert stream

            async def updates() -> AsyncIterator[AgentResponseUpdate]:
                try:
                    events.append("run")
                    yield AgentResponseUpdate(role="assistant", contents=[Content.from_text("first")])
                    blocked.set()
                    await asyncio.Event().wait()
                finally:
                    events.append("cleanup started")
                    await asyncio.sleep(0)
                    events.append("cleanup finished")

            return ResponseStream(updates(), finalizer=AgentResponse.from_updates)

    server = _Stores().server(lambda: TaskGroupAgent(events))

    async def consume() -> None:
        with scope:
            await _collect(server)

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(blocked.wait(), 2)
    scope.cancel()
    await asyncio.wait_for(consumer, 2)
    assert not server._scope_locks._entries
    assert events == ["enter", "run", "cleanup started", "cleanup finished", "exit"]


async def test_checkpoint_preparation_failure_rejects_older_checkpoint_and_fresh_host_retry() -> None:
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
    assert "Executor counter on_checkpoint_save failed" in _failure(await _collect(first))
    storage = stores.checkpoints[("alice", "conversation")]
    checkpoint = await storage.get_latest(workflow_name="checkpoint-preparation")
    assert checkpoint is not None
    assert checkpoint.iteration_count == 0
    assert 0 in snapshots and 1 in snapshots
    session = await stores.sessions["alice"].get("conversation")
    assert session is not None
    assert session.state["_foundry_responses_workflow"]["checkpoint_failed"] is True

    second = stores.server(factory)
    assert "incomplete checkpoint persistence" in _failure(
        await _collect(second, _context("must-not-run", response="two"))
    )
    assert calls == ["hello"]
    assert len(agents) == 2
    assert agents[0] is not agents[1]
    assert agents[0].workflow is not agents[1].workflow
    assert not first._scope_locks._entries
    assert not second._scope_locks._entries


@pytest.mark.parametrize("functional", [False, True])
async def test_checkpoint_save_failure_does_not_report_success_and_closes_owner(
    functional: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    storage = InMemoryCheckpointStorage()
    save = AsyncMock(side_effect=RuntimeError("checkpoint save failed"))
    monkeypatch.setattr(storage, "save", save)
    stores = _Stores()
    stores.checkpoints[("alice", "conversation")] = storage

    class OwnedGraph(WorkflowAgent):
        async def __aenter__(self) -> Self:
            events.append("enter")
            return self

        async def __aexit__(self, *args: Any) -> None:
            events.append("exit")

    class OwnedFunctional(FunctionalWorkflowAgent):
        async def __aenter__(self) -> Self:
            events.append("enter")
            return self

        async def __aexit__(self, *args: Any) -> None:
            events.append("exit")

    server = stores.server(
        lambda: OwnedFunctional(_functional.build()) if functional else OwnedGraph(_graph().workflow)
    )
    result = await _collect(server)
    assert events == ["enter", "exit"]
    assert save.await_count > 0
    assert not server._scope_locks._entries
    assert "checkpoint save failed" in _failure(result)


async def test_interrupted_functional_step_does_not_restart_with_new_input() -> None:
    stores = _Stores()
    calls: list[str] = []

    @step
    async def saved() -> str:
        return "saved"

    @workflow(name="interrupted-functional")
    async def interrupted(messages: list[Message]) -> str:
        calls.append(messages[0].text)
        await saved()
        raise RuntimeError("failed after step")

    def factory() -> FunctionalWorkflowAgent:
        return interrupted.build().as_agent()

    assert "failed after step" in _failure(await _collect(stores.server(factory)))
    assert "interrupted functional workflow" in _failure(
        await _collect(stores.server(factory), _context("next", response="two"))
    )
    assert calls == ["hello"]


@pytest.mark.parametrize("functional", [False, True])
async def test_cross_user_previous_response_cannot_resume_another_users_pending_request(functional: bool) -> None:
    stores = _Stores()
    factory = (lambda: _pending_string.build().as_agent()) if functional else _pending_graph
    first = await _collect(stores.server(factory), _context("alice-private", conversation=None))
    assert _types(first)[-1] == "response.completed"
    checkpoint = await stores.checkpoints[("alice", "response-1")].get_latest(
        workflow_name="functional-pending-string" if functional else "pending"
    )
    assert checkpoint is not None
    request_id = next(iter(checkpoint.pending_request_info_events))
    result = {"type": "function_call_output", "call_id": request_id, "output": "approved"}
    rejected = await _collect(
        stores.server(factory),
        _context(response="two", conversation=None, items=[result]),
        user="bob",
        previous="response-1",
    )
    assert "checkpoint" in _failure(rejected)
    approved = await _collect(
        stores.server(factory), _context(response="three", conversation=None, items=[result]), previous="response-1"
    )
    assert _text(approved) == "alice-private:approved"


class _RecoveryStart(Executor):
    @handler
    async def start(self, messages: list[Message], ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output(f"first:{messages[0].text}")
        await ctx.send_message(messages[0].text)


class _RecoveryEnd(Executor):
    @handler
    async def end(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(f"last:{text}")


def _recovery_graph() -> WorkflowAgent:
    start = _RecoveryStart(id="start")
    end = _RecoveryEnd(id="end")
    return WorkflowBuilder(name="recovery", start_executor=start).add_edge(start, end).build().as_agent()


@pytest.mark.parametrize("saved_input", [False, True])
async def test_graph_recovery_preserves_explicit_outer_history_for_continuation(saved_input: bool) -> None:
    stores = _Stores()
    transcripts: list[list[str]] = []
    agents: list[WorkflowAgent] = []
    original = Message("user", ["original"])

    class Start(Executor):
        @handler
        async def start(self, messages: list[Message], ctx: WorkflowContext[str]) -> None:
            transcripts.append([message.text for message in messages])
            await ctx.send_message(messages[-1].text)

    def factory() -> WorkflowAgent:
        start = Start(id="start")
        end = _RecoveryEnd(id="end")
        agent = (
            WorkflowBuilder(name="recovery-history", start_executor=start)
            .add_edge(start, end)
            .build()
            .as_agent(context_providers=[InMemoryHistoryProvider(source_id="outer-history")])
        )
        agents.append(agent)
        return agent

    interrupted = factory()
    storage = InMemoryCheckpointStorage()
    iterator = interrupted.workflow.run([original], stream=True, checkpoint_storage=storage).__aiter__()
    try:
        async for event in iterator:
            if event.type == "superstep_completed":
                break
    finally:
        await close_run_iterator(iterator)
    checkpoint = await storage.get_latest(workflow_name="recovery-history")
    assert checkpoint is not None
    assert checkpoint.iteration_count == 1
    assert transcripts == [["original"]]
    stores.checkpoints[("alice", "conversation")] = storage
    session = AgentSession()
    session.state["_foundry_responses_workflow"] = {
        "name": "recovery-history",
        "kind": "graph",
        "completed": False,
    }
    if saved_input:
        await InMemoryHistoryProvider(source_id="outer-history").save_messages(
            session.session_id, [original], state=session.state.setdefault("outer-history", {})
        )
    stores.sessions["alice"] = SessionStore()
    await stores.sessions["alice"].set("conversation", session)

    context = _context("original")
    context.is_recovery = True
    recovered = await _collect(
        stores.server(factory, options=ResponsesServerOptions(resilient_background=True)), context
    )
    assert _types(recovered)[-1] == "response.completed"
    assert _text(recovered) == "last:original"
    assert transcripts == [["original"]]
    recovered_session = await stores.sessions["alice"].get("conversation")
    assert recovered_session is not None
    history = await InMemoryHistoryProvider(source_id="outer-history").get_messages(
        recovered_session.session_id, state=recovered_session.state.get("outer-history")
    )
    assert [(message.role, message.text) for message in history] == [
        ("user", "original"),
        ("assistant", "last:original"),
    ]

    continued = await _collect(stores.server(factory), _context("next", response="two"))
    assert _types(continued)[-1] == "response.completed"
    assert _text(continued) == "last:next"
    assert transcripts == [["original"], ["original", "last:original", "next"]]
    continued_session = await stores.sessions["alice"].get("conversation")
    assert continued_session is not None
    history = await InMemoryHistoryProvider(source_id="outer-history").get_messages(
        continued_session.session_id, state=continued_session.state.get("outer-history")
    )
    assert [message.text for message in history] == ["original", "last:original", "next", "last:next"]
    assert len({id(agent.workflow) for agent in agents}) == 3


@pytest.mark.parametrize("snapshot_kind", ["latest", "empty", "partial"])
async def test_graph_recovery_selects_latest_or_response_paired_checkpoint(
    snapshot_kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    stores = _Stores()
    options = ResponsesServerOptions(resilient_background=True)
    server = stores.server(_recovery_graph, options=options)
    snapshots: list[Any] = []
    with _platform():
        async for event in server._handle_response(_request(), _context("original"), asyncio.Event()):
            if isinstance(event, ResponseCheckpointEvent):
                snapshots.append(copy.deepcopy(event.response))
    assert snapshots
    storage = stores.checkpoints[("alice", "conversation")]
    latest = await storage.get_latest(workflow_name="recovery")
    assert latest is not None
    load = AsyncMock(wraps=storage.load)
    monkeypatch.setattr(storage, "load", load)
    context = _context("must-not-replay")
    context.is_recovery = True
    if snapshot_kind != "latest":
        context.persisted_response = (
            next(snapshot for snapshot in snapshots if snapshot.get("output"))
            if snapshot_kind == "partial"
            else snapshots[0]
        )
    events = await _collect(stores.server(_recovery_graph, options=options), context)
    assert _types(events)[-1] == "response.completed", events
    assert "must-not-replay" not in _text(events)
    load.assert_awaited_once()
    if snapshot_kind != "latest":
        assert load.await_args is not None
        assert load.await_args.args[0] != latest.checkpoint_id
        assert "original" in _text(events)
        if snapshot_kind == "partial":
            assert _text(events) == "last:original"
            final_text = "".join(
                content.get("text", "")
                for item in events[-1]["response"]["output"]
                for content in item.get("content", [])
            )
            assert final_text == "first:originallast:original"
    else:
        load.assert_awaited_once_with(latest.checkpoint_id)
