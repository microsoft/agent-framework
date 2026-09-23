# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import VectorStoreCollectionDefinition, VectorStoreField

from agent_framework_oracle import OracleCollection


@pytest.fixture
def definition_factory():
    def make(
        *,
        key_type="str",
        generated=False,
        vector_type="float32",
        dimensions=3,
        index_kind="flat",
        distance_function="DEFAULT",
        second_vector=False,
        data_type="str",
    ):
        fields = [
            VectorStoreField("key", name="id", type_=key_type, storage_name='doc"id', is_auto_generated=generated),
            VectorStoreField("data", name="text", type_=data_type, storage_name="body text"),
            VectorStoreField("data", name="number", type_="int"),
            VectorStoreField("data", name="flag", type_="bool"),
            VectorStoreField(
                "vector",
                name="embedding",
                type_=vector_type,
                storage_name="dense vector",
                dimensions=dimensions,
                index_kind=index_kind,
                distance_function=distance_function,
            ),
        ]
        if second_vector:
            fields.append(
                VectorStoreField(
                    "vector",
                    name="second",
                    type_="float64",
                    dimensions=dimensions,
                )
            )
        return VectorStoreCollectionDefinition(fields, collection_name="AF_DOCUMENTS")

    return make


@pytest.fixture
def record_factory():
    def make(id="one", *, text="Hello Oracle", number=2, flag=True, embedding=None, second=None):
        record = {
            "id": id,
            "text": text,
            "number": number,
            "flag": flag,
            "embedding": embedding if embedding is not None else [1.0, 0.0, 0.0],
        }
        if second is not None:
            record["second"] = second
        return record

    return make


@pytest.fixture
def collection(definition_factory):
    return OracleCollection(
        dict,
        definition=definition_factory(),
        dsn="unused",
        user="example",
        password="not-used",
    )


class FakeCursor:
    def __init__(self):
        self.execute = AsyncMock()
        self.executemany = AsyncMock()
        self.fetchone = AsyncMock(return_value=None)
        self.fetchall = AsyncMock(return_value=[])
        self.setinputsizes = MagicMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None


@pytest.fixture
def mock_database(collection):
    cursor = FakeCursor()
    connection = MagicMock()
    connection.cursor.return_value = cursor
    writes = []

    @asynccontextmanager
    async def acquire(*, write=False):
        writes.append(write)
        yield connection

    with patch.object(collection._client, "connection", side_effect=acquire) as mocked:
        yield connection, cursor, writes, mocked
