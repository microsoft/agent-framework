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
# Run with: uv run session_app.py

# Copyright (c) Microsoft. All rights reserved.

"""Host a session-aware Agent Framework agent through native MCP constructs.

The MCP tool accepts an opaque, app-defined ``session_id`` string. Its format is
not prescribed by MCP or Agent Framework; an application might use a UUID, a
database key, or a key derived from authenticated tenant and conversation IDs.
Reusing an ID continues and updates that one conversation.

This is deliberately different from ``previous_response_id``-style branching,
where an earlier point can be used to create a new conversation branch. An app
that needs branching should accept separate source and destination IDs, load a
copy from the source, and store the updated session under the destination.

This local sample uses the caller-provided ID directly for clarity. Production
servers must derive or authorize the session key from authenticated outer-server
context rather than trusting an arbitrary caller-provided identifier.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from agent_framework import Agent, InMemoryHistoryProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_hosting import AgentState
from agent_framework_hosting_mcp import AgentMCPTool
from azure.identity.aio import DefaultAzureCredential
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

server = Server("agent-framework-hosting-mcp-session-sample")
credential = DefaultAzureCredential()
agent = Agent(
    client=FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=credential,
    ),
    name="SessionAwareAgent",
    description="Answer requests while preserving app-owned conversation state.",
    instructions="Answer clearly and use prior conversation context when relevant.",
    context_providers=[InMemoryHistoryProvider()],
    default_options={"store": False},
)
state = AgentState(agent)
agent_tool = AgentMCPTool(
    state,
    name="run_agent",
    argument_description="The request for the hosted agent.",
    parameters={
        "session_id": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Opaque, app-defined conversation key. Reuse the same value to continue and update one conversation."
            ),
        }
    },
    required_parameters={"session_id"},
    chat_option_parameters={
        "reasoning_effort": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Optional reasoning effort for models that support it.",
        }
    },
    session_id_parameter="session_id",
)
session_locks: dict[str, asyncio.Lock] = {}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the agent-derived MCP tool definition."""
    return await agent_tool.list_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, object] | None) -> list[types.ContentBlock]:
    """Serialize calls per app-owned session before using ``AgentState``."""
    session_id = arguments.get("session_id") if arguments else None
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("MCP tool argument 'session_id' must be a non-empty string.")
    lock = session_locks.setdefault(session_id, asyncio.Lock())
    async with lock:
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
