# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIAssistantsClient
from openai import AsyncOpenAI
from pydantic import Field

"""
OpenAI Assistants with Existing Assistant Example

This sample demonstrates how to use an existing OpenAI Assistant with the agent framework.
The example includes:

- Creating a new assistant programmatically with custom tools
- Connecting to existing assistants by ID for reuse
- Function calling with custom business logic
- Assistant lifecycle management and cleanup
- Integration with pre-configured OpenAI assistants

This approach is ideal for scenarios where you have pre-built assistants
with specific configurations, tools, and training that you want to reuse
across multiple agent framework applications.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== OpenAI Assistants Chat Client with Existing Assistant ===")

    # Create the client
    client = AsyncOpenAI()

    # Create an assistant that will persist
    created_assistant = await client.beta.assistants.create(
        model=os.environ["OPENAI_CHAT_MODEL_ID"], name="WeatherAssistant"
    )

    try:
        async with ChatAgent(
            chat_client=OpenAIAssistantsClient(async_client=client, assistant_id=created_assistant.id),
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        ) as agent:
            result = await agent.run("What's the weather like in Tokyo?")
            print(f"Result: {result}\n")
    finally:
        # Clean up the assistant manually
        await client.beta.assistants.delete(created_assistant.id)


if __name__ == "__main__":
    asyncio.run(main())
