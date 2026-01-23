# Copyright (c) Microsoft. All rights reserved.

"""
Github Copilot Agent with Shell Permissions

This sample demonstrates how to enable shell command execution with GithubCopilotAgent.
By setting allowed_permissions to include "shell", the agent can execute shell commands
to perform tasks like listing files, running scripts, or executing system commands.

SECURITY NOTE: Only enable shell permissions when you trust the agent's actions.
Shell commands have full access to your system within the permissions of the running process.
"""

import asyncio

from agent_framework.github_copilot import GithubCopilotAgent, GithubCopilotOptions


async def main() -> None:
    print("=== Github Copilot Agent with Shell Permissions ===\n")

    agent: GithubCopilotAgent[GithubCopilotOptions] = GithubCopilotAgent(
        instructions="You are a helpful assistant that can execute shell commands.",
        default_options={"allowed_permissions": ["shell"]},
    )

    async with agent:
        # Example: List files in current directory
        query = "List all Python files in the current directory"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

        # Example: Get system information
        query = "What is the current working directory?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
