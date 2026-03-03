# Copyright (c) Microsoft. All rights reserved.

"""Sample demonstrating CodexAgent usage with Agent Framework.

This sample shows how to use the CodexAgent for:
- Basic non-streaming interaction
- Streaming responses
- Multi-turn conversations with sessions
- Custom tool integration

Prerequisites:
    pip install agent-framework-codex
    export OPENAI_API_KEY="your-api-key"
"""

import asyncio

from agent_framework import tool

from agent_framework_codex import CodexAgent


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    # Stub implementation for demonstration
    return f"The weather in {city} is 72°F and sunny."


async def basic_usage() -> None:
    """Run a simple non-streaming query."""
    print("=== Basic Usage ===")
    async with CodexAgent(
        instructions="You are a helpful coding assistant.",
    ) as agent:
        response = await agent.run("What is a Python list comprehension? Give a short example.")
        print(response.text)
        print()


async def streaming_usage() -> None:
    """Stream a response token-by-token."""
    print("=== Streaming ===")
    async with CodexAgent() as agent:
        async for update in agent.run(
            "Write a short haiku about coding.",
            stream=True,
        ):
            print(update.text, end="", flush=True)
        print("\n")


async def session_usage() -> None:
    """Demonstrate multi-turn conversation using sessions."""
    print("=== Session (Multi-turn) ===")
    async with CodexAgent() as agent:
        session = agent.create_session()

        await agent.run("My name is Alice and I'm working on a FastAPI project.", session=session)
        print("(context set)")

        response = await agent.run("What's my name and what am I working on?", session=session)
        print(response.text)
        print()


async def tool_usage() -> None:
    """Demonstrate custom tool integration."""
    print("=== Custom Tools ===")
    async with CodexAgent(
        instructions="Use the get_weather tool when asked about weather.",
        tools=[get_weather],
    ) as agent:
        response = await agent.run("What's the weather like in Seattle?")
        print(response.text)
        print()


async def main() -> None:
    """Run all samples."""
    await basic_usage()
    await streaming_usage()
    await session_usage()
    await tool_usage()


if __name__ == "__main__":
    asyncio.run(main())
