# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentProvider, get_agent
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Existing Agent Example

This sample demonstrates working with pre-existing Azure AI Agents by using get_agent method
and AzureAIAgentProvider class, showing agent reuse patterns for production scenarios.
"""


async def using_method() -> None:
    print("=== Get existing Azure AI agent with get_agent method ===")

    # Create the client
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
    ):
        # Create remote agent
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
            # Get newly created agent as ChatAgent by using get_agent method
            agent: ChatAgent = await get_agent(project_client=project_client, agent_name=azure_ai_agent.name)

            # Verify agent properties
            print(f"Agent ID: {agent.id}")
            print(f"Agent name: {agent.name}")
            print(f"Agent description: {agent.description}")
            print(f"Agent instructions: {agent.chat_options.instructions}")

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


async def using_provider() -> None:
    print("=== Get existing Azure AI agent with AzureAIAgentProvider class ===")

    # Create the client
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
    ):
        # Create remote agent
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
            # Get newly created agent as ChatAgent by using AzureAIAgentProvider class
            provider = AzureAIAgentProvider(project_client=project_client)
            agent: ChatAgent = await provider.get_agent(agent_name=azure_ai_agent.name)

            # Verify agent properties
            print(f"Agent ID: {agent.id}")
            print(f"Agent name: {agent.name}")
            print(f"Agent description: {agent.description}")
            print(f"Agent instructions: {agent.chat_options.instructions}")

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
    await using_method()
    await using_provider()


if __name__ == "__main__":
    asyncio.run(main())
