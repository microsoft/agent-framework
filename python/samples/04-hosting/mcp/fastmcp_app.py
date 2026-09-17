# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-foundry",
#     "agent-framework-hosting-mcp",
#     "azure-identity",
#     "mcp>=1.27.0,<2",
# ]
# ///
# Run with: uv run fastmcp_app.py

# Copyright (c) Microsoft. All rights reserved.

"""Host an Agent Framework agent with FastMCP and the conversion helpers.

FastMCP derives the native MCP tool schema from the decorated function
signature. The Agent Framework hosting package only converts the validated
arguments and completed agent response at the protocol boundary.

This compact local sample is intentionally unauthenticated and stateless:
every tool call starts a fresh Agent Framework conversation.

Required environment variables: ``FOUNDRY_PROJECT_ENDPOINT`` and
``FOUNDRY_MODEL``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_hosting_mcp import mcp_from_run, mcp_to_run
from azure.identity.aio import DefaultAzureCredential
from mcp import types
from mcp.server.fastmcp import FastMCP

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


@asynccontextmanager
async def lifespan(_server: FastMCP[None]) -> AsyncIterator[None]:
    """Close the model credential when the FastMCP server stops."""
    async with credential:
        yield


server = FastMCP(
    name="agent-framework-hosting-fastmcp-sample",
    instructions="Expose an Agent Framework agent as an MCP tool.",
    host="127.0.0.1",
    port=8000,
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    lifespan=lifespan,
)


@server.tool(
    name="run_agent",
    description="Run the hosted Agent Framework agent.",
    structured_output=False,
)
async def run_agent(
    task: str,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
) -> list[types.ContentBlock]:
    """Run the agent with FastMCP-validated arguments."""
    arguments: dict[str, object] = {"task": task}
    if reasoning_effort is not None:
        arguments["reasoning_effort"] = reasoning_effort

    run = mcp_to_run(arguments, chat_option_arguments={"reasoning_effort"})
    result = await agent.run(
        run["messages"],
        options=run["options"],
        stream=False,
    )
    return mcp_from_run(result)


if __name__ == "__main__":
    server.run(transport="streamable-http")
