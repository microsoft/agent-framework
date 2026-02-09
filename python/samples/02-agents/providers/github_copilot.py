# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.github import GitHubCopilotAgent

"""
GitHub Copilot Provider

Demonstrates setting up GitHubCopilotAgent and running a simple query.
Uses the GitHub Copilot CLI for authentication and model access.

Environment variables (optional):
- GITHUB_COPILOT_CLI_PATH: Path to Copilot CLI executable
- GITHUB_COPILOT_MODEL: Model to use (e.g., "gpt-5", "claude-sonnet-4")
- GITHUB_COPILOT_TIMEOUT: Request timeout in seconds

For more GitHub Copilot examples:
- With tools: getting_started/agents/github_copilot/github_copilot_with_file_operations.py
- With MCP: getting_started/agents/github_copilot/github_copilot_with_mcp.py
- Docs: https://learn.microsoft.com/agent-framework/providers/github-copilot
"""


async def main() -> None:
    print("=== GitHub Copilot Provider ===\n")

    # <create_agent>
    agent = GitHubCopilotAgent(
        instructions="You are a helpful assistant.",
    )
    # </create_agent>

    # <run_query>
    async with agent:
        query = "What is the capital of France?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")
    # </run_query>


if __name__ == "__main__":
    asyncio.run(main())
