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
OpenAI Assistants with Explicit Settings Example

This sample demonstrates creating OpenAI Assistants with explicit configuration
settings rather than relying on environment variable defaults.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}C."


async def main() -> None:
    print("=== OpenAI Assistants Provider with Explicit Settings ===")

    # Create client with explicit API key
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    provider = OpenAIAssistantProvider(client)

    agent = await provider.create_agent(
        name="WeatherAssistant",
        model=os.environ["OPENAI_CHAT_MODEL_ID"],
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    try:
        result = await agent.run("What's the weather like in New York?")
        print(f"Result: {result}\n")
    finally:
        await client.beta.assistants.delete(agent.id)


if __name__ == "__main__":
    asyncio.run(main())
