# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os
import uuid

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Memory Search Example

This sample demonstrates usage of AzureAIProjectAgentProvider with memory search capabilities
to retrieve relevant past user messages and maintain conversation context across sessions.
It shows explicit memory store creation using Azure AI Projects client and agent creation
using the Agent Framework.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables.
2. Set AZURE_AI_CHAT_MODEL_DEPLOYMENT_NAME for the memory chat model.
3. Set AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME for the memory embedding model.
4. Deploy both a chat model (e.g. gpt-4.1) and an embedding model (e.g. text-embedding-3-small).
"""


async def main() -> None:
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    # Generate a unique memory store name to avoid conflicts
    memory_store_name = f"agent_framework_memory_store_{uuid.uuid4().hex[:8]}"

    async with AzureCliCredential() as credential:
        # Create the memory store using Azure AI Projects client
        async with AIProjectClient(endpoint=endpoint, credential=credential) as project_client:
            # Create a memory store using proper model classes
            memory_store_definition = MemoryStoreDefaultDefinition(
                chat_model=os.environ["AZURE_AI_CHAT_MODEL_DEPLOYMENT_NAME"],
                embedding_model=os.environ["AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME"],
                options=MemoryStoreDefaultOptions(user_profile_enabled=True, chat_summary_enabled=True),
            )

            memory_store = await project_client.memory_stores.create(
                name=memory_store_name,
                description="Memory store for Agent Framework conversations",
                definition=memory_store_definition,
            )
            print(f"Created memory store: {memory_store.name} ({memory_store.id}): {memory_store.description}")

        # Then, create the agent using Agent Framework provider
        async with AzureAIProjectAgentProvider(credential=credential) as provider:
            agent = await provider.create_agent(
                name="MyMemoryAgent",
                instructions="""You are a helpful assistant that remembers past conversations.
                Use the memory search tool to recall relevant information from previous interactions.""",
                tools={
                    "type": "memory_search",
                    "memory_store_name": memory_store.name,
                    "scope": "user_123",
                    "update_delay": 1,  # Wait 1 second before updating memories (use higher value in production)
                },
            )

            # First interaction - establish some preferences
            print("=== First conversation ===")
            query1 = "I prefer dark roast coffee"
            print(f"User: {query1}")
            result1 = await agent.run(query1)
            print(f"Agent: {result1}\n")

            # Wait for memories to be processed
            print("Waiting for memories to be stored...")
            await asyncio.sleep(5)  # Reduced wait time for demo purposes

            # Second interaction - test memory recall
            print("=== Second conversation ===")
            query2 = "Please order my usual coffee"
            print(f"User: {query2}")
            result2 = await agent.run(query2)
            print(f"Agent: {result2}\n")

        # Clean up - delete the memory store
        async with AIProjectClient(endpoint=endpoint, credential=credential) as project_client:
            await project_client.memory_stores.delete(memory_store_name)
            print("Memory store deleted")


if __name__ == "__main__":
    asyncio.run(main())
