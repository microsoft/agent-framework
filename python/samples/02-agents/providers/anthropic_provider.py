# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.anthropic import AnthropicClient

"""
Anthropic Provider

Demonstrates setting up AnthropicClient and running a simple query.

Environment variables:
- ANTHROPIC_API_KEY: Your Anthropic API key

For more Anthropic examples:
- With tools: getting_started/agents/anthropic/anthropic_claude_with_tools.py
- With MCP: getting_started/agents/anthropic/anthropic_claude_with_mcp.py
- Docs: https://learn.microsoft.com/agent-framework/providers/anthropic
"""


async def main() -> None:
    print("=== Anthropic Provider ===\n")

    # <create_agent>
    agent = AnthropicClient().as_agent(
        name="ClaudeAgent",
        instructions="You are a helpful assistant.",
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
