# Copyright (c) Microsoft. All rights reserved.

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from agent_framework import Agent, tool
from agent_framework.mistral import MistralChatClient
from dotenv import load_dotenv

# Load environment variables from the local .env file.
load_dotenv()

"""Demonstrates a Mistral AI agent with basic tool usage.

Requires ``MISTRAL_API_KEY`` and ``MISTRAL_CHAT_MODEL`` environment variables
(e.g. MISTRAL_CHAT_MODEL=mistral-small-latest).
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_time(timezone: str) -> str:
    """Get the current time in an IANA timezone (e.g. 'America/Los_Angeles')."""
    now = datetime.now(ZoneInfo(timezone))
    return f"The current time in {timezone} is {now.strftime('%I:%M %p')}."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    client = MistralChatClient()
    agent = Agent(
        client=client,
        name="TimeAgent",
        instructions="You are a helpful time agent, answer in one sentence.",
        tools=get_time,
    )

    query = "What time is it in Seattle? Use a tool call"
    print(f"User: {query}")
    try:
        result = await agent.run(query)
        print(f"Result: {result}\n")
    finally:
        await client.close()


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    client = MistralChatClient()
    agent = Agent(
        client=client,
        name="TimeAgent",
        instructions="You are a helpful time agent, answer in one sentence.",
        tools=get_time,
    )
    query = "What time is it in San Francisco? Use a tool call"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    try:
        async for chunk in agent.run(query, stream=True):
            if chunk.text:
                print(chunk.text, end="", flush=True)
        print("\n")
    finally:
        await client.close()


async def main() -> None:
    print("=== Basic Mistral Chat Client Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Basic Mistral Chat Client Agent Example ===
=== Non-streaming Response Example ===
User: What time is it in Seattle? Use a tool call
Result: The current time in Seattle is 10:30 AM.

=== Streaming Response Example ===
User: What time is it in San Francisco? Use a tool call
Agent: The current time in San Francisco is 10:30 AM.
"""
