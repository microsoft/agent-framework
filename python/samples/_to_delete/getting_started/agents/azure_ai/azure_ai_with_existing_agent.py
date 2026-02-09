# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Existing Agent Example

This sample demonstrates working with pre-existing Azure AI Agents by using provider.get_agent() method,
showing agent reuse patterns for production scenarios.
"""


async def using_provider_get_agent() -> None:
    print("=== Get existing Azure AI agent with provider.get_agent() ===")

    # Create the client
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
    ):
        # Create remote agent using SDK directly
        azure_ai_agent = await project_client.agents.create_version(
            agent_name="MyNewTestAgent",
            description="Agent for testing purposes.",
            definition=PromptAgentDefinition(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                # Setting specific requirements to verify that this agent is used.
                instructions="End each response with [END].",
            ),
        )

        try:
            # Get newly created agent as ChatAgent by using provider.get_agent()
            provider = AzureAIProjectAgentProvider(project_client=project_client)
            agent = await provider.get_agent(name=azure_ai_agent.name)

            # Verify agent properties
            print(f"Agent ID: {agent.id}")
            print(f"Agent name: {agent.name}")
            print(f"Agent description: {agent.description}")

            query = "How are you?"
            print(f"User: {query}")
            result = await agent.run(query)
            # Response that indicates that previously created agent was used:
            # "I'm here and ready to help you! How can I assist you today? [END]"
            print(f"Agent: {result}\n")
        finally:
            # Clean up the agent manually
            await project_client.agents.delete_version(
                agent_name=azure_ai_agent.name, agent_version=azure_ai_agent.version
            )


async def main() -> None:
    await using_provider_get_agent()


if __name__ == "__main__":
    asyncio.run(main())
