# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with Multiple Permissions

This sample demonstrates how multiple permission types are requested when GitHubCopilotAgent
performs complex tasks that require different capabilities.

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

from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.session import PermissionHandler, PermissionRequestResult
from copilot.session_events import PermissionRequest


def approve_and_log(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that auto-approves and logs each permission kind."""
    print(f"  [Permission: {request.kind}]", flush=True)
    return PermissionHandler.approve_all(request, context)


async def main() -> None:
    print("=== GitHub Copilot Agent with Multiple Permissions ===\n")

    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions="You are a helpful development assistant that can read, write files and run commands.",
        default_options=GitHubCopilotOptions(on_permission_request=approve_and_log),
    )

    async with agent:
        query = "List the first 3 Python files, then read the first one and create a summary in summary.txt"
        print(f"User: {query}\n")
        result = await agent.run(query)
        print(f"\nAgent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
