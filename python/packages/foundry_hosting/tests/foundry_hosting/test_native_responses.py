# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
import logging
import warnings
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, MutableMapping, Sequence
from typing import Any, cast
from unittest.mock import patch

import httpx
import pytest
from agent_framework import (
    Agent,
    AgentExecutor,
    AgentResponse,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    ContinuationToken,
    Executor,
    Message,
    RawAgent,
    ResponseStream,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)
from agent_framework._workflows._agent_utils import prepare_executor_run_kwargs
from agent_framework._workflows._const import RESOLVED_WORKFLOW_RUN_KWARGS_KEY, WORKFLOW_RUN_KWARGS_KEY
from azure.ai.agentserver.responses import FileResponseStore, InMemoryResponseProvider, ResponsesServerOptions
from azure.ai.agentserver.responses._id_generator import IdGenerator
from pydantic import BaseModel

from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    FoundryRequestScope,
    HostedResponseRequest,
    ResponsesHostServer,
    WorkflowTurn,
)
from agent_framework_foundry_hosting._workflow_state import FoundryWorkflowBindingStore, HostedWorkflowRun


class _Ticket(BaseModel):
    text: str
    increment: int = 1


class _Summary(BaseModel):
    text: str
    count: int


class _PrivateToken(ContinuationToken):
    token: str


class _RecordingClient(BaseChatClient):
    STORES_BY_DEFAULT = True

    def __init__(self, calls: list[dict[str, Any]], lifecycle: list[str], *, violates_store: bool = False) -> None:
        super().__init__()
        self.calls = calls
        self.lifecycle = lifecycle
        self.violates_store = violates_store

    async def __aenter__(self) -> _RecordingClient:
        self.lifecycle.append("open")
        return self

    async def __aexit__(self, *args: object) -> None:
        self.lifecycle.append("close")

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        self.calls.append({"messages": list(messages), "options": dict(options), "kwargs": kwargs})

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(
                role="assistant",
                contents=[Content.from_text("safe")],
                response_id="private-provider-id",
                conversation_id="private-service-id" if self.violates_store else None,
            )

        if stream:
            return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

        async def response() -> ChatResponse:
            return ChatResponse(messages=[Message("assistant", "safe")])

        return response()


class _TypedCounter(Executor):
    def __init__(self) -> None:
        super().__init__("counter")

    @handler
    async def count(self, message: _Ticket, ctx: WorkflowContext[str, _Summary]) -> None:
        count = ctx.get_state("count", 0) + message.increment
        ctx.set_state("count", count)
        await ctx.yield_output(_Summary(text=message.text, count=count))


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


class _Approvals(Executor):
    def __init__(self) -> None:
        super().__init__("approvals")

    @handler
    async def start(self, message: str, ctx: WorkflowContext[str, str]) -> None:
        for request_id in ("first", "second"):
            call = Content.from_function_call(
                f"call-{request_id}",
                "delete",
                arguments={"path": message},
                id=request_id,
            )
            await ctx.request_info(
                Content.from_function_approval_request(request_id, call), Content, request_id=request_id
            )

    @response_handler
    async def decide(self, request: Content, response: Content, ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output(f"{request.id}:{response.approved}")


class _Progress(Executor):
    def __init__(self, started: asyncio.Event, release: asyncio.Event, stopped: asyncio.Event) -> None:
        super().__init__("progress")
        self.started = started
        self.release = release
        self.stopped = stopped

    @handler
    async def step(self, message: int, ctx: WorkflowContext[int, AgentResponse]) -> None:
        if message == 1:
            self.started.set()
            try:
                await self.release.wait()
            finally:
                self.stopped.set()
        await ctx.yield_output(
            AgentResponse(
                messages=[Message("assistant", str(message))],
                usage_details={"input_token_count": 1, "output_token_count": 1, "total_token_count": 2},
            )
        )
        if message:
            await ctx.send_message(message - 1)


class _RegistryExecutor(Executor):
    def __init__(self, agent: Agent[Any]) -> None:
        super().__init__("registered_action")
        self._agents = {"registered": agent}

    @handler
    async def run_registered(self, message: str, ctx: WorkflowContext[str, Message]) -> None:
        run_kwargs = prepare_executor_run_kwargs(
            self.id,
            ctx.get_state(WORKFLOW_RUN_KWARGS_KEY, {}),
            ctx.get_state(RESOLVED_WORKFLOW_RUN_KWARGS_KEY),
        )
        options = run_kwargs.pop("options", None)
        result = await self._agents["registered"].run(message, options=options, **run_kwargs)
        await ctx.yield_output(result.messages[-1])


def _progress_factory(
    started: asyncio.Event,
    release: asyncio.Event,
    stopped: asyncio.Event,
) -> Callable[[HostedResponseRequest], Workflow]:
    def create(request: HostedResponseRequest) -> Workflow:
        progress = _Progress(started, release, stopped)
        return WorkflowBuilder(name="progress", start_executor=progress).add_edge(progress, progress).build()

    return create


async def _parse_count(request: HostedResponseRequest) -> WorkflowTurn[int]:
    return WorkflowTurn(input=int(await request.get_input_text() or ""))


async def _poll(client: httpx.AsyncClient, response_id: str) -> dict[str, Any]:
    for _ in range(150):
        response = await client.get(f"/responses/{response_id}")
        if response.status_code == 200 and response.json()["status"] not in ("queued", "in_progress"):
            return response.json()
        await asyncio.sleep(0.01)
    pytest.fail("The bounded local background response did not reach a terminal state.")


def _build(executor: Executor | None = None, *, name: str = "native-responses") -> Workflow:
    return WorkflowBuilder(name=name, start_executor=executor or _TypedCounter()).build()


async def _parse(request: HostedResponseRequest) -> WorkflowTurn[Any]:
    items = await request.get_input_items()
    if any(item.get("type") in ("function_call_output", "mcp_approval_response") for item in items):
        return WorkflowTurn(responses=await request.get_workflow_responses())
    return WorkflowTurn(input=_Ticket.model_validate_json(await request.get_input_text() or ""))


async def _parse_text(request: HostedResponseRequest) -> WorkflowTurn[Any]:
    items = await request.get_input_items()
    if any(item.get("type") in ("function_call_output", "mcp_approval_response") for item in items):
        return WorkflowTurn(responses=await request.get_workflow_responses())
    return WorkflowTurn(input=await request.get_input_text())


def _server(
    source: Any = None,
    *,
    parser: Callable[..., Any] = _parse,
    response_store: Any = None,
    **kwargs: Any,
) -> ResponsesHostServer:
    return ResponsesHostServer(
        workflow=source or (lambda request: _build()),
        parse_response=parser,
        response_store=response_store or InMemoryResponseProvider(),
        checkpoint_store_provider=CheckpointStoreProvider(
            allowed_checkpoint_types=[f"{_Ticket.__module__}:{_Ticket.__qualname__}"],
        ),
        configure_observability=None,
        **kwargs,
    )


async def _post(
    server: ResponsesHostServer,
    input: Any,
    *,
    sandbox: str = "sandbox",
    user: str = "user",
    call: str = "call",
    **kwargs: Any,
) -> dict[str, Any]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
        response = await client.post(
            "/responses",
            params={"agent_session_id": sandbox},
            headers={"x-agent-user-id": user, "x-agent-foundry-call-id": call},
            json={"input": input, "agent_session_id": sandbox, **kwargs},
        )
    assert response.status_code == 200, response.text
    return response.json()


def _texts(response: dict[str, Any]) -> list[str]:
    return [
        content["text"]
        for item in response["output"]
        if item["type"] == "message"
        for content in item["content"]
        if content["type"] == "output_text"
    ]


async def test_typed_native_turns_use_fresh_graphs_and_exact_state() -> None:
    graphs: list[Workflow] = []
    scopes: list[FoundryRequestScope] = []

    def build(request: HostedResponseRequest) -> Workflow:
        scopes.append(request.scope)
        graph = _build()
        graphs.append(graph)
        return graph

    provider = InMemoryResponseProvider()
    server = _server(build, response_store=provider)
    first = await _post(server, '{"text":"one","increment":2}')
    assert first["status"] == "completed", first
    assert first["output"][0]["type"] == "structured_outputs"
    assert first["output"][0]["output"] == {"text": "one", "count": 2}
    second = await _post(server, '{"text":"two","increment":3}', previous_response_id=first["id"], call="call-two")
    assert second["status"] == "completed", second
    assert second["output"][0]["output"] == {"text": "two", "count": 5}
    assert graphs[0] is not graphs[1]
    assert graphs[0].get_start_executor() is not graphs[1].get_start_executor()
    assert scopes[0].session_id == scopes[1].session_id == "sandbox"
    assert scopes[0].call_id != scopes[1].call_id
    restarted = _server(response_store=provider)
    third = await _post(restarted, '{"text":"three"}', previous_response_id=second["id"])
    assert third["status"] == "completed", third
    assert third["output"][0]["output"]["count"] == 6
    stale = await _post(server, '{"text":"fork"}', previous_response_id=first["id"])
    assert stale["status"] == "failed"
    store = FoundryWorkflowBindingStore(scopes[0])
    original, _ = await store.get_response(first["id"])
    latest, _ = await store.get_response(third["id"])
    assert original is not None and latest is not None
    assert original.binding.checkpoint_id != latest.binding.checkpoint_id
    assert "_internal_metadata" not in (first.get("metadata") or {})


@pytest.mark.parametrize("different", [{"sandbox": "other"}, {"user": "other"}])
async def test_native_continuation_rejects_cross_scope(different: dict[str, str]) -> None:
    server = _server()
    first = await _post(server, '{"text":"one"}')
    second = await _post(server, '{"text":"two"}', previous_response_id=first["id"], **different)
    assert second["status"] == "failed"
    assert not second["output"]


async def test_graph_change_cannot_choose_a_new_unrelated_checkpoint() -> None:
    provider = InMemoryResponseProvider()
    first = await _post(_server(response_store=provider), '{"text":"one"}')
    incompatible = _server(lambda request: _build(name="changed"), response_store=provider)
    second = await _post(incompatible, '{"text":"two"}', previous_response_id=first["id"])
    assert second["status"] == "failed"
    assert "graph" in second["error"]["message"]


async def test_generic_pending_replies_are_complete_and_consumed_once() -> None:
    server = _server(lambda request: _build(_Review()), parser=_parse_text)
    first = await _post(server, "review")
    assert first["status"] == "completed", first
    call_ids = [item["call_id"] for item in first["output"]]
    assert len(set(call_ids)) == 2
    partial = await _post(
        server,
        [{"type": "function_call_output", "call_id": call_ids[0], "output": "true"}],
        previous_response_id=first["id"],
    )
    assert partial["status"] == "failed"
    assert not partial["output"]
    full = [
        {"type": "function_call_output", "call_id": call_ids[0], "output": "true"},
        {"type": "function_call_output", "call_id": call_ids[1], "output": "false"},
    ]
    duplicate = await _post(server, [full[0], dict(full[0]), full[1]], previous_response_id=first["id"])
    assert duplicate["status"] == "failed"
    assert not duplicate["output"]
    completed = await _post(server, full, previous_response_id=first["id"])
    assert completed["status"] == "completed", completed
    assert _texts(completed) == ["review:True", "review:False"]
    replay = await _post(server, full, previous_response_id=first["id"])
    assert replay["status"] == "failed"
    assert not replay["output"]


async def test_named_conversation_rejects_old_wire_replies_when_core_request_ids_repeat() -> None:
    server = _server(lambda request: _build(_Review()), parser=_parse_text)
    conversation = IdGenerator.new_id("conv")
    first = await _post(server, "old question", conversation=conversation)
    old_ids = [item["call_id"] for item in first["output"]]
    old_replies = [{"type": "function_call_output", "call_id": wire_id, "output": "true"} for wire_id in old_ids]
    completed = await _post(server, old_replies, conversation=conversation)
    assert completed["status"] == "completed", completed
    next_pause = await _post(server, "new question", conversation=conversation)
    assert next_pause["status"] == "completed", next_pause
    new_ids = [item["call_id"] for item in next_pause["output"]]
    assert set(new_ids).isdisjoint(old_ids)
    replay = await _post(server, old_replies, conversation=conversation)
    assert replay["status"] == "failed" and not replay["output"]
    new_replies = [{"type": "function_call_output", "call_id": wire_id, "output": "false"} for wire_id in new_ids]
    accepted = await _post(server, new_replies, conversation=conversation)
    assert accepted["status"] == "completed", accepted
    assert _texts(accepted) == ["new question:False", "new question:False"]


async def test_approval_wire_ids_bind_only_to_exact_pending_checkpoint() -> None:
    server = _server(lambda request: _build(_Approvals()), parser=_parse_text)
    first = await _post(server, "/safe")
    assert first["status"] == "completed", first
    wire_ids = [item["id"] for item in first["output"] if item["type"] == "mcp_approval_request"]
    assert len(wire_ids) == 2
    full = [
        {"type": "mcp_approval_response", "approval_request_id": wire_ids[0], "approve": True},
        {"type": "mcp_approval_response", "approval_request_id": wire_ids[1], "approve": False},
    ]
    for replies in (
        full[:1],
        [full[0], dict(full[0]), full[1]],
        [{**full[0], "approval_request_id": "forged"}, full[1]],
    ):
        rejected = await _post(server, replies, previous_response_id=first["id"])
        assert rejected["status"] == "failed"
        assert not rejected["output"]
    wrong_scope = await _post(server, full, sandbox="other", previous_response_id=first["id"])
    assert wrong_scope["status"] == "failed"
    completed = await _post(server, full, previous_response_id=first["id"])
    assert completed["status"] == "completed", completed
    assert _texts(completed) == ["first:True", "second:False"]
    replay = await _post(server, full, previous_response_id=first["id"])
    assert replay["status"] == "failed"


async def test_store_false_has_no_durable_native_state_and_cannot_pause() -> None:
    with (
        patch("agent_framework_foundry_hosting._workflow_state.FoundryStateStore.get_or_create") as bindings,
        patch("agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create") as checkpoints,
    ):
        response = await _post(_server(), '{"text":"one"}', store=False)
        assert response["status"] == "completed", response
        paused = await _post(_server(lambda request: _build(_Approvals()), parser=_parse_text), "/safe", store=False)
        assert paused["status"] == "failed"
        assert not paused["output"]
        bindings.assert_not_called()
        checkpoints.assert_not_called()


async def test_unsupported_shared_workflow_is_not_cloned_or_unwrapped() -> None:
    graph = _build()
    server = _server(graph)
    first = await _post(server, '{"text":"one"}', store=False)
    assert first["status"] == "completed", first
    second = await _post(server, '{"text":"two"}', store=False)
    assert second["status"] == "failed"
    with pytest.raises(TypeError, match="parse_response"):
        ResponsesHostServer(workflow=_build())
    with pytest.raises(ValueError, match="exactly one"):
        ResponsesHostServer()
    with pytest.raises(ValueError, match="request-aware factory"):
        ResponsesHostServer(
            workflow=_build(), parse_response=_parse, options=ResponsesServerOptions(resilient_background=True)
        )


async def test_pair_write_failure_withholds_tentative_approval_output() -> None:
    server = _server(lambda request: _build(_Approvals()), parser=_parse_text)
    original = HostedWorkflowRun.stage

    async def stage(run: HostedWorkflowRun, snapshot: Any, **kwargs: Any) -> None:
        if any(item["type"] == "mcp_approval_request" for item in snapshot["output"]):
            raise RuntimeError("private-persistence-token")
        await original(run, snapshot, **kwargs)

    with patch.object(HostedWorkflowRun, "stage", stage):
        response = await _post(server, "/safe")
    assert response["status"] == "failed"
    assert not response["output"]
    assert "private-persistence-token" not in json.dumps(response)


async def test_private_executor_error_never_reaches_wire_or_native_logs(caplog: pytest.LogCaptureFixture) -> None:
    class _Fail(Executor):
        def __init__(self) -> None:
            super().__init__("fail")

        @handler
        async def start(self, message: str, ctx: WorkflowContext[str, str]) -> None:
            raise RuntimeError("private-provider-token at /srv/private/path")

    caplog.set_level(logging.ERROR, logger="agent_framework_foundry_hosting._workflow_responses")
    response = await _post(_server(lambda request: _build(_Fail()), parser=_parse_text), "fail")
    assert response["status"] == "failed"
    assert "private-provider-token" not in json.dumps(response)
    assert not any(
        "private-provider-token" in record.getMessage()
        for record in caplog.records
        if record.name.startswith("agent_framework_foundry_hosting")
    )


async def test_typed_framework_output_hides_private_provider_continuation() -> None:
    class _Output(Executor):
        def __init__(self) -> None:
            super().__init__("output")

        @handler
        async def start(self, message: str, ctx: WorkflowContext[str, AgentResponse]) -> None:
            await ctx.yield_output(
                AgentResponse(
                    messages=[Message("assistant", [Content.from_text("safe")])],
                    response_id="private-response",
                    raw_representation={"continuation_token": "private-continuation"},
                )
            )

    response = await _post(_server(lambda request: _build(_Output()), parser=_parse_text), "go")
    assert response["status"] == "completed", response
    assert _texts(response) == ["safe"]
    assert "private-continuation" not in json.dumps(response)
    assert "private-response" not in json.dumps(response)


async def test_native_agent_executor_applies_options_without_mutating_defaults_or_double_keywords() -> None:
    calls: list[dict[str, Any]] = []
    lifecycle: list[str] = []
    agents: list[Agent[Any]] = []

    def create(request: HostedResponseRequest) -> Workflow:
        agent = Agent(
            client=_RecordingClient(calls, lifecycle),
            name="model",
            default_options=cast(ChatOptions[Any], {"temperature": 0.2, "store": True}),
        )
        agents.append(agent)
        return _build(AgentExecutor(agent, id="model"))

    async def parse(request: HostedResponseRequest) -> WorkflowTurn[Any]:
        return WorkflowTurn(input=[Message("user", await request.get_input_text() or "")])

    server = _server(create, parser=parse)
    first = await _post(server, "one", temperature=0.7, max_output_tokens=12, store=True)
    assert first["status"] == "completed", first
    second = await _post(server, "two", temperature=0.4, store=False, call="call-two")
    assert second["status"] == "completed", second
    assert [call["options"]["store"] for call in calls] == [False, False]
    assert [call["options"]["temperature"] for call in calls] == [0.7, 0.4]
    assert calls[0]["options"]["max_tokens"] == 12
    assert all(
        agent.default_options["temperature"] == 0.2 and agent.default_options["store"] is True for agent in agents
    )
    assert lifecycle == ["open", "close", "open", "close"]
    assert "private-provider-id" not in json.dumps(first)
    assert all("options" not in call["kwargs"] for call in calls)


async def test_registry_backed_executor_gets_native_options_and_resource_lifecycle() -> None:
    calls: list[dict[str, Any]] = []
    lifecycle: list[str] = []

    def create(request: HostedResponseRequest) -> Workflow:
        agent = Agent(
            client=_RecordingClient(calls, lifecycle),
            name="registered",
            default_options=cast(ChatOptions[Any], {"temperature": 0.2, "store": True}),
        )
        return _build(_RegistryExecutor(agent))

    response = await _post(_server(create, parser=_parse_text), "hello", temperature=0.7)

    assert response["status"] == "completed", response
    assert _texts(response) == ["safe"]
    assert calls[0]["options"]["temperature"] == 0.7
    assert calls[0]["options"]["store"] is False
    assert lifecycle == ["open", "close"]


@pytest.mark.parametrize("failure", ["parser", "continuation"])
async def test_request_owned_resources_close_when_pre_execution_preparation_fails(failure: str) -> None:
    calls: list[dict[str, Any]] = []
    lifecycle: list[str] = []

    def create(request: HostedResponseRequest) -> Workflow:
        agent = Agent(client=_RecordingClient(calls, lifecycle), name="owned")
        return _build(AgentExecutor(agent, id="owned"))

    async def parse(request: HostedResponseRequest) -> WorkflowTurn[Any]:
        raise ValueError("malformed typed input")

    kwargs = {"previous_response_id": IdGenerator.new_response_id()} if failure == "continuation" else {}
    response = await _post(_server(create, parser=parse), "hello", **kwargs)

    assert response["status"] == "failed"
    assert calls == []
    assert lifecycle == ["open", "close"]


async def test_native_provider_that_ignores_store_false_cannot_commit_or_leak_token() -> None:
    calls: list[dict[str, Any]] = []
    lifecycle: list[str] = []

    def create(request: HostedResponseRequest) -> Workflow:
        agent = Agent(client=_RecordingClient(calls, lifecycle, violates_store=True), name="model")
        return _build(AgentExecutor(agent, id="model"))

    async def parse(request: HostedResponseRequest) -> WorkflowTurn[Any]:
        return WorkflowTurn(input=[Message("user", "test")])

    response = await _post(_server(create, parser=parse), "one", store=False)
    assert response["status"] == "failed"
    assert not response["output"]
    assert "private-service-id" not in json.dumps(response)
    assert lifecycle == ["open", "close"]
    assert len(calls) == 1 and calls[0]["options"]["store"] is False


async def test_bare_raw_agent_fails_before_dispatch_instead_of_pretending_to_apply_options() -> None:
    calls: list[dict[str, Any]] = []

    def create(request: HostedResponseRequest) -> Workflow:
        return _build(AgentExecutor(RawAgent(client=_RecordingClient(calls, []), name="raw"), id="raw"))

    async def parse(request: HostedResponseRequest) -> WorkflowTurn[Any]:
        return WorkflowTurn(input=[Message("user", "test")])

    response = await _post(_server(create, parser=parse), "one", temperature=0.4)
    assert response["status"] == "failed"
    assert calls == []


@pytest.mark.parametrize("stored", [False, True])
@pytest.mark.parametrize("stream", [False, True])
async def test_raw_agent_fresh_factory_matches_explicit_defaults(stored: bool, stream: bool) -> None:
    calls: list[dict[str, Any]] = []
    lifecycle: list[str] = []

    def create(request: HostedResponseRequest) -> Workflow:
        agent = RawAgent(
            client=_RecordingClient(calls, lifecycle),
            name="raw",
            default_options=cast(ChatOptions[Any], {**request.options, "store": False}),
        )
        return _build(AgentExecutor(agent, id="raw"))

    async def parse(request: HostedResponseRequest) -> WorkflowTurn[Any]:
        return WorkflowTurn(input=[Message("user", await request.get_input_text() or "")])

    server = _server(create, parser=parse)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
        response = await client.post(
            "/responses",
            json={
                "input": "hello",
                "agent_session_id": "sandbox",
                "store": stored,
                "stream": stream,
                "temperature": 0.6,
                "max_output_tokens": 9,
            },
        )
    assert response.status_code == 200
    if stream:
        payloads = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]
        final = next(item["response"] for item in payloads if item["type"] == "response.completed")
    else:
        final = response.json()
    assert final["status"] == "completed", final
    assert _texts(final) == ["safe"]
    assert calls[0]["options"]["temperature"] == 0.6
    assert calls[0]["options"]["max_tokens"] == 9
    assert calls[0]["options"]["store"] is False
    assert "options" not in calls[0]["kwargs"]
    assert lifecycle == ["open", "close"]


@pytest.mark.parametrize("default_store", [None, True])
async def test_raw_agent_unverified_storage_defaults_fail_before_claim(default_store: bool | None) -> None:
    calls: list[dict[str, Any]] = []
    lifecycle: list[str] = []

    def create(request: HostedResponseRequest) -> Workflow:
        options: ChatOptions[Any] = {}
        if default_store is not None:
            options["store"] = default_store
        return _build(
            AgentExecutor(
                RawAgent(
                    client=_RecordingClient(calls, lifecycle),
                    name="raw",
                    default_options=options,
                ),
                id="raw",
            )
        )

    async def parse(request: HostedResponseRequest) -> WorkflowTurn[Any]:
        return WorkflowTurn(input=[Message("user", "hello")])

    response = await _post(_server(create, parser=parse), "hello")
    assert response["status"] == "failed"
    assert calls == [] and lifecycle == ["open", "close"]


@pytest.mark.parametrize("stored", [False, True])
async def test_raw_agent_private_continuation_violation_never_publishes_output(stored: bool) -> None:
    calls: list[dict[str, Any]] = []
    lifecycle: list[str] = []

    def create(request: HostedResponseRequest) -> Workflow:
        return _build(
            AgentExecutor(
                RawAgent(
                    client=_RecordingClient(calls, lifecycle, violates_store=True),
                    name="raw",
                    default_options=cast(ChatOptions[Any], {"store": False}),
                ),
                id="raw",
            )
        )

    async def parse(request: HostedResponseRequest) -> WorkflowTurn[Any]:
        return WorkflowTurn(input=[Message("user", "hello")])

    response = await _post(_server(create, parser=parse), "hello", store=stored)
    assert response["status"] == "failed"
    assert not response["output"]
    assert "private-service-id" not in json.dumps(response)
    assert calls[0]["options"]["store"] is False
    assert lifecycle == ["open", "close"]


async def test_real_sdk_background_polling_pairs_each_step_and_usage() -> None:
    started, release, stopped = (asyncio.Event() for _ in range(3))
    server = _server(_progress_factory(started, release, stopped), parser=_parse_count)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
        pending = await client.post(
            "/responses",
            json={
                "input": "2",
                "agent_session_id": "sandbox",
                "store": True,
                "background": True,
            },
        )
        assert pending.status_code == 200
        response_id = pending.json()["id"]
        await asyncio.wait_for(started.wait(), timeout=2)
        release.set()
        result = await _poll(client, response_id)
    assert result["status"] == "completed", result
    assert _texts(result) == ["2", "1", "0"]
    assert result["usage"]["total_tokens"] == 6
    assert stopped.is_set()


async def test_real_sdk_background_cancel_drains_suspended_executor_and_blocks_claim() -> None:
    started, release, stopped = (asyncio.Event() for _ in range(3))
    server = _server(_progress_factory(started, release, stopped), parser=_parse_count)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
        pending = await client.post(
            "/responses",
            json={
                "input": "2",
                "agent_session_id": "sandbox",
                "store": True,
                "background": True,
            },
        )
        response_id = pending.json()["id"]
        await asyncio.wait_for(started.wait(), timeout=2)
        cancelled = await client.post(f"/responses/{response_id}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        await asyncio.wait_for(stopped.wait(), timeout=2)
        result = await _poll(client, response_id)
    assert result["status"] == "cancelled"
    record, _ = await FoundryWorkflowBindingStore(FoundryRequestScope("sandbox", None, None, False)).get_response(
        response_id
    )
    assert record is not None and record.status == "blocked"


async def test_real_sdk_raw_agent_cancel_closes_request_owned_client_in_trusted_context() -> None:
    from azure.ai.agentserver.core import get_request_context

    started, release, stopped = (asyncio.Event() for _ in range(3))
    lifecycle: list[str] = []
    cleanup_calls: list[str | None] = []

    class GatedClient(_RecordingClient):
        def _inner_get_response(self, **kwargs: Any) -> Any:
            async def updates() -> AsyncIterator[ChatResponseUpdate]:
                started.set()
                try:
                    await release.wait()
                    yield ChatResponseUpdate(role="assistant", contents=[Content.from_text("too late")])
                finally:
                    stopped.set()

            return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

        async def __aexit__(self, *args: object) -> None:
            cleanup_calls.append(get_request_context().call_id)
            await super().__aexit__(*args)

    def create(request: HostedResponseRequest) -> Workflow:
        agent = RawAgent(
            client=GatedClient([], lifecycle),
            name="raw",
            default_options=cast(ChatOptions[Any], {"store": False}),
        )
        return _build(AgentExecutor(agent, id="raw"))

    async def parse(request: HostedResponseRequest) -> WorkflowTurn[Any]:
        return WorkflowTurn(input=[Message("user", "wait")])

    server = _server(create, parser=parse)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
        pending = await client.post(
            "/responses",
            headers={"x-agent-foundry-call-id": "trusted-original-call"},
            json={"input": "wait", "agent_session_id": "sandbox", "store": True, "background": True},
        )
        response_id = pending.json()["id"]
        await asyncio.wait_for(started.wait(), timeout=2)
        cancelled = await client.post(
            f"/responses/{response_id}/cancel",
            headers={"x-agent-foundry-call-id": "cancel-request-call"},
        )
        assert cancelled.status_code == 200
        await asyncio.wait_for(stopped.wait(), timeout=2)
        result = await _poll(client, response_id)
    assert result["status"] == "cancelled"
    assert lifecycle == ["open", "close"]
    assert cleanup_calls == ["trusted-original-call"]
    assert "too late" not in json.dumps(result)


async def test_real_sdk_foreground_disconnect_closes_native_raw_agent_and_blocks_resume() -> None:
    started, release, stopped = (asyncio.Event() for _ in range(3))
    lifecycle: list[str] = []

    class GatedClient(_RecordingClient):
        def _inner_get_response(self, **kwargs: Any) -> Any:
            async def updates() -> AsyncIterator[ChatResponseUpdate]:
                started.set()
                try:
                    await release.wait()
                    yield ChatResponseUpdate(role="assistant", contents=[Content.from_text("too late")])
                finally:
                    stopped.set()

            return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

    def create(request: HostedResponseRequest) -> Workflow:
        return _build(
            AgentExecutor(
                RawAgent(
                    client=GatedClient([], lifecycle),
                    name="raw",
                    default_options=cast(ChatOptions[Any], {"store": False}),
                ),
                id="raw",
            )
        )

    async def parse(request: HostedResponseRequest) -> WorkflowTurn[Any]:
        return WorkflowTurn(input=[Message("user", "wait")])

    server = _server(create, parser=parse)
    body = json.dumps({"input": "wait", "agent_session_id": "sandbox", "store": True, "stream": True}).encode()
    delivered = False
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await started.wait()
        return {"type": "http.disconnect"}

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(dict(message))

    scope: Any = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/responses",
        "raw_path": b"/responses",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    await asyncio.wait_for(server(scope, receive, send), timeout=3)
    await asyncio.wait_for(stopped.wait(), timeout=2)
    assert lifecycle == ["open", "close"]
    wire = b"".join(message.get("body", b"") for message in messages)
    assert b"response.completed" not in wire and b"too late" not in wire


@pytest.mark.parametrize("outer_checkpoint_failure", [False, True])
async def test_real_sdk_shutdown_and_restart_recovers_exact_background_output(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    outer_checkpoint_failure: bool,
) -> None:
    from azure.ai.agentserver.core.tasks import resilient_tasks_enabled, set_resilient_tasks_enabled

    enabled = resilient_tasks_enabled()
    set_resilient_tasks_enabled(True)
    monkeypatch.setenv("AGENTSERVER_SHUTDOWN_GRACE_SECONDS", "0.1")
    started, release, stopped = (asyncio.Event() for _ in range(3))

    class FailingCheckpointStore(FileResponseStore):
        fail_intermediate = outer_checkpoint_failure
        failures = 0

        async def update_response(self, response: Any, **kwargs: Any) -> None:
            if self.fail_intermediate and response.get("status") == "in_progress" and response.get("output"):
                self.failures += 1
                raise RuntimeError("Synthetic intermediate SDK checkpoint failure.")
            await super().update_response(response, **kwargs)

    provider = FailingCheckpointStore(storage_dir=tmp_path / "responses")
    factory = _progress_factory(started, release, stopped)
    options = ResponsesServerOptions(resilient_background=True, shutdown_grace_period_seconds=1)
    server = _server(factory, parser=_parse_count, response_store=provider, options=options)
    paired = asyncio.Event()
    original = HostedWorkflowRun.stage

    async def stage(run: HostedWorkflowRun, snapshot: Any, **kwargs: Any) -> None:
        await original(run, snapshot, **kwargs)
        if snapshot.get("output"):
            paired.set()

    try:
        with patch.object(HostedWorkflowRun, "stage", stage):
            async with server.router.lifespan_context(server):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=server), base_url="http://test"
                ) as client:
                    pending = await client.post(
                        "/responses",
                        json={
                            "input": "2",
                            "agent_session_id": "sandbox",
                            "store": True,
                            "background": True,
                        },
                    )
                    assert pending.status_code == 200
                    response_id = pending.json()["id"]
                    await asyncio.wait_for(started.wait(), timeout=3)
                    await asyncio.wait_for(paired.wait(), timeout=3)
        assert stopped.is_set()
        if outer_checkpoint_failure:
            assert provider.failures > 0
        provider.fail_intermediate = False
        release.set()
        restarted = _server(
            factory,
            parser=_parse_count,
            response_store=provider,
            options=ResponsesServerOptions(resilient_background=True, shutdown_grace_period_seconds=1),
        )
        async with (
            restarted.router.lifespan_context(restarted),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url="http://test") as client,
        ):
            result = await _poll(client, response_id)
        assert result["status"] == "completed", result
        assert _texts(result) == ["2", "1", "0"]
        assert result["usage"]["total_tokens"] == 6
    finally:
        release.set()
        set_resilient_tasks_enabled(enabled)


async def test_legacy_wrapper_warns_once_per_host_and_keeps_message_semantics() -> None:
    class _Legacy(Executor):
        def __init__(self) -> None:
            super().__init__("legacy")

        @handler
        async def start(self, message: list[Message], ctx: WorkflowContext[str, str]) -> None:
            await ctx.yield_output(message[-1].text)

    def create() -> Any:
        return _build(_Legacy()).as_agent()

    server = ResponsesHostServer(agent=create, response_store=InMemoryResponseProvider(), configure_observability=None)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", DeprecationWarning)
        first = await _post(server, "legacy")
        second = await _post(server, "again", previous_response_id=first["id"])
    assert first["status"] == second["status"] == "completed"
    assert _texts(first) == ["legacy"]
    assert _texts(second) == ["again"]
    assert sum("Hosting WorkflowAgent" in str(item.message) for item in captured) == 1
