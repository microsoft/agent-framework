# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import math
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Annotated, Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import duckdb
import pytest
from agent_framework import (
    Embedding,
    Filter,
    FilterGroup,
    GeneratedEmbeddings,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    vectorstoremodel,
)
from agent_framework.exceptions import IntegrationException

from agent_framework_duckdb import DuckDBCollection, DuckDBStore
from agent_framework_duckdb._vector_store import _identifier


async def test_default_database_persists_across_closed_stores(definition, record_factory, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DUCKDB_CONNECTION_STRING", raising=False)
    filename = tmp_path / "agent-framework.duckdb"
    async with DuckDBStore() as store:
        assert not filename.exists()
        collection = store.get_collection(dict, definition=definition)
        await collection.ensure_collection_exists()
        assert await collection.upsert([record_factory()], generate_vectors=False) == ["one"]
    assert filename.is_file()
    async with DuckDBStore() as reopened:
        collection = reopened.get_collection(dict, definition=definition)
        assert (await collection.get(["one"]))[0]["text"] == "DuckDB stores vectors"
        assert (await collection.get(["one"], include_vectors=True))[0]["embedding"] == [1.0, 0.0, 0.0]


async def test_lifecycle_and_direct_collection(definition, tmp_path):
    path = str(tmp_path / "collections.duckdb")
    async with DuckDBCollection(dict, connection_string=path, definition=definition) as collection:
        assert not await collection.collection_exists()
        await collection.ensure_collection_exists()
        await collection.ensure_collection_exists()
        assert await collection.collection_exists()
    async with DuckDBStore(connection_string=path) as store:
        assert await store.collection_exists("documents")
        assert "documents" in await store.list_collection_names()
        await store.ensure_collection_deleted("documents")
        assert not await store.collection_exists("documents")
        await store.ensure_collection_deleted("documents")


async def test_store_collection_checks_and_deletion_are_case_insensitive(tmp_path):
    definition = VectorStoreCollectionDefinition(
        [VectorStoreField("key", name="id", type_="str")], collection_name="MiXeD"
    )
    async with DuckDBStore(connection_string=str(tmp_path / "mixed-case.duckdb")) as store:
        collection = store.get_collection(dict, definition=definition)
        await collection.ensure_collection_exists()
        assert await store.list_collection_names() == ["MiXeD"]
        assert await store.collection_exists("mixed")
        assert await store.collection_exists("MIXED")

        await store.ensure_collection_deleted("mIxEd")

        assert not await store.collection_exists("MiXeD")
        assert "MiXeD" not in await store.list_collection_names()


@pytest.mark.parametrize(
    ("table_name", "same_table", "different_table"),
    [("ÄBC", "Äbc", "äbc"), ("äbc", "äBC", "Äbc")],
)
@pytest.mark.parametrize("config", [None, {"default_collation": "NOCASE"}])
async def test_non_ascii_table_existence_matches_duckdb_identifiers(
    tmp_path, table_name: str, same_table: str, different_table: str, config: dict[str, str] | None
):
    definition = VectorStoreCollectionDefinition(
        [VectorStoreField("key", name="id", type_="str")], collection_name=table_name
    )
    async with DuckDBStore(connection_string=str(tmp_path / "unicode.duckdb"), config=config) as store:
        original = store.get_collection(dict, definition=definition)
        same = store.get_collection(dict, definition=definition, collection_name=same_table)
        different = store.get_collection(dict, definition=definition, collection_name=different_table)
        await original.ensure_collection_exists()

        assert await original.collection_exists()
        assert await same.collection_exists()
        assert await store.collection_exists(same_table)
        assert not await different.collection_exists()
        assert not await store.collection_exists(different_table)
        await store.ensure_collection_deleted(different_table)
        assert await original.collection_exists()
        await store.ensure_collection_deleted(same_table)
        assert not await original.collection_exists()


async def test_non_ascii_columns_are_distinct(tmp_path):
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("data", name="first", type_="str", storage_name="Ä"),
            VectorStoreField("data", name="second", type_="str", storage_name="ä"),
        ],
        collection_name="unicode_columns",
    )
    async with DuckDBCollection(
        dict, definition=definition, connection_string=str(tmp_path / "unicode-columns.duckdb")
    ) as collection:
        await collection.ensure_collection_exists()
        await collection.upsert([{"id": "one", "first": "upper", "second": "lower"}])
        assert await collection.get(["one"]) == [{"id": "one", "first": "upper", "second": "lower"}]


async def test_batch_crud_preserves_key_order_and_upserts(collection: DuckDBCollection[Any, Any], record_factory):
    first = record_factory("first", priority=1)
    second = record_factory("second", text="second text", priority=2, embedding=[0.0, 1.0, 0.0])
    assert await collection.upsert([first, second], generate_vectors=False) == ["first", "second"]
    await collection.upsert([record_factory("first", priority=3)], generate_vectors=False)
    records = await collection.get(["second", "missing", "first", "second"], include_vectors=True)
    assert [item["id"] for item in records] == ["second", "first", "second"]
    assert records[1]["priority"] == 3
    assert records[0]["embedding"] == [0.0, 1.0, 0.0]
    assert records[1]["tags"] == ["example", True]
    assert [item["id"] for item in await collection.get(order_by={"priority": False})] == ["first", "second"]
    await collection.delete(["missing", "first", "second"])
    assert await collection.get(["first", "second"]) == []
    assert await collection.upsert([], generate_vectors=False) == []
    assert await collection.get([]) == []
    await collection.delete([])


async def test_typed_model_roundtrips_and_searches(tmp_path):
    @vectorstoremodel(collection_name="articles")
    @dataclass
    class Article:
        id: Annotated[str, VectorStoreField("key", storage_name="article_id")]
        text: Annotated[str, VectorStoreField("data")]
        embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None

    async with DuckDBStore(connection_string=str(tmp_path / "typed.duckdb")) as store:
        collection = store.get_collection(Article)
        await collection.ensure_collection_exists()
        assert await collection.upsert([Article("one", "typed", [1, 0, 0])], generate_vectors=False) == ["one"]
        assert await collection.get(["one"]) == [Article("one", "typed", None)]
        assert await collection.get(["one"], include_vectors=True) == [Article("one", "typed", [1, 0, 0])]
        results = [result async for result in await collection.search(vector=[1, 0, 0])]
        assert results[0]["record"] == Article("one", "typed", None)
        assert results[0]["score"] == pytest.approx(0)


async def test_typed_uuid_date_datetime_bytes_json_and_float32_vectors(tmp_path):
    @vectorstoremodel(collection_name="typed_values")
    @dataclass
    class TypedRecord:
        id: Annotated[UUID, VectorStoreField("key")]
        created: Annotated[datetime, VectorStoreField("data")]
        event_date: Annotated[date, VectorStoreField("data")]
        attachment: Annotated[bytes, VectorStoreField("data")]
        payload: Annotated[dict[str, Any], VectorStoreField("data")]
        reading: Annotated[float, VectorStoreField("data")]
        embedding: Annotated[
            list[float] | None,
            VectorStoreField("vector", type_="float32", dimensions=3, distance_function="euclidean_distance"),
        ] = None

    original = TypedRecord(
        UUID("a16b0f43-39b2-4c5a-a0fa-9a7f266685c6"),
        datetime(2026, 9, 23, 9, 30, tzinfo=timezone.utc),
        date(2026, 9, 23),
        b"\x00\xff",
        {"labels": [True, 3, "mixed"]},
        1.25,
        [0.1, 0.2, 0.3],
    )
    async with DuckDBCollection(TypedRecord, connection_string=str(tmp_path / "types.duckdb")) as collection:
        await collection.ensure_collection_exists()
        assert await collection.upsert([original], generate_vectors=False) == [original.id]
        restored = (await collection.get([original.id], include_vectors=True))[0]
        assert restored.id == original.id
        assert restored.created == original.created
        assert restored.event_date == original.event_date
        assert restored.attachment == original.attachment
        assert restored.payload == original.payload
        assert restored.reading == original.reading
        assert restored.embedding == pytest.approx(original.embedding)
        assert len(await collection.get(filter=Filter("event_date", "eq", original.event_date))) == 1
        assert len(await collection.get(filter=Filter("created", "gte", original.created))) == 1
        assert len(await collection.get(filter=Filter("id", "eq", str(original.id)))) == 1
        assert [result async for result in await collection.search(vector=[0, 0, 0])]


async def test_local_embeddings_are_generated_for_writes_and_value_search(definition, record_factory, tmp_path):
    generator = MagicMock(
        get_embeddings=AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[1.0, 0.0, 0.0])]))
    )
    async with DuckDBStore(
        connection_string=str(tmp_path / "generated-vectors.duckdb"), embedding_generator=generator
    ) as store:
        collection = store.get_collection(dict, definition=definition)
        await collection.ensure_collection_exists()
        await collection.upsert([record_factory(embedding=[0.0, 0.0, 0.0])])
        assert (await collection.get(["one"], include_vectors=True))[0]["embedding"] == [1.0, 0.0, 0.0]
        found = [item async for item in await collection.search("query text")]
        assert [item["record"]["id"] for item in found] == ["one"]
        assert generator.get_embeddings.await_count == 2
        assert generator.get_embeddings.await_args_list[0].kwargs["options"] == {"dimensions": 3}


async def test_search_selects_requested_vector_field(tmp_path):
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("vector", name="primary", type_="float", dimensions=3),
            VectorStoreField("vector", name="secondary", type_="float", dimensions=3),
        ],
        collection_name="two_vectors",
    )
    async with DuckDBCollection(
        dict, definition=definition, connection_string=str(tmp_path / "two-vectors.duckdb")
    ) as collection:
        await collection.ensure_collection_exists()
        await collection.upsert(
            [
                {"id": "a", "primary": [1, 0, 0], "secondary": [0, 1, 0]},
                {"id": "b", "primary": [0, 1, 0], "secondary": [1, 0, 0]},
            ],
            generate_vectors=False,
        )
        primary = [item async for item in await collection.search(vector=[1, 0, 0], top=1)]
        secondary = [
            item
            async for item in await collection.search(
                vector=[1, 0, 0], vector_property_name="secondary", include_vectors=True, top=1
            )
        ]
        assert primary[0]["record"]["id"] == "a"
        assert secondary[0]["record"]["id"] == "b"
        assert secondary[0]["record"]["primary"] == [0.0, 1.0, 0.0]


async def test_generated_string_and_uuid_keys(tmp_path):
    for key_type in ("str", "UUID"):
        definition = VectorStoreCollectionDefinition(
            [
                VectorStoreField("key", name="id", type_=key_type, is_auto_generated=True),
                VectorStoreField("data", name="text", type_="str"),
            ],
            collection_name=f"generated_{key_type}",
        )
        async with DuckDBCollection(
            dict, definition=definition, connection_string=str(tmp_path / f"{key_type}.duckdb")
        ) as collection:
            await collection.ensure_collection_exists()
            keys = await collection.upsert([{"text": "first"}, {"id": None, "text": "second"}])
            assert len(set(keys)) == 2
            assert all(isinstance(key, str if key_type == "str" else UUID) for key in keys)
            assert [item["text"] for item in await collection.get(keys)] == ["first", "second"]


async def test_scalar_filters_and_ordering(collection: DuckDBCollection[Any, Any], record_factory):
    await collection.upsert(
        [
            record_factory("a", text="alpha%_!", priority=3),
            record_factory("b", text="alpha", priority=1, active=False, embedding=[0, 1, 0]),
            record_factory("c", text=None, priority=None, embedding=None),
        ],
        generate_vectors=False,
    )

    async def matching(expression) -> list[str]:
        return [item["id"] for item in await collection.get(filter=expression, order_by={"priority": False}, top=10)]

    assert await matching(Filter("text", "contains_text", "%_!")) == ["a"]
    assert await matching(Filter("text", "starts_with", "alpha")) == ["a", "b"]
    assert await matching(Filter("text", "ends_with", "alpha")) == ["b"]
    assert await matching(Filter("text", "is_null")) == ["c"]
    assert await matching(Filter("text", "is_not_null")) == ["a", "b"]
    assert await matching(Filter("text", "exists")) == ["a", "b", "c"]
    assert await matching(Filter("priority", "gte", 2)) == ["a"]
    assert await matching(Filter("priority", "between", [1, 3])) == ["a", "b"]
    assert await matching(Filter("priority", "in", [None, 1])) == ["b"]
    assert await matching(Filter("priority", "not_in", [None, 1])) == ["a"]
    assert await matching(Filter("priority", "in", [])) == []
    assert await matching(Filter("priority", "not_in", [])) == ["a", "b"]
    assert await matching(Filter("active", "eq", 1)) == []
    assert await matching(Filter("active", "ne", 1)) == ["a", "b", "c"]
    assert await matching(
        FilterGroup(
            "and",
            [
                Filter("text", "starts_with", "alpha"),
                FilterGroup("not", [Filter("active", "eq", False)]),
            ],
        )
    ) == ["a"]
    assert await matching(FilterGroup("not", [Filter("priority", "gt", 2)])) == ["b", "c"]
    assert [item["id"] for item in await collection.get(top=1, skip=1, order_by={"priority": False})] == ["b"]


@pytest.mark.parametrize(
    "expression,error",
    [
        (Filter("tags", "eq", ["example"]), NotImplementedError),
        (Filter("tags", "contains", "example"), NotImplementedError),
        (Filter("tags.nested", "eq", "example"), NotImplementedError),
        (Filter("embedding", "is_null"), NotImplementedError),
        (Filter("text", "duckdb.raw", "anything"), NotImplementedError),
        (Filter("priority", "starts_with", "1"), TypeError),
        (Filter("active", "gt", 1), NotImplementedError),
        (Filter("priority", "gt", True), TypeError),
    ],
)
async def test_unsupported_filters_fail_loudly(collection: DuckDBCollection[Any, Any], expression, error):
    with pytest.raises(error):
        await collection.get(filter=expression)


async def test_invalid_order_and_operation_options_fail_loudly(collection: DuckDBCollection[Any, Any]):
    for order_by in ({"tags": True}, {"embedding": False}, {"text.nested": True}):
        with pytest.raises(NotImplementedError):
            await collection.get(order_by=order_by)
    with pytest.raises(ValueError, match="Unknown"):
        await collection.get(order_by={"missing": True})
    with pytest.raises(TypeError, match="booleans"):
        await collection.get(order_by={"text": cast(Any, "ASC; DROP TABLE documents")})
    with pytest.raises(ValueError, match="order_by"):
        await collection.get(["one"], order_by={"text": True})
    with pytest.raises(NotImplementedError, match="Unsupported DuckDB operation"):
        await collection.get(operation_options={"timeout": 4})
    with pytest.raises(NotImplementedError, match="Unsupported DuckDB operation"):
        await collection.ensure_collection_exists(operation_options={"index": True})


@pytest.mark.parametrize(
    "metric,first_score,threshold",
    [
        ("DEFAULT", 0.0, 0.1),
        ("cosine_distance", 0.0, 0.1),
        ("cosine_similarity", 1.0, 0.5),
        ("euclidean_distance", 0.0, 0.1),
        ("dot_prod", 1.0, 0.5),
        ("negative_dot_prod", -1.0, -0.5),
    ],
)
async def test_metric_ranking_threshold_filter_and_paging(tmp_path, metric, first_score, threshold):
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("data", name="category", type_="str"),
            VectorStoreField("vector", name="embedding", type_="float", dimensions=3, distance_function=metric),
        ],
        collection_name="scores",
    )
    async with DuckDBCollection(
        dict, definition=definition, connection_string=str(tmp_path / f"{metric}.duckdb")
    ) as collection:
        await collection.ensure_collection_exists()
        await collection.upsert(
            [
                {"id": "a", "category": "keep", "embedding": [1, 0, 0]},
                {"id": "b", "category": "keep", "embedding": [0, 1, 0]},
                {"id": "c", "category": "exclude", "embedding": [1, 0, 0]},
                {"id": "d", "category": "keep", "embedding": None},
            ],
            generate_vectors=False,
        )
        found = [
            item
            async for item in await collection.search(
                vector=[1, 0, 0], filter=Filter("category", "eq", "keep"), score_threshold=threshold
            )
        ]
        assert [item["record"]["id"] for item in found] == ["a"]
        assert found[0]["score"] == pytest.approx(first_score)
        unfiltered = [item async for item in await collection.search(vector=[1, 0, 0], top=1, skip=1)]
        assert unfiltered[0]["record"]["id"] == "c"
        with pytest.raises(ValueError, match="finite"):
            await collection.search(vector=[1, 0, 0], score_threshold=math.nan)


async def test_zero_and_invalid_vectors_and_unavailable_search_types(
    collection: DuckDBCollection[Any, Any], record_factory
):
    await collection.upsert([record_factory()], generate_vectors=False)
    for vector in ([0, 0, 0], [1, math.inf, 0], [1, True, 0], b"binary"):
        with pytest.raises((TypeError, ValueError)):
            await collection.search(vector=vector)
    with pytest.raises(ValueError, match="dimensions"):
        await collection.upsert([record_factory(embedding=[1, 0])], generate_vectors=False)
    assert len(await collection.get(["one"])) == 1
    with pytest.raises(NotImplementedError, match="vectorize"):
        await collection.search("unembedded text")
    with pytest.raises(NotImplementedError, match="keyword_hybrid"):
        await collection.search("query", search_type="keyword_hybrid")
    with pytest.raises(NotImplementedError, match="hybrid"):
        await collection.search(vector=[1, 0, 0], additional_property_name="text")
    with pytest.raises(NotImplementedError, match="Unsupported DuckDB operation"):
        await collection.search(vector=[1, 0, 0], operation_options={"exact": False})


async def test_existing_zero_cosine_vectors_are_skipped_without_failing_search():
    connection = duckdb.connect(":memory:")
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("vector", name="embedding", type_="float", dimensions=3),
        ],
        collection_name="external_rows",
    )
    try:
        async with DuckDBStore(client=connection) as store:
            collection = store.get_collection(dict, definition=definition)
            await collection.ensure_collection_exists()
            await collection.upsert([{"id": "valid", "embedding": [1, 0, 0]}], generate_vectors=False)
            connection.execute("INSERT INTO external_rows VALUES ('zero', [0, 0, 0])")
            found = [item async for item in await collection.search(vector=[1, 0, 0])]
            assert [item["record"]["id"] for item in found] == ["valid"]
    finally:
        connection.close()


def test_model_options_rejected_before_connecting(definition):
    def model(*, key_type="str", index_kind="flat", distance="DEFAULT", data_indexed=False, generated=False):
        return VectorStoreCollectionDefinition(
            [
                VectorStoreField("key", name="id", type_=key_type, is_auto_generated=generated),
                VectorStoreField("data", name="text", type_="str", is_indexed=data_indexed),
                VectorStoreField(
                    "vector",
                    name="embedding",
                    type_="float",
                    dimensions=3,
                    index_kind=index_kind,
                    distance_function=distance,
                ),
            ],
            collection_name="rows",
        )

    for invalid_definition in (
        model(key_type="float"),
        model(key_type="int", generated=True),
        model(data_indexed=True),
        model(index_kind="hnsw"),
        model(distance="hamming"),
    ):
        with pytest.raises((NotImplementedError, ValueError)):
            DuckDBCollection(dict, definition=invalid_definition)
    with pytest.raises(ValueError, match="ignoring case"):
        DuckDBCollection(
            dict,
            definition=VectorStoreCollectionDefinition(
                [
                    VectorStoreField("key", name="id", type_="str"),
                    VectorStoreField("data", name="text", storage_name="ID", type_="str"),
                ],
                collection_name="rows",
            ),
        )
    with pytest.raises(ValueError, match="NUL"):
        DuckDBCollection(dict, definition=definition, collection_name="unsafe\0name")


async def test_all_identifiers_and_values_are_safe(tmp_path):
    assert _identifier('foo"; DROP TABLE other; --') == '"foo""; DROP TABLE other; --"'
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("data", name="text", type_="str", storage_name='body "; DROP TABLE safe; --'),
        ],
        collection_name='unsafe"; DROP TABLE safe; --',
    )
    payload = "' OR 1=1; DROP TABLE safe; --%_!"
    async with DuckDBStore(connection_string=str(tmp_path / "safe.duckdb")) as store:
        unsafe = store.get_collection(dict, definition=definition)
        safe = store.get_collection(
            dict,
            definition=VectorStoreCollectionDefinition(
                [VectorStoreField("key", name="id", type_="str")], collection_name="safe"
            ),
        )
        await safe.ensure_collection_exists()
        await unsafe.ensure_collection_exists()
        await unsafe.upsert([{"id": "x", "text": payload}], generate_vectors=False)
        assert [record["id"] for record in await unsafe.get(filter=Filter("text", "eq", payload))] == ["x"]
        assert [record["id"] for record in await unsafe.get(filter=Filter("text", "contains_text", "%_!"))] == ["x"]
        assert await safe.collection_exists()
        assert await unsafe.collection_exists()
        await unsafe.ensure_collection_deleted()
        assert await safe.collection_exists()


async def test_owned_upsert_rolls_back_on_driver_failure(tmp_path):
    path = str(tmp_path / "transactions.duckdb")
    connection = duckdb.connect(path)
    connection.execute("CREATE TABLE checked (id VARCHAR PRIMARY KEY, text VARCHAR CHECK (text <> 'fail'))")
    connection.close()
    definition = VectorStoreCollectionDefinition(
        [VectorStoreField("key", name="id", type_="str"), VectorStoreField("data", name="text", type_="str")],
        collection_name="checked",
    )
    async with DuckDBStore(connection_string=path) as store:
        collection = store.get_collection(dict, definition=definition)
        with pytest.raises(IntegrationException, match="DuckDB operation failed") as error:
            await collection.upsert([{"id": "one", "text": "ok"}, {"id": "two", "text": "fail"}])
        assert isinstance(error.value.__cause__, duckdb.Error)
        assert await collection.get(["one", "two"]) == []


async def test_borrowed_connection_preserves_caller_transactions():
    connection = duckdb.connect(":memory:")
    definition = VectorStoreCollectionDefinition(
        [VectorStoreField("key", name="id", type_="str"), VectorStoreField("data", name="text", type_="str")],
        collection_name="checked",
    )
    try:
        connection.execute("CREATE TABLE checked (id VARCHAR PRIMARY KEY, text VARCHAR CHECK (text <> 'fail'))")
        async with DuckDBStore(client=connection) as store:
            collection = store.get_collection(dict, definition=definition)
            connection.execute("BEGIN TRANSACTION")
            await collection.upsert([{"id": "one", "text": "pending"}])
            connection.execute("ROLLBACK")
            assert await collection.get(["one"]) == []
            with pytest.raises(IntegrationException, match="DuckDB operation failed"):
                await collection.upsert([{"id": "one", "text": "ok"}, {"id": "two", "text": "fail"}])
            assert [item["id"] for item in await collection.get(["one"])] == ["one"]
    finally:
        assert connection.execute("SELECT 42").fetchone() == (42,)
        connection.close()


async def test_io_is_offloaded_serial_and_close_drains_cancelled_work(tmp_path):
    store = DuckDBStore(connection_string=str(tmp_path / "worker.duckdb"))
    started = threading.Event()
    completed = threading.Event()
    worker_thread_ids: list[int] = []

    def slow(connection: duckdb.DuckDBPyConnection) -> None:
        started.set()
        time.sleep(0.1)
        worker_thread_ids.append(threading.get_ident())
        connection.execute("CREATE TABLE done (id INTEGER)")
        completed.set()

    task = asyncio.create_task(store._client.run(slow))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        await asyncio.sleep(0.01)
        assert not completed.is_set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        other = await store._client.run(lambda _connection: threading.get_ident())
        assert other == worker_thread_ids[0] != threading.get_ident()
        await store.aclose()
        assert completed.is_set()
        with pytest.raises(RuntimeError, match="closed"):
            await store.list_collection_names()
        reopened = duckdb.connect(str(tmp_path / "worker.duckdb"))
        try:
            assert reopened.execute("SELECT count(*) FROM done").fetchone() == (0,)
        finally:
            reopened.close()
    finally:
        await store.aclose()
