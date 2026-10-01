# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from dataclasses import replace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    Agent,
    AgentExecutor,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Executor,
    InMemoryCheckpointStorage,
    MCPStreamableHTTPTool,
    Message,
    RawAgent,
    ResponseStream,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowInvocationKwargs,
    handler,
    response_handler,
    tool,
)
from agent_framework._workflows._const import RESOLVED_WORKFLOW_RUN_KWARGS_KEY
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.ai.agentserver.core.storage import FoundryStorageConflictError, FoundryStoragePreconditionError

from agent_framework_foundry_hosting import CheckpointStoreProvider, FoundryRequestScope, WorkflowTurn
from agent_framework_foundry_hosting._workflow_source import WorkflowResolver, prepare_workflow_kwargs
from agent_framework_foundry_hosting._workflow_state import (
    FoundryWorkflowBindingStore,
    HostedWorkflowRun,
    WorkflowConflictError,
    WorkflowHead,
)


def _scope(*, user: str = "user", sandbox: str = "sandbox", call: str = "call") -> FoundryRequestScope:
    return FoundryRequestScope(sandbox, user, call, False)


def _config() -> AgentConfig:
    return AgentConfig(
        agent_name="",
        agent_version="",
        agent_id="",
        is_hosted=False,
        project_endpoint="",
        project_id="",
        session_id="",
        port=8088,
        appinsights_connection_string="",
        otlp_endpoint="",
        sse_keepalive_interval=0,
    )


class _Counter(Executor):
    def __init__(self, id: str = "counter") -> None:
        super().__init__(id)

    @handler
    async def start(self, message: int, ctx: WorkflowContext[int, int]) -> None:
        count = ctx.get_state("count", 0) + message
        ctx.set_state("count", count)
        await ctx.yield_output(count)


class _Review(Executor):
    def __init__(self) -> None:
        super().__init__("review")

    @handler
    async def start(self, message: str, ctx: WorkflowContext[str, str]) -> None:
        await ctx.request_info(message, bool, request_id="first")
        await ctx.request_info(message, bool, request_id="second")

    @response_handler
    async def decide(self, request: str, response: bool, ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output(f"{request}:{response}")


class _Approval(Executor):
    def __init__(self) -> None:
        super().__init__("approval")

    @handler
    async def start(self, message: str, ctx: WorkflowContext[str, str]) -> None:
        function = Content.from_function_call("call-1", "delete", arguments={"path": message}, id="approval-1")
        await ctx.request_info(
            Content.from_function_approval_request("approval-1", function), Content, request_id="approval-1"
        )

    @response_handler
    async def decide(self, request: Content, response: Content, ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output("approved" if response.approved else "rejected")


class _Loop(Executor):
    def __init__(self, calls: list[str] | None = None) -> None:
        super().__init__("loop")
        self.calls = calls

    @handler
    async def step(self, message: int, ctx: WorkflowContext[int, int]) -> None:
        if self.calls is not None:
            kwargs = ctx.get_state(RESOLVED_WORKFLOW_RUN_KWARGS_KEY)
            self.calls.append(kwargs["client_kwargs"]["global_kwargs"]["additional_function_arguments"]["call_id"])
        await ctx.yield_output(message)
        if message:
            await ctx.send_message(message - 1)


class _RegistryExecutor(Executor):
    def __init__(self, agent: Agent[Any]) -> None:
        super().__init__("registry")
        self._agents = {"registered": agent}

    @handler
    async def start(self, message: str, ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output(message)


def _workflow(executor: Executor | None = None, *, name: str = "native-test") -> Workflow:
    executor = executor or _Counter()
    builder = WorkflowBuilder(name=name, start_executor=executor)
    if isinstance(executor, _Loop):
        builder.add_edge(executor, executor)
    return builder.build()


async def _prepare(
    response_id: str,
    *,
    workflow: Workflow | None = None,
    scope: FoundryRequestScope | None = None,
    **kwargs: Any,
) -> HostedWorkflowRun:
    scope = scope or _scope()
    return await HostedWorkflowRun.prepare(
        workflow or _workflow(),
        scope=scope,
        response_id=response_id,
        config=_config(),
        platform_context=FoundryAgentRequestContext(
            session_id=scope.session_id,
            user_id=scope.user_id,
            call_id=scope.call_id,
        ),
        checkpoint_store_provider=CheckpointStoreProvider(),
        **kwargs,
    )


async def _finish(run: HostedWorkflowRun, turn: WorkflowTurn[Any]) -> list[Any]:
    turn = run.validate_turn(turn)
    await run.claim()
    outputs = [event.data async for event in run.events(turn) if event.type == "output"]
    await run.stage({"output": outputs})
    await run.commit()
    return outputs


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"input": "x", "responses": {"r": True}},
        {"responses": {}},
        {"responses": {1: "x"}},
        {"input": "x", "stream": 1},
    ],
)
def test_turn_rejects_invalid_shape(values: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        WorkflowTurn(**values)


async def test_resolver_requires_fresh_built_graphs_and_resources() -> None:
    shared = _workflow()
    resolver = WorkflowResolver(lambda request: shared)
    assert await resolver.resolve(object()) is shared
    with pytest.raises(RuntimeError, match="cannot share"):
        await resolver.resolve(object())

    executor = _Counter()
    resolver = WorkflowResolver(lambda request: _workflow(executor))
    first = await resolver.resolve(object())
    with pytest.raises(RuntimeError, match="cannot share"):
        await resolver.resolve(object())
    assert first.get_start_executor() is executor

    def zero_argument_factory() -> Workflow:
        return _workflow()

    with pytest.raises(TypeError, match="one request"):
        WorkflowResolver(cast(Any, zero_argument_factory))

    def builder_factory(request: object) -> Any:
        return WorkflowBuilder(start_executor=_Counter())

    resolver = WorkflowResolver(builder_factory)
    with pytest.raises(TypeError, match="built Workflow"):
        await resolver.resolve(object())
    with pytest.raises(RuntimeError, match="without a store"):
        await WorkflowResolver(
            WorkflowBuilder(start_executor=_Counter(), checkpoint_storage=InMemoryCheckpointStorage()).build()
        ).resolve(object())


async def test_request_aware_async_factory() -> None:
    requests: list[object] = []

    async def create(request: object) -> Workflow:
        requests.append(request)
        return _workflow()

    resolver = WorkflowResolver(create)
    one, two = object(), object()
    first, second = await resolver.resolve(one), await resolver.resolve(two)
    assert first is not second
    assert first.get_start_executor() is not second.get_start_executor()
    assert requests == [one, two]


@pytest.mark.parametrize("mcp", [False, True])
async def test_resolver_rejects_reused_local_and_mcp_tools(mcp: bool) -> None:
    class _UnusedClient(BaseChatClient):
        async def _inner_get_response(self, **kwargs: Any) -> Any:
            raise AssertionError("Ownership validation must not call the model.")

    @tool
    def local_tool(value: str) -> str:
        """Return a value without accessing external services."""
        return value

    shared = MCPStreamableHTTPTool(name="shared", url="https://unused.example.test/mcp") if mcp else local_tool

    def create(request: object) -> Workflow:
        agent = Agent(client=_UnusedClient(), name="agent", tools=[shared])
        return _workflow(AgentExecutor(agent, id="agent"))

    resolver = WorkflowResolver(create)
    first = await resolver.resolve(object())
    with pytest.raises(RuntimeError, match="cannot share"):
        await resolver.resolve(object())
    assert first.get_start_executor().id == "agent"


async def test_resolver_rejects_reused_registry_backed_agent_resources() -> None:
    class _UnusedClient(BaseChatClient):
        async def _inner_get_response(self, **kwargs: Any) -> Any:
            raise AssertionError("Ownership validation must not call the model.")

    shared = Agent(client=_UnusedClient(), name="registered")
    resolver = WorkflowResolver(lambda request: _workflow(_RegistryExecutor(shared)))

    await resolver.resolve(object())
    with pytest.raises(RuntimeError, match="cannot share"):
        await resolver.resolve(object())


@pytest.mark.parametrize("raw", [False, True])
async def test_shared_real_agent_options_use_the_correct_existing_boundary(raw: bool) -> None:
    calls: list[dict[str, Any]] = []
    agents: list[RawAgent[Any]] = []

    class RecordingClient(BaseChatClient):
        STORES_BY_DEFAULT = True

        def _inner_get_response(
            self,
            *,
            messages: Sequence[Message],
            stream: bool,
            options: Mapping[str, Any],
            **kwargs: Any,
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            calls.append({"options": dict(options), "kwargs": kwargs})

            async def updates() -> AsyncIterator[ChatResponseUpdate]:
                yield ChatResponseUpdate(role="assistant", contents=[Content.from_text("safe")])

            return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

    def create(request: object) -> Workflow:
        agent = (
            RawAgent(
                client=RecordingClient(),
                name="model",
                default_options=cast(ChatOptions[Any], {"store": False, "temperature": 0.6}),
            )
            if raw
            else Agent(
                client=RecordingClient(),
                name="model",
                default_options=cast(ChatOptions[Any], {"store": True, "temperature": 0.2}),
            )
        )
        agents.append(agent)
        return _workflow(AgentExecutor(agent, id="model"))

    resolver = WorkflowResolver(create)
    workflow = await resolver.resolve(object())
    run = await _prepare("model-turn", workflow=workflow, fresh_factory=resolver.is_factory)
    turn = run.validate_turn(WorkflowTurn(input=[Message("user", "hello")]))
    clients, functions = prepare_workflow_kwargs(
        workflow,
        turn,
        run.scope,
        options={"temperature": 0.6},
        fresh_factory=resolver.is_factory,
    )
    await run.claim()
    events = [event async for event in run.events(turn, client_kwargs=clients, function_invocation_kwargs=functions)]
    assert any(event.type == "output" for event in events)
    await run.stage({"output": ["safe"]})
    await run.commit()
    assert calls[0]["options"]["store"] is False
    assert calls[0]["options"]["temperature"] == 0.6
    assert "options" not in calls[0]["kwargs"]
    assert agents[0].default_options["temperature"] == (0.6 if raw else 0.2)
    if raw:
        with pytest.raises(ValueError, match="materialized"):
            prepare_workflow_kwargs(
                _workflow(
                    AgentExecutor(
                        RawAgent(
                            client=RecordingClient(),
                            name="model",
                            default_options=cast(ChatOptions[Any], {"store": False, "temperature": 0.2}),
                        ),
                        id="model",
                    )
                ),
                WorkflowTurn(input=[Message("user", "hello")]),
                run.scope,
                options={"temperature": 0.6},
                fresh_factory=True,
            )


async def test_exact_pairs_restore_state_and_reject_old_lineage() -> None:
    first = await _prepare("one")
    assert await _finish(first, WorkflowTurn(input=2)) == [2]
    first_checkpoint = first.checkpoint_id
    second = await _prepare("two", previous_response_id="one")
    assert second.checkpoint_id == first_checkpoint
    assert await _finish(second, WorkflowTurn(input=3)) == [5]
    assert second.checkpoint_id != first_checkpoint
    with pytest.raises(WorkflowConflictError, match="stale or forked"):
        await _prepare("fork", previous_response_id="one")
    store = FoundryWorkflowBindingStore(_scope())
    old, _ = await store.get_response("one")
    assert old is not None and old.binding.checkpoint_id == first_checkpoint
    recovered = await _prepare("one", recovery=True)
    assert recovered.already_completed
    assert recovered.snapshot == {"output": [2]}
    recovered.validate_turn(WorkflowTurn(input=2))
    await recovered.claim()
    assert [event async for event in recovered.events(WorkflowTurn(input=2))] == []
    await recovered.commit()
    head, _ = await store.get_head("one", None)
    assert head is not None and head.binding == second.binding


@pytest.mark.parametrize("scope", [_scope(user="other"), _scope(sandbox="other")])
async def test_checkpoint_and_reply_scope_isolation(scope: FoundryRequestScope) -> None:
    first = await _prepare("one", workflow=_workflow(_Review()))
    await _finish(first, WorkflowTurn(input="review"))
    with pytest.raises(ValueError, match="trusted scope"):
        await _prepare("two", workflow=_workflow(_Review()), scope=scope, previous_response_id="one")
    with pytest.raises(RuntimeError, match="No acknowledged"):
        await _prepare("one", workflow=_workflow(_Review()), scope=scope, recovery=True)


@pytest.mark.parametrize("changed", [_workflow(_Counter("changed")), _workflow(name="changed")])
async def test_graph_and_name_mismatch(changed: Workflow) -> None:
    first = await _prepare("one", lineage_id="invocations")
    await _finish(first, WorkflowTurn(input=1))
    with pytest.raises(WorkflowConflictError, match="incompatible"):
        await _prepare("two", workflow=changed, lineage_id="invocations")


async def test_partial_and_invalid_replies_do_not_claim_or_consume() -> None:
    first = await _prepare("one", workflow=_workflow(_Review()))
    await _finish(first, WorkflowTurn(input="review"))
    second = await _prepare("two", workflow=_workflow(_Review()), previous_response_id="one")
    for replies in ({"first": True}, {"first": True, "forged": False}, {"first": {}, "second": True}):
        with pytest.raises(ValueError):
            second.validate_turn(WorkflowTurn(responses=replies))
        head, _ = await second.store.get_head("one", None)
        assert head is not None and head.response_id is None
    assert await _finish(second, WorkflowTurn(responses={"first": True, "second": False})) == [
        "review:True",
        "review:False",
    ]
    with pytest.raises(WorkflowConflictError, match="stale or forked"):
        await _prepare("replay", workflow=_workflow(_Review()), previous_response_id="one")


async def test_forged_embedded_approval_is_rejected_before_consumption() -> None:
    first = await _prepare("one", workflow=_workflow(_Approval()))
    await _finish(first, WorkflowTurn(input="/safe"))
    second = await _prepare("two", workflow=_workflow(_Approval()), previous_response_id="one")
    pending = second.pending_requests["approval-1"].data
    forged = Content.from_function_call("call-1", "delete", arguments={"path": "/forged"}, id="approval-1")
    with pytest.raises(ValueError, match="exact pending"):
        second.validate_turn(
            WorkflowTurn(
                responses={
                    "approval-1": Content.from_function_approval_response(True, "approval-1", forged),
                }
            )
        )
    decision = pending.to_function_approval_response(True)
    assert await _finish(second, WorkflowTurn(responses={"approval-1": decision})) == ["approved"]


async def test_racing_claims_consume_authority_once() -> None:
    first = await _prepare("one")
    await _finish(first, WorkflowTurn(input=1))
    left = await _prepare("left", previous_response_id="one")
    right = await _prepare("right", previous_response_id="one")
    left.validate_turn(WorkflowTurn(input=1))
    right.validate_turn(WorkflowTurn(input=1))
    await left.claim()
    with pytest.raises(RuntimeError, match="Another request"):
        await right.claim()
    await left.abort()
    with pytest.raises(RuntimeError, match="fresh workflow lineage"):
        await _prepare("retry", previous_response_id="one")


@pytest.mark.parametrize("error", [FoundryStorageConflictError, FoundryStoragePreconditionError])
async def test_both_sdk_cas_errors_are_visible_and_private(error: type[Exception]) -> None:
    storage = MagicMock()
    storage.__aenter__ = AsyncMock(return_value=storage)
    storage.__aexit__ = AsyncMock(return_value=None)
    storage.create_item = AsyncMock(side_effect=error("private-token-and-checkpoint"))
    store = FoundryWorkflowBindingStore(_scope())
    run = await _prepare("one")
    run.validate_turn(WorkflowTurn(input=1))
    with (
        patch.object(store, "_get_store", AsyncMock(return_value=storage)),
        pytest.raises(RuntimeError, match="Another request") as raised,
    ):
        await store.save_head(WorkflowHead("one", None), expected_etag=None)
    assert "private-token" not in str(raised.value)


async def test_store_false_writes_nothing_and_rejects_resumption() -> None:
    with patch("agent_framework_foundry_hosting._workflow_state.FoundryStateStore.get_or_create") as get_store:
        run = await _prepare("one", stored=False)
        assert await _finish(run, WorkflowTurn(input=3)) == [3]
        get_store.assert_not_called()
    with pytest.raises(ValueError, match="one-shot"):
        await _prepare("two", stored=False, previous_response_id="one")
    with patch("agent_framework_foundry_hosting._workflow_state.FoundryStateStore.get_or_create") as get_store:
        run = await _prepare("pause", workflow=_workflow(_Review()), stored=False)
        turn = run.validate_turn(WorkflowTurn(input="review"))
        await run.claim()
        with pytest.raises(ValueError, match="store=true"):
            async for event in run.events(turn):
                assert event.type != "request_info"
        get_store.assert_not_called()


async def test_close_does_not_commit_and_abort_blocks_authority() -> None:
    run = await _prepare("one", workflow=_workflow(_Loop()))
    turn = run.validate_turn(WorkflowTurn(input=2))
    await run.claim()
    events = run.events(turn)
    async for event in events:
        if event.type == "superstep_completed":
            await run.stage({"output": [2]})
            break
    await events.aclose()
    with pytest.raises(RuntimeError, match="finalization"):
        await run.commit()
    await run.abort()
    with pytest.raises(RuntimeError, match="fresh workflow lineage"):
        await _prepare("one", workflow=_workflow(_Loop()), recovery=True)


async def test_recovery_uses_exact_output_pair_not_newer_core_checkpoint() -> None:
    run = await _prepare("one", workflow=_workflow(_Loop()))
    turn = run.validate_turn(WorkflowTurn(input=2))
    await run.claim()
    events = run.events(turn)
    async for event in events:
        if event.type == "superstep_completed":
            await run.stage({"output": [2]})
            break
    paired = run.binding.checkpoint_id
    async for event in events:
        if event.type == "superstep_completed":
            break
    assert run.checkpoint_id != paired
    await events.aclose()
    recovered = await _prepare("one", workflow=_workflow(_Loop()), recovery=True)
    assert recovered.checkpoint_id == paired
    assert recovered.snapshot == {"output": [2]}
    turn = recovered.validate_turn(WorkflowTurn(input=2))
    await recovered.claim()
    outputs = [event.data async for event in recovered.events(turn) if event.type == "output"]
    assert outputs == [1, 0]
    await recovered.stage({"output": [2, *outputs]})
    await recovered.commit()


async def test_recovery_refreshes_private_current_call_kwargs() -> None:
    calls: list[str] = []
    run = await _prepare("one", workflow=_workflow(_Loop(calls)), scope=_scope(call="old-call"))
    turn = run.validate_turn(WorkflowTurn(input=1))
    await run.claim()
    events = run.events(turn)
    async for event in events:
        if event.type == "superstep_completed":
            await run.stage({"output": [1]})
            break
    await events.aclose()
    recovered = await _prepare("one", workflow=_workflow(_Loop(calls)), scope=_scope(call="new-call"), recovery=True)
    await _finish(recovered, recovered.recovery_turn())
    assert calls == ["old-call", "new-call"]


async def test_checkpoint_mutation_and_foreign_pairing_fail() -> None:
    run = await _prepare("one")
    await _finish(run, WorkflowTurn(input=1))
    assert run._storage is not None and run.checkpoint_id is not None
    checkpoint = await run._storage.storage.load(run.checkpoint_id)
    await run._storage.storage.save(replace(checkpoint, state={**checkpoint.state, "forged": True}))
    with pytest.raises(ValueError, match="does not match"):
        await _prepare("two", previous_response_id="one")
    fresh = await _prepare("fresh")
    fresh.validate_turn(WorkflowTurn(input=1))
    await fresh.claim()
    with pytest.raises(ValueError, match="exact workflow turn"):
        await fresh.stage({"output": []}, checkpoint_id=run.checkpoint_id)
    await fresh.abort()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"session": "forged"},
        {"additional_function_arguments": {"call_id": "forged"}},
        {"options": {"extra_body": {"store": True}}},
        WorkflowInvocationKwargs(executor_kwargs={"counter": {"options": {"instructions": "forged"}}}),
    ],
)
def test_client_kwargs_reject_controls_in_all_namespaces(kwargs: Any) -> None:
    with pytest.raises(ValueError, match="controls"):
        prepare_workflow_kwargs(_workflow(), WorkflowTurn(input=1, client_kwargs=kwargs), _scope())


def test_tool_context_stays_separate_from_model_options() -> None:
    clients, functions = prepare_workflow_kwargs(
        _workflow(),
        WorkflowTurn(input=1, function_invocation_kwargs={"ticket": "application"}),
        _scope(),
        options={"temperature": 0.5},
    )
    assert functions.global_kwargs == {"ticket": "application"}
    assert clients.global_kwargs["additional_function_arguments"] == {
        "session_id": "sandbox",
        "user_id": "user",
        "call_id": "call",
    }


async def test_missing_pair_cannot_replay_original_input() -> None:
    run = await _prepare("one")
    run.validate_turn(WorkflowTurn(input=1))
    await run.claim()
    with pytest.raises(RuntimeError, match="No acknowledged"):
        await _prepare("one", recovery=True)
    await run.abort()
