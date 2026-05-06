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
Azure Cosmos DB Context Provider — Basic RAG Example

This sample demonstrates Retrieval Augmented Generation (RAG) with Azure Cosmos DB
as the knowledge store. It shows how CosmosContextProvider retrieves relevant context
from Cosmos DB before each agent run, allowing the agent to answer questions grounded
in your data.

Key components:
- CosmosContextProvider configured for vector search retrieval
- FoundryChatClient for the agent's LLM
- A simple embedding function (toy 3D vectors for demo purposes)
- Seed documents representing a small knowledge base

The flow:
1. Seed knowledge documents into the Cosmos container
2. Create an agent with CosmosContextProvider
3. Ask questions — the provider retrieves relevant docs as context
4. The agent answers grounded in the retrieved knowledge
5. Clean up seeded documents

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT  — Azure AI Foundry project endpoint
    FOUNDRY_MODEL             — Model deployment name (e.g. gpt-4o)
    AZURE_COSMOS_ENDPOINT     — Cosmos DB account endpoint
    AZURE_COSMOS_DATABASE_NAME — Database name
    AZURE_COSMOS_CONTAINER_NAME — Container name
Optional:
    AZURE_COSMOS_KEY          — Account key (if not using AzureCliCredential)
"""

# Toy 3-dimensional embedding function for demonstration.
# Replace with a real embedding model (e.g., OpenAIEmbeddingClient) for production.
EMBEDDING_DIMENSION = 3


async def fake_embed(text: str) -> list[float]:
    """Deterministic hash-based 3D vector — sufficient for testing retrieval ordering."""
    h = hash(text) % 1000
    return [h / 1000.0, (h * 37 % 1000) / 1000.0, (h * 73 % 1000) / 1000.0]


# Knowledge documents to seed into Cosmos DB.
KNOWLEDGE_DOCS = [
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
    (
        "Hybrid search combines vector and full-text search using Reciprocal Rank Fusion (RRF) "
        "to get the best of semantic and keyword-based retrieval."
    ),
    (
        "Python is widely used for data science, machine learning, and web development. "
        "Popular frameworks include Django, Flask, and FastAPI."
    ),
]


async def seed_knowledge(client: CosmosClient, database_name: str, container_name: str, session_id: str) -> None:
    """Seed knowledge documents into the Cosmos container with embeddings."""
    container = client.get_database_client(database_name).get_container_client(container_name)
    for text in KNOWLEDGE_DOCS:
        doc = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "content": text,
            "role": "assistant",
            "source_id": "knowledge_base",
            "embedding": await fake_embed(text),
        }
        await container.upsert_item(doc)
    print(f"  Seeded {len(KNOWLEDGE_DOCS)} knowledge documents.\n")


async def cleanup_documents(client: CosmosClient, database_name: str, container_name: str, session_id: str) -> None:
    """Remove seeded test documents from the container."""
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
    """Run the basic Cosmos DB RAG sample."""
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
            # 1. Seed knowledge documents into the container.
            print("=== Step 1: Seeding knowledge documents ===")
            await seed_knowledge(cosmos_client, database_name, container_name, session_id)

            # 2. Create the CosmosContextProvider for vector search retrieval.
            print("=== Step 2: Creating agent with Cosmos context provider ===\n")
            context_provider = CosmosContextProvider(
                source_id="cosmos_knowledge",
                cosmos_client=cosmos_client,
                database_name=database_name,
                container_name=container_name,
                search_mode=CosmosContextSearchMode.VECTOR,
                embedding_function=fake_embed,
                partition_key=session_id,
                top_k=3,
                context_prompt="Use the following knowledge base context to answer the question:",
            )

            # 3. Create the agent with the context provider.
            async with Agent(
                client=FoundryChatClient(
                    project_endpoint=project_endpoint,
                    model=model,
                    credential=credential,
                ),
                name="CosmosRAGAgent",
                instructions=(
                    "You are a helpful assistant. Answer questions using the provided context. "
                    "If the context doesn't contain relevant information, say so."
                ),
                context_providers=[context_provider],
            ) as agent:
                # 4. Ask questions — the provider retrieves relevant context from Cosmos.
                questions = [
                    "What is Azure Cosmos DB?",
                    "How does vector search work in Cosmos DB?",
                    "What is hybrid search?",
                ]

                for question in questions:
                    print(f"User: {question}")
                    response = await agent.run(question)
                    print(f"Agent: {response.text}\n")

            # 5. Clean up seeded documents.
            print("=== Step 3: Cleaning up ===")
            await cleanup_documents(cosmos_client, database_name, container_name, session_id)

    print("\n✓ Basic RAG sample complete.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Step 1: Seeding knowledge documents ===
  Seeded 5 knowledge documents.

=== Step 2: Creating agent with Cosmos context provider ===

User: What is Azure Cosmos DB?
Agent: Azure Cosmos DB is a globally distributed, multi-model database service that supports
NoSQL, MongoDB, Cassandra, Gremlin, and Table APIs.

User: How does vector search work in Cosmos DB?
Agent: Vector search in Cosmos DB enables AI applications to find semantically similar
documents using embeddings and cosine distance functions.

User: What is hybrid search?
Agent: Hybrid search combines vector and full-text search using Reciprocal Rank Fusion (RRF)
to get the best of semantic and keyword-based retrieval.

=== Step 3: Cleaning up ===

  Cleaned up 5 documents.

✓ Basic RAG sample complete.
"""
