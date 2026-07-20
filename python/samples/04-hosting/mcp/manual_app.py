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
# Run with: uv run manual_app.py

# Copyright (c) Microsoft. All rights reserved.

"""Host an Agent Framework agent using the conversion functions directly.

This version is useful when an application's MCP tool contract does not fit the
single-agent ``MCPAgentTool`` adapter. The native tool schema and handler stay
fully visible while ``mcp_to_run`` and ``mcp_from_run`` bridge AF values.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_hosting_mcp import mcp_from_run, mcp_to_run
from azure.identity.aio import DefaultAzureCredential
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

TASK_ARGUMENT = "task"
CHAT_OPTION_ARGUMENTS = {
    "reasoning_effort": {
        "type": "string",
        "enum": ["low", "medium", "high"],
        "description": "Optional reasoning effort for models that support it.",
    }
}

server = Server("agent-framework-hosting-mcp-manual-sample")
credential = DefaultAzureCredential()
agent = Agent(
    client=FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=credential,
    ),
    name="ManualMCPAgent",
    description="Answer requests through a manually defined MCP tool.",
    instructions="Answer the user's request clearly and concisely.",
)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the app-owned native MCP tool definition."""
    return [
        types.Tool(
            name="run_agent_manually",
            description=agent.description or "",
            inputSchema={
                "type": "object",
                "properties": {
                    TASK_ARGUMENT: {
                        "type": "string",
                        "description": "The request for the hosted agent.",
                    },
                    **CHAT_OPTION_ARGUMENTS,
                },
                "required": [TASK_ARGUMENT],
                "additionalProperties": False,
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, object] | None) -> list[types.ContentBlock]:
    """Convert, run, and render without the agent-backed adapter."""
    if name != "run_agent_manually":
        raise ValueError(f"Unknown MCP tool: {name}")
    run = mcp_to_run(
        arguments,
        argument_name=TASK_ARGUMENT,
        chat_option_arguments=CHAT_OPTION_ARGUMENTS,
    )
    result = await agent.run(run["messages"], options=run["options"])
    return mcp_from_run(result)


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
