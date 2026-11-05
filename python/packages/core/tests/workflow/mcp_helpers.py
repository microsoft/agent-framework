# Copyright (c) Microsoft. All rights reserved.

"""In-process stateful MCP server for workflow isolation regressions."""

from typing import Any

import httpx2 as httpx
from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.shared.exceptions import MCPError
from starlette.requests import Request

_AsyncClient = httpx.AsyncClient


class StatefulMCPServer:
    def __init__(self) -> None:
        self.histories: dict[str, list[str]] = {}
        self.clients: list[httpx.AsyncClient] = []
        self.server = Server(
            "workflow-isolation",
            on_list_tools=self.list_tools,
            on_call_tool=self.call_tool,
        )
        self.server.add_request_handler("server/discover", types.RequestParams, self.reject_discovery)
        self.app = self.server.streamable_http_app(json_response=True)

    async def reject_discovery(self, ctx: ServerRequestContext, params: types.RequestParams) -> types.DiscoverResult:
        # Exercise the stateful handshake, not the modern stateless HTTP protocol.
        raise MCPError(-32601, "Method not found")

    async def list_tools(
        self, ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[types.Tool(name="remember", input_schema={"type": "object", "properties": {}})]
        )

    async def call_tool(self, ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
        assert isinstance(ctx.request, Request)
        session_id = ctx.request.headers["mcp-session-id"]
        history = self.histories.setdefault(session_id, [])
        history.append("marker")
        return types.CallToolResult(content=[types.TextContent(type="text", text=str(len(history)))])

    def create_client(self, **kwargs: Any) -> httpx.AsyncClient:
        client = _AsyncClient(transport=httpx.ASGITransport(app=self.app), **kwargs)
        self.clients.append(client)
        return client
