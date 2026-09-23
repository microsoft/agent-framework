# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from agent_framework import Filter, VectorStoreCollectionDefinition, VectorStoreField

from agent_framework_oracle import OracleStore


def _oracle_test_database_configured() -> bool:
    return all(os.getenv(f"ORACLE_TEST_{name}") for name in ("DSN", "USER", "PASSWORD"))


pytestmark = [
    pytest.mark.integration,
    pytest.mark.flaky,
    pytest.mark.skipif(
        not _oracle_test_database_configured(),
        reason="Set ORACLE_TEST_DSN, ORACLE_TEST_USER, and ORACLE_TEST_PASSWORD for a disposable Oracle 23ai+ schema.",
    ),
]


async def test_oracle_vector_lifecycle_crud_filters_and_search():
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="str", storage_name="DOC_ID"),
        VectorStoreField("data", name="text", type_="str", storage_name="BODY"),
        VectorStoreField("data", name="amount", type_="int"),
        VectorStoreField("data", name="flag", type_="bool"),
        VectorStoreField("vector", name="embedding", type_="float32", dimensions=3),
        VectorStoreField("vector", name="second", type_="float64", dimensions=3, distance_function="dot_prod"),
    ])
    table = f"AF_ORACLE_TEST_{uuid4().hex}"
    async with OracleStore(
        dsn=os.environ["ORACLE_TEST_DSN"],
        user=os.environ["ORACLE_TEST_USER"],
        password=os.environ["ORACLE_TEST_PASSWORD"],
    ) as store:
        collection = store.get_collection(dict, definition=definition, collection_name=table)
        try:
            assert not await collection.collection_exists()
            await collection.ensure_collection_exists()
            await collection.ensure_collection_exists()
            assert table in await store.list_collection_names()
            first = {
                "id": "first",
                "text": "100%_! literal",
                "amount": 1,
                "flag": True,
                "embedding": [1.0, 0, 0],
                "second": [1.0, 0, 0],
            }
            second = {
                "id": "second",
                "text": "unrelated",
                "amount": 2,
                "flag": False,
                "embedding": [0, 1.0, 0],
                "second": [0, 1.0, 0],
            }
            assert await collection.upsert([first, second], generate_vectors=False) == ["first", "second"]
            assert await collection.get(["second", "first", "second"], include_vectors=True) == [
                second,
                first,
                second,
            ]
            assert [
                item["id"]
                for item in await collection.get(filter=Filter("amount", "gte", 1), order_by={"amount": False}, top=1)
            ] == ["second"]
            assert [item["id"] for item in await collection.get(filter=Filter("text", "contains_text", "%_"))] == [
                "first"
            ]
            results = [
                item
                async for item in await collection.search(
                    vector=[1, 0, 0],
                    filter=Filter("flag", "eq", True),
                    score_threshold=0.1,
                )
            ]
            assert [item["record"]["id"] for item in results] == ["first"]
            assert results[0]["score"] == pytest.approx(0.0)
            dot_results = [
                item
                async for item in await collection.search(
                    vector=[1, 0, 0],
                    vector_property_name="second",
                    score_threshold=0.5,
                )
            ]
            assert [item["record"]["id"] for item in dot_results] == ["first"]
            assert dot_results[0]["score"] == pytest.approx(1.0)
            await collection.upsert([dict(first, text="updated")], generate_vectors=False)
            assert (await collection.get(["first"]))[0]["text"] == "updated"
            await collection.delete(["first", "second"])
            assert await collection.get() == []
        finally:
            await collection.ensure_collection_deleted()
            assert not await collection.collection_exists()
