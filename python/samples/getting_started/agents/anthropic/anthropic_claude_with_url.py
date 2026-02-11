# Copyright (c) Microsoft. All rights reserved.

"""
Claude Agent with URL Fetching

This sample demonstrates how to enable URL fetching with ClaudeAgent.
By enabling the WebFetch tool, the agent can fetch and process content from web URLs.

Available web tools:
- "WebFetch": Fetch content from URLs
- "WebSearch": Search the web

SECURITY NOTE: Only enable URL permissions when you trust the agent's actions.
URL fetching allows the agent to access any URL accessible from your network.
"""

import asyncio

from agent_framework_claude import ClaudeAgent


async def main() -> None:
    print("=== Claude Agent with URL Fetching ===\n")

    agent = ClaudeAgent(
        instructions="You are a helpful assistant that can fetch and summarize web content.",
        tools=["WebFetch"],
    )

    async with agent:
        query = "Fetch https://learn.microsoft.com/agent-framework/tutorials/quick-start and summarize its contents"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
