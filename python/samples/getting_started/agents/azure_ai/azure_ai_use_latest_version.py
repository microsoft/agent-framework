# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Azure AI Agent Latest Version Example

This sample demonstrates how to reuse the latest version of an existing agent
instead of creating a new agent version on each instantiation. The first call creates a new agent,
while subsequent calls with `use_latest_version=True` reuse the latest agent version.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with AzureCliCredential() as credential:
        async with (
            AzureAIClient(
                async_credential=credential,
            ).create_agent(
                name="MyWeatherAgent",
                instructions="You are a helpful weather agent.",
                tools=get_weather,
            ) as agent,
        ):
            # First query will create a new agent
            query = "What's the weather like in Seattle?"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result}\n")

        # Create a new agent instance
        async with (
            AzureAIClient(
                async_credential=credential,
                # This parameter will allow to re-use latest agent version
                # instead of creating a new one
                use_latest_version=True,
            ).create_agent(
                name="MyWeatherAgent",
                instructions="You are a helpful weather agent.",
                tools=get_weather,
            ) as agent,
        ):
            query = "What's the weather like in Tokyo?"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
