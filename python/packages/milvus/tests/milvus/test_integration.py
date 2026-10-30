# Copyright (c) Microsoft. All rights reserved.

"""Live integration tests against a real Milvus server.

These run only when MILVUS_TEST_URI is set (see the ``server_collection`` fixture) and are
selected with ``pytest -m integration`` / ``poe test-integration``.
"""

from __future__ import annotations

import pytest
from agent_framework import Filter

pytestmark = pytest.mark.integration


async def test_upsert_get_delete(server_collection, record):
    keys = await server_collection.upsert([record(1), record(2)], generate_vectors=False)
    assert sorted(keys) == [1, 2]

    loaded = await server_collection.get([1, 2])
    assert {item["id"] for item in loaded} == {1, 2}

    await server_collection.delete([1])
    assert await server_collection.get([1]) == []


async def test_vector_search_ranks_closest(server_collection, record):
    await server_collection.upsert(
        [
            record(1, embedding=[1.0, 0.0, 0.0]),
            record(2, embedding=[0.0, 1.0, 0.0]),
            record(3, embedding=[0.0, 0.0, 1.0]),
        ],
        generate_vectors=False,
    )
    results = [item async for item in await server_collection.search(vector=[1.0, 0.0, 0.0], top=3)]
    assert results[0]["record"]["id"] == 1
    assert results[0]["score"] is not None


async def test_filtered_search(server_collection, record):
    await server_collection.upsert(
        [record(1, number=1.0), record(2, number=2.0), record(3, number=3.0)],
        generate_vectors=False,
    )
    results = [
        item
        async for item in await server_collection.search(
            vector=[1.0, 0.0, 0.0], top=10, filter=Filter("number", "gte", 2.0)
        )
    ]
    assert {item["record"]["id"] for item in results} == {2, 3}


async def test_get_by_filter(server_collection, record):
    await server_collection.upsert([record(1), record(2, flag=False)], generate_vectors=False)
    matches = await server_collection.get(filter=Filter("flag", "eq", False), top=10)
    assert [item["id"] for item in matches] == [2]
