# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from array import array
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import oracledb
import pytest
from agent_framework import (
    Embedding,
    Filter,
    GeneratedEmbeddings,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    vectorstoremodel,
)
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException

from agent_framework_oracle import OracleCollection, OracleStore
from agent_framework_oracle._vector_store import _prepare_vector


@pytest.mark.parametrize(
    "vector_type,kind,value",
    [
        ("float", "f", [0.1, 1, 0]),
        ("float32", "f", [0.1, 1, 0]),
        ("float64", "d", [0.1, 1, 0]),
        ("int8", "b", [-128, 0, 127]),
    ],
)
def test_native_vector_adapter(vector_type, kind, value, definition_factory):
    field = definition_factory(vector_type=vector_type).vector_fields[0]
    prepared = _prepare_vector(field, value)
    assert isinstance(prepared, array) and prepared.typecode == kind
    assert list(prepared) == pytest.approx(value)


@pytest.mark.parametrize(
    "vector,error",
    [
        (b"\x00\x01\x02", TypeError),
        ("0,1,2", TypeError),
        ([True, 0, 1], TypeError),
        ([1, 2], ValueError),
        ([float("nan"), 0, 1], ValueError),
        ([float("inf"), 0, 1], ValueError),
        ([1e100, 0, 1], ValueError),
    ],
)
def test_bad_vectors_rejected(vector, error, definition_factory):
    with pytest.raises(error):
        _prepare_vector(definition_factory().vector_fields[0], vector)


@pytest.mark.parametrize("vector", [[128, 0, 1], [-129, 0, 1], [1.0, 0, 1], [True, 0, 1]])
def test_int8_vector_is_strict(vector, definition_factory):
    with pytest.raises(ValueError, match="int8"):
        _prepare_vector(definition_factory(vector_type="int8").vector_fields[0], vector)


@pytest.mark.parametrize(
    "definition",
    [
        {"generated": True},
        {"vector_type": "float16"},
        {"vector_type": "int"},
        {"index_kind": "hnsw"},
        {"distance_function": "hamming"},
        {"dimensions": 65536},
        {"data_type": "dict"},
    ],
)
def test_unsupported_model_capabilities_rejected_before_io(definition, definition_factory):
    with patch.object(oracledb, "create_pool_async") as create, pytest.raises((ValueError, NotImplementedError)):
        OracleCollection(dict, definition=definition_factory(**definition), dsn="unused", user="user", password="pass")
    create.assert_not_called()


def test_missing_vector_and_data_index_rejected_before_connecting():
    with pytest.raises(ValueError, match="vector"):
        OracleCollection(
            dict,
            definition=VectorStoreCollectionDefinition([VectorStoreField("key", name="id", type_="str")]),
            collection_name="AF_ONLY_KEY",
            dsn="unused",
            user="user",
            password="pass",
        )
    with pytest.raises(NotImplementedError, match="indexes"):
        OracleCollection(
            dict,
            definition=VectorStoreCollectionDefinition([
                VectorStoreField("key", name="id", type_="str"),
                VectorStoreField("data", name="text", type_="str", is_indexed=True),
                VectorStoreField("vector", name="vector", dimensions=3),
            ]),
            collection_name="AF_INDEXED",
            dsn="unused",
            user="user",
            password="pass",
        )


async def test_lifecycle_sql_is_scoped_and_identifiers_are_quoted(collection, mock_database):
    _, cursor, writes, _ = mock_database
    cursor.fetchone.side_effect = [None, ("exists",), ("exists",)]
    await collection.ensure_collection_exists()
    sql = cursor.execute.call_args_list[1].args[0]
    assert sql.startswith('CREATE TABLE "AF_DOCUMENTS" (')
    assert '"doc""id" VARCHAR2(512 BYTE) PRIMARY KEY' in sql
    assert '"dense vector" VECTOR(3, FLOAT32)' in sql
    assert all("ALTER" not in call.args[0] and "SCHEMA" not in call.args[0] for call in cursor.execute.call_args_list)
    assert await collection.collection_exists()
    await collection.ensure_collection_deleted()
    assert cursor.execute.call_args.args[0] == 'DROP TABLE "AF_DOCUMENTS" PURGE'
    assert writes == [False, False, False, False]


async def test_hostile_table_name_is_quoted_and_bound_in_metadata_lookup(definition_factory, mock_database):
    _, cursor, _, acquire = mock_database
    name = 'x"; DROP TABLE USERS; --'
    collection = OracleCollection(
        dict,
        definition=definition_factory(),
        collection_name=name,
        dsn="unused",
        user="user",
        password="pass",
    )
    with patch.object(collection._client, "connection", side_effect=acquire.side_effect):
        await collection.ensure_collection_exists()
    assert cursor.execute.call_args_list[0].args == (
        "SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :name",
        {"name": name},
    )
    statement = cursor.execute.call_args_list[1].args[0]
    assert statement.startswith('CREATE TABLE "x""; DROP TABLE USERS; --" (')


async def test_concurrent_create_checks_the_conflicting_object_is_a_table(collection, mock_database):
    _, cursor, _, _ = mock_database
    cursor.fetchone.side_effect = [None, ("exists",)]
    cursor.execute.side_effect = [None, oracledb.DatabaseError(SimpleNamespace(code=955)), None]
    await collection.ensure_collection_exists()
    assert cursor.execute.await_count == 3


async def test_upsert_merges_batch_with_typed_binds(collection, mock_database, record_factory):
    _, cursor, writes, _ = mock_database
    records = [record_factory("one"), record_factory("two", text="second", embedding=[0, 1, 0])]
    assert await collection.upsert(records, generate_vectors=False) == ["one", "two"]
    statement, params = cursor.executemany.call_args.args
    assert statement.startswith('MERGE INTO "AF_DOCUMENTS" target USING DUAL')
    assert 'target."doc""id" = :p0' in statement
    assert 'target."body text" = :p1' in statement
    assert "WHEN NOT MATCHED THEN INSERT" in statement
    assert len(params) == 2
    assert params[0]["p0"] == "one" and params[1]["p1"] == "second"
    assert params[0]["p3"] == 1 and params[1]["p3"] == 1
    assert isinstance(params[0]["p4"], array) and params[0]["p4"].typecode == "f"
    cursor.setinputsizes.assert_called_once_with(
        p0=512,
        p1=4000,
        p2=oracledb.DB_TYPE_NUMBER,
        p3=oracledb.DB_TYPE_NUMBER,
        p4=oracledb.DB_TYPE_VECTOR,
    )
    assert writes == [True]


async def test_nullable_vectors_and_float_data_have_explicit_bind_types(
    definition_factory, mock_database, record_factory
):
    _, cursor, _, acquire = mock_database
    collection = OracleCollection(
        dict,
        definition=definition_factory(data_type="float"),
        dsn="unused",
        user="user",
        password="pass",
    )
    empty_vector = record_factory("first", text=1.5)
    empty_vector["embedding"] = None
    with patch.object(collection._client, "connection", side_effect=acquire.side_effect):
        await collection.upsert(
            [empty_vector, record_factory("second", text=2.5)],
            generate_vectors=False,
        )
    assert cursor.executemany.call_args.args[1][0]["p4"] is None
    assert cursor.executemany.call_args.args[1][1]["p4"].typecode == "f"
    assert cursor.setinputsizes.call_args.kwargs["p1"] == oracledb.DB_TYPE_BINARY_DOUBLE
    assert cursor.setinputsizes.call_args.kwargs["p4"] == oracledb.DB_TYPE_VECTOR


async def test_embedding_generation_uses_the_shared_base_contract(collection, mock_database, record_factory):
    _, cursor, _, _ = mock_database
    generator = MagicMock()
    generator.get_embeddings = AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[0.0, 1.0, 0.0])]))
    collection.embedding_generator = generator
    await collection.upsert([record_factory(embedding="source text")])
    assert list(cursor.executemany.call_args.args[1][0]["p4"]) == [0, 1, 0]
    generator.get_embeddings.assert_awaited_once()


async def test_upsert_multiple_vectors_and_repeated_keys(definition_factory, record_factory, mock_database):
    _, cursor, _, acquire = mock_database
    collection = OracleCollection(
        dict,
        definition=definition_factory(second_vector=True),
        dsn="unused",
        user="user",
        password="pass",
    )
    with patch.object(collection._client, "connection", side_effect=acquire.side_effect):
        keys = await collection.upsert(
            [record_factory("same", second=[0, 1, 0]), record_factory("same", second=[1, 0, 0])],
            generate_vectors=False,
        )
    assert keys == ["same", "same"]
    assert cursor.executemany.call_args.args[1][0]["p5"].typecode == "d"


@pytest.mark.parametrize("bad_key", [None, "", True, 3])
async def test_invalid_keys_rejected_without_io(collection, mock_database, record_factory, bad_key):
    _, cursor, _, acquire = mock_database
    with pytest.raises((TypeError, ValueError)):
        await collection.upsert([record_factory(bad_key)], generate_vectors=False)
    with pytest.raises((TypeError, ValueError)):
        await collection.get([bad_key])
    acquire.assert_not_called()
    cursor.executemany.assert_not_awaited()


async def test_core_checks_batch_dimensions_before_writing(collection, mock_database, record_factory):
    _, _, _, acquire = mock_database
    with pytest.raises(ValueError, match="index 1"):
        await collection.upsert(
            [record_factory("good"), record_factory("bad", embedding=[1, 0])],
            generate_vectors=False,
        )
    with pytest.raises(ValueError, match="dimensions"):
        await collection.search(vector=[1])
    acquire.assert_not_called()


async def test_retrieval_projects_vectors_only_when_requested(collection, mock_database, record_factory):
    _, cursor, _, _ = mock_database
    cursor.fetchall.return_value = [("one", "Hello Oracle", 2, 1)]
    assert await collection.get(filter=Filter("number", "gte", 2), top=1, skip=1) == [
        {k: v for k, v in record_factory().items() if k != "embedding"}
    ]
    statement, binds = cursor.execute.call_args.args
    assert "dense vector" not in statement
    assert "ORDER BY" in statement and "OFFSET :skip ROWS FETCH NEXT :top ROWS ONLY" in statement
    assert binds == {"f0": 2, "top": 1, "skip": 1}
    cursor.fetchall.return_value = [("one", "Hello Oracle", 2, 1, array("f", [1, 0, 0]))]
    assert await collection.get(["one"], include_vectors=True) == [record_factory()]
    assert '"dense vector"' in cursor.execute.call_args.args[0]


async def test_key_lookup_preserves_order_duplicates_and_chunks(collection, mock_database):
    _, cursor, _, _ = mock_database
    cursor.fetchall.side_effect = [
        [("two", "other", 2, 0), ("one", "hello", 1, 1)],
        [("last", "last", 3, 1)],
    ]
    keys = ["one", "two", *["one"] * 498, "last"]
    records = await collection.get(keys)
    assert [record["id"] for record in records] == keys
    assert cursor.execute.await_count == 2
    assert "IN (" in cursor.execute.call_args_list[0].args[0]
    assert "IN (:k0)" in cursor.execute.call_args_list[1].args[0]


async def test_empty_batches_and_unsupported_options_do_not_hit_database(collection, mock_database):
    _, _, _, acquire = mock_database
    assert await collection.upsert([], generate_vectors=False) == []
    assert await collection.get([]) == []
    await collection.delete([])
    acquire.assert_not_called()
    with pytest.raises(NotImplementedError):
        await collection.get(operation_options={"sql": "DROP TABLE AF_DOCUMENTS"})
    with pytest.raises(ValueError, match="key lookup"):
        await collection.get(["one"], top=1)
    acquire.assert_not_called()


async def test_delete_is_bound_and_chunked(collection, mock_database):
    _, cursor, writes, _ = mock_database
    await collection.delete(["first", "second"] * 251)
    assert cursor.execute.await_count == 2
    statement, binds = cursor.execute.call_args_list[0].args
    assert statement.startswith('DELETE FROM "AF_DOCUMENTS" WHERE "doc""id" IN (')
    assert "first" not in statement and binds["k0"] == "first"
    assert writes == [True]


async def test_search_filter_threshold_and_paging_execute_in_database(collection, mock_database):
    _, cursor, _, _ = mock_database
    cursor.fetchall.return_value = [("one", "Hello Oracle", 2, 1, 0.05)]
    result = await collection.search(
        vector=[1, 0, 0],
        filter=Filter("text", "contains_text", "%_"),
        score_threshold=0.1,
        top=1,
        skip=2,
    )
    assert result.metadata == {"distance_function": "DEFAULT"}
    assert [item async for item in result] == [
        {
            "record": {"id": "one", "text": "Hello Oracle", "number": 2, "flag": True},
            "score": 0.05,
        }
    ]
    statement, binds = cursor.execute.call_args.args
    assert statement.count("VECTOR_DISTANCE(") == 3
    assert statement.index("<= :threshold") < statement.index("ORDER BY") < statement.index("OFFSET :skip")
    assert "COSINE" in statement and "embedding" not in statement
    assert binds["f0"] == "%!%!_%" and binds["threshold"] == 0.1
    assert binds["top"] == 1 and binds["skip"] == 2
    assert isinstance(binds["query_vector"], array)
    cursor.setinputsizes.assert_called_once_with(query_vector=oracledb.DB_TYPE_VECTOR)


@pytest.mark.parametrize(
    "metric,cutoff,score_expression",
    [
        ("cosine_similarity", 0.9, "1 - VECTOR_DISTANCE"),
        ("dot_prod", -0.1, "-VECTOR_DISTANCE"),
        ("euclidean_distance", 0.1, "VECTOR_DISTANCE"),
        ("negative_dot_prod", 0.1, "VECTOR_DISTANCE"),
    ],
)
async def test_metric_score_and_threshold_units(definition_factory, mock_database, metric, cutoff, score_expression):
    _, cursor, _, acquire = mock_database
    collection = OracleCollection(
        dict,
        definition=definition_factory(distance_function=metric),
        dsn="unused",
        user="user",
        password="pass",
    )
    with patch.object(collection._client, "connection", side_effect=acquire.side_effect):
        await collection.search(vector=[1, 0, 0], score_threshold=0.1)
    statement, binds = cursor.execute.call_args.args
    assert score_expression in statement
    assert binds["threshold"] == pytest.approx(cutoff)


async def test_invalid_search_modes_and_bad_thresholds_fail_without_io(collection, mock_database):
    _, _, _, acquire = mock_database
    with pytest.raises(NotImplementedError):
        await collection.search("text", search_type="keyword_hybrid", vector=[1, 0, 0])
    with pytest.raises(NotImplementedError):
        await collection.search("text")
    with pytest.raises(NotImplementedError):
        await collection.search(vector=[1, 0, 0], additional_property_name="text")
    with pytest.raises(NotImplementedError):
        await collection.search(vector=[1, 0, 0], operation_options={"exact": True})
    with pytest.raises(ValueError):
        await collection.search(vector=[1, 0, 0], score_threshold=float("nan"))
    with pytest.raises(ValueError):
        await collection.search(vector=[1, 0, 0], score_threshold=10**1000)
    acquire.assert_not_called()


async def test_invalid_search_response_is_reported(collection, mock_database):
    _, cursor, _, _ = mock_database
    cursor.fetchall.return_value = [("one", "text", 1, 1, None)]
    with pytest.raises(IntegrationInvalidResponseException, match="null vector distance"):
        await collection.search(vector=[1, 0, 0])
    cursor.fetchall.return_value = [("one",)]
    with pytest.raises(IntegrationInvalidResponseException, match="number of columns"):
        await collection.get()
    cursor.fetchall.return_value = [("one", "text", 1, 1, float("nan"))]
    with pytest.raises(IntegrationInvalidResponseException, match="nonfinite"):
        await collection.search(vector=[1, 0, 0])
    cursor.fetchall.return_value = [("one", "text", float(2**63), 1)]
    with pytest.raises(IntegrationInvalidResponseException, match="invalid integer"):
        await collection.get()
    cursor.fetchall.return_value = [("one", "text", Decimal("9223372036854775807"), 1)]
    assert (await collection.get())[0]["number"] == 2**63 - 1


@vectorstoremodel(collection_name="AF_TYPED")
@dataclass
class TypedDocument:
    id: Annotated[UUID, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


def test_typed_model_deserializes_native_vectors():
    collection = OracleCollection(TypedDocument, dsn="unused", user="user", password="pass")
    record = collection.deserialize({"id": str(UUID(int=1)), "text": "one", "embedding": array("f", [1, 0, 0])})
    assert isinstance(record, TypedDocument)
    assert record.id == UUID(int=1)
    assert record.embedding == [1, 0, 0]


async def test_uuid_key_lookup_uses_normalized_bind(definition_factory, mock_database):
    _, cursor, _, acquire = mock_database
    collection = OracleCollection(
        dict,
        definition=definition_factory(key_type="UUID"),
        dsn="unused",
        user="user",
        password="pass",
    )
    key = UUID(int=1)
    cursor.fetchall.return_value = [(str(key), "text", 1, 1)]
    with patch.object(collection._client, "connection", side_effect=acquire.side_effect):
        records = await collection.get([key])
    assert [record["id"] for record in records] == [key]
    assert cursor.execute.call_args.args[1] == {"k0": str(key)}


async def test_uuid_upsert_returns_typed_key(definition_factory, mock_database, record_factory):
    _, cursor, _, acquire = mock_database
    collection = OracleCollection(
        dict,
        definition=definition_factory(key_type="UUID"),
        dsn="unused",
        user="user",
        password="pass",
    )
    key = UUID(int=1)
    with patch.object(collection._client, "connection", side_effect=acquire.side_effect):
        keys = await collection.upsert([record_factory(key)], generate_vectors=False)
    assert keys == [key]
    assert cursor.executemany.call_args.args[1][0]["p0"] == str(key)


async def test_store_close_invalidates_children_but_borrowed_client_stays_open(definition_factory):
    connection = MagicMock(spec=oracledb.AsyncConnection)
    store = OracleStore(client=connection)
    child = store.get_collection(dict, definition=definition_factory())
    await child.close()
    await store.close()
    connection.close.assert_not_called()
    with pytest.raises(IntegrationException, match="closed"):
        await child.get()
