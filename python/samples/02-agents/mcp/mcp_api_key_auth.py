# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
MCP API Key Authentication Example

This sample demonstrates the runtime ``header_provider`` pattern for
``MCPStreamableHTTPTool``. The MCP tool derives authentication headers from
``function_invocation_kwargs`` passed to ``Agent.run(...)`` so the API key stays
in runtime context instead of being baked into a shared ``httpx.AsyncClient``.

Replace the ``url`` parameter in the ``MCPStreamableHTTPTool`` with your authenticated server URL and
run the sample with your API key as a command-line argument:
    python mcp_api_key_auth.py <your_api_key>

The ``header_provider`` here is just a simple lambda, but it can be a more complex function that retrieves and
formats headers as needed, allowing for flexible authentication schemes.
For more complex scenarios, you could implement token refresh logic or support multiple authentication methods
within the header provider function.

For more authentication examples including OAuth 2.0 flows, see:
- https://github.com/modelcontextprotocol/python-sdk/tree/main/examples/clients/simple-auth-client
- https://github.com/modelcontextprotocol/python-sdk/tree/main/examples/servers/simple-auth
"""


async def api_key_auth_example(api_key: str) -> None:
    """Run an agent against an MCP server using runtime-provided API key headers."""

    async with Agent(
        client=OpenAIChatClient(),
        name="Agent",
        instructions="You are a helpful assistant. Use your MCP tool when answering the user's question.",
        tools=MCPStreamableHTTPTool(
            name="MCP tool",
            description="MCP tool description.",
            url="<your authenticated server url>",
            header_provider=lambda kwargs: {"Authorization": f"Bearer {kwargs['mcp_api_key']}"},
        ),
    ) as agent:
        query = "Use your MCP tool to tell me what tools are available to you."
        print(f"User: {query}")
        result = await agent.run(
            query,
            function_invocation_kwargs={"mcp_api_key": api_key},
        )
        print(f"Agent: {result.text}")


if __name__ == "__main__":
    asyncio.run(api_key_auth_example(sys.argv[1]))
