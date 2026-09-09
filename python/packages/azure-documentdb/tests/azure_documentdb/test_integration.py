# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from agent_framework import Filter, VectorStoreCollectionDefinition, VectorStoreField

from agent_framework_azure_documentdb import AzureDocumentDBCollection

pytestmark = [pytest.mark.flaky, pytest.mark.integration]

_CONNECTION_STRING = os.getenv("AZURE_DOCUMENTDB_TEST_CONNECTION_STRING")
_DATABASE_NAME = os.getenv("AZURE_DOCUMENTDB_TEST_DATABASE_NAME")
_WRITES_AUTHORIZED = os.getenv("AZURE_DOCUMENTDB_TEST_ALLOW_WRITES") == "true"
skip_if_managed_tests_disabled = pytest.mark.skipif(
    not _CONNECTION_STRING or not _DATABASE_NAME or not _WRITES_AUTHORIZED,
    reason=(
        "Set AZURE_DOCUMENTDB_TEST_CONNECTION_STRING, AZURE_DOCUMENTDB_TEST_DATABASE_NAME, and "
        "AZURE_DOCUMENTDB_TEST_ALLOW_WRITES=true for an authorized disposable managed test database."
    ),
)


def _vector(seed: int, *, dimensions: int = 1536) -> list[float]:
    return [((seed * 17 + index * 31) % 997) / 997 for index in range(dimensions)]


@skip_if_managed_tests_disabled
async def test_managed_documentdb_two_vector_fields_with_1000_records() -> None:
    assert _DATABASE_NAME is not None and "test" in _DATABASE_NAME.lower()
    collection_name = os.getenv("AZURE_DOCUMENTDB_TEST_COLLECTION_NAME") or f"af_vector_test_{uuid4().hex}"
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("data", name="category", type_="str", is_indexed=True),
            VectorStoreField(
                "vector",
                name="content_vector",
                type_="float",
                dimensions=1536,
                index_kind="ivf_flat",
                provider_annotations={"azure_documentdb.num_lists": 1},
            ),
            VectorStoreField(
                "vector",
                name="title_vector",
                type_="float",
                dimensions=1536,
                index_kind="ivf_flat",
                provider_annotations={"azure_documentdb.num_lists": 1},
            ),
        ],
        collection_name=collection_name,
    )
    connector = AzureDocumentDBCollection(
        dict,
        definition=definition,
        connection_string=_CONNECTION_STRING,
        database_name=_DATABASE_NAME,
    )
    await connector.ensure_collection_exists()
    try:
        records = [
            {
                "id": f"record-{index:04d}",
                "category": "even" if index % 2 == 0 else "odd",
                "content_vector": _vector(index),
                "title_vector": _vector(1000 - index),
            }
            for index in range(1000)
        ]
        keys = await connector.upsert(records, generate_vectors=False)
        assert len(keys) == 1000

        content_results = await connector.search(
            vector=_vector(0),
            vector_property_name="content_vector",
            filter=Filter("category", "eq", "even"),
            top=5,
        )
        content_page = [result async for result in content_results]
        assert content_page and content_page[0]["record"]["id"] == "record-0000"

        title_results = await connector.search(
            vector=_vector(1),
            vector_property_name="title_vector",
            top=5,
            include_vectors=True,
        )
        title_page = [result async for result in title_results]
        assert title_page and len(title_page[0]["record"]["title_vector"]) == 1536
    finally:
        await connector.ensure_collection_deleted()
        await connector.aclose()
