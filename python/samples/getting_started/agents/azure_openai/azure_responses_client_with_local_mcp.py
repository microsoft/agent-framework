# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent, MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

"""
Azure OpenAI Responses Client with local Model Context Protocol (MCP) Example

This sample demonstrates integration of Azure OpenAI Responses Client with local Model Context Protocol (MCP)
servers.
"""


# --- Below code uses Microsoft Learn MCP server over Streamable HTTP ---
# --- Users can set these environment variables, or just edit the values below to their desired local MCP server
MCP_NAME = os.environ.get("MCP_NAME", "Microsoft Learn MCP")  # example name
MCP_URL = os.environ.get("MCP_URL", "https://learn.microsoft.com/api/mcp")  # example endpoint

# Environment variables for Azure OpenAI Responses authentication
# AZURE_OPENAI_ENDPOINT="<your-azure openai-endpoint>"
# AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME="<your-deployment-name>"
# AZURE_OPENAI_API_VERSION="<your-api-version>"  # e.g. "2025-03-01-preview"


async def main():
    """Example showing local MCP tools for a Azure OpenAI Responses Agent."""
    # AuthN: use Azure CLI
    credential = AzureCliCredential()

    # Build an agent backed by Azure OpenAI Responses
    # (endpoint/deployment/api_version can also come from env vars above)
    responses_client = AzureOpenAIResponsesClient(
        credential=credential,
    )

    agent: ChatAgent = responses_client.create_agent(
        name="DocsAgent",
        instructions=("You are a helpful assistant that can help with Microsoft documentation questions."),
    )

    # Connect to the MCP server (Streamable HTTP)
    async with MCPStreamableHTTPTool(
        name=MCP_NAME,
        url=MCP_URL,
    ) as mcp_tool:
        # First query — expect the agent to use the MCP tool if it helps
        q1 = "How to create an Azure storage account using az cli?"
        r1 = await agent.run(q1, tools=mcp_tool)
        print("\n=== Answer 1 ===\n", r1.text)

        # Follow-up query (connection is reused)
        q2 = "What is Microsoft Agent Framework?"
        r2 = await agent.run(q2, tools=mcp_tool)
        print("\n=== Answer 2 ===\n", r2.text)


if __name__ == "__main__":
    asyncio.run(main())
