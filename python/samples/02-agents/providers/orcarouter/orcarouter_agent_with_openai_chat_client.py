# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
OrcaRouter with OpenAI Chat Completion Client Example

This sample demonstrates using OrcaRouter models through the OpenAI Chat
Completion client by pointing the base URL at the OrcaRouter gateway.
OrcaRouter is an OpenAI-compatible AI gateway for models and agents: like
OpenRouter it exposes a provider/model namespace across many models, but it
also combines adaptive routing, automatic failover, observability,
guardrails, and agent-tool governance behind the same endpoint.

Environment Variables:
- ORCAROUTER_API_KEY: Your OrcaRouter API key
- ORCAROUTER_BASE_URL: The OrcaRouter gateway base URL
  (e.g., "https://api.orcarouter.ai/v1")
- ORCAROUTER_MODEL: The model name to use (e.g., "orcarouter/fusion")
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


def _client() -> OpenAIChatCompletionClient:
    """Create an OpenAI Chat Completion client pointed at the OrcaRouter gateway."""
    return OpenAIChatCompletionClient(
        api_key=os.getenv("ORCAROUTER_API_KEY"),
        base_url=os.getenv("ORCAROUTER_BASE_URL", "https://api.orcarouter.ai/v1"),
        model=os.getenv("ORCAROUTER_MODEL", "orcarouter/fusion"),
    )


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    agent = Agent(
        client=_client(),
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    agent = Agent(
        client=_client(),
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    query = "What's the weather like in Portland?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== OrcaRouter with OpenAI Chat Completion Client Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
