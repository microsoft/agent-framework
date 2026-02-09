# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.openai import OpenAIResponsesClient

"""
Step 1: Your First Agent

The simplest possible agent — send a message, get a response.
Uses Azure OpenAI Responses as the default provider.

Environment variables:
  OPENAI_API_KEY              — Your OpenAI API key
  OPENAI_RESPONSES_MODEL_ID   — Model to use (e.g. "gpt-4o")
  # Or for Azure OpenAI:
  AZURE_OPENAI_ENDPOINT       — Your Azure OpenAI endpoint
  AZURE_OPENAI_API_KEY        — Your Azure OpenAI key (or use Azure CLI auth)

For more on agents, see: ../02-agents/README.md
For docs: https://learn.microsoft.com/agent-framework/get-started/your-first-agent
"""


# <create_agent>
client = OpenAIResponsesClient(
    api_key=os.environ.get("OPENAI_API_KEY"),
    model_id=os.environ.get("OPENAI_RESPONSES_MODEL_ID", "gpt-4o"),
)
agent = client.as_agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
)
# </create_agent>


async def main():
    # <run_agent>
    response = await agent.run("What is the capital of France?")
    print(response)
    # </run_agent>

    # <run_agent_streaming>
    stream = agent.run("Tell me a fun fact about Paris.", stream=True)
    async for update in stream:
        print(update.text, end="")
    print()
    # </run_agent_streaming>


if __name__ == "__main__":
    asyncio.run(main())
