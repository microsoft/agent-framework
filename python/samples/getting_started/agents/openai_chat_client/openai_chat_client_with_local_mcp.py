# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatClientAgent, MCPStreamableHttpTools
from agent_framework.openai import OpenAIChatClient


async def tools_on_agent_level() -> None:
    """Example showing tools defined when creating the agent."""
    print("=== Tools Defined on Agent Level ===")
    mcp_server = MCPStreamableHttpTools(name="Microsoft Learn MCP", url="https://learn.microsoft.com/api/mcp")

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    async with ChatClientAgent(
        chat_client=OpenAIChatClient(),
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=mcp_server,  # Tools defined at agent creation
    ) as agent:
        # First query
        query1 = "How to create an Azure storage account using az cli?"
        print(f"User: {query1}")
        result1 = await agent.run(query1)
        print(f"{agent.name}: {result1}\n")

        # Second query
        query2 = "What is Microsoft Semantic Kernel?"
        print(f"User: {query2}")
        result2 = await agent.run(query2)
        print(f"{agent.name}: {result2}\n")


async def main() -> None:
    print("=== OpenAI Chat Client Agent with MCP Tools Examples ===\n")

    await tools_on_agent_level()


if __name__ == "__main__":
    asyncio.run(main())
