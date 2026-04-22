# Copyright (c) Microsoft. All rights reserved.

"""Shows how to enable extended thinking with ThinkingConfig.

Allows the model to reason through complex problems before responding.

Requires ``GOOGLE_MODEL`` or ``GEMINI_MODEL`` and either Gemini Developer API credentials
(``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``) or Vertex AI settings
(``GOOGLE_GENAI_USE_VERTEXAI``, ``GOOGLE_CLOUD_PROJECT``, and ``GOOGLE_CLOUD_LOCATION``).
"""

import asyncio

from agent_framework import Agent
from dotenv import load_dotenv

from agent_framework_gemini import GeminiChatClient, GeminiChatOptions, ThinkingConfig

load_dotenv()


async def main() -> None:
    """Example of extended thinking with a Python version comparison question."""
    print("=== Extended thinking ===")

    # 1. Configure Gemini extended thinking for a reasoning-heavy request.
    options: GeminiChatOptions = {
        "thinking_config": ThinkingConfig(thinking_budget=2048),
    }

    # 2. Create the agent with the Gemini chat client and default thinking options.
    agent = Agent(
        client=GeminiChatClient(),
        name="PythonAgent",
        instructions="You are a helpful Python expert.",
        default_options=options,
    )

    # 3. Stream the answer so you can see the final response as it arrives.
    query = "What new language features were introduced in Python between 3.10 and 3.14?"
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
=== Extended thinking ===
User: What new language features were introduced in Python between 3.10 and 3.14?
Agent: Python 3.11 introduced exception groups and TaskGroup.
Python 3.12 added PEP 695 type parameter syntax.
Python 3.13-3.14 continued improving typing, performance, and developer ergonomics.
"""
