# Copyright (c) Microsoft. All rights reserved.

"""
Claude Agent with Multiple Permissions

This sample demonstrates how to enable multiple permission types with ClaudeAgent.
By combining different tools and using a permission handler, the agent can perform
complex tasks that require multiple capabilities.

Available built-in tools:
- "Bash": Execute shell commands
- "Read": Read files from the filesystem
- "Write": Write files to the filesystem
- "Edit": Edit existing files
- "Glob": Search for files by pattern
- "Grep": Search file contents

SECURITY NOTE: Only enable permissions that are necessary for your use case.
More permissions mean more potential for unintended actions.
"""

import asyncio
from typing import Any

from agent_framework_claude import ClaudeAgent
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny


async def prompt_permission(
    tool_name: str,
    tool_input: dict[str, Any],
    context: object,
) -> PermissionResultAllow | PermissionResultDeny:
    """Permission handler that prompts the user for approval."""
    print(f"\n[Permission Request: {tool_name}]")

    if "command" in tool_input:
        print(f"  Command: {tool_input.get('command')}")
    if "file_path" in tool_input:
        print(f"  Path: {tool_input.get('file_path')}")
    if "pattern" in tool_input:
        print(f"  Pattern: {tool_input.get('pattern')}")

    response = input("Approve? (y/n): ").strip().lower()
    if response in ("y", "yes"):
        return PermissionResultAllow()
    return PermissionResultDeny(message="Denied by user")


async def main() -> None:
    print("=== Claude Agent with Multiple Permissions ===\n")

    agent = ClaudeAgent(
        instructions="You are a helpful development assistant that can read, write files and run commands.",
        tools=["Bash", "Read", "Write", "Glob"],
        default_options={
            "can_use_tool": prompt_permission,
        },
    )

    async with agent:
        query = "List the first 3 Python files, then read the first one and create a summary in summary.txt"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
