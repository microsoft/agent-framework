# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
aimlapi.com Chat Completion Client Basic Example

This sample demonstrates using models served by aimlapi.com through
`OpenAIChatCompletionClient` by overriding the base URL. aimlapi.com exposes a plain
OpenAI Chat Completions endpoint, so no provider-specific client is needed — this is the
"base URL override" route described in `python/packages/openai/AGENTS.md`.

Shows both non-streaming and streaming responses.

Environment Variables:
- AIMLAPI_API_KEY: Your aimlapi.com API key (required). Create one at https://aimlapi.com/app/keys
- AIMLAPI_MODEL: The model id to use (optional, defaults to `openai/gpt-4o-mini`).
  Browse the catalog at https://api.aimlapi.com/v1/models
"""

# aimlapi.com speaks the OpenAI Chat Completions wire format at this base URL.
# Note: only `/v1/chat/completions` and `/v1/responses` exist — there is no `/v1/completions`.
AIMLAPI_BASE_URL = "https://api.aimlapi.com/v1"

# Default model id. Model ids are namespaced (`<vendor>/<model>`); the catalog at
# https://api.aimlapi.com/v1/models?include=all lists ids, aliases and capabilities.
AIMLAPI_DEFAULT_MODEL = "openai/gpt-4o-mini"

# Attribution headers understood by aimlapi.com. `HTTP-Referer` and `X-Title` follow the
# OpenRouter convention and identify the *calling* project (Agent Framework), while the two
# `X-AIMLAPI-*` headers identify the integration channel. They are passed as
# `default_headers` on the client, so they only ever ride requests to AIMLAPI_BASE_URL.
AIMLAPI_ATTRIBUTION_HEADERS = {
    "HTTP-Referer": "https://github.com/microsoft/agent-framework",
    "X-Title": "Microsoft Agent Framework",
    "X-AIMLAPI-Partner-ID": "part_agentframework",
    "X-AIMLAPI-Source": "agent/agent-framework",
}


def create_client() -> OpenAIChatCompletionClient:
    """Build a chat completion client pointed at aimlapi.com."""
    return OpenAIChatCompletionClient(
        model=os.environ.get("AIMLAPI_MODEL", AIMLAPI_DEFAULT_MODEL),
        api_key=os.environ["AIMLAPI_API_KEY"],
        base_url=AIMLAPI_BASE_URL,
        # A fresh dict per client: the module-level constant is never handed out or mutated.
        default_headers={**AIMLAPI_ATTRIBUTION_HEADERS},
    )


async def non_streaming_example() -> None:
    """Example of a non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    agent = Agent(
        client=create_client(),
        name="HaikuAgent",
        instructions="You are a concise assistant.",
    )

    query = "Why is the sky blue? Answer in one sentence."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def streaming_example() -> None:
    """Example of a streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    agent = Agent(
        client=create_client(),
        name="HaikuAgent",
        instructions="You are a concise assistant.",
    )

    query = "Name three primary colors."
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== aimlapi.com Chat Completion Client Agent Example ===\n")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
=== aimlapi.com Chat Completion Client Agent Example ===

=== Non-streaming Response Example ===
User: Why is the sky blue? Answer in one sentence.
Agent: The sky appears blue because molecules in Earth's atmosphere scatter shorter blue
wavelengths of sunlight more than longer wavelengths.

=== Streaming Response Example ===
User: Name three primary colors.
Agent: Red, blue, and yellow.
"""
