# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent
from agent_framework_gemini import GeminiChatClient, GeminiChatOptions
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Gemini Google Maps Grounding Example

This sample demonstrates Google Maps grounding, which lets Gemini retrieve
location and mapping information from Google Maps before responding.

Environment variables used:
- GEMINI_API_KEY
- GEMINI_CHAT_MODEL_ID (defaults to gemini-2.5-flash if unset)
"""


async def main() -> None:
    print("=== Google Maps Grounding Example ===")

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
