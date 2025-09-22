# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework.openai import OpenAIChatClient

"""
Anthropic with OpenAI Chat Client Example

This sample demonstrates how to use Anthropic models through the OpenAI Chat Client by
configuring the base URL to point to Anthropic's API. The example includes:

- Setting up OpenAI Chat Client with Anthropic API configuration
- Creating an agent with tool calling capabilities (weather function)
- Non-streaming response example to get complete results at once
- Streaming response example to receive results as they are generated

This approach allows you to leverage Anthropic's Claude models while using the familiar
OpenAI client interface, making it easy to switch between different model providers.
"""


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    agent = OpenAIChatClient(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url="https://api.anthropic.com/v1/",
        ai_model_id=os.getenv("ANTHROPIC_MODEL"),
    ).create_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    agent = OpenAIChatClient(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url="https://api.anthropic.com/v1/",
        ai_model_id=os.getenv("ANTHROPIC_MODEL"),
    ).create_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    query = "What's the weather like in Portland?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run_stream(query):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== Anthropic with OpenAI Chat Client Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
