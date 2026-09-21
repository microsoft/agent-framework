# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, cast

from agent_framework import Agent, MCPStdioTool
from typesafe_sdk import Noul, SystemOneResponse

from agent_framework_typesafe import TypeSafeChatClient

"""
Discover and execute a closed-set MCP tool through TypeSafe routing.

Environment variables:
    TYPESAFE_API_KEY — TypeSafe API key.
"""


async def main() -> None:
    """Run the local stdio MCP weather tool."""
    server_path = Path(__file__).with_name("mcp_weather_server.py")
    mcp = MCPStdioTool(
        name="typesafe-weather",
        command=sys.executable,
        args=[str(server_path)],
    )

    async with TypeSafeChatClient() as client, mcp:
        agent = Agent(client=client, name="MCPWeatherEvaluator", tools=[mcp])
        response = await agent.run(
            "Give me a detailed weather report for Paris.",
            options=cast(
                Any,
                {
                    "response_format": {
                        "succeeded": Noul(instructions="Did the MCP tool result contain a successful weather report?")
                    }
                },
            ),
        )

    if not isinstance(response.value, SystemOneResponse):
        raise RuntimeError("TypeSafe did not return the terminal structured response.")
    print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
