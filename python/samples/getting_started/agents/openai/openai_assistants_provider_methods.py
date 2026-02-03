# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework.openai import OpenAIAssistantProvider
from openai import AsyncOpenAI
from pydantic import Field
from agent_framework import tool

"""
OpenAI Assistant Provider Methods Example

This sample demonstrates the methods available on the OpenAIAssistantProvider class:
- create_agent(): Create a new assistant on the service
- get_agent(): Retrieve an existing assistant by ID
- as_agent(): Wrap an SDK Assistant object without making HTTP calls
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}C."


async def create_agent_example() -> None:
    """Create a new assistant using provider.create_agent()."""
    print("\n--- create_agent() ---")

    async with (
        AsyncOpenAI() as client,
        OpenAIAssistantProvider(client) as provider,
    ):
        agent = await provider.create_agent(
            name="WeatherAssistant",
            model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            instructions="You are a helpful weather assistant.",
            tools=[get_weather],
        )

        try:
            print(f"Created: {agent.name} (ID: {agent.id})")
            result = await agent.run("What's the weather in Seattle?")
            print(f"Response: {result}")
        finally:
            await client.beta.assistants.delete(agent.id)


async def get_agent_example() -> None:
    """Retrieve an existing assistant by ID using provider.get_agent()."""
    print("\n--- get_agent() ---")

    async with (
        AsyncOpenAI() as client,
        OpenAIAssistantProvider(client) as provider,
    ):
        # Create an assistant directly with SDK (simulating pre-existing assistant)
        sdk_assistant = await client.beta.assistants.create(
            model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            name="ExistingAssistant",
            instructions="You always respond with 'Hello!'",
        )

        try:
            # Retrieve using provider
            agent = await provider.get_agent(sdk_assistant.id)
            print(f"Retrieved: {agent.name} (ID: {agent.id})")

            result = await agent.run("Hi there!")
            print(f"Response: {result}")
        finally:
            await client.beta.assistants.delete(sdk_assistant.id)


async def as_agent_example() -> None:
    """Wrap an SDK Assistant object using provider.as_agent()."""
    print("\n--- as_agent() ---")

    async with (
        AsyncOpenAI() as client,
        OpenAIAssistantProvider(client) as provider,
    ):
        # Create assistant using SDK
        sdk_assistant = await client.beta.assistants.create(
            model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            name="WrappedAssistant",
            instructions="You respond with poetry.",
        )

        try:
            # Wrap synchronously (no HTTP call)
            agent = provider.as_agent(sdk_assistant)
            print(f"Wrapped: {agent.name} (ID: {agent.id})")

            result = await agent.run("Tell me about the sunset.")
            print(f"Response: {result}")
        finally:
            await client.beta.assistants.delete(sdk_assistant.id)


async def multiple_agents_example() -> None:
    """Create and manage multiple assistants with a single provider."""
    print("\n--- Multiple Agents ---")

    async with (
        AsyncOpenAI() as client,
        OpenAIAssistantProvider(client) as provider,
    ):
        weather_agent = await provider.create_agent(
            name="WeatherSpecialist",
            model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            instructions="You are a weather specialist.",
            tools=[get_weather],
        )

        greeter_agent = await provider.create_agent(
            name="GreeterAgent",
            model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            instructions="You are a friendly greeter.",
        )

        try:
            print(f"Created: {weather_agent.name}, {greeter_agent.name}")

            greeting = await greeter_agent.run("Hello!")
            print(f"Greeter: {greeting}")

            weather = await weather_agent.run("What's the weather in Tokyo?")
            print(f"Weather: {weather}")
        finally:
            await client.beta.assistants.delete(weather_agent.id)
            await client.beta.assistants.delete(greeter_agent.id)


async def main() -> None:
    print("OpenAI Assistant Provider Methods")

    await create_agent_example()
    await get_agent_example()
    await as_agent_example()
    await multiple_agents_example()


if __name__ == "__main__":
    asyncio.run(main())
