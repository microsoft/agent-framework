# Copyright (c) Microsoft. All rights reserved.

"""MCP client script for the local_mcp sample.

Creates a second agent that uses ``MCPStreamableHTTPTool`` to point at the
running ``local_mcp`` server. The outer agent has *no direct access* to the
weather tool — it calls the hosted ``WeatherAgent`` through MCP.

Start the server first (in another shell)::

    uv run python app.py

Then::

    uv run python call_client.py "What is the weather in Tokyo?"
    uv run python call_client.py --session my-session "What is the weather in Amsterdam?"
"""

from __future__ import annotations

import asyncio
import os
import sys

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework_foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential

BASE_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000")
MCP_URL = f"{BASE_URL}/mcp"


async def main() -> None:
    args = sys.argv[1:]
    session_id: str | None = None
    if len(args) >= 2 and args[0] == "--session":
        session_id = args[1]
        args = args[2:]
    prompt = " ".join(args) or "What is the weather in Seattle?"

    credential = DefaultAzureCredential()

    # MCPStreamableHTTPTool connects to the hosted agent's /mcp endpoint and
    # exposes its tools (run_agent) as local function tools for the outer agent.
    mcp_tool = MCPStreamableHTTPTool(
        name="weather_host",
        url=MCP_URL,
        description="Hosted WeatherAgent accessible over MCP",
    )

    outer_agent = Agent(
        client=FoundryChatClient(credential=credential),
        name="MCPCallerAgent",
        instructions="You are a helpful assistant. Use the run_agent tool to answer weather questions.",
        tools=mcp_tool,
    )

    async with mcp_tool, credential:
        tool_call_args = {"input": prompt}
        if session_id is not None:
            tool_call_args["session_id"] = session_id
        response = await outer_agent.run(prompt)
        print(f"User: {prompt}")
        print(f"Agent: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
