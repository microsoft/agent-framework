# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with URL Fetching

This sample demonstrates how to enable URL fetching with GitHubCopilotAgent.
By providing a permission handler that approves "url" requests, the agent can
fetch and process content from web URLs.

SECURITY NOTE: Only enable URL permissions when you trust the agent's actions.
URL fetching allows the agent to access any URL accessible from your network.
"""

import asyncio

from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.types import PermissionRequest, PermissionRequestResult


def prompt_permission(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that prompts the user for approval."""
    kind = request.get("kind", "unknown")
    print(f"\n[Permission Request: {kind}]")

    if "url" in request:
        print(f"  URL: {request.get('url')}")

    response = input("Approve? (y/n): ").strip().lower()
    if response in ("y", "yes"):
        return PermissionRequestResult(kind="approved")
    return PermissionRequestResult(kind="denied-interactively-by-user")


async def main() -> None:
    print("=== GitHub Copilot Agent with URL Fetching ===\n")

    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        default_options={
            "instructions": "You are a helpful assistant that can fetch and summarize web content.",
            "on_permission_request": prompt_permission,
        },
    )

    async with agent:
        query = "Fetch https://learn.microsoft.com/agent-framework/tutorials/quick-start and summarize its contents"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
