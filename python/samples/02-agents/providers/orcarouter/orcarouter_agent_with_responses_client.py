# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
OrcaRouter with OpenAI Responses Chat Client Example

This sample demonstrates using OrcaRouter models through the OpenAI Responses
client by pointing the base URL at the OrcaRouter gateway. In addition to the
OpenAI-compatible Chat Completions API, the gateway also exposes the Responses
API (``/responses``) behind the same endpoint, so ``OpenAIChatClient`` can be
used directly with OrcaRouter.

Environment Variables:
- ORCAROUTER_API_KEY: Your OrcaRouter API key
- ORCAROUTER_BASE_URL: The OrcaRouter gateway base URL
  (e.g., "https://api.orcarouter.ai/v1")
- ORCAROUTER_MODEL: The model name to use (e.g., "orcarouter/fusion")
"""


def _client() -> OpenAIChatClient:
    """Create an OpenAI Responses client pointed at the OrcaRouter gateway."""
    return OpenAIChatClient(
        api_key=os.getenv("ORCAROUTER_API_KEY"),
        base_url=os.getenv("ORCAROUTER_BASE_URL", "https://api.orcarouter.ai/v1"),
        model=os.getenv("ORCAROUTER_MODEL", "orcarouter/fusion"),
    )


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    agent = Agent(
        client=_client(),
        name="Assistant",
        instructions="You are a helpful assistant.",
    )

    query = "What is the capital of France?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    agent = Agent(
        client=_client(),
        name="Assistant",
        instructions="You are a helpful assistant.",
    )

    query = "Write a haiku about the ocean."
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== OrcaRouter with OpenAI Responses Chat Client Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
