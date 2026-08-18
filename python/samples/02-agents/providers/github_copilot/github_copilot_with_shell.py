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
from copilot.generated.rpc import PermissionDecisionUserNotAvailable
from copilot.session import PermissionHandler, PermissionRequestResult
from copilot.session_events import PermissionRequest


def approve_and_log(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that approves only shell commands and logs them."""
    if request.kind == "shell":
        print(f"\n  [Permission: {request.kind}]", flush=True)
        command = getattr(request, "full_command_text", None)
        if command is not None:
            print(f"  Command: {command}", flush=True)
        return PermissionHandler.approve_all(request, context)
    return PermissionDecisionUserNotAvailable()


async def main() -> None:
    print("=== GitHub Copilot Agent with Shell Permissions ===\n")

    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions="You are a helpful assistant that can execute shell commands.",
        default_options=GitHubCopilotOptions(on_permission_request=approve_and_log),
    )

    async with agent:
        query = "List the first 3 Python files in the current directory"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"\nAgent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
