# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential
from pydantic import Field
from agent_framework import tool

"""
Azure AI Agent Latest Version Example

This sample demonstrates how to reuse the latest version of an existing agent
instead of creating a new agent version on each instantiation. The first call creates a new agent,
while subsequent calls with `get_agent()` reuse the latest agent version.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # First call creates a new agent
        agent = await provider.create_agent(
            name="MyWeatherAgent",
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        )

        query = "What's the weather like in Seattle?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

        # Second call retrieves the existing agent (latest version) instead of creating a new one
        # This is useful when you want to reuse an agent that was created earlier
        agent2 = await provider.get_agent(
            name="MyWeatherAgent",
            tools=get_weather,  # Tools must be provided for function tools
        )

        query = "What's the weather like in Tokyo?"
        print(f"User: {query}")
        result = await agent2.run(query)
        print(f"Agent: {result}\n")

        print(f"First agent ID with version: {agent.id}")
        print(f"Second agent ID with version: {agent2.id}")


if __name__ == "__main__":
    asyncio.run(main())
