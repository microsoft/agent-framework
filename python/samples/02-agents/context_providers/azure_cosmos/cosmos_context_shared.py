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
Azure Cosmos DB Context Provider -- Shared Knowledge Across Conversations

This sample demonstrates how multiple agent conversations can share context
through a common Cosmos DB partition. By setting `partition_key` on the
CosmosContextProvider constructor, all providers using the same value will
read from and write to the same partition, regardless of their session_id.

This is useful for scenarios like:
- A team knowledge base that all agents can query and contribute to
- Pre-populated reference material accessible to every conversation
- Cross-session context where one conversation's insights are available to others

The flow:
1. Seed a few knowledge documents into a shared partition
2. Run two separate agent sessions that both use the same partition_key
3. Both sessions can retrieve the shared knowledge and each other's writeback
4. Clean up all documents

Note: Each written-back document still records the real session_id of the
conversation that produced it, so you can trace which session contributed
each piece of knowledge.

Important: When using partition_key with a container whose partition key path
is /session_id, the partition_key value is written into the session_id field
of the document. For shared knowledge scenarios where you want session_id to
reflect the real conversation, consider using a container with a different
partition key path (e.g., /partition_key). See the README for details.

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


# Seed documents representing pre-existing knowledge from prior conversations.
# In a real application, these might come from a knowledge ingestion pipeline
# or from previous agent sessions that wrote back into the same partition.
SHARED_KNOWLEDGE = [
    (
        "Azure Cosmos DB is a globally distributed, multi-model database service. "
        "It supports NoSQL, MongoDB, Cassandra, Gremlin, and Table APIs."
    ),
    (
        "Vector search in Cosmos DB enables AI applications to find semantically similar "
        "documents using embeddings and cosine distance functions."
    ),
    (
        "Full-text search in Cosmos DB uses BM25 ranking to find documents matching "
        "keyword queries, similar to traditional search engines."
    ),
]

SHARED_PARTITION = "team-knowledge"


async def seed_shared_knowledge(
    client: CosmosClient, database_name: str, container_name: str
) -> None:
    """Seed shared knowledge documents into the common partition.

    These documents simulate pre-existing context from prior conversations
    or an external knowledge ingestion pipeline. The session_id values on
    seed documents represent the original sessions that produced them.
    """
    container = client.get_database_client(database_name).get_container_client(container_name)
    for text in SHARED_KNOWLEDGE:
        doc = {
            "id": f"seed-{uuid.uuid4().hex[:8]}",
            "session_id": SHARED_PARTITION,
            "content": text,
            "role": "assistant",
            "source_id": "knowledge_base",
            "embedding": await fake_embed(text),
        }
        await container.upsert_item(doc)
    print(f"  Seeded {len(SHARED_KNOWLEDGE)} shared knowledge documents.\n")


async def cleanup_documents(
    client: CosmosClient, database_name: str, container_name: str
) -> None:
    """Remove all documents in the shared partition."""
    container = client.get_database_client(database_name).get_container_client(container_name)
    items = [
        item
        async for item in container.query_items(
            query="SELECT c.id FROM c WHERE c.session_id = @sid",
            parameters=[{"name": "@sid", "value": SHARED_PARTITION}],
            partition_key=SHARED_PARTITION,
        )
    ]
    for item in items:
        await container.delete_item(item["id"], partition_key=SHARED_PARTITION)
    print(f"\n  Cleaned up {len(items)} documents.")


async def main() -> None:
    """Run the shared knowledge sample."""
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

    async with AzureCliCredential() as credential:
        cosmos_client = CosmosClient(url=cosmos_endpoint, credential=cosmos_key or credential)

        async with cosmos_client:
            # 1. Seed shared knowledge into the common partition.
            #    These represent pre-existing context from other sessions or
            #    an external knowledge pipeline.
            print("=== Step 1: Seed shared knowledge ===")
            await seed_shared_knowledge(cosmos_client, database_name, container_name)

            # 2. Create a CosmosContextProvider with partition_key.
            #    All sessions using this partition_key share the same context.
            shared_provider = CosmosContextProvider(
                source_id="cosmos_knowledge",
                cosmos_client=cosmos_client,
                database_name=database_name,
                container_name=container_name,
                search_mode=CosmosContextSearchMode.VECTOR,
                embedding_function=fake_embed,
                partition_key=SHARED_PARTITION,
                top_k=3,
                context_prompt="Use the following shared knowledge base to answer the question:",
            )

            # 3. Session A: ask a question using shared context.
            print("=== Step 2: Session A queries shared knowledge ===\n")
            async with Agent(
                client=FoundryChatClient(
                    project_endpoint=project_endpoint,
                    model=model,
                    credential=credential,
                ),
                name="AgentSessionA",
                instructions=(
                    "You are a helpful assistant. Answer questions using the provided context. "
                    "If the context doesn't contain relevant information, say so."
                ),
                context_providers=[shared_provider],
            ) as agent:
                session_a = agent.create_session(session_id=f"session-a-{uuid.uuid4().hex[:8]}")
                question_a = "What database APIs does Azure Cosmos DB support?"
                print(f"[Session A] User: {question_a}")
                response = await agent.run(question_a, session=session_a)
                print(f"[Session A] Agent: {response.text}\n")

            # 4. Session B: a different conversation can see both the seed
            #    documents and the exchange written back by Session A.
            print("=== Step 3: Session B sees shared context ===\n")
            async with Agent(
                client=FoundryChatClient(
                    project_endpoint=project_endpoint,
                    model=model,
                    credential=credential,
                ),
                name="AgentSessionB",
                instructions=(
                    "You are a helpful assistant. Answer questions using the provided context. "
                    "If the context doesn't contain relevant information, say so."
                ),
                context_providers=[shared_provider],
            ) as agent:
                session_b = agent.create_session(session_id=f"session-b-{uuid.uuid4().hex[:8]}")
                question_b = "What search capabilities are available in Cosmos DB?"
                print(f"[Session B] User: {question_b}")
                response = await agent.run(question_b, session=session_b)
                print(f"[Session B] Agent: {response.text}\n")

            # 5. Clean up all documents in the shared partition.
            print("=== Step 4: Cleaning up ===")
            await cleanup_documents(cosmos_client, database_name, container_name)

    print("\n✓ Shared knowledge sample complete.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Step 1: Seed shared knowledge ===
  Seeded 3 shared knowledge documents.

=== Step 2: Session A queries shared knowledge ===

[Session A] User: What database APIs does Azure Cosmos DB support?
[Session A] Agent: Azure Cosmos DB supports NoSQL, MongoDB, Cassandra, Gremlin, and Table APIs.

=== Step 3: Session B sees shared context ===

[Session B] User: What search capabilities are available in Cosmos DB?
[Session B] Agent: Cosmos DB supports vector search for semantic similarity using embeddings,
and full-text search using BM25 ranking for keyword matching.

=== Step 4: Cleaning up ===

  Cleaned up 7 documents.

✓ Shared knowledge sample complete.
"""
