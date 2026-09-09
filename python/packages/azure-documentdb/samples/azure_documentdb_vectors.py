# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-documentdb",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import Filter, VectorStoreField, vectorstoremodel

from agent_framework_azure_documentdb import AzureDocumentDBStore

"""
Use Azure DocumentDB with two top-level vector fields and an indexed metadata filter.

This sample uses deterministic vectors, not an embedding API. It creates and
deletes a uniquely named collection in the configured development database.
"""


@vectorstoremodel
@dataclass
class Note:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data")]
    category: Annotated[str, VectorStoreField("data", is_indexed=True)]
    title_vector: Annotated[
        list[float] | None,
        VectorStoreField("vector", dimensions=3, index_kind="ivf_flat"),
    ] = None
    body_vector: Annotated[
        list[float] | None,
        VectorStoreField("vector", dimensions=3, index_kind="ivf_flat"),
    ] = None


async def main() -> None:
    # 1. The store resolves AF settings and owns the PyMongo async client.
    async with AzureDocumentDBStore() as store:
        collection = store.get_collection(Note, collection_name=f"af_demo_{uuid4().hex}")
        await collection.ensure_collection_exists()
        try:
            # 2. Preserve the supplied vectors rather than calling an embedding API.
            await collection.upsert(
                [
                    Note("documentdb", "Azure DocumentDB stores vectors", "database", [1, 0, 0], [0, 1, 0]),
                    Note("travel", "A travel journal", "travel", [0, 1, 0], [1, 0, 0]),
                ],
                generate_vectors=False,
            )

            # 3. Select one vector path and apply the filter in cosmosSearch.
            results = await collection.search(
                vector=[1, 0, 0],
                vector_property_name="title_vector",
                filter=Filter("category", "eq", "database"),
            )
            async for result in results:
                print(result["record"].text, result["score"])

            # 4. Ordinary retrieval omits vectors unless explicitly requested.
            notes = await collection.get(["documentdb"], include_vectors=True)
            print(notes[0].body_vector)
        finally:
            await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())

# Expected output resembles:
# Azure DocumentDB stores vectors 1.0
# [0.0, 1.0, 0.0]
