# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.azure import AzureAIAgentsProvider
from azure.ai.agents.aio import AgentsClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Existing Agent Example

This sample demonstrates working with pre-existing Azure AI Agents by providing
agent IDs, showing agent reuse patterns for production scenarios.
"""


async def main() -> None:
    print("=== Azure AI Agent with Existing Agent ===")

    # Create the client and provider
    async with (
        AzureCliCredential() as credential,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
        AzureAIAgentsProvider(agents_client=agents_client) as provider,
    ):
        # Create an agent on the service with default instructions
        # These instructions will persist on created agent for every run.
        azure_ai_agent = await agents_client.create_agent(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            instructions="End each response with [END].",
        )

        try:
            # Wrap existing agent instance using provider.as_agent()
            agent = provider.as_agent(azure_ai_agent)

            query = "How are you?"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result}\n")
        finally:
            # Clean up the agent manually
            await agents_client.delete_agent(azure_ai_agent.id)


if __name__ == "__main__":
    asyncio.run(main())
