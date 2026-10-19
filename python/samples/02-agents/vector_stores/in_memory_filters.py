# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import Filter, FilterGroup, InMemoryCollection, VectorStoreField, vectorstoremodel

"""
This sample demonstrates direct vector searches with portable, data-only filters.

The in-memory store is process-local and uses a linear scan. It is intended for
tests and development, not as a production vector database.
"""


@vectorstoremodel(collection_name="hotels")
@dataclass
class Hotel:
    hotel_id: Annotated[str, VectorStoreField("key")]
    name: Annotated[str, VectorStoreField("data")]
    city: Annotated[str, VectorStoreField("data")]
    rating: Annotated[float, VectorStoreField("data")]
    amenities: Annotated[list[str], VectorStoreField("data")]
    vector: Annotated[
        list[float] | None,
        VectorStoreField("vector", dimensions=2, distance_function="cosine_similarity"),
    ] = None


async def main() -> None:
    """Store precomputed vectors and search them with direct filters."""
    collection: InMemoryCollection[str, Hotel] = InMemoryCollection(Hotel)
    await collection.ensure_collection_exists()

    # 1. The sample already has vectors, so generation is disabled explicitly.
    await collection.upsert(
        [
            Hotel("hotel-1", "Harbor View", "Lisbon", 4.8, ["wifi", "pool"], [1.0, 0.1]),
            Hotel("hotel-2", "Old Town Rooms", "Lisbon", 4.1, ["wifi"], [0.8, 0.2]),
            Hotel("hotel-3", "City Center", "Seattle", 4.7, ["wifi", "gym"], [0.1, 1.0]),
        ],
        generate_vectors=False,
    )

    # 2. Filter values are ordinary data. No Python source is parsed or executed.
    search_filter = FilterGroup(
        "and",
        (
            Filter("city", "eq", "Lisbon"),
            Filter("rating", "between", (4.5, 5.0)),
            Filter("amenities", "contains", "pool"),
        ),
    )
    results = await collection.search(
        vector=[1.0, 0.0],
        filter=search_filter,
        top=5,
    )

    # 3. Search results are consumed asynchronously.
    async for result in results:
        print(f"{result['record'].name}: {result['score']:.3f}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
Harbor View: 0.995
"""
