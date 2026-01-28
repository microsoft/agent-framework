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
OpenAI Assistants with Existing Assistant Example

This sample demonstrates working with pre-existing OpenAI Assistants
using the provider's get_agent() and as_agent() methods.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}C."


async def example_get_agent_by_id() -> None:
    """Example: Using get_agent() to retrieve an existing assistant by ID."""
    print("=== Get Existing Assistant by ID ===")

    client = AsyncOpenAI()
    provider = OpenAIAssistantProvider(client)

    # Create an assistant via SDK (simulating an existing assistant)
    created_assistant = await client.beta.assistants.create(
        model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
        name="WeatherAssistant",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the weather for a given location.",
                    "parameters": {
                        "type": "object",
                        "properties": {"location": {"type": "string", "description": "The location"}},
                        "required": ["location"],
                    },
                },
            }
        ],
    )
    print(f"Created assistant: {created_assistant.id}")

    try:
        # Use get_agent() to retrieve the existing assistant
        agent = await provider.get_agent(
            assistant_id=created_assistant.id,
            tools=[get_weather],  # Required: implementation for function tools
            instructions="You are a helpful weather agent.",
        )

        result = await agent.run("What's the weather like in Tokyo?")
        print(f"Agent: {result}\n")
    finally:
        await client.beta.assistants.delete(created_assistant.id)
        print("Assistant deleted.\n")


async def example_as_agent_wrap_sdk_object() -> None:
    """Example: Using as_agent() to wrap an existing SDK Assistant object."""
    print("=== Wrap Existing SDK Assistant Object ===")

    client = AsyncOpenAI()
    provider = OpenAIAssistantProvider(client)

    # Create and fetch an assistant via SDK
    created_assistant = await client.beta.assistants.create(
        model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
        name="SimpleAssistant",
        instructions="You are a friendly assistant.",
    )
    print(f"Created assistant: {created_assistant.id}")

    try:
        # Use as_agent() to wrap the SDK object
        agent = provider.as_agent(
            created_assistant,
            instructions="You are an extremely helpful assistant. Be enthusiastic!",
        )

        result = await agent.run("Hello! What can you help me with?")
        print(f"Agent: {result}\n")
    finally:
        await client.beta.assistants.delete(created_assistant.id)
        print("Assistant deleted.\n")


async def main() -> None:
    print("=== OpenAI Assistants Provider with Existing Assistant Examples ===\n")

    await example_get_agent_by_id()
    await example_as_agent_wrap_sdk_object()


if __name__ == "__main__":
    asyncio.run(main())
