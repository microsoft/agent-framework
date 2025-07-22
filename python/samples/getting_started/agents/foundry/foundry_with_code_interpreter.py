# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatClientAgent, HostedCodeInterpreterTool
from agent_framework.foundry import FoundryChatClient


async def main() -> None:
    """Example showing how to use the HostedCodeInterpreterTool with Foundry."""
    print("=== Foundry Chat Client with Code Interpreter Example ===")

    async with ChatClientAgent(
        chat_client=FoundryChatClient(),
        instructions="You are a helpful assistant that can write and execute Python code to solve problems.",
        tools=HostedCodeInterpreterTool(),
    ) as agent:
        query = "Calculate the fibonacci sequence for the first 10 numbers and plot them"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Assistant: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
