# Copyright (c) Microsoft. All rights reserved.

"""Shows how to use GeminiChatClient with an agent and a custom tool.

Covers both non-streaming and streaming responses.

Requires ``GOOGLE_MODEL`` or ``GEMINI_MODEL`` and either Gemini Developer API credentials
(``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``) or Vertex AI settings
(``GOOGLE_GENAI_USE_VERTEXAI``, ``GOOGLE_CLOUD_PROJECT``, and ``GOOGLE_CLOUD_LOCATION``).
"""

import asyncio
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from dotenv import load_dotenv

from agent_framework_gemini import GeminiChatClient

load_dotenv()


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example() -> None:
    """Runs the agent and waits for the complete response before printing it."""
    print("=== Non-streaming ===")

    # 1. Create the agent with the Gemini chat client and local weather tool.
    agent = Agent(
        client=GeminiChatClient(),
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    # 2. Ask the agent for a single weather lookup and print the final response.
    query = "What's the weather like in Karlsruhe, Germany?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")


async def streaming_example() -> None:
    """Runs the agent and prints each chunk as it is received."""
    print("=== Streaming ===")

    # 1. Create the same agent configuration for a streaming tool-call example.
    agent = Agent(
        client=GeminiChatClient(),
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    # 2. Ask a multi-location question and stream the model output as it arrives.
    query = "What's the weather like in Portland and in Paris?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    """Run non-streaming and streaming examples."""
    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Non-streaming ===
User: What's the weather like in Karlsruhe, Germany?
Result: The weather in Karlsruhe, Germany is currently sunny with a high of 16°C.

=== Streaming ===
User: What's the weather like in Portland and in Paris?
Agent: In Portland, it is currently rainy with a high of 11°C. In Paris, it is cloudy with a high of 27°C.
"""
