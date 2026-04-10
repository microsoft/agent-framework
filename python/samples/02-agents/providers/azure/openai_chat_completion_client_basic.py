# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatCompletionClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Azure OpenAI Chat Client Basic Example

This sample demonstrates basic usage of OpenAIChatCompletionClient with explicit Azure
settings and a credential, showing both streaming and non-streaming responses.
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    agent = Agent(
        client=OpenAIChatCompletionClient(
            model=os.getenv("AZURE_OPENAI_MODEL"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            credential=AzureCliCredential(),
        ),
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

    agent = Agent(
        client=OpenAIChatCompletionClient(
            model=os.getenv("AZURE_OPENAI_MODEL"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            credential=AzureCliCredential(),
        ),
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    query = "What's the weather like in Portland?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== Basic Azure Chat Completion Client Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
