# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import Filter, VectorStoreField, vectorstoremodel

from agent_framework_oracle import OracleStore

"""
Use Oracle Database 23ai native vectors with local precomputed embeddings.

Environment variables:
    ORACLE_DSN      - Oracle connect string for a disposable 23ai+ schema
    ORACLE_USER     - User permitted to create and drop tables in that schema
    ORACLE_PASSWORD - Password for that user

Run from python/:
    uv run --package agent-framework-oracle python packages/oracle/samples/oracle_vectors.py

The sample creates and drops only its uniquely named table.
"""


@vectorstoremodel
@dataclass
class Note:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data", storage_name="body")]
    category: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main() -> None:
    async with OracleStore() as store:
        collection = store.get_collection(Note, collection_name=f"AF_NOTE_{uuid4().hex}")
        await collection.ensure_collection_exists()
        try:
            await collection.upsert(
                [
                    Note("oracle", "Oracle supports native VECTOR columns", "database", [1, 0, 0]),
                    Note("travel", "A travel journal", "travel", [0, 1, 0]),
                ],
                generate_vectors=False,
            )
            results = await collection.search(
                vector=[1, 0, 0],
                filter=Filter("category", "eq", "database"),
                score_threshold=0.1,
            )
            async for result in results:
                print(result["record"].text, result["score"])
            print((await collection.get(["oracle"], include_vectors=True))[0].embedding)
        finally:
            await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())

# Expected output:
# Oracle supports native VECTOR columns 0.0
# [1.0, 0.0, 0.0]
