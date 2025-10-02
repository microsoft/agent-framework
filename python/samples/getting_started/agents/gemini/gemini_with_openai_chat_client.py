# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework.openai import OpenAIChatClient

"""
Gemini with OpenAI Chat Client Example

This sample demonstrates using Gemini models through OpenAI Chat Client by
configuring the base URL to point to Google's API for cross-provider compatibility.
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
        api_key=os.getenv("GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model_id=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    ).create_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")


async def main() -> None:
    print("=== Gemini with OpenAI Chat Client Agent Example ===")

    await non_streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
