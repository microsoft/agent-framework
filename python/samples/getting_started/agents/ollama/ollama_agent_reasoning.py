# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.ollama import OllamaChatClient

"""
Ollama Agent Reasoning Example

This sample demonstrates implementing a Ollama agent with reasoning.

Ensure to install Ollama and have a model running locally before running the sample
Not all Models support reasoning, to test reasoning try qwen3:8b
Set the model to use via the OLLAMA_CHAT_MODEL_ID environment variable or modify the code below.
https://ollama.com/

"""


async def reasoning_example() -> None:
    print("=== Response Reasoning Example ===")

    agent = OllamaChatClient().create_agent(
        name="TimeAgent",
        instructions="You are a helpful agent answer in one sentence.",
        additional_chat_options={"think": True},  # Enable Reasoning on agent level
    )
    query = "Hey what is 3+4? Can you explain how you got to that answer?"
    print(f"User: {query}")
    # Enable Reasoning on per request level
    result = await agent.run(query)
    print(f"Reasoning: {result.reasoning}")
    print(f"Answer: {result}\n")


async def main() -> None:
    print("=== Basic Ollama Chat Client Agent Reasoning ===")

    await reasoning_example()


if __name__ == "__main__":
    asyncio.run(main())
