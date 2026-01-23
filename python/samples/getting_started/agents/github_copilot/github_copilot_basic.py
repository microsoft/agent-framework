# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent Basic Example

This sample demonstrates basic usage of GithubCopilotAgent.
Shows both streaming and non-streaming responses with function tools.

Environment variables (optional):
- GITHUB_COPILOT_CLI_PATH - Path to the Copilot CLI executable
- GITHUB_COPILOT_MODEL - Model to use (e.g., "gpt-5", "claude-sonnet-4")
- GITHUB_COPILOT_TIMEOUT - Request timeout in seconds
- GITHUB_COPILOT_LOG_LEVEL - CLI log level
"""

import asyncio
from random import randint
from typing import Annotated

from agent_framework.github_copilot import GithubCopilotAgent
from pydantic import Field


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}C."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    async with GithubCopilotAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    ) as agent:
        query = "What's the weather like in Seattle?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    async with GithubCopilotAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    ) as agent:
        query = "What's the weather like in Tokyo?"
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run_stream(query):
            if chunk.text:
                print(chunk.text, end="", flush=True)
        print("\n")


async def main() -> None:
    print("=== Basic GitHub Copilot Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
