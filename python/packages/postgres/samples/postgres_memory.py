# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core>=1.18.0,<2",
#     "agent-framework-openai>=1.14.3,<2",
#     "agent-framework-postgres>=1.0.0a260914,<2",
# ]
# ///
# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
import sys

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient, OpenAIEmbeddingClient

from agent_framework_postgres import (
    PostgresMemoryClientOptions,
    PostgresMemoryContextProvider,
    PostgresMemoryScope,
    PostgresMemoryVectorIndexKind,
)

"""
Use PostgreSQL-backed durable memory with an Agent Framework agent.

Prerequisites:
    - PostgreSQL with pgvector enabled and an existing ``public`` schema.
    - ``POSTGRES_CONNECTION_STRING``, ``OPENAI_API_KEY``, ``OPENAI_CHAT_MODEL``,
      and ``OPENAI_EMBEDDING_MODEL`` environment variables.
        - For ``--azure``, Azure Database for PostgreSQL with ``pg_diskann`` and
            ``azure_ai`` enabled and a configured Foundry reranker deployment.

Run:
    uv run python packages/postgres/samples/postgres_memory.py
        uv run python packages/postgres/samples/postgres_memory.py --azure
"""


async def main() -> None:
    use_azure_retrieval = "--azure" in sys.argv[1:]

    # 1. Create caller-owned model clients.
    chat_client = OpenAIChatClient(
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.environ["OPENAI_CHAT_MODEL"],
    )
    embedding_client = OpenAIEmbeddingClient(
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.environ["OPENAI_EMBEDDING_MODEL"],
    )

    # 2. Let the provider create and own the PostgreSQL memory client.
    provider = PostgresMemoryContextProvider(
        embedding_generator=embedding_client,
        chat_client=chat_client,
        application_id="postgres-memory-sample",
        agent_id="assistant",
        client_options=PostgresMemoryClientOptions(
            embedding_dimensions=1536,
            vector_index_kind=(
                PostgresMemoryVectorIndexKind.DISK_ANN
                if use_azure_retrieval
                else PostgresMemoryVectorIndexKind.HNSW
            ),
            enable_azure_ai_reranking=use_azure_retrieval,
            azure_ai_reranker_model=os.getenv("FOUNDRY_RERANKER_MODEL", "cohere-rerank-v3.5"),
        ),
    )
    agent = Agent(
        client=chat_client,
        name="PostgresMemoryAgent",
        instructions="Answer clearly and use relevant prior context.",
        context_providers=[provider],
    )

    # 3. Supply a stable, application-authorized user identity in provider state.
    session = agent.create_session()
    session.state.setdefault(provider.source_id, {})["user_id"] = "sample-user"

    # 4. The first run stores turns and schedules memory processing.
    async with provider:
        response = await agent.run(
            "Remember that I prefer concise Python examples.",
            session=session,
        )
        print(f"Agent: {response}\n")
        await provider.flush()

        # 5. The next run can retrieve the stored preference.
        response = await agent.run(
            "What style of examples do I prefer?",
            session=session,
        )
        print(f"Agent: {response}")

        if use_azure_retrieval:
            results = await provider.memory_client.search(
                PostgresMemoryScope(
                    user_id="sample-user",
                    application_id="postgres-memory-sample",
                    agent_id="assistant",
                ),
                "What style of examples does the user prefer?",
                min_confidence=0,
            )
            print("\nDiskANN candidates after azure_ai.rank():")
            for result in results:
                print(f"RRF={result.score}, reranker={result.reranker_score}: {result.content}")


if __name__ == "__main__":
    asyncio.run(main())

# Expected output:
# Agent: Understood. I will keep Python examples concise.
#
# Agent: You prefer concise Python examples.
