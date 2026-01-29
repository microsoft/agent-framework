# Copyright (c) Microsoft. All rights reserved.

"""
Claude Agent Basic Example

This sample demonstrates using ClaudeAgent for basic interactions
with Claude Agent SDK.

Prerequisites:
- Claude Code CLI must be installed and configured
- pip install agent-framework-claude

Environment variables:
- CLAUDE_AGENT_MODEL: Model to use (sonnet, opus, haiku)
- CLAUDE_AGENT_PERMISSION_MODE: Permission mode (default, acceptEdits, bypassPermissions)
"""

import asyncio
from typing import Annotated

from agent_framework import tool
from agent_framework_claude import ClaudeAgent


@tool
def get_weather(location: Annotated[str, "The city name"]) -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is sunny with a high of 25C."


async def non_streaming_example() -> None:
    """Example of non-streaming response."""
    print("=== Non-streaming Example ===")

    agent = ClaudeAgent(
        name="BasicAgent",
        instructions="You are a helpful assistant. Keep responses concise.",
        tools=[get_weather],
    )

    async with agent:
        query = "What's the weather in Seattle?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}\n")


async def streaming_example() -> None:
    """Example of streaming response."""
    print("=== Streaming Example ===")

    agent = ClaudeAgent(
        name="StreamingAgent",
        instructions="You are a helpful assistant.",
        tools=[get_weather],
    )

    async with agent:
        query = "What's the weather in Paris?"
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run_stream(query):
            if chunk.text:
                print(chunk.text, end="", flush=True)
        print("\n")


async def main() -> None:
    print("=== Claude Agent Basic Example ===\n")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
