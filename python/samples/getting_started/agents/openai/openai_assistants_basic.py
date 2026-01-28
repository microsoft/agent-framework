# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework.openai import OpenAIAssistantProvider
from openai import AsyncOpenAI
from pydantic import Field
from agent_framework import tool

"""
OpenAI Assistants Basic Example

This sample demonstrates basic usage of OpenAIAssistantProvider with automatic
assistant lifecycle management, showing both streaming and non-streaming responses.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}C."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    client = AsyncOpenAI()
    provider = OpenAIAssistantProvider(client)

    # Create a new assistant via the provider
    agent = await provider.create_agent(
        name="WeatherAssistant",
        model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    try:
        query = "What's the weather like in Seattle?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")
    finally:
        # Clean up the assistant from OpenAI
        await client.beta.assistants.delete(agent.id)


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    client = AsyncOpenAI()
    provider = OpenAIAssistantProvider(client)

    # Create a new assistant via the provider
    agent = await provider.create_agent(
        name="WeatherAssistant",
        model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    try:
        query = "What's the weather like in Portland?"
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run_stream(query):
            if chunk.text:
                print(chunk.text, end="", flush=True)
        print("\n")
    finally:
        # Clean up the assistant from OpenAI
        await client.beta.assistants.delete(agent.id)


async def main() -> None:
    print("=== Basic OpenAI Assistants Provider Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
