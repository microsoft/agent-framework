# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import pytest
from agent_framework import Filter, VectorStoreCollectionDefinition, VectorStoreField
from pymilvus import DataType
from pymilvus.exceptions import MilvusException

from agent_framework_milvus import MilvusCollection, MilvusStore


async def test_upsert_returns_keys(collection, mock_client, record):
    keys = await collection.upsert([record(1), record(2)], generate_vectors=False)
    assert keys == [1, 2]
    mock_client.upsert.assert_called_once()
    assert mock_client.upsert.call_args.kwargs["collection_name"] == "docs"


async def test_upsert_empty(collection):
    assert await collection.upsert([], generate_vectors=False) == []


async def test_get_by_keys_maps_storage_to_model(collection, mock_client):
    records = await collection.get([1])
    assert records[0]["id"] == 1
    assert records[0]["text"] == "hello"
    assert records[0]["number"] == 1.0
    mock_client.get.assert_called_once()
    assert mock_client.get.call_args.kwargs["ids"] == [1]


async def test_get_without_keys_uses_query(collection, mock_client):
    records = await collection.get(top=5)
    assert records[0]["id"] == 1
    mock_client.query.assert_called_once()


async def test_get_empty_keys(collection):
    assert await collection.get([]) == []


async def test_get_rejects_order_by(collection):
    with pytest.raises(NotImplementedError):
        await collection.get(order_by={"number": False}, top=1)


async def test_delete(collection, mock_client):
    await collection.delete([1, 2])
    mock_client.delete.assert_called_once()
    assert mock_client.delete.call_args.kwargs["ids"] == [1, 2]


async def test_collection_exists(collection, mock_client):
    assert await collection.collection_exists() is True
    mock_client.has_collection.assert_called_with("docs")


async def test_ensure_collection_exists_creates_when_absent(collection, mock_client):
    mock_client.has_collection.return_value = False
    await collection.ensure_collection_exists()
    mock_client.create_collection.assert_called_once()
    assert mock_client.create_collection.call_args.kwargs["collection_name"] == "docs"


async def test_ensure_collection_exists_validates_when_present(collection, mock_client):
    mock_client.has_collection.return_value = True
    await collection.ensure_collection_exists()
    mock_client.create_collection.assert_not_called()
    mock_client.describe_collection.assert_called_once()


async def test_ensure_collection_exists_rejects_dimension_mismatch(collection, mock_client):
    mock_client.has_collection.return_value = True
    mock_client.describe_collection.return_value = {
        "fields": [
            {"name": "point_key", "type": DataType.INT64, "is_primary": True, "params": {}},
            {"name": "body", "type": DataType.VARCHAR, "params": {"max_length": 65535}},
            {"name": "price", "type": DataType.DOUBLE, "params": {}},
            {"name": "flag", "type": DataType.BOOL, "params": {}},
            {"name": "dense", "type": DataType.FLOAT_VECTOR, "params": {"dim": 99}},
        ]
    }
    with pytest.raises(ValueError, match="dimension"):
        await collection.ensure_collection_exists()


async def test_ensure_collection_exists_rejects_metric_mismatch(collection, mock_client):
    mock_client.has_collection.return_value = True
    mock_client.describe_index.return_value = {"metric_type": "L2"}
    with pytest.raises(ValueError, match="metric"):
        await collection.ensure_collection_exists()


async def test_ensure_collection_deleted(collection, mock_client):
    mock_client.has_collection.return_value = True
    await collection.ensure_collection_deleted()
    mock_client.drop_collection.assert_called_once_with("docs")


async def test_search_returns_records_and_scores(collection, mock_client):
    results = [item async for item in await collection.search(vector=[1.0, 0.0, 0.0], top=2)]
    assert [item["record"]["id"] for item in results] == [1, 2]
    assert [item["score"] for item in results] == [0.95, 0.10]
    assert mock_client.search.call_args.kwargs["anns_field"] == "dense"
    assert mock_client.search.call_args.kwargs["search_params"]["metric_type"] == "COSINE"


async def test_search_applies_filter(collection, mock_client):
    _ = [item async for item in await collection.search(vector=[1.0, 0.0, 0.0], filter=Filter("flag", "eq", True))]
    assert mock_client.search.call_args.kwargs["filter"] == "(flag == true)"


async def test_search_score_threshold_cosine(collection):
    results = [item async for item in await collection.search(vector=[1.0, 0.0, 0.0], score_threshold=0.5)]
    assert [item["record"]["id"] for item in results] == [1]


async def test_search_requires_query(collection):
    with pytest.raises(ValueError, match="values or a precomputed vector"):
        await collection.search(top=1)


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf")])
async def test_search_rejects_invalid_score_threshold(collection, bad):
    with pytest.raises(ValueError, match="score_threshold must be a finite number"):
        await collection.search(vector=[1.0, 0.0, 0.0], score_threshold=bad)


async def test_ensure_collection_exists_swallows_concurrent_create(collection, mock_client):
    # Another worker wins the race: create raises a genuine already-exists error, so ensure
    # semantics treat it as success (after validating the existing schema matches).
    mock_client.has_collection.return_value = False
    mock_client.create_collection.side_effect = MilvusException(message="collection already exist")
    await collection.ensure_collection_exists()  # must not raise
    mock_client.describe_collection.assert_called_once()


async def test_ensure_collection_exists_reraises_index_or_load_failure(collection, mock_client):
    # create_collection builds the collection then indexes/loads it; a later-step failure must
    # NOT be masked as success even though the collection now exists.
    mock_client.has_collection.return_value = False
    mock_client.create_collection.side_effect = MilvusException(message="create index failed")
    with pytest.raises(MilvusException, match="create index failed"):
        await collection.ensure_collection_exists()


async def test_ensure_collection_exists_reraises_non_milvus_error(collection, mock_client):
    mock_client.has_collection.return_value = False
    mock_client.create_collection.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        await collection.ensure_collection_exists()


def test_serialize_round_trip(collection):
    # The handler serializes a model to a storage-keyed dict before calling this method.
    storage_record = {"point_key": 7, "body": "hello", "price": 7.0, "flag": True, "dense": [1.0, 0.0, 0.0]}
    stored = collection._serialize_dicts_to_store_models([storage_record])
    assert stored[0] == storage_record
    back = collection._deserialize_store_models_to_dicts(stored)
    assert back[0]["point_key"] == 7
    assert back[0]["dense"] == [1.0, 0.0, 0.0]


def test_build_schema_has_primary_and_vector(collection):
    schema, _ = collection._build_schema_and_index()
    field_types = {field.name: field.dtype for field in schema.fields}
    assert field_types["point_key"] == DataType.INT64
    assert field_types["dense"] == DataType.FLOAT_VECTOR
    assert next(field for field in schema.fields if field.name == "point_key").is_primary


def test_auto_generated_key_rejected(mock_client):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int", is_auto_generated=True),
        VectorStoreField("vector", name="v", dimensions=3, distance_function="cosine_similarity"),
    ])
    with pytest.raises(NotImplementedError, match="application-provided primary keys"):
        MilvusCollection(dict, definition=definition, collection_name="docs", client=mock_client)


def test_is_indexed_rejected(mock_client):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("data", name="text", type_="str", is_indexed=True),
        VectorStoreField("vector", name="v", dimensions=3, distance_function="cosine_similarity"),
    ])
    with pytest.raises(NotImplementedError, match="is_indexed"):
        MilvusCollection(dict, definition=definition, collection_name="docs", client=mock_client)


def test_unsupported_distance_rejected(mock_client):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("vector", name="v", dimensions=3, distance_function="manhattan"),
    ])
    with pytest.raises(NotImplementedError, match="distance function"):
        MilvusCollection(dict, definition=definition, collection_name="docs", client=mock_client)


def test_client_and_settings_conflict(mock_client):
    with pytest.raises(ValueError, match="not both"):
        MilvusStore(client=mock_client, uri="http://localhost:19530")


async def test_store_list_collection_names(store, mock_client):
    assert await store.list_collection_names() == ["docs"]


async def test_store_get_collection_borrows_client(store, definition):
    collection = store.get_collection(dict, definition=definition, collection_name="docs")
    assert collection.client is store.client
    assert collection.managed_client is False


async def test_store_ensure_collection_deleted(store, mock_client):
    mock_client.has_collection.return_value = True
    await store.ensure_collection_deleted("docs")
    mock_client.drop_collection.assert_called_once()


async def test_injected_client_not_closed(collection, mock_client):
    await collection.aclose()
    mock_client.close.assert_not_called()
