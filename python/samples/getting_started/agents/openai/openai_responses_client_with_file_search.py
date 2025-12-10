# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, HostedFileSearchTool, HostedVectorStoreContent
from agent_framework.openai import OpenAIResponsesClient

"""
OpenAI Responses Client with File Search Example

This sample demonstrates using HostedFileSearchTool with OpenAI Responses Client
for direct document-based question answering and information retrieval.
"""

# Helper functions


async def create_vector_store(client: OpenAIResponsesClient) -> tuple[str, HostedVectorStoreContent]:
    """Create a vector store with sample documents."""
    file = await client.client.files.create(
        file=("todays_weather.txt", b"The weather today is sunny with a high of 75F."), purpose="user_data"
    )
    vector_store = await client.client.vector_stores.create(
        name="knowledge_base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    result = await client.client.vector_stores.files.create_and_poll(vector_store_id=vector_store.id, file_id=file.id)
    if result.last_error is not None:
        raise Exception(f"Vector store file processing failed with status: {result.last_error.message}")

    return file.id, HostedVectorStoreContent(vector_store_id=vector_store.id)


async def delete_vector_store(client: OpenAIResponsesClient, file_id: str, vector_store_id: str) -> None:
    """Delete the vector store after using it."""

    await client.client.vector_stores.delete(vector_store_id=vector_store_id)
    await client.client.files.delete(file_id=file_id)


async def main() -> None:
    client = OpenAIResponsesClient()

    message = "What is the weather today? Do a file search to find the answer."

    stream = False
    print(f"User: {message}")
    file_id, vector_store = await create_vector_store(client)

    agent = ChatAgent(
        chat_client=client,
        instructions="You are a helpful assistant that can search through files to find information.",
        tools=[HostedFileSearchTool(inputs=vector_store)],
    )

    if stream:
        print("Assistant: ", end="")
        async for chunk in agent.run_stream(message):
            if chunk.text:
                print(chunk.text, end="")
        print("")
    else:
        response = await agent.run(message)
        print(f"Assistant: {response}")
    await delete_vector_store(client, file_id, vector_store.vector_store_id)


if __name__ == "__main__":
    asyncio.run(main())
