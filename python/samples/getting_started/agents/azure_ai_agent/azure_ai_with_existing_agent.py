# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.agents.aio import AgentsClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Existing Agent Example

This sample demonstrates working with pre-existing Azure AI Agents by providing
agent IDs, showing agent reuse patterns for production scenarios.
"""


async def main() -> None:
    print("=== Azure AI Chat Client with Existing Agent ===")

    # Create the client
    async with (
        AzureCliCredential() as credential,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
    ):
        azure_ai_agent = await agents_client.create_agent(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            # Create remote agent with default instructions
            # These instructions will persist on created agent for every run.
            instructions="End each response with [END].",
        )

        chat_client = AzureAIAgentClient(agents_client=agents_client, agent_id=azure_ai_agent.id)

        try:
            async with ChatAgent(
                chat_client=chat_client,
                # Instructions here are applicable only to this ChatAgent instance
                # These instructions will be combined with instructions on existing remote agent.
                # The final instructions during the execution will look like:
                # "'End each response with [END]. Respond with 'Hello World' only'"
                instructions="Respond with 'Hello World' only",
            ) as agent:
                query = "How are you?"
                print(f"User: {query}")
                result = await agent.run(query)
                # Based on local and remote instructions, the result will be
                # 'Hello World [END]'.
                print(f"Agent: {result}\n")
        finally:
            # Clean up the agent manually
            await agents_client.delete_agent(azure_ai_agent.id)


if __name__ == "__main__":
    asyncio.run(main())
