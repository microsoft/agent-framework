# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIResponsesClient

"""
OpenAI Responses Client with Local MCP Example

This sample demonstrates integrating local Model Context Protocol (MCP) tools with
OpenAI Responses Client for direct response generation with external capabilities.
"""


async def streaming_with_mcp(show_raw_stream: bool = False) -> None:
    """Example showing tools defined when creating the agent.

    If you want to access the full stream of events that has come from the model, you can access it,
    through the raw_representation. You can view this, by setting the show_raw_stream parameter to True.
    """
    print("=== Tools Defined on Agent Level ===")
    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
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
        print(f"{agent.name}: ", end="")
        async for chunk in agent.run_stream(query1):
            if show_raw_stream:
                print("Streamed event: ", chunk.raw_representation.raw_representation)  # type:ignore
            elif chunk.text:
                print(chunk.text, end="")
        print("")
        print("\n=======================================\n")
        # Second query
        query2 = "What is Microsoft Agent Framework?"
        print(f"User: {query2}")
        print(f"{agent.name}: ", end="")
        async for chunk in agent.run_stream(query2):
            if show_raw_stream:
                print("Streamed event: ", chunk.raw_representation.raw_representation)  # type:ignore
            elif chunk.text:
                print(chunk.text, end="")
        print("\n\n")


async def run_with_mcp() -> None:
    """Example showing tools defined when creating the agent."""
    print("=== Tools Defined on Agent Level ===")

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
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
    print("=== OpenAI Responses Client Agent with Function Tools Examples ===\n")

    await run_with_mcp()
    await streaming_with_mcp()


if __name__ == "__main__":
    asyncio.run(main())
