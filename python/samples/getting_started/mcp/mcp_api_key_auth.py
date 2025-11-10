# Copyright (c) Microsoft. All rights reserved.

import os

from agent_framework import ChatAgent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIResponsesClient

"""
MCP Authentication Example

This example demonstrates how to authenticate with MCP servers using API key headers.

For more authentication examples including OAuth 2.0 flows, see:
- https://github.com/modelcontextprotocol/python-sdk/tree/main/examples/clients/simple-auth-client
- https://github.com/modelcontextprotocol/python-sdk/tree/main/examples/servers/simple-auth
"""


async def api_key_auth_example() -> None:
    """Example of using API key authentication with MCP server."""
    # Configuration
    mcp_server_url = os.getenv("MCP_SERVER_URL", "your-mcp-server-url")
    api_key = os.getenv("MCP_API_KEY")

    # Create authentication headers
    # Common patterns:
    # - Bearer token: "Authorization": f"Bearer {api_key}"
    # - API key header: "X-API-Key": api_key
    # - Custom header: "Authorization": f"ApiKey {api_key}"
    auth_headers = {
        "Authorization": f"Bearer {api_key}",
    }

    # Create MCP tool with authentication headers
    async with (
        MCPStreamableHTTPTool(
            name="MCP tool",
            description="MCP tool description",
            url=mcp_server_url,
            headers=auth_headers,  # Authentication headers
        ) as mcp_tool,
        ChatAgent(
            chat_client=OpenAIResponsesClient(),
            name="Agent",
            instructions="You are a helpful assistant.",
            tools=mcp_tool,
        ) as agent,
    ):
        query = "What tools are available to you?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}")
