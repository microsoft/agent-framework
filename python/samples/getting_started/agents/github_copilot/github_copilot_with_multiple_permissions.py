# Copyright (c) Microsoft. All rights reserved.

"""
Github Copilot Agent with Multiple Permissions

This sample demonstrates how to enable multiple permission types with GithubCopilotAgent.
By combining different permission kinds, the agent can perform complex tasks that require
multiple capabilities.

Available permission kinds:
- "shell": Execute shell commands
- "read": Read files from the filesystem
- "write": Write files to the filesystem
- "mcp": Use MCP (Model Context Protocol) servers
- "url": Fetch content from URLs

SECURITY NOTE: Only enable permissions that are necessary for your use case.
More permissions mean more potential for unintended actions.
"""

import asyncio

from agent_framework.github_copilot import GithubCopilotAgent, GithubCopilotOptions


async def main() -> None:
    print("=== Github Copilot Agent with Multiple Permissions ===\n")

    # Enable shell, read, and write permissions for a development assistant
    agent: GithubCopilotAgent[GithubCopilotOptions] = GithubCopilotAgent(
        instructions="You are a helpful development assistant that can read, write files and run commands.",
        default_options={"allowed_permissions": ["shell", "read", "write"]},
    )

    async with agent:
        # Complex task that requires multiple permissions
        query = "List all Python files, then read the first one and create a summary in summary.txt"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
