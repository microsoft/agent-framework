# Copyright (c) Microsoft. All rights reserved.

"""HTTP round-trip tests for ResponsesHostServer.

These tests exercise the full HTTP pipeline using httpx.AsyncClient with
ASGITransport — no real server process is started. Requests go through
the Starlette routing stack, the Responses API middleware, and arrive at
the registered _handle_create handler.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    Content,
    HistoryProvider,
    Message,
    RawAgent,
    ResponseStream,
)
from azure.ai.agentserver.responses import InMemoryResponseProvider
from typing_extensions import Any

from agent_framework_foundry_hosting import ResponsesHostServer

# region Helpers


def _make_agent(
    *,
    response: AgentResponse | None = None,
    stream_updates: list[AgentResponseUpdate] | None = None,
) -> MagicMock:
    """Create a mock agent implementing SupportsAgentRun."""
    agent = MagicMock(spec=RawAgent)
    agent.id = "test-agent"
    agent.name = "Test Agent"
    agent.description = "A mock agent for testing"
    agent.context_providers = []

    if response is not None:

        async def run_non_streaming(*args: Any, **kwargs: Any) -> AgentResponse:
            return response

        agent.run = AsyncMock(side_effect=run_non_streaming)

    if stream_updates is not None:

        async def _stream_gen() -> AsyncIterator[AgentResponseUpdate]:
            for update in stream_updates:
                yield update

        def run_streaming(*args: Any, **kwargs: Any) -> Any:
            if kwargs.get("stream"):
                return ResponseStream(_stream_gen())  # type: ignore
            raise NotImplementedError("Only streaming is configured on this mock")

        agent.run = MagicMock(side_effect=run_streaming)

    return agent


def _make_server(agent: MagicMock, **kwargs: Any) -> ResponsesHostServer:
    """Create a ResponsesHostServer with an in-memory store."""
    return ResponsesHostServer(agent, store=InMemoryResponseProvider(), **kwargs)


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

    def test_init_rejects_history_provider_with_load_messages(self) -> None:
        hp = HistoryProvider(source_id="test", load_messages=True)
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("hi")])])
        )
        agent.context_providers = [hp]
        with pytest.raises(RuntimeError, match="history provider"):
            ResponsesHostServer(agent)


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

    async def test_reasoning_content(self) -> None:
        agent = _make_agent(
            response=AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_text_reasoning(text="Let me think..."),
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

    async def test_empty_response(self) -> None:
        agent = _make_agent(response=AgentResponse(messages=[]))
        server = _make_server(agent)
        resp = await _post(server, stream=False)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

    async def test_chat_options_forwarded(self) -> None:
        agent = _make_agent(
            response=AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("ok")])])
        )
        server = _make_server(agent)
        resp = await _post(server, stream=False, temperature=0.5, top_p=0.9, max_output_tokens=1024)

        assert resp.status_code == 200
        agent.run.assert_awaited_once()
        call_kwargs = agent.run.call_args.kwargs
        assert call_kwargs["stream"] is False
        options = call_kwargs["options"]
        assert options["temperature"] == 0.5
        assert options["top_p"] == 0.9
        assert options["max_tokens"] == 1024


# endregion


# region Streaming


class TestStreaming:
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
        agent = _make_agent(
            stream_updates=[
                # Reasoning deltas
                AgentResponseUpdate(contents=[Content.from_text_reasoning(text="Let me ")], role="assistant"),
                AgentResponseUpdate(contents=[Content.from_text_reasoning(text="think...")], role="assistant"),
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


# endregion
