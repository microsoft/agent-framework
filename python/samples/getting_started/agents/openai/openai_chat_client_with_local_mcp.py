# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient

"""
OpenAI Chat Client with Local MCP Example

This sample demonstrates integrating Model Context Protocol (MCP) tools with
OpenAI Chat Client for extended functionality and external service access.

The Agent Framework now supports enhanced metadata extraction from MCP tool
results, including error states, token usage, costs, and other arbitrary
metadata through the _meta field of CallToolResult objects.
"""


async def mcp_tools_on_run_level() -> None:
    """Example showing MCP tools defined when running the agent."""
    print("=== Tools Defined on Run Level ===")

    # Tools are provided when running the agent
    # This means we have to ensure we connect to the MCP server before running the agent
    # and pass the tools to the run method.
    async with (
        MCPStreamableHTTPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
        ) as mcp_server,
        ChatAgent(
            chat_client=OpenAIChatClient(),
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
    async with OpenAIChatClient().create_agent(
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=MCPStreamableHTTPTool(  # Tools defined at agent creation
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
        ),
    ) as agent:
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
    print("=== OpenAI Chat Client Agent with MCP Tools Examples ===\n")

    await mcp_tools_on_agent_level()
    await mcp_tools_on_run_level()


if __name__ == "__main__":
    asyncio.run(main())
