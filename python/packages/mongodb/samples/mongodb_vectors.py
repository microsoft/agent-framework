# /// script
# dependencies = [
#   "agent-framework-core>=1.17.0,<2",
#   "agent-framework-mongodb>=1.0.0a260909,<2",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import Filter, VectorStoreField, vectorstoremodel

from agent_framework_mongodb import MongoDBStore

"""Store and search deterministic vectors with MongoDB Vector Search."""


@vectorstoremodel
@dataclass
class Note:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data", storage_name="body")]
    category: Annotated[str, VectorStoreField("data", is_indexed=True)]
    title_vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None
    body_vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main() -> None:
    # 1. Resolve the URI and database through MongoDBSettings.
    async with MongoDBStore() as store:
        collection = store.get_collection(Note, collection_name=f"af_demo_{uuid4().hex}")
        await collection.ensure_collection_exists()
        try:
            # 2. Store two independent vector fields without calling an embedding service.
            await collection.upsert(
                [
                    Note("mongodb", "MongoDB supports vector search", "database", [1, 0, 0], [0, 1, 0]),
                    Note("travel", "A travel journal", "travel", [0, 1, 0], [1, 0, 0]),
                ],
                generate_vectors=False,
            )

            # 3. Select one vector index and apply an indexed metadata prefilter.
            results = await collection.search(
                vector=[1, 0, 0],
                vector_property_name="title_vector",
                filter=Filter("category", "eq", "database"),
            )
            async for result in results:
                print(result["record"].text, result["score"])

            # 4. Retrieval excludes vectors unless explicitly requested.
            note = (await collection.get(["mongodb"], include_vectors=True))[0]
            print(note.body_vector)
        finally:
            await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())

# Expected output includes:
# MongoDB supports vector search <native vectorSearchScore>
# [0.0, 1.0, 0.0]
