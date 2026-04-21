# Copyright (c) Microsoft. All rights reserved.

"""Shows how to enable Google Maps grounding.

Allows Gemini to retrieve location and mapping information before responding.

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
    """Run the Google Maps grounding example."""
    print("=== Google Maps grounding ===")

    # 1. Create the agent with Gemini and the built-in Google Maps grounding tool.
    agent = Agent(
        client=GeminiChatClient(),
        name="MapsAgent",
        instructions="You are a helpful travel assistant. Use Google Maps to provide accurate location information.",
        tools=[GeminiChatClient.get_maps_grounding_tool()],
    )

    # 2. Ask a location-aware question and stream the grounded answer.
    query = "What are some highly rated restaurants in the city center of Karlsruhe, Germany?"
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
=== Google Maps grounding ===
User: What are some highly rated restaurants in the city center of Karlsruhe, Germany?
Agent: Here are several highly rated restaurants near Karlsruhe city center,
along with their cuisine styles and approximate walking distance.
"""
