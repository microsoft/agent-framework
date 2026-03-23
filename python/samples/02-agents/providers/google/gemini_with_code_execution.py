# Copyright (c) Microsoft. All rights reserved.

"""
Shows how to enable Gemini's built-in code execution tool so the model can write
and run code in a sandboxed environment to answer questions.

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
    print("=== Code execution ===")

    options: GeminiChatOptions = {
        "code_execution": True,
    }

    agent = Agent(
        client=GeminiChatClient(),
        name="CodeAgent",
        instructions="You are a helpful assistant. Use code execution to compute precise answers.",
        default_options=options,
    )

    query = "What are the first 20 prime numbers? Compute them in code."
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
