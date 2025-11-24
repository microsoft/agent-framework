# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Existing Agent Example

This sample demonstrates working with pre-existing Azure AI Agents by providing
agent name and version, showing agent reuse patterns for production scenarios.
"""


async def main() -> None:
    # Create the client
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
    ):
        azure_ai_agent = await project_client.agents.create_version(
            agent_name="MyNewTestAgent",
            definition=PromptAgentDefinition(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                # Setting specific requirements to verify that this agent is used.
                instructions="End each response with [END].",
            ),
        )

        chat_client = AzureAIClient(
            project_client=project_client,
            agent_name=azure_ai_agent.name,
            # Property agent_version is required for existing agents.
            # If this property is not configured, the client will try to create a new agent using
            # provided agent_name.
            # It's also possible to leave agent_version empty but set use_latest_version=True.
            # This will pull latest available agent version and use that version for operations.
            agent_version=azure_ai_agent.version,
        )

        try:
            async with ChatAgent(
                chat_client=chat_client,
            ) as agent:
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


if __name__ == "__main__":
    asyncio.run(main())
