# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import VectorStoreCollectionDefinition, VectorStoreField
from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from agent_framework_azure_documentdb import AzureDocumentDBCollection


class AsyncCursor:
    def __init__(self, values: Sequence[dict[str, Any]]) -> None:
        self.values = list(values)
        self.skip_value = 0
        self.limit_value: int | None = None

    def skip(self, value: int) -> AsyncCursor:
        self.skip_value = value
        return self

    def limit(self, value: int) -> AsyncCursor:
        self.limit_value = value
        return self

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        async def iterate() -> AsyncIterator[dict[str, Any]]:
            end = None if self.limit_value is None else self.skip_value + self.limit_value
            for value in self.values[self.skip_value : end]:
                yield value

        return iterate()


@pytest.fixture
def definition_factory():
    def make(
        *,
        key_type: str = "str",
        generated: bool = False,
        dimensions: int = 3,
        index_kind: str = "ivf_flat",
        distance_function: str = "DEFAULT",
        annotations: dict[str, Any] | None = None,
        second_vector: bool = False,
        category_indexed: bool = True,
    ) -> VectorStoreCollectionDefinition:
        fields = [
            VectorStoreField("key", name="id", type_=key_type, storage_name="record_id", is_auto_generated=generated),
            VectorStoreField("data", name="text", type_="str", storage_name="body"),
            VectorStoreField("data", name="category", type_="str", is_indexed=category_indexed),
            VectorStoreField("data", name="number", type_="int", is_indexed=True),
            VectorStoreField("data", name="ratio", type_="float", is_indexed=True),
            VectorStoreField("data", name="flag", type_="bool", is_indexed=True),
            VectorStoreField("data", name="tags", type_="list", is_indexed=True),
            VectorStoreField(
                "vector",
                name="embedding",
                type_="float",
                storage_name="contentVector",
                dimensions=dimensions,
                index_kind=index_kind,
                distance_function=distance_function,
                provider_annotations=annotations,
            ),
        ]
        if second_vector:
            fields.append(
                VectorStoreField(
                    "vector",
                    name="secondary",
                    type_="float",
                    storage_name="titleVector",
                    dimensions=dimensions,
                    index_kind="ivf_flat",
                )
            )
        return VectorStoreCollectionDefinition(fields, collection_name="documents")

    return make


@pytest.fixture
def record_factory():
    def make(
        id: str | int = "one",
        *,
        text: str = "Azure DocumentDB",
        category: str | None = "database",
        number: Any = 1,
        ratio: Any = 1.5,
        flag: Any = True,
        tags: Any = None,
        embedding: Any = None,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "id": id,
            "text": text,
            "category": category,
            "number": number,
            "ratio": ratio,
            "flag": flag,
            "tags": ["azure", 1, True, None] if tags is None else tags,
            "embedding": [1.0, 0.0, 0.0] if embedding is None else embedding,
            **extra,
        }

    return make


@pytest.fixture
def pymongo_objects():
    client = MagicMock(spec=AsyncMongoClient)
    client.close = AsyncMock()
    database = MagicMock(spec=AsyncDatabase)
    database.name = "test_database"
    database.client = client
    database.list_collection_names = AsyncMock(return_value=["documents"])
    database.create_collection = AsyncMock()
    database.drop_collection = AsyncMock()
    database.command = AsyncMock(return_value={"ok": 1})
    collection = MagicMock(spec=AsyncCollection)
    collection.name = "documents"
    collection.database = database
    collection.bulk_write = AsyncMock()
    collection.delete_many = AsyncMock()
    collection.list_indexes = AsyncMock(return_value=AsyncCursor([{"name": "_id_", "key": {"_id": 1}}]))
    collection.aggregate = AsyncMock(return_value=AsyncCursor([]))
    collection.find = MagicMock(return_value=AsyncCursor([]))
    database.__getitem__.return_value = collection
    client.__getitem__.return_value = database
    return client, database, collection


@pytest.fixture
def collection(definition_factory, pymongo_objects):
    return AzureDocumentDBCollection(
        dict,
        definition=definition_factory(),
        collection=pymongo_objects[2],
    )
