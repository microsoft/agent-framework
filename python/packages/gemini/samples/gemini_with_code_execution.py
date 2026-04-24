# Copyright (c) Microsoft. All rights reserved.

"""Shows how to enable Gemini's built-in code execution tool.

Allows the model to write and run code in a sandboxed environment to answer questions.

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
    """Run the code execution example."""
    print("=== Code execution ===")

    # 1. Create the agent with Gemini and the built-in code execution tool.
    agent = Agent(
        client=GeminiChatClient(),
        name="CodeAgent",
        instructions="You are a helpful assistant. Use code execution to compute precise answers.",
        tools=[GeminiChatClient.get_code_interpreter_tool()],
    )

    # 2. Ask for a computed answer and stream the generated code and final result.
    query = "What are the first 20 prime numbers? Compute them in code."
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
=== Code execution ===
User: What are the first 20 prime numbers? Compute them in code.
Agent: The first 20 prime numbers are 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, and 71.
"""
