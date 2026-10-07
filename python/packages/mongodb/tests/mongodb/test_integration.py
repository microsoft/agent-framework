# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from agent_framework import (
    Filter,
    FilterGroup,
    InMemoryCollection,
    SecretString,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    register_vectorstoremodel,
)
from bson import ObjectId
from pymongo import AsyncMongoClient
from pymongo.errors import InvalidOperation

from agent_framework_mongodb import MongoDBCollection, MongoDBStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.flaky,
    pytest.mark.skipif(
        not os.getenv("MONGODB_TEST_URI"),
        reason="Set MONGODB_TEST_URI to a disposable Atlas or Atlas Local deployment.",
    ),
]


@pytest.fixture
async def mongodb_client():
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(os.environ["MONGODB_TEST_URI"])
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
def integration_definition() -> VectorStoreCollectionDefinition:
    return VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("data", name="text", type_="str"),
        VectorStoreField("data", name="category", type_="str", is_indexed=True),
        VectorStoreField("data", name="number", type_="float", is_indexed=True),
        VectorStoreField("data", name="integer", type_="int", is_indexed=True),
        VectorStoreField("data", name="flag", type_="bool", is_indexed=True),
        VectorStoreField("data", name="tags", type_="list"),
        VectorStoreField("vector", name="vector", dimensions=3),
    ])


@pytest.fixture
async def collections(mongodb_client, integration_definition):
    name = f"af_mongodb_test_{uuid4().hex}"
    database_name = os.getenv("MONGODB_TEST_DATABASE", "af_vectors_test")
    mongodb = MongoDBCollection(
        dict,
        definition=integration_definition,
        collection_name=name,
        async_client=mongodb_client,
        database_name=database_name,
    )
    memory = InMemoryCollection(dict, definition=integration_definition, collection_name=name)
    await mongodb.ensure_collection_exists(operation_options={"index_timeout": 300})
    await memory.ensure_collection_exists()
    try:
        yield mongodb, memory
    finally:
        await mongodb.ensure_collection_deleted()


async def test_crud_search_and_filter_parity(collections):
    mongodb, memory = collections
    records: list[dict[str, Any]] = [
        {
            "id": 1,
            "text": "alpha .* [literal]",
            "category": "database",
            "number": 1.0,
            "integer": 1,
            "flag": True,
            "tags": ["one", ["nested"]],
            "vector": [1.0, 0.0, 0.0],
        },
        {
            "id": 2,
            "text": "beta",
            "category": "database",
            "number": 2.0,
            "integer": 2,
            "flag": False,
            "tags": [],
            "vector": [0.9, 0.1, 0.0],
        },
        {
            "id": 3,
            "text": None,
            "category": "travel",
            "number": 3.0,
            "integer": 3,
            "flag": True,
            "tags": ["two"],
            "vector": [0.0, 1.0, 0.0],
        },
    ]
    for collection in (mongodb, memory):
        await collection.upsert(records, generate_vectors=False)

    expressions = [
        Filter("integer", "eq", 1),
        Filter("integer", "ne", 1),
        Filter("number", "eq", 1),
        Filter("number", "gt", 1),
        Filter("number", "gte", 2),
        Filter("number", "lt", 3),
        Filter("number", "lte", 2),
        Filter("number", "between", [1, 2]),
        Filter("integer", "in", [1, 3]),
        Filter("integer", "not_in", [1, 3]),
        Filter("flag", "eq", 1),
        Filter("text", "eq", "beta"),
        Filter("text", "ne", "beta"),
        Filter("tags", "eq", []),
        Filter("tags", "ne", []),
        Filter("tags", "in", [[], ["two"]]),
        Filter("tags", "not_in", [["one"]]),
        Filter("tags", "contains", ["nested"]),
        Filter("tags", "contains_any", ["two", "missing"]),
        Filter("tags", "contains_all", []),
        Filter("text", "starts_with", "alpha"),
        Filter("text", "ends_with", "beta"),
        Filter("text", "contains_text", ".* [literal]"),
        Filter("text", "is_null"),
        Filter("text", "is_not_null"),
        FilterGroup("and", [Filter("category", "eq", "database"), Filter("number", "gte", 2)]),
        FilterGroup("or", [Filter("integer", "eq", 1), Filter("integer", "eq", 3)]),
        FilterGroup("not", [Filter("flag", "eq", True)]),
    ]
    for expression in expressions:
        mongo_ids = [item["id"] for item in await mongodb.get(filter=expression, top=10)]
        memory_ids = [item["id"] for item in await memory.get(filter=expression, top=10)]
        assert mongo_ids == memory_ids, expression

    loaded = await mongodb.get([2, 1], include_vectors=True)
    assert [item["id"] for item in loaded] == [2, 1]
    assert loaded[0]["vector"] == [0.9, 0.1, 0.0]
    assert "vector" not in (await mongodb.get([1]))[0]

    results = []
    for _ in range(40):
        results = [
            item
            async for item in await mongodb.search(
                vector=[1, 0, 0],
                filter=Filter("category", "eq", "database"),
                score_threshold=0.5,
                operation_options={"exact": True},
            )
        ]
        if results:
            break
        await asyncio.sleep(0.25)
    assert [item["record"]["id"] for item in results] == [1, 2]
    assert all(0 <= item["score"] <= 1 for item in results)

    ann_results = [
        item
        async for item in await mongodb.search(
            vector=[1, 0, 0],
            filter=Filter("category", "eq", "database"),
            top=1,
            skip=1,
            operation_options={"num_candidates": 40},
        )
    ]
    assert [item["record"]["id"] for item in ann_results] == [2]

    await mongodb.delete([1, 999])
    assert await mongodb.get([1]) == []


async def test_missing_fields_do_not_match_null_or_negative_filters(collections):
    mongodb, _ = collections
    await mongodb._collection.insert_one({
        "_id": 100,
        "category": "external",
        "number": 100.0,
        "integer": 100,
        "flag": False,
        "tags": [],
        "vector": [0.0, 0.0, 1.0],
    })
    assert await mongodb.get(filter=Filter("text", "is_null")) == []
    assert await mongodb.get(filter=Filter("text", "ne", "anything")) == []
    assert await mongodb.get(filter=Filter("text", "not_in", ["anything"])) == []
    assert [item["id"] for item in await mongodb.get(filter=Filter("text", "exists"))] == []


async def test_realistic_multiple_1536_dimension_indexes(mongodb_client):
    dimensions = 1536
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("data", name="group", type_="int", is_indexed=True),
        VectorStoreField("vector", name="first", dimensions=dimensions),
        VectorStoreField("vector", name="second", dimensions=dimensions, distance_function="dot_prod"),
    ])
    collection = MongoDBCollection(
        dict,
        definition=definition,
        collection_name=f"af_mongodb_scale_{uuid4().hex}",
        async_client=mongodb_client,
        database_name=os.getenv("MONGODB_TEST_DATABASE", "af_vectors_test"),
    )
    await collection.ensure_collection_exists(operation_options={"create_indexes": False})
    try:
        records: list[dict[str, Any]] = [
            {
                "id": index,
                "group": index % 2,
                "first": [1.0 if position == index % dimensions else 0.0 for position in range(dimensions)],
                "second": [1.0 if position == (index + 1) % dimensions else 0.0 for position in range(dimensions)],
            }
            for index in range(1000)
        ]
        assert len(await collection.upsert(records, generate_vectors=False)) == 1000
        await collection.ensure_collection_exists(operation_options={"index_timeout": 300})
        results = [
            item
            async for item in await collection.search(
                vector=records[10]["second"],
                vector_property_name="second",
                top=2,
                operation_options={"exact": True},
            )
        ]
        assert results[0]["record"]["id"] == 10
    finally:
        await collection.ensure_collection_deleted()


async def test_generated_object_id_custom_codec_round_trip(mongodb_client):
    @dataclass
    class Document:
        id: ObjectId | None
        text: str
        vector: list[float] | None = None

    register_vectorstoremodel(
        Document,
        definition=VectorStoreCollectionDefinition([
            VectorStoreField("key", name="id", type_="ObjectId", is_auto_generated=True),
            VectorStoreField("data", name="text", type_="str"),
            VectorStoreField("vector", name="vector", dimensions=3),
        ]),
        encoder=lambda item: {"id": item.id, "text": item.text, "vector": item.vector},
        decoder=lambda item: Document(item["id"], item["text"], item.get("vector")),
    )
    collection = MongoDBCollection(
        Document,
        collection_name=f"af_mongodb_objectid_{uuid4().hex}",
        async_client=mongodb_client,
        database_name=os.getenv("MONGODB_TEST_DATABASE", "af_vectors_test"),
    )
    await collection.ensure_collection_exists(operation_options={"index_timeout": 300})
    try:
        key = (await collection.upsert([Document(None, "hello", [1, 0, 0])], generate_vectors=False))[0]
        assert isinstance(key, ObjectId)
        assert await collection.get([key]) == [Document(key, "hello")]
        assert await collection.get([key], include_vectors=True) == [Document(key, "hello", [1.0, 0.0, 0.0])]
        await collection.delete([key])
        assert await collection.get([key]) == []
    finally:
        await collection.ensure_collection_deleted()


async def test_connector_owned_uri_client_lifecycle():
    store = MongoDBStore(
        uri=SecretString(os.environ["MONGODB_TEST_URI"]),
        database_name=os.getenv("MONGODB_TEST_DATABASE", "af_vectors_test"),
        app_name="agent-framework-mongodb-integration",
    )
    async with store:
        await store.list_collection_names()
    with pytest.raises(InvalidOperation, match="after close"):
        await store.list_collection_names()
