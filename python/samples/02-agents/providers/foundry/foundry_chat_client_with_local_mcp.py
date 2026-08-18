# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Foundry Chat Client with Local Model Context Protocol (MCP) Example

This sample demonstrates integration of FoundryChatClient with local Model Context Protocol (MCP)
servers.
"""


# --- Below code uses Microsoft Learn MCP server over Streamable HTTP ---
# --- Users can set these environment variables, or just edit the values below to their desired local MCP server
MCP_NAME = os.environ.get("MCP_NAME", "Microsoft Learn MCP")  # example name
MCP_URL = os.environ.get("MCP_URL", "https://learn.microsoft.com/api/mcp")  # example endpoint

# Environment variables for FoundryChatClient authentication
# FOUNDRY_PROJECT_ENDPOINT="<your-foundry-project-endpoint>"
# FOUNDRY_MODEL="<your-deployment-name>"


async def main():
    """Example showing local MCP tools for a Foundry Chat Client agent."""
    # AuthN: use Azure CLI
    credential = AzureCliCredential()

    # Build an agent backed by FoundryChatClient
    # (project endpoint and model can also come from env vars above)
    responses_client = FoundryChatClient(
        credential=credential,
    )

    agent: Agent = Agent(
        client=responses_client,
        name="DocsAgent",
        instructions=("You are a helpful assistant that can help with Microsoft documentation questions."),
    )

    # Connect to the MCP server (Streamable HTTP)
    async with MCPStreamableHTTPTool(
        name=MCP_NAME,
        url=MCP_URL,
    ) as mcp_tool:
        # First query — expect the agent to use the MCP tool if it helps
        first_query = "How to create an Azure storage account using az cli?"
        first_response = await agent.run(first_query, tools=mcp_tool)
        print("\n=== Answer 1 ===\n", first_response.text)

        # Follow-up query (connection is reused)
        second_query = "What is Microsoft Agent Framework?"
        second_response = await agent.run(second_query, tools=mcp_tool)
        print("\n=== Answer 2 ===\n", second_response.text)


if __name__ == "__main__":
    asyncio.run(main())
