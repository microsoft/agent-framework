# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIResponsesClient

"""
Local MCP Tools (Streamable HTTP)

Demonstrates using MCPStreamableHTTPTool to connect to a local or remote MCP server
via the Streamable HTTP transport. Unlike HostedMCPTool (which is provider-managed),
MCPStreamableHTTPTool manages the MCP connection client-side.

Use this when:
- You're running your own MCP server
- You need more control over the MCP connection
- You need to use API key or custom authentication

For more on MCP tools:
- API key auth: getting_started/mcp/mcp_api_key_auth.py
- Azure AI local MCP: getting_started/agents/azure_ai/azure_ai_with_local_mcp.py
- Hosted MCP tools: ./hosted_mcp_tools.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/mcp-tools
"""


async def main() -> None:
    print("=== Local MCP Tools (Streamable HTTP) ===\n")

    # <create_mcp_tool>
    mcp_tool = MCPStreamableHTTPTool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
    )
    # </create_mcp_tool>

    # <create_agent>
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        name="DocsAgent",
        instructions="You are a helpful assistant that can answer questions using Microsoft documentation.",
        tools=mcp_tool,
    ) as agent:
        query = "How to create an Azure storage account using the Azure CLI?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}\n")

        query = "What is Microsoft Agent Framework?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}")
    # </create_agent>


if __name__ == "__main__":
    asyncio.run(main())
