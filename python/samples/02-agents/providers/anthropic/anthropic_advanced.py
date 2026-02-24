# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.anthropic import AnthropicChatOptions, AnthropicClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Anthropic Chat Agent Example

This sample demonstrates using Anthropic with:
- Setting up an Anthropic-based agent with hosted tools.
- Using the `thinking` feature.
- Displaying both thinking and usage information during streaming responses.
"""


async def main() -> None:
    """Example of streaming response (get results as they are generated)."""
    client = AnthropicClient[AnthropicChatOptions]()

    # Create MCP tool configuration using instance method
    mcp_tool = client.get_mcp_tool(
        name="Microsoft_Learn_MCP",
        url="https://learn.microsoft.com/api/mcp",
    )

    # Create web search tool configuration using instance method
    web_search_tool = client.get_web_search_tool()

    agent = client.as_agent(
        name="DocsAgent",
        instructions="You are a helpful agent for both Microsoft docs questions and general questions.",
        tools=[mcp_tool, web_search_tool],
        default_options={
            # anthropic needs a value for the max_tokens parameter
            # we set it to 1024, but you can override like this:
            "max_tokens": 20000,
            "thinking": {"type": "enabled", "budget_tokens": 10000},
        },
    )

    query = "Can you compare Python decorators with C# attributes?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        for content in chunk.contents:
            if content.type == "text_reasoning" and content.text:
                print(f"\033[32m{content.text}\033[0m", end="", flush=True)
            if content.type == "usage":
                print(f"\n\033[34m[Usage so far: {content.usage_details}]\033[0m\n", end="", flush=True)
        if chunk.text:
            print(chunk.text, end="", flush=True)

    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
