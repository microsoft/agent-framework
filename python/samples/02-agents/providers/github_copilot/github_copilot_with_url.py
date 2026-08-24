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
from copilot.generated.rpc import PermissionDecisionUserNotAvailable
from copilot.session import PermissionHandler, PermissionRequestResult
from copilot.session_events import PermissionRequest


def approve_and_log(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that approves only URL requests and logs them."""
    if request.kind == "url":
        print(f"\n  [Permission: {request.kind}]", flush=True)
        url = getattr(request, "url", None)
        if url is not None:
            print(f"  URL: {url}", flush=True)
        return PermissionHandler.approve_all(request, context)
    return PermissionDecisionUserNotAvailable()


async def main() -> None:
    print("=== GitHub Copilot Agent with URL Fetching ===\n")

    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions="You are a helpful assistant that can fetch and summarize web content.",
        default_options=GitHubCopilotOptions(on_permission_request=approve_and_log),
    )

    async with agent:
        query = "Fetch https://learn.microsoft.com/agent-framework/tutorials/quick-start and summarize its contents"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"\nAgent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
