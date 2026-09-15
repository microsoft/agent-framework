# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from agent_framework import VectorStoreCollectionDefinition, VectorStoreField
from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from agent_framework_mongodb import MongoDBCollection


class AsyncCursor:
    def __init__(self, values: Iterable[dict[str, Any]]) -> None:
        self.values = list(values)
        self.sort_spec: list[tuple[str, int]] | None = None
        self.skip_count = 0
        self.limit_count: int | None = None

    def sort(self, spec: list[tuple[str, int]]) -> AsyncCursor:
        self.sort_spec = spec
        return self

    def skip(self, count: int) -> AsyncCursor:
        self.skip_count = count
        return self

    def limit(self, count: int) -> AsyncCursor:
        self.limit_count = count
        return self

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        async def iterate() -> AsyncIterator[dict[str, Any]]:
            values = self.values[self.skip_count :]
            if self.limit_count is not None:
                values = values[: self.limit_count]
            for value in values:
                yield value

        return iterate()


@pytest.fixture
def cursor_factory():
    return AsyncCursor


@pytest.fixture(autouse=True)
def clear_mongodb_environment(monkeypatch):
    for name in ("MONGODB_URI", "MONGODB_DATABASE_NAME", "MONGODB_APP_NAME"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def definition() -> VectorStoreCollectionDefinition:
    return VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int", storage_name="document_key"),
        VectorStoreField("data", name="text", type_="str", storage_name="body"),
        VectorStoreField("data", name="number", type_="float", is_indexed=True),
        VectorStoreField("data", name="integer", type_="int", is_indexed=True),
        VectorStoreField("data", name="flag", type_="bool", is_indexed=True),
        VectorStoreField("data", name="tags", type_="list"),
        VectorStoreField(
            "vector",
            name="embedding",
            storage_name="dense_text",
            dimensions=3,
            provider_annotations={"mongodb.index_name": "text_vector_index"},
        ),
        VectorStoreField(
            "vector",
            name="image",
            storage_name="dense_image",
            dimensions=3,
            distance_function="dot_prod",
        ),
    ])


@pytest.fixture
def record():
    def make(id: int = 1, **values: Any) -> dict[str, Any]:
        return {
            "id": id,
            "text": "hello",
            "number": float(id),
            "integer": id,
            "flag": True,
            "tags": ["one", "two"],
            "embedding": [1.0, 0.0, 0.0],
            "image": [0.0, 1.0, 0.0],
        } | values

    return make


@pytest.fixture
def mongo_mocks():
    client = AsyncMock(spec=AsyncMongoClient)
    database = AsyncMock(spec=AsyncDatabase)
    native_collection = AsyncMock(spec=AsyncCollection)
    client.get_database.return_value = database
    database.get_collection.return_value = native_collection
    database.list_collection_names.return_value = ["test"]
    return client, database, native_collection


@pytest.fixture
def collection(definition, mongo_mocks):
    client, _, _ = mongo_mocks
    return MongoDBCollection(
        dict,
        definition=definition,
        collection_name="test",
        async_client=client,
        database_name="vectors",
    )
