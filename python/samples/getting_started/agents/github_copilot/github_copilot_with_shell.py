# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with Shell Permissions

This sample demonstrates how to enable shell command execution with GitHubCopilotAgent.
By providing a permission handler that approves "shell" requests, the agent can execute
shell commands to perform tasks like listing files, running scripts, or executing system commands.

SECURITY NOTE: Only enable shell permissions when you trust the agent's actions.
Shell commands have full access to your system within the permissions of the running process.
"""

import asyncio

from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.types import PermissionRequest, PermissionRequestResult


def prompt_permission(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that prompts the user for approval."""
    kind = request.get("kind", "unknown")
    print(f"\n[Permission Request: {kind}]")

    if "command" in request:
        print(f"  Command: {request.get('command')}")

    response = input("Approve? (y/n): ").strip().lower()
    if response in ("y", "yes"):
        return PermissionRequestResult(kind="approved")
    return PermissionRequestResult(kind="denied-interactively-by-user")


async def main() -> None:
    print("=== GitHub Copilot Agent with Shell Permissions ===\n")

    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        default_options={
            "instructions": "You are a helpful assistant that can execute shell commands.",
            "on_permission_request": prompt_permission,
        },
    )

    async with agent:
        query = "List the first 3 Python files in the current directory"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
