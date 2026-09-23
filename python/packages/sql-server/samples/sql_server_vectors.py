# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import Filter, VectorStoreField, vectorstoremodel

from agent_framework_sql_server import SqlServerStore

"""
Search native VECTOR columns in SQL Server 2025 or Azure SQL.

Set SQL_SERVER_CONNECTION_STRING to a connection string for an explicitly
designated development database. The example creates a unique table in the
existing dbo schema and drops only that table. No embedding service is needed.

Run: uv run --package agent-framework-sql-server python packages/sql-server/samples/sql_server_vectors.py
"""


@vectorstoremodel
@dataclass
class Note:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data", storage_name="body")]
    category: Annotated[str, VectorStoreField("data", is_indexed=True)]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main() -> None:
    # 1. Resolve SQL_SERVER_CONNECTION_STRING using Agent Framework settings.
    async with SqlServerStore() as store:
        collection = store.get_collection(Note, collection_name=f"af_sql_demo_{uuid4().hex}")
        await collection.ensure_collection_exists()
        try:
            # 2. Preserve precomputed vectors; pass a generator to produce them locally instead.
            await collection.upsert(
                [
                    Note("sql", "SQL Server has native vector columns", "database", [1, 0, 0]),
                    Note("travel", "Travel journal", "travel", [0, 1, 0]),
                ],
                generate_vectors=False,
            )

            # 3. Filter, rank, and apply the score threshold in the database before paging.
            results = await collection.search(
                vector=[1, 0, 0],
                filter=Filter("category", "eq", "database"),
                score_threshold=0.1,
            )
            async for result in results:
                print(result["record"].text, result["score"])

            # 4. Retrieval excludes embeddings by default; request them explicitly.
            notes = await collection.get(["sql"], include_vectors=True)
            print(notes[0].embedding)
        finally:
            await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())

# Expected output:
# SQL Server has native vector columns 0.0
# [1.0, 0.0, 0.0]
