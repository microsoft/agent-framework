# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent, HostedMCPTool
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv

"""
MCP GitHub Integration with Personal Access Token (PAT)

This example demonstrates how to connect to GitHub's remote MCP server using a Personal Access
Token (PAT) for authentication. The agent can use GitHub operations like searching repositories,
reading files, creating issues, and more depending on how you scope your token.

Prerequisites:
1. A GitHub Personal Access Token with appropriate scopes
   - Create one at: https://github.com/settings/tokens
   - For read-only operations, you can use more restrictive scopes
2. Environment variables:
   - GITHUB_PAT: Your GitHub Personal Access Token (required)
   - OPENAI_API_KEY: Your OpenAI API key (required)
   - OPENAI_RESPONSES_MODEL_ID: Your OpenAI model ID (required)
"""


async def github_mcp_example() -> None:
    """Example of using GitHub MCP server with PAT authentication."""
    # 1. Load environment variables from .env file if present
    load_dotenv()

    # 2. Get configuration from environment
    github_pat = os.getenv("GITHUB_PAT")
    if not github_pat:
        raise ValueError(
            "GITHUB_PAT environment variable must be set. Create a token at https://github.com/settings/tokens"
        )

    # 3. Create authentication headers with GitHub PAT
    auth_headers = {
        "Authorization": f"Bearer {github_pat}",
    }

    # 4. Create MCP tool with authentication
    # HostedMCPTool manages the connection to the MCP server and makes its tools available
    # Set approval_mode="never_require" to allow the MCP tool to execute without approval
    github_mcp_tool = HostedMCPTool(
        name="GitHub",
        description="Tool for interacting with GitHub.",
        url="https://api.githubcopilot.com/mcp/",
        headers=auth_headers,
        approval_mode="never_require",
    )

    # 5. Create agent with the GitHub MCP tool
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        name="GitHubAgent",
        instructions=(
            "You are a helpful assistant that can help users interact with GitHub. "
            "You can search for repositories, read file contents, check issues, and more. "
            "Always be clear about what operations you're performing."
        ),
        tools=github_mcp_tool,
    ) as agent:
        # Example 1: Get authenticated user information
        query1 = "What is my GitHub username and tell me about my account?"
        print(f"\nUser: {query1}")
        result1 = await agent.run(query1)
        print(f"Agent: {result1.text}")

        # Example 2: List my repositories
        query2 = "List all the repositories I own on GitHub"
        print(f"\nUser: {query2}")
        result2 = await agent.run(query2)
        print(f"Agent: {result2.text}")


if __name__ == "__main__":
    asyncio.run(github_mcp_example())
