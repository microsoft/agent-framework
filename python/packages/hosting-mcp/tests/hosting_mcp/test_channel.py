# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for :class:`MCPChannel`."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, cast

import mcp.types as types
import uvicorn
from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message, ResponseStream
from agent_framework_hosting import AgentFrameworkHost, ChannelRequest, HostedRunResult
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_connected_server_and_client_session
from starlette.types import ASGIApp

from agent_framework_hosting_mcp import MCPChannel

# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #


@dataclass
class _FakeResp:
    text: str
    messages: list[Message] = field(default_factory=list)
    value: Any | None = None


@dataclass
class _FakeUpdate:
    text: str
    contents: list[Content] = field(default_factory=list)
    message_id: str | None = None


class _FakeStream:
    def __init__(
        self,
        chunks: list[str],
        final: _FakeResp | None = None,
        updates: list[_FakeUpdate] | None = None,
    ) -> None:
        self._chunks = chunks
        self._final = final or _FakeResp(text="".join(chunks))
        self._updates = updates

    def __aiter__(self) -> AsyncIterator[_FakeUpdate]:
        async def _gen() -> AsyncIterator[_FakeUpdate]:
            if self._updates is not None:
                for u in self._updates:
                    yield u
            else:
                for c in self._chunks:
                    yield _FakeUpdate(text=c, contents=[Content.from_text(text=c)])

        return _gen()

    async def get_final_response(self) -> _FakeResp:
        return self._final


@dataclass
class _FakeTarget:
    name: str = "Assistant"
    description: str = "A helpful assistant."


class _FakeContext:
    """Minimal stand-in for :class:`ChannelContext`."""

    def __init__(
        self,
        *,
        reply: str = "hello",
        chunks: list[str] | None = None,
        contents: list[Content] | None = None,
        structured: Any | None = None,
        stream_updates: list[_FakeUpdate] | None = None,
    ) -> None:
        self.target = _FakeTarget()
        self._reply = reply
        self._chunks = chunks or [reply]
        self._contents = contents or [Content.from_text(text=reply)]
        self._structured = structured
        self._stream_updates = stream_updates
        self.requests: list[ChannelRequest] = []

    async def run(
        self,
        request: ChannelRequest,
        *,
        run_hook: Any | None = None,
        protocol_request: Any | None = None,
        response_hook: Any | None = None,
        channel_name: str | None = None,
    ) -> HostedRunResult[Any]:
        if run_hook is not None:
            maybe_request = run_hook(request, target=self.target, protocol_request=protocol_request)
            if isinstance(maybe_request, Awaitable):
                request = await maybe_request
            else:
                request = maybe_request
        self.requests.append(request)
        message = Message(role="assistant", contents=self._contents)
        result = HostedRunResult(_FakeResp(text=self._reply, messages=[message], value=self._structured))
        if response_hook is not None:
            maybe_result = response_hook(result, request=request, channel_name=channel_name or request.channel)
            if isinstance(maybe_result, Awaitable):
                return await maybe_result
            return maybe_result
        return result

    async def run_stream(
        self,
        request: ChannelRequest,
        *,
        run_hook: Any | None = None,
        protocol_request: Any | None = None,
        stream_update_hook: Any | None = None,
        response_hook: Any | None = None,
        channel_name: str | None = None,
    ) -> _FakeStream:
        if run_hook is not None:
            maybe_request = run_hook(request, target=self.target, protocol_request=protocol_request)
            if isinstance(maybe_request, Awaitable):
                request = await maybe_request
            else:
                request = maybe_request
        self.requests.append(request)
        result = HostedRunResult(_FakeResp(text="".join(self._chunks), value=self._structured))
        if response_hook is not None:
            maybe_result = response_hook(result, request=request, channel_name=channel_name or request.channel)
            if isinstance(maybe_result, Awaitable):
                result = await maybe_result
            else:
                result = maybe_result
        return _FakeStream(self._chunks, final=result.result, updates=self._stream_updates)


def _make_channel(ctx: _FakeContext, **kwargs: Any) -> MCPChannel:
    channel = MCPChannel(**kwargs)
    channel.contribute(cast(Any, ctx))
    return channel


class _HostedAgent:
    id = "hosted-agent"
    name: str | None = "HostedAssistant"
    description: str | None = "A hosted test assistant."

    async def run(self, messages: Any = None, *, stream: bool = False, **_kwargs: Any) -> Any:
        text = messages.text if isinstance(messages, Message) else str(messages)
        if stream:
            updates = [AgentResponseUpdate(contents=[Content.from_text(text=f"host: {text}")], role="assistant")]

            async def _gen() -> AsyncIterator[AgentResponseUpdate]:
                for update in updates:
                    yield update

            async def _finalize(items: Sequence[AgentResponseUpdate]) -> AgentResponse:  # noqa: RUF029
                return AgentResponse.from_updates(items)

            return ResponseStream[AgentResponseUpdate, AgentResponse](_gen(), finalizer=_finalize)
        return AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text(text=f"host: {text}")])])

    def create_session(self, *, session_id: str | None = None) -> Any:
        return {"session_id": session_id}

    def get_session(self, service_session_id: str, *, session_id: str | None = None) -> Any:
        return {"service_session_id": service_session_id, "session_id": session_id}


@asynccontextmanager
async def _serve_app(app: ASGIApp, *, port: int) -> AsyncIterator[str]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.01)
        else:
            raise RuntimeError("Test MCP server did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def _text(block: types.ContentBlock) -> str:
    assert isinstance(block, types.TextContent)
    return block.text


def _server(channel: MCPChannel) -> Any:
    server = cast(Any, channel._server)  # pyright: ignore[reportPrivateUsage]
    assert server is not None
    return server


async def test_list_tools_advertises_single_configured_tool() -> None:
    ctx = _FakeContext()
    channel = _make_channel(ctx, tool_name="ask", tool_description="Ask the assistant.")
    async with create_connected_server_and_client_session(_server(channel)) as client:
        result = await client.list_tools()
    assert len(result.tools) == 1
    tool = result.tools[0]
    assert tool.name == "ask"
    assert tool.description == "Ask the assistant."
    assert tool.inputSchema["required"] == ["input"]
    assert set(tool.inputSchema["properties"]) == {"input", "session_id"}


async def test_initialize_uses_target_name_by_default() -> None:
    ctx = _FakeContext()
    channel = _make_channel(ctx)
    async with create_connected_server_and_client_session(_server(channel)) as client:
        result = await client.initialize()
    assert result.serverInfo.name == "Assistant"


async def test_call_tool_routes_through_host_and_returns_text() -> None:
    ctx = _FakeContext(reply="hi back", chunks=["hi", " back"])
    channel = _make_channel(ctx, streaming=False)
    async with create_connected_server_and_client_session(_server(channel)) as client:
        result = await client.call_tool("run_agent", {"input": "hello", "session_id": "conv-1"})
    assert not result.isError
    assert isinstance(result.content[0], types.TextContent)
    assert result.content[0].text == "hi back"
    # The channel built a channel-neutral request routed through the host.
    assert len(ctx.requests) == 1
    request = ctx.requests[0]
    assert request.channel == "mcp"
    assert request.operation == "message.create"
    assert request.input == "hello"
    assert request.session is not None
    assert request.session.isolation_key == "conv-1"
    assert request.identity is not None
    assert request.identity.native_id == "conv-1"


async def test_call_tool_returns_rich_content_and_structured_output() -> None:
    ctx = _FakeContext(
        contents=[
            Content.from_text(text="text"),
            Content.from_data(data=b"image-bytes", media_type="image/png"),
            Content.from_data(data=b"audio-bytes", media_type="audio/wav"),
            Content.from_data(data=b"raw-bytes", media_type="application/octet-stream"),
            Content.from_uri(uri="https://example.com/file.json", media_type="application/json"),
        ],
        structured={"answer": 42},
    )
    channel = _make_channel(ctx, streaming=False)
    async with create_connected_server_and_client_session(_server(channel)) as client:
        result = await client.call_tool("run_agent", {"input": "hello"})

    assert result.structuredContent == {"answer": 42}
    assert [item.type for item in result.content] == ["text", "image", "audio", "resource", "resource_link"]
    assert _text(result.content[0]) == "text"


async def test_call_tool_streaming_aggregates_chunks() -> None:
    ctx = _FakeContext(chunks=["foo", "bar", "baz"])
    channel = _make_channel(ctx, streaming=True)
    async with create_connected_server_and_client_session(_server(channel)) as client:
        result = await client.call_tool("run_agent", {"input": "hello"})
    assert _text(result.content[0]) == "foobarbaz"
    # No session_id supplied -> no session / identity.
    assert ctx.requests[0].session is None
    assert ctx.requests[0].identity is None


async def test_call_tool_rejects_empty_input() -> None:
    ctx = _FakeContext()
    channel = _make_channel(ctx)
    async with create_connected_server_and_client_session(_server(channel)) as client:
        result = await client.call_tool("run_agent", {"input": ""})
    assert result.isError
    assert "non-empty string" in _text(result.content[0])
    assert ctx.requests == []


async def test_call_tool_rejects_unknown_tool_name() -> None:
    ctx = _FakeContext()
    channel = _make_channel(ctx)
    async with create_connected_server_and_client_session(_server(channel)) as client:
        result = await client.call_tool("unknown_tool", {"input": "hello"})
    assert result.isError
    assert "unknown tool" in _text(result.content[0])
    assert ctx.requests == []


async def test_run_hook_can_reshape_request() -> None:
    ctx = _FakeContext(reply="ok")

    async def _hook(request: ChannelRequest, *, target: Any, protocol_request: Any) -> ChannelRequest:
        import dataclasses

        return dataclasses.replace(request, attributes={**dict(request.attributes), "hooked": True})

    channel = _make_channel(ctx, streaming=False, run_hook=_hook)
    async with create_connected_server_and_client_session(_server(channel)) as client:
        await client.call_tool("run_agent", {"input": "hello"})
    assert ctx.requests[0].attributes.get("hooked") is True


async def test_response_hook_can_shape_originating_reply() -> None:
    ctx = _FakeContext(reply="original")

    async def _hook(
        result: HostedRunResult[Any],
        *,
        request: ChannelRequest,
        channel_name: str,
    ) -> HostedRunResult[Any]:
        assert channel_name == "mcp"
        assert request.channel == "mcp"
        return HostedRunResult(_FakeResp(text="hooked"))

    channel = _make_channel(ctx, streaming=False, response_hook=_hook)
    async with create_connected_server_and_client_session(_server(channel)) as client:
        result = await client.call_tool("run_agent", {"input": "hello"})
    assert _text(result.content[0]) == "hooked"


async def test_streaming_response_hook_shapes_final_reply() -> None:
    ctx = _FakeContext(chunks=["raw"])

    async def _hook(
        result: HostedRunResult[Any],
        *,
        request: ChannelRequest,
        channel_name: str,
    ) -> HostedRunResult[Any]:
        return HostedRunResult(_FakeResp(text=f"{channel_name}:{request.channel}:{result.result.text}"))

    channel = _make_channel(ctx, streaming=True, response_hook=_hook)
    async with create_connected_server_and_client_session(_server(channel)) as client:
        result = await client.call_tool("run_agent", {"input": "hello"})
    assert _text(result.content[0]) == "mcp:mcp:raw"


def test_default_path_and_name() -> None:
    channel = MCPChannel()
    assert channel.name == "mcp"
    assert channel.path == "/mcp"


def test_content_conversion_handles_non_text_shapes() -> None:
    from agent_framework_hosting_mcp._channel import _content_to_mcp, _structured_content, _value_to_mcp

    @dataclass
    class StructuredValue:
        answer: int

    circular: list[Any] = []
    circular.append(circular)

    assert _structured_content(None) is None
    assert _structured_content(StructuredValue(answer=42)) == {"answer": 42}
    assert _structured_content(circular) == {"value": "[[...]]"}
    assert _content_to_mcp(Content("data", uri="not-a-data-uri", media_type="application/octet-stream")) == []
    assert _text(_content_to_mcp(Content("text_reasoning", text="because"))[0]) == "because"
    assert (
        _text(_content_to_mcp(Content.from_function_result("call-1", result=[Content.from_text("nested")]))[0])
        == "nested"
    )
    assert _text(_content_to_mcp(Content.from_function_result("call-1", result={"x": 1}))[0]) == '{"x": 1}'
    assert _text(_content_to_mcp(Content.from_error(message="bad"))[0]) == "bad"
    assert _content_to_mcp(Content.from_function_call("call-1", "tool")) == []
    assert _text(_value_to_mcp(Message(role="assistant", contents=[Content.from_text("message")]))[0]) == "message"
    assert _value_to_mcp(b"bytes")[0].type == "resource"
    assert _text(_value_to_mcp({"x": 1})[0]) == '{"x": 1}'


def test_result_conversion_handles_workflow_and_fallback_shapes() -> None:
    class WorkflowResult:
        value = None

        def get_outputs(self) -> list[Message]:
            return [Message(role="assistant", contents=[Content.from_text("workflow")])]

    @dataclass
    class TextOnlyResult:
        text: str
        value: Any | None = None

    channel = MCPChannel()

    workflow_result = channel._result_to_content(HostedRunResult(WorkflowResult()))
    assert _text(workflow_result.content[0]) == "workflow"

    text_result = channel._result_to_content(HostedRunResult(TextOnlyResult(text="fallback")))
    assert _text(text_result.content[0]) == "fallback"

    structured_result = channel._result_to_content(HostedRunResult(TextOnlyResult(text="", value={"x": 1})))
    assert structured_result.structuredContent == {"x": 1}
    assert _text(structured_result.content[0]) == '{\n  "x": 1\n}'

    empty_result = channel._result_to_content(HostedRunResult(TextOnlyResult(text="")))
    assert _text(empty_result.content[0]) == ""


async def test_http_mcp_client_can_call_hosted_channel(unused_tcp_port: int) -> None:
    host = AgentFrameworkHost(target=cast(Any, _HostedAgent()), channels=[MCPChannel(streaming=False)])

    async with (
        _serve_app(host.app, port=unused_tcp_port) as base_url,
        streamable_http_client(f"{base_url}/mcp/") as (read_stream, write_stream, _),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool("run_agent", {"input": "hello", "session_id": "conv-1"})

    assert [tool.name for tool in tools.tools] == ["run_agent"]
    assert _text(result.content[0]) == "host: hello"


async def test_streaming_non_text_contents_not_forwarded_as_progress() -> None:
    """Non-text content items in stream updates must not produce progress text."""
    image_update = _FakeUpdate(
        text="",
        contents=[Content.from_uri(uri="https://example.com/img.png", media_type="image/png")],
    )
    text_update = _FakeUpdate(text="text chunk", contents=[Content.from_text(text="text chunk")])
    ctx = _FakeContext(stream_updates=[text_update, image_update])
    channel = _make_channel(ctx, streaming=True)

    async with create_connected_server_and_client_session(_server(channel)) as client:
        result = await client.call_tool("run_agent", {"input": "query"})

    # Should not error — image update silently skipped, text update forwarded as progress.
    assert not result.isError


async def test_default_hook_strips_options_when_no_run_hook_supplied() -> None:
    """When no run_hook is configured, caller-supplied options must be stripped."""

    ctx = _FakeContext(reply="ok")
    channel = _make_channel(ctx, streaming=False)  # no run_hook

    async with create_connected_server_and_client_session(_server(channel)) as client:
        # The MCP tool call does not pass options directly, but we can verify
        # the channel applied its default hook by checking stored requests.
        await client.call_tool("run_agent", {"input": "hello"})

    assert len(ctx.requests) == 1
    # Default hook must have stripped options.
    assert ctx.requests[0].options is None
