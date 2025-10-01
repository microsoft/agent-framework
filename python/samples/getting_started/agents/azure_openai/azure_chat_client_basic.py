# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import Field

"""
Azure OpenAI Chat Client Basic Example

This sample demonstrates basic usage of AzureOpenAIChatClient for direct chat-based
interactions, showing both streaming and non-streaming responses.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    # Create agent with Azure Chat Client
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
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

    # Create agent with Azure Chat Client
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
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
    print("=== Basic Azure Chat Client Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
