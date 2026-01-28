# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with MCP Servers

This sample demonstrates how to configure MCP (Model Context Protocol) servers
with GitHubCopilotAgent. It shows both local (stdio) and remote (HTTP) server
configurations, giving the agent access to external tools and data sources.

SECURITY NOTE: MCP servers can expose powerful capabilities. Only configure
servers you trust. The permission handler below prompts the user for approval
of MCP-related actions.
"""

import asyncio

from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.types import MCPServerConfig, PermissionRequest, PermissionRequestResult


def prompt_permission(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that prompts the user for approval."""
    kind = request.get("kind", "unknown")
    print(f"\n[Permission Request: {kind}]")

    response = input("Approve? (y/n): ").strip().lower()
    if response in ("y", "yes"):
        return PermissionRequestResult(kind="approved")
    return PermissionRequestResult(kind="denied-interactively-by-user")


async def main() -> None:
    print("=== GitHub Copilot Agent with MCP Servers ===\n")

    # Configure both local and remote MCP servers
    mcp_servers: dict[str, MCPServerConfig] = {
        # Local stdio server: provides filesystem access tools
        "filesystem": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
            "tools": ["*"],
        },
        # Remote HTTP server: Microsoft Learn documentation
        "microsoft-learn": {
            "type": "http",
            "url": "https://learn.microsoft.com/api/mcp",
            "tools": ["*"],
        },
    }

    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        default_options={
            "instructions": "You are a helpful assistant with access to the local filesystem and Microsoft Learn.",
            "on_permission_request": prompt_permission,
            "mcp_servers": mcp_servers,
        },
    )

    async with agent:
        # Query that exercises the local filesystem MCP server
        query1 = "List the files in the current directory"
        print(f"User: {query1}")
        result1 = await agent.run(query1)
        print(f"Agent: {result1}\n")

        # Query that exercises the remote Microsoft Learn MCP server
        query2 = "Search Microsoft Learn for 'Azure Functions Python' and summarize the top result"
        print(f"User: {query2}")
        result2 = await agent.run(query2)
        print(f"Agent: {result2}\n")


if __name__ == "__main__":
    asyncio.run(main())
