# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, HostedFileSearchTool, HostedVectorStoreContent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

"""
Azure OpenAI Responses Client with File Search Example

This sample demonstrates using HostedFileSearchTool with Azure OpenAI Responses Client
for direct document-based question answering and information retrieval.

Prerequisites:
- Set environment variables:
  - AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint URL
  - AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME: Your Responses API deployment name
- Authenticate via 'az login' for AzureCliCredential
"""

# Helper functions


async def create_vector_store(client: AzureOpenAIResponsesClient) -> tuple[str, HostedVectorStoreContent]:
    """Create a vector store with sample documents."""
    file = await client.client.files.create(
        file=("todays_weather.txt", b"The weather today is sunny with a high of 75F."), purpose="assistants"
    )
    vector_store = await client.client.vector_stores.create(
        name="knowledge_base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    result = await client.client.vector_stores.files.create_and_poll(vector_store_id=vector_store.id, file_id=file.id)
    if result.last_error is not None:
        raise Exception(f"Vector store file processing failed with status: {result.last_error.message}")

    return file.id, HostedVectorStoreContent(vector_store_id=vector_store.id)


async def delete_vector_store(client: AzureOpenAIResponsesClient, file_id: str, vector_store_id: str) -> None:
    """Delete the vector store after using it."""
    await client.client.vector_stores.delete(vector_store_id=vector_store_id)
    await client.client.files.delete(file_id=file_id)


async def main() -> None:
    print("=== Azure OpenAI Responses Client with File Search Example ===\n")

    # Initialize Responses client
    # Make sure you're logged in via 'az login' before running this sample
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    file_id, vector_store = await create_vector_store(client)

    agent = ChatAgent(
        chat_client=client,
        instructions="You are a helpful assistant that can search through files to find information.",
        tools=[HostedFileSearchTool(inputs=vector_store)],
    )

    query = "What is the weather today? Do a file search to find the answer."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    await delete_vector_store(client, file_id, vector_store.vector_store_id)


if __name__ == "__main__":
    asyncio.run(main())
