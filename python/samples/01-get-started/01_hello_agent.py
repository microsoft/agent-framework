# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.openai import OpenAIResponsesClient

"""
Step 1: Your First Agent

The simplest possible agent — send a message, get a response.
Uses Azure OpenAI Responses as the default provider.

For more on agents, see: ../02-agents/README.md
For docs: https://learn.microsoft.com/agent-framework/get-started/your-first-agent
"""


# <create_agent>
agent = OpenAIResponsesClient().as_agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
)
# </create_agent>


async def main():
    # <run_agent>
    response = await agent.run("What is the capital of France?")
    print(response)
    # </run_agent>


if __name__ == "__main__":
    asyncio.run(main())
