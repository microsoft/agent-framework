# Copyright (c) Microsoft. All rights reserved.

"""Shows how to enable Google Maps grounding.

Allows Gemini to retrieve location and mapping information before responding.

Requires the following environment variables to be set:
- GEMINI_API_KEY
- GEMINI_MODEL
"""

import asyncio

from agent_framework import Agent
from dotenv import load_dotenv

from agent_framework_gemini import GeminiChatClient, GeminiChatOptions

load_dotenv()


async def main() -> None:
    """Run the Google Maps grounding example."""
    print("=== Google Maps grounding ===")

    options: GeminiChatOptions = {
        "google_maps_grounding": True,
    }

    agent = Agent(
        client=GeminiChatClient(),
        name="MapsAgent",
        instructions="You are a helpful travel assistant. Use Google Maps to provide accurate location information.",
        default_options=options,
    )

    query = "What are some highly rated restaurants in the city center of Karlsruhe, Germany?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
