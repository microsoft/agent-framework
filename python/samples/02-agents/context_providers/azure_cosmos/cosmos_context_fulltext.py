# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import uuid

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_cosmos import CosmosContextProvider, CosmosContextSearchMode
from azure.cosmos.aio import CosmosClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

"""
Azure Cosmos DB Context Provider -- Full-Text Search

This sample demonstrates RAG with Azure Cosmos DB using full-text search mode.
Full-text search uses BM25 ranking to find documents by keyword relevance rather
than vector similarity. No embedding function is needed for this mode.

After each agent run, the conversation exchange is written back to the container
automatically. Follow-up questions can then retrieve prior exchanges by keyword.

Key components:
- CosmosContextProvider configured for FULL_TEXT search mode
- No embedding function required (BM25 keyword matching only)
- FoundryChatClient for the agent's LLM
- Automatic writeback of conversation exchanges

The flow:
1. Create an agent with CosmosContextProvider (full-text mode)
2. Ask questions -- the agent answers using its own knowledge
3. After each run, the exchange is written back to Cosmos automatically
4. Clean up written-back documents

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT    -- Azure AI Foundry project endpoint
    FOUNDRY_MODEL               -- Model deployment name (e.g. gpt-4o)
    AZURE_COSMOS_ENDPOINT       -- Cosmos DB account endpoint
    AZURE_COSMOS_DATABASE_NAME  -- Database name
    AZURE_COSMOS_CONTAINER_NAME -- Container name
Optional:
    AZURE_COSMOS_KEY            -- Account key (if not using AzureCliCredential)
"""


async def cleanup_documents(client: CosmosClient, database_name: str, container_name: str, session_id: str) -> None:
    """Remove all documents written back during this sample's session."""
    container = client.get_database_client(database_name).get_container_client(container_name)
    items = [
        item
        async for item in container.query_items(
            query="SELECT c.id FROM c WHERE c.session_id = @sid",
            parameters=[{"name": "@sid", "value": session_id}],
            partition_key=session_id,
        )
    ]
    for item in items:
        await container.delete_item(item["id"], partition_key=session_id)
    print(f"\n  Cleaned up {len(items)} documents.")


async def main() -> None:
    """Run the full-text search sample."""
    # Read configuration from environment
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL")
    cosmos_endpoint = os.getenv("AZURE_COSMOS_ENDPOINT")
    database_name = os.getenv("AZURE_COSMOS_DATABASE_NAME")
    container_name = os.getenv("AZURE_COSMOS_CONTAINER_NAME")
    cosmos_key = os.getenv("AZURE_COSMOS_KEY")

    if not project_endpoint or not model or not cosmos_endpoint or not database_name or not container_name:
        print(
            "Please set FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL, "
            "AZURE_COSMOS_ENDPOINT, AZURE_COSMOS_DATABASE_NAME, and AZURE_COSMOS_CONTAINER_NAME."
        )
        return

    session_id = f"fulltext-{uuid.uuid4().hex[:8]}"

    async with AzureCliCredential() as credential:
        cosmos_client = CosmosClient(url=cosmos_endpoint, credential=cosmos_key or credential)

        async with cosmos_client:
            # 1. Create the CosmosContextProvider for full-text search.
            #    No embedding function is needed since BM25 uses keyword matching.
            #    No partition_key is set, so the provider uses session_id from the
            #    conversation context for both retrieval and writeback.
            print("=== Step 1: Ask questions with full-text search ===\n")
            context_provider = CosmosContextProvider(
                source_id="cosmos_knowledge",
                cosmos_client=cosmos_client,
                database_name=database_name,
                container_name=container_name,
                search_mode=CosmosContextSearchMode.FULL_TEXT,
                top_k=3,
                context_prompt="Use the following knowledge base context to answer the question:",
            )

            # 2. Create the agent with the context provider.
            async with Agent(
                client=FoundryChatClient(
                    project_endpoint=project_endpoint,
                    model=model,
                    credential=credential,
                ),
                name="CosmosFullTextAgent",
                instructions=(
                    "You are a helpful assistant. Answer questions using the provided context. "
                    "If the context doesn't contain relevant information, say so."
                ),
                context_providers=[context_provider],
            ) as agent:
                session = agent.create_session(session_id=session_id)

                # 3. Ask questions. Full-text search finds documents by keyword relevance.
                #    After each run, the exchange is written back to Cosmos.
                questions = [
                    "What is BM25 ranking?",
                    "Tell me about Python web frameworks",
                    "How does Cosmos DB handle distributed data with multiple APIs?",
                ]

                for question in questions:
                    print(f"User: {question}")
                    response = await agent.run(question, session=session)
                    print(f"Agent: {response.text}\n")

            # 4. Clean up written-back documents.
            print("=== Step 2: Cleaning up ===")
            await cleanup_documents(cosmos_client, database_name, container_name, session_id)

    print("\n✓ Full-text search sample complete.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Step 1: Ask questions with full-text search ===

User: What is BM25 ranking?
Agent: Full-text search in Cosmos DB uses BM25 ranking to find documents matching
keyword queries, similar to traditional search engines.

User: Tell me about Python web frameworks
Agent: Python is widely used for web development. Popular frameworks include Django,
Flask, and FastAPI.

User: How does Cosmos DB handle distributed data with multiple APIs?
Agent: Azure Cosmos DB is a globally distributed, multi-model database service that
supports NoSQL, MongoDB, Cassandra, Gremlin, and Table APIs.

=== Step 2: Cleaning up ===

  Cleaned up 6 documents.

✓ Full-text search sample complete.
"""
