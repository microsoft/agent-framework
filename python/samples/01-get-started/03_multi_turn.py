# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentThread
from agent_framework.openai import OpenAIResponsesClient

"""
Step 3: Multi-Turn Conversations

Use AgentThread to maintain conversation context across multiple exchanges.

For more on conversations, see: ../02-agents/conversations/
For docs: https://learn.microsoft.com/agent-framework/get-started/multi-turn
"""


# <create_agent>
agent = OpenAIResponsesClient().as_agent(
    name="Assistant",
    instructions="You are a helpful assistant. Be concise.",
)
# </create_agent>


async def main():
    # <multi_turn>
    thread = AgentThread()

    response = await agent.run("My name is Alice.", thread=thread)
    print(f"Agent: {response}")

    response = await agent.run("What's my name?", thread=thread)
    print(f"Agent: {response}")
    # </multi_turn>


if __name__ == "__main__":
    asyncio.run(main())
