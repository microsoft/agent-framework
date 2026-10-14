# Copyright (c) Microsoft. All rights reserved.

"""Protocol-specific regressions for native Invocations workflows."""

from __future__ import annotations

import asyncio
import gc
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any, cast
from unittest.mock import patch

import httpx
import pytest
from agent_framework import (
    Agent,
    AgentExecutor,
    AgentResponse,
    AgentResponseUpdate,
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Executor,
    FunctionInvocationContext,
    FunctionInvocationLayer,
    InMemoryHistoryProvider,
    Message,
    RawAgent,
    ResponseStream,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
    tool,
)
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    get_request_context,
    reset_request_context,
    set_request_context,
)
from pydantic import BaseModel
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response, StreamingResponse

from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    FoundryRequestScope,
    InvocationsHostServer,
    WorkflowSource,
    WorkflowTurn,
)
from agent_framework_foundry_hosting._invocations import _workflow_output, _WorkflowOutputError
from agent_framework_foundry_hosting._state_store import FoundryCheckpointStore
from agent_framework_foundry_hosting._workflow_state import FoundryWorkflowBindingStore, WorkflowHead


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    question: str


class TicketModel(BaseModel):
    ticket_id: str
    due: date


@dataclass(frozen=True)
class MappingEnvelope:
    payload: Mapping[Any, str]


class MappingModel(BaseModel):
    payload: dict[Any, str]


class MappingSerializer:
    def to_dict(self) -> dict[Any, str]:
        return {1: "private-token", "1": "safe"}


@dataclass(frozen=True)
class TicketState:
    turns: int = 0
    last_ticket: str | None = None


@dataclass(frozen=True)
class TicketReview:
    ticket_id: str
    reviewer: str


@dataclass(frozen=True)
class TicketDecision:
    approved: bool


@dataclass(frozen=True)
class UnallowlistedReply:
    value: str


class _TicketExecutor(Executor):
    def __init__(self, calls: list[tuple[Ticket, str | None]], *, id: str = "ticket-start") -> None:
        super().__init__(id=id)
        self.calls = calls

    @handler
    async def handle(self, ticket: Ticket, ctx: WorkflowContext[None, dict[str, Any]]) -> None:
        assert isinstance(ticket, Ticket)
        self.calls.append((ticket, get_request_context().call_id))
        state = ctx.get_state("tickets", TicketState())
        assert isinstance(state, TicketState)
        ctx.set_state("tickets", TicketState(state.turns + 1, ticket.ticket_id))
        await ctx.yield_output({"ticket": ticket, "turn": state.turns + 1, "previous_ticket": state.last_ticket})


class _ReviewExecutor(Executor):
    def __init__(self, replies: list[tuple[str, bool]], starts: list[str] | None = None) -> None:
        super().__init__(id="ticket-review")
        self.replies = replies
        self.starts = starts

    @handler
    async def handle(self, ticket: Ticket, ctx: WorkflowContext[None, dict[str, Any]]) -> None:
        if self.starts is not None:
            self.starts.append(ticket.ticket_id)
        for reviewer in ("support", "security"):
            await ctx.request_info(TicketReview(ticket.ticket_id, reviewer), response_type=TicketDecision)

    @response_handler
    async def review(
        self, request: TicketReview, response: TicketDecision, ctx: WorkflowContext[None, dict[str, Any]]
    ) -> None:
        self.replies.append((request.reviewer, response.approved))
        await ctx.yield_output({
            "ticket_id": request.ticket_id,
            "reviewer": request.reviewer,
            "approved": response.approved,
        })


class _AnyReplyExecutor(Executor):
    def __init__(self, replies: list[object]) -> None:
        super().__init__(id="any-reply")
        self.replies = replies

    @handler
    async def handle(self, message: str, ctx: WorkflowContext[None, object]) -> None:
        await ctx.request_info(f"{message}:first", response_type=object, request_id="first")
        await ctx.request_info(f"{message}:second", response_type=object, request_id="second")

    @response_handler
    async def decide(self, request: str, response: object, ctx: WorkflowContext[None, object]) -> None:
        self.replies.append(response)
        await ctx.yield_output({"request": request, "accepted": True})


class _ApprovalExecutor(Executor):
    def __init__(self, decisions: list[bool]) -> None:
        super().__init__(id="approval")
        self.decisions = decisions

    @handler
    async def handle(self, ticket: Ticket, ctx: WorkflowContext[None, dict[str, Any]]) -> None:
        for reviewer in ("support", "security"):
            function = Content.from_function_call(
                call_id=uuid.uuid4().hex,
                name="approve_ticket",
                arguments={"ticket_id": ticket.ticket_id, "reviewer": reviewer},
            )
            await ctx.request_info(
                Content.from_function_approval_request(uuid.uuid4().hex, function),
                response_type=Content,
            )

    @response_handler
    async def decide(self, request: Content, response: Content, ctx: WorkflowContext[None, dict[str, Any]]) -> None:
        assert isinstance(response.approved, bool)
        self.decisions.append(response.approved)
        await ctx.yield_output({"approved": response.approved})


class _RegistryExecutor(Executor):
    def __init__(self, agent: Agent[Any]) -> None:
        super().__init__("registry")
        self._agents = {"registered": agent}

    @handler
    async def handle(self, ticket: Ticket, ctx: WorkflowContext[None, dict[str, Any]]) -> None:
        await ctx.yield_output({"ticket_id": ticket.ticket_id})


class _ContextClient(
    FunctionInvocationLayer[ChatOptions], ChatMiddlewareLayer[ChatOptions], BaseChatClient[ChatOptions]
):
    STORES_BY_DEFAULT = True

    def __init__(
        self,
        calls: list[dict[str, Any]],
        resources: list[tuple[str, str | None]],
    ) -> None:
        super().__init__(middleware=[])
        self.calls = calls
        self.resources = resources
        self.round = 0

    async def __aenter__(self) -> _ContextClient:
        self.resources.append(("enter", get_request_context().call_id))
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.resources.append(("exit", get_request_context().call_id))

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        self.round += 1
        self.calls.append({
            "options": dict(options),
            "kwargs": dict(kwargs),
            "call_id": get_request_context().call_id,
        })
        contents = (
            [Content.from_function_call(uuid.uuid4().hex, "inspect_runtime", arguments={})]
            if self.round == 1
            else [Content.from_text("checked")]
        )

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=contents)

        async def complete() -> ChatResponse:
            return ChatResponse(messages=[Message("assistant", contents=contents)])

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates) if stream else complete()


def _request(payload: Any, *, session_id: str = "session") -> Request:
    body = json.dumps(payload).encode()

    async def receive() -> Any:
        return {"type": "http.request", "body": body}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/invocations",
            "query_string": f"agent_session_id={session_id}".encode(),
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )


@contextmanager
def _context(*, session_id: str = "session", call_id: str | None = None, user_id: str | None = None) -> Iterator[None]:
    token = set_request_context(FoundryAgentRequestContext(session_id=session_id, call_id=call_id, user_id=user_id))
    try:
        yield
    finally:
        reset_request_context(token)


async def _parse_ticket(request: Request) -> WorkflowTurn[Ticket]:
    payload = await request.json()
    if "responses" in payload:
        return WorkflowTurn(
            responses={
                request_id: TicketDecision(approved=value["approved"])
                for request_id, value in payload["responses"].items()
            },
            stream=payload.get("stream", False),
        )
    return WorkflowTurn(
        input=Ticket(payload["ticket_id"], payload.get("question", "Help")),
        stream=payload.get("stream", False),
    )


def _host(
    factory: WorkflowSource[Request],
    *,
    parser: Any = _parse_ticket,
    checkpoints: CheckpointStoreProvider | None = None,
) -> InvocationsHostServer:
    return InvocationsHostServer(
        workflow=factory,
        parse_request=parser,
        checkpoint_store_provider=checkpoints
        or CheckpointStoreProvider(
            allowed_checkpoint_types=[
                f"{__name__}:{value.__qualname__}"
                for value in (Ticket, TicketModel, TicketState, TicketReview, TicketDecision)
            ]
        ),
        configure_observability=None,
    )


def _sse_events(body: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for frame in body.split("\n\n"):
        if frame.startswith("event: "):
            event, data = frame.split("\n", 1)
            frames.append({"event": event.removeprefix("event: "), **json.loads(data.removeprefix("data: "))})
    return frames


async def _events(response: Response) -> list[dict[str, Any]]:
    if isinstance(response, StreamingResponse):
        body = "".join([
            chunk if isinstance(chunk, str) else bytes(chunk).decode() async for chunk in response.body_iterator
        ])
        return _sse_events(body)
    payload = json.loads(bytes(response.body))
    if response.status_code != 200:
        return [{"event": "error", **payload, "status": response.status_code}]
    assert response.media_type == "application/json"
    return [{"event": item["type"], **item} for item in payload["output"]]


async def _invoke(
    server: InvocationsHostServer,
    payload: Any,
    *,
    session_id: str = "session",
    call_id: str | None = None,
    user_id: str | None = None,
) -> tuple[Response, list[dict[str, Any]]]:
    with _context(session_id=session_id, call_id=call_id, user_id=user_id):
        response = await server._handle_invoke(_request(payload, session_id=session_id))
    # Deliberately collect after the original request context has been removed.
    return response, await _events(response)


class TestWorkflowOutput:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, None),
            (True, True),
            (3, 3),
            (0.25, 0.25),
            ("ready", "ready"),
            (("one", 2), ["one", 2]),
            (Ticket("T-1", "Help"), {"ticket_id": "T-1", "question": "Help"}),
            (
                TicketModel(ticket_id="T-1", due=date(2026, 10, 1)),
                {"ticket_id": "T-1", "due": "2026-10-01"},
            ),
            (
                {"tickets": [Ticket("T-1", "Help"), Ticket("T-2", "Thanks")]},
                {"tickets": [{"ticket_id": "T-1", "question": "Help"}, {"ticket_id": "T-2", "question": "Thanks"}]},
            ),
        ],
    )
    def test_encodes_application_values(self, value: Any, expected: Any) -> None:
        assert _workflow_output(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            Content.from_text("typed content"),
            Message("assistant", ["typed message"]),
            AgentResponse(messages=[Message("assistant", ["typed response"])]),
        ],
    )
    def test_preserves_framework_output_instead_of_flattening_to_text(self, value: Any) -> None:
        assert _workflow_output(value) == value.to_dict()
        assert isinstance(_workflow_output(value), dict)

    @pytest.mark.parametrize(
        "value", [object(), {"nested": object()}, [object()], float("nan"), float("inf"), Ticket, "\ud800"]
    )
    def test_rejects_unsupported_values_without_stringifying_or_dropping_them(self, value: Any) -> None:
        with pytest.raises(_WorkflowOutputError, match="not JSON-serializable"):
            _workflow_output(value)

    def test_rejects_circular_output(self) -> None:
        circular: list[Any] = []
        circular.append(circular)
        with pytest.raises(_WorkflowOutputError, match="not JSON-serializable"):
            _workflow_output(circular)

    def test_rejects_invalid_nested_framework_data(self) -> None:
        content = Content.from_text("text", additional_properties={"invalid": object()})
        with pytest.raises(_WorkflowOutputError, match="not JSON-serializable"):
            _workflow_output(content)

    @pytest.mark.parametrize(
        "value",
        [
            {"nested": {1: "private-token", "1": "safe"}},
            MappingEnvelope({1: "private-token", "1": "safe"}),
            MappingModel(payload={1: "private-token", "1": "safe"}),
            Content.from_text(
                "typed content",
                additional_properties=cast(Any, {1: "private-token", "1": "safe"}),
            ),
            MappingSerializer(),
        ],
    )
    def test_rejects_non_string_mapping_keys_before_json_coercion_without_leaking_values(self, value: Any) -> None:
        with pytest.raises(_WorkflowOutputError, match=r"at \$.*mapping keys must be strings") as raised:
            _workflow_output(value)
        assert "private-token" not in str(raised.value)
        assert "'1'" not in str(raised.value)

    @pytest.mark.parametrize("response_type", [AgentResponse, AgentResponseUpdate, ChatResponse, ChatResponseUpdate])
    def test_does_not_expose_private_provider_continuation(self, response_type: Any) -> None:
        response = response_type(continuation_token={"private": "provider-token"})
        assert "continuation_token" not in _workflow_output(response)
        assert response.continuation_token == {"private": "provider-token"}


class TestNativeWorkflowConfiguration:
    def test_requires_one_source_and_an_explicit_parser(self) -> None:
        def create(_request: Request) -> Workflow:
            return WorkflowBuilder(name="tickets", start_executor=_TicketExecutor([])).build()

        invalid_agent: Any = object()
        with pytest.raises(TypeError, match="exactly one"):
            InvocationsHostServer(agent=invalid_agent, workflow=create, parse_request=_parse_ticket)
        with pytest.raises(TypeError, match="parse_request is required"):
            InvocationsHostServer(workflow=create)

    def test_workflow_rejects_agent_legacy_wire_format(self) -> None:
        with pytest.raises(ValueError, match="legacy_wire_format.*native"):
            InvocationsHostServer(
                workflow=lambda _: WorkflowBuilder(name="tickets", start_executor=_TicketExecutor([])).build(),
                parse_request=_parse_ticket,
                legacy_wire_format=True,
            )

    @pytest.mark.parametrize("stream", [False, True])
    async def test_parser_must_return_workflow_turn_before_building_or_loading_state(self, stream: bool) -> None:
        created: list[Request] = []

        def create(request: Request) -> Workflow:
            created.append(request)
            return WorkflowBuilder(name="tickets", start_executor=_TicketExecutor([])).build()

        server = _host(create, parser=lambda _: {"input": "untyped", "stream": stream})
        response, events = await _invoke(server, {})
        assert response.status_code == 400
        assert "WorkflowTurn" in events[0]["error"]
        assert created == []

    @pytest.mark.parametrize(
        "field", ["additional_function_arguments", "instructions", "tools", "middleware", "session"]
    )
    @pytest.mark.parametrize("shape", ["flat", "options", "executor-options"])
    async def test_client_kwargs_cannot_override_execution_controls(self, field: str, shape: str) -> None:
        created: list[Request] = []
        calls: list[tuple[Ticket, str | None]] = []

        def create(request: Request) -> Workflow:
            created.append(request)
            return WorkflowBuilder(name="tickets", start_executor=_TicketExecutor(calls)).build()

        unsafe: dict[str, Any] = {field: {"caller": "forged"}}
        if shape == "options":
            unsafe = {"options": unsafe}
        elif shape == "executor-options":
            unsafe = {"ticket-start": {"options": unsafe}}
        server = _host(create, parser=lambda _: WorkflowTurn(input=Ticket("T-1", "Help"), client_kwargs=unsafe))
        response, _ = await _invoke(server, {})
        assert response.status_code == 400
        assert len(created) == 1
        assert calls == []

    @pytest.mark.parametrize("stream", [False, True])
    async def test_built_workflow_allows_one_shot_output_but_rejects_pauses_without_state(self, stream: bool) -> None:
        calls: list[tuple[Ticket, str | None]] = []
        one_shot = WorkflowBuilder(name="one-shot", start_executor=_TicketExecutor(calls)).build()
        response, events = await _invoke(_host(one_shot), {"ticket_id": "T-1", "stream": stream})
        assert response.status_code == 200
        assert [event["event"] for event in events if event["event"] == "output"] == ["output"]
        assert calls == [(Ticket("T-1", "Help"), None)]
        store = FoundryWorkflowBindingStore(FoundryRequestScope("session", None, None, False))
        assert await store.get_head("invocations", None) == (None, None)

        pausing = WorkflowBuilder(name="pausing", start_executor=_ReviewExecutor([])).build()
        response, events = await _invoke(_host(pausing), {"ticket_id": "T-2", "stream": stream})
        assert response.status_code == (200 if stream else 400)
        assert [event["event"] for event in events] == ["error"]
        message = events[0].get("message") or events[0].get("error")
        assert isinstance(message, str) and "request-aware factory" in message
        assert await store.get_head("invocations", None) == (None, None)


class TestNativeWorkflowTurns:
    async def test_checkpoint_allowlist_failure_happens_before_claim_and_dispatch(self) -> None:
        calls: list[tuple[Ticket, str | None]] = []

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="tickets", start_executor=_TicketExecutor(calls)).build()

        response, events = await _invoke(_host(factory, checkpoints=CheckpointStoreProvider()), {"ticket_id": "T-1"})
        assert response.status_code == 400
        assert "checkpoint-allowlisted" in events[0]["error"]
        assert calls == []
        allowed = CheckpointStoreProvider(
            allowed_checkpoint_types=[f"{__name__}:{value.__qualname__}" for value in (Ticket, TicketState)]
        )
        response, events = await _invoke(_host(factory, checkpoints=allowed), {"ticket_id": "T-1"})
        assert response.status_code == 200
        assert events[0]["data"]["turn"] == 1
        assert len(calls) == 1

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("async_factory", [False, True])
    async def test_typed_input_state_and_output_survive_fresh_factories_and_host_replacement(
        self, stream: bool, async_factory: bool
    ) -> None:
        calls: list[tuple[Ticket, str | None]] = []
        created: list[tuple[Request, _TicketExecutor, str | None]] = []

        def create(request: Request) -> Workflow:
            executor = _TicketExecutor(calls)
            created.append((request, executor, get_request_context().call_id))
            return WorkflowBuilder(name="tickets", start_executor=executor).build()

        async def create_async(request: Request) -> Workflow:
            await asyncio.sleep(0)
            return create(request)

        factory: Any = create_async if async_factory else create
        for number in (1, 2, 3):
            server = _host(factory)
            response, events = await _invoke(
                server, {"ticket_id": f"T-{number}", "stream": stream}, call_id=f"call-{number}"
            )
            assert response.status_code == 200
            outputs = [item["data"] for item in events if item["event"] == "output"]
            assert outputs == [
                {
                    "ticket": {"ticket_id": f"T-{number}", "question": "Help"},
                    "turn": number,
                    "previous_ticket": f"T-{number - 1}" if number > 1 else None,
                }
            ]
            if stream:
                assert response.media_type == "text/event-stream"
                assert events[-1] == {"event": "done", "session_id": "session"}
            assert len(server._session_locks) == 0

        assert [call_id for _, call_id in calls] == ["call-1", "call-2", "call-3"]
        assert [call_id for _, _, call_id in created] == ["call-1", "call-2", "call-3"]
        assert len({id(executor) for _, executor, _ in created}) == 3
        assert all(isinstance(request, Request) for request, _, _ in created)

    async def test_local_turn_ids_are_host_owned_when_no_call_id_exists(self) -> None:
        calls: list[tuple[Ticket, str | None]] = []
        server = _host(lambda _: WorkflowBuilder(name="tickets", start_executor=_TicketExecutor(calls)).build())
        for number in (1, 2):
            response, events = await _invoke(server, {"ticket_id": f"T-{number}", "response_id": "caller-collision"})
            assert response.status_code == 200
            assert events[0]["data"]["turn"] == number
        assert [call_id for _, call_id in calls] == [None, None]

    async def test_trusted_call_ids_not_body_ids_control_records_and_duplicate_calls_do_not_dispatch(self) -> None:
        calls: list[tuple[Ticket, str | None]] = []
        server = _host(lambda _: WorkflowBuilder(name="tickets", start_executor=_TicketExecutor(calls)).build())
        server.config.is_hosted = True
        server.config.session_id = ""
        payload = {
            "ticket_id": "T-1",
            "response_id": "caller-collision",
            "previous_response_id": "forged-parent",
            "agent_session_id": "forged-sandbox",
            "session_id": "forged-session",
            "user_id": "forged-user",
            "call_id": "forged-call",
        }
        for number in (1, 2):
            response, events = await _invoke(
                server, payload, session_id="sandbox", user_id="user", call_id=f"trusted-{number}"
            )
            assert response.status_code == 200
            assert events[0]["data"]["turn"] == number
        response, events = await _invoke(server, payload, session_id="sandbox", user_id="user", call_id="trusted-2")
        assert response.status_code == 200
        assert events[0]["data"]["turn"] == 2
        assert [call_id for _, call_id in calls] == ["trusted-1", "trusted-2"]

    @pytest.mark.parametrize("stream", [False, True])
    async def test_native_output_keeps_pydantic_application_json(self, stream: bool) -> None:
        class ModelOutput(Executor):
            @handler
            async def handle(self, ticket: Ticket, ctx: WorkflowContext[None, TicketModel]) -> None:
                await ctx.yield_output(TicketModel(ticket_id=ticket.ticket_id, due=date(2026, 10, 1)))

        server = _host(lambda _: WorkflowBuilder(name="model-output", start_executor=ModelOutput("start")).build())
        response, events = await _invoke(server, {"ticket_id": "T-1", "stream": stream})
        assert response.status_code == 200
        assert [item["data"] for item in events if item["event"] == "output"] == [
            {
                "ticket_id": "T-1",
                "due": "2026-10-01",
            }
        ]

    @pytest.mark.parametrize("stream", [False, True])
    async def test_hosted_workflow_isolates_same_user_sandboxes_and_other_users(self, stream: bool) -> None:
        calls: list[tuple[Ticket, str | None]] = []
        identities = [("sandbox-a", "user-a"), ("sandbox-b", "user-a"), ("sandbox-a", "user-b")]
        for round_number in (1, 2):
            for session_id, user_id in identities:
                server = _host(lambda _: WorkflowBuilder(name="tickets", start_executor=_TicketExecutor(calls)).build())
                server.config.is_hosted = True
                server.config.session_id = ""
                response, events = await _invoke(
                    server,
                    {"ticket_id": f"T-{round_number}", "stream": stream},
                    session_id=session_id,
                    user_id=user_id,
                    call_id=f"call-{round_number}-{session_id}-{user_id}",
                )
                assert response.status_code == 200
                outputs = [item["data"] for item in events if item["event"] == "output"]
                assert outputs[0]["turn"] == round_number

    async def test_restore_uses_exact_cursor_instead_of_an_unrelated_later_checkpoint(self) -> None:
        calls: list[tuple[Ticket, str | None]] = []
        stores: list[Any] = []

        class RecordingCheckpoints(CheckpointStoreProvider):
            def get_store_for_scope(
                self, *, scope: Any, context_id: str, platform_context: FoundryAgentRequestContext
            ) -> Any:
                store = super().get_store_for_scope(
                    scope=scope, context_id=context_id, platform_context=platform_context
                )
                stores.append(store)
                return store

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="tickets", start_executor=_TicketExecutor(calls)).build()

        provider = RecordingCheckpoints(
            allowed_checkpoint_types=[f"{__name__}:{value.__qualname__}" for value in (Ticket, TicketState)]
        )
        first, _ = await _invoke(_host(factory, checkpoints=provider), {"ticket_id": "T-1"})
        assert first.status_code == 200
        unrelated = WorkflowBuilder(name="tickets", start_executor=_TicketExecutor([])).build()
        with _context():
            await unrelated.run(Ticket("unrelated", "Different run"), checkpoint_storage=stores[0])
        latest = await stores[0].get_latest(workflow_name="tickets")
        assert latest.checkpoint_id == unrelated.get_last_checkpoint_id()
        with patch.object(
            FoundryCheckpointStore, "get_latest", side_effect=AssertionError("must restore exact cursor")
        ):
            response, events = await _invoke(_host(factory, checkpoints=provider), {"ticket_id": "T-2"})
        assert response.status_code == 200
        assert events[0]["data"]["turn"] == 2
        assert events[0]["data"]["previous_ticket"] == "T-1"

    async def test_multiple_host_restarts_retain_only_current_response_and_checkpoint(self) -> None:
        calls: list[tuple[Ticket, str | None]] = []
        stores: list[FoundryCheckpointStore] = []

        class RecordingCheckpoints(CheckpointStoreProvider):
            def get_store_for_scope(
                self, *, scope: Any, context_id: str, platform_context: FoundryAgentRequestContext
            ) -> FoundryCheckpointStore:
                store = cast(
                    FoundryCheckpointStore,
                    super().get_store_for_scope(
                        scope=scope,
                        context_id=context_id,
                        platform_context=platform_context,
                    ),
                )
                stores.append(store)
                return store

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="tickets", start_executor=_TicketExecutor(calls)).build()

        provider = RecordingCheckpoints(
            allowed_checkpoint_types=[f"{__name__}:{value.__qualname__}" for value in (Ticket, TicketState)]
        )
        for number in range(1, 6):
            response, events = await _invoke(
                _host(factory, checkpoints=provider),
                {"ticket_id": f"T-{number}"},
                session_id="retained",
                call_id=f"call-{number}",
            )
            assert response.status_code == 200
            assert events[0]["data"]["turn"] == number

        binding_store = FoundryWorkflowBindingStore(FoundryRequestScope("retained", None, None, False))
        for number in range(1, 5):
            assert await binding_store.get_response(f"call-{number}") == (None, None)
        current, _ = await binding_store.get_response("call-5")
        head, _ = await binding_store.get_head("invocations", None)
        assert current is not None and current.status == "completed"
        assert head is not None and head.binding == current.binding
        raw_bindings = await binding_store._get_store()  # pyright: ignore[reportPrivateUsage]
        async with raw_bindings:
            keys = await raw_bindings.list_keys(call_id=None)
        assert len(keys.keys) == 2  # Current response record plus the fixed lineage head.
        # The current turn retains its entry and final checkpoints; prior turns are reclaimed.
        assert len(await stores[-1].list_checkpoint_ids(workflow_name="tickets")) == 2

        before = list(calls)
        replay, events = await _invoke(
            _host(factory, checkpoints=provider),
            {"ticket_id": "T-5"},
            session_id="retained",
            call_id="call-5",
        )
        assert replay.status_code == 200
        assert events[0]["data"]["turn"] == 5
        assert calls == before

    @pytest.mark.parametrize("change", ["name", "executor"])
    async def test_graph_changes_fail_before_executor_dispatch(self, change: str) -> None:
        calls: list[tuple[Ticket, str | None]] = []
        first = _host(lambda _: WorkflowBuilder(name="tickets", start_executor=_TicketExecutor(calls)).build())
        assert (await _invoke(first, {"ticket_id": "first"}))[0].status_code == 200
        changed = _host(
            lambda _: WorkflowBuilder(
                name="renamed" if change == "name" else "tickets",
                start_executor=_TicketExecutor(calls, id="renamed" if change == "executor" else "ticket-start"),
            ).build()
        )
        response, _ = await _invoke(changed, {"ticket_id": "second"})
        assert response.status_code == 409
        assert len(calls) == 1

    @pytest.mark.parametrize("stream", [False, True])
    async def test_nonserializable_output_is_a_visible_failure_without_done(self, stream: bool) -> None:
        class UnsupportedOutput(Executor):
            @handler
            async def handle(self, _: Ticket, ctx: WorkflowContext[None, Any]) -> None:
                await ctx.yield_output({"unsupported": object()})

        server = _host(
            lambda _: WorkflowBuilder(name="invalid-output", start_executor=UnsupportedOutput("start")).build()
        )
        response, events = await _invoke(server, {"ticket_id": "T-1", "stream": stream})
        assert response.status_code == (200 if stream else 500)
        assert [item["event"] for item in events] == ["error"]
        message = events[0].get("message") or events[0].get("error")
        assert isinstance(message, str)
        assert "JSON-serializable" in message

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
    async def test_workflow_failure_is_sanitized_and_never_reports_done(
        self, stream: bool, error_type: type[Exception]
    ) -> None:
        class Broken(Executor):
            @handler
            async def handle(self, _: Ticket, ctx: WorkflowContext[None, Any]) -> None:
                raise error_type("private provider-token and checkpoint-id")

        server = _host(lambda _: WorkflowBuilder(name="broken", start_executor=Broken("start")).build())
        response, events = await _invoke(server, {"ticket_id": "T-1", "stream": stream})
        assert response.status_code == (200 if stream else 500)
        assert [item["event"] for item in events] == ["error"]
        assert "private" not in json.dumps(events)


class TestNativeWorkflowPendingReplies:
    @pytest.mark.parametrize("stream", [False, True])
    async def test_json_approval_metadata_is_bound_to_exact_pending_calls_before_dispatch(self, stream: bool) -> None:
        decisions: list[bool] = []

        async def parser(request: Request) -> WorkflowTurn[Ticket]:
            payload = await request.json()
            if "responses" in payload:
                return WorkflowTurn(
                    responses={key: Content.from_dict(value) for key, value in payload["responses"].items()},
                    stream=payload.get("stream", False),
                )
            return WorkflowTurn(input=Ticket(payload["ticket_id"], "Help"), stream=payload.get("stream", False))

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="approvals", start_executor=_ApprovalExecutor(decisions)).build()

        _, events = await _invoke(_host(factory, parser=parser), {"ticket_id": "T-1", "stream": stream})
        pending = [event for event in events if event["event"] == "request_info"]
        assert len(pending) == 2
        valid = {
            item["request_id"]: Content.from_dict(item["data"]).to_function_approval_response(True).to_dict()
            for item in pending
        }
        request_ids = list(valid)
        duplicated = {request_ids[0]: valid[request_ids[0]], request_ids[1]: valid[request_ids[0]]}
        response, rejected = await _invoke(_host(factory, parser=parser), {"responses": duplicated, "stream": stream})
        assert response.status_code == (200 if stream else 400)
        assert [event["event"] for event in rejected] == ["error"]
        assert decisions == []
        forged = json.loads(json.dumps(valid))
        forged[request_ids[0]]["function_call"]["arguments"] = {"ticket_id": "forged"}
        response, rejected = await _invoke(_host(factory, parser=parser), {"responses": forged, "stream": stream})
        assert response.status_code == (200 if stream else 400)
        assert [event["event"] for event in rejected] == ["error"]
        assert decisions == []
        response, _ = await _invoke(_host(factory, parser=parser), {"responses": valid, "stream": stream})
        assert response.status_code == 200
        assert decisions == [True, True]
        response, replayed = await _invoke(_host(factory, parser=parser), {"responses": valid, "stream": stream})
        assert response.status_code == (200 if stream else 400)
        assert [event["event"] for event in replayed] == ["error"]
        assert decisions == [True, True]

    async def test_unallowlisted_reply_batch_is_rejected_before_claim_and_valid_retry_succeeds(self) -> None:
        replies: list[object] = []
        provider = CheckpointStoreProvider()

        async def parser(request: Request) -> WorkflowTurn[str]:
            payload = await request.json()
            if "responses" not in payload:
                return WorkflowTurn(input=payload["input"])
            values = {
                request_id: (
                    UnallowlistedReply(value["value"])
                    if isinstance(value, dict) and value.get("kind") == "custom"
                    else value
                )
                for request_id, value in payload["responses"].items()
            }
            return WorkflowTurn(responses=values)

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="any-reply", start_executor=_AnyReplyExecutor(replies)).build()

        response, events = await _invoke(_host(factory, parser=parser, checkpoints=provider), {"input": "review"})
        assert response.status_code == 200
        request_ids = [event["request_id"] for event in events if event["event"] == "request_info"]
        assert request_ids == ["first", "second"]
        store = FoundryWorkflowBindingStore(FoundryRequestScope("session", None, None, False))
        before, before_etag = await store.get_head("invocations", None)

        invalid = {
            "responses": {
                "first": {"accepted": True},
                "second": {"kind": "custom", "value": "private-token"},
            }
        }
        response, rejected = await _invoke(_host(factory, parser=parser, checkpoints=provider), invalid)
        assert response.status_code == 400
        assert [event["event"] for event in rejected] == ["error"]
        assert "checkpoint-allowlisted" in rejected[0]["error"]
        assert "private-token" not in rejected[0]["error"]
        after, after_etag = await store.get_head("invocations", None)
        assert (after, after_etag) == (before, before_etag)
        assert replies == []

        valid = {"responses": {"first": {"accepted": True}, "second": {"accepted": False}}}
        response, _ = await _invoke(_host(factory, parser=parser, checkpoints=provider), valid)
        assert response.status_code == 200
        assert replies == [{"accepted": True}, {"accepted": False}]

    @pytest.mark.parametrize("stream", [False, True])
    async def test_partial_replies_do_not_consume_authority_and_complete_replies_survive_restart(
        self, stream: bool
    ) -> None:
        replies: list[tuple[str, bool]] = []

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="reviews", start_executor=_ReviewExecutor(replies)).build()

        response, events = await _invoke(_host(factory), {"ticket_id": "T-1", "stream": stream})
        assert response.status_code == 200
        pending = [item for item in events if item["event"] == "request_info"]
        assert len(pending) == 2
        ids = {item["data"]["reviewer"]: item["request_id"] for item in pending}
        first_reply = {"responses": {ids["support"]: {"approved": True}}, "stream": stream}
        response, events = await _invoke(_host(factory), first_reply)
        assert response.status_code == (200 if stream else 400)
        assert [item["event"] for item in events] == ["error"]
        assert replies == []

        complete = {
            "responses": {ids["support"]: {"approved": True}, ids["security"]: {"approved": False}},
            "stream": stream,
        }
        response, events = await _invoke(_host(factory), complete)
        assert response.status_code == 200
        assert sorted(replies) == [("security", False), ("support", True)]
        assert not [item for item in events if item["event"] == "request_info"]

        response, events = await _invoke(_host(factory), complete)
        assert response.status_code == (200 if stream else 400)
        assert [item["event"] for item in events] == ["error"]
        assert len(replies) == 2

    @pytest.mark.parametrize("identity", ["other-sandbox", "other-user", "forged-request"])
    async def test_pending_reply_cannot_cross_scope_or_forge_a_request(self, identity: str) -> None:
        replies: list[tuple[str, bool]] = []

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="reviews", start_executor=_ReviewExecutor(replies)).build()

        server = _host(factory)
        server.config.is_hosted = True
        server.config.session_id = ""
        response, events = await _invoke(
            server, {"ticket_id": "T-1"}, session_id="sandbox-a", user_id="user-a", call_id="first"
        )
        assert response.status_code == 200
        request_id = next(item["request_id"] for item in events if item["event"] == "request_info")
        other = _host(factory)
        other.config.is_hosted = True
        other.config.session_id = ""
        response, _ = await _invoke(
            other,
            {"responses": {"forged" if identity == "forged-request" else request_id: {"approved": True}}},
            session_id="sandbox-b" if identity == "other-sandbox" else "sandbox-a",
            user_id="user-b" if identity == "other-user" else "user-a",
            call_id="second",
        )
        assert response.status_code == 400
        assert replies == []

    async def test_new_input_does_not_discard_pending_replies(self) -> None:
        replies: list[tuple[str, bool]] = []

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="reviews", start_executor=_ReviewExecutor(replies)).build()

        first, events = await _invoke(_host(factory), {"ticket_id": "T-1"})
        assert first.status_code == 200
        request_ids = [item["request_id"] for item in events if item["event"] == "request_info"]
        response, _ = await _invoke(_host(factory), {"ticket_id": "T-2"})
        assert response.status_code == 400
        response, _ = await _invoke(
            _host(factory), {"responses": {request_id: {"approved": True} for request_id in request_ids}}
        )
        assert response.status_code == 200
        assert len(replies) == 2

    async def test_invalid_mixed_reply_batch_does_not_consume_valid_authority(self) -> None:
        replies: list[tuple[str, bool]] = []

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="reviews", start_executor=_ReviewExecutor(replies)).build()

        _, events = await _invoke(_host(factory), {"ticket_id": "T-1"})
        ids = [item["request_id"] for item in events if item["event"] == "request_info"]
        response, _ = await _invoke(
            _host(factory), {"responses": {ids[0]: {"approved": True}, "forged": {"approved": True}}}
        )
        assert response.status_code == 400
        assert replies == []
        response, _ = await _invoke(_host(factory), {"responses": {key: {"approved": True} for key in ids}})
        assert response.status_code == 200
        assert len(replies) == 2


class TestNativeWorkflowConcurrency:
    async def test_partial_claim_is_repaired_and_reported_as_blocked(self) -> None:
        scope = FoundryRequestScope("session", None, None, False)
        store = FoundryWorkflowBindingStore(scope)
        owner = "interrupted-owner"
        await store.save_head(
            WorkflowHead("invocations", None, response_id="interrupted", owner=owner),
            expected_etag=None,
        )
        server = _host(lambda _: WorkflowBuilder(name="tickets", start_executor=_TicketExecutor([])).build())
        response, events = await _invoke(server, {"ticket_id": "T-1"})
        assert response.status_code == 409
        assert events[0]["event"] == "error"
        assert events[0]["status"] == 409
        record, _ = await store.get_response("interrupted")
        head, _ = await store.get_head("invocations", None)
        assert record is not None and record.status == "blocked" and record.owner == owner
        assert head is not None and head.blocked

    @pytest.mark.parametrize("same_host", [False, True])
    async def test_same_session_serializes_locally_or_fails_claim_cas_before_dispatch(self, same_host: bool) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()
        runs: list[str] = []

        class Waiting(Executor):
            @handler
            async def handle(self, ticket: Ticket, ctx: WorkflowContext[None, str]) -> None:
                runs.append(ticket.ticket_id)
                if ticket.ticket_id == "first":
                    entered.set()
                    await release.wait()
                await ctx.yield_output(ticket.ticket_id)

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="concurrent", start_executor=Waiting("start")).build()

        server = _host(factory)
        first = asyncio.create_task(_invoke(server, {"ticket_id": "first"}, call_id="call-first"))
        second: asyncio.Task[Any] | None = None
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            second = asyncio.create_task(
                _invoke(server if same_host else _host(factory), {"ticket_id": "second"}, call_id="call-second")
            )
            if same_host:
                await asyncio.sleep(0.05)
                assert runs == ["first"]
                assert not second.done()
            else:
                second_response, events = await asyncio.wait_for(second, timeout=5)
                assert second_response.status_code == 409
                assert [item["event"] for item in events] == ["error"]
                assert runs == ["first"]
            release.set()
            assert (await asyncio.wait_for(first, timeout=5))[0].status_code == 200
            if same_host:
                assert (await asyncio.wait_for(second, timeout=5))[0].status_code == 200
                assert runs == ["first", "second"]
            assert len(server._session_locks) == 0
        finally:
            release.set()
            for task in (first, second):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*(task for task in (first, second) if task is not None), return_exceptions=True)


class TestNativeWorkflowAgentExecutors:
    async def test_registry_backed_agent_resources_are_owned_and_reuse_is_rejected(self) -> None:
        resources: list[tuple[str, str | None]] = []

        def fresh(_request: Request) -> Workflow:
            options: ChatOptions = {"store": False}
            agent = Agent(client=_ContextClient([], resources), name="registered", default_options=options)
            return WorkflowBuilder(name="registry", start_executor=_RegistryExecutor(agent)).build()

        for number in (1, 2):
            response, _ = await _invoke(_host(fresh), {"ticket_id": f"T-{number}"}, call_id=f"call-{number}")
            assert response.status_code == 200
        assert resources == [
            ("enter", "call-1"),
            ("exit", "call-1"),
            ("enter", "call-2"),
            ("exit", "call-2"),
        ]

        options: ChatOptions = {"store": False}
        shared = Agent(client=_ContextClient([], resources), name="shared", default_options=options)

        def reused(_request: Request) -> Workflow:
            return WorkflowBuilder(name="registry", start_executor=_RegistryExecutor(shared)).build()

        server = _host(reused)
        assert (await _invoke(server, {"ticket_id": "T-3"}, session_id="reused"))[0].status_code == 200
        response, _ = await _invoke(server, {"ticket_id": "T-4"}, session_id="reused")
        assert response.status_code == 500

    @pytest.mark.parametrize("failure", ["store", "overrides"])
    async def test_raw_factory_rejects_unsafe_or_unmaterialized_defaults_before_resources_and_dispatch(
        self, failure: str
    ) -> None:
        calls: list[dict[str, Any]] = []
        resources: list[tuple[str, str | None]] = []

        def factory(_request: Request) -> Workflow:
            options: ChatOptions = {
                "store": failure == "store",
                "temperature": 0.2 if failure == "overrides" else 0.7,
            }
            agent = RawAgent(
                client=_ContextClient(calls, resources),
                name="raw",
                default_options=options,
            )
            return WorkflowBuilder(name="raw-agent", start_executor=AgentExecutor(agent, id="responder")).build()

        server = _host(
            factory,
            parser=lambda _: WorkflowTurn(input="hello", client_kwargs={"options": {"temperature": 0.7}}),
        )
        response, _ = await _invoke(server, {})
        assert response.status_code == 400
        assert calls == resources == []

    async def test_borrowed_raw_workflow_cannot_forge_fresh_factory_authority(self) -> None:
        calls: list[dict[str, Any]] = []
        resources: list[tuple[str, str | None]] = []
        options: ChatOptions = {"store": False, "temperature": 0.7}
        agent = RawAgent(client=_ContextClient(calls, resources), name="raw", default_options=options)
        workflow = WorkflowBuilder(name="raw-agent", start_executor=AgentExecutor(agent, id="responder")).build()
        server = _host(
            workflow,
            parser=lambda _: WorkflowTurn(input="hello", client_kwargs={"options": {"temperature": 0.7}}),
        )
        response, _ = await _invoke(server, {"fresh_factory": True})
        assert response.status_code == 400
        assert calls == resources == []

    @pytest.mark.parametrize("bare_raw", [False, True])
    @pytest.mark.parametrize("stream", [False, True])
    async def test_unfinished_provider_tokens_are_not_published_or_committed(
        self, bare_raw: bool, stream: bool
    ) -> None:
        class BackgroundClient(_ContextClient):
            def _inner_get_response(
                self, *, messages: Sequence[Message], stream: bool, options: Mapping[str, Any], **kwargs: Any
            ) -> Any:
                async def updates() -> AsyncIterator[ChatResponseUpdate]:
                    yield ChatResponseUpdate(
                        role="assistant", contents=[Content.from_text("unfinished")], continuation_token={}
                    )

                async def complete() -> ChatResponse:
                    return ChatResponse(messages=[Message("assistant", ["unfinished"])], continuation_token={})

                return ResponseStream(updates(), finalizer=ChatResponse.from_updates) if stream else complete()

        def factory(_request: Request) -> Workflow:
            agent_type = RawAgent if bare_raw else Agent
            options: ChatOptions = {"store": False}
            agent = agent_type(client=BackgroundClient([], []), default_options=options)
            return WorkflowBuilder(name="background", start_executor=AgentExecutor(agent, id="responder")).build()

        response, events = await _invoke(
            _host(factory, parser=lambda _: WorkflowTurn(input="hello", stream=stream)), {}
        )
        assert response.status_code == (200 if stream else 500)
        assert [event["event"] for event in events] == ["error"]
        assert "continuation_token" not in json.dumps(events)

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("bare_raw", [False, True])
    async def test_real_agent_client_options_tool_context_and_owned_resources_refresh_each_turn(
        self, stream: bool, bare_raw: bool
    ) -> None:
        calls: list[dict[str, Any]] = []
        resources: list[tuple[str, str | None]] = []
        tools: list[tuple[str | None, str | None]] = []
        agents: list[RawAgent[Any]] = []
        defaults: list[dict[str, Any]] = []

        async def factory(request: Request) -> Workflow:
            @tool
            def inspect_runtime(ctx: FunctionInvocationContext) -> str:
                """Inspect only the explicit trusted function context."""
                tools.append((get_request_context().call_id, ctx.kwargs.get("tenant_id")))
                return "checked"

            payload = await request.json()
            agent_type = RawAgent if bare_raw else Agent
            options: ChatOptions = (
                {"store": False, "temperature": payload["temperature"]}
                if bare_raw
                else {"store": True, "temperature": 0.2}
            )
            agent = agent_type(
                client=_ContextClient(calls, resources),
                name="responder",
                tools=[inspect_runtime],
                context_providers=[InMemoryHistoryProvider()],
                default_options=options,
            )
            agents.append(agent)
            defaults.append(dict(agent.default_options))
            return WorkflowBuilder(name="real-agent", start_executor=AgentExecutor(agent, id="responder")).build()

        async def parser(request: Request) -> WorkflowTurn[str]:
            payload = await request.json()
            return WorkflowTurn(
                input=payload["message"],
                stream=payload.get("stream", False),
                client_kwargs={"options": {"temperature": payload["temperature"]}, "application_marker": "retained"},
                function_invocation_kwargs={"tenant_id": "trusted-tenant"},
            )

        for number in (1, 2):
            server = _host(factory, parser=parser)
            server.config.is_hosted = True
            server.config.session_id = ""
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
                response = await client.post(
                    "/invocations",
                    params={"agent_session_id": "session"},
                    headers={"x-agent-user-id": "trusted-user", "x-agent-foundry-call-id": f"trusted-{number}"},
                    json={"message": "inspect", "temperature": 0.7, "stream": stream},
                )
            assert response.status_code == 200
            if stream:
                assert _sse_events(response.text)[-1] == {"event": "done", "session_id": "session"}
            else:
                assert any(event["type"] == "output" for event in response.json()["output"])
        assert tools == [("trusted-1", "trusted-tenant"), ("trusted-2", "trusted-tenant")]
        assert resources == [
            ("enter", "trusted-1"),
            ("exit", "trusted-1"),
            ("enter", "trusted-2"),
            ("exit", "trusted-2"),
        ]
        assert [call["call_id"] for call in calls] == ["trusted-1", "trusted-1", "trusted-2", "trusted-2"]
        assert all(call["options"]["temperature"] == 0.7 and call["options"]["store"] is False for call in calls)
        assert all(
            call["kwargs"]["application_marker"] == "retained" and "options" not in call["kwargs"] for call in calls
        )
        expected_defaults = {"store": False, "temperature": 0.7} if bare_raw else {"store": True, "temperature": 0.2}
        assert all(agent.default_options == original for agent, original in zip(agents, defaults))
        assert all(
            all(agent.default_options[key] == value for key, value in expected_defaults.items()) for agent in agents
        )


class TestNativeWorkflowStreamingLifecycle:
    @pytest.mark.parametrize("stream", [False, True])
    async def test_final_head_cas_failure_never_publishes_pending_authority_or_success(self, stream: bool) -> None:
        replies: list[tuple[str, bool]] = []
        save_head = FoundryWorkflowBindingStore.save_head

        async def lose_final_cas(
            store: FoundryWorkflowBindingStore, head: WorkflowHead, *, expected_etag: str | None
        ) -> str:
            return await save_head(
                store,
                head,
                expected_etag="deliberately-stale-etag" if head.response_id is None else expected_etag,
            )

        server = _host(lambda _: WorkflowBuilder(name="reviews", start_executor=_ReviewExecutor(replies)).build())
        with patch.object(FoundryWorkflowBindingStore, "save_head", lose_final_cas):
            response, events = await _invoke(server, {"ticket_id": "T-1", "stream": stream})
        assert response.status_code == (200 if stream else 409)
        assert [item["event"] for item in events] == ["error"]
        assert events[0]["status"] == 409
        assert replies == []

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("limit_kind", ["events", "bytes"])
    async def test_snapshot_retention_limits_abort_without_done_or_cross_session_impact(
        self, stream: bool, limit_kind: str
    ) -> None:
        class Fanout(Executor):
            @handler
            async def handle(self, _: Ticket, ctx: WorkflowContext[None, str]) -> None:
                values = ["one", "two", "three"] if limit_kind == "events" else ["x" * 512]
                for value in values:
                    await ctx.yield_output(value)

        server = _host(lambda _: WorkflowBuilder(name="fanout", start_executor=Fanout("start")).build())
        event_limit = 2 if limit_kind == "events" else 100
        byte_limit = 4096 if limit_kind == "events" else 128
        with (
            patch(
                "agent_framework_foundry_hosting._invocations._MAX_WORKFLOW_SNAPSHOT_EVENTS",
                event_limit,
            ),
            patch(
                "agent_framework_foundry_hosting._invocations._MAX_WORKFLOW_SNAPSHOT_BYTES",
                byte_limit,
            ),
        ):
            response, events = await _invoke(server, {"ticket_id": "T-1", "stream": stream}, session_id="limited")
        assert response.status_code == (200 if stream else 500)
        assert events[-1]["event"] == "error"
        message = events[-1].get("message") or events[-1].get("error")
        assert isinstance(message, str)
        assert "bounded Invocations snapshot limit" in message
        assert not any(event["event"] == "done" for event in events)
        store = FoundryWorkflowBindingStore(FoundryRequestScope("limited", None, None, False))
        head, _ = await store.get_head("invocations", None)
        assert head is not None and head.blocked

        other, other_events = await _invoke(
            _host(lambda _: WorkflowBuilder(name="tickets", start_executor=_TicketExecutor([])).build()),
            {"ticket_id": "T-2"},
            session_id="unrelated",
        )
        assert other.status_code == 200
        assert other_events[0]["event"] == "output"

    async def test_same_call_replays_complete_committed_pending_batch_after_first_frame_disconnect(self) -> None:
        replies: list[tuple[str, bool]] = []
        starts: list[str] = []
        delivered: list[dict[str, Any]] = []

        def factory(_request: Request) -> Workflow:
            return WorkflowBuilder(name="reviews", start_executor=_ReviewExecutor(replies, starts)).build()

        server = _host(factory)
        server.config.is_hosted = True
        server.config.session_id = ""
        server.config.sse_keepalive_interval = 0
        received = False
        body = json.dumps({"ticket_id": "T-1", "stream": True}).encode()

        async def receive() -> Any:
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body}
            await asyncio.Event().wait()
            return {"type": "http.disconnect"}

        async def send(message: Any) -> None:
            if message["type"] == "http.response.body":
                delivered.extend(_sse_events(message.get("body", b"").decode()))
                if len(delivered) == 1:
                    raise OSError("disconnected after the first durable pending frame")

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "method": "POST",
            "scheme": "http",
            "path": "/invocations",
            "root_path": "",
            "query_string": b"agent_session_id=session",
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-agent-foundry-call-id", b"pending-call"),
                (b"x-agent-user-id", b"user-a"),
            ],
            "server": ("test", 80),
            "client": ("test", 1234),
        }
        with pytest.raises(ClientDisconnect):
            await asyncio.wait_for(server(scope, receive, send), timeout=5)
        assert [item["event"] for item in delivered] == ["request_info"]
        assert starts == ["T-1"]
        trusted_scope = FoundryRequestScope("session", "user-a", "inspect", True)
        store = FoundryWorkflowBindingStore(trusted_scope)
        before, before_etag = await store.get_head("invocations", None)

        def hosted() -> InvocationsHostServer:
            replacement = _host(factory)
            replacement.config.is_hosted = True
            replacement.config.session_id = ""
            return replacement

        headers = {"x-agent-foundry-call-id": "pending-call", "x-agent-user-id": "user-a"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=hosted()), base_url="http://test") as client:
            replay_json = await client.post(
                "/invocations",
                params={"agent_session_id": "session"},
                headers=headers,
                json={"ticket_id": "T-1", "stream": False},
            )
        assert replay_json.status_code == 200
        complete = replay_json.json()["output"]
        assert [item["type"] for item in complete] == ["request_info", "request_info"]
        assert complete[0]["request_id"] == delivered[0]["request_id"]
        assert [item["data"]["reviewer"] for item in complete] == ["support", "security"]
        assert starts == ["T-1"]

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=hosted()), base_url="http://test") as client:
            replay_sse = await client.post(
                "/invocations",
                params={"agent_session_id": "session"},
                headers=headers,
                json={"ticket_id": "T-1", "stream": True},
            )
        replay_events = _sse_events(replay_sse.text)
        assert [item["event"] for item in replay_events] == ["request_info", "request_info", "done"]
        assert [item["request_id"] for item in replay_events[:-1]] == [item["request_id"] for item in complete]
        assert starts == ["T-1"]
        after, after_etag = await store.get_head("invocations", None)
        assert (after, after_etag) == (before, before_etag)

        different_headers = {"x-agent-foundry-call-id": "different-call", "x-agent-user-id": "user-a"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=hosted()), base_url="http://test") as client:
            different = await client.post(
                "/invocations",
                params={"agent_session_id": "session"},
                headers=different_headers,
                json={"ticket_id": "T-1"},
            )
        assert different.status_code == 400
        assert starts == ["T-1"]

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=hosted()), base_url="http://test") as client:
            cross_scope = await client.post(
                "/invocations",
                params={"agent_session_id": "other-session"},
                headers=headers,
                json={"ticket_id": "T-1"},
            )
        assert cross_scope.status_code == 200
        assert [item["request_id"] for item in cross_scope.json()["output"]] != [
            item["request_id"] for item in complete
        ]
        assert starts == ["T-1", "T-1"]

        reply_headers = {"x-agent-foundry-call-id": "reply-call", "x-agent-user-id": "user-a"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=hosted()), base_url="http://test") as client:
            response = await client.post(
                "/invocations",
                params={"agent_session_id": "session"},
                headers=reply_headers,
                json={"responses": {item["request_id"]: {"approved": True} for item in complete}},
            )
        assert response.status_code == 200
        assert sorted(replies) == [("security", True), ("support", True)]

    @pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
    @pytest.mark.parametrize("keep_alive", [False, True])
    @pytest.mark.parametrize("executor_kind", ["typed", "agent", "raw"])
    async def test_sdk_disconnect_closes_core_stream_without_success(
        self, spec_version: str, keep_alive: bool, executor_kind: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        entered = asyncio.Event()
        closed = asyncio.Event()
        disconnected = asyncio.Event()
        messages: list[Any] = []
        cleanup_calls: list[str | None] = []
        factory_calls: list[str | None] = []
        client_resources: list[tuple[str, str | None]] = []

        class Idle(Executor):
            @handler
            async def handle(self, _: Ticket, ctx: WorkflowContext[None, str]) -> None:
                entered.set()
                try:
                    if not keep_alive:
                        await ctx.yield_output("first")
                    await asyncio.Event().wait()
                finally:
                    cleanup_calls.append(get_request_context().call_id)
                    closed.set()

        class SlowClient(_ContextClient):
            def _inner_get_response(
                self, *, messages: Sequence[Message], stream: bool, options: Mapping[str, Any], **kwargs: Any
            ) -> Any:
                async def updates() -> AsyncIterator[ChatResponseUpdate]:
                    entered.set()
                    try:
                        if not keep_alive:
                            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text("first")])
                        await asyncio.Event().wait()
                    finally:
                        cleanup_calls.append(get_request_context().call_id)
                        closed.set()

                return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

        def factory(_request: Request) -> Workflow:
            factory_calls.append(get_request_context().call_id)
            if executor_kind == "typed":
                return WorkflowBuilder(name="idle", start_executor=Idle("start")).build()
            agent_type = RawAgent if executor_kind == "raw" else Agent
            options: ChatOptions = {"store": False}
            agent = agent_type(client=SlowClient([], client_resources), default_options=options)
            return WorkflowBuilder(name="idle", start_executor=AgentExecutor(agent, id="start")).build()

        server = _host(
            factory,
            parser=_parse_ticket if executor_kind == "typed" else lambda _: WorkflowTurn(input="start", stream=True),
        )
        server.config.sse_keepalive_interval = 1 if keep_alive else 0
        body = json.dumps({"ticket_id": "T-1", "stream": True}).encode()
        received = False

        async def receive() -> Any:
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message: Any) -> None:
            messages.append(message)
            expected = b": keep-alive\n\n" if keep_alive else b"event: output"
            if message["type"] == "http.response.body" and expected in message.get("body", b""):
                assert entered.is_set()
                if spec_version == "2.4":
                    raise OSError("disconnected")
                disconnected.set()
                await asyncio.Event().wait()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": spec_version},
            "method": "POST",
            "scheme": "http",
            "path": "/invocations",
            "root_path": "",
            "query_string": b"agent_session_id=session",
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-agent-foundry-call-id", b"trusted-call"),
                (b"x-agent-user-id", b"trusted-user"),
            ],
            "server": ("test", 80),
            "client": ("test", 1234),
        }
        with _context(session_id="ambient", call_id="ambient-call"):
            ambient = get_request_context()
            if spec_version == "2.4":
                with pytest.raises(ClientDisconnect):
                    await asyncio.wait_for(server(scope, receive, send), timeout=5)
            else:
                await asyncio.wait_for(server(scope, receive, send), timeout=5)
            assert get_request_context() is ambient
        assert closed.is_set()
        assert factory_calls == cleanup_calls == ["trusted-call"]
        if executor_kind != "typed":
            assert client_resources == [("enter", "trusted-call"), ("exit", "trusted-call")]
        assert not any(b"event: done" in message.get("body", b"") for message in messages)
        assert all(not lock.locked() for lock in server._session_locks.values())
        # Cancelled-task tracebacks can retain released locks until their reference cycles are collected.
        gc.collect()
        assert len(server._session_locks) == 0
        assert "different Context" not in caplog.text

    async def test_json_and_sse_use_the_real_invocations_asgi_route(self) -> None:
        calls: list[tuple[Ticket, str | None]] = []
        server = _host(lambda _: WorkflowBuilder(name="tickets", start_executor=_TicketExecutor(calls)).build())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
            first = await client.post("/invocations", json={"ticket_id": "T-1"})
            assert first.status_code == 200
            assert first.headers["content-type"] == "application/json"
            session_id = first.headers["x-agent-session-id"]
            assert first.json()["output"][0]["data"]["turn"] == 1
            second = await client.post(
                "/invocations",
                params={"agent_session_id": session_id},
                json={"ticket_id": "T-2", "stream": True},
            )
            assert second.status_code == 200
            assert second.headers["content-type"].startswith("text/event-stream")
            frames = _sse_events(second.text)
            assert frames[0]["data"]["turn"] == 2
            assert frames[-1] == {"event": "done", "session_id": session_id}
