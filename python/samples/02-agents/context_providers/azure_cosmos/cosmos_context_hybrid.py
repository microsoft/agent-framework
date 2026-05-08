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
Azure Cosmos DB Context Provider -- Hybrid Search

This sample demonstrates RAG with Azure Cosmos DB using hybrid search mode.
Hybrid search combines vector similarity (VectorDistance) and full-text keyword
matching (FullTextScore) using Reciprocal Rank Fusion (RRF) to get the best of
both approaches.

Optionally, you can pass weights to control the relative importance of each
component (e.g., weighting vector results higher than keyword results).

After each agent run, the conversation exchange is written back to the container
automatically. Follow-up questions can then retrieve prior exchanges using both
semantic similarity and keyword matching.

Key components:
- CosmosContextProvider configured for HYBRID search mode
- An embedding function for vector similarity
- Optional weighted RRF for tuning vector vs. keyword balance
- FoundryChatClient for the agent's LLM
- Automatic writeback of conversation exchanges

The flow:
1. Create an agent with CosmosContextProvider (hybrid mode)
2. Ask questions -- the agent answers using its own knowledge
3. Show optional weighted hybrid search configuration
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
    """Run the hybrid search sample."""
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

    session_id = f"hybrid-{uuid.uuid4().hex[:8]}"

    async with AzureCliCredential() as credential:
        cosmos_client = CosmosClient(url=cosmos_endpoint, credential=cosmos_key or credential)

        async with cosmos_client:
            # 1. Create the CosmosContextProvider for hybrid search.
            #    Hybrid combines vector similarity and BM25 keyword matching via RRF.
            #    No partition_key is set, so the provider uses session_id from the
            #    conversation context for both retrieval and writeback.
            print("=== Step 1: Ask questions with hybrid search ===\n")
            context_provider = CosmosContextProvider(
                source_id="cosmos_knowledge",
                cosmos_client=cosmos_client,
                database_name=database_name,
                container_name=container_name,
                search_mode=CosmosContextSearchMode.HYBRID,
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
                name="CosmosHybridAgent",
                instructions=(
                    "You are a helpful assistant. Answer questions using the provided context. "
                    "If the context doesn't contain relevant information, say so."
                ),
                context_providers=[context_provider],
            ) as agent:
                session = agent.create_session(session_id=session_id)

                # 3. Ask questions. Hybrid search combines semantic and keyword matching.
                #    After each run, the exchange is written back to Cosmos.
                questions = [
                    "What is Azure Cosmos DB and what APIs does it support?",
                    "How does full-text search ranking work?",
                ]

                for question in questions:
                    print(f"User: {question}")
                    response = await agent.run(question, session=session)
                    print(f"Agent: {response.text}\n")

            # 4. Demonstrate weighted hybrid search.
            #    Weights control the relative importance of each RRF component.
            #    weights=[1, 2] means full-text results are weighted 2x vs vector results.
            print("=== Step 2: Weighted hybrid search ===\n")
            weighted_provider = CosmosContextProvider(
                source_id="cosmos_knowledge",
                cosmos_client=cosmos_client,
                database_name=database_name,
                container_name=container_name,
                search_mode=CosmosContextSearchMode.HYBRID,
                embedding_function=fake_embed,
                top_k=3,
                weights=[1, 2],  # [full-text weight, vector weight]
                context_prompt="Use the following knowledge base context to answer the question:",
            )

            async with Agent(
                client=FoundryChatClient(
                    project_endpoint=project_endpoint,
                    model=model,
                    credential=credential,
                ),
                name="CosmosWeightedHybridAgent",
                instructions=(
                    "You are a helpful assistant. Answer questions using the provided context. "
                    "If the context doesn't contain relevant information, say so."
                ),
                context_providers=[weighted_provider],
            ) as agent:
                session = agent.create_session(session_id=session_id)
                question = "Tell me about search capabilities in Cosmos DB"
                print(f"User: {question}")
                response = await agent.run(question, session=session)
                print(f"Agent: {response.text}\n")

            # 5. Clean up written-back documents.
            print("=== Step 3: Cleaning up ===")
            await cleanup_documents(cosmos_client, database_name, container_name, session_id)

    print("\n✓ Hybrid search sample complete.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Step 1: Ask questions with hybrid search ===

User: What is Azure Cosmos DB and what APIs does it support?
Agent: Azure Cosmos DB is a globally distributed, multi-model database service that supports
NoSQL, MongoDB, Cassandra, Gremlin, and Table APIs.

User: How does full-text search ranking work?
Agent: Full-text search in Cosmos DB uses BM25 ranking to find documents matching keyword
queries, similar to traditional search engines.

=== Step 2: Weighted hybrid search ===

User: Tell me about search capabilities in Cosmos DB
Agent: Cosmos DB supports multiple search capabilities: vector search for semantic similarity
using embeddings, full-text search using BM25 ranking for keyword matching, and hybrid search
that combines both using Reciprocal Rank Fusion (RRF).

=== Step 3: Cleaning up ===

  Cleaned up 6 documents.

✓ Hybrid search sample complete.
"""
