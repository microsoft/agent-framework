# Copyright (c) Microsoft. All rights reserved.

"""Explicitly opt-in service tests that own only a newly created disposable index."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from agent_framework import Filter, VectorStoreCollectionDefinition, VectorStoreField
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes.aio import SearchIndexClient

from agent_framework_azure_ai_search import AzureAISearchCollection

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(180),
    pytest.mark.skipif(
        os.getenv("AZURE_SEARCH_VECTOR_TESTS") != "1"
        or not os.getenv("AZURE_SEARCH_VECTOR_TEST_ENDPOINT")
        or not os.getenv("AZURE_SEARCH_VECTOR_TEST_API_KEY"),
        reason="Requires explicit disposable-index authorization and dedicated vector-test settings.",
    ),
]


async def test_disposable_index_1000_records_two_1536_vectors() -> None:
    name = f"af-vector-test-{uuid4().hex}"
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="key", storage_name="doc_id", type_="str"),
            VectorStoreField("data", name="text", type_="str", is_full_text_indexed=True),
            VectorStoreField(
                "data",
                name="ordinal",
                type_="int",
                is_indexed=True,
                provider_annotations={"azure_ai_search": {"sortable": True}},
            ),
            VectorStoreField("vector", name="vector", storage_name="embedding", dimensions=1536, type_="float"),
            VectorStoreField("vector", name="other", dimensions=1536, type_="float"),
        ],
        collection_name=name,
    )
    records = [
        {
            "key": str(i),
            "text": "deterministic hotel",
            "ordinal": i,
            "vector": [1.0, i / 1000, *([0.0] * 1534)],
            "other": [i / 1000, 1.0, *([0.0] * 1534)],
        }
        for i in range(1000)
    ]
    query_vector = records[0]["vector"]
    assert isinstance(query_vector, list)
    async with (
        SearchIndexClient(
            os.environ["AZURE_SEARCH_VECTOR_TEST_ENDPOINT"],
            AzureKeyCredential(os.environ["AZURE_SEARCH_VECTOR_TEST_API_KEY"]),
        ) as index_client,
        AzureAISearchCollection(dict, definition=definition, index_client=index_client) as collection,
    ):
        # Create, not ensure/update: never adopt or delete an index we did not create.
        await index_client.create_index(collection.build_index())
        try:
            assert len(await collection.upsert(records, generate_vectors=False)) == 1000
            for _ in range(60):
                if len(await collection.get(top=1000)) == 1000:
                    break
                await asyncio.sleep(0.5)
            else:
                pytest.fail("Index did not make all uploaded documents visible within 30 seconds.")
            found = await collection.get(["0", "999"], include_vectors=True)
            assert [row["key"] for row in found] == ["0", "999"]
            assert all(len(row["vector"]) == len(row["other"]) == 1536 for row in found)
            filtered = await collection.get(filter=Filter("ordinal", "lt", 3), order_by={"ordinal": True})
            assert [row["key"] for row in filtered] == ["0", "1", "2"]
            results = [
                r
                async for r in await collection.search(
                    vector=query_vector, top=2, skip=1, operation_options={"exhaustive": True}
                )
            ]
            assert [r["record"]["key"] for r in results] == ["1", "2"]
            hybrid = [
                r
                async for r in await collection.search(
                    "hotel",
                    vector=query_vector,
                    search_type="keyword_hybrid",
                    additional_property_name="text",
                    filter=Filter("ordinal", "lt", 3),
                )
            ]
            assert hybrid and all(int(r["record"]["key"]) < 3 for r in hybrid)
            await collection.delete(["0", "999"])
            for _ in range(60):
                if not await collection.get(["0", "999"]):
                    break
                await asyncio.sleep(0.5)
            else:
                pytest.fail("Deleted documents remained visible after 30 seconds.")
        finally:
            await collection.ensure_collection_deleted()
        assert not await collection.collection_exists()
