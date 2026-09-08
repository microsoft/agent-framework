# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os

import pytest
from agent_framework import Filter, FilterGroup, Param, create_vector_search_tool
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
    values = await collection.get(filter=expression, top=1, skip=1, order_by={"number": True})
    assert values[0]["id"] == 3
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


async def test_ordering_excludes_nulls_and_pages(server_collection, record):
    await server_collection.upsert(
        [
            record(1, number=None),
            record(2, number=2.0),
            record(3, number=1.0),
        ],
        generate_vectors=False,
    )
    assert [item["id"] for item in await server_collection.get(order_by={"number": True})] == [3, 2]
    assert await server_collection.get(order_by={"number": True}, skip=2, top=1) == []
