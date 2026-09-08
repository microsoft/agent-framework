# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from agent_framework import (
    Filter,
    FilterGroup,
    Param,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    create_vector_search_tool,
)
from agent_framework._vector_filters import filter_values_equal
from agent_framework.exceptions import IntegrationInvalidResponseException
from qdrant_client import models

from agent_framework_qdrant import QdrantCollection

pytestmark = [
    pytest.mark.integration,
    pytest.mark.flaky,
    pytest.mark.skipif(not os.getenv("QDRANT_TEST_URL"), reason="Set QDRANT_TEST_URL to a disposable Qdrant server."),
]


@pytest.fixture
async def payload_collection(server_collection):
    payloads = [
        {},
        {"body": None, "tags": None},
        {"body": "", "tags": []},
        {"body": "x' OR true %_*", "tags": ["one", "two"], "integer": 1, "price": 1.0, "flag": True},
        {"body": "other", "tags": ["two", True, 1.0], "integer": 2, "price": 2.0, "flag": False},
        {"body": "one", "tags": [None], "integer": 2**63 - 1},
        {"body": "two", "integer": -(2**63)},
    ]
    await server_collection.async_client.upsert(
        server_collection.collection_name,
        points=[models.PointStruct(id=index, vector={}, payload=payload) for index, payload in enumerate(payloads)],
        wait=True,
    )
    return server_collection


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (Filter("text", "exists"), [1, 2, 3, 4, 5, 6]),
        (Filter("text", "is_null"), [1]),
        (Filter("text", "is_not_null"), [2, 3, 4, 5, 6]),
        (Filter("text", "ne", "other"), [1, 2, 3, 5, 6]),
        (Filter("text", "eq", "x' OR true %_*"), [3]),
        (Filter("text", "in", ["other", None]), [4]),
        (Filter("text", "not_in", ["other"]), [2, 3, 5, 6]),
        (Filter("text", "not_in", []), [2, 3, 4, 5, 6]),
        (Filter("text", "in", []), []),
        (Filter("tags", "exists"), [1, 2, 3, 4, 5]),
        (Filter("tags", "is_null"), [1]),
        (Filter("tags", "is_not_null"), [2, 3, 4, 5]),
        (Filter("tags", "contains", "two"), [3, 4]),
        (Filter("tags", "contains", True), [4]),
        (Filter("tags", "contains", 1), [4]),
        (Filter("tags", "contains_any", ["one", "two"]), [3, 4]),
        (Filter("tags", "contains_any", []), []),
        (Filter("tags", "contains_all", ["one", "two"]), [3]),
        (Filter("tags", "contains_all", []), [2, 3, 4, 5]),
        (Filter("integer", "eq", 2**63 - 1), [5]),
        (Filter("integer", "ne", 2**63 - 1), [3, 4, 6]),
        (Filter("integer", "eq", -(2**63)), [6]),
        (Filter("integer", "eq", 1.0), [3]),
        (Filter("integer", "eq", True), []),
        (Filter("flag", "eq", 1), []),
        (Filter("flag", "eq", True), [3]),
        (Filter("number", "eq", 1), [3]),
        (Filter("number", "gt", 1), [4]),
        (Filter("number", "gte", 1), [3, 4]),
        (Filter("number", "lt", 2), [3]),
        (Filter("number", "lte", 2), [3, 4]),
        (Filter("number", "between", (1, 2)), [3, 4]),
        (Filter("integer", "gt", 2**53 - 1), [5]),
        (Filter("id", "in", [0, 3]), [0, 3]),
        (Filter("id", "not_in", [0, 3]), [1, 2, 4, 5, 6]),
        (Filter("id", "is_null"), []),
        (FilterGroup("not", [Filter("text", "eq", "other")]), [0, 1, 2, 3, 5, 6]),
        (
            FilterGroup(
                "and",
                [
                    Filter("text", "exists"),
                    FilterGroup(
                        "or",
                        [
                            Filter("text", "is_null"),
                            Filter("text", "eq", "other"),
                        ],
                    ),
                ],
            ),
            [1, 4],
        ),
        (
            FilterGroup("not", [FilterGroup("and", [Filter("integer", "gte", 1), Filter("flag", "eq", True)])]),
            [0, 1, 2, 4, 5, 6],
        ),
    ],
)
async def test_server_native_portable_semantics(payload_collection: QdrantCollection, expression, expected):
    collection = payload_collection
    points, _ = await collection.async_client.scroll(
        collection.collection_name,
        scroll_filter=collection._prepare_filter(expression),
        limit=100,
    )
    assert [point.id for point in points] == expected


async def test_filtered_get_search_and_tool_params(server_collection, record):
    collection = server_collection
    await collection.upsert(
        [
            record(1, text="tenant-a", embedding=[3, 0, 0]),
            record(2, text="tenant-b", embedding=[2, 0, 0]),
            record(3, text="tenant-a", embedding=[1, 0, 0]),
        ],
        generate_vectors=False,
    )
    expression = Filter("text", "eq", "tenant-a")
    values = await collection.get(filter=expression, top=1, skip=1)
    assert values[0]["id"] == 3
    with pytest.raises(NotImplementedError, match="order_by"):
        await collection.get(filter=expression, top=1, skip=1, order_by={"number": True})
    results = [item async for item in await collection.search(vector=[1, 0, 0], filter=expression, top=1, skip=1)]
    assert results[0]["record"]["id"] == 3
    assert [
        item
        async for item in await collection.search(
            vector=[1, 0, 0],
            filter=expression,
            score_threshold=4,
        )
    ] == []
    # A deterministic embedding client allows the actual search tool to run without an OpenAI dependency.
    from unittest.mock import AsyncMock

    from agent_framework import Embedding, GeneratedEmbeddings

    generator = AsyncMock()
    generator.get_embeddings.return_value = GeneratedEmbeddings([Embedding(vector=[1.0, 0, 0])])
    collection.embedding_generator = generator
    tool = create_vector_search_tool(
        collection,
        filter=Filter("text", "eq", Param("tenant", str, required=True)),
        result_mapper=lambda response: response["record"]["text"],
    )
    response = await tool.invoke(arguments={"query": "test", "tenant": "tenant-a"})
    assert len(response) == 2
    assert all(content.text == "tenant-a" for content in response)

    optional_tool = create_vector_search_tool(
        collection,
        filter=FilterGroup(
            "and",
            [
                Filter("integer", "gte", 2),
                Filter("text", "eq", Param("tenant", str | None, default=None, omit_if_none=True)),
            ],
        ),
        result_mapper=lambda response: str(response["record"]["id"]),
    )
    assert [content.text for content in await optional_tool.invoke(arguments={"query": "test"})] == ["2", "3"]
    assert [
        content.text
        for content in await optional_tool.invoke(
            arguments={"query": "test", "tenant": "tenant-a"},
        )
    ] == ["3"]


async def test_missing_payload_is_not_fabricated(payload_collection: QdrantCollection):
    with pytest.raises(IntegrationInvalidResponseException, match="missing required"):
        await payload_collection.get([0])


async def test_ordering_rejected_with_nulls_and_offsets(server_collection, record):
    await server_collection.upsert(
        [
            record(1, number=None),
            record(2, number=2.0),
            record(3, number=1.0),
        ],
        generate_vectors=False,
    )
    for skip in (0, 2):
        with pytest.raises(NotImplementedError, match="order_by"):
            await server_collection.get(order_by={"number": True}, skip=skip, top=1)


@pytest.mark.parametrize("ascending", [True, False])
@pytest.mark.parametrize("filtered", [True, False])
async def test_ordered_reads_rejected_with_large_ties(server_collection, record, ascending, filtered):
    collection = server_collection
    ids = list(range(1000))
    values = [record(index, number=float(index // 700), flag=index % 2 == 0) for index in reversed(ids)]
    await collection.upsert(values, generate_vectors=False)
    expression = Filter("flag", "eq", True) if filtered else None
    with (
        patch.object(collection.async_client, "scroll") as scroll,
        patch.object(collection.async_client, "query_points") as query_points,
    ):
        for skip in (0, 253, 1000):
            with pytest.raises(NotImplementedError, match="Omit order_by"):
                await collection.get(order_by={"number": ascending}, filter=expression, top=300, skip=skip)
        scroll.assert_not_awaited()
        query_points.assert_not_awaited()
    assert {item["id"] for item in await collection.get(top=1005)} == set(ids)


@pytest.mark.parametrize("operator", ["eq", "ne", "in", "not_in"])
async def test_portable_integer_key_filters(server_collection, record, operator):
    collection = server_collection
    keys = [0, 1, 2, 2**53 + 1, 2**63, 2**64 - 1]
    await collection.upsert([record(key, integer=0, number=0.0) for key in keys], generate_vectors=False)
    for value in [1.0, True, False, 1.5, -1, "1", 2**53 + 1, float(2**63), 2**64 - 1, float(2**64 - 1), 10**400]:
        operands = [value, True, None, "invalid"] if operator in {"in", "not_in"} else [value]
        expected = {
            key
            for key in keys
            if any(filter_values_equal(key, operand) for operand in operands) != (operator in {"ne", "not_in"})
        }
        records = await collection.get(
            filter=Filter("id", operator, operands if operator in {"in", "not_in"} else value)
        )
        assert {item["id"] for item in records} == expected


@pytest.mark.parametrize("key_type", ["str", "UUID"])
async def test_uuid_key_filters_preserve_identity(server_collection, key_type):
    definition = VectorStoreCollectionDefinition([VectorStoreField("key", name="id", type_=key_type)])
    collection = QdrantCollection(
        dict,
        definition=definition,
        collection_name=server_collection.collection_name,
        async_client=server_collection.async_client,
    )
    uuids = [uuid4(), uuid4()]
    keys = [str(key) for key in uuids] if key_type == "str" else uuids
    await collection.upsert([{"id": key} for key in keys], generate_vectors=False)
    assert [item["id"] for item in await collection.get(filter=Filter("id", "eq", str(uuids[0])))] == [keys[0]]
    assert [item["id"] for item in await collection.get(filter=Filter("id", "ne", str(uuids[0])))] == [keys[1]]
    assert await collection.get(filter=Filter("id", "eq", 1.0)) == []
    assert await collection.get(filter=Filter("id", "eq", True)) == []
    assert [item["id"] for item in await collection.get(filter=Filter("id", "in", [str(uuids[0]), 1, True]))] == [
        keys[0]
    ]
    assert [item["id"] for item in await collection.get(filter=Filter("id", "not_in", [str(uuids[0]), 1, True]))] == [
        keys[1]
    ]
