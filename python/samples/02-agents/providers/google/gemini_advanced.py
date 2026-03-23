# Copyright (c) Microsoft. All rights reserved.

"""
Shows how to enable extended thinking with ThinkingConfig so the model can
reason through complex problems before responding.

Requires the following environment variables to be set:
- GEMINI_API_KEY
- GEMINI_CHAT_MODEL_ID
"""

import asyncio

from agent_framework import Agent
from agent_framework_gemini import GeminiChatClient, GeminiChatOptions, ThinkingConfig
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    """Example of extended thinking with a Python version comparison question."""
    print("=== Extended thinking ===")

    options: GeminiChatOptions = {
        "thinking_config": ThinkingConfig(thinking_budget=2048),
    }

    agent = Agent(
        client=GeminiChatClient(),
        name="PythonAgent",
        instructions="You are a helpful Python expert.",
        default_options=options,
    )

    query = "What new language features were introduced in Python between 3.10 and 3.14?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
