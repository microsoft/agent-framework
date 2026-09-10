# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import Filter, VectorStoreField, vectorstoremodel

from agent_framework_postgres import PostgresStore

"""
Use PostgreSQL/pgvector with two vector columns and literal metadata filtering.

Run against an explicitly designated development database with pgvector 0.8+:
    POSTGRES_CONNECTION_STRING=... uv run --package agent-framework-postgres \
        python packages/postgres/samples/postgres_vectors.py

The public schema and vector extension must already exist. This example creates
a uniquely named table and drops only that table. It uses deterministic vectors,
not a paid embedding service.
PostgresStore uses AF PostgresSettings to resolve POSTGRES_CONNECTION_STRING.
Alternatively pass env_file_path="postgres.env" or an explicit connection_string.
"""


@vectorstoremodel
@dataclass
class Note:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data", storage_name="body")]
    category: Annotated[str, VectorStoreField("data", is_indexed=True)]
    title_vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3, index_kind="hnsw")] = None
    body_vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main() -> None:
    # 1. Resolve AF settings from the environment. The store owns its pool; collections borrow it.
    async with PostgresStore() as store:
        collection = store.get_collection(Note, collection_name=f"af_demo_{uuid4().hex}")
        await collection.ensure_collection_exists()
        try:
            # 2. Preserve supplied vectors. With a generator, select just the fields to regenerate.
            await collection.upsert(
                [
                    Note("postgres", "PostgreSQL supports pgvector", "database", [1, 0, 0], [0, 1, 0]),
                    Note("travel", "A travel journal", "travel", [0, 1, 0], [1, 0, 0]),
                ],
                generate_vectors=False,
            )

            # 3. Choose a vector column and apply the filter/threshold in PostgreSQL.
            results = await collection.search(
                vector=[1, 0, 0],
                vector_property_name="title_vector",
                filter=Filter("category", "eq", "database"),
                score_threshold=0.1,
            )
            async for result in results:
                print(result["record"].text, result["score"])

            # 4. Ordinary retrieval omits vector columns; opt in to return them.
            notes = await collection.get(["postgres"], include_vectors=True)
            print(notes[0].body_vector)
        finally:
            await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())

# Expected output:
# PostgreSQL supports pgvector 0.0
# [0.0, 1.0, 0.0]
