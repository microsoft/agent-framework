# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Azure AI Agent Basic Example

This sample demonstrates basic usage of AzureAIAgentClient to create agents with automatic
lifecycle management. Shows both streaming and non-streaming responses with function tools.
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

    # Since no Agent ID is provided, the agent will be automatically created
    # and deleted after getting a response
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        ) as agent,
    ):
        query = "What's the weather like in Seattle?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    # Since no Agent ID is provided, the agent will be automatically created
    # and deleted after getting a response
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        ) as agent,
    ):
        query = "What's the weather like in Portland?"
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run_stream(query):
            if chunk.text:
                print(chunk.text, end="", flush=True)
        print("\n")


async def main() -> None:
    print("=== Basic Azure AI Chat Client Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
