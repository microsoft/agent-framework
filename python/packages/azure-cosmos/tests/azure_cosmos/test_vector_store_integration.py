# Copyright (c) Microsoft. All rights reserved.

"""Explicitly authorized cloud test for a unique, disposable Cosmos database."""

from __future__ import annotations

import os
from contextlib import suppress
from typing import cast
from uuid import uuid4

import pytest
from agent_framework import Filter, FilterGroup, VectorStoreCollectionDefinition, VectorStoreField
from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity.aio import AzureCliCredential

from agent_framework_azure_cosmos import CosmosCollection, CosmosStore

_USE_AZURE_CLI = os.getenv("AZURE_COSMOS_VECTOR_TEST_USE_AZURE_CLI") == "1"
_CREATE_DATABASE = os.getenv("AZURE_COSMOS_VECTOR_TEST_CREATE_DATABASE", "1") == "1"

pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.timeout(240),
    pytest.mark.filterwarnings("ignore::agent_framework._feature_stage.ExperimentalWarning"),
    pytest.mark.skipif(
        os.getenv("AZURE_COSMOS_VECTOR_TESTS") != "1"
        or not os.getenv("AZURE_COSMOS_ENDPOINT")
        or (not _USE_AZURE_CLI and not os.getenv("AZURE_COSMOS_KEY")),
        reason="Requires explicit disposable-database authorization and a vector-enabled Cosmos NoSQL account.",
    ),
]


async def test_disposable_vector_database_crud_filter_and_search() -> None:
    """Use a bounded exact index because no high-volume live-test cost is authorized by default."""
    database_name = os.getenv("AZURE_COSMOS_VECTOR_TEST_DATABASE_NAME", f"af-vector-{uuid4().hex}")
    container_name = os.getenv("AZURE_COSMOS_VECTOR_TEST_CONTAINER_NAME", f"items-{uuid4().hex}")
    default_container_name = os.getenv(
        "AZURE_COSMOS_VECTOR_TEST_DEFAULT_CONTAINER_NAME",
        f"items-default-{uuid4().hex}",
    )
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="key", storage_name="id", type_="str"),
            VectorStoreField("data", name="label", type_="str", is_indexed=True),
            VectorStoreField(
                "vector",
                name="vector",
                storage_name="embedding",
                type_="float32",
                dimensions=3,
                index_kind="flat",
                distance_function="cosine_similarity",
            ),
        ],
        collection_name=container_name,
    )
    credential: str | AzureCliCredential
    cli_credential: AzureCliCredential | None = None
    if _USE_AZURE_CLI:
        cli_credential = AzureCliCredential(
            tenant_id=os.getenv("AZURE_COSMOS_VECTOR_TEST_TENANT_ID", ""),
        )
        credential = cli_credential
    else:
        credential = os.environ["AZURE_COSMOS_KEY"]
    client = CosmosClient(
        os.environ["AZURE_COSMOS_ENDPOINT"],
        credential=credential,  # pyrefly: ignore[bad-argument-type]
    )
    store = CosmosStore(
        cosmos_client=client,
        database_name=database_name,
        create_database=_CREATE_DATABASE,
    )
    collection: CosmosCollection[dict] | None = None
    default_collection: CosmosCollection[dict] | None = None
    try:
        collection = store.get_collection(dict, definition=definition)
        await collection.ensure_collection_exists()
        records = [
            {"id": "one", "label": "first", "embedding": [1.0, 0.0, 0.0]},
            {"id": "two", "label": "second", "embedding": [0.0, 1.0, 0.0]},
            {"id": "three", "label": "third", "embedding": [0.0, 0.0, 1.0]},
        ]
        assert await collection.upsert(records, generate_vectors=False) == ["one", "two", "three"]
        assert [item["key"] for item in await collection.get(["one", "three"])] == ["one", "three"]
        assert [item["key"] for item in await collection.get(filter=Filter("label", "eq", "second"))] == ["two"]
        results = await collection.search(vector=[1.0, 0.0, 0.0], top=1)
        rows = [row async for row in results]
        assert rows[0]["record"]["key"] == "one"
        await collection.delete(["one", "two", "three"])
        assert await collection.get(["one", "two", "three"]) == []
        await collection.ensure_collection_deleted()

        default_definition = VectorStoreCollectionDefinition(
            [
                VectorStoreField("key", name="key", storage_name="id", type_="str"),
                VectorStoreField("data", name="category", type_="str", is_indexed=True),
                VectorStoreField("data", name="count", type_="int", is_indexed=True),
                VectorStoreField("data", name="active", type_="bool", is_indexed=True),
                VectorStoreField("data", name="tags", type_="list", is_indexed=True),
                VectorStoreField("data", name="optional", type_="str", is_indexed=True),
                VectorStoreField(
                    "vector",
                    name="cosine",
                    type_="float32",
                    dimensions=3,
                    distance_function="cosine_similarity",
                ),
                VectorStoreField(
                    "vector",
                    name="dot",
                    type_="float32",
                    dimensions=3,
                    index_kind="flat",
                    distance_function="dot_prod",
                ),
                VectorStoreField(
                    "vector",
                    name="euclidean",
                    type_="int8",
                    dimensions=3,
                    index_kind="flat",
                    distance_function="euclidean_distance",
                ),
                VectorStoreField(
                    "vector",
                    name="byte_vector",
                    type_="uint8",
                    dimensions=3,
                    index_kind="flat",
                    distance_function="cosine_similarity",
                ),
            ],
            collection_name=default_container_name,
        )
        default_collection = store.get_collection(dict, definition=default_definition)
        await default_collection.ensure_collection_exists()
        await default_collection.ensure_collection_exists()

        multi_records = [
            {
                "id": "one",
                "category": "a",
                "count": 1,
                "active": True,
                "tags": ["x", None],
                "optional": None,
                "cosine": [1.0, 0.0, 0.0],
                "dot": [2.0, 0.0, 0.0],
                "euclidean": [1, 0, 0],
                "byte_vector": [255, 0, 0],
            },
            {
                "id": "two",
                "category": "b",
                "count": 2,
                "active": False,
                "tags": [],
                "optional": "value",
                "cosine": [0.0, 1.0, 0.0],
                "dot": [1.0, 0.0, 0.0],
                "euclidean": [2, 0, 0],
                "byte_vector": [0, 255, 0],
            },
            {
                "id": "three",
                "category": "c",
                "count": 3,
                "active": True,
                "tags": ["y"],
                "optional": "other",
                "cosine": [-1.0, 0.0, 0.0],
                "dot": [0.0, 1.0, 0.0],
                "euclidean": [3, 0, 0],
                "byte_vector": [0, 0, 255],
            },
        ]
        assert await default_collection.upsert(multi_records, generate_vectors=False) == ["one", "two", "three"]

        sdk_container = client.get_database_client(database_name).get_container_client(default_container_name)
        properties = await sdk_container.read()
        assert properties["partitionKey"]["paths"] == ["/id"]
        assert {item["dataType"] for item in properties["vectorEmbeddingPolicy"]["vectorEmbeddings"]} == {
            "float32",
            "int8",
            "uint8",
        }
        assert {item["type"] for item in properties["indexingPolicy"]["vectorIndexes"]} == {
            "quantizedFlat",
            "flat",
        }

        cosine_results = [
            item
            async for item in await default_collection.search(
                vector=[1.0, 0.0, 0.0],
                vector_property_name="cosine",
                top=3,
                operation_options={"quantized_vector_list_multiplier": 5},
            )
        ]
        assert [item["record"]["key"] for item in cosine_results] == ["one", "two", "three"]
        assert [item["score"] for item in cosine_results] == pytest.approx([1.0, 0.0, -1.0])

        dot_results = [
            item
            async for item in await default_collection.search(
                vector=[1.0, 0.0, 0.0],
                vector_property_name="dot",
                top=3,
            )
        ]
        assert [item["record"]["key"] for item in dot_results] == ["one", "two", "three"]
        assert [item["score"] for item in dot_results] == pytest.approx([2.0, 1.0, 0.0])

        euclidean_results = [
            item
            async for item in await default_collection.search(
                vector=[1, 0, 0],
                vector_property_name="euclidean",
                top=3,
            )
        ]
        assert [item["record"]["key"] for item in euclidean_results] == ["one", "two", "three"]
        assert [item["score"] for item in euclidean_results] == pytest.approx([0.0, 1.0, 2.0])

        cosine_threshold = [
            item
            async for item in await default_collection.search(
                vector=[1.0, 0.0, 0.0],
                vector_property_name="cosine",
                filter=Filter("active", "eq", True),
                score_threshold=0.5,
                top=3,
            )
        ]
        assert [item["record"]["key"] for item in cosine_threshold] == ["one"]
        dot_threshold = [
            item
            async for item in await default_collection.search(
                vector=[1.0, 0.0, 0.0],
                vector_property_name="dot",
                score_threshold=1.5,
                top=3,
            )
        ]
        assert [item["record"]["key"] for item in dot_threshold] == ["one"]
        with pytest.raises(NotImplementedError, match="Omit score_threshold"):
            await default_collection.search(
                vector=[1, 0, 0],
                vector_property_name="euclidean",
                score_threshold=1.0,
                top=3,
            )

        assert [item["key"] for item in await default_collection.get(filter=Filter("optional", "is_null"))] == ["one"]
        assert [
            item["key"] for item in await default_collection.get(filter=Filter("tags", "contains_any", [None]))
        ] == ["one"]
        assert {item["key"] for item in await default_collection.get(filter=Filter("tags", "contains_all", []))} == {
            "one",
            "two",
            "three",
        }
        assert await default_collection.get(filter=Filter("count", "eq", True)) == []
        assert await default_collection.get(filter=Filter("active", "eq", 1)) == []

        missing_optional = {**multi_records[0], "id": "missing"}
        missing_optional.pop("optional")
        await sdk_container.upsert_item(missing_optional)
        exists_clause, exists_parameters = default_collection._prepare_filter(Filter("optional", "exists"))
        missing_clause, missing_parameters = default_collection._prepare_filter(
            FilterGroup("not", [Filter("optional", "exists")])
        )
        assert exists_clause is not None
        assert missing_clause is not None
        defined_ids = {
            cast(str, item)
            async for item in sdk_container.query_items(
                query=f"SELECT VALUE c.id FROM c WHERE {exists_clause}",  # noqa: S608
                parameters=exists_parameters,
            )
        }
        missing_ids = [
            cast(str, item)
            async for item in sdk_container.query_items(
                query=f"SELECT VALUE c.id FROM c WHERE {missing_clause}",  # noqa: S608
                parameters=missing_parameters,
            )
        ]
        assert defined_ids == {"one", "two", "three"}
        assert missing_ids == ["missing"]

        late_valid = {**multi_records[0], "id": "late-valid"}
        late_invalid = {**multi_records[1], "id": "late-invalid", "euclidean": [1, 2.5, 3]}
        with pytest.raises(TypeError, match="integer elements"):
            await default_collection.upsert([late_valid, late_invalid], generate_vectors=False)
        assert await default_collection.get(["late-valid"]) == []

        assert cosine_results[0]["record"].keys().isdisjoint({"cosine", "dot", "euclidean", "byte_vector"})
        assert cosine_results[0]["score"] == pytest.approx(1.0)
        await default_collection.delete(["one", "two", "three", "missing"])
        assert await default_collection.get(["one", "two", "three", "missing"]) == []
    finally:
        try:
            if _CREATE_DATABASE:
                with suppress(CosmosResourceNotFoundError):
                    await client.delete_database(database_name)
            else:
                for candidate in (default_collection, collection):
                    if candidate is not None:
                        await candidate.ensure_collection_deleted()
        finally:
            await store.close()
            await client.close()
            if cli_credential is not None:
                await cli_credential.close()
