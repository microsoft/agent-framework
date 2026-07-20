# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

import pytest
import uvicorn
from agent_framework import (
    Agent,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    MCPStreamableHTTPTool,
    Message,
    ResponseStream,
)
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

from agent_framework_hosting_mcp import MCPAgentTool


class HostedAgentClient(BaseChatClient[ChatOptions[None]]):
    """Return a deterministic response from the hosted agent."""

    def __init__(self) -> None:
        super().__init__()
        self.received_options: Mapping[str, Any] | None = None

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool = False,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def get_response() -> ChatResponse:
            self.received_options = options
            return ChatResponse(messages=Message("assistant", [f"Hosted agent received: {messages[-1].text}"]))

        return get_response()


@pytest.mark.flaky
@pytest.mark.integration
async def test_mcp_tool_calls_locally_hosted_agent() -> None:
    """Host an agent, connect an MCP tool, and invoke it through real HTTP."""
    hosted_client = HostedAgentClient()
    hosted_agent = Agent(client=hosted_client, name="HostedAgent", description="Hosted test agent.")
    agent_tool: MCPAgentTool[Any] = MCPAgentTool(
        hosted_agent,
        name="run_agent",
        chat_option_parameters={"reasoning_effort": {"type": "string"}},
    )
    mcp_server = Server("hosting-mcp-integration")

    @mcp_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return await agent_tool.list_tools()

    @mcp_server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.ContentBlock]:
        return await agent_tool.call_tool(name, arguments)

    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        event_store=None,
        json_response=True,
        stateless=True,
    )

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    app = Starlette(routes=[Mount("/", app=session_manager.handle_request)], lifespan=lifespan)
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]

    uvicorn_server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on"))
    server_task = asyncio.create_task(uvicorn_server.serve())
    try:
        for _ in range(100):
            if uvicorn_server.started:
                break
            await asyncio.sleep(0.01)
        assert uvicorn_server.started

        mcp_tool = MCPStreamableHTTPTool(
            name="hosted_agent",
            url=f"http://127.0.0.1:{port}/mcp",
            approval_mode="never_require",
        )
        async with mcp_tool:
            assert len(mcp_tool.functions) == 1
            result = await mcp_tool.functions[0].invoke(task="hello through MCP", reasoning_effort="low")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].type == "text"
        assert result[0].text == "Hosted agent received: hello through MCP"
        assert hosted_client.received_options is not None
        assert hosted_client.received_options["reasoning_effort"] == "low"
    finally:
        uvicorn_server.should_exit = True
        await server_task
