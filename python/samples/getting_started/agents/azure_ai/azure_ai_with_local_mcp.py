# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import MCPStreamableHTTPTool
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Local MCP Example

This sample demonstrates integration of Azure AI Agents with local Model Context Protocol (MCP)
servers, showing both agent-level and run-level tool configuration patterns.

Pre-requisites:
- Make sure to set up the AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME
  environment variables before running this sample.
"""


async def mcp_tools_on_agent_level() -> None:
    """Example showing MCP tools defined when creating the agent."""
    print("=== Tools Defined on Agent Level ===")

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    # The agent will connect to the MCP server through its context manager.
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(async_credential=credential).create_agent(
            name="DocsAgent",
            instructions="You are a helpful assistant that can help with Microsoft documentation questions.",
            tools=MCPStreamableHTTPTool(  # Tools defined at agent creation
                name="Microsoft Learn MCP",
                url="https://learn.microsoft.com/api/mcp",
            ),
        ) as agent,
    ):
        # First query
        first_query = "How to create an Azure storage account using az cli?"
        print(f"User: {first_query}")
        first_result = await agent.run(first_query)
        print(f"Agent: {first_result}\n")
        print("\n=======================================\n")
        # Second query
        second_query = "What is Microsoft Agent Framework?"
        print(f"User: {second_query}")
        second_result = await agent.run(second_query)
        print(f"Agent: {second_result}\n")


async def mcp_tools_on_run_level() -> None:
    """Example showing MCP tools defined when running the agent."""
    print("=== Tools Defined on Run Level ===")

    # Tools are provided when running the agent
    # This means we have to ensure we connect to the MCP server before running the agent
    # and pass the tools to the run method.
    async with (
        AzureCliCredential() as credential,
        MCPStreamableHTTPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
        ) as mcp_server,
        AzureAIClient(async_credential=credential).create_agent(
            name="DocsAgent",
            instructions="You are a helpful assistant that can help with Microsoft documentation questions.",
        ) as agent,
    ):
        # First query
        first_query = "How to create an Azure storage account using az cli?"
        print(f"User: {first_query}")
        first_result = await agent.run(first_query, tools=mcp_server)
        print(f"Agent: {first_result}\n")
        print("\n=======================================\n")
        # Second query
        second_query = "What is Microsoft Agent Framework?"
        print(f"User: {second_query}")
        second_result = await agent.run(second_query, tools=mcp_server)
        print(f"Agent: {second_result}\n")


async def main() -> None:
    print("=== Azure AI Agent with Local MCP Tools Example ===\n")

    await mcp_tools_on_agent_level()
    await mcp_tools_on_run_level()


if __name__ == "__main__":
    asyncio.run(main())
