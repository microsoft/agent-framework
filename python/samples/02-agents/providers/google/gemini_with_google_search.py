# Copyright (c) Microsoft. All rights reserved.

"""
Shows how to enable Google Search grounding so Gemini can retrieve up-to-date
information from the web before responding.

Requires the following environment variables to be set:
- GEMINI_API_KEY
- GEMINI_CHAT_MODEL_ID
"""

import asyncio

from agent_framework import Agent
from agent_framework_gemini import GeminiChatClient, GeminiChatOptions
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    print("=== Google Search grounding ===")

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
