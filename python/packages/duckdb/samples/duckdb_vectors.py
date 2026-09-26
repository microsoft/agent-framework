# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import Filter, VectorStoreField, vectorstoremodel

from agent_framework_duckdb import DuckDBStore

"""
Persist and reopen typed vector records in the default on-disk DuckDB database.

Run from python/:
    uv run --package agent-framework-duckdb python packages/duckdb/samples/duckdb_vectors.py

The default agent-framework.duckdb file remains in the working directory.
Only the uniquely named sample table is deleted. No service or API key is needed.
"""


@vectorstoremodel
@dataclass
class Note:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main() -> None:
    table_name = f"af_duckdb_example_{uuid4().hex}"
    async with DuckDBStore() as store:
        collection = store.get_collection(Note, collection_name=table_name)
        await collection.ensure_collection_exists()
        await collection.upsert(
            [Note("one", "A persistent DuckDB record", [1, 0, 0])],
            generate_vectors=False,
        )

    async with DuckDBStore() as reopened:
        collection = reopened.get_collection(Note, collection_name=table_name)
        try:
            print((await collection.get(["one"]))[0].text)
            results = await collection.search(
                vector=[1, 0, 0],
                filter=Filter("text", "contains_text", "DuckDB"),
            )
            async for result in results:
                print(result["record"].text, result["score"])
        finally:
            await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())
