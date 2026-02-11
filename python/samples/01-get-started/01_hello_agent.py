# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.openai import OpenAIResponsesClient

"""
Hello Agent — Simplest possible agent

This sample creates a minimal agent using OpenAIResponsesClient and runs it
in both non-streaming and streaming modes.
"""


async def main() -> None:
    # <create_agent>
    client = OpenAIResponsesClient(
        api_key=os.environ["OPENAI_API_KEY"],
        model_id=os.environ.get("OPENAI_RESPONSES_MODEL_ID", "gpt-4o"),
    )

    agent = client.as_agent(
        name="HelloAgent",
        instructions="You are a friendly assistant. Keep your answers brief.",
    )
    # </create_agent>

    # <run_agent>
    # Non-streaming: get the complete response at once
    result = await agent.run("What is the capital of France?")
    print(f"Agent: {result}")
    # </run_agent>

    # <run_agent_streaming>
    # Streaming: receive tokens as they are generated
    print("Agent (streaming): ", end="", flush=True)
    async for chunk in agent.run("Tell me a one-sentence fun fact.", stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()
    # </run_agent_streaming>


if __name__ == "__main__":
    asyncio.run(main())
