# Copyright (c) Microsoft. All rights reserved.

"""HTTP round-trip tests for ResponsesHostServer.

These tests exercise the full HTTP pipeline using httpx.AsyncClient with
ASGITransport — no real server process is started. Requests go through
the Starlette routing stack, the Responses API middleware, and arrive at
the registered _handle_create handler.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast, overload
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from agent_framework import (
    Agent,
    AgentExecutorRequest,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    HistoryProvider,
    InMemoryHistoryProvider,
    Message,
    RawAgent,
    ResponseStream,
    ServiceSessionId,
    SessionStore,
    SupportsAgentRun,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    tool,
)
from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.responses import InMemoryResponseProvider, ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse, Item, OutputItem
from mcp import McpError
from mcp.types import ErrorData
from typing_extensions import Any

from agent_framework_foundry_hosting import ResponsesHostServer
from agent_framework_foundry_hosting._responses import (
    CONSENT_ERROR_CODE,
    ConsentError,
    _item_to_message,  # pyright: ignore[reportPrivateUsage]
    _output_item_to_message,  # pyright: ignore[reportPrivateUsage]
    consent_url_from_error,
)
from agent_framework_foundry_hosting._state_store import (
    AgentSessionStoreProvider,
    CheckpointStoreProvider,
    FunctionApprovalStoreProvider,
)


def _function_approval_store(request: Content) -> MagicMock:
    storage = MagicMock()
    storage.load_approval_request = AsyncMock(return_value=request)
    return storage


def _make_function_approval_request_content(
    *,
    request_id: str = "apr_test",
    call_id: str = "call_1",
    name: str = "delete_file",
    arguments: str = '{"path": "/foo"}',
    server_label: str = "my_server",
) -> Content:
    """Build a function_approval_request Content with an embedded function_call."""
    function_call = Content.from_function_call(
        call_id, name, arguments=arguments, additional_properties={"server_label": server_label}
    )
    return Content.from_function_approval_request(request_id, function_call)


# region Helpers


async def _raising_updates(
    message: str,
    *,
    initial_updates: Sequence[AgentResponseUpdate] = (),
    before_raise: Callable[[], None] | None = None,
) -> AsyncIterator[AgentResponseUpdate]:
    if before_raise is not None:
        before_raise()
    for update in initial_updates:
        yield update
    raise RuntimeError(message)


def _make_agent(
    *,
    response: AgentResponse | None = None,
    stream_updates: list[AgentResponseUpdate] | None = None,
    raw_agent: bool = True,
) -> MagicMock:
    """Create a mock agent implementing SupportsAgentRun.

    ``ResponsesHostServer`` always invokes the inner agent in streaming mode. ``response`` is a convenience for
    tests that only care about complete output messages: the helper converts those messages into streamed updates.
    ``stream_updates`` is for tests that need explicit chunk boundaries to verify streaming event behavior.
    """
    agent = MagicMock(spec=RawAgent) if raw_agent else MagicMock()
    agent.id = "test-agent"
    agent.name = "Test Agent"
    agent.description = "A mock agent for testing"
    agent.context_providers = []

    def create_session(*, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    agent.create_session.side_effect = create_session

    if response is not None:

        async def _response_gen() -> AsyncIterator[AgentResponseUpdate]:
            for message in response.messages:
                yield AgentResponseUpdate(contents=message.contents, role=message.role)

        def run_response(*args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del args, kwargs
            return ResponseStream(_response_gen(), finalizer=AgentResponse.from_updates)

        agent.run = MagicMock(side_effect=run_response)

    if stream_updates is not None:

        async def _stream_gen() -> AsyncIterator[AgentResponseUpdate]:
            for update in stream_updates:
                yield update

        def run_streaming(*args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del args
            assert kwargs.get("stream") is True
            return ResponseStream(_stream_gen(), finalizer=AgentResponse.from_updates)

        agent.run = MagicMock(side_effect=run_streaming)

    return agent


class _RecordingHistoryClient(BaseChatClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[Message]] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        del options, kwargs
        assert stream is True, "The inner agent only runs in stream mode in Foundry Hosted Agents."
        self.calls.append(list(messages))

        async def stream_response() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(contents=[Content.from_text("recorded")], role="assistant")

        return ResponseStream(stream_response(), finalizer=ChatResponse.from_updates)


class _PerServiceCallHistoryProvider(HistoryProvider):
    def __init__(self) -> None:
        super().__init__("per_service_call_history", load_messages=False)
        self.save_calls = 0

    async def get_messages(
        self, session_id: str | None, *, state: dict[str, Any] | None = None, **kwargs: Any
    ) -> list[Message]:
        del session_id, state, kwargs
        return []

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del session_id, messages, state, kwargs
        self.save_calls += 1


class _FunctionLoopRecordingClient(
    FunctionInvocationLayer[Any],
    ChatMiddlewareLayer[Any],
    BaseChatClient[Any],
):
    def __init__(self, provider: _PerServiceCallHistoryProvider) -> None:
        super().__init__(middleware=[])
        self._provider = provider
        self.calls: list[list[Message]] = []
        self.saves_before_call: list[int] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        del options, kwargs
        assert stream is True, "The inner agent only runs in stream mode in Foundry Hosted Agents."
        self.calls.append(list(messages))
        self.saves_before_call.append(self._provider.save_calls)
        call_number = len(self.calls)

        async def stream_response() -> AsyncIterator[ChatResponseUpdate]:
            if call_number == 1:
                yield ChatResponseUpdate(
                    contents=[
                        Content.from_function_call(
                            call_id="call_1",
                            name="lookup_weather",
                            arguments='{"location": "Seattle"}',
                        )
                    ],
                    role="assistant",
                )
            else:
                yield ChatResponseUpdate(contents=[Content.from_text("It is sunny in Seattle.")], role="assistant")

        return ResponseStream(stream_response(), finalizer=ChatResponse.from_updates)


@tool(name="lookup_weather", approval_mode="never_require")
def _lookup_weather(location: str) -> str:
    return f"Weather in {location}: sunny"


class _FailingSessionStore(SessionStore):
    def __init__(self) -> None:
        super().__init__()
        self.set_attempts = 0

    async def set(self, session_id: str, session: AgentSession) -> None:
        del session_id, session
        self.set_attempts += 1
        raise OSError("session storage is full")


_SESSION_STORE_UNSET = object()


def _make_server(agent: Any, **kwargs: Any) -> ResponsesHostServer:
    """Create a ResponsesHostServer, optionally replacing its private store for tests."""
    session_store = kwargs.pop("session_store", _SESSION_STORE_UNSET)
    response_store = kwargs.pop("response_store", InMemoryResponseProvider())
    server = ResponsesHostServer(agent, store=response_store, **kwargs)
    if session_store is not _SESSION_STORE_UNSET:
        provider = MagicMock(spec=AgentSessionStoreProvider)
        provider.get_store.return_value = cast(SessionStore | None, session_store)
        server._session_storage_provider = provider  # pyright: ignore[reportPrivateUsage]
    return server


async def _post(
    server: ResponsesHostServer,
    *,
    input_text: str = "Hello",
    model: str = "test-model",
    stream: bool = False,
    temperature: float | None = None,
    top_p: float | None = None,
    max_output_tokens: int | None = None,
    parallel_tool_calls: bool | None = None,
    previous_response_id: str | None = None,
    conversation_id: str | None = None,
) -> httpx.Response:
    """Send a POST /responses request through the ASGI transport."""
    payload: dict[str, Any] = {"model": model, "input": input_text, "stream": stream}
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens
    if parallel_tool_calls is not None:
        payload["parallel_tool_calls"] = parallel_tool_calls
    if previous_response_id is not None:
        payload["previous_response_id"] = previous_response_id
    if conversation_id is not None:
        payload["conversation"] = conversation_id

    transport = httpx.ASGITransport(app=server)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/responses", json=payload)


def _parse_sse_events(body: str) -> list[dict[str, Any]]:
    """Parse SSE text into a list of event dicts with 'event' and 'data' keys."""
    events: list[dict[str, Any]] = []
    current_event: str | None = None
    current_data_lines: list[str] = []

    for line in body.split("\n"):
        if line.startswith("event: "):
            current_event = line[len("event: ") :]
        elif line.startswith("data: "):
            current_data_lines.append(line[len("data: ") :])
        elif line.strip() == "" and current_event is not None:
            data_str = "\n".join(current_data_lines)
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = data_str
            events.append({"event": current_event, "data": data})
            current_event = None
            current_data_lines = []

    return events


def _sse_event_types(events: list[dict[str, Any]]) -> list[str]:
    """Extract event type strings from parsed SSE events."""
    return [e["event"] for e in events]


# endregion


# region Initialization


class TestResponsesHostServerInit:
    def test_init_basic(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        server = _make_server(agent)
        assert server is not None
        assert len(agent.context_providers) == 1
        history_sentinel = agent.context_providers[0]
        assert isinstance(history_sentinel, InMemoryHistoryProvider)
        assert history_sentinel.load_messages is True
        assert history_sentinel.store_inputs is True
        assert history_sentinel.store_outputs is True

    def test_init_uses_default_store_providers(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        server = ResponsesHostServer(agent, store=InMemoryResponseProvider())

        assert isinstance(
            server._session_storage_provider,  # pyright: ignore[reportPrivateUsage]
            AgentSessionStoreProvider,
        )
        assert isinstance(
            server._checkpoint_storage_provider,  # pyright: ignore[reportPrivateUsage]
            CheckpointStoreProvider,
        )
        assert isinstance(
            server._function_approval_storage_provider,  # pyright: ignore[reportPrivateUsage]
            FunctionApprovalStoreProvider,
        )

    def test_init_rejects_history_provider_with_load_messages(self) -> None:

        class _LoadMessagesHistoryProvider(HistoryProvider):
            async def get_messages(
                self, session_id: str | None, *, state: dict[str, Any] | None = None, **kwargs: Any
            ) -> list[Message]:
                del session_id, state, kwargs
                return []

            async def save_messages(
                self,
                session_id: str | None,
                messages: Sequence[Message],
                *,
                state: dict[str, Any] | None = None,
                **kwargs: Any,
            ) -> None:
                del session_id, messages, state, kwargs

        hp = _LoadMessagesHistoryProvider(source_id="test", load_messages=True)
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        agent.context_providers = [hp]
        with pytest.raises(RuntimeError, match="history provider"):
            ResponsesHostServer(agent)

    async def test_previous_response_requires_existing_agent_session(self) -> None:
        agent = _make_agent()
        server = _make_server(agent, session_store=SessionStore())
        request = CreateResponse(model="m", input="hi", previous_response_id="response-missing")
        context = ResponseContext(response_id="response-current", mode_flags=MagicMock())

        handler = await server._handle_response(request, context, asyncio.Event())  # pyright: ignore[reportPrivateUsage]
        events = [event async for event in handler]

        failed_events = [event for event in events if event.get("type") == "response.failed"]
        assert len(failed_events) == 1
        failed_event = cast(Mapping[str, Any], failed_events[0])
        response = cast(Mapping[str, Any], failed_event["response"])
        error = cast(Mapping[str, Any], response["error"])
        assert "Cannot find an existing agent session for previous_response_id=response-missing." in error["message"]
        agent.run.assert_not_called()
        agent.create_session.assert_not_called()


# endregion


# region Session persistence


class TestAgentSessionPersistence:
    async def test_previous_response_chain_restores_session_state(self) -> None:
        seen_counts: list[int] = []
        seen_session_ids: list[str] = []

        def run_with_state(*args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del args
            session = kwargs["session"]
            assert isinstance(session, AgentSession)
            count = int(session.state.get("turn_count", 0)) + 1
            session.state["turn_count"] = count
            seen_counts.append(count)
            seen_session_ids.append(session.session_id)

            async def updates() -> AsyncIterator[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=[Content.from_text(f"turn {count}")], role="assistant")

            return ResponseStream(updates())

        agent = _make_agent()
        agent.run = MagicMock(side_effect=run_with_state)
        server = _make_server(agent)

        first = await _post(server)
        second = await _post(server, previous_response_id=first.json()["id"])
        third = await _post(server, previous_response_id=first.json()["id"])

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 200
        assert seen_counts == [1, 2, 2]
        assert seen_session_ids[0] == seen_session_ids[1] == seen_session_ids[2]

        provider = server._session_storage_provider  # pyright: ignore[reportPrivateUsage]
        assert provider is not None
        session_store = provider.get_store(config=server.config, platform_context=get_request_context())
        assert session_store is not None
        first_session = await session_store.get(first.json()["id"])
        second_session = await session_store.get(second.json()["id"])
        third_session = await session_store.get(third.json()["id"])
        assert first_session is not None
        assert second_session is not None
        assert third_session is not None
        assert first_session.state["turn_count"] == 1
        assert second_session.state["turn_count"] == 2
        assert third_session.state["turn_count"] == 2
        assert first_session.session_id == second_session.session_id == third_session.session_id

    async def test_responses_history_is_not_duplicated_by_default_local_history(self) -> None:
        client = _RecordingHistoryClient()
        agent = Agent(client=client, name="History Test Agent")
        store = SessionStore()
        server = _make_server(agent, session_store=store)

        first = await _post(server, input_text="first")
        await _post(server, input_text="second", previous_response_id=first.json()["id"])

        assert [[message.text for message in call] for call in client.calls] == [
            ["first"],
            ["first", "recorded", "second"],
        ]
        assert [provider.source_id for provider in agent.context_providers] == ["_foundry_responses_history"]

        session_id = first.json()["id"]
        stored = await store.get(session_id)
        assert stored is not None
        assert InMemoryHistoryProvider.DEFAULT_SOURCE_ID not in stored.state
        assert "_foundry_responses_history" not in stored.state

    async def test_per_service_call_persistence_preserves_function_loop_history(self) -> None:
        provider = _PerServiceCallHistoryProvider()
        client = _FunctionLoopRecordingClient(provider)
        agent = Agent(
            client=client,
            tools=[_lookup_weather],
            context_providers=[provider],
            require_per_service_call_history_persistence=True,
        )
        store = SessionStore()
        server = _make_server(agent, session_store=store)

        response = await _post(server, input_text="What's the weather in Seattle?")

        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert len(client.calls) == 2
        assert client.saves_before_call == [0, 1]
        assert provider.save_calls == 2
        assert [content.type for message in client.calls[1] for content in message.contents] == [
            "text",
            "function_call",
            "function_result",
        ]
        assert client.calls[1][0].text == "What's the weather in Seattle?"
        assert client.calls[1][1].contents[0].call_id == "call_1"
        assert client.calls[1][2].contents[0].call_id == "call_1"

        stored = await store.get(response.json()["id"])
        assert stored is not None
        assert "_foundry_responses_history" not in stored.state

    async def test_run_saves_final_session_state(self) -> None:
        store = SessionStore()
        agent = _make_agent()

        def run(*_args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del _args
            session = kwargs["session"]
            assert isinstance(session, AgentSession)

            async def updates() -> AsyncIterator[AgentResponseUpdate]:
                session.state["run_complete"] = True
                yield AgentResponseUpdate(contents=[Content.from_text("done")], role="assistant")

            return ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        agent.run = MagicMock(side_effect=run)
        server = _make_server(agent, session_store=store)

        response = await _post(server, stream=True)
        session_id = _parse_sse_events(response.text)[-1]["data"]["response"]["id"]

        stored = await store.get(session_id)

        assert stored is not None
        assert stored.state["run_complete"] is True

    async def test_failed_run_still_saves_mutated_session(self) -> None:
        store = SessionStore()
        agent = _make_agent()

        def failing_run(*_args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del _args
            session = kwargs["session"]
            assert isinstance(session, AgentSession)

            return ResponseStream(
                _raising_updates(
                    "agent failed",
                    before_raise=lambda: session.state.__setitem__("before_failure", "saved"),
                ),
                finalizer=AgentResponse.from_updates,
            )

        agent.run = MagicMock(side_effect=failing_run)
        server = _make_server(agent, session_store=store)

        response = await _post(server)
        body = response.json()
        session_id = body["id"]

        stored = await store.get(session_id)

        assert body["status"] == "failed"
        assert stored is not None
        assert stored.state["before_failure"] == "saved"

    async def test_run_save_failure_emits_failed_response(self) -> None:
        store = _FailingSessionStore()
        agent = _make_agent()

        def run(*_args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del _args
            session = kwargs["session"]
            assert isinstance(session, AgentSession)

            async def updates() -> AsyncIterator[AgentResponseUpdate]:
                session.state["run_complete"] = True
                yield AgentResponseUpdate(contents=[Content.from_text("done")], role="assistant")

            return ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        agent.run = MagicMock(side_effect=run)
        server = _make_server(agent, session_store=store)

        response = await _post(server, stream=True)
        event_types = _sse_event_types(_parse_sse_events(response.text))

        assert event_types[-1] == "response.failed"
        assert "response.completed" not in event_types
        assert store.set_attempts == 1

    async def test_run_and_save_failure_emit_one_combined_failure(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        store = _FailingSessionStore()
        agent = _make_agent()

        def failing_run(*_args: Any, **_kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del _args, _kwargs

            return ResponseStream(_raising_updates("agent failed"), finalizer=AgentResponse.from_updates)

        agent.run = MagicMock(side_effect=failing_run)
        server = _make_server(agent, session_store=store)

        response = await _post(server, stream=True)
        events = _parse_sse_events(response.text)
        event_types = _sse_event_types(events)
        failed_events = [event for event in events if event["event"] == "response.failed"]

        assert event_types[-1] == "response.failed"
        assert event_types.count("response.failed") == 1
        assert "response.completed" not in event_types
        error = failed_events[0]["data"]["response"]["error"]
        assert "agent failed" in error["message"]
        assert "session storage is full" in error["message"]
        assert "Failed to produce response for agent" in caplog.text
        assert "Failed to persist the Agent Framework session after an agent failure" in caplog.text

    async def test_cancellation_is_preserved_when_best_effort_save_fails(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        store = _FailingSessionStore()
        agent = _make_agent()

        def run_streaming(*_args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del _args
            session = kwargs["session"]
            assert isinstance(session, AgentSession)

            async def updates() -> AsyncIterator[AgentResponseUpdate]:
                session.state["started"] = True
                yield AgentResponseUpdate(contents=[Content.from_text("started")], role="assistant")

            return ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        agent.run = MagicMock(side_effect=run_streaming)
        server = _make_server(agent, session_store=store)
        request = CreateResponse(model="m", input="hi", stream=True)
        context = ResponseContext(response_id="response-1", mode_flags=MagicMock())

        with (
            patch.object(ResponseContext, "get_input_items", new=AsyncMock(return_value=[])),
            patch.object(ResponseContext, "get_history", new=AsyncMock(return_value=[])),
        ):
            handler = cast(
                AsyncGenerator[Any, None],
                server._handle_inner_agent(request, context),  # pyright: ignore[reportPrivateUsage]
            )
            await anext(handler)
            await anext(handler)
            await anext(handler)
            with pytest.raises(asyncio.CancelledError):
                await handler.athrow(asyncio.CancelledError())

        assert store.set_attempts == 1
        assert "while unwinding an interrupted request" in caplog.text

    async def test_abandoned_stream_saves_partial_session(self) -> None:
        store = SessionStore()
        agent = _make_agent()

        def run_streaming(*_args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del _args
            session = kwargs["session"]
            assert isinstance(session, AgentSession)

            async def updates() -> AsyncIterator[AgentResponseUpdate]:
                session.state["started"] = True
                yield AgentResponseUpdate(contents=[Content.from_text("started")], role="assistant")

            return ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        agent.run = MagicMock(side_effect=run_streaming)
        server = _make_server(agent, session_store=store)
        request = CreateResponse(model="m", input="hi", stream=True)
        context = ResponseContext(response_id="response-1", mode_flags=MagicMock())

        with (
            patch.object(ResponseContext, "get_input_items", new=AsyncMock(return_value=[])),
            patch.object(ResponseContext, "get_history", new=AsyncMock(return_value=[])),
        ):
            handler = cast(
                AsyncGenerator[Any, None],
                server._handle_inner_agent(request, context),  # pyright: ignore[reportPrivateUsage]
            )
            await anext(handler)
            await anext(handler)
            await anext(handler)
            await handler.aclose()

        stored = await store.get("response-1")
        assert stored is not None
        assert stored.state["started"] is True


# endregion


# region Health Check


class TestHealthCheck:
    async def test_readiness(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        server = _make_server(agent)
        transport = httpx.ASGITransport(app=server)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/readiness")
        assert resp.status_code == 200


# endregion


# region Non-streaming


class TestNonStreaming:
    """
    Non-streaming here means that the client requested a non-streaming response, instead of
    the inner agent being run in non-streaming mode. The inner agent is always run in streaming mode, and the
    ResponsesHostServer collects the streamed updates and returns a single JSON response at the end of the
    request.

    The opposite case, where the client requested a streaming response, is tested in `TestStreaming`.
    """

    async def test_basic_text_response(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Hello!")])])
        )
        server = _make_server(agent)
        resp = await _post(server, input_text="Hi", stream=False)

        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

        body = resp.json()
        assert body["object"] == "response"
        assert body["status"] == "completed"
        assert len(body["output"]) > 0

        # Find the message output item with our text
        text_found = False
        for item in body["output"]:
            assert item["type"] == "message"
            for part in item.get("content", []):
                if part.get("type") == "output_text" and part.get("text") == "Hello!":
                    text_found = True
        assert text_found, f"Expected 'Hello!' in output, got: {body['output']}"

    async def test_function_call_and_result(self) -> None:
        agent = _make_agent(
            response=AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[Content.from_function_call("call_1", "get_weather", arguments='{"loc": "NYC"}')],
                    ),
                    Message(role="tool", contents=[Content.from_function_result("call_1", result="sunny")]),
                    Message(role="assistant", contents=[Content.from_text("The weather is sunny!")]),
                ]
            )
        )
        server = _make_server(agent)
        resp = await _post(server, stream=False)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        types = [item["type"] for item in body["output"]]
        assert "function_call" in types
        assert "function_call_output" in types
        assert "message" in types

    async def test_hosted_mcp_call_and_result_persist_as_single_mcp_call(self) -> None:
        agent = _make_agent(
            response=AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_mcp_server_tool_call(
                                call_id="mcp_abc123",
                                tool_name="search",
                                server_name="api_specs",
                                arguments='{"q": "cats"}',
                            )
                        ],
                    ),
                    Message(
                        role="tool",
                        contents=[
                            Content.from_mcp_server_tool_result(
                                call_id="mcp_abc123",
                                output=[Content.from_text(text="found 10 cats")],
                            )
                        ],
                    ),
                    Message(role="assistant", contents=[Content.from_text("I found 10 cats!")]),
                ]
            )
        )
        server = _make_server(agent)
        resp = await _post(server, stream=False)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        types = [item["type"] for item in body["output"]]
        assert "mcp_call" in types
        assert "custom_tool_call_output" not in types

        mcp_items = [item for item in body["output"] if item["type"] == "mcp_call"]
        assert len(mcp_items) == 1
        assert mcp_items[0]["id"] == "mcp_abc123"
        assert mcp_items[0]["output"] == "found 10 cats"

    async def test_reasoning_content(self) -> None:
        reasoning_id = "rs_576d207b35d96b3200pkcXkMwXAij920Wcv7WhRXiMPiLdOA63"
        agent = _make_agent(
            response=AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_text_reasoning(
                                id=reasoning_id,
                                text="Let me ",
                                protected_data="encrypted-reasoning",
                            ),
                            Content.from_text_reasoning(id=reasoning_id, text="think..."),
                            Content.from_text("The answer is 42"),
                        ],
                    ),
                ]
            )
        )
        server = _make_server(agent)
        resp = await _post(server, stream=False)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        types = [item["type"] for item in body["output"]]
        assert "reasoning" in types
        assert "message" in types
        reasoning_items = [item for item in body["output"] if item["type"] == "reasoning"]
        assert len(reasoning_items) == 1
        assert reasoning_items[0]["id"] == reasoning_id
        assert reasoning_items[0]["encrypted_content"] == "encrypted-reasoning"
        assert [part["text"] for part in reasoning_items[0]["summary"]] == ["Let me think..."]

    async def test_empty_response(self) -> None:
        agent = _make_agent(response=AgentResponse(messages=[]))
        server = _make_server(agent)
        resp = await _post(server, stream=False)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

    async def test_chat_options_forwarded(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("ok")])]),
            raw_agent=True,
        )
        server = _make_server(agent)
        resp = await _post(
            server,
            stream=False,
            temperature=0.5,
            top_p=0.9,
            max_output_tokens=1024,
            parallel_tool_calls=False,
        )

        assert resp.status_code == 200
        agent.run.assert_called_once()
        call_kwargs = agent.run.call_args.kwargs
        assert call_kwargs["stream"] is True
        options = call_kwargs["options"]
        assert options["temperature"] == 0.5
        assert options["top_p"] == 0.9
        assert options["max_tokens"] == 1024
        assert options["allow_multiple_tool_calls"] is False


# endregion


# region Streaming


class TestStreaming:
    """
    Streaming here means that the client requested a streaming response, and the ResponsesHostServer
    forwards the stream of updates from the inner agent to the client as a Server-Sent Events (SSE) stream.
    The inner agent is always run in streaming mode, and the ResponsesHost Server forwards the updates as
    are created, without waiting for the entire response to complete.

    The opposite case, where the client requested a non-streaming response, is tested in `TestNonStreaming`.
    """

    async def test_chat_options_forwarded(self) -> None:
        agent = _make_agent(
            stream_updates=[AgentResponseUpdate(contents=[Content.from_text("ok")], role="assistant")],
            raw_agent=True,
        )
        server = _make_server(agent)
        resp = await _post(
            server,
            stream=True,
            temperature=0.5,
            top_p=0.9,
            max_output_tokens=1024,
            parallel_tool_calls=True,
        )

        assert resp.status_code == 200
        agent.run.assert_called_once()
        call_kwargs = agent.run.call_args.kwargs
        assert call_kwargs["stream"] is True
        options = call_kwargs["options"]
        assert options["temperature"] == 0.5
        assert options["top_p"] == 0.9
        assert options["max_tokens"] == 1024
        assert options["allow_multiple_tool_calls"] is True

    async def test_basic_text_streaming(self) -> None:
        agent = _make_agent(
            stream_updates=[
                AgentResponseUpdate(contents=[Content.from_text("Hello ")], role="assistant"),
                AgentResponseUpdate(contents=[Content.from_text("world!")], role="assistant"),
            ]
        )
        server = _make_server(agent)
        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        assert types[0] == "response.created"
        assert types[1] == "response.in_progress"
        assert types[-1] == "response.completed"
        assert "response.output_text.delta" in types
        assert types.count("response.output_text.delta") == 2
        assert "response.output_text.done" in types

        # Verify the accumulated text in the done event
        done_events = [e for e in events if e["event"] == "response.output_text.done"]
        assert len(done_events) == 1
        assert done_events[0]["data"]["text"] == "Hello world!"

    async def test_function_call_streaming(self) -> None:
        agent = _make_agent(
            stream_updates=[
                AgentResponseUpdate(
                    contents=[Content.from_function_call("call_1", "search", arguments='{"q":')],
                    role="assistant",
                ),
                AgentResponseUpdate(
                    contents=[Content.from_function_call("call_1", "search", arguments=' "hello"}')],
                    role="assistant",
                ),
            ]
        )
        server = _make_server(agent)
        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        assert types[0] == "response.created"
        assert types[-1] == "response.completed"
        assert types.count("response.function_call_arguments.delta") == 2
        assert "response.function_call_arguments.done" in types

        # Verify accumulated arguments
        args_done = [e for e in events if e["event"] == "response.function_call_arguments.done"]
        assert len(args_done) == 1
        assert args_done[0]["data"]["arguments"] == '{"q": "hello"}'

    @pytest.mark.parametrize(("arguments", "expected_count"), [(None, 1), ("", 2)])
    async def test_declaration_only_metadata_replay_requires_none_arguments(
        self, arguments: str | None, expected_count: int
    ) -> None:
        metadata = Content.from_function_call("call_1", "search", arguments=arguments)
        metadata.id = "call_1"
        metadata.user_input_request = True
        agent = _make_agent(
            stream_updates=[
                AgentResponseUpdate(
                    contents=[Content.from_function_call("call_1", "search", arguments='{"q": "hello"}')],
                    role="assistant",
                ),
                AgentResponseUpdate(contents=[Content.from_text("Waiting for the result")], role="assistant"),
                AgentResponseUpdate(contents=[metadata], role="assistant"),
            ]
        )
        server = _make_server(agent)

        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        function_items = [
            event
            for event in events
            if event["event"] == "response.output_item.added" and event["data"]["item"]["type"] == "function_call"
        ]
        assert len(function_items) == expected_count

    async def test_function_call_id_can_be_reused_after_terminal_result(self) -> None:
        reused_call = Content.from_function_call("call_1", "search", arguments=None)
        reused_call.id = "call_1"
        reused_call.user_input_request = True
        agent = _make_agent(
            stream_updates=[
                AgentResponseUpdate(
                    contents=[Content.from_function_call("call_1", "search", arguments='{"q": "first"}')],
                    role="assistant",
                ),
                AgentResponseUpdate(
                    contents=[Content.from_function_result("call_1", result="first result")],
                    role="tool",
                ),
                AgentResponseUpdate(contents=[reused_call], role="assistant"),
            ]
        )
        server = _make_server(agent)

        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        function_items = [
            event
            for event in events
            if event["event"] == "response.output_item.added" and event["data"]["item"]["type"] == "function_call"
        ]
        assert [event["data"]["item"]["call_id"] for event in function_items] == ["call_1", "call_1"]

    async def test_function_call_streaming_serializes_dataclass_arguments(self) -> None:
        @dataclass
        class HandoffLikeRequest:
            agent_response: AgentResponse

        request = HandoffLikeRequest(
            agent_response=AgentResponse(
                messages=[Message(role="assistant", contents=[Content.from_text("Need more details")])]
            )
        )
        agent = _make_agent(
            stream_updates=[
                AgentResponseUpdate(
                    contents=[Content.from_function_call("call_1", "handoff_to_refund", arguments=request.__dict__)],
                    role="assistant",
                ),
            ]
        )
        server = _make_server(agent)
        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        args_done = [e for e in events if e["event"] == "response.function_call_arguments.done"]
        assert len(args_done) == 1

        payload = json.loads(args_done[0]["data"]["arguments"])
        assert payload["agent_response"]["type"] == "agent_response"
        assert payload["agent_response"]["messages"][0]["contents"][0]["text"] == "Need more details"

    async def test_alternating_text_and_function_call(self) -> None:
        agent = _make_agent(
            stream_updates=[
                # Text deltas
                AgentResponseUpdate(contents=[Content.from_text("Let me ")], role="assistant"),
                AgentResponseUpdate(contents=[Content.from_text("search...")], role="assistant"),
                # Function call argument deltas
                AgentResponseUpdate(
                    contents=[Content.from_function_call("call_1", "search", arguments='{"q":')],
                    role="assistant",
                ),
                AgentResponseUpdate(
                    contents=[Content.from_function_call("call_1", "search", arguments=' "x"}')],
                    role="assistant",
                ),
                # More text deltas
                AgentResponseUpdate(contents=[Content.from_text("Found ")], role="assistant"),
                AgentResponseUpdate(contents=[Content.from_text("it!")], role="assistant"),
            ]
        )
        server = _make_server(agent)
        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        assert types[0] == "response.created"
        assert types[-1] == "response.completed"

        # 4 text deltas + 2 function call argument deltas
        assert types.count("response.output_text.delta") == 4
        assert types.count("response.function_call_arguments.delta") == 2

        # 3 distinct output items (text, fc, text)
        assert types.count("response.output_item.added") == 3
        assert types.count("response.output_item.done") == 3

        # Verify accumulated content
        text_done = [e for e in events if e["event"] == "response.output_text.done"]
        assert len(text_done) == 2
        assert text_done[0]["data"]["text"] == "Let me search..."
        assert text_done[1]["data"]["text"] == "Found it!"

        args_done = [e for e in events if e["event"] == "response.function_call_arguments.done"]
        assert len(args_done) == 1
        assert args_done[0]["data"]["arguments"] == '{"q": "x"}'

    async def test_reasoning_then_text_streaming(self) -> None:
        reasoning_id = "rs_576d207b35d96b3200pkcXkMwXAij920Wcv7WhRXiMPiLdOA63"
        agent = _make_agent(
            stream_updates=[
                # Reasoning deltas
                AgentResponseUpdate(
                    contents=[Content.from_text_reasoning(id=reasoning_id, text="Let me ")], role="assistant"
                ),
                AgentResponseUpdate(
                    contents=[Content.from_text_reasoning(id=reasoning_id, text="think...")], role="assistant"
                ),
                AgentResponseUpdate(
                    contents=[
                        Content.from_text_reasoning(
                            id=reasoning_id,
                            text="",
                            protected_data="encrypted-reasoning",
                        )
                    ],
                    role="assistant",
                ),
                # Text deltas
                AgentResponseUpdate(contents=[Content.from_text("The answer ")], role="assistant"),
                AgentResponseUpdate(contents=[Content.from_text("is 42")], role="assistant"),
            ]
        )
        server = _make_server(agent)
        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        assert types[0] == "response.created"
        assert types[-1] == "response.completed"
        # Reasoning + text = 2 output items
        assert types.count("response.output_item.added") == 2
        assert types.count("response.output_item.done") == 2
        assert types.count("response.output_text.delta") == 2

        # Verify accumulated text
        text_done = [e for e in events if e["event"] == "response.output_text.done"]
        assert len(text_done) == 1
        assert text_done[0]["data"]["text"] == "The answer is 42"
        reasoning_done = [
            event
            for event in events
            if event["event"] == "response.output_item.done" and event["data"]["item"]["type"] == "reasoning"
        ]
        assert len(reasoning_done) == 1
        assert reasoning_done[0]["data"]["item"]["id"] == reasoning_id
        assert reasoning_done[0]["data"]["item"]["encrypted_content"] == "encrypted-reasoning"

    async def test_empty_streaming(self) -> None:
        agent = _make_agent(stream_updates=[])
        server = _make_server(agent)
        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        assert types == ["response.created", "response.in_progress", "response.completed"]

    async def test_mixed_contents_in_single_update(self) -> None:
        """Text and function call in one update switches builder mid-update."""
        agent = _make_agent(
            stream_updates=[
                AgentResponseUpdate(
                    contents=[
                        Content.from_text("Let me search"),
                        Content.from_function_call("call_1", "search", arguments='{"q": "test"}'),
                    ],
                    role="assistant",
                ),
            ]
        )
        server = _make_server(agent)
        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        assert "response.output_text.delta" in types
        assert "response.output_text.done" in types
        assert "response.function_call_arguments.delta" in types
        assert "response.function_call_arguments.done" in types

    async def test_different_function_call_ids_produce_separate_items(self) -> None:
        agent = _make_agent(
            stream_updates=[
                AgentResponseUpdate(
                    contents=[Content.from_function_call("call_1", "func_a", arguments='{"x":1}')],
                    role="assistant",
                ),
                AgentResponseUpdate(
                    contents=[Content.from_function_call("call_2", "func_b", arguments='{"y":2}')],
                    role="assistant",
                ),
            ]
        )
        server = _make_server(agent)
        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        # Two separate function call items
        assert types.count("response.output_item.added") == 2
        assert types.count("response.function_call_arguments.done") == 2

    async def test_mcp_tool_call_streaming(self) -> None:
        agent = _make_agent(
            stream_updates=[
                AgentResponseUpdate(
                    contents=[
                        Content(
                            type="mcp_server_tool_call",
                            server_name="my_server",
                            tool_name="search",
                            arguments='{"query":',
                        )
                    ],
                    role="assistant",
                ),
                AgentResponseUpdate(
                    contents=[
                        Content(
                            type="mcp_server_tool_call",
                            server_name="my_server",
                            tool_name="search",
                            arguments=' "test"}',
                        )
                    ],
                    role="assistant",
                ),
            ]
        )
        server = _make_server(agent)
        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        assert types[0] == "response.created"
        assert types[-1] == "response.completed"
        assert "response.output_item.added" in types
        assert "response.output_item.done" in types

    async def test_mcp_tool_call_and_result_streaming_emit_single_completed_mcp_call(self) -> None:
        agent = _make_agent(
            stream_updates=[
                AgentResponseUpdate(
                    contents=[
                        Content.from_mcp_server_tool_call(
                            call_id="mcp_abc123",
                            tool_name="search",
                            server_name="api_specs",
                            arguments='{"q":',
                        )
                    ],
                    role="assistant",
                ),
                AgentResponseUpdate(
                    contents=[
                        Content.from_mcp_server_tool_call(
                            call_id="mcp_abc123",
                            tool_name="search",
                            server_name="api_specs",
                            arguments=' "cats"}',
                        )
                    ],
                    role="assistant",
                ),
                AgentResponseUpdate(
                    contents=[
                        Content.from_mcp_server_tool_result(
                            call_id="mcp_abc123",
                            output=[Content.from_text(text="found 10 cats")],
                        )
                    ],
                    role="tool",
                ),
            ]
        )
        server = _make_server(agent)
        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        done_events = [e for e in events if e["event"] == "response.output_item.done"]
        assert len(done_events) == 1
        assert done_events[0]["data"]["item"]["type"] == "mcp_call"
        assert done_events[0]["data"]["item"]["id"] == "mcp_abc123"
        assert done_events[0]["data"]["item"]["output"] == "found 10 cats"


# endregion


# region _output_item_to_message conversion


class TestOutputItemToMessage:
    """Tests for _output_item_to_message covering all supported OutputItem types."""

    async def test_output_message(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemOutputMessage, OutputMessageContentOutputTextContent

        item = cast(
            OutputItemOutputMessage,
            {
                "type": "output_message",
                "role": "assistant",
                "content": [cast(OutputMessageContentOutputTextContent, {"type": "output_text", "text": "hello"})],
                "status": "completed",
                "id": "msg-1",
            },
        )
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert len(msg.contents) == 1
        assert msg.contents[0].type == "text"
        assert msg.contents[0].text == "hello"

    async def test_message(self) -> None:
        from azure.ai.agentserver.responses.models import MessageContentInputTextContent, OutputItemMessage

        item = cast(
            OutputItemMessage,
            {
                "type": "message",
                "role": "user",
                "content": [MessageContentInputTextContent({"type": "input_text", "text": "hi"})],
            },
        )
        msg = await _output_item_to_message(item)
        assert msg.role == "user"
        assert len(msg.contents) == 1
        assert msg.contents[0].text == "hi"

    async def test_function_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemFunctionToolCall

        item = OutputItemFunctionToolCall({
            "type": "function_call",
            "call_id": "call_1",
            "name": "get_weather",
            "arguments": '{"city": "NYC"}',
            "status": "completed",
            "id": "fc-1",
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].call_id == "call_1"
        assert msg.contents[0].name == "get_weather"
        assert msg.contents[0].informational_only is False

    async def test_function_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import FunctionCallOutputItemParam

        item = FunctionCallOutputItemParam({"type": "function_call_output", "call_id": "call_1", "output": "sunny"})
        msg = await _output_item_to_message(item)  # type: ignore[arg-type] # ty: ignore[invalid-argument-type]
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].call_id == "call_1"
        assert msg.contents[0].result == "sunny"

    async def test_reasoning(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemReasoningItem, SummaryTextContent

        item = OutputItemReasoningItem({
            "type": "reasoning",
            "id": "r-1",
            "encrypted_content": "encrypted-reasoning",
            "summary": [SummaryTextContent({"type": "summary_text", "text": "thinking hard"})],
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert len(msg.contents) == 1
        assert msg.contents[0].type == "text_reasoning"
        assert msg.contents[0].id == "r-1"
        assert msg.contents[0].text == "thinking hard"
        assert msg.contents[0].protected_data == "encrypted-reasoning"

    async def test_reasoning_no_summary(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemReasoningItem

        item = cast(OutputItemReasoningItem, {"type": "reasoning", "id": "r-2"})
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert len(msg.contents) == 1
        assert msg.contents[0].type == "text_reasoning"
        assert msg.contents[0].id == "r-2"
        assert msg.contents[0].text is None

    async def test_mcp_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpToolCall

        item = OutputItemMcpToolCall({
            "type": "mcp_call",
            "id": "mcp-1",
            "server_label": "my_server",
            "name": "search",
            "arguments": '{"q": "test"}',
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "mcp_server_tool_call"
        assert msg.contents[0].server_name == "my_server"
        assert msg.contents[0].tool_name == "search"

    async def test_mcp_call_with_output_reconstructs_mcp_result_content(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpToolCall

        item = OutputItemMcpToolCall({
            "type": "mcp_call",
            "id": "mcp-1",
            "server_label": "my_server",
            "name": "search",
            "arguments": '{"q": "test"}',
            "output": "found 10 cats",
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert len(msg.contents) == 2
        assert msg.contents[0].type == "mcp_server_tool_call"
        assert msg.contents[1].type == "mcp_server_tool_result"
        assert msg.contents[1].output == "found 10 cats"

    async def test_mcp_approval_request(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpApprovalRequest

        saved = _make_function_approval_request_content(request_id="apr-1")
        storage = _function_approval_store(saved)

        item = OutputItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "apr-1",
            "server_label": "srv",
            "name": "dangerous_tool",
            "arguments": "{}",
        })
        msg = await _output_item_to_message(item, approval_storage=storage)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_approval_request"

    async def test_mcp_approval_response(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpApprovalResponseResource

        saved = _make_function_approval_request_content(request_id="apr-1")
        storage = _function_approval_store(saved)

        item = OutputItemMcpApprovalResponseResource({
            "type": "mcp_approval_response",
            "id": "resp-1",
            "approval_request_id": "apr-1",
            "approve": True,
        })
        msg = await _output_item_to_message(item, approval_storage=storage)
        assert msg.role == "user"
        assert msg.contents[0].type == "function_approval_response"
        assert msg.contents[0].approved is True

    async def test_code_interpreter_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemCodeInterpreterToolCall

        item = OutputItemCodeInterpreterToolCall({
            "type": "code_interpreter_call",
            "id": "ci-1",
            "status": "completed",
            "container_id": "c-1",
            "code": "print('hi')",
            "outputs": [],
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "code_interpreter_tool_call"

    async def test_image_generation_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemImageGenToolCall

        item = cast(
            OutputItemImageGenToolCall,
            {"type": "image_generation_call", "id": "ig-1", "status": "completed"},
        )
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "image_generation_tool_call"

    async def test_shell_call(self) -> None:
        item = cast(
            OutputItem,
            {
                "type": "shell_call",
                "id": "sc-1",
                "call_id": "call_sc",
                "action": {"commands": ["ls", "-la"], "timeout_ms": 5000, "max_output_length": 1024},
                "status": "completed",
                "environment": {"type": "local"},
            },
        )
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "shell_tool_call"
        assert msg.contents[0].commands == ["ls", "-la"]
        assert msg.contents[0].call_id == "call_sc"

    async def test_shell_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import (
            FunctionShellCallOutputContent,
            FunctionShellCallOutputExitOutcome,
            OutputItemFunctionShellCallOutput,
        )

        item = OutputItemFunctionShellCallOutput({
            "type": "shell_call_output",
            "id": "sco-1",
            "call_id": "call_sc",
            "status": "completed",
            "output": [
                FunctionShellCallOutputContent({
                    "stdout": "file.txt",
                    "stderr": "",
                    "outcome": cast(FunctionShellCallOutputExitOutcome, {"exit_code": 0}),
                })
            ],
            "max_output_length": 1024,
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "tool"
        assert msg.contents[0].type == "shell_tool_result"
        assert msg.contents[0].call_id == "call_sc"

    async def test_local_shell_call(self) -> None:
        from azure.ai.agentserver.responses.models import LocalShellExecAction, OutputItemLocalShellToolCall

        item = OutputItemLocalShellToolCall({
            "type": "local_shell_call",
            "id": "lsc-1",
            "call_id": "call_lsc",
            "action": LocalShellExecAction({"type": "exec", "command": ["echo", "hello"], "env": {}}),
            "status": "completed",
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "shell_tool_call"
        assert msg.contents[0].commands == ["echo", "hello"]

    async def test_local_shell_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemLocalShellToolCallOutput

        item = OutputItemLocalShellToolCallOutput({
            "type": "local_shell_call_output",
            "id": "lsco-1",
            "output": "hello\n",
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "tool"
        assert msg.contents[0].type == "shell_tool_result"

    async def test_file_search_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemFileSearchToolCall

        item = OutputItemFileSearchToolCall({
            "type": "file_search_call",
            "id": "fs-1",
            "status": "completed",
            "queries": ["what is AI"],
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "file_search"
        assert '"what is AI"' in (msg.contents[0].arguments or "")
        assert msg.contents[0].informational_only is True

    async def test_web_search_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemWebSearchToolCall, WebSearchActionSearch

        item = OutputItemWebSearchToolCall({
            "type": "web_search_call",
            "id": "ws-1",
            "status": "completed",
            "action": WebSearchActionSearch({"type": "search", "query": "test"}),
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "web_search"
        assert msg.contents[0].informational_only is True

    async def test_computer_call(self) -> None:
        item = cast(
            OutputItem,
            {
                "type": "computer_call",
                "id": "cc-1",
                "call_id": "call_cc",
                "action": {"type": "click"},
                "pending_safety_checks": [],
                "status": "completed",
            },
        )
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "computer_use"
        assert msg.contents[0].informational_only is True

    async def test_computer_call_output(self) -> None:
        item = cast(
            OutputItem,
            {
                "type": "computer_call_output",
                "call_id": "call_cc",
                "output": {
                    "type": "computer_screenshot",
                    "image_url": "data:image/png;base64,abc",
                },
            },
        )
        msg = await _output_item_to_message(item)
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].call_id == "call_cc"

    async def test_custom_tool_call(self) -> None:
        item = cast(
            OutputItem,
            {
                "type": "custom_tool_call",
                "call_id": "call_ct",
                "name": "my_tool",
                "input": '{"key": "value"}',
            },
        )
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "my_tool"
        assert msg.contents[0].arguments == '{"key": "value"}'
        assert msg.contents[0].informational_only is True

    async def test_custom_tool_call_output(self) -> None:
        item = cast(
            OutputItem,
            {
                "type": "custom_tool_call_output",
                "call_id": "call_ct",
                "output": "result text",
            },
        )
        msg = await _output_item_to_message(item)
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].result == "result text"

    async def test_custom_tool_call_output_with_mcp_call_id_routes_to_mcp_server_tool_result(self) -> None:
        """When the host wrote a hosted-MCP result via
        `aoutput_item_custom_tool_call_output`, the persisted call_id keeps
        its `mcp_*` prefix. On read, that result must reconstruct as a
        `mcp_server_tool_result` Content (not `function_result`), so the
        chat-client serialize layer treats it as a hosted-MCP result and
        does not produce an orphan `function_call_output`.
        """
        item = cast(
            OutputItem,
            {
                "type": "custom_tool_call_output",
                "call_id": "mcp_06b686e11f118cf40169f0e5badb3081979842929d5cf04920",
                "output": "found 10 cats",
            },
        )
        msg = await _output_item_to_message(item)
        assert msg.role == "tool"
        assert len(msg.contents) == 1
        c = msg.contents[0]
        assert c.type == "mcp_server_tool_result", (
            f"expected mcp_server_tool_result for mcp_-prefixed call_id; got {c.type}"
        )
        assert c.call_id == "mcp_06b686e11f118cf40169f0e5badb3081979842929d5cf04920"

    async def test_apply_patch_call(self) -> None:
        from azure.ai.agentserver.responses.models import ApplyPatchUpdateFileOperation, OutputItemApplyPatchToolCall

        item = OutputItemApplyPatchToolCall({
            "type": "apply_patch_call",
            "id": "ap-1",
            "call_id": "call_ap",
            "status": "completed",
            "operation": ApplyPatchUpdateFileOperation({
                "type": "update_file",
                "path": "file.py",
                "diff": "+ new line",
            }),
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "apply_patch"
        assert msg.contents[0].informational_only is True

    async def test_apply_patch_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemApplyPatchToolCallOutput

        item = OutputItemApplyPatchToolCallOutput({
            "type": "apply_patch_call_output",
            "id": "apo-1",
            "call_id": "call_ap",
            "status": "completed",
            "output": "patch applied",
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].result == "patch applied"

    async def test_oauth_consent_request(self) -> None:
        from azure.ai.agentserver.responses.models import OAuthConsentRequestOutputItem

        item = OAuthConsentRequestOutputItem({
            "type": "oauth_consent_request",
            "id": "oauth-1",
            "consent_link": "https://example.com/consent",
            "server_label": "my_server",
        })
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "oauth_consent_request"
        assert msg.contents[0].consent_link == "https://example.com/consent"

    async def test_structured_outputs_dict(self) -> None:
        from azure.ai.agentserver.responses.models import StructuredOutputsOutputItem

        item = StructuredOutputsOutputItem({"type": "structured_outputs", "id": "so-1", "output": {"answer": 42}})
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "text"
        assert json.loads(msg.contents[0].text or "") == {"answer": 42}

    async def test_structured_outputs_string(self) -> None:
        from azure.ai.agentserver.responses.models import StructuredOutputsOutputItem

        item = StructuredOutputsOutputItem({"type": "structured_outputs", "id": "so-2", "output": "plain text"})
        msg = await _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].text == "plain text"

    async def test_unsupported_type_raises(self) -> None:
        item = cast(OutputItem, {"type": "some_unknown_type"})
        with pytest.raises(ValueError, match="Unsupported OutputItem type: some_unknown_type"):
            await _output_item_to_message(item)


# endregion


# region _item_to_message conversion


class TestItemToMessage:
    """Tests for _item_to_message covering all supported Item types."""

    async def test_message_with_string_content(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMessage

        item = ItemMessage({"type": "message", "role": "user", "content": "hello"})
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "user"
        assert len(msg.contents) == 1
        assert msg.contents[0].type == "text"
        assert msg.contents[0].text == "hello"

    async def test_message_with_input_text_content(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMessage, MessageContentInputTextContent

        item = ItemMessage({
            "type": "message",
            "role": "user",
            "content": [MessageContentInputTextContent({"type": "input_text", "text": "hi there"})],
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "user"
        assert len(msg.contents) == 1
        assert msg.contents[0].text == "hi there"

    async def test_message_with_multiple_contents(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMessage, MessageContentInputTextContent

        item = ItemMessage({
            "type": "message",
            "role": "user",
            "content": [
                MessageContentInputTextContent({"type": "input_text", "text": "first"}),
                MessageContentInputTextContent({"type": "input_text", "text": "second"}),
            ],
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert len(msg.contents) == 2
        assert msg.contents[0].text == "first"
        assert msg.contents[1].text == "second"

    async def test_output_message(self) -> None:
        from azure.ai.agentserver.responses.models import ItemOutputMessage, OutputMessageContentOutputTextContent

        item = cast(
            ItemOutputMessage,
            {
                "type": "output_message",
                "role": "assistant",
                "content": [cast(OutputMessageContentOutputTextContent, {"type": "output_text", "text": "response"})],
                "status": "completed",
                "id": "msg-1",
            },
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert len(msg.contents) == 1
        assert msg.contents[0].type == "text"
        assert msg.contents[0].text == "response"

    async def test_function_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemFunctionToolCall

        item = cast(
            ItemFunctionToolCall,
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "get_weather",
                "arguments": '{"city": "NYC"}',
                "status": "completed",
                "id": "fc-1",
            },
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].call_id == "call_1"
        assert msg.contents[0].name == "get_weather"
        assert msg.contents[0].arguments == '{"city": "NYC"}'
        assert msg.contents[0].informational_only is False

    async def test_function_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import FunctionCallOutputItemParam

        item = FunctionCallOutputItemParam({"type": "function_call_output", "call_id": "call_1", "output": "sunny"})
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].call_id == "call_1"
        assert msg.contents[0].result == "sunny"

    async def test_function_call_output_non_string(self) -> None:
        from azure.ai.agentserver.responses.models import FunctionCallOutputItemParam

        item = cast(
            FunctionCallOutputItemParam,
            {"type": "function_call_output", "call_id": "call_2", "output": 42},
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].result == "42"

    async def test_reasoning_with_summary(self) -> None:
        from azure.ai.agentserver.responses.models import ItemReasoningItem, SummaryTextContent

        item = ItemReasoningItem({
            "type": "reasoning",
            "id": "r-1",
            "encrypted_content": "encrypted-reasoning",
            "summary": [SummaryTextContent({"type": "summary_text", "text": "thinking hard"})],
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert len(msg.contents) == 1
        assert msg.contents[0].type == "text_reasoning"
        assert msg.contents[0].id == "r-1"
        assert msg.contents[0].text == "thinking hard"
        assert msg.contents[0].protected_data == "encrypted-reasoning"

    async def test_reasoning_no_summary(self) -> None:
        from azure.ai.agentserver.responses.models import ItemReasoningItem

        item = cast(ItemReasoningItem, {"type": "reasoning", "id": "r-2"})
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert len(msg.contents) == 1
        assert msg.contents[0].type == "text_reasoning"
        assert msg.contents[0].id == "r-2"
        assert msg.contents[0].text is None

    async def test_mcp_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMcpToolCall

        item = ItemMcpToolCall({
            "type": "mcp_call",
            "id": "mcp-1",
            "server_label": "my_server",
            "name": "search",
            "arguments": '{"q": "test"}',
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "mcp_server_tool_call"
        assert msg.contents[0].server_name == "my_server"
        assert msg.contents[0].tool_name == "search"

    async def test_mcp_call_with_output_reconstructs_mcp_result_content(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMcpToolCall

        item = ItemMcpToolCall({
            "type": "mcp_call",
            "id": "mcp-1",
            "server_label": "my_server",
            "name": "search",
            "arguments": '{"q": "test"}',
            "output": "found 10 cats",
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert len(msg.contents) == 2
        assert msg.contents[0].type == "mcp_server_tool_call"
        assert msg.contents[1].type == "mcp_server_tool_result"
        assert msg.contents[1].output == "found 10 cats"

    async def test_mcp_approval_request(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMcpApprovalRequest

        saved = _make_function_approval_request_content(request_id="apr-1")
        storage = _function_approval_store(saved)

        item = ItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "apr-1",
            "server_label": "srv",
            "name": "dangerous_tool",
            "arguments": "{}",
        })
        msg = await _item_to_message(item, approval_storage=storage)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_approval_request"

    async def test_mcp_approval_response(self) -> None:
        from azure.ai.agentserver.responses.models import MCPApprovalResponse

        saved = _make_function_approval_request_content(request_id="apr-1")
        storage = _function_approval_store(saved)

        item = MCPApprovalResponse({
            "type": "mcp_approval_response",
            "approval_request_id": "apr-1",
            "approve": True,
        })
        msg = await _item_to_message(item, approval_storage=storage)
        assert msg is not None
        assert msg.role == "user"
        assert msg.contents[0].type == "function_approval_response"
        assert msg.contents[0].approved is True

    async def test_code_interpreter_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemCodeInterpreterToolCall

        item = ItemCodeInterpreterToolCall({
            "type": "code_interpreter_call",
            "id": "ci-1",
            "status": "completed",
            "container_id": "c-1",
            "code": "print('hi')",
            "outputs": [],
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "code_interpreter_tool_call"

    async def test_image_generation_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemImageGenToolCall

        item = cast(
            ItemImageGenToolCall,
            {"type": "image_generation_call", "id": "ig-1", "status": "completed"},
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "image_generation_tool_call"

    async def test_shell_call(self) -> None:
        from azure.ai.agentserver.responses.models import FunctionShellAction, FunctionShellCallItemParam

        item = cast(
            FunctionShellCallItemParam,
            {
                "type": "shell_call",
                "call_id": "call_sc",
                "action": FunctionShellAction({
                    "commands": ["ls", "-la"],
                    "timeout_ms": 5000,
                    "max_output_length": 1024,
                }),
                "status": "in_progress",
            },
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "shell_tool_call"
        assert msg.contents[0].commands == ["ls", "-la"]
        assert msg.contents[0].call_id == "call_sc"

    async def test_shell_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import (
            FunctionShellCallOutputContent,
            FunctionShellCallOutputExitOutcome,
            FunctionShellCallOutputItemParam,
        )

        item = FunctionShellCallOutputItemParam({
            "type": "shell_call_output",
            "call_id": "call_sc",
            "output": [
                FunctionShellCallOutputContent({
                    "stdout": "file.txt",
                    "stderr": "",
                    "outcome": cast(FunctionShellCallOutputExitOutcome, {"exit_code": 0}),
                })
            ],
            "max_output_length": 1024,
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "shell_tool_result"
        assert msg.contents[0].call_id == "call_sc"

    async def test_local_shell_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemLocalShellToolCall, LocalShellExecAction

        item = ItemLocalShellToolCall({
            "type": "local_shell_call",
            "id": "lsc-1",
            "call_id": "call_lsc",
            "action": LocalShellExecAction({"type": "exec", "command": ["echo", "hello"], "env": {}}),
            "status": "completed",
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "shell_tool_call"
        assert msg.contents[0].commands == ["echo", "hello"]

    async def test_local_shell_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import ItemLocalShellToolCallOutput

        item = ItemLocalShellToolCallOutput({
            "type": "local_shell_call_output",
            "id": "lsco-1",
            "output": "hello\n",
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "shell_tool_result"

    async def test_file_search_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemFileSearchToolCall

        item = ItemFileSearchToolCall({
            "type": "file_search_call",
            "id": "fs-1",
            "status": "completed",
            "queries": ["what is AI"],
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "file_search"
        assert '"what is AI"' in (msg.contents[0].arguments or "")
        assert msg.contents[0].informational_only is True

    async def test_web_search_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemWebSearchToolCall

        item = cast(
            ItemWebSearchToolCall,
            {
                "type": "web_search_call",
                "id": "ws-1",
                "status": "completed",
            },
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "web_search"
        assert msg.contents[0].informational_only is True

    async def test_computer_call(self) -> None:
        item = cast(
            Item,
            {
                "type": "computer_call",
                "id": "cc-1",
                "call_id": "call_cc",
                "action": {"type": "click"},
                "pending_safety_checks": [],
                "status": "completed",
            },
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "computer_use"
        assert msg.contents[0].informational_only is True

    async def test_computer_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import ComputerCallOutputItemParam, ComputerScreenshotImage

        item = ComputerCallOutputItemParam({
            "type": "computer_call_output",
            "call_id": "call_cc",
            "output": ComputerScreenshotImage({
                "type": "computer_screenshot",
                "image_url": "data:image/png;base64,abc",
            }),
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].call_id == "call_cc"

    async def test_custom_tool_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemCustomToolCall

        item = ItemCustomToolCall({
            "type": "custom_tool_call",
            "call_id": "call_ct",
            "name": "my_tool",
            "input": '{"key": "value"}',
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "my_tool"
        assert msg.contents[0].arguments == '{"key": "value"}'
        assert msg.contents[0].informational_only is True

    async def test_custom_tool_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import ItemCustomToolCallOutput

        item = cast(
            ItemCustomToolCallOutput,
            {
                "type": "custom_tool_call_output",
                "call_id": "call_ct",
                "output": "result text",
            },
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].result == "result text"

    async def test_custom_tool_call_output_non_string(self) -> None:
        from azure.ai.agentserver.responses.models import ItemCustomToolCallOutput

        item = cast(
            ItemCustomToolCallOutput,
            {
                "type": "custom_tool_call_output",
                "call_id": "call_ct2",
                "output": 123,
            },
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.contents[0].result == "123"

    async def test_custom_tool_call_output_with_mcp_call_id_routes_to_mcp_server_tool_result(self) -> None:
        """Issue #5546: input items carrying a hosted-MCP result (from a
        prior turn that the framework wrote via
        `aoutput_item_custom_tool_call_output`) must reconstruct as a
        `mcp_server_tool_result` Content, not `function_result`. Otherwise
        the chat-client serialize layer turns it into an orphan
        `function_call_output` with `mcp_*` call_id and the Responses API
        rejects the next turn.
        """
        from azure.ai.agentserver.responses.models import ItemCustomToolCallOutput

        item = ItemCustomToolCallOutput({
            "type": "custom_tool_call_output",
            "call_id": "mcp_06b686e11f118cf40169f0e5badb3081979842929d5cf04920",
            "output": "found 10 cats",
        })
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "tool"
        assert len(msg.contents) == 1
        c = msg.contents[0]
        assert c.type == "mcp_server_tool_result", (
            f"expected mcp_server_tool_result for mcp_-prefixed call_id; got {c.type}"
        )
        assert c.call_id == "mcp_06b686e11f118cf40169f0e5badb3081979842929d5cf04920"

    async def test_apply_patch_call(self) -> None:
        from azure.ai.agentserver.responses.models import ApplyPatchToolCallItemParam, ApplyPatchUpdateFileOperation

        item = cast(
            ApplyPatchToolCallItemParam,
            {
                "type": "apply_patch_call",
                "call_id": "call_ap",
                "operation": ApplyPatchUpdateFileOperation({
                    "type": "update_file",
                    "path": "file.py",
                    "diff": "+ new line",
                }),
            },
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "apply_patch"
        assert msg.contents[0].informational_only is True

    async def test_apply_patch_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import ApplyPatchToolCallOutputItemParam

        item = cast(
            ApplyPatchToolCallOutputItemParam,
            {
                "type": "apply_patch_call_output",
                "call_id": "call_ap",
                "output": "patch applied",
            },
        )
        msg = await _item_to_message(item)
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].result == "patch applied"

    async def test_unsupported_type_raises(self) -> None:
        item = cast(Item, {"type": "some_unknown_type"})
        with pytest.raises(ValueError, match="Unsupported Item type: some_unknown_type"):
            await _item_to_message(item)


# endregion


# region Multi-turn with mixed content


async def _post_json(
    server: ResponsesHostServer,
    payload: dict[str, Any],
) -> httpx.Response:
    """Send a POST /responses request with a raw JSON payload."""
    transport = httpx.ASGITransport(app=server)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/responses", json=payload)


def _make_multi_response_agent(
    responses: list[AgentResponse],
    stream_updates_list: list[list[AgentResponseUpdate]] | None = None,
) -> MagicMock:
    """Create a mock agent that returns different responses on successive calls."""
    agent = MagicMock(spec=RawAgent)
    agent.id = "test-agent"
    agent.name = "Test Agent"
    agent.description = "A mock agent for testing"
    agent.context_providers = []

    def create_session(*, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    agent.create_session.side_effect = create_session

    call_index = [0]

    async def _stream_gen(updates: list[AgentResponseUpdate]) -> AsyncIterator[AgentResponseUpdate]:
        for update in updates:
            yield update

    async def _response_gen(response: AgentResponse) -> AsyncIterator[AgentResponseUpdate]:
        for message in response.messages:
            yield AgentResponseUpdate(contents=message.contents, role=message.role)

    def run_dispatch(*args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        del args, kwargs
        idx = call_index[0]
        call_index[0] += 1
        updates = stream_updates_list[idx] if stream_updates_list is not None else None
        return ResponseStream(
            _stream_gen(updates) if updates is not None else _response_gen(responses[idx]),
            finalizer=AgentResponse.from_updates,
        )

    agent.run = MagicMock(side_effect=run_dispatch)

    return agent


class TestMultiTurnMixedContent:
    """End-to-end multi-turn tests with mixed text and non-text content types."""

    async def test_text_and_image_input_single_turn(self) -> None:
        """Agent receives a message with text and image content via URL."""
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("I see a cat!")])])
        )
        server = _make_server(agent)

        resp = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Describe this animal"},
                            {"type": "input_image", "image_url": "https://example.com/cat.jpg"},
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        # Verify agent received text + image
        messages = agent.run.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert len(messages[0].contents) == 2
        assert messages[0].contents[0].type == "text"
        assert messages[0].contents[0].text == "Describe this animal"
        assert messages[0].contents[1].type == "uri"
        assert messages[0].contents[1].uri == "https://example.com/cat.jpg"

    async def test_text_and_file_input_single_turn(self) -> None:
        """Agent receives a message with text and file content via URL."""
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("File received")])])
        )
        server = _make_server(agent)

        resp = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Summarize this document"},
                            {"type": "input_file", "file_url": "https://example.com/doc.pdf", "filename": "doc.pdf"},
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        messages = agent.run.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert len(messages[0].contents) == 2
        assert messages[0].contents[0].type == "text"
        assert messages[0].contents[0].text == "Summarize this document"
        assert messages[0].contents[1].type == "uri"
        assert messages[0].contents[1].uri == "https://example.com/doc.pdf"

    async def test_text_and_file_data_input_single_turn(self) -> None:
        """Agent receives a message with text and file content via inline file_data."""
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("File received")])])
        )
        server = _make_server(agent)

        resp = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Summarize this document"},
                            {
                                "type": "input_file",
                                "file_data": "data:application/pdf;base64,JVBERi0xLjQ=",
                                "filename": "doc.pdf",
                            },
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        messages = agent.run.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert len(messages[0].contents) == 2
        assert messages[0].contents[0].type == "text"
        assert messages[0].contents[0].text == "Summarize this document"
        assert messages[0].contents[1].type == "data"
        assert messages[0].contents[1].uri == "data:application/pdf;base64,JVBERi0xLjQ="

    async def test_text_mime_file_data_decoded(self) -> None:
        """Agent receives a text/* file_data that is base64-decoded to plain text."""
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Got it")])])
        )
        server = _make_server(agent)

        import base64

        encoded = base64.b64encode(b"Hello, world!").decode()

        resp = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_file",
                                "file_data": f"data:text/plain;base64,{encoded}",
                                "filename": "greeting.txt",
                            },
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200

        messages = agent.run.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0].contents[0].type == "text"
        assert messages[0].contents[0].text == "[File: greeting.txt]\nHello, world!"

    async def test_text_mime_file_data_invalid_base64_falls_through(self) -> None:
        """Invalid base64 in a text/* file_data falls through to URI passthrough."""
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Got it")])])
        )
        server = _make_server(agent)

        resp = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_file",
                                "file_data": "data:text/plain;base64,!!!invalid!!!",
                                "filename": "bad.txt",
                            },
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200

        messages = agent.run.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0].contents[0].type == "data"
        assert messages[0].contents[0].uri == "data:text/plain;base64,!!!invalid!!!"

    async def test_mixed_text_and_image_input(self) -> None:
        """Agent receives a single message with both text and image content."""
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Got it!")])])
        )
        server = _make_server(agent)

        resp = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "What's in this image?"},
                            {"type": "input_image", "image_url": "https://example.com/photo.jpg"},
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        messages = agent.run.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert len(messages[0].contents) == 2
        assert messages[0].contents[0].type == "text"
        assert messages[0].contents[0].text == "What's in this image?"
        assert messages[0].contents[1].type == "uri"
        assert messages[0].contents[1].uri == "https://example.com/photo.jpg"

    async def test_function_call_items_in_input(self) -> None:
        """Input contains function_call and function_call_output items."""
        agent = _make_agent(
            response=AgentResponse(
                messages=[Message(role="assistant", contents=[Content.from_text("Weather is sunny!")])]
            )
        )
        server = _make_server(agent)

        resp = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {"type": "message", "role": "user", "content": "What's the weather?"},
                    {
                        "type": "function_call",
                        "id": "fc-1",
                        "call_id": "call_1",
                        "name": "get_weather",
                        "arguments": '{"city": "NYC"}',
                        "status": "completed",
                    },
                    {"type": "function_call_output", "call_id": "call_1", "output": "sunny, 72F"},
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        messages = agent.run.call_args.kwargs["messages"]
        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[0].contents[0].type == "text"
        assert messages[1].role == "assistant"
        assert messages[1].contents[0].type == "function_call"
        assert messages[1].contents[0].name == "get_weather"
        assert messages[2].role == "tool"
        assert messages[2].contents[0].type == "function_result"
        assert messages[2].contents[0].result == "sunny, 72F"

    async def test_multi_turn_text_then_text_with_image(self) -> None:
        """First turn sends text, second turn sends text + image with previous_response_id."""
        agent = _make_multi_response_agent([
            AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Send me an image")])]),
            AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Nice cat!")])]),
        ])
        server = _make_server(agent)

        # Turn 1: simple text
        resp1 = await _post(server, input_text="Hello", stream=False)
        assert resp1.status_code == 200
        response_id = resp1.json()["id"]

        # Turn 2: text + image input referencing turn 1
        resp2 = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Here is my cat photo"},
                            {"type": "input_image", "image_url": "https://example.com/cat.jpg"},
                        ],
                    }
                ],
                "stream": False,
                "previous_response_id": response_id,
            },
        )

        assert resp2.status_code == 200
        body2 = resp2.json()
        assert body2["status"] == "completed"

        # Verify second call receives history from turn 1 + text+image input
        second_call_messages = agent.run.call_args_list[1].kwargs["messages"]
        # History: output message from turn 1 ("Send me an image")
        # Input: message with text + image
        assert len(second_call_messages) >= 2
        # Last message should be the text+image input
        last_msg = second_call_messages[-1]
        assert last_msg.role == "user"
        assert len(last_msg.contents) == 2
        assert last_msg.contents[0].type == "text"
        assert last_msg.contents[0].text == "Here is my cat photo"
        assert last_msg.contents[1].type == "uri"
        assert last_msg.contents[1].uri == "https://example.com/cat.jpg"
        # History should include the assistant response from turn 1
        history_msgs = second_call_messages[:-1]
        assistant_texts = [
            c.text for m in history_msgs if m.role == "assistant" for c in m.contents if c.type == "text"
        ]
        assert "Send me an image" in assistant_texts

    async def test_multi_turn_function_call_in_history(self) -> None:
        """Turn 1 produces function call + result, turn 2 sees them in history."""
        agent = _make_multi_response_agent([
            AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[Content.from_function_call("call_1", "search", arguments='{"q": "cats"}')],
                    ),
                    Message(role="tool", contents=[Content.from_function_result("call_1", result="found 10 cats")]),
                    Message(role="assistant", contents=[Content.from_text("I found 10 cats!")]),
                ]
            ),
            AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Here are more details")])]),
        ])
        server = _make_server(agent)

        # Turn 1
        resp1 = await _post(server, input_text="Search for cats", stream=False)
        assert resp1.status_code == 200
        response_id = resp1.json()["id"]

        # Verify turn 1 output has function_call, function_call_output, and message
        types1 = [item["type"] for item in resp1.json()["output"]]
        assert "function_call" in types1
        assert "function_call_output" in types1
        assert "message" in types1

        # Turn 2
        resp2 = await _post_json(
            server,
            {
                "model": "test-model",
                "input": "Tell me more",
                "stream": False,
                "previous_response_id": response_id,
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "completed"

        # Verify turn 2 received history including function call/result
        second_call_messages = agent.run.call_args_list[1].kwargs["messages"]
        roles = [m.role for m in second_call_messages]
        assert "assistant" in roles
        assert "tool" in roles
        # The function call should be in the history
        fc_contents = [
            c for m in second_call_messages if m.role == "assistant" for c in m.contents if c.type == "function_call"
        ]
        assert len(fc_contents) >= 1
        assert fc_contents[0].name == "search"

    async def test_hosted_mcp_call_round_trip_does_not_orphan_function_call_output(self) -> None:
        """Turn 1 produces hosted MCP call + result, turn 2 must replay both without orphaning output."""
        agent = _make_multi_response_agent([
            AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_mcp_server_tool_call(
                                call_id="mcp_abc123",
                                tool_name="search",
                                server_name="api_specs",
                                arguments='{"q": "cats"}',
                            )
                        ],
                    ),
                    Message(
                        role="tool",
                        contents=[
                            Content.from_mcp_server_tool_result(
                                call_id="mcp_abc123",
                                output=[Content.from_text(text="found 10 cats")],
                            )
                        ],
                    ),
                    Message(role="assistant", contents=[Content.from_text("I found 10 cats!")]),
                ]
            ),
            AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Here are more details")])]),
        ])
        server = _make_server(agent)

        resp1 = await _post(server, input_text="Search for cats", stream=False)
        assert resp1.status_code == 200
        response_id = resp1.json()["id"]

        types1 = [item["type"] for item in resp1.json()["output"]]
        assert "mcp_call" in types1
        assert "custom_tool_call_output" not in types1

        resp2 = await _post_json(
            server,
            {
                "model": "test-model",
                "input": "Tell me more",
                "stream": False,
                "previous_response_id": response_id,
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "completed"

        second_call_messages = agent.run.call_args_list[1].kwargs["messages"]
        mcp_call_contents = [c for m in second_call_messages for c in m.contents if c.type == "mcp_server_tool_call"]
        mcp_result_contents = [
            c for m in second_call_messages for c in m.contents if c.type == "mcp_server_tool_result"
        ]
        function_result_contents = [c for m in second_call_messages for c in m.contents if c.type == "function_result"]

        assert len(mcp_call_contents) >= 1
        assert len(mcp_result_contents) >= 1
        assert all((c.call_id or "") != "mcp_abc123" for c in function_result_contents)
        assert any((c.call_id or "") == "mcp_abc123" for c in mcp_call_contents)
        assert any((c.call_id or "") == "mcp_abc123" for c in mcp_result_contents)

    async def test_multi_turn_reasoning_in_history(self) -> None:
        """Turn 1 produces reasoning + text, turn 2 sees them in history."""
        agent = _make_multi_response_agent([
            AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_text_reasoning(text="Let me think about this..."),
                            Content.from_text("The answer is 42"),
                        ],
                    ),
                ]
            ),
            AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Indeed, it is 42")])]),
        ])
        server = _make_server(agent)

        # Turn 1
        resp1 = await _post(server, input_text="What is the answer?", stream=False)
        assert resp1.status_code == 200
        response_id = resp1.json()["id"]
        types1 = [item["type"] for item in resp1.json()["output"]]
        assert "reasoning" in types1
        assert "message" in types1

        # Turn 2
        resp2 = await _post_json(
            server,
            {
                "model": "test-model",
                "input": "Are you sure?",
                "stream": False,
                "previous_response_id": response_id,
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "completed"

        # Verify history includes the reasoning and text from turn 1
        second_call_messages = agent.run.call_args_list[1].kwargs["messages"]
        assert len(second_call_messages) >= 2  # history + new input

    async def test_multi_turn_with_mixed_content_and_streaming(self) -> None:
        """Turn 1 non-streaming, turn 2 streaming with image input."""
        turn2_updates = [
            AgentResponseUpdate(contents=[Content.from_text("I see ")], role="assistant"),
            AgentResponseUpdate(contents=[Content.from_text("a cat!")], role="assistant"),
        ]

        agent = _make_multi_response_agent(
            responses=[
                AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Send me an image")])]),
                AgentResponse(messages=[]),  # placeholder, not used for streaming
            ],
            stream_updates_list=[
                [],  # placeholder for turn 1 (non-streaming)
                turn2_updates,
            ],
        )
        server = _make_server(agent)

        # Turn 1: non-streaming text
        resp1 = await _post(server, input_text="Hello", stream=False)
        assert resp1.status_code == 200
        response_id = resp1.json()["id"]

        # Turn 2: streaming with image input
        resp2 = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Describe this:"},
                            {"type": "input_image", "image_url": "https://example.com/cat.jpg"},
                        ],
                    }
                ],
                "stream": True,
                "previous_response_id": response_id,
            },
        )

        assert resp2.status_code == 200
        assert "text/event-stream" in resp2.headers["content-type"]

        events = _parse_sse_events(resp2.text)
        types = _sse_event_types(events)
        assert types[0] == "response.created"
        assert types[-1] == "response.completed"
        assert "response.output_text.delta" in types

        # Verify accumulated text
        text_done = [e for e in events if e["event"] == "response.output_text.done"]
        assert len(text_done) == 1
        assert text_done[0]["data"]["text"] == "I see a cat!"

    async def test_text_with_mcp_call_items(self) -> None:
        """Input contains text message + mcp_call item and the agent processes it."""
        agent = _make_agent(
            response=AgentResponse(
                messages=[Message(role="assistant", contents=[Content.from_text("MCP result received")])]
            )
        )
        server = _make_server(agent)

        resp = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {"type": "message", "role": "user", "content": "Search using MCP"},
                    {
                        "type": "mcp_call",
                        "id": "mcp-1",
                        "server_label": "my_server",
                        "name": "search",
                        "arguments": '{"query": "test"}',
                    },
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        messages = agent.run.call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].contents[0].type == "text"
        assert messages[0].contents[0].text == "Search using MCP"
        assert messages[1].role == "assistant"
        assert messages[1].contents[0].type == "mcp_server_tool_call"
        assert messages[1].contents[0].server_name == "my_server"
        assert messages[1].contents[0].tool_name == "search"

    async def test_three_turn_conversation_with_mixed_content(self) -> None:
        """Three-turn conversation: text → function call → image input."""
        agent = _make_multi_response_agent([
            AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Hello! How can I help?")])]),
            AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[Content.from_function_call("call_1", "analyze", arguments='{"mode": "deep"}')],
                    ),
                    Message(role="tool", contents=[Content.from_function_result("call_1", result="analysis complete")]),
                    Message(role="assistant", contents=[Content.from_text("Analysis done!")]),
                ]
            ),
            AgentResponse(
                messages=[Message(role="assistant", contents=[Content.from_text("The image shows a chart")])]
            ),
        ])
        server = _make_server(agent)

        # Turn 1: text
        resp1 = await _post(server, input_text="Hi", stream=False)
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        # Turn 2: text, referencing turn 1
        resp2 = await _post_json(
            server,
            {
                "model": "test-model",
                "input": "Analyze something",
                "stream": False,
                "previous_response_id": id1,
            },
        )
        assert resp2.status_code == 200
        id2 = resp2.json()["id"]

        # Turn 3: image input, referencing turn 2
        resp3 = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "What about this image?"},
                            {"type": "input_image", "image_url": "https://example.com/chart.png"},
                        ],
                    }
                ],
                "stream": False,
                "previous_response_id": id2,
            },
        )

        assert resp3.status_code == 200
        assert resp3.json()["status"] == "completed"

        # Verify turn 3 received full history from turns 1+2 plus new image input
        third_call_messages = agent.run.call_args_list[2].kwargs["messages"]
        # Should have: history from turn 1 (assistant text) + history from turn 2
        # (function_call, function_call_output, text) + new input (text + image)
        assert len(third_call_messages) >= 5

        # Last message should contain the image
        last_msg = third_call_messages[-1]
        assert last_msg.role == "user"
        image_contents = [c for c in last_msg.contents if c.type == "uri"]
        assert len(image_contents) == 1
        assert image_contents[0].uri == "https://example.com/chart.png"

        # History should include function call from turn 2
        fc_contents = [
            c
            for m in third_call_messages[:-1]
            if m.role == "assistant"
            for c in m.contents
            if c.type == "function_call"
        ]
        assert any(c.name == "analyze" for c in fc_contents)

    async def test_input_with_hosted_file_image(self) -> None:
        """Input contains an image referenced by file_id (hosted file)."""
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Image analyzed")])])
        )
        server = _make_server(agent)

        resp = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Analyze this image"},
                            {"type": "input_image", "file_id": "file-abc123"},
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        messages = agent.run.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert len(messages[0].contents) == 2
        assert messages[0].contents[0].type == "text"
        assert messages[0].contents[0].text == "Analyze this image"
        assert messages[0].contents[1].type == "hosted_file"
        assert messages[0].contents[1].file_id == "file-abc123"

    async def test_multi_turn_text_and_image_then_text_and_file(self) -> None:
        """Turn 1 sends text+image, turn 2 sends text+file, both in history."""
        agent = _make_multi_response_agent([
            AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("I see a landscape")])]),
            AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Document summarized")])]),
        ])
        server = _make_server(agent)

        # Turn 1: text + image
        resp1 = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "What is in this photo?"},
                            {"type": "input_image", "image_url": "https://example.com/landscape.jpg"},
                        ],
                    }
                ],
                "stream": False,
            },
        )
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        # Turn 2: text + file, referencing turn 1
        resp2 = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Now summarize this report"},
                            {
                                "type": "input_file",
                                "file_url": "https://example.com/report.pdf",
                                "filename": "report.pdf",
                            },
                        ],
                    }
                ],
                "stream": False,
                "previous_response_id": id1,
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "completed"

        # Verify turn 2 received history from turn 1 + new text+file input
        second_call_messages = agent.run.call_args_list[1].kwargs["messages"]
        assert len(second_call_messages) >= 2

        # History should include the assistant response from turn 1
        assistant_texts = [
            c.text for m in second_call_messages if m.role == "assistant" for c in m.contents if c.type == "text"
        ]
        assert "I see a landscape" in assistant_texts

        # Last message should be text + file
        last_msg = second_call_messages[-1]
        assert last_msg.role == "user"
        assert len(last_msg.contents) == 2
        assert last_msg.contents[0].type == "text"
        assert last_msg.contents[0].text == "Now summarize this report"
        assert last_msg.contents[1].type == "uri"
        assert last_msg.contents[1].uri == "https://example.com/report.pdf"

    async def test_multi_turn_function_call_then_text_and_image(self) -> None:
        """Turn 1: text + function call + result, turn 2: text + image."""
        agent = _make_multi_response_agent([
            AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[Content.from_function_call("call_1", "get_info", arguments='{"id": 1}')],
                    ),
                    Message(role="tool", contents=[Content.from_function_result("call_1", result="info data")]),
                    Message(role="assistant", contents=[Content.from_text("Here is the info")]),
                ]
            ),
            AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Image matches the data")])]),
        ])
        server = _make_server(agent)

        # Turn 1: text triggers function call
        resp1 = await _post(server, input_text="Get info for item 1", stream=False)
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        types1 = [item["type"] for item in resp1.json()["output"]]
        assert "function_call" in types1
        assert "function_call_output" in types1
        assert "message" in types1

        # Turn 2: text + image referencing turn 1
        resp2 = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Does this image match?"},
                            {"type": "input_image", "image_url": "https://example.com/item1.jpg"},
                        ],
                    }
                ],
                "stream": False,
                "previous_response_id": id1,
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "completed"

        # Verify turn 2 received history with function call + new text+image
        second_call_messages = agent.run.call_args_list[1].kwargs["messages"]
        # History should contain function_call and function_result from turn 1
        fc_contents = [
            c for m in second_call_messages if m.role == "assistant" for c in m.contents if c.type == "function_call"
        ]
        assert any(c.name == "get_info" for c in fc_contents)
        tool_contents = [
            c for m in second_call_messages if m.role == "tool" for c in m.contents if c.type == "function_result"
        ]
        assert any(c.result == "info data" for c in tool_contents)

        # Last message should be text + image
        last_msg = second_call_messages[-1]
        assert last_msg.role == "user"
        assert len(last_msg.contents) == 2
        assert last_msg.contents[0].type == "text"
        assert last_msg.contents[0].text == "Does this image match?"
        assert last_msg.contents[1].type == "uri"
        assert last_msg.contents[1].uri == "https://example.com/item1.jpg"


# endregion


# region Function approval round-trip


class TestFunctionApprovalConversion:
    """Tests for the approval-aware paths in `_item_to_message` / `_output_item_to_message`."""

    async def test_output_item_mcp_approval_request_loads_from_storage(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpApprovalRequest

        saved = _make_function_approval_request_content(request_id="apr-1")
        storage = _function_approval_store(saved)

        item = OutputItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "apr-1",
            "server_label": "srv",
            "name": "dangerous_tool",
            "arguments": "{}",
        })
        msg = await _output_item_to_message(item, approval_storage=storage)
        assert msg.role == "assistant"
        c = msg.contents[0]
        assert c.type == "function_approval_request"
        assert c.id == "apr-1"
        # The full saved Content (incl. function_call) is restored.
        function_call = c.function_call
        assert function_call is not None
        assert function_call.name == "delete_file"

    async def test_output_item_mcp_approval_request_without_storage_raises(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpApprovalRequest

        item = OutputItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "apr-1",
            "server_label": "srv",
            "name": "dangerous_tool",
            "arguments": "{}",
        })
        with pytest.raises(ValueError, match="ApprovalStorage is required"):
            await _output_item_to_message(item)

    async def test_output_item_mcp_approval_response_resolves_to_approval_response(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpApprovalResponseResource

        saved = _make_function_approval_request_content(request_id="apr-1")
        storage = _function_approval_store(saved)

        item = OutputItemMcpApprovalResponseResource({
            "type": "mcp_approval_response",
            "id": "resp-1",
            "approval_request_id": "apr-1",
            "approve": True,
        })
        msg = await _output_item_to_message(item, approval_storage=storage)
        assert msg.role == "user"
        c = msg.contents[0]
        assert c.type == "function_approval_response"
        assert c.approved is True
        assert c.id == "apr-1"
        function_call = c.function_call
        assert function_call is not None
        assert function_call.name == "delete_file"

    async def test_output_item_mcp_approval_response_without_storage_raises(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpApprovalResponseResource

        item = OutputItemMcpApprovalResponseResource({
            "type": "mcp_approval_response",
            "id": "resp-1",
            "approval_request_id": "apr-1",
            "approve": False,
        })
        with pytest.raises(ValueError, match="ApprovalStorage is required"):
            await _output_item_to_message(item)

    async def test_input_item_mcp_approval_request_loads_from_storage(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMcpApprovalRequest

        saved = _make_function_approval_request_content(request_id="apr-1")
        storage = _function_approval_store(saved)

        item = ItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "apr-1",
            "server_label": "srv",
            "name": "dangerous_tool",
            "arguments": "{}",
        })
        msg = await _item_to_message(item, approval_storage=storage)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_approval_request"
        assert msg.contents[0].id == "apr-1"

    async def test_input_item_mcp_approval_response_resolves_to_approval_response(self) -> None:
        from azure.ai.agentserver.responses.models import MCPApprovalResponse

        saved = _make_function_approval_request_content(request_id="apr-1")
        storage = _function_approval_store(saved)

        item = MCPApprovalResponse({
            "type": "mcp_approval_response",
            "approval_request_id": "apr-1",
            "approve": False,
        })
        msg = await _item_to_message(item, approval_storage=storage)
        assert msg.role == "user"
        c = msg.contents[0]
        assert c.type == "function_approval_response"
        assert c.approved is False


class TestFunctionApprovalRoundTrip:
    """End-to-end round-trip tests for the function approval flow.

    Turn 1: the agent emits a `function_approval_request` content; the
        server emits an `mcp_approval_request` output item and persists
        the original Content under the emitted id in approval storage.
    Turn 2: the caller sends an `mcp_approval_response` input item back;
        the server resolves it (via approval storage) into a
        `function_approval_response` content delivered to the agent.
    """

    async def test_non_streaming_emits_mcp_approval_request_and_persists_to_storage(self) -> None:
        request_content = _make_function_approval_request_content()
        agent = _make_agent(response=AgentResponse(messages=[Message(role="assistant", contents=[request_content])]))
        server = _make_server(agent)

        resp = await _post(server, stream=False)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        approval_items = [item for item in body["output"] if item["type"] == "mcp_approval_request"]
        assert len(approval_items) == 1
        approval_request_id = approval_items[0]["id"]
        assert approval_items[0]["name"] == "delete_file"
        assert approval_items[0]["server_label"] == "my_server"

        # Storage must contain a saved entry under the emitted request id.
        loaded = await server._function_approval_storage_provider.get_store(  # pyright: ignore[reportPrivateUsage]
            config=server.config, platform_context=get_request_context()
        ).load_approval_request(approval_request_id)
        assert loaded.type == "function_approval_request"
        assert loaded.function_call is not None
        assert loaded.function_call.name == "delete_file"

    async def test_streaming_emits_mcp_approval_request_and_persists_to_storage(self) -> None:
        request_content = _make_function_approval_request_content(request_id="apr_streaming")
        agent = _make_agent(stream_updates=[AgentResponseUpdate(contents=[request_content], role="assistant")])
        server = _make_server(agent)

        resp = await _post(server, stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)
        assert types[0] == "response.created"
        assert types[-1] == "response.completed"

        approval_request_id: str | None = None
        for e in events:
            if e["event"] != "response.output_item.added":
                continue
            item: dict[str, Any] = e["data"].get("item") or {}
            if item.get("type") == "mcp_approval_request":
                approval_request_id = item.get("id")
                break
        assert approval_request_id is not None

        loaded = await server._function_approval_storage_provider.get_store(  # pyright: ignore[reportPrivateUsage]
            config=server.config, platform_context=get_request_context()
        ).load_approval_request(approval_request_id)
        assert loaded.type == "function_approval_request"

    async def test_round_trip_approval_response_reaches_agent(self) -> None:
        """Two-turn: turn 1 emits an approval request; turn 2 sends an
        approval response and the agent receives a `function_approval_response`."""
        request_content = _make_function_approval_request_content()

        agent = _make_multi_response_agent(
            responses=[
                AgentResponse(messages=[Message(role="assistant", contents=[request_content])]),
                AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("done")])]),
            ]
        )
        server = _make_server(agent)

        first = await _post(server, stream=False)
        assert first.status_code == 200
        first_body = first.json()
        approval_items = [item for item in first_body["output"] if item["type"] == "mcp_approval_request"]
        assert len(approval_items) == 1
        approval_request_id = approval_items[0]["id"]

        # Send back an approval response that references the saved request id.
        second_payload: dict[str, Any] = {
            "model": "test-model",
            "input": [
                {
                    "type": "mcp_approval_response",
                    "approval_request_id": approval_request_id,
                    "approve": True,
                }
            ],
            "stream": False,
        }
        second = await _post_json(server, second_payload)
        assert second.status_code == 200

        # The agent's second invocation must have received a
        # function_approval_response content carrying the original function_call.
        assert agent.run.call_count == 2
        second_call_kwargs = agent.run.call_args_list[1].kwargs
        approval_responses = [
            c for m in second_call_kwargs["messages"] for c in m.contents if c.type == "function_approval_response"
        ]
        assert len(approval_responses) == 1
        assert approval_responses[0].approved is True
        assert approval_responses[0].function_call.name == "delete_file"

    async def test_round_trip_approval_response_rejected(self) -> None:
        """Same as above but the user rejects the approval; the agent must
        receive `approved=False`."""
        request_content = _make_function_approval_request_content()

        agent = _make_multi_response_agent(
            responses=[
                AgentResponse(messages=[Message(role="assistant", contents=[request_content])]),
                AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("ok")])]),
            ]
        )
        server = _make_server(agent)

        first = await _post(server, stream=False)
        approval_request_id = next(
            item["id"] for item in first.json()["output"] if item["type"] == "mcp_approval_request"
        )

        second = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "mcp_approval_response",
                        "approval_request_id": approval_request_id,
                        "approve": False,
                    }
                ],
                "stream": False,
            },
        )
        assert second.status_code == 200

        second_call_kwargs = agent.run.call_args_list[1].kwargs
        approval_responses = [
            c for m in second_call_kwargs["messages"] for c in m.contents if c.type == "function_approval_response"
        ]
        assert len(approval_responses) == 1
        assert approval_responses[0].approved is False

    async def test_approval_response_referencing_unknown_id_fails(self) -> None:
        """Sending an `mcp_approval_response` for a request id that was
        never persisted must surface as a ``response.failed`` event whose
        ``error.message`` contains the missing approval request id."""
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("ok")])])
        )
        server = _make_server(agent)

        resp = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "mcp_approval_response",
                        "approval_request_id": "apr_unknown",
                        "approve": True,
                    }
                ],
                "stream": False,
            },
        )
        # The handler converts the underlying KeyError into a terminal
        # ``response.failed`` event, so non-streaming callers see HTTP 200
        # with status="failed" and a meaningful error message rather than
        # a generic 5xx response.
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        error: dict[str, Any] = body.get("error") or {}
        assert "apr_unknown" in (error.get("message") or "")


# endregion


# region Checkpoint context validation


class TestCheckpointContextValidation:
    @pytest.mark.parametrize(
        ("context_field", "bad_id"),
        [
            ("previous_response_id", "../../escape"),
            ("conversation_id", "foo/bar"),
            ("response_id", "..\\..\\escape"),
        ],
    )
    async def test_workflow_rejects_invalid_checkpoint_scope(
        self,
        context_field: str,
        bad_id: str,
    ) -> None:
        agent = MagicMock(spec=WorkflowAgent)
        agent.context_providers = []
        agent.workflow = MagicMock()
        agent.workflow.name = "workflow"
        agent.workflow._runner_context.has_checkpointing.return_value = False
        server = ResponsesHostServer(agent, store=InMemoryResponseProvider())

        context_kwargs: dict[str, Any] = {"response_id": "response-current", "mode_flags": MagicMock()}
        request = CreateResponse(model="m", input="hi")
        if context_field == "previous_response_id":
            request = CreateResponse(model="m", input="hi", previous_response_id=bad_id)
            context_kwargs["previous_response_id"] = bad_id
        else:
            context_kwargs[context_field] = bad_id

        with patch.object(ResponseContext, "get_input_items", new=AsyncMock(return_value=[])):
            events = [
                event
                async for event in server._handle_inner_workflow(  # pyright: ignore[reportPrivateUsage]
                    request,
                    ResponseContext(**context_kwargs),
                )
            ]

        failed_events = [event for event in events if event.get("type") == "response.failed"]
        assert len(failed_events) == 1
        failed_event = cast(Mapping[str, Any], failed_events[0])
        response = cast(Mapping[str, Any], failed_event["response"])
        error = cast(Mapping[str, Any], response["error"])
        assert "Invalid context id" in error["message"]
        agent.run.assert_not_called()

    # endregion


# region Agent lifecycle (lazy entry & OAuth consent surfacing)


def _make_consent_error(
    url: str = "https://consent.example.com/auth",
    name: str = "Foundry Toolbox",
    source_type: str = "mcp",
) -> Exception:
    """Build an exception wrapping a Foundry MCP gateway consent error.

    Mirrors the real-world wrapping produced by ``MCPStreamableHTTPTool.__aenter__``,
    which catches connection-time ``McpError``s and re-raises them as a
    ``ToolExecutionException`` (an ``AgentFrameworkException`` subclass) with the
    original error attached via ``inner_exception``. ``consent_url_from_error``
    then finds the wrapped ``McpError`` in ``exc.args``.

    The McpError message uses the structured Foundry MCP gateway format:
    a human-readable prefix followed by a JSON document describing each
    failed tool source and its consent URL.
    """
    from agent_framework.exceptions import ToolExecutionException

    payload = json.dumps({
        "errors": [
            {
                "name": name,
                "type": source_type,
                "error": {
                    "code": "CONSENT_REQUIRED",
                    "message": url,
                },
            }
        ]
    })
    message = f"tools/list failed for 1 tool source(s), succeeded for 0 tool source(s) {payload}"
    inner = McpError(ErrorData(code=CONSENT_ERROR_CODE, message=message))
    return ToolExecutionException("MCP consent required", inner_exception=inner)


class TestConsentUrlFromError:
    def test_returns_consent_url_when_inner_arg_is_consent_mcp_error(self) -> None:
        exc = _make_consent_error("https://example.com/consent", name="my-tool")
        assert consent_url_from_error(exc) == [ConsentError(name="my-tool", consent_url="https://example.com/consent")]

    def test_returns_consent_url_for_a2a_preview_source(self) -> None:
        exc = _make_consent_error(
            "https://example.com/a2a-consent",
            name="work-iq",
            source_type="a2a_preview",
        )
        assert consent_url_from_error(exc) == [
            ConsentError(name="work-iq", consent_url="https://example.com/a2a-consent")
        ]

    def test_returns_none_when_no_mcp_error_in_args(self) -> None:
        assert consent_url_from_error(Exception("boom")) is None

    def test_returns_none_when_mcp_error_has_different_code(self) -> None:
        inner = McpError(ErrorData(code=-32000, message="some other error"))
        exc = Exception("wrapped", inner)
        assert consent_url_from_error(exc) is None

    def test_returns_none_for_bare_mcp_error_without_wrapping(self) -> None:
        # `args` of a bare McpError holds the message string, not an McpError
        # instance, so it does not match the wrapping pattern produced by the
        # MCP client when it bubbles consent errors up.
        bare = McpError(ErrorData(code=CONSENT_ERROR_CODE, message="https://x"))
        assert consent_url_from_error(bare) is None

    def test_returns_none_when_message_has_no_json(self) -> None:
        from agent_framework.exceptions import ToolExecutionException

        inner = McpError(ErrorData(code=CONSENT_ERROR_CODE, message="no json here"))
        exc = ToolExecutionException("MCP consent required", inner_exception=inner)
        assert consent_url_from_error(exc) is None


class TestAgentLifecycle:
    async def test_agent_entered_lazily_on_first_request(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        server = _make_server(agent)
        # Construction must not enter the agent.
        assert agent.__aenter__.await_count == 0

        await _post(server, input_text="hello", stream=False)
        assert agent.__aenter__.await_count == 1

    async def test_agent_entered_only_once_across_requests(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        server = _make_server(agent)

        await _post(server, input_text="first", stream=False)
        await _post(server, input_text="second", stream=False)
        await _post(server, input_text="third", stream=False)
        assert agent.__aenter__.await_count == 1

    async def test_cleanup_exits_agent_and_allows_reentry(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        server = _make_server(agent)

        await _post(server, input_text="hello", stream=False)
        assert agent.__aenter__.await_count == 1
        assert agent.__aexit__.await_count == 0

        await server._cleanup_agent()  # pyright: ignore[reportPrivateUsage]
        assert agent.__aexit__.await_count == 1

        # Cleanup is idempotent.
        await server._cleanup_agent()  # pyright: ignore[reportPrivateUsage]
        assert agent.__aexit__.await_count == 1

        # After cleanup, a follow-up request re-enters the agent.
        await _post(server, input_text="again", stream=False)
        assert agent.__aenter__.await_count == 2

    async def test_failed_entry_does_not_cache_stack(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        agent.__aenter__.side_effect = [_make_consent_error(), None]
        server = _make_server(agent)

        await _post(server, input_text="first", stream=False)
        # Failed entry must leave the stack empty so the next request retries.
        await _post(server, input_text="second", stream=False)
        assert agent.__aenter__.await_count == 2


class TestOAuthConsentSurfacing:
    async def test_non_streaming_consent_error_emits_oauth_output_item(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        agent.__aenter__.side_effect = _make_consent_error("https://consent.example.com/auth")
        server = _make_server(agent)

        resp = await _post(server, input_text="hello", stream=False)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "incomplete"

        oauth_items = [it for it in body["output"] if it["type"] == "oauth_consent_request"]
        assert len(oauth_items) == 1
        assert oauth_items[0]["consent_link"] == "https://consent.example.com/auth"
        assert oauth_items[0]["server_label"] == "Foundry Toolbox"

        # The agent must not be run when entry fails.
        agent.run.assert_not_called()

    async def test_streaming_consent_error_emits_oauth_output_item(self) -> None:
        agent = _make_agent(stream_updates=[AgentResponseUpdate(contents=[Content.from_text("hi")], role="assistant")])
        agent.__aenter__.side_effect = _make_consent_error("https://consent.example.com/auth")
        server = _make_server(agent)

        resp = await _post(server, input_text="hello", stream=True)
        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        assert types[0] == "response.created"
        assert types[1] == "response.in_progress"
        assert types[-1] == "response.incomplete"

        added = [e for e in events if e["event"] == "response.output_item.added"]
        oauth_added = [e for e in added if e["data"]["item"]["type"] == "oauth_consent_request"]
        assert len(oauth_added) == 1
        assert oauth_added[0]["data"]["item"]["consent_link"] == "https://consent.example.com/auth"
        assert oauth_added[0]["data"]["item"]["server_label"] == "Foundry Toolbox"

        done = [e for e in events if e["event"] == "response.output_item.done"]
        assert any(e["data"]["item"]["type"] == "oauth_consent_request" for e in done)

        agent.run.assert_not_called()

    async def test_non_consent_error_during_entry_propagates(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        agent.__aenter__.side_effect = RuntimeError("boom")
        server = _make_server(agent)

        resp = await _post(server, input_text="hello", stream=False)
        # Non-consent errors are not swallowed: the response is marked failed
        # and no `oauth_consent_request` item is emitted. The exception
        # message is propagated to the client via ``error.message``.
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert not any(it["type"] == "oauth_consent_request" for it in body.get("output", []))
        error: dict[str, Any] = body.get("error") or {}
        assert error.get("message") == "An internal server error occurred."
        agent.run.assert_not_called()

    async def test_retry_after_consent_succeeds(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hello!")])])
        )
        agent.__aenter__.side_effect = [_make_consent_error("https://consent.example.com/auth"), None]
        server = _make_server(agent)

        # First request surfaces consent; agent.run is not called.
        resp1 = await _post(server, input_text="first", stream=False)
        assert resp1.status_code == 200
        body1 = resp1.json()
        oauth = [it for it in body1["output"] if it["type"] == "oauth_consent_request"]
        assert len(oauth) == 1
        agent.run.assert_not_called()

        # After the user authenticates, the next request enters successfully.
        resp2 = await _post(server, input_text="second", stream=False)
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert body2["status"] == "completed"
        assert any(it["type"] == "message" for it in body2["output"])
        assert agent.__aenter__.await_count == 2
        agent.run.assert_called_once()


# endregion

# region Error handling (response.failed surfacing)


class TestResponseFailedSurfacing:
    """Tests that exceptions raised by the hosted agent are converted into
    terminal ``response.failed`` events carrying the exception message,
    rather than propagating as 5xx HTTP errors or being replaced by the
    orchestrator's generic ``"An internal server error occurred."``
    fallback.
    """

    async def test_non_streaming_run_failure_emits_response_failed(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )

        def run_failure(*args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del args, kwargs
            return ResponseStream(
                _raising_updates("non-stream kaboom"),
                finalizer=AgentResponse.from_updates,
            )

        agent.run = MagicMock(side_effect=run_failure)
        server = _make_server(agent)

        resp = await _post(server, input_text="hello", stream=False)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        error: dict[str, Any] = body.get("error") or {}
        assert error.get("message") == "non-stream kaboom"

    async def test_streaming_run_failure_emits_response_failed(self) -> None:
        async def _raise_stream() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text("partial ")], role="assistant")
            raise RuntimeError("stream kaboom")

        agent = MagicMock(spec=RawAgent)
        agent.id = "test-agent"
        agent.name = "Test Agent"
        agent.description = "A mock agent for testing"
        agent.context_providers = []

        def create_session(*, session_id: str | None = None) -> AgentSession:
            return AgentSession(session_id=session_id)

        agent.create_session.side_effect = create_session

        def run_streaming(*args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del args
            assert kwargs.get("stream") is True
            return ResponseStream(_raise_stream(), finalizer=AgentResponse.from_updates)

        agent.run = MagicMock(side_effect=run_streaming)
        server = _make_server(agent)

        resp = await _post(server, input_text="hello", stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)
        assert types[0] == "response.created"
        assert types[1] == "response.in_progress"
        # Last lifecycle event must be ``response.failed``, never ``response.completed``.
        assert types[-1] == "response.failed"
        assert "response.completed" not in types

        failed = [e for e in events if e["event"] == "response.failed"]
        assert len(failed) == 1
        response_payload: dict[str, Any] = failed[0]["data"].get("response") or {}
        error: dict[str, Any] = response_payload.get("error") or {}
        assert error.get("message") == "stream kaboom"

    async def test_streaming_run_failure_drains_pending_output_item(self) -> None:
        """If a streaming output item was open when the failure happens, the
        handler must close it before emitting ``response.failed`` so the SSE
        stream stays well-formed (every ``output_item.added`` has a matching
        ``output_item.done``).
        """

        async def _raise_stream() -> AsyncIterator[AgentResponseUpdate]:
            # Open a text output item, then blow up before it closes.
            yield AgentResponseUpdate(contents=[Content.from_text("hello ")], role="assistant")
            raise RuntimeError("mid-item kaboom")

        agent = MagicMock(spec=RawAgent)
        agent.id = "test-agent"
        agent.name = "Test Agent"
        agent.description = "A mock agent for testing"
        agent.context_providers = []

        def create_session(*, session_id: str | None = None) -> AgentSession:
            return AgentSession(session_id=session_id)

        agent.create_session.side_effect = create_session

        def run_streaming(*args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del args, kwargs
            return ResponseStream(_raise_stream(), finalizer=AgentResponse.from_updates)

        agent.run = MagicMock(side_effect=run_streaming)
        server = _make_server(agent)

        resp = await _post(server, input_text="hello", stream=True)

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)
        assert types.count("response.output_item.added") == types.count("response.output_item.done")
        assert types[-1] == "response.failed"

    async def test_workflow_agent_run_failure_emits_response_failed(self) -> None:
        """Exceptions raised by a hosted ``WorkflowAgent`` are converted into a
        terminal ``response.failed`` event in the same way as the regular
        agent path.
        """
        workflow_agent = _build_text_workflow_agent("ignored")

        def run_failure(*args: Any, **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            del args, kwargs
            return ResponseStream(
                _raising_updates("workflow kaboom"),
                finalizer=AgentResponse.from_updates,
            )

        # Patch the public ``run`` to fail. ``_handle_inner_workflow`` only
        # invokes the agent once (no checkpoint to restore on a fresh
        # request), so this is the call that will raise.
        with patch.object(workflow_agent, "run", side_effect=run_failure):
            server = _make_server(workflow_agent)
            resp = await _post(server, input_text="hello", stream=False)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        error: dict[str, Any] = body.get("error") or {}
        assert error.get("message") == "workflow kaboom"


# endregion

# region Workflow agent hosting (end-to-end)


class _ToolApprovalWorkflowAgentMock(SupportsAgentRun):
    """Inner agent for a hosted ``WorkflowAgent`` whose first run emits a
    ``FunctionApprovalRequestContent`` and whose follow-up run (after
    receiving a ``FunctionApprovalResponseContent`` in its inputs) returns a
    final assistant text response.

    Mirrors a real agent whose tool invocation requires user approval. Used
    here to exercise the full HTTP pipeline through ``ResponsesHostServer``
    when the hosted agent is a ``WorkflowAgent`` containing a tool-approval
    flow.
    """

    def __init__(
        self,
        name: str,
        *,
        tool_name: str = "delete_file",
        tool_arguments: dict[str, Any] | None = None,
        approval_request_ids: Sequence[str] | None = None,
        final_text: str = "done",
    ) -> None:
        self.id = str(uuid.uuid4())
        self.name = name
        self.description: str | None = None
        self._tool_name = tool_name
        self._tool_arguments = tool_arguments or {"path": "/tmp/example"}
        self._approval_request_ids: list[str] = list(approval_request_ids) if approval_request_ids else []
        self._final_text = final_text
        self.run_count = 0
        self.last_run_messages: list[Message] = []

    def create_session(self, **kwargs: Any) -> AgentSession:
        del kwargs
        return AgentSession()

    def get_session(self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None) -> AgentSession:
        del service_session_id, session_id
        return AgentSession()

    def _next_request_id(self) -> str:
        # Stable across calls: when the workflow checkpoint round-trips through
        # restore, ``AgentExecutor`` re-invokes the inner agent during replay.
        # We must surface the *same* approval request id on each invocation so
        # the workflow's pending-request id matches the id the test echoes
        # back as ``mcp_approval_response``.
        if self._approval_request_ids:
            return self._approval_request_ids[0]
        return str(uuid.uuid4())

    def _build_approval_request(self) -> Content:
        request_id = self._next_request_id()
        function_call = Content.from_function_call(
            call_id=request_id,
            name=self._tool_name,
            arguments=self._tool_arguments,
            additional_properties={"server_label": "test_server"},
        )
        return Content.from_function_approval_request(id=request_id, function_call=function_call)

    @overload
    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = ...,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = ...,
        *,
        stream: Literal[True],
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        del session
        assert stream is True, "The inner agent only runs in stream mode in Foundry Hosted Agents."
        return self._run_stream(messages=messages, **kwargs)

    @staticmethod
    def _normalize(
        messages: str | Content | Message | Sequence[str | Content | Message] | None,
    ) -> list[Message]:
        if messages is None:
            return []
        if isinstance(messages, str):
            return [Message(role="user", contents=[Content.from_text(text=messages)])]
        if isinstance(messages, Message):
            return [messages]
        if isinstance(messages, Content):
            return [Message(role="user", contents=[messages])]
        result: list[Message] = []
        for item in messages:
            if isinstance(item, Message):
                result.append(item)
            elif isinstance(item, Content):
                result.append(Message(role="user", contents=[item]))
            else:
                result.append(Message(role="user", contents=[Content.from_text(text=item)]))
        return result

    @staticmethod
    def _approval_responses_in(messages: list[Message]) -> list[Content]:
        return [c for m in messages for c in m.contents if c.type == "function_approval_response"]

    def _run_stream(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        del kwargs
        normalized = self._normalize(messages)
        self.last_run_messages = normalized
        self.run_count += 1
        approvals = self._approval_responses_in(normalized)

        async def _iter() -> AsyncIterator[AgentResponseUpdate]:
            if approvals:
                yield AgentResponseUpdate(
                    contents=[Content.from_text(text=self._final_text)],
                    role="assistant",
                    author_name=self.name,
                )
                return
            yield AgentResponseUpdate(
                contents=[self._build_approval_request()],
                role="assistant",
                author_name=self.name,
            )

        return ResponseStream(_iter(), finalizer=AgentResponse.from_updates)


def _build_text_workflow_agent(text: str) -> WorkflowAgent:
    """Build a minimal ``WorkflowAgent`` whose inner agent emits a fixed text."""

    class _TextAgent(SupportsAgentRun):
        def __init__(self, name: str, text: str) -> None:
            self.id = str(uuid.uuid4())
            self.name = name
            self.description: str | None = None
            self._text = text

        def create_session(self, **kwargs: Any) -> AgentSession:
            del kwargs
            return AgentSession()

        def get_session(
            self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None
        ) -> AgentSession:
            del service_session_id, session_id
            return AgentSession()

        @overload
        def run(
            self,
            messages: Any = ...,
            *,
            stream: Literal[False] = ...,
            session: AgentSession | None = ...,
            **kwargs: Any,
        ) -> Awaitable[AgentResponse[Any]]: ...

        @overload
        def run(
            self,
            messages: Any = ...,
            *,
            stream: Literal[True],
            session: AgentSession | None = ...,
            **kwargs: Any,
        ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

        def run(
            self,
            messages: Any = None,
            *,
            stream: bool = False,
            session: AgentSession | None = None,
            **kwargs: Any,
        ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
            del messages, session, kwargs
            assert stream is True, "The inner agent only runs in stream mode in Foundry Hosted Agents."
            text = self._text
            name = self.name

            async def _aiter() -> AsyncIterator[AgentResponseUpdate]:
                yield AgentResponseUpdate(
                    contents=[Content.from_text(text=text)],
                    role="assistant",
                    author_name=name,
                )

            return ResponseStream(_aiter(), finalizer=AgentResponse.from_updates)

    inner = _TextAgent("text-agent", text)

    @executor
    async def start(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

    workflow = WorkflowBuilder(start_executor=start).add_edge(start, inner).build()
    return WorkflowAgent(workflow=workflow, name="Text Workflow Agent")


def _build_approval_workflow_agent(
    *,
    approval_request_id: str,
    tool_name: str = "delete_file",
    tool_arguments: dict[str, Any] | None = None,
    final_text: str = "done",
) -> tuple[WorkflowAgent, _ToolApprovalWorkflowAgentMock]:
    """Build a ``WorkflowAgent`` whose inner agent emits a tool approval request."""
    mock_agent = _ToolApprovalWorkflowAgentMock(
        name="approval-agent",
        tool_name=tool_name,
        tool_arguments=tool_arguments or {"path": "/tmp/secret.txt"},
        approval_request_ids=[approval_request_id],
        final_text=final_text,
    )

    @executor
    async def start(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

    workflow = WorkflowBuilder(start_executor=start).add_edge(start, mock_agent).build()
    workflow_agent = WorkflowAgent(workflow=workflow, name="Approval Workflow Agent")
    return workflow_agent, mock_agent


class TestWorkflowAgentHosting:
    """End-to-end HTTP tests for ``ResponsesHostServer`` hosting a ``WorkflowAgent``.

    These tests drive ``_handle_inner_workflow`` through the ASGI stack:
    they exercise checkpoint write/restore (multi-turn) and the
    tool-approval round-trip path, which is the primary differentiator
    relative to the regular agent path.
    """

    async def test_basic_text_response(self) -> None:
        workflow_agent = _build_text_workflow_agent("hello from workflow")
        server = _make_server(workflow_agent)

        resp = await _post(server, input_text="hi", stream=False)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        text_found = any(
            part.get("type") == "output_text" and part.get("text") == "hello from workflow"
            for item in body["output"]
            if item["type"] == "message"
            for part in item.get("content", [])
        )
        assert text_found, f"Expected workflow output text in {body['output']}"

    async def test_basic_text_response_streaming(self) -> None:
        workflow_agent = _build_text_workflow_agent("hello stream")
        server = _make_server(workflow_agent)

        resp = await _post(server, input_text="hi", stream=True)
        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)
        assert types[0] == "response.created"
        assert types[-1] == "response.completed"
        assert "response.output_text.delta" in types
        text_done = [e for e in events if e["event"] == "response.output_text.done"]
        assert any(e["data"]["text"] == "hello stream" for e in text_done)

    async def test_non_streaming_emits_mcp_approval_request_and_persists_to_storage(self) -> None:
        workflow_agent, mock_agent = _build_approval_workflow_agent(approval_request_id="apr_wf_ns")
        server = _make_server(workflow_agent)

        resp = await _post(server, stream=False)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        approval_items = [it for it in body["output"] if it["type"] == "mcp_approval_request"]
        assert len(approval_items) == 1
        assert approval_items[0]["name"] == "delete_file"
        assert approval_items[0]["server_label"] == "test_server"
        approval_request_id = approval_items[0]["id"]

        # The id surfaced over the wire is generated by the response stream
        # builder; the original approval ``Content`` (carrying the inner
        # ``function_call``) must be persisted under that id so the next
        # turn can reconstruct it.
        loaded = await server._function_approval_storage_provider.get_store(  # pyright: ignore[reportPrivateUsage]
            config=server.config, platform_context=get_request_context()
        ).load_approval_request(approval_request_id)
        assert loaded.type == "function_approval_request"
        assert loaded.function_call is not None
        assert loaded.function_call.name == "delete_file"
        assert mock_agent.run_count == 1

    async def test_streaming_emits_mcp_approval_request_and_persists_to_storage(self) -> None:
        workflow_agent, mock_agent = _build_approval_workflow_agent(approval_request_id="apr_wf_st")
        server = _make_server(workflow_agent)

        resp = await _post(server, stream=True)
        assert resp.status_code == 200

        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)
        assert types[0] == "response.created"
        assert types[-1] == "response.completed"

        approval_request_id: str | None = None
        for e in events:
            if e["event"] != "response.output_item.added":
                continue
            item: dict[str, Any] = e["data"].get("item") or {}
            if item.get("type") == "mcp_approval_request":
                approval_request_id = item.get("id")
                break
        assert approval_request_id is not None

        loaded = await server._function_approval_storage_provider.get_store(  # pyright: ignore[reportPrivateUsage]
            config=server.config, platform_context=get_request_context()
        ).load_approval_request(approval_request_id)
        assert loaded.type == "function_approval_request"
        assert mock_agent.run_count == 1

    async def test_round_trip_approval_response_resumes_workflow_agent(self) -> None:
        """Two-turn HTTP round-trip:

        Turn 1 emits ``mcp_approval_request`` and writes a workflow
        checkpoint under the response id. Turn 2 sends the
        ``mcp_approval_response`` with ``previous_response_id`` set, so the
        host restores the checkpoint, the WorkflowAgent routes the
        approval response back to the paused inner agent, and the inner
        agent emits the final assistant text.
        """
        workflow_agent, mock_agent = _build_approval_workflow_agent(
            approval_request_id="apr_wf_rt",
            final_text="done with approval",
        )
        server = _make_server(workflow_agent)
        checkpoint_provider = server._checkpoint_storage_provider  # pyright: ignore[reportPrivateUsage]

        with patch.object(checkpoint_provider, "get_store", wraps=checkpoint_provider.get_store) as get_store:
            first = await _post(server, stream=False)
            assert first.status_code == 200
            first_body = first.json()
            first_response_id = first_body["id"]
            approval_items = [it for it in first_body["output"] if it["type"] == "mcp_approval_request"]
            assert len(approval_items) == 1
            approval_request_id = approval_items[0]["id"]
            assert mock_agent.run_count == 1

            second_payload: dict[str, Any] = {
                "model": "test-model",
                "input": [
                    {
                        "type": "mcp_approval_response",
                        "approval_request_id": approval_request_id,
                        "approve": True,
                    }
                ],
                "stream": False,
                "previous_response_id": first_response_id,
            }
            second = await _post_json(server, second_payload)
        assert second.status_code == 200
        second_body = second.json()
        assert second_body["status"] == "completed"
        assert [call.kwargs["context_id"] for call in get_store.call_args_list] == [
            first_response_id,
            second_body["id"],
            first_response_id,
        ]

        # The inner agent must have been resumed (restore replay + new turn).
        # Restore call is a no-op for the mock (no input); the new-turn call
        # delivers the approval response, so run_count grows by at least 1.
        assert mock_agent.run_count >= 2

        # The final assistant text from the resumed inner agent surfaces in
        # the HTTP output.
        text_pieces = [
            part.get("text", "")
            for item in second_body["output"]
            if item["type"] == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        ]
        assert any("done with approval" in t for t in text_pieces), (
            f"expected resumed workflow output, got {second_body['output']}"
        )

        # The new-turn invocation of the inner agent must have received the
        # approval response routed back through WorkflowAgent.
        approval_responses = [
            c for m in mock_agent.last_run_messages for c in m.contents if c.type == "function_approval_response"
        ]
        assert len(approval_responses) == 1
        assert approval_responses[0].approved is True

    async def test_round_trip_approval_response_streaming(self) -> None:
        """Streaming variant of the round-trip: turn 2 is requested with
        ``stream=true`` and surfaces the resumed text as SSE events."""
        workflow_agent, mock_agent = _build_approval_workflow_agent(
            approval_request_id="apr_wf_rt_st",
            final_text="streamed-done",
        )
        server = _make_server(workflow_agent)

        first = await _post(server, stream=False)
        first_body = first.json()
        first_response_id = first_body["id"]
        approval_request_id = next(it["id"] for it in first_body["output"] if it["type"] == "mcp_approval_request")

        second = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "mcp_approval_response",
                        "approval_request_id": approval_request_id,
                        "approve": True,
                    }
                ],
                "stream": True,
                "previous_response_id": first_response_id,
            },
        )
        assert second.status_code == 200
        events = _parse_sse_events(second.text)
        types = _sse_event_types(events)
        assert types[0] == "response.created"
        assert types[-1] == "response.completed"

        text_done = [e for e in events if e["event"] == "response.output_text.done"]
        assert any("streamed-done" in e["data"]["text"] for e in text_done)
        assert mock_agent.run_count >= 2

    async def test_round_trip_approval_response_rejected(self) -> None:
        """Sending ``approve=False`` must surface as ``approved=False`` to the
        inner agent on resume."""
        workflow_agent, mock_agent = _build_approval_workflow_agent(
            approval_request_id="apr_wf_reject",
            final_text="acknowledged",
        )
        server = _make_server(workflow_agent)

        first = await _post(server, stream=False)
        first_body = first.json()
        first_response_id = first_body["id"]
        approval_request_id = next(it["id"] for it in first_body["output"] if it["type"] == "mcp_approval_request")

        second = await _post_json(
            server,
            {
                "model": "test-model",
                "input": [
                    {
                        "type": "mcp_approval_response",
                        "approval_request_id": approval_request_id,
                        "approve": False,
                    }
                ],
                "stream": False,
                "previous_response_id": first_response_id,
            },
        )
        assert second.status_code == 200

        approval_responses = [
            c for m in mock_agent.last_run_messages for c in m.contents if c.type == "function_approval_response"
        ]
        assert len(approval_responses) == 1
        assert approval_responses[0].approved is False


# endregion
