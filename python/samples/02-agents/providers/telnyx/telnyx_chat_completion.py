# Copyright (c) Microsoft. All rights reserved.

"""Telnyx Chat Completion Example

This sample demonstrates using Telnyx as an OpenAI-compatible inference
provider through the OpenAIChatClient by configuring the base_url to
point to the Telnyx AI API endpoint.

Telnyx provides an OpenAI-compatible API at https://api.telnyx.com/v2/ai/openai
that supports chat completions, embeddings, and function/tool calling.

Environment Variables:
    TELNYX_API_KEY   — Your Telnyx API key (from https://portal.telnyx.com/)
    TELNYX_MODEL     — Model name to use (default: "Kimi-K2.5")
                       Available models include: Kimi-K2.5, GLM-5.1-FP8,
                       MiniMax-M2.7, Qwen3-235B-A22B
"""

import asyncio
import os

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    # 1. Configure the OpenAI client to use Telnyx as the backend.
    client = OpenAIChatClient(
        api_key=os.getenv("TELNYX_API_KEY"),
        base_url="https://api.telnyx.com/v2/ai/openai",
        model=os.getenv("TELNYX_MODEL", "Kimi-K2.5"),
    )

    # 2. Create an agent that uses the Telnyx-backed client.
    agent = Agent(
        client=client,
        name="TelnyxAgent",
        instructions="You are a helpful assistant.",
    )

    # 3. Send a message and wait for the full response.
    query = "What is the capital of France?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    # 1. Configure the OpenAI client to use Telnyx as the backend.
    client = OpenAIChatClient(
        api_key=os.getenv("TELNYX_API_KEY"),
        base_url="https://api.telnyx.com/v2/ai/openai",
        model=os.getenv("TELNYX_MODEL", "Kimi-K2.5"),
    )

    # 2. Create an agent that uses the Telnyx-backed client.
    agent = Agent(
        client=client,
        name="TelnyxAgent",
        instructions="You are a helpful assistant.",
    )

    # 3. Send a message and stream the response token by token.
    query = "Explain quantum computing in one paragraph."
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== Telnyx Chat Completion Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

=== Telnyx Chat Completion Agent Example ===
=== Non-streaming Response Example ===
User: What is the capital of France?
Agent: The capital of France is Paris.

=== Streaming Response Example ===
User: Explain quantum computing in one paragraph.
Agent: Quantum computing is a type of computation that harnesses quantum-mechanical
phenomena, such as superposition and entanglement, to process information in ways that
classical computers cannot...
"""
