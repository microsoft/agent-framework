# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with File Operation Permissions

This sample demonstrates how to enable file read and write operations with GitHubCopilotAgent.
By providing a permission handler that approves "read" and/or "write" requests, the agent can
read from and write to files on the filesystem.

SECURITY NOTE: Only enable file permissions when you trust the agent's actions.
- "read" allows the agent to read any accessible file
- "write" allows the agent to create or modify files
"""

import asyncio

from agent_framework.github import GitHubCopilotAgent
from copilot.generated.session_events import PermissionRequest
from copilot.session import PermissionRequestResult


def prompt_permission(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that prompts the user for approval."""
    print(f"\n[Permission Request: {request.kind}]")

    if request.path is not None:
        print(f"  Path: {request.path}")

    response = input("Approve? (y/n): ").strip().lower()
    if response in ("y", "yes"):
        return PermissionRequestResult(kind="approved")
    return PermissionRequestResult(kind="denied-interactively-by-user")


async def main() -> None:
    print("=== GitHub Copilot Agent with File Operation Permissions ===\n")

    agent = GitHubCopilotAgent(
        instructions="You are a helpful assistant that can read and write files.",
        default_options={"on_permission_request": prompt_permission},
    )

    async with agent:
        query = "Read the contents of README.md and summarize it"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
