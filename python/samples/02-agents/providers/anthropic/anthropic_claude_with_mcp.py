# Copyright (c) Microsoft. All rights reserved.

"""
Claude Agent with MCP Servers

This sample demonstrates how to configure MCP (Model Context Protocol) servers
with ClaudeAgent. It shows both local (stdio) and remote (HTTP) server
configurations, giving the agent access to external tools and data sources.

Supported MCP server types:
- "stdio": Local process-based server
- "http": Remote HTTP server
- "sse": Remote SSE (Server-Sent Events) server

SECURITY NOTE: MCP servers can expose powerful capabilities. Only configure
servers you trust. Use permission handlers to control what actions are allowed.
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

    response = input("Approve? (y/n): ").strip().lower()
    if response in ("y", "yes"):
        return PermissionResultAllow()
    return PermissionResultDeny(message="Denied by user")


async def main() -> None:
    print("=== Claude Agent with MCP Servers ===\n")

    # Configure both local and remote MCP servers
    mcp_servers: dict[str, Any] = {
        # Local stdio server: provides filesystem access tools
        "filesystem": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        },
        # Remote HTTP server: Microsoft Learn documentation
        "microsoft-learn": {
            "type": "http",
            "url": "https://learn.microsoft.com/api/mcp",
        },
    }

    agent = ClaudeAgent(
        instructions="You are a helpful assistant with access to the local filesystem and Microsoft Learn.",
        default_options={
            "can_use_tool": prompt_permission,
            "mcp_servers": mcp_servers,
        },
    )

    async with agent:
        # Query that exercises the local filesystem MCP server
        query1 = "List the first three files in the current directory"
        print(f"User: {query1}")
        result1 = await agent.run(query1)
        print(f"Agent: {result1.text}\n")

        # Query that exercises the remote Microsoft Learn MCP server
        query2 = "Search Microsoft Learn for 'Azure Functions Python' and summarize the top result"
        print(f"User: {query2}")
        result2 = await agent.run(query2)
        print(f"Agent: {result2.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
