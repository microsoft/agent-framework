# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from httpx import AsyncClient

"""
MCP GitHub Integration with Personal Access Token (PAT) using Azure OpenAI Chat Client

This example demonstrates how to connect to GitHub's remote MCP server using a Personal Access
Token (PAT) for authentication with Azure OpenAI Chat Client. The agent can use GitHub operations
like searching repositories, reading files, creating issues, and more depending on how you scope
your token.

Prerequisites:
1. A GitHub Personal Access Token with appropriate scopes
   - Create one at: https://github.com/settings/tokens
   - For read-only operations, you can use more restrictive scopes
2. Environment variables:
   - GITHUB_PAT: Your GitHub Personal Access Token (required)
   - AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint (required)
   - AZURE_OPENAI_CHAT_DEPLOYMENT_NAME: Your Azure OpenAI chat deployment name (required)
   - Or use Azure CLI credential for authentication (run `az login`)
"""


async def github_mcp_example() -> None:
    """Example of using GitHub MCP server with PAT authentication and Azure OpenAI Chat Client."""
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

    # 4. Create HTTP client with authentication headers
    http_client = AsyncClient(headers=auth_headers)

    # 5. Create Azure OpenAI Chat Client
    # For authentication, run `az login` command in terminal or replace AzureCliCredential
    # with your preferred authentication option (e.g., api_key parameter)
    client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # 6. Create MCP tool for GitHub with PAT authentication
    # The MCPStreamableHTTPTool manages the connection to the MCP server and makes its tools available
    async with MCPStreamableHTTPTool(
        name="GitHub",
        description="GitHub MCP server for interacting with GitHub repositories, issues, and more",
        url="https://api.githubcopilot.com/mcp/",
        http_client=http_client,  # Pass HTTP client with authentication headers
        approval_mode="never_require",  # For sample brevity; use "always_require" in production
    ) as github_mcp_tool:
        # 7. Create agent with the GitHub MCP tool
        agent = client.as_agent(
            instructions=(
                "You are a helpful assistant that can help users interact with GitHub. "
                "You can search for repositories, read file contents, check issues, and more. "
                "Always be clear about what operations you're performing."
            ),
            tools=github_mcp_tool,
        )

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
