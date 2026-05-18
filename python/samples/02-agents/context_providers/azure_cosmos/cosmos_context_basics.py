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
Azure Cosmos DB Context Provider -- Vector Search with Writeback

This sample demonstrates Retrieval Augmented Generation (RAG) with Azure Cosmos DB
using vector search (the default mode). After each agent run, the conversation
exchange is automatically written back into the Cosmos container, so the knowledge
base grows over time and follow-up questions can retrieve prior exchanges.

By default, context is scoped to the current session_id, keeping each conversation's
knowledge isolated.

Key components:
- CosmosContextProvider configured for vector search retrieval
- Automatic writeback of conversation exchanges after each run
- FoundryChatClient for the agent's LLM
- A simple embedding function (toy 3D vectors for demo purposes)

The flow:
1. Create an agent with CosmosContextProvider (vector mode)
2. Ask questions -- the agent answers using its own knowledge
3. After each run, the exchange is written back to Cosmos automatically
4. A follow-up question retrieves the written-back exchanges as context
5. Clean up all documents

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT    -- Azure AI Foundry project endpoint
    FOUNDRY_MODEL               -- Model deployment name (e.g. gpt-4o)
    AZURE_COSMOS_ENDPOINT       -- Cosmos DB account endpoint
    AZURE_COSMOS_DATABASE_NAME  -- Database name
    AZURE_COSMOS_CONTAINER_NAME -- Container name
Optional:
    AZURE_COSMOS_KEY            -- Account key (if not using AzureCliCredential)
"""

# Toy 3-dimensional embedding function for demonstration.
# Replace with a real embedding model (e.g., OpenAIEmbeddingClient) for production.
EMBEDDING_DIMENSION = 3


async def fake_embed(text: str) -> list[float]:
    """Deterministic hash-based 3D vector for testing retrieval ordering."""
    h = hash(text) % 1000
    return [h / 1000.0, (h * 37 % 1000) / 1000.0, (h * 73 % 1000) / 1000.0]


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
    """Run the vector search + writeback sample."""
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

    session_id = f"basics-{uuid.uuid4().hex[:8]}"

    async with AzureCliCredential() as credential:
        cosmos_client = CosmosClient(url=cosmos_endpoint, credential=cosmos_key or credential)

        async with cosmos_client:
            # 1. Create the CosmosContextProvider for vector search retrieval.
            #    No partition_key is set, so the provider uses session_id from the
            #    conversation context for both retrieval and writeback.
            print("=== Step 1: Ask questions with vector search ===\n")
            context_provider = CosmosContextProvider(
                source_id="cosmos_knowledge",
                cosmos_client=cosmos_client,
                database_name=database_name,
                container_name=container_name,
                search_mode=CosmosContextSearchMode.VECTOR,
                embedding_function=fake_embed,
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
                name="CosmosVectorAgent",
                instructions=(
                    "You are a helpful assistant. Answer questions using the provided context. "
                    "If the context doesn't contain relevant information, say so."
                ),
                context_providers=[context_provider],
            ) as agent:
                session = agent.create_session(session_id=session_id)

                # 3. Ask questions. The agent answers from its own knowledge.
                #    After each run, the exchange is written back to Cosmos.
                questions = [
                    "What is Azure Cosmos DB?",
                    "How does vector search work in Cosmos DB?",
                ]

                for question in questions:
                    print(f"User: {question}")
                    response = await agent.run(question, session=session)
                    print(f"Agent: {response.text}\n")

                # 4. Demonstrate writeback: ask a follow-up question.
                #    The provider retrieves the conversation exchanges that were
                #    written back in the previous steps as additional context.
                print("=== Step 2: Writeback in action ===\n")
                followup = "What did we just discuss about Cosmos DB?"
                print(f"User: {followup}")
                response = await agent.run(followup, session=session)
                print(f"Agent: {response.text}\n")

            # 5. Clean up written-back documents.
            print("=== Step 3: Cleaning up ===")
            await cleanup_documents(cosmos_client, database_name, container_name, session_id)

    print("\n✓ Vector search + writeback sample complete.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Step 1: Ask questions with vector search ===

User: What is Azure Cosmos DB?
Agent: Azure Cosmos DB is a globally distributed, multi-model database service that supports
NoSQL, MongoDB, Cassandra, Gremlin, and Table APIs.

User: How does vector search work in Cosmos DB?
Agent: Vector search in Cosmos DB enables AI applications to find semantically similar
documents using embeddings and cosine distance functions.

=== Step 2: Writeback in action ===

User: What did we just discuss about Cosmos DB?
Agent: We discussed that Azure Cosmos DB is a globally distributed database service, and that
it supports vector search for finding semantically similar documents using embeddings.

=== Step 3: Cleaning up ===

  Cleaned up 6 documents.

✓ Vector search + writeback sample complete.
"""
