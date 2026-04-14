# Copyright (c) Microsoft. All rights reserved.

"""Shows how to enable Google Search grounding.

Allows Gemini to retrieve up-to-date information from the web before responding.

Requires ``GOOGLE_MODEL`` or ``GEMINI_MODEL`` and either Gemini Developer API credentials
(``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``) or Vertex AI settings
(``GOOGLE_GENAI_USE_VERTEXAI``, ``GOOGLE_CLOUD_PROJECT``, and ``GOOGLE_CLOUD_LOCATION``).
"""

import asyncio

from agent_framework import Agent
from dotenv import load_dotenv

from agent_framework_gemini import GeminiChatClient

load_dotenv()


async def main() -> None:
    """Run the Google Search grounding example."""
    print("=== Google Search grounding ===")

    # 1. Create the agent with Gemini and the built-in Google Search grounding tool.
    agent = Agent(
        client=GeminiChatClient(),
        name="SearchAgent",
        instructions="You are a helpful assistant. Use Google Search to provide accurate, up-to-date answers.",
        tools=[GeminiChatClient.get_web_search_tool()],
    )

    # 2. Ask a current-events style question and stream the grounded answer.
    query = "What is the latest stable release of the .NET SDK?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Google Search grounding ===
User: What is the latest stable release of the .NET SDK?
Agent: As of April 14, 2026, the latest stable release of the .NET SDK is .NET 10.0 (SDK 10.0.201).
"""
