# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import Filter, VectorStoreField, vectorstoremodel
from agent_framework.redis import RedisStore

"""
Store and search the same model using both native Redis HASH and JSON storage.

Requires agent-framework-redis and Redis 8.0.3+ with Search and RedisJSON.

Start a disposable server:
    docker run --rm --name af-redis-sample -p 127.0.0.1:6379:6379 redis:8.0.3

Vectors are supplied directly; no embedding API or credentials are required.
The example uses a unique namespace and removes only its own collections.
"""


@vectorstoremodel
@dataclass
class Document:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data", is_indexed=True)]
    category: Annotated[str, VectorStoreField("data", is_indexed=True)]
    vector: Annotated[
        list[float] | None,
        VectorStoreField("vector", dimensions=2, index_kind="flat", distance_function="cosine_distance"),
    ] = None


async def main() -> None:
    # 1. One store can create both storage formats, with shared client ownership.
    async with RedisStore(redis_url="redis://localhost:6379", namespace="sample-" + uuid4().hex) as store:
        for storage_type in ("hash", "json"):
            collection = store.get_collection(Document, collection_name=storage_type, storage_type=storage_type)
            await collection.ensure_collection_exists()
            try:
                # 2. CRUD is batch-only. False preserves the supplied vectors.
                await collection.upsert(
                    [
                        Document("one", "A guide to Redis", "database", [1.0, 0.0]),
                        Document("two", "A guide to gardening", "garden", [0.0, 1.0]),
                    ],
                    generate_vectors=False,
                )
                # 3. Native filtering and a maximum COSINE distance happen before paging.
                results = await collection.search(
                    vector=[1.0, 0.0],
                    filter=Filter("category", "eq", "database"),
                    score_threshold=0.25,
                    top=3,
                )
                async for result in results:
                    print(storage_type, result["record"].text, result["score"])
                # Vectors are excluded by default; request them when needed.
                loaded = await collection.get(["one"], include_vectors=True)
                print("Stored vector:", loaded[0].vector)
            finally:
                await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())

"""
Expected output:
hash A guide to Redis 0.0
Stored vector: [1.0, 0.0]
json A guide to Redis 0.0
Stored vector: [1.0, 0.0]
"""
