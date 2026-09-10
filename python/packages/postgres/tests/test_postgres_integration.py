# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from dataclasses import dataclass, make_dataclass
from datetime import date, datetime, timezone
from types import GenericAlias
from typing import Annotated, Any
from uuid import UUID, uuid4

import pytest
from agent_framework import (
    Embedding,
    Filter,
    FilterGroup,
    GeneratedEmbeddings,
    InMemoryCollection,
    Param,
    SecretString,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    create_vector_search_tool,
    register_vectorstoremodel,
    vectorstoremodel,
)
from agent_framework.exceptions import IntegrationException
from psycopg import AsyncConnection, AsyncCursor, sql
from psycopg_pool import AsyncConnectionPool
from typing_extensions import Self

from agent_framework_postgres import PostgresCollection, PostgresStore

pytestmark = pytest.mark.integration


async def test_lifecycle_crud_multiple_vectors_and_aliases(database, definition_factory, record_factory):
    connection, schema = database
    async with PostgresStore(client=connection, schema=schema) as store:
        collection = store.get_collection(
            dict, definition=definition_factory(second_vector=True), collection_name='quoted"; -- table'
        )
        assert not await collection.collection_exists()
        assert await store.list_collection_names() == []
        await collection.ensure_collection_exists()
        await collection.ensure_collection_exists()
        assert await store.collection_exists('quoted"; -- table')
        assert await collection.get() == []
        assert [
            item async for item in await collection.search(vector=[1, 0, 0], vector_property_name="embedding")
        ] == []
        records = [record_factory("a", secondary=[0, 1, 0]), record_factory("b", secondary=None)]
        assert await collection.upsert(records, generate_vectors=False) == ["a", "b"]
        assert await collection.get(["a", "missing", "a"], include_vectors=True) == [records[0], records[0]]
        assert all("embedding" not in row and "secondary" not in row for row in await collection.get())
        results = [
            item
            async for item in await collection.search(
                vector=[0, 1, 0],
                vector_property_name="secondary",
                include_vectors=True,
            )
        ]
        assert [item["record"]["id"] for item in results] == ["a"]
        assert results[0]["record"]["secondary"] == [0, 1, 0]
        await collection.close()
        assert not connection.closed
        await collection.delete(["missing", "a"])
        assert [row["id"] for row in await collection.get()] == ["b"]
        await store.ensure_collection_deleted('quoted"; -- table')
        await store.ensure_collection_deleted('quoted"; -- table')
        assert not await collection.collection_exists()
    assert not connection.closed


async def test_filters_match_portable_semantics_in_database(database, definition_factory, record_factory):
    connection, schema = database
    definition = definition_factory()
    postgres = PostgresCollection(dict, client=connection, schema=schema, definition=definition)
    memory = InMemoryCollection(dict, definition=definition)
    rows = [
        record_factory("a", text="100%_!\\ exact", number=1, flag=True, tags=[True, None, "tag", ["x", True]]),
        record_factory("b", text="100xx!\\ exact", number=2, flag=False, tags=[1, "other", ["x", 1]]),
        record_factory("c", text="", number=3, flag=True, tags=[]),
        {**record_factory("d"), "text": None, "number": None, "flag": None, "tags": None, "embedding": None},
    ]
    await postgres.ensure_collection_exists()
    await memory.ensure_collection_exists()
    await postgres.upsert(rows, generate_vectors=False)
    await memory.upsert(rows, generate_vectors=False)
    expressions: list[Filter | FilterGroup] = [
        Filter("number", "eq", 1),
        Filter("number", "eq", True),
        Filter("flag", "eq", 1),
        Filter("flag", "eq", True),
        Filter("number", "ne", True),
        Filter("flag", "ne", 1),
        Filter("number", "ne", 1),
        Filter("number", "gt", 1),
        Filter("number", "gte", 2),
        Filter("number", "lt", 2),
        Filter("number", "lte", 2),
        Filter("number", "between", [1, 2]),
        Filter("number", "between", [2, 1]),
        Filter("number", "in", [True, 2, None]),
        Filter("number", "not_in", [True, 2, None]),
        Filter("number", "in", []),
        Filter("number", "not_in", []),
        Filter("number", "exists"),
        Filter("number", "is_null"),
        Filter("number", "is_not_null"),
        Filter("tags", "contains", True),
        Filter("tags", "contains", 1),
        Filter("tags", "contains_any", [None]),
        Filter("tags", "contains", ["x", True]),
        Filter("tags", "contains_any", [True, "other"]),
        Filter("tags", "contains_all", [True, "tag"]),
        Filter("tags", "contains_any", []),
        Filter("tags", "contains_all", []),
        Filter("tags", "eq", []),
        Filter("text", "contains_text", "%_"),
        Filter("text", "starts_with", "100%"),
        Filter("text", "ends_with", "!\\ exact"),
        Filter("text", "contains_text", ""),
        Filter("text", "contains_text", "'; DROP TABLE documents; --"),
        FilterGroup("not", [Filter("number", "gt", 2)]),
        FilterGroup("not", [Filter("text", "contains_text", "%_")]),
        FilterGroup("not", [Filter("number", "not_in", [1])]),
        FilterGroup(
            "and",
            [
                Filter("number", "lte", 2),
                FilterGroup(
                    "or",
                    [
                        Filter("flag", "eq", True),
                        Filter("tags", "contains", "other"),
                    ],
                ),
            ],
        ),
    ]
    for expression in expressions:
        expected = await memory.get(filter=expression, top=10)
        actual = await postgres.get(filter=expression, top=10)
        assert {row["id"] for row in actual} == {row["id"] for row in expected}, repr(expression)
        # Exercise the same filters in native vector queries. Row d has no vector.
        results = [
            item
            async for item in await postgres.search(
                vector=[1, 0, 0],
                filter=expression,
                top=10,
                score_threshold=0.1,
            )
        ]
        assert {item["record"]["id"] for item in results} == {row["id"] for row in expected} - {"d"}, repr(expression)
    assert [row["id"] for row in await postgres.get(order_by={"number": False}, top=2, skip=1)] == ["b", "a"]


@pytest.mark.parametrize(
    "metric,query,expected,threshold,accepted",
    [
        ("DEFAULT", [1, 0, 0], [0, 1, 2], 1, ["same", "orthogonal"]),
        ("cosine_distance", [1, 0, 0], [0, 1, 2], 1, ["same", "orthogonal"]),
        ("cosine_similarity", [1, 0, 0], [1, 0, -1], 0, ["same", "orthogonal"]),
        ("dot_prod", [2, 0, 0], [2, 0, -2], 0, ["same", "orthogonal"]),
        ("negative_dot_prod", [2, 0, 0], [-2, 0, 2], 0, ["same", "orthogonal"]),
        ("euclidean_distance", [1, 0, 0], [0, 2**0.5, 2], 1.5, ["same", "orthogonal"]),
        ("manhattan", [2, 0, 0], [1, 3, 3], 1, ["same"]),
    ],
)
async def test_metric_units_threshold_ranking_and_offset(
    database,
    definition_factory,
    record_factory,
    metric,
    query,
    expected,
    threshold,
    accepted,
):
    connection, schema = database
    collection = PostgresCollection(
        dict, client=connection, schema=schema, definition=definition_factory(distance_function=metric)
    )
    await collection.ensure_collection_exists()
    rows = [
        record_factory("opposite", embedding=[-1, 0, 0]),
        record_factory("orthogonal", embedding=[0, 1, 0]),
        record_factory("same", embedding=[1, 0, 0]),
    ]
    await collection.upsert(rows, generate_vectors=False)
    results = [item async for item in await collection.search(vector=query, top=10)]
    assert [item["score"] for item in results] == pytest.approx(expected)
    assert results[0]["record"]["id"] == "same"
    filtered = [item async for item in await collection.search(vector=query, score_threshold=threshold, top=10)]
    assert [item["record"]["id"] for item in filtered] == accepted
    page = [item async for item in await collection.search(vector=query, score_threshold=threshold, skip=1, top=1)]
    assert [item["record"]["id"] for item in page] == accepted[1:2]
    assert all("embedding" not in item["record"] for item in results)


@pytest.mark.parametrize("key_type,explicit", [("int", 1000), ("UUID", UUID(int=5)), ("str", "chosen")])
async def test_generated_and_preserved_typed_keys(database, definition_factory, record_factory, key_type, explicit):
    connection, schema = database
    collection = PostgresCollection(
        dict, client=connection, schema=schema, definition=definition_factory(key_type=key_type, generated=True)
    )
    await collection.ensure_collection_exists()
    omitted = record_factory()
    del omitted["id"]
    keys = await collection.upsert([record_factory(None), record_factory(explicit), omitted], generate_vectors=False)
    assert keys[1] == explicit
    assert len(set(keys)) == 3
    assert all(type(key).__name__ == key_type for key in keys)
    assert [row["id"] for row in await collection.get(list(reversed(keys)))] == list(reversed(keys))
    await collection.upsert(
        [record_factory(explicit, text="updated"), record_factory(explicit, text="last")], generate_vectors=False
    )
    assert (await collection.get([explicit]))[0]["text"] == "last"
    await collection.delete(keys)
    assert await collection.get() == []


async def test_atomic_batch_failure_does_not_rollback_callers_prior_work(database, definition_factory, record_factory):
    connection, schema = database
    collection = PostgresCollection(dict, client=connection, schema=schema, definition=definition_factory())
    await collection.ensure_collection_exists()
    async with connection.transaction():
        await collection.upsert([record_factory("prior")], generate_vectors=False)
        with pytest.raises(IntegrationException):
            # The driver sends both records; pgvector rejects infinity in the second row.
            await collection.upsert(
                [
                    record_factory("new"),
                    record_factory("bad", embedding=[float("inf"), 0, 0]),
                ],
                generate_vectors=False,
            )
        assert [row["id"] for row in await collection.get()] == ["prior"]
    assert [row["id"] for row in await collection.get()] == ["prior"]
    with pytest.raises(ValueError, match="index 1"):
        await collection.upsert([record_factory("new"), record_factory("bad", embedding=[1])], generate_vectors=False)
    assert [row["id"] for row in await collection.get()] == ["prior"]


async def test_owned_pool_and_borrowed_pool_lifetimes(database, definition_factory, record_factory):
    _, schema = database
    conninfo = os.environ["POSTGRES_TEST_CONNECTION_STRING"]
    store = PostgresStore(connection_string=conninfo, schema=schema)
    collection = store.get_collection(dict, definition=definition_factory())
    assert store._client.client.closed
    await collection.ensure_collection_exists()
    assert not store._client.client.closed
    await collection.upsert([record_factory()], generate_vectors=False)
    await collection.close()
    assert await collection.get(["one"])
    await store.close()
    assert store._client.client.closed
    with pytest.raises(RuntimeError, match="closed"):
        await collection.collection_exists()
    async with AsyncConnectionPool[AsyncConnection[Any]](conninfo, open=False) as pool:
        async with PostgresStore(client=pool, schema=schema) as borrowed:
            child = borrowed.get_collection(dict, definition=definition_factory())
            assert await child.get(["one"])
        assert not pool.closed
        async with pool.connection() as connection:
            assert await (await connection.execute("SELECT 1")).fetchone() == (1,)


@pytest.mark.parametrize("source", ["environment", "file", "secret"])
@pytest.mark.parametrize("kind", ["collection", "store"])
async def test_settings_resolved_owned_connections(
    database,
    definition_factory,
    record_factory,
    monkeypatch,
    tmp_path,
    source,
    kind,
):
    _, schema = database
    conninfo = os.environ["POSTGRES_TEST_CONNECTION_STRING"]
    options: dict[str, Any] = {}
    if source == "environment":
        monkeypatch.setenv("POSTGRES_CONNECTION_STRING", conninfo)
    elif source == "file":
        monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "host=must_not_connect")
        env_file = tmp_path / "postgres.env"
        env_file.write_text(f"POSTGRES_CONNECTION_STRING='{conninfo}'\n", encoding="utf-8")
        options["env_file_path"] = str(env_file)
    else:
        monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "host=must_not_connect")
        options["connection_string"] = SecretString(conninfo)
    owner = (
        PostgresStore(schema=schema, **options)
        if kind == "store"
        else PostgresCollection(dict, schema=schema, definition=definition_factory(), **options)
    )
    async with owner:
        collection = (
            owner.get_collection(dict, definition=definition_factory()) if isinstance(owner, PostgresStore) else owner
        )
        await collection.ensure_collection_exists()
        await collection.upsert([record_factory()], generate_vectors=False)
        assert (await collection.get(["one"]))[0]["id"] == "one"
        results = [item async for item in await collection.search(vector=[1, 0, 0], score_threshold=0)]
        assert [item["record"]["id"] for item in results] == ["one"]
    assert owner._client.client.closed


@pytest.mark.parametrize(
    "index_kind,annotations",
    [
        ("hnsw", {"postgres.m": 8, "postgres.ef_construction": 32}),
        ("ivf_flat", {"postgres.lists": 1}),
        ("hnsw", {"postgres.vector_type": "halfvec"}),
    ],
)
@pytest.mark.parametrize("approximate_options", [{}, {"exact": False}])
async def test_ann_indexes_creation_filtered_query_and_exact_override(
    database,
    definition_factory,
    record_factory,
    index_kind,
    annotations,
    approximate_options,
):
    connection, schema = database
    collection = PostgresCollection(
        dict,
        client=connection,
        schema=schema,
        definition=definition_factory(index_kind=index_kind, annotations=annotations),
    )
    if index_kind == "ivf_flat":
        with pytest.raises(ValueError, match="training"):
            await collection.ensure_collection_exists()
        assert not await collection.collection_exists()
        await collection.ensure_collection_exists(operation_options={"create_indexes": False})
    else:
        await collection.ensure_collection_exists()
    records = [record_factory(str(i), number=i, embedding=[1, i / 100, 0]) for i in range(100)]
    await collection.upsert(records, generate_vectors=False)
    await collection.ensure_collection_exists()
    cursor = await connection.execute("SELECT indexdef FROM pg_indexes WHERE schemaname = %s", [schema])
    indexes = [row[0] for row in await cursor.fetchall()]
    assert any(("USING hnsw" if index_kind == "hnsw" else "USING ivfflat") in item for item in indexes)
    if annotations.get("postgres.vector_type") == "halfvec":
        assert (await collection.get(["0"], include_vectors=True))[0]["embedding"] == [1, 0, 0]
    options = {"hnsw_ef_search": 100} if index_kind == "hnsw" else {"ivfflat_probes": 1}
    search_results = await collection.search(
        vector=(1, 0, 0),
        filter=Filter("number", "gte", 90),
        top=3,
        operation_options={**options, **approximate_options},
    )
    assert search_results.metadata is not None
    assert search_results.metadata["approximate"] is True
    results = [item async for item in search_results]
    assert [item["record"]["id"] for item in results] == ["90", "91", "92"]
    search_results = await collection.search(
        vector=(1, 0, 0),
        filter=Filter("number", "gte", 90),
        top=3,
        operation_options={"exact": True},
    )
    assert search_results.metadata is not None
    assert search_results.metadata["approximate"] is False
    results = [item async for item in search_results]
    assert [item["record"]["id"] for item in results] == ["90", "91", "92"]


@pytest.mark.parametrize(
    "vector_type,annotations",
    [
        ("float", None),
        ("float32", None),
        ("float16", None),
        ("float", {"postgres.vector_type": "halfvec"}),
        ("float32", {"postgres.vector_type": "halfvec"}),
        ("float16", {"postgres.vector_type": "vector"}),
    ],
)
async def test_floating_vector_types_preserve_typed_roundtrips(database, vector_type, annotations):
    @dataclass
    class FloatingRecord:
        id: str
        embedding: list[float] | None = None

    register_vectorstoremodel(
        FloatingRecord,
        definition=VectorStoreCollectionDefinition(
            [
                VectorStoreField("key", name="id", type_="str"),
                VectorStoreField(
                    "vector", name="embedding", dimensions=3, type_=vector_type, provider_annotations=annotations
                ),
            ],
            collection_name="floating_vectors",
        ),
    )
    connection, schema = database
    collection = PostgresCollection(FloatingRecord, client=connection, schema=schema)
    await collection.ensure_collection_exists()
    await collection.upsert([FloatingRecord("one", [0.1, 1, 0])], generate_vectors=False)
    records = await collection.get(["one"], include_vectors=True)
    assert len(records) == 1
    assert isinstance(records[0], FloatingRecord)
    assert records[0].embedding == pytest.approx([0.1, 1, 0], rel=1e-3)
    results = [item async for item in await collection.search(vector=(0.1, 1, 0), include_vectors=True)]
    assert len(results) == 1
    assert results[0]["record"] == records[0]
    results = [item async for item in await collection.search(vector=range(3))]
    assert [item["record"].id for item in results] == ["one"]


@pytest.mark.parametrize("scalar_name", ["float16", "float32"])
async def test_numpy_scalar_annotations_roundtrip_with_custom_decoder(database, scalar_name):
    np = pytest.importorskip("numpy")
    scalar_type = getattr(np, scalar_name)
    record_type = make_dataclass(
        "NumpyRecord",
        [
            ("id", str),
            ("embedding", GenericAlias(list, scalar_type) | None, None),
        ],
    )

    def decode_record(row):
        vector = row.get("embedding")
        return record_type(
            id=row["id"],
            embedding=[scalar_type(value) for value in vector] if vector is not None else None,
        )

    register_vectorstoremodel(
        record_type,
        definition=VectorStoreCollectionDefinition(
            [
                VectorStoreField("key", name="id", type_="str"),
                VectorStoreField("vector", name="embedding", dimensions=3, type_=scalar_name),
            ],
            collection_name="numpy_vectors",
        ),
        decoder=decode_record,
    )
    connection, schema = database
    collection = PostgresCollection(record_type, client=connection, schema=schema)
    assert collection.definition.vector_fields[0].type_ == scalar_name
    await collection.ensure_collection_exists()
    original = record_type("one", [scalar_type(0.1), scalar_type(1), scalar_type(0)])
    await collection.upsert([original], generate_vectors=False)

    records = await collection.get(["one"], include_vectors=True)
    results = [item async for item in await collection.search(vector=(0.1, 1, 0), include_vectors=True)]
    assert len(records) == len(results) == 1
    for restored in (records[0], results[0]["record"]):
        assert isinstance(restored, record_type)
        assert restored == original
        assert all(isinstance(value, scalar_type) for value in vars(restored)["embedding"])
    assert vars((await collection.get(["one"]))[0])["embedding"] is None


async def test_missing_schema_is_not_created(database, definition_factory):
    connection, schema = database
    collection = PostgresCollection(dict, client=connection, schema=f"{schema}_absent", definition=definition_factory())
    with pytest.raises(IntegrationException):
        await collection.ensure_collection_exists()
    cursor = await connection.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", [f"{schema}_absent"])
    assert await cursor.fetchone() is None


class DeterministicEmbeddingClient:
    def __init__(self):
        self.additional_properties: dict[str, Any] = {}
        self.inputs: list[list[Any]] = []

    async def get_embeddings(self, values, *, options=None):
        self.inputs.append(list(values))
        return GeneratedEmbeddings([Embedding(vector=[0, 1, 0]) for _ in values])


async def test_generation_selection_and_search_tool_params(database, definition_factory, record_factory):
    connection, schema = database
    generator = DeterministicEmbeddingClient()
    collection = PostgresCollection(
        dict,
        client=connection,
        schema=schema,
        definition=definition_factory(second_vector=True),
        embedding_generator=generator,
    )
    await collection.ensure_collection_exists()
    await collection.upsert(
        [record_factory("one", embedding="generate", secondary=[1, 0, 0])], generate_vectors=["embedding"]
    )
    row = (await collection.get(["one"], include_vectors=True))[0]
    assert row["embedding"] == [0, 1, 0] and row["secondary"] == [1, 0, 0]
    assert generator.inputs == [["generate"]]
    await collection.upsert([record_factory("two", embedding="first", secondary="second")])
    assert generator.inputs[1:] == [["first"], ["second"]]
    tool_collection = PostgresCollection(
        dict, client=connection, schema=schema, definition=definition_factory(), embedding_generator=generator
    )
    tool = create_vector_search_tool(
        tool_collection,
        filter=FilterGroup(
            "and",
            [
                Filter("id", "eq", "one"),
                Filter("text", "contains_text", Param("text", str | None, default=None, omit_if_none=True)),
            ],
        ),
    )
    result = await tool.invoke(arguments={"query": "search", "text": None})
    text = "".join(content.text or "" for content in result)
    assert "one" in text and "two" not in text


@vectorstoremodel
@dataclass
class NativeRecord:
    id: Annotated[UUID, VectorStoreField("key")]
    day: Annotated[date, VectorStoreField("data")]
    timestamp: Annotated[datetime, VectorStoreField("data")]
    data: Annotated[bytes, VectorStoreField("data")]
    details: Annotated[dict, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def test_msgspec_typed_roundtrip(database):
    connection, schema = database
    collection = PostgresCollection(NativeRecord, client=connection, schema=schema, collection_name="native")
    await collection.ensure_collection_exists()
    row = NativeRecord(
        uuid4(),
        date(2026, 9, 8),
        datetime(2026, 9, 8, tzinfo=timezone.utc),
        b"\x00binary",
        {"nested": [True, 1, None]},
        [1, 0, 0],
    )
    assert await collection.upsert([row], generate_vectors=False) == [row.id]
    assert await collection.get([row.id], include_vectors=True) == [row]
    assert (await collection.get([row.id]))[0].embedding is None


@pytest.mark.timeout(120)
async def test_thousand_records_two_1536_dimensional_vectors(database, definition_factory, record_factory):
    connection, schema = database
    collection = PostgresCollection(
        dict, client=connection, schema=schema, definition=definition_factory(dimensions=1536, second_vector=True)
    )
    await collection.ensure_collection_exists()
    records = [
        record_factory(
            str(i), number=i, embedding=[1.0, i / 1000, *([0.0] * 1534)], secondary=[i / 1000, 1.0, *([0.0] * 1534)]
        )
        for i in range(1000)
    ]
    assert await collection.upsert(records, generate_vectors=False) == [str(i) for i in range(1000)]
    assert len(await collection.get(top=1001)) == 1000
    stored = await collection.get(["0", "500", "999"], include_vectors=True)
    assert all(len(row["embedding"]) == len(row["secondary"]) == 1536 for row in stored)
    assert stored[1]["embedding"] == pytest.approx(records[500]["embedding"])
    assert stored[2]["secondary"] == pytest.approx(records[999]["secondary"])
    results = [
        item
        async for item in await collection.search(
            vector=[1.0, 0.0, *([0.0] * 1534)],
            vector_property_name="embedding",
            filter=Filter("number", "gte", 900),
            top=5,
            score_threshold=0.4,
        )
    ]
    assert [item["record"]["id"] for item in results] == [str(i) for i in range(900, 905)]
    await collection.delete([str(i) for i in range(1000)])
    assert await collection.get() == []


@pytest.mark.parametrize(
    "metric,operator",
    [
        ("cosine_similarity", "<=>"),
        ("dot_prod", "<#>"),
        ("euclidean_distance", "<->"),
    ],
)
async def test_ann_sql_uses_index_and_restores_callers_settings(
    database,
    definition_factory,
    record_factory,
    metric,
    operator,
):
    connection, schema = database
    collection = PostgresCollection(
        dict,
        client=connection,
        schema=schema,
        definition=definition_factory(index_kind="hnsw", distance_function=metric),
    )
    await collection.ensure_collection_exists()
    await collection.upsert(
        [record_factory(str(i), embedding=[1, i / 100, 0]) for i in range(100)], generate_vectors=False
    )
    captured: list[tuple[sql.Composed, Any]] = []

    class RecordingCursor(AsyncCursor):
        async def execute(
            self,
            query: Any,
            params: Any = None,
            *,
            prepare: bool | None = None,
            binary: bool | None = None,
        ) -> Self:
            if isinstance(query, sql.Composed) and "ORDER BY" in query.as_string():
                captured.append((query, params))
            return await super().execute(query, params, prepare=prepare, binary=binary)

    original_factory = connection.cursor_factory
    connection.cursor_factory = RecordingCursor
    try:
        async with connection.transaction():
            await connection.execute("SET LOCAL enable_seqscan = off")
            await connection.execute("SET LOCAL hnsw.ef_search = 55")
            await connection.execute("SET LOCAL hnsw.iterative_scan = off")
            await collection.search(vector=[1, 0, 0], score_threshold=0.5, operation_options={"hnsw_ef_search": 100})
            assert (await (await connection.execute("SHOW hnsw.ef_search")).fetchone())[0] == "55"
            assert (await (await connection.execute("SHOW hnsw.iterative_scan")).fetchone())[0] == "off"
            query, params = captured[0]
            assert f'ORDER BY "dense vector" {operator} %s ASC LIMIT %s OFFSET %s' in query.as_string()
            cursor = await connection.execute(sql.SQL("EXPLAIN ") + query, params)
            assert any("Index Scan using af_vector_" in row[0] for row in await cursor.fetchall())
    finally:
        connection.cursor_factory = original_factory


async def test_identity_collision_fails_instead_of_overwriting(database, definition_factory, record_factory):
    connection, schema = database
    collection = PostgresCollection(
        dict, client=connection, schema=schema, definition=definition_factory(key_type="int", generated=True)
    )
    await collection.ensure_collection_exists()
    await collection.upsert([record_factory(1, text="preserve")], generate_vectors=False)
    with pytest.raises(IntegrationException):
        await collection.upsert([record_factory(None, text="must not overwrite")], generate_vectors=False)
    assert (await collection.get([1]))[0]["text"] == "preserve"


async def test_generated_key_only_table_and_zero_vectors(database, definition_factory, record_factory):
    connection, schema = database
    key_only = PostgresCollection(
        dict,
        client=connection,
        schema=schema,
        collection_name="keys",
        definition=VectorStoreCollectionDefinition([
            VectorStoreField("key", name="id", type_="UUID", is_auto_generated=True),
        ]),
    )
    await key_only.ensure_collection_exists()
    keys = await key_only.upsert([{}, {}], generate_vectors=False)
    assert len(keys) == 2 and all(isinstance(key, UUID) for key in keys)
    assert await key_only.upsert([{"id": keys[0]}], generate_vectors=False) == [keys[0]]
    assert await key_only.get([keys[0]]) == [{"id": keys[0]}]
    collection = PostgresCollection(dict, client=connection, schema=schema, definition=definition_factory())
    await collection.ensure_collection_exists()
    await collection.upsert(
        [record_factory("zero", embedding=[0, 0, 0]), record_factory("nonzero")], generate_vectors=False
    )
    assert [item async for item in await collection.search(vector=[0, 0, 0])] == []
    results = [item async for item in await collection.search(vector=[1, 0, 0])]
    assert [item["record"]["id"] for item in results] == ["nonzero"]
