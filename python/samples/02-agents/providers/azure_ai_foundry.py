# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential

"""
Azure AI Foundry Provider

Demonstrates setting up AzureAIProjectAgentProvider and running a simple query.
This provider creates agents hosted in Azure AI Foundry projects.

Environment variables:
- AZURE_AI_PROJECT_ENDPOINT: Your Azure AI Foundry project endpoint
- AZURE_AI_MODEL_DEPLOYMENT_NAME: Model deployment name (e.g., "gpt-4o")

For more Azure AI Foundry examples:
- With tools: getting_started/agents/azure_ai/azure_ai_with_agent_as_tool.py
- With file search: getting_started/agents/azure_ai/azure_ai_with_file_search.py
- Docs: https://learn.microsoft.com/agent-framework/providers/azure-ai-foundry
"""


async def main() -> None:
    print("=== Azure AI Foundry Provider ===\n")

    # <create_agent>
    # For authentication, run `az login` or replace AzureCliCredential with your preferred credential.
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="FoundryAgent",
            instructions="You are a helpful assistant.",
        )
        # </create_agent>

        # <run_query>
        query = "What is the capital of France?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")
        # </run_query>


if __name__ == "__main__":
    asyncio.run(main())
