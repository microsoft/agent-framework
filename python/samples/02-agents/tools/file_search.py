# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, Content, HostedFileSearchTool
from agent_framework.openai import OpenAIResponsesClient

"""
File Search Tool

Demonstrates using HostedFileSearchTool to search through uploaded documents.
Files are uploaded to a vector store, then the agent can search and retrieve
information from them.

For more on file search:
- Azure AI file search: getting_started/agents/azure_ai/azure_ai_with_file_search.py
- Azure OpenAI: getting_started/agents/azure_openai/azure_responses_client_with_file_search.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/file-search
"""


async def create_vector_store(client: OpenAIResponsesClient) -> tuple[str, Content]:
    """Create a vector store with a sample document."""
    # <upload_file>
    file = await client.client.files.create(
        file=("todays_weather.txt", b"The weather today is sunny with a high of 75F."),
        purpose="user_data",
    )
    vector_store = await client.client.vector_stores.create(
        name="knowledge_base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    result = await client.client.vector_stores.files.create_and_poll(
        vector_store_id=vector_store.id, file_id=file.id
    )
    if result.last_error is not None:
        raise Exception(f"Vector store file processing failed: {result.last_error.message}")

    return file.id, Content.from_hosted_vector_store(vector_store_id=vector_store.id)
    # </upload_file>


async def main() -> None:
    print("=== File Search Tool ===\n")

    client = OpenAIResponsesClient()
    file_id, vector_store = await create_vector_store(client)

    try:
        # <create_agent>
        agent = ChatAgent(
            chat_client=client,
            instructions="You are a helpful assistant that can search through files to find information.",
            tools=[HostedFileSearchTool(inputs=vector_store)],
        )
        # </create_agent>

        # <run_query>
        message = "What is the weather today? Do a file search to find the answer."
        print(f"User: {message}")
        response = await agent.run(message)
        print(f"Assistant: {response}")
        # </run_query>
    finally:
        # Cleanup
        await client.client.vector_stores.delete(vector_store.vector_store_id)
        await client.client.files.delete(file_id)


if __name__ == "__main__":
    asyncio.run(main())
