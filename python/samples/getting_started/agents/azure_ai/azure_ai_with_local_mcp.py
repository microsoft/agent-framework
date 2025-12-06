# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import MCPStreamableHTTPTool
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Local MCP Example

This sample demonstrates integration of Azure AI Agents with local Model Context Protocol (MCP)
servers.

Pre-requisites:
- Make sure to set up the AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME
  environment variables before running this sample.
"""


async def main() -> None:
    """Example showing use of Local MCP Tool with AzureAIClient."""
    print("=== Azure AI Agent with Local MCP Tools Example ===\n")

    async with (
        AzureCliCredential() as credential,
        AzureAIClient(credential=credential).create_agent(
            name="DocsAgent",
            instructions="You are a helpful assistant that can help with Microsoft documentation questions.",
            tools=MCPStreamableHTTPTool(
                name="Microsoft Learn MCP",
                url="https://learn.microsoft.com/api/mcp",
            ),
        ) as agent,
    ):
        # First query
        first_query = "How to create an Azure storage account using az cli?"
        print(f"User: {first_query}")
        first_result = await agent.run(first_query)
        print(f"Agent: {first_result}")
        print("\n=======================================\n")
        # Second query
        second_query = "What is Microsoft Agent Framework?"
        print(f"User: {second_query}")
        second_result = await agent.run(second_query)
        print(f"Agent: {second_result}")


if __name__ == "__main__":
    asyncio.run(main())
