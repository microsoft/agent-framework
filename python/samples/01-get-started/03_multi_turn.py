# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.openai import OpenAIResponsesClient

"""
Multi-Turn Conversations — Use AgentThread to maintain context

This sample shows how to keep conversation history across multiple calls
by reusing the same thread object.
"""


async def main() -> None:
    # <create_agent>
    client = OpenAIResponsesClient(
        api_key=os.environ["OPENAI_API_KEY"],
        model_id=os.environ.get("OPENAI_RESPONSES_MODEL_ID", "gpt-4o"),
    )

    agent = client.as_agent(
        name="ConversationAgent",
        instructions="You are a friendly assistant. Keep your answers brief.",
    )
    # </create_agent>

    # <multi_turn>
    # Create a thread to maintain conversation history
    thread = agent.get_new_thread()

    # First turn
    result = await agent.run("My name is Alice and I love hiking.", thread=thread)
    print(f"Agent: {result}\n")

    # Second turn — the agent should remember the user's name and hobby
    result = await agent.run("What do you remember about me?", thread=thread)
    print(f"Agent: {result}")
    # </multi_turn>


if __name__ == "__main__":
    asyncio.run(main())
