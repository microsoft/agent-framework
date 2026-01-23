# Copyright (c) Microsoft. All rights reserved.

"""
Github Copilot Agent with File Operation Permissions

This sample demonstrates how to enable file read and write operations with GithubCopilotAgent.
By setting allowed_permissions to include "read" and/or "write", the agent can read from
and write to files on the filesystem.

SECURITY NOTE: Only enable file permissions when you trust the agent's actions.
- "read" allows the agent to read any accessible file
- "write" allows the agent to create or modify files
"""

import asyncio

from agent_framework.github_copilot import GithubCopilotAgent, GithubCopilotOptions


async def read_only_example() -> None:
    """Example with read-only file permissions."""
    print("=== Read-Only File Access Example ===\n")

    agent: GithubCopilotAgent[GithubCopilotOptions] = GithubCopilotAgent(
        instructions="You are a helpful assistant that can read files.",
        default_options={"allowed_permissions": ["read"]},
    )

    async with agent:
        query = "Read the contents of README.md and summarize it"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


async def read_write_example() -> None:
    """Example with both read and write file permissions."""
    print("=== Read and Write File Access Example ===\n")

    agent: GithubCopilotAgent[GithubCopilotOptions] = GithubCopilotAgent(
        instructions="You are a helpful assistant that can read and write files.",
        default_options={"allowed_permissions": ["read", "write"]},
    )

    async with agent:
        query = "Create a file called 'hello.txt' with the text 'Hello from Copilot!'"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


async def main() -> None:
    print("=== Github Copilot Agent with File Operation Permissions ===\n")

    await read_only_example()
    await read_write_example()


if __name__ == "__main__":
    asyncio.run(main())
