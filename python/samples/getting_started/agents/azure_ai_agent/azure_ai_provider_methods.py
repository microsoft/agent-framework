# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework.azure import AzureAIAgentsProvider
from azure.ai.agents.aio import AgentsClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field
from agent_framework import tool

"""
Azure AI Agent Provider Methods Example

This sample demonstrates the methods available on the AzureAIAgentsProvider class:
- create_agent(): Create a new agent on the service
- get_agent(): Retrieve an existing agent by ID
- as_agent(): Wrap an SDK Agent object without making HTTP calls
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def create_agent_example() -> None:
    """Create a new agent using provider.create_agent()."""
    print("\n--- create_agent() ---")

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather assistant.",
            tools=get_weather,
        )

        print(f"Created: {agent.name} (ID: {agent.id})")
        result = await agent.run("What's the weather in Seattle?")
        print(f"Response: {result}")


async def get_agent_example() -> None:
    """Retrieve an existing agent by ID using provider.get_agent()."""
    print("\n--- get_agent() ---")

    async with (
        AzureCliCredential() as credential,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
        AzureAIAgentsProvider(agents_client=agents_client) as provider,
    ):
        # Create an agent directly with SDK (simulating pre-existing agent)
        sdk_agent = await agents_client.create_agent(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            name="ExistingAgent",
            instructions="You always respond with 'Hello!'",
        )

        try:
            # Retrieve using provider
            agent = await provider.get_agent(sdk_agent.id)
            print(f"Retrieved: {agent.name} (ID: {agent.id})")

            result = await agent.run("Hi there!")
            print(f"Response: {result}")
        finally:
            await agents_client.delete_agent(sdk_agent.id)


async def as_agent_example() -> None:
    """Wrap an SDK Agent object using provider.as_agent()."""
    print("\n--- as_agent() ---")

    async with (
        AzureCliCredential() as credential,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
        AzureAIAgentsProvider(agents_client=agents_client) as provider,
    ):
        # Create agent using SDK
        sdk_agent = await agents_client.create_agent(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            name="WrappedAgent",
            instructions="You respond with poetry.",
        )

        try:
            # Wrap synchronously (no HTTP call)
            agent = provider.as_agent(sdk_agent)
            print(f"Wrapped: {agent.name} (ID: {agent.id})")

            result = await agent.run("Tell me about the sunset.")
            print(f"Response: {result}")
        finally:
            await agents_client.delete_agent(sdk_agent.id)


async def multiple_agents_example() -> None:
    """Create and manage multiple agents with a single provider."""
    print("\n--- Multiple Agents ---")

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        weather_agent = await provider.create_agent(
            name="WeatherSpecialist",
            instructions="You are a weather specialist.",
            tools=get_weather,
        )

        greeter_agent = await provider.create_agent(
            name="GreeterAgent",
            instructions="You are a friendly greeter.",
        )

        print(f"Created: {weather_agent.name}, {greeter_agent.name}")

        greeting = await greeter_agent.run("Hello!")
        print(f"Greeter: {greeting}")

        weather = await weather_agent.run("What's the weather in Tokyo?")
        print(f"Weather: {weather}")


async def main() -> None:
    print("Azure AI Agent Provider Methods")

    await create_agent_example()
    await get_agent_example()
    await as_agent_example()
    await multiple_agents_example()


if __name__ == "__main__":
    asyncio.run(main())
