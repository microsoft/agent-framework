# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with Multiple Permissions

This sample demonstrates how to enable multiple permission types with GitHubCopilotAgent.
By combining different permission kinds in the handler, the agent can perform complex tasks
that require multiple capabilities.

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

from agent_framework.github import GitHubCopilotAgent
from copilot.generated.session_events import PermissionRequest
from copilot.session import PermissionRequestResult


def prompt_permission(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that prompts the user for approval."""
    print(f"\n[Permission Request: {request.kind}]")

    if request.full_command_text is not None:
        print(f"  Command: {request.full_command_text}")
    if request.path is not None:
        print(f"  Path: {request.path}")

    response = input("Approve? (y/n): ").strip().lower()
    if response in ("y", "yes"):
        return PermissionRequestResult(kind="approved")
    return PermissionRequestResult(kind="denied-interactively-by-user")


async def main() -> None:
    print("=== GitHub Copilot Agent with Multiple Permissions ===\n")

    agent = GitHubCopilotAgent(
        instructions="You are a helpful development assistant that can read, write files and run commands.",
        default_options={"on_permission_request": prompt_permission},
    )

    async with agent:
        query = "List the first 3 Python files, then read the first one and create a summary in summary.txt"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
