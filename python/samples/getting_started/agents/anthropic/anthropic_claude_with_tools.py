# Copyright (c) Microsoft. All rights reserved.

"""
Claude Agent with Built-in Tools

This sample demonstrates using ClaudeAgent with built-in tools for file operations.
Built-in tools are specified as strings in the tools parameter.

Available built-in tools:
- "Bash": Execute shell commands
- "Read": Read files from the filesystem
- "Write": Write files to the filesystem
- "Edit": Edit existing files
- "Glob": Search for files by pattern
- "Grep": Search file contents
"""

import asyncio

from agent_framework_claude import ClaudeAgent


async def main() -> None:
    print("=== Claude Agent with Built-in Tools ===\n")

    # Built-in tools can be specified as strings in the tools parameter
    agent = ClaudeAgent(
        instructions="You are a helpful assistant that can read files.",
        tools=["Read", "Glob"],
    )

    async with agent:
        query = "List the first 3 Python files in the current directory"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
