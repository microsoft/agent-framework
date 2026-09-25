# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-typesafe",
#     "mcp>=1.27.0,<2",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, cast

from agent_framework import Agent, AgentResponse, MCPStdioTool
from dotenv import load_dotenv
from typesafe_sdk import Noul, SystemOneResponse

from agent_framework_typesafe import TypeSafeChatClient

load_dotenv()

"""
Discover and execute a closed-set MCP tool through TypeSafe routing.

Agent Framework connects to the MCP server and expands its discovered functions
before the TypeSafe connector sees them. Compatible MCP schemas use the same
closed-set tool routing as local FunctionTool objects.

For tool runs:

- ``response.text`` is the readable MCP tool result.
- ``response.value`` is the terminal ``SystemOneResponse`` containing all
  configured TypeSafe answers. ``Noul`` probabilities are read from that object.

Environment variables:
    TYPESAFE_API_KEY — TypeSafe API key.
"""


async def main() -> None:
    """Run the local stdio MCP weather tool."""
    # 1. Start a local stdio MCP server whose tool has Literal and boolean arguments.
    server_path = Path(__file__).with_name("mcp_weather_server.py")
    mcp = MCPStdioTool(
        name="typesafe-weather",
        command=sys.executable,
        args=[str(server_path)],
    )

    # 2. Agent connects to MCP and passes the discovered FunctionTool to TypeSafe routing.
    async with TypeSafeChatClient() as client, mcp:
        agent = Agent(client=client, name="MCPWeatherEvaluator", tools=[mcp])
        response = cast(
            AgentResponse[Any],
            await agent.run(
                "Give me a detailed weather report for Paris.",
                options={
                    # 3. Noul returns P(yes), not generated text or a separate confidence.
                    "response_format": {
                        "succeeded": Noul(instructions="Did the MCP tool result contain a successful weather report?")
                    }
                },
            ),
        )

    structured_response = response.value
    if not isinstance(structured_response, SystemOneResponse):
        raise RuntimeError("TypeSafe did not return the terminal structured response.")
    # 4. Print the useful tool output, then the typed Noul probability.
    print(response.text)
    print(f"Success probability: {structured_response.nouls['succeeded'].noul:.3f}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:

Paris is sunny and 22 C with a detailed hourly forecast.
Success probability: 0.950

The weather line comes from the MCP tool. The probability comes from the Noul
answer in ``response.value`` and is intentionally not appended to response.text.
"""
