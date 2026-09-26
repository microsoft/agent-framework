# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from agent_framework import VectorStoreCollectionDefinition, VectorStoreField

from agent_framework_duckdb import DuckDBCollection, DuckDBStore


@pytest.fixture
def definition() -> VectorStoreCollectionDefinition:
    return VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str", storage_name='record "id"'),
            VectorStoreField("data", name="text", type_="str", storage_name='body "text"'),
            VectorStoreField("data", name="priority", type_="int"),
            VectorStoreField("data", name="active", type_="bool"),
            VectorStoreField("data", name="tags", type_="list"),
            VectorStoreField("vector", name="embedding", type_="float", storage_name="dense vector", dimensions=3),
        ],
        collection_name="documents",
    )


@pytest.fixture
def record_factory():
    def make(
        record_id: str = "one",
        *,
        text: str | None = "DuckDB stores vectors",
        priority: int | None = 1,
        active: bool = True,
        tags: list[Any] | None = None,
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": record_id,
            "text": text,
            "priority": priority,
            "active": active,
            "tags": ["example", True] if tags is None else tags,
            "embedding": [1.0, 0.0, 0.0] if embedding is None else embedding,
        }

    return make


@pytest.fixture
async def collection(
    tmp_path, definition: VectorStoreCollectionDefinition
) -> AsyncIterator[DuckDBCollection[Any, Any]]:
    async with DuckDBStore(connection_string=str(tmp_path / "vectors.duckdb")) as store:
        selected = store.get_collection(dict, definition=definition)
        await selected.ensure_collection_exists()
        yield selected
