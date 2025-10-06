# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, MCPStreamableHTTPTool
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Local MCP Example

This sample demonstrates integration of Azure AI Agents with local Model Context Protocol (MCP)
servers, showing both agent-level and run-level tool configuration patterns.
"""


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
        ChatAgent(
            chat_client=AzureAIAgentClient(async_credential=credential),
            name="DocsAgent",
            instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        ) as agent,
    ):
        # First query
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await agent.run(query1, tools=mcp_server)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        result2 = await agent.run(query2, tools=mcp_server)
        print(f"{agent.name}: {result2}\n")


async def mcp_tools_on_agent_level() -> None:
    """Example showing tools defined when creating the agent."""
    print("=== Tools Defined on Agent Level ===")

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    # The agent will connect to the MCP server through its context manager.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="DocsAgent",
            instructions="You are a helpful assistant that can help with microsoft documentation questions.",
            tools=MCPStreamableHTTPTool(  # Tools defined at agent creation
                name="Microsoft Learn MCP",
                url="https://learn.microsoft.com/api/mcp",
            ),
        ) as agent,
    ):
        # First query
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await agent.run(query1)
        print(f"{agent.name}: {result1}\n")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        result2 = await agent.run(query2)
        print(f"{agent.name}: {result2}\n")


async def main() -> None:
    print("=== Azure AI Chat Client Agent with MCP Tools Examples ===\n")

    await mcp_tools_on_agent_level()
    await mcp_tools_on_run_level()


if __name__ == "__main__":
    asyncio.run(main())
