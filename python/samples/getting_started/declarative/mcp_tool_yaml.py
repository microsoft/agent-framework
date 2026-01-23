# Copyright (c) Microsoft. All rights reserved.

"""
MCP Tool via YAML Declaration

This sample demonstrates how to create agents with MCP (Model Context Protocol)
tools using YAML declarations and the declarative AgentFactory.

Key Features Demonstrated:
1. Loading agent definitions from YAML using AgentFactory
2. Configuring MCP tools with different authentication methods:
   - API key authentication (OpenAI.Responses provider)
   - Azure AI Foundry connection references (AzureAI.ProjectProvider)

Authentication Options:
- OpenAI.Responses: Supports inline API key auth via headers
- AzureAI.ProjectProvider: Uses Foundry connections for secure credential storage
  (no secrets passed in API calls - connection name references pre-configured auth)

Prerequisites:
- `pip install agent-framework-openai agent-framework-declarative --pre`
- For OpenAI example: Set OPENAI_API_KEY and GITHUB_PAT environment variables
- For Azure AI example: Set up a Foundry connection in your Azure AI project
"""

import asyncio

from agent_framework.declarative import AgentFactory
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Example 1: OpenAI.Responses with API key authentication
# Uses inline API key - suitable for OpenAI provider which supports headers
YAML_OPENAI_WITH_API_KEY = """
kind: Prompt
name: GitHubAgent
displayName: GitHub Assistant
description: An agent that can interact with GitHub using the MCP protocol
instructions: |
  You are a helpful assistant that can interact with GitHub.
  You can search for repositories, read file contents, and check issues.
  Always be clear about what operations you're performing.

model:
  id: gpt-4o
  provider: OpenAI.Responses  # Uses OpenAI's Responses API (requires OPENAI_API_KEY env var)

tools:
  - kind: mcp
    name: github-mcp
    description: GitHub MCP tool for repository operations
    url: https://api.githubcopilot.com/mcp/
    connection:
      kind: key
      apiKey: =Env.GITHUB_PAT  # PowerFx syntax to read from environment variable
    approvalMode: never
    allowedTools:
      - get_file_contents
      - get_me
      - search_repositories
      - search_code
      - list_issues
"""

# Example 2: Azure AI with Foundry connection reference
# No secrets in YAML - references a pre-configured Foundry connection by name
# The connection stores credentials securely in Azure AI Foundry
YAML_AZURE_AI_WITH_FOUNDRY_CONNECTION = """
kind: Prompt
name: GitHubAgent
displayName: GitHub Assistant
description: An agent that can interact with GitHub using the MCP protocol
instructions: |
  You are a helpful assistant that can interact with GitHub.
  You can search for repositories, read file contents, and check issues.
  Always be clear about what operations you're performing.

model:
  id: gpt-4o
  provider: AzureAI.ProjectProvider

tools:
  - kind: mcp
    name: github-mcp
    description: GitHub MCP tool for repository operations
    url: https://api.githubcopilot.com/mcp/
    connection:
      kind: remote
      authenticationMode: oauth
      name: github-mcp-oauth-connection  # References a Foundry connection
    approvalMode: never
    allowedTools:
      - get_file_contents
      - get_me
      - search_repositories
      - search_code
      - list_issues
"""


async def run_openai_example():
    """Run the OpenAI.Responses example with API key auth."""
    print("=" * 60)
    print("Example 1: OpenAI.Responses with API Key Authentication")
    print("=" * 60)

    factory = AgentFactory(
        safe_mode=False,  # Allow PowerFx env var resolution (=Env.VAR_NAME)
    )

    print("\nCreating agent from YAML definition...")
    agent = factory.create_agent_from_yaml(YAML_OPENAI_WITH_API_KEY)

    async with agent:
        query = "What is my GitHub username?"
        print(f"\nUser: {query}")
        response = await agent.run(query)
        print(f"\nAgent: {response.text}")


async def run_azure_ai_example():
    """Run the Azure AI example with Foundry connection.

    Prerequisites:
    1. Create a Foundry connection named 'github-mcp-oauth-connection' in your
       Azure AI project with OAuth credentials for GitHub
    2. Set PROJECT_ENDPOINT environment variable to your Azure AI project endpoint
    """
    print("=" * 60)
    print("Example 2: Azure AI with Foundry Connection Reference")
    print("=" * 60)

    from azure.identity import DefaultAzureCredential

    factory = AgentFactory(client_kwargs={"credential": DefaultAzureCredential()})

    print("\nCreating agent from YAML definition...")
    # Use async method for provider-based agent creation
    agent = await factory.create_agent_from_yaml_async(YAML_AZURE_AI_WITH_FOUNDRY_CONNECTION)

    async with agent:
        query = "What is my GitHub username?"
        print(f"\nUser: {query}")
        response = await agent.run(query)
        print(f"\nAgent: {response.text}")


async def main():
    """Run the MCP tool examples."""
    # Run the OpenAI example
    await run_openai_example()

    # Run the Azure AI example (uncomment to run)
    # Requires: Foundry connection set up and PROJECT_ENDPOINT env var
    # await run_azure_ai_example()


if __name__ == "__main__":
    asyncio.run(main())
