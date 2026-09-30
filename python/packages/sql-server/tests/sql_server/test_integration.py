# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import uuid4

import pytest
from agent_framework import (
    Filter,
    FilterGroup,
    InMemoryCollection,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    vectorstoremodel,
)
from agent_framework.exceptions import IntegrationException

from agent_framework_sql_server import SqlServerCollection, SqlServerStore

pytestmark = [pytest.mark.flaky, pytest.mark.integration]


@pytest.fixture
def connection_string() -> str:
    value = os.getenv("SQL_SERVER_TEST_CONNECTION_STRING")
    if not value:
        pytest.skip("Set a non-empty SQL_SERVER_TEST_CONNECTION_STRING for a vector-enabled test database.")
    assert value is not None
    return value


@vectorstoremodel
@dataclass
class Note:
    id: Annotated[str, VectorStoreField("key", storage_name="record]id")]
    text: Annotated[str, VectorStoreField("data", storage_name="body [text]")]
    count: Annotated[int | None, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def test_typed_lifecycle_crud_search_and_portable_filters(connection_string: str) -> None:
    name = f"af_sql_test_{uuid4().hex}_]';--"
    async with SqlServerStore(connection_string=connection_string) as store:
        collection = store.get_collection(Note, collection_name=name)
        assert not await collection.collection_exists()
        await collection.ensure_collection_exists()
        try:
            assert await store.collection_exists(name)
            assert name in await store.list_collection_names()
            assert await collection.upsert(
                [
                    Note("same", "literal %_[ab]! sample", 1, [1, 0, 0]),
                    Note("other", "other [ab] sample", 2, [0, 1, 0]),
                    Note("null", "no embedding", None, None),
                ],
                generate_vectors=False,
            ) == ["same", "other", "null"]
            assert [item.id for item in await collection.get(["other", "absent", "same", "same"])] == [
                "other",
                "same",
                "same",
            ]
            assert (await collection.get(["same"], include_vectors=True))[0].embedding == [1, 0, 0]
            assert [item.id for item in await collection.get(filter=Filter("count", "is_null"))] == ["null"]
            assert [item.id for item in await collection.get(filter=Filter("count", "not_in", [1, None]))] == ["other"]
            assert [item.id for item in await collection.get(filter=Filter("text", "contains_text", "%_[ab]!"))] == [
                "same"
            ]

            results = [
                item
                async for item in await collection.search(
                    vector=[1, 0, 0],
                    filter=FilterGroup("not", [Filter("count", "gt", 1)]),
                    score_threshold=0.2,
                    top=1,
                )
            ]
            assert len(results) == 1 and results[0]["record"].id == "same"
            assert results[0]["score"] == pytest.approx(0)
            assert results[0]["record"].embedding is None

            await collection.upsert([Note("same", "updated", 4, [0, 1, 0])], generate_vectors=False)
            assert (await collection.get(["same"]))[0].text == "updated"
            await collection.delete(["missing", "other"])
            assert [item.id for item in await collection.get(order_by={"count": False})] == ["same", "null"]
        finally:
            await collection.ensure_collection_deleted()
        assert not await collection.collection_exists()


async def test_generated_key_and_vector_metrics(connection_string: str) -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="int", is_auto_generated=True),
            VectorStoreField("data", name="text", type_="str"),
            VectorStoreField(
                "vector",
                name="embedding",
                type_="float32",
                dimensions=3,
                distance_function="dot_prod",
            ),
        ],
        collection_name=f"af_sql_generated_{uuid4().hex}",
    )
    async with SqlServerStore(connection_string=connection_string) as store:
        collection = store.get_collection(dict, definition=definition)
        await collection.ensure_collection_exists()
        try:
            keys = await collection.upsert(
                [
                    {"text": "same", "embedding": [1, 0, 0]},
                    {"text": "opposite", "embedding": [-1, 0, 0]},
                ],
                generate_vectors=False,
            )
            assert len(keys) == 2 and all(type(key) is int for key in keys)
            results = [item async for item in await collection.search(vector=[1, 0, 0], score_threshold=0.5)]
            assert [item["record"]["id"] for item in results] == [keys[0]]
            assert results[0]["score"] == pytest.approx(1)
        finally:
            await collection.ensure_collection_deleted()


async def test_portable_scalar_filters_match_in_memory(connection_string: str) -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("data", name="text", type_="str"),
            VectorStoreField("data", name="count", type_="int"),
            VectorStoreField("data", name="flag", type_="bool"),
            VectorStoreField("vector", name="embedding", dimensions=3),
        ],
        collection_name=f"af_sql_filters_{uuid4().hex}",
    )
    rows: list[dict[str, Any]] = [
        {"id": "alpha", "text": "A[ab]%_! ", "count": 1, "flag": True, "embedding": [1, 0, 0]},
        {"id": "beta", "text": "Aabx", "count": 2, "flag": False, "embedding": [0, 1, 0]},
        {"id": "null", "text": None, "count": None, "flag": None, "embedding": None},
    ]
    filters: list[Filter | FilterGroup] = [
        Filter("text", "eq", "A[ab]%_! "),
        Filter("text", "ne", "A[ab]%_! "),
        Filter("text", "contains_text", "[ab]%_!"),
        Filter("text", "starts_with", "A["),
        Filter("text", "ends_with", "! "),
        Filter("count", "gt", 1),
        Filter("count", "between", [1, 2]),
        Filter("count", "in", [2, None]),
        Filter("count", "not_in", [2, None]),
        Filter("count", "eq", True),
        Filter("flag", "ne", 1),
        Filter("text", "is_null"),
        FilterGroup("not", [Filter("count", "gt", 1)]),
    ]
    memory = InMemoryCollection(dict, definition=definition)
    await memory.ensure_collection_exists()
    await memory.upsert(rows, generate_vectors=False)
    async with SqlServerStore(connection_string=connection_string) as store:
        collection = store.get_collection(dict, definition=definition)
        await collection.ensure_collection_exists()
        try:
            await collection.upsert(rows, generate_vectors=False)
            for expression in filters:
                expected = await memory.get(filter=expression)
                actual = await collection.get(filter=expression)
                assert {row["id"] for row in actual} == {row["id"] for row in expected}, repr(expression)
        finally:
            await collection.ensure_collection_deleted()


async def test_failed_batch_rolls_back_without_losing_prior_committed_write(connection_string: str) -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("data", name="count", type_="int"),
            VectorStoreField("vector", name="embedding", dimensions=3),
        ],
        collection_name=f"af_sql_tx_{uuid4().hex}",
    )
    async with SqlServerCollection(dict, connection_string=connection_string, definition=definition) as collection:
        await collection.ensure_collection_exists()
        try:
            constraint = f"af_check_{uuid4().hex}"

            def add_constraint(cursor):
                cursor.execute(f"ALTER TABLE {collection._table} ADD CONSTRAINT [{constraint}] CHECK ([count] >= 0)")

            await collection._client.run(add_constraint)
            await collection.upsert([{"id": "prior", "count": 1, "embedding": [1, 0, 0]}], generate_vectors=False)
            with pytest.raises(IntegrationException):
                await collection.upsert(
                    [
                        {"id": "new", "count": 2, "embedding": [1, 0, 0]},
                        {"id": "invalid", "count": -1, "embedding": [1, 0, 0]},
                    ],
                    generate_vectors=False,
                )
            assert [row["id"] for row in await collection.get()] == ["prior"]
        finally:
            await collection.ensure_collection_deleted()
