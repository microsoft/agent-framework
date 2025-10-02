# Copyright (c) Microsoft. All rights reserved.

import asyncio
from datetime import datetime

from agent_framework.ollama import OllamaChatClient

# Ensure to install Ollama and have a model running locally before running the sample
# Not all Models support function calling, to test function calling try llama3.2
# Set the model to use via the OLLAMA_CHAT_MODEL_ID environment variable or modify the code below.
# https://ollama.com/


def get_time(location: str) -> str:
    """Get the current time."""
    return f"The current time in {location} is {datetime.now().strftime('%I:%M %p')}."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    agent = OllamaChatClient().create_agent(
        name="TimeAgent",
        instructions="You are a helpful time agent answer in one sentence.",
        tools=get_time,
        request_kwargs={"think": True},  # Enable think to get reasoning on Agent Level
    )

    query = "What time is it in Seattle? Use a tool call"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    agent = OllamaChatClient().create_agent(
        name="TimeAgent",
        instructions="You are a helpful time agent answer in one sentence.",
        tools=get_time,
    )
    query = "What time is it in San Francisco? Use a tool call"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    # Enable Reasoning on per request level
    async for chunk in agent.run_stream(query, think=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== Basic Ollama Chat Client Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
