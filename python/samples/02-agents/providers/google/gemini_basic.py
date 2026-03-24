# Copyright (c) Microsoft. All rights reserved.

"""
Shows how to use GeminiChatClient with an agent and a custom tool, covering both
non-streaming and streaming responses.

Requires the following environment variables to be set:
- GEMINI_API_KEY
- GEMINI_MODEL
"""

import asyncio
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework_gemini import GeminiChatClient
from dotenv import load_dotenv

load_dotenv()


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example() -> None:
    """Runs the agent and waits for the complete response before printing it."""
    print("=== Non-streaming ===")

    agent = Agent(
        client=GeminiChatClient(),
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    query = "What's the weather like in Karlsruhe, Germany?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")


async def streaming_example() -> None:
    """Runs the agent and prints each chunk as it is received."""
    print("=== Streaming ===")

    agent = Agent(
        client=GeminiChatClient(),
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    query = "What's the weather like in Portland and in Paris?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
