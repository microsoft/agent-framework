# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent, HostedMCPTool
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv

"""
Hosted MCP Tools

Demonstrates using HostedMCPTool to connect to remote Model Context Protocol (MCP)
servers. The provider manages the MCP connection — you just provide the URL and
authentication headers.

This example connects to GitHub's MCP server using a Personal Access Token (PAT).

Prerequisites:
- GITHUB_PAT: GitHub Personal Access Token (https://github.com/settings/tokens)
- OPENAI_API_KEY: Your OpenAI API key

For more on MCP tools:
- Azure AI hosted MCP: getting_started/agents/azure_ai/azure_ai_with_hosted_mcp.py
- Local MCP tools: ./local_mcp_tools.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/mcp-tools
"""

load_dotenv()


async def main() -> None:
    print("=== Hosted MCP Tools (GitHub) ===\n")

    github_pat = os.getenv("GITHUB_PAT")
    if not github_pat:
        raise ValueError("GITHUB_PAT environment variable must be set.")

    # <create_mcp_tool>
    github_mcp_tool = HostedMCPTool(
        name="GitHub",
        description="Tool for interacting with GitHub.",
        url="https://api.githubcopilot.com/mcp/",
        headers={"Authorization": f"Bearer {github_pat}"},
        approval_mode="never_require",
    )
    # </create_mcp_tool>

    # <create_agent>
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        name="GitHubAgent",
        instructions=(
            "You are a helpful assistant that can interact with GitHub. "
            "You can search repositories, read files, check issues, and more."
        ),
        tools=github_mcp_tool,
    ) as agent:
        query = "What is my GitHub username?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}\n")

        query = "List my repositories"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}")
    # </create_agent>


if __name__ == "__main__":
    asyncio.run(main())
