# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent
from agent_framework_gemini import GeminiChatClient, GeminiChatOptions
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Gemini Google Search Grounding Example

This sample demonstrates Google Search grounding, which lets Gemini retrieve
up-to-date information from the web before responding.

Environment variables used:
- GEMINI_API_KEY
- GEMINI_CHAT_MODEL_ID (defaults to gemini-2.5-flash if unset)
"""


async def main() -> None:
    print("=== Google Search Grounding Example ===")

    options: GeminiChatOptions = {
        "google_search_grounding": True,
    }

    agent = Agent(
        client=GeminiChatClient(),
        name="SearchAgent",
        instructions="You are a helpful assistant. Use Google Search to provide accurate, up-to-date answers.",
        default_options=options,
    )

    query = "What is the latest stable release of the .NET SDK?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
