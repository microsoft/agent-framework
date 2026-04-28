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
from agent_framework_foundry_hosting._responses import (
    _item_to_message,  # pyright: ignore[reportPrivateUsage]
    _output_item_to_message,  # pyright: ignore[reportPrivateUsage]
)

# region Helpers


def _make_agent(
    *,
    response: AgentResponse | None = None,
    stream_updates: list[AgentResponseUpdate] | None = None,
    raw_agent: bool = True,
) -> MagicMock:
    """Create a mock agent implementing SupportsAgentRun."""
    agent = MagicMock(spec=RawAgent) if raw_agent else MagicMock()
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
            parallel_tool_calls=True,
        )

        assert resp.status_code == 200
        agent.run.assert_awaited_once()
        call_kwargs = agent.run.call_args.kwargs
        assert call_kwargs["stream"] is False
        options = call_kwargs["options"]
        assert options["temperature"] == 0.5
        assert options["top_p"] == 0.9
        assert options["max_tokens"] == 1024
        assert options["allow_multiple_tool_calls"] is True


# endregion


# region Streaming


class TestStreaming:
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


# region _output_item_to_message conversion


class TestOutputItemToMessage:
    """Tests for _output_item_to_message covering all supported OutputItem types."""

    def test_output_message(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemOutputMessage, OutputMessageContentOutputTextContent

        item = OutputItemOutputMessage({
            "type": "output_message",
            "role": "assistant",
            "content": [OutputMessageContentOutputTextContent({"type": "output_text", "text": "hello"})],
            "status": "completed",
            "id": "msg-1",
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert len(msg.contents) == 1
        assert msg.contents[0].type == "text"
        assert msg.contents[0].text == "hello"

    def test_message(self) -> None:
        from azure.ai.agentserver.responses.models import MessageContentInputTextContent, OutputItemMessage

        item = OutputItemMessage({
            "type": "message",
            "role": "user",
            "content": [MessageContentInputTextContent({"type": "input_text", "text": "hi"})],
        })
        msg = _output_item_to_message(item)
        assert msg.role == "user"
        assert len(msg.contents) == 1
        assert msg.contents[0].text == "hi"

    def test_function_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemFunctionToolCall

        item = OutputItemFunctionToolCall({
            "type": "function_call",
            "call_id": "call_1",
            "name": "get_weather",
            "arguments": '{"city": "NYC"}',
            "status": "completed",
            "id": "fc-1",
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].call_id == "call_1"
        assert msg.contents[0].name == "get_weather"

    def test_function_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import FunctionCallOutputItemParam

        item = FunctionCallOutputItemParam({"type": "function_call_output", "call_id": "call_1", "output": "sunny"})
        msg = _output_item_to_message(item)  # type: ignore[arg-type]
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].call_id == "call_1"
        assert msg.contents[0].result == "sunny"

    def test_reasoning(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemReasoningItem, SummaryTextContent

        item = OutputItemReasoningItem({
            "type": "reasoning",
            "id": "r-1",
            "summary": [SummaryTextContent({"type": "summary_text", "text": "thinking hard"})],
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert len(msg.contents) == 1
        assert msg.contents[0].text == "thinking hard"

    def test_reasoning_no_summary(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemReasoningItem

        item = OutputItemReasoningItem({"type": "reasoning", "id": "r-2"})
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents == []

    def test_mcp_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpToolCall

        item = OutputItemMcpToolCall({
            "type": "mcp_call",
            "id": "mcp-1",
            "server_label": "my_server",
            "name": "search",
            "arguments": '{"q": "test"}',
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "mcp_server_tool_call"
        assert msg.contents[0].server_name == "my_server"
        assert msg.contents[0].tool_name == "search"

    def test_mcp_approval_request(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpApprovalRequest

        item = OutputItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "apr-1",
            "server_label": "srv",
            "name": "dangerous_tool",
            "arguments": "{}",
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_approval_request"

    def test_mcp_approval_response(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemMcpApprovalResponseResource

        item = OutputItemMcpApprovalResponseResource({
            "type": "mcp_approval_response",
            "id": "resp-1",
            "approval_request_id": "apr-1",
            "approve": True,
        })
        msg = _output_item_to_message(item)
        assert msg.role == "user"
        assert msg.contents[0].type == "function_approval_response"
        assert msg.contents[0].approved is True

    def test_code_interpreter_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemCodeInterpreterToolCall

        item = OutputItemCodeInterpreterToolCall({
            "type": "code_interpreter_call",
            "id": "ci-1",
            "status": "completed",
            "container_id": "c-1",
            "code": "print('hi')",
            "outputs": [],
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "code_interpreter_tool_call"

    def test_image_generation_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemImageGenToolCall

        item = OutputItemImageGenToolCall({"type": "image_generation_call", "id": "ig-1", "status": "completed"})
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "image_generation_tool_call"

    def test_shell_call(self) -> None:
        from azure.ai.agentserver.responses.models import (
            FunctionShellAction,
            FunctionShellCallEnvironment,
            OutputItemFunctionShellCall,
        )

        item = OutputItemFunctionShellCall({
            "type": "shell_call",
            "id": "sc-1",
            "call_id": "call_sc",
            "action": FunctionShellAction({"commands": ["ls", "-la"], "timeout_ms": 5000, "max_output_length": 1024}),
            "status": "completed",
            "environment": FunctionShellCallEnvironment({"type": "local"}),
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "shell_tool_call"
        assert msg.contents[0].commands == ["ls", "-la"]
        assert msg.contents[0].call_id == "call_sc"

    def test_shell_call_output(self) -> None:
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
                    "outcome": FunctionShellCallOutputExitOutcome({"exit_code": 0}),
                })
            ],
            "max_output_length": 1024,
        })
        msg = _output_item_to_message(item)
        assert msg.role == "tool"
        assert msg.contents[0].type == "shell_tool_result"
        assert msg.contents[0].call_id == "call_sc"

    def test_local_shell_call(self) -> None:
        from azure.ai.agentserver.responses.models import LocalShellExecAction, OutputItemLocalShellToolCall

        item = OutputItemLocalShellToolCall({
            "type": "local_shell_call",
            "id": "lsc-1",
            "call_id": "call_lsc",
            "action": LocalShellExecAction({"type": "exec", "command": ["echo", "hello"], "env": {}}),
            "status": "completed",
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "shell_tool_call"
        assert msg.contents[0].commands == ["echo", "hello"]

    def test_local_shell_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemLocalShellToolCallOutput

        item = OutputItemLocalShellToolCallOutput({
            "type": "local_shell_call_output",
            "id": "lsco-1",
            "output": "hello\n",
        })
        msg = _output_item_to_message(item)
        assert msg.role == "tool"
        assert msg.contents[0].type == "shell_tool_result"

    def test_file_search_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemFileSearchToolCall

        item = OutputItemFileSearchToolCall({
            "type": "file_search_call",
            "id": "fs-1",
            "status": "completed",
            "queries": ["what is AI"],
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "file_search"
        assert '"what is AI"' in (msg.contents[0].arguments or "")

    def test_web_search_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemWebSearchToolCall, WebSearchActionSearch

        item = OutputItemWebSearchToolCall({
            "type": "web_search_call",
            "id": "ws-1",
            "status": "completed",
            "action": WebSearchActionSearch({"type": "search", "query": "test"}),
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "web_search"

    def test_computer_call(self) -> None:
        from azure.ai.agentserver.responses.models import ComputerAction, OutputItemComputerToolCall

        item = OutputItemComputerToolCall({
            "type": "computer_call",
            "id": "cc-1",
            "call_id": "call_cc",
            "action": ComputerAction({"type": "click"}),
            "pending_safety_checks": [],
            "status": "completed",
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "computer_use"

    def test_computer_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import (
            ComputerScreenshotImage,
            OutputItemComputerToolCallOutputResource,
        )

        item = OutputItemComputerToolCallOutputResource({
            "type": "computer_call_output",
            "call_id": "call_cc",
            "output": ComputerScreenshotImage({
                "type": "computer_screenshot",
                "image_url": "data:image/png;base64,abc",
            }),
        })
        msg = _output_item_to_message(item)
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].call_id == "call_cc"

    def test_custom_tool_call(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemCustomToolCall

        item = OutputItemCustomToolCall({
            "type": "custom_tool_call",
            "call_id": "call_ct",
            "name": "my_tool",
            "input": '{"key": "value"}',
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "my_tool"
        assert msg.contents[0].arguments == '{"key": "value"}'

    def test_custom_tool_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemCustomToolCallOutput

        item = OutputItemCustomToolCallOutput({
            "type": "custom_tool_call_output",
            "call_id": "call_ct",
            "output": "result text",
        })
        msg = _output_item_to_message(item)
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].result == "result text"

    def test_apply_patch_call(self) -> None:
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
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "apply_patch"

    def test_apply_patch_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItemApplyPatchToolCallOutput

        item = OutputItemApplyPatchToolCallOutput({
            "type": "apply_patch_call_output",
            "id": "apo-1",
            "call_id": "call_ap",
            "status": "completed",
            "output": "patch applied",
        })
        msg = _output_item_to_message(item)
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].result == "patch applied"

    def test_oauth_consent_request(self) -> None:
        from azure.ai.agentserver.responses.models import OAuthConsentRequestOutputItem

        item = OAuthConsentRequestOutputItem({
            "type": "oauth_consent_request",
            "id": "oauth-1",
            "consent_link": "https://example.com/consent",
            "server_label": "my_server",
        })
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "oauth_consent_request"
        assert msg.contents[0].consent_link == "https://example.com/consent"

    def test_structured_outputs_dict(self) -> None:
        from azure.ai.agentserver.responses.models import StructuredOutputsOutputItem

        item = StructuredOutputsOutputItem({"type": "structured_outputs", "id": "so-1", "output": {"answer": 42}})
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].type == "text"
        assert json.loads(msg.contents[0].text or "") == {"answer": 42}

    def test_structured_outputs_string(self) -> None:
        from azure.ai.agentserver.responses.models import StructuredOutputsOutputItem

        item = StructuredOutputsOutputItem({"type": "structured_outputs", "id": "so-2", "output": "plain text"})
        msg = _output_item_to_message(item)
        assert msg.role == "assistant"
        assert msg.contents[0].text == "plain text"

    def test_unsupported_type_raises(self) -> None:
        from azure.ai.agentserver.responses.models import OutputItem

        item = OutputItem({"type": "some_unknown_type"})
        with pytest.raises(ValueError, match="Unsupported OutputItem type: some_unknown_type"):
            _output_item_to_message(item)


# endregion


# region _item_to_message conversion


class TestItemToMessage:
    """Tests for _item_to_message covering all supported Item types."""

    def test_message_with_string_content(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMessage

        item = ItemMessage({"type": "message", "role": "user", "content": "hello"})
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "user"
        assert len(msg.contents) == 1
        assert msg.contents[0].type == "text"
        assert msg.contents[0].text == "hello"

    def test_message_with_input_text_content(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMessage, MessageContentInputTextContent

        item = ItemMessage({
            "type": "message",
            "role": "user",
            "content": [MessageContentInputTextContent({"type": "input_text", "text": "hi there"})],
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "user"
        assert len(msg.contents) == 1
        assert msg.contents[0].text == "hi there"

    def test_message_with_multiple_contents(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMessage, MessageContentInputTextContent

        item = ItemMessage({
            "type": "message",
            "role": "user",
            "content": [
                MessageContentInputTextContent({"type": "input_text", "text": "first"}),
                MessageContentInputTextContent({"type": "input_text", "text": "second"}),
            ],
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert len(msg.contents) == 2
        assert msg.contents[0].text == "first"
        assert msg.contents[1].text == "second"

    def test_output_message(self) -> None:
        from azure.ai.agentserver.responses.models import ItemOutputMessage, OutputMessageContentOutputTextContent

        item = ItemOutputMessage({
            "type": "output_message",
            "role": "assistant",
            "content": [OutputMessageContentOutputTextContent({"type": "output_text", "text": "response"})],
            "status": "completed",
            "id": "msg-1",
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert len(msg.contents) == 1
        assert msg.contents[0].type == "text"
        assert msg.contents[0].text == "response"

    def test_function_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemFunctionToolCall

        item = ItemFunctionToolCall({
            "type": "function_call",
            "call_id": "call_1",
            "name": "get_weather",
            "arguments": '{"city": "NYC"}',
            "status": "completed",
            "id": "fc-1",
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].call_id == "call_1"
        assert msg.contents[0].name == "get_weather"
        assert msg.contents[0].arguments == '{"city": "NYC"}'

    def test_function_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import FunctionCallOutputItemParam

        item = FunctionCallOutputItemParam({"type": "function_call_output", "call_id": "call_1", "output": "sunny"})
        msg = _item_to_message(item)  # type: ignore[arg-type]
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].call_id == "call_1"
        assert msg.contents[0].result == "sunny"

    def test_function_call_output_non_string(self) -> None:
        from azure.ai.agentserver.responses.models import FunctionCallOutputItemParam

        item = FunctionCallOutputItemParam({"type": "function_call_output", "call_id": "call_2", "output": 42})
        msg = _item_to_message(item)  # type: ignore[arg-type]
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].result == "42"

    def test_reasoning_with_summary(self) -> None:
        from azure.ai.agentserver.responses.models import ItemReasoningItem, SummaryTextContent

        item = ItemReasoningItem({
            "type": "reasoning",
            "id": "r-1",
            "summary": [SummaryTextContent({"type": "summary_text", "text": "thinking hard"})],
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert len(msg.contents) == 1
        assert msg.contents[0].text == "thinking hard"

    def test_reasoning_no_summary(self) -> None:
        from azure.ai.agentserver.responses.models import ItemReasoningItem

        item = ItemReasoningItem({"type": "reasoning", "id": "r-2"})
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents == []

    def test_mcp_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMcpToolCall

        item = ItemMcpToolCall({
            "type": "mcp_call",
            "id": "mcp-1",
            "server_label": "my_server",
            "name": "search",
            "arguments": '{"q": "test"}',
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "mcp_server_tool_call"
        assert msg.contents[0].server_name == "my_server"
        assert msg.contents[0].tool_name == "search"

    def test_mcp_approval_request(self) -> None:
        from azure.ai.agentserver.responses.models import ItemMcpApprovalRequest

        item = ItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "apr-1",
            "server_label": "srv",
            "name": "dangerous_tool",
            "arguments": "{}",
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_approval_request"

    def test_mcp_approval_response(self) -> None:
        from azure.ai.agentserver.responses.models import MCPApprovalResponse

        item = MCPApprovalResponse({
            "type": "mcp_approval_response",
            "approval_request_id": "apr-1",
            "approve": True,
        })
        msg = _item_to_message(item)  # type: ignore[arg-type]
        assert msg is not None
        assert msg.role == "user"
        assert msg.contents[0].type == "function_approval_response"
        assert msg.contents[0].approved is True

    def test_code_interpreter_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemCodeInterpreterToolCall

        item = ItemCodeInterpreterToolCall({
            "type": "code_interpreter_call",
            "id": "ci-1",
            "status": "completed",
            "container_id": "c-1",
            "code": "print('hi')",
            "outputs": [],
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "code_interpreter_tool_call"

    def test_image_generation_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemImageGenToolCall

        item = ItemImageGenToolCall({"type": "image_generation_call", "id": "ig-1", "status": "completed"})
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "image_generation_tool_call"

    def test_shell_call(self) -> None:
        from azure.ai.agentserver.responses.models import FunctionShellAction, FunctionShellCallItemParam

        item = FunctionShellCallItemParam({
            "type": "shell_call",
            "call_id": "call_sc",
            "action": FunctionShellAction({"commands": ["ls", "-la"], "timeout_ms": 5000, "max_output_length": 1024}),
            "status": "in_progress",
        })
        msg = _item_to_message(item)  # type: ignore[arg-type]
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "shell_tool_call"
        assert msg.contents[0].commands == ["ls", "-la"]
        assert msg.contents[0].call_id == "call_sc"

    def test_shell_call_output(self) -> None:
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
                    "outcome": FunctionShellCallOutputExitOutcome({"exit_code": 0}),
                })
            ],
            "max_output_length": 1024,
        })
        msg = _item_to_message(item)  # type: ignore[arg-type]
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "shell_tool_result"
        assert msg.contents[0].call_id == "call_sc"

    def test_local_shell_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemLocalShellToolCall, LocalShellExecAction

        item = ItemLocalShellToolCall({
            "type": "local_shell_call",
            "id": "lsc-1",
            "call_id": "call_lsc",
            "action": LocalShellExecAction({"type": "exec", "command": ["echo", "hello"], "env": {}}),
            "status": "completed",
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "shell_tool_call"
        assert msg.contents[0].commands == ["echo", "hello"]

    def test_local_shell_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import ItemLocalShellToolCallOutput

        item = ItemLocalShellToolCallOutput({
            "type": "local_shell_call_output",
            "id": "lsco-1",
            "output": "hello\n",
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "shell_tool_result"

    def test_file_search_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemFileSearchToolCall

        item = ItemFileSearchToolCall({
            "type": "file_search_call",
            "id": "fs-1",
            "status": "completed",
            "queries": ["what is AI"],
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "file_search"
        assert '"what is AI"' in (msg.contents[0].arguments or "")

    def test_web_search_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemWebSearchToolCall

        item = ItemWebSearchToolCall({
            "type": "web_search_call",
            "id": "ws-1",
            "status": "completed",
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "web_search"

    def test_computer_call(self) -> None:
        from azure.ai.agentserver.responses.models import ComputerAction, ItemComputerToolCall

        item = ItemComputerToolCall({
            "type": "computer_call",
            "id": "cc-1",
            "call_id": "call_cc",
            "action": ComputerAction({"type": "click"}),
            "pending_safety_checks": [],
            "status": "completed",
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "computer_use"

    def test_computer_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import ComputerCallOutputItemParam, ComputerScreenshotImage

        item = ComputerCallOutputItemParam({
            "type": "computer_call_output",
            "call_id": "call_cc",
            "output": ComputerScreenshotImage({
                "type": "computer_screenshot",
                "image_url": "data:image/png;base64,abc",
            }),
        })
        msg = _item_to_message(item)  # type: ignore[arg-type]
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].call_id == "call_cc"

    def test_custom_tool_call(self) -> None:
        from azure.ai.agentserver.responses.models import ItemCustomToolCall

        item = ItemCustomToolCall({
            "type": "custom_tool_call",
            "call_id": "call_ct",
            "name": "my_tool",
            "input": '{"key": "value"}',
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "my_tool"
        assert msg.contents[0].arguments == '{"key": "value"}'

    def test_custom_tool_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import ItemCustomToolCallOutput

        item = ItemCustomToolCallOutput({
            "type": "custom_tool_call_output",
            "call_id": "call_ct",
            "output": "result text",
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].result == "result text"

    def test_custom_tool_call_output_non_string(self) -> None:
        from azure.ai.agentserver.responses.models import ItemCustomToolCallOutput

        item = ItemCustomToolCallOutput({
            "type": "custom_tool_call_output",
            "call_id": "call_ct2",
            "output": 123,
        })
        msg = _item_to_message(item)
        assert msg is not None
        assert msg.contents[0].result == "123"

    def test_apply_patch_call(self) -> None:
        from azure.ai.agentserver.responses.models import ApplyPatchToolCallItemParam, ApplyPatchUpdateFileOperation

        item = ApplyPatchToolCallItemParam({
            "type": "apply_patch_call",
            "call_id": "call_ap",
            "operation": ApplyPatchUpdateFileOperation({
                "type": "update_file",
                "path": "file.py",
                "diff": "+ new line",
            }),
        })
        msg = _item_to_message(item)  # type: ignore[arg-type]
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.contents[0].type == "function_call"
        assert msg.contents[0].name == "apply_patch"

    def test_apply_patch_call_output(self) -> None:
        from azure.ai.agentserver.responses.models import ApplyPatchToolCallOutputItemParam

        item = ApplyPatchToolCallOutputItemParam({
            "type": "apply_patch_call_output",
            "call_id": "call_ap",
            "output": "patch applied",
        })
        msg = _item_to_message(item)  # type: ignore[arg-type]
        assert msg is not None
        assert msg.role == "tool"
        assert msg.contents[0].type == "function_result"
        assert msg.contents[0].result == "patch applied"

    def test_unsupported_type_raises(self) -> None:
        from azure.ai.agentserver.responses.models import Item

        item = Item({"type": "some_unknown_type"})
        with pytest.raises(ValueError, match="Unsupported Item type: some_unknown_type"):
            _item_to_message(item)


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

    call_index = [0]

    async def run_non_streaming(*args: Any, **kwargs: Any) -> AgentResponse:
        idx = call_index[0]
        call_index[0] += 1
        return responses[idx]

    async def _stream_gen(updates: list[AgentResponseUpdate]) -> AsyncIterator[AgentResponseUpdate]:
        for update in updates:
            yield update

    def run_dispatch(*args: Any, **kwargs: Any) -> Any:
        idx = call_index[0]
        call_index[0] += 1
        if kwargs.get("stream") and stream_updates_list is not None:
            return ResponseStream(_stream_gen(stream_updates_list[idx]))  # type: ignore
        if not kwargs.get("stream"):
            # Need to return a coroutine for non-streaming
            async def _ret() -> AgentResponse:
                return responses[idx]

            return _ret()
        raise NotImplementedError("Streaming not configured for this call index")

    if stream_updates_list is not None:
        agent.run = MagicMock(side_effect=run_dispatch)
    else:
        agent.run = AsyncMock(side_effect=run_non_streaming)

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
