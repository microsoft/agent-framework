# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for :class:`MCPChannel` using the in-memory MCP client transport."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass, field
from typing import Any

import mcp.types as types
from agent_framework import Content
from agent_framework_hosting import ChannelRequest, HostedRunResult
from mcp.shared.memory import create_connected_server_and_client_session

from agent_framework_hosting_mcp import MCPChannel

# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #


@dataclass
class _FakeResp:
    text: str


@dataclass
class _FakeUpdate:
    text: str
    contents: list[Content] = field(default_factory=list)
    message_id: str | None = None


class _FakeStream:
    def __init__(self, chunks: list[str], final: _FakeResp | None = None) -> None:
        self._chunks = chunks
        self._final = final or _FakeResp(text="".join(chunks))

    def __aiter__(self) -> AsyncIterator[_FakeUpdate]:
        async def _gen() -> AsyncIterator[_FakeUpdate]:
            for c in self._chunks:
                yield _FakeUpdate(text=c)

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
    ) -> None:
        self.target = _FakeTarget()
        self._reply = reply
        self._chunks = chunks or [reply]
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
        result = HostedRunResult(_FakeResp(text=self._reply))
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
        result = HostedRunResult(_FakeResp(text="".join(self._chunks)))
        if response_hook is not None:
            maybe_result = response_hook(result, request=request, channel_name=channel_name or request.channel)
            if isinstance(maybe_result, Awaitable):
                result = await maybe_result
            else:
                result = maybe_result
        return _FakeStream(self._chunks, final=result.result)


def _make_channel(ctx: _FakeContext, **kwargs: Any) -> MCPChannel:
    channel = MCPChannel(**kwargs)
    channel.contribute(ctx)  # type: ignore[arg-type]
    return channel


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


async def test_list_tools_advertises_single_configured_tool() -> None:
    ctx = _FakeContext()
    channel = _make_channel(ctx, tool_name="ask", tool_description="Ask the assistant.")
    async with create_connected_server_and_client_session(channel._server) as client:  # type: ignore[arg-type]
        result = await client.list_tools()
    assert len(result.tools) == 1
    tool = result.tools[0]
    assert tool.name == "ask"
    assert tool.description == "Ask the assistant."
    assert tool.inputSchema["required"] == ["input"]
    assert set(tool.inputSchema["properties"]) == {"input", "session_id"}


async def test_call_tool_routes_through_host_and_returns_text() -> None:
    ctx = _FakeContext(reply="hi back", chunks=["hi", " back"])
    channel = _make_channel(ctx, streaming=False)
    async with create_connected_server_and_client_session(channel._server) as client:  # type: ignore[arg-type]
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


async def test_call_tool_streaming_aggregates_chunks() -> None:
    ctx = _FakeContext(chunks=["foo", "bar", "baz"])
    channel = _make_channel(ctx, streaming=True)
    async with create_connected_server_and_client_session(channel._server) as client:  # type: ignore[arg-type]
        result = await client.call_tool("run_agent", {"input": "hello"})
    assert result.content[0].text == "foobarbaz"  # type: ignore[union-attr]
    # No session_id supplied -> no session / identity.
    assert ctx.requests[0].session is None
    assert ctx.requests[0].identity is None


async def test_call_tool_rejects_empty_input() -> None:
    ctx = _FakeContext()
    channel = _make_channel(ctx)
    async with create_connected_server_and_client_session(channel._server) as client:  # type: ignore[arg-type]
        result = await client.call_tool("run_agent", {"input": ""})
    assert "non-empty string" in result.content[0].text  # type: ignore[union-attr]
    assert ctx.requests == []


async def test_run_hook_can_reshape_request() -> None:
    ctx = _FakeContext(reply="ok")

    async def _hook(request: ChannelRequest, *, target: Any, protocol_request: Any) -> ChannelRequest:
        import dataclasses

        return dataclasses.replace(request, attributes={**dict(request.attributes), "hooked": True})

    channel = _make_channel(ctx, streaming=False, run_hook=_hook)
    async with create_connected_server_and_client_session(channel._server) as client:  # type: ignore[arg-type]
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
    async with create_connected_server_and_client_session(channel._server) as client:  # type: ignore[arg-type]
        result = await client.call_tool("run_agent", {"input": "hello"})
    assert result.content[0].text == "hooked"  # type: ignore[union-attr]


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
    async with create_connected_server_and_client_session(channel._server) as client:  # type: ignore[arg-type]
        result = await client.call_tool("run_agent", {"input": "hello"})
    assert result.content[0].text == "mcp:mcp:raw"  # type: ignore[union-attr]


def test_default_path_and_name() -> None:
    channel = MCPChannel()
    assert channel.name == "mcp"
    assert channel.path == "/mcp"
