# Copyright (c) Microsoft. All rights reserved.

"""
Claude Agent with Shell Permissions

This sample demonstrates how to enable shell command execution with ClaudeAgent.
By providing a permission handler via `can_use_tool`, the agent can execute
shell commands to perform tasks like listing files, running scripts, or executing system commands.

SECURITY NOTE: Only enable shell permissions when you trust the agent's actions.
Shell commands have full access to your system within the permissions of the running process.
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

    response = input("Approve? (y/n): ").strip().lower()
    if response in ("y", "yes"):
        return PermissionResultAllow()
    return PermissionResultDeny(message="Denied by user")


async def main() -> None:
    print("=== Claude Agent with Shell Permissions ===\n")

    agent = ClaudeAgent(
        instructions="You are a helpful assistant that can execute shell commands.",
        tools=["Bash"],
        default_options={
            "can_use_tool": prompt_permission,
        },
    )

    async with agent:
        query = "List the first 3 Python files in the current directory"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
