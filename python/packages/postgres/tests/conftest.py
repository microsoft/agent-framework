# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from agent_framework import VectorStoreCollectionDefinition, VectorStoreField
from psycopg import AsyncConnection, sql


@pytest.fixture
def definition_factory():
    def make(
        *,
        key_type="str",
        generated=False,
        dimensions=3,
        vector_type="float",
        index_kind="flat",
        distance_function="DEFAULT",
        annotations=None,
        second_vector=False,
    ):
        fields = [
            VectorStoreField("key", name="id", type_=key_type, storage_name="record_id", is_auto_generated=generated),
            VectorStoreField("data", name="text", type_="str", storage_name='body "text"', is_indexed=True),
            VectorStoreField("data", name="number", type_="int"),
            VectorStoreField("data", name="flag", type_="bool"),
            VectorStoreField("data", name="tags", type_="list"),
            VectorStoreField(
                "vector",
                name="embedding",
                type_=vector_type,
                storage_name="dense vector",
                dimensions=dimensions,
                index_kind=index_kind,
                distance_function=distance_function,
                provider_annotations=annotations,
            ),
        ]
        if second_vector:
            fields.append(
                VectorStoreField(
                    "vector",
                    name="secondary",
                    type_="float",
                    storage_name="other_vector",
                    dimensions=dimensions,
                )
            )
        return VectorStoreCollectionDefinition(fields, collection_name="documents")

    return make


@pytest.fixture
def record_factory():
    def make(id="one", *, text="literal 100%_!\\", number=1, flag=True, tags=None, embedding=None, **extra):
        return {
            "id": id,
            "text": text,
            "number": number,
            "flag": flag,
            "tags": tags if tags is not None else [True, 2, None, "tag"],
            "embedding": embedding if embedding is not None else [1.0, 0.0, 0.0],
            **extra,
        }

    return make


@pytest.fixture
async def database():
    connection_string = os.getenv("POSTGRES_TEST_CONNECTION_STRING")
    if not connection_string:
        pytest.skip("Set POSTGRES_TEST_CONNECTION_STRING to an explicitly designated test database.")
    async with await AsyncConnection.connect(connection_string, autocommit=True) as connection:
        cursor = await connection.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        version = await cursor.fetchone()
        if version is None:
            pytest.fail("The designated test database must already have the pgvector extension enabled.")
        schema = f"af_pg_test_{uuid4().hex}"
        await connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield connection, schema
        finally:
            cursor = await connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s", [schema]
            )
            for (name,) in await cursor.fetchall():
                await connection.execute(
                    sql.SQL("DROP TABLE {}.{}").format(sql.Identifier(schema), sql.Identifier(name))
                )
            await connection.execute(sql.SQL("DROP SCHEMA {}").format(sql.Identifier(schema)))
