# Copyright (c) Microsoft. All rights reserved.

"""Pytest configuration for declarative tests."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    import httpx2 as httpx
    from mcp.server import Server

# Skip all tests in this directory on Python 3.14+ because powerfx doesn't support it yet
if sys.version_info >= (3, 14):
    collect_ignore_glob = ["test_*.py"]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip all declarative tests on Python 3.14+ due to powerfx incompatibility."""
    if sys.version_info >= (3, 14):
        skip_marker = pytest.mark.skip(reason="powerfx does not support Python 3.14+")
        for item in items:
            if "declarative" in str(item.fspath):
                item.add_marker(skip_marker)


@pytest.fixture
def mcp_tool_factory() -> Callable[[], MagicMock]:
    from agent_framework import Content, MCPStreamableHTTPTool
    from mcp import types

    def create() -> MagicMock:
        tool = MagicMock(spec=MCPStreamableHTTPTool)
        tool.connect = AsyncMock()
        tool.close = AsyncMock()
        tool.call_tool = AsyncMock(return_value=[Content.from_text("ok")])
        tool._require_connection.return_value.list_tools_page = AsyncMock(return_value=types.ListToolsResult(tools=[]))
        return tool

    return create


@pytest.fixture
def mcp_tool(mcp_tool_factory: Callable[[], MagicMock]) -> MagicMock:
    return mcp_tool_factory()


@pytest.fixture
def mcp_tool_constructor(mcp_tool: MagicMock, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    import agent_framework

    constructor = MagicMock(return_value=mcp_tool)
    monkeypatch.setattr(agent_framework, "MCPStreamableHTTPTool", constructor)
    return constructor


@pytest.fixture
def stateful_mcp_server(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Server[Any], dict[str, list[str]], list[httpx.AsyncClient]]:
    import httpx2 as httpx
    from mcp import types
    from mcp.server import Server, ServerRequestContext
    from mcp.shared.exceptions import MCPError
    from starlette.requests import Request

    histories: dict[str, list[str]] = {}
    clients: list[httpx.AsyncClient] = []
    client_type = httpx.AsyncClient

    async def reject_discovery(ctx: ServerRequestContext, params: types.RequestParams) -> types.DiscoverResult:
        # Force the stateful handshake, not the modern stateless HTTP protocol.
        raise MCPError(-32601, "Method not found")

    async def list_tools(
        ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        assert isinstance(ctx.request, Request)
        histories.setdefault(ctx.request.headers["mcp-session-id"], [])
        return types.ListToolsResult(
            tools=[types.Tool(name="remember", input_schema={"type": "object", "properties": {}})]
        )

    async def call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
        assert isinstance(ctx.request, Request)
        history = histories[ctx.request.headers["mcp-session-id"]]
        history.append("marker")
        return types.CallToolResult(content=[types.TextContent(type="text", text=str(len(history)))])

    server: Server[Any] = Server("invocation-isolation", on_list_tools=list_tools, on_call_tool=call_tool)
    server.add_request_handler("server/discover", types.RequestParams, reject_discovery)
    app = server.streamable_http_app(json_response=True)

    def create_client(**kwargs: Any) -> httpx.AsyncClient:
        client = client_type(transport=httpx.ASGITransport(app=app), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", create_client)
    return server, histories, clients
