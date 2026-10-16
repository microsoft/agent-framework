# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from agent_framework import VectorStoreCollectionDefinition, VectorStoreField
from pymilvus import AsyncMilvusClient, DataType

from agent_framework_milvus import MilvusCollection, MilvusStore

SERVER_MARKS = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("MILVUS_URI"), reason="Set MILVUS_URI to a disposable Milvus server."),
]


@pytest.fixture(autouse=True)
def clear_connection_environment(request, monkeypatch):
    # Integration tests connect to a real server via MILVUS_URI, so leave the environment intact.
    if request.node.get_closest_marker("integration"):
        return
    for name in ("MILVUS_URI", "MILVUS_TOKEN", "MILVUS_USER", "MILVUS_PASSWORD", "MILVUS_DB_NAME"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def definition():
    return VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int", storage_name="point_key"),
        VectorStoreField("data", name="text", type_="str", storage_name="body"),
        VectorStoreField("data", name="number", type_="float", storage_name="price"),
        VectorStoreField("data", name="flag", type_="bool"),
        VectorStoreField(
            "vector",
            name="embedding",
            storage_name="dense",
            dimensions=3,
            distance_function="cosine_similarity",
        ),
    ])


@pytest.fixture
def record():
    def make(id=1, **values):
        return {
            "id": id,
            "text": "hello",
            "number": float(id),
            "flag": True,
            "embedding": [1.0, 0.0, 0.0],
        } | values

    return make


@pytest.fixture
def mock_client():
    client = MagicMock(spec=AsyncMilvusClient)
    client.has_collection.return_value = True
    client.list_collections.return_value = ["docs"]
    client.get.return_value = [{"point_key": 1, "body": "hello", "price": 1.0, "flag": True}]
    client.query.return_value = [{"point_key": 1, "body": "hello", "price": 1.0, "flag": True}]
    client.search.return_value = [
        [
            {"id": 1, "distance": 0.95, "entity": {"body": "hello", "price": 1.0, "flag": True}},
            {"id": 2, "distance": 0.10, "entity": {"body": "world", "price": 2.0, "flag": False}},
        ]
    ]
    # Matches the `definition` fixture so ensure_collection_exists validates cleanly when present.
    client.describe_collection.return_value = {
        "collection_name": "docs",
        "fields": [
            {"name": "point_key", "type": DataType.INT64, "is_primary": True, "params": {}},
            {"name": "body", "type": DataType.VARCHAR, "params": {"max_length": 65535}},
            {"name": "price", "type": DataType.DOUBLE, "params": {}},
            {"name": "flag", "type": DataType.BOOL, "params": {}},
            {"name": "dense", "type": DataType.FLOAT_VECTOR, "params": {"dim": 3}},
        ],
    }
    client.describe_index.return_value = {"metric_type": "COSINE"}
    return client


@pytest.fixture
def collection(definition, mock_client):
    return MilvusCollection(dict, definition=definition, collection_name="docs", client=mock_client)


@pytest.fixture
def store(mock_client):
    return MilvusStore(client=mock_client)


@pytest.fixture
async def server_collection(definition):
    if not os.getenv("MILVUS_URI"):
        pytest.skip("Set MILVUS_URI to a disposable Milvus server.")
    async with MilvusStore(uri=os.environ["MILVUS_URI"]) as store:
        collection = store.get_collection(dict, definition=definition, collection_name=f"af_milvus_test_{uuid4().hex}")
        await collection.ensure_collection_exists()
        try:
            yield collection
        finally:
            await collection.ensure_collection_deleted()
