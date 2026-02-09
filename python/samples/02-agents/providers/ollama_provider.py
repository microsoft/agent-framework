# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.ollama import OllamaChatClient

"""
Ollama Provider (Local Models)

Demonstrates setting up OllamaChatClient and running a simple query against
a locally running Ollama instance.

Prerequisites:
- Install Ollama: https://ollama.com/
- Pull a model: `ollama pull llama3.2`
- Ollama server running locally

Environment variables:
- OLLAMA_MODEL_ID: Model to use (default: llama3.2)

For more Ollama examples:
- With reasoning: getting_started/agents/ollama/ollama_agent_reasoning.py
- Multimodal: getting_started/agents/ollama/ollama_chat_multimodal.py
- Docs: https://learn.microsoft.com/agent-framework/providers/ollama
"""


async def main() -> None:
    print("=== Ollama Provider (Local) ===\n")

    # <create_agent>
    agent = OllamaChatClient().as_agent(
        name="OllamaAgent",
        instructions="You are a helpful assistant. Answer in one sentence.",
    )
    # </create_agent>

    # <run_query>
    query = "What is the capital of France?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}")
    # </run_query>


if __name__ == "__main__":
    asyncio.run(main())
