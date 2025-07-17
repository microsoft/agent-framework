# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatClientAgent
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def example_1_simplest() -> None:
    """Example 1: Simplest example using environment variables only."""
    print("=== Example 1: Simplest ===")

    instructions = "You are a helpful weather assistant."

    agent = ChatClientAgent(
        FoundryChatClient(),  # Will automatically read from env vars and create/cleanup client and agent
        instructions=instructions,
        tools=get_weather,
    )

    result = await agent.run("What's the weather like in Seattle?")
    print(f"Result: {result}\n")


async def example_2_with_explicit_settings() -> None:
    """Example 2: Initialization with explicit settings."""
    print("=== Example 2: Explicit settings ===")

    instructions = "You are a helpful weather assistant."

    agent = ChatClientAgent(
        FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model_deployment_name=os.environ["FOUNDRY_MODEL_DEPLOYMENT_NAME"],
            agent_name="WeatherAgent",
        ),
        instructions=instructions,
        tools=get_weather,
    )

    result = await agent.run("What's the weather like in New York?")
    print(f"Result: {result}\n")


async def example_3_with_existing_client() -> None:
    """Example 3: Using an existing AIProjectClient."""
    print("=== Example 3: With existing AIProjectClient ===")

    instructions = "You are a helpful weather assistant."

    # Create the client yourself
    client = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=AzureCliCredential())

    agent = ChatClientAgent(
        FoundryChatClient(
            client=client,
            model_deployment_name=os.environ["FOUNDRY_MODEL_DEPLOYMENT_NAME"],
            agent_name="WeatherAgent",
        ),
        instructions=instructions,
        tools=get_weather,
    )

    result = await agent.run("What's the weather like in London?")
    print(f"Result: {result}\n")


async def example_4_with_existing_agent() -> None:
    """Example 4: Using an existing agent."""
    print("=== Example 4: With existing agent ===")

    instructions = "You are a helpful weather assistant."

    # Create the client and agent yourself
    client = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=AzureCliCredential())

    # Create an agent that will persist
    created_agent = await client.agents.create_agent(
        model=os.environ["FOUNDRY_MODEL_DEPLOYMENT_NAME"], name="WeatherAgent"
    )

    try:
        agent = ChatClientAgent(
            FoundryChatClient(
                client=client,
                agent_id=created_agent.id,  # Use existing agent - won't be auto-deleted
            ),
            instructions=instructions,
            tools=get_weather,
        )

        result = await agent.run("What's the weather like in Tokyo?")
        print(f"Result: {result}\n")
    finally:
        # Clean up the agent manually since we created it
        await client.agents.delete_agent(created_agent.id)


async def main() -> None:
    # Run all examples
    await example_1_simplest()
    # await example_2_with_explicit_settings()
    # await example_3_with_existing_client()
    # await example_4_with_existing_agent()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
