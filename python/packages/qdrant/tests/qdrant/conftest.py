# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from agent_framework import VectorStoreCollectionDefinition, VectorStoreField
from qdrant_client import AsyncQdrantClient

from agent_framework_qdrant import QdrantCollection

SERVER_MARKS = [
    pytest.mark.integration,
    pytest.mark.flaky,
    pytest.mark.skipif(not os.getenv("QDRANT_TEST_URL"), reason="Set QDRANT_TEST_URL to a disposable Qdrant server."),
]


@pytest.fixture(autouse=True)
def clear_connection_environment(monkeypatch):
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)


@pytest.fixture(params=["local", pytest.param("server", marks=SERVER_MARKS)])
async def client(request):
    client = AsyncQdrantClient(
        location=":memory:" if request.param == "local" else None,
        url=os.getenv("QDRANT_TEST_URL") if request.param == "server" else None,
        check_compatibility=False,
    )
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
def definition():
    return VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int", storage_name="point_key"),
        VectorStoreField("data", name="text", type_="str", storage_name="body"),
        VectorStoreField("data", name="number", type_="float", storage_name="price", is_indexed=True),
        VectorStoreField("data", name="integer", type_="int"),
        VectorStoreField("data", name="flag", type_="bool"),
        VectorStoreField("data", name="tags", type_="list"),
        VectorStoreField(
            "vector", name="embedding", storage_name="dense_text", dimensions=3, distance_function="dot_prod"
        ),
        VectorStoreField(
            "vector", name="image", storage_name="dense_image", dimensions=3, distance_function="dot_prod"
        ),
    ])


@pytest.fixture
def record():
    def make(id=1, **values):
        return {
            "id": id,
            "text": "hello",
            "number": float(id),
            "integer": id,
            "flag": True,
            "tags": ["one", "two"],
            "embedding": [1.0, 0.0, 0.0],
            "image": [0.0, 1.0, 0.0],
        } | values

    return make


@pytest.fixture
async def collection_factory(client, definition):
    names: list[str] = []

    def make(record_type=dict, *, definition=definition, embedding_generator=None):
        name = f"af_qdrant_test_{uuid4().hex}"
        names.append(name)
        return QdrantCollection(
            record_type,
            async_client=client,
            collection_name=name,
            definition=definition if record_type is dict else None,
            embedding_generator=embedding_generator,
        )

    yield make
    for name in names:
        if await client.collection_exists(name):
            await client.delete_collection(name)


@pytest.fixture
async def server_collection(definition):
    if not os.getenv("QDRANT_TEST_URL"):
        pytest.skip("Set QDRANT_TEST_URL to a disposable Qdrant server.")
    async with QdrantCollection(
        dict,
        definition=definition,
        collection_name=f"af_qdrant_test_{uuid4().hex}",
        async_client=AsyncQdrantClient(url=os.environ["QDRANT_TEST_URL"], check_compatibility=False),
        managed_client=True,
    ) as collection:
        await collection.ensure_collection_exists()
        try:
            yield collection
        finally:
            await collection.ensure_collection_deleted()
