# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import HostedMCPTool, HostedWebSearchTool, TextReasoningContent, UsageContent
from agent_framework.anthropic import AnthropicClient

"""
Anthropic Chat Agent Example

This sample demonstrates using Anthropic with:
- Setting up an Anthropic-based agent with hosted tools.
- Using the `thinking` feature.
- Displaying both thinking and usage information during streaming responses.
"""


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    agent = AnthropicClient().create_agent(
        name="DocsAgent",
        instructions="You are a helpful agent for both Microsoft docs questions and general questions.",
        tools=[
            HostedMCPTool(
                name="Microsoft Learn MCP",
                url="https://learn.microsoft.com/api/mcp",
            ),
            HostedWebSearchTool(),
        ],
        # anthropic needs a value for the max_tokens parameter
        # we set it to 1024, but you can override like this:
        max_tokens=20000,
        additional_chat_options={"thinking": {"type": "enabled", "budget_tokens": 10000}},
    )

    query = "Can you compare Python decorators with C# attributes?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run_stream(query):
        for content in chunk.contents:
            if isinstance(content, TextReasoningContent):
                print(f"\033[32m{content.text}\033[0m", end="", flush=True)
            if isinstance(content, UsageContent):
                print(f"\n\033[34m[Usage so far: {content.details}]\033[0m\n", end="", flush=True)
        if chunk.text:
            print(chunk.text, end="", flush=True)

    print("\n")


async def main() -> None:
    print("=== Anthropic Example ===")

    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
