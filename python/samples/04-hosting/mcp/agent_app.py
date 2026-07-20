# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-foundry",
#     "agent-framework-hosting-mcp",
#     "azure-identity",
#     "mcp>=1.27.0,<2",
#     "starlette>=0.40",
#     "uvicorn>=0.30",
# ]
# ///
# Run with: uv run agent_app.py

# Copyright (c) Microsoft. All rights reserved.

"""Host an Agent Framework agent with the native MCP streamable HTTP server.

The hosting helper package only converts values at the protocol boundary. This
application owns the MCP tool schema, server, transport, authentication policy,
and Agent Framework session policy.

This compact local sample is intentionally unauthenticated and stateless:
every tool call starts a fresh Agent Framework conversation. Add authentication
in the outer ASGI server before deriving a trusted user or tenant session key.

Required environment variables: ``FOUNDRY_PROJECT_ENDPOINT`` and
``FOUNDRY_MODEL``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_hosting_mcp import MCPAgentTool
from azure.identity.aio import DefaultAzureCredential
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

server = Server("agent-framework-hosting-mcp-sample")
credential = DefaultAzureCredential()
agent = Agent(
    client=FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=credential,
    ),
    name="MCPHostedAgent",
    description="Answer a request with the hosted Agent Framework agent.",
    instructions="Answer the user's request clearly and concisely.",
)
agent_tool = MCPAgentTool(
    agent,
    name="run_agent",
    argument_description="The request for the hosted agent.",
    chat_option_parameters={
        "reasoning_effort": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Optional reasoning effort for models that support it.",
        }
    },
)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Describe the app-owned MCP tool schema."""
    return await agent_tool.list_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, object] | None) -> list[types.ContentBlock]:
    """Run the app-owned tool with native MCP and Agent Framework values."""
    return await agent_tool.call_tool(name, arguments)


session_manager = StreamableHTTPSessionManager(
    app=server,
    event_store=None,
    json_response=True,
    stateless=True,
)


@asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    """Start and stop native MCP and model-client resources."""
    async with session_manager.run(), credential:
        yield


app = Starlette(
    routes=[Mount("/", app=session_manager.handle_request)],
    lifespan=lifespan,
)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
