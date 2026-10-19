# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from agent_framework import (
    Embedding,
    Filter,
    FilterGroup,
    GeneratedEmbeddings,
    Param,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    create_vector_search_tool,
    vectorstoremodel,
)
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException
from pgvector import HalfVector
from pgvector import Vector as PgVector
from psycopg import AsyncConnection, OperationalError
from psycopg_pool import AsyncConnectionPool

from agent_framework_postgres import PostgresCollection, PostgresStore
from agent_framework_postgres._vector_store import _Client, _FilterCompiler, _prepare_identifier, _prepare_value


@pytest.fixture
def collection(definition_factory, request):
    return PostgresCollection(
        dict, definition=definition_factory(**getattr(request, "param", {})), connection_string="host=unused"
    )


@pytest.fixture
def mock_database(collection):
    connection = MagicMock(spec=AsyncConnection)
    connection.execute = AsyncMock()
    cursor = MagicMock()
    cursor.execute = AsyncMock()
    cursor.executemany = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=("one",))
    cursor.fetchall = AsyncMock(return_value=[])
    cursor.nextset = MagicMock(return_value=True)
    connection.cursor.return_value.__aenter__.return_value = cursor
    with patch.object(collection._client, "connection") as acquire:
        acquire.return_value.__aenter__.return_value = connection
        yield connection, cursor, acquire


@pytest.mark.parametrize("name", ["", "x\0y", "a" * 64, "\u00e9" * 32])
def test_identifier_rejects_truncation_and_nul(name):
    with pytest.raises(ValueError):
        _prepare_identifier(name)


def test_identifiers_are_quoted_not_executed():
    assert _prepare_identifier('a"; DROP TABLE users; --').as_string() == '"a""; DROP TABLE users; --"'
    assert _prepare_identifier("public.documents").as_string() == '"public.documents"'


def test_filter_values_are_bound(collection):
    payload = "'; DROP TABLE documents; --%_!"
    condition, params = collection._prepare_filter(Filter("text", "contains_text", payload))
    statement = condition.as_string()
    assert payload not in statement
    assert '"body ""text"""' in statement
    assert "%s" in statement and "ESCAPE '!'" in statement
    assert params == ["%'; DROP TABLE documents; --!%!_!!%"]


@pytest.mark.parametrize("op", ["eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in"])
def test_scalar_operators_parameterized(collection, op):
    value = [1, 2] if op in ("between", "in", "not_in") else 7
    condition, params = collection._prepare_filter(Filter("number", op, value))
    assert "%s" in condition.as_string()
    assert params == (value if isinstance(value, list) else [value])


@pytest.mark.parametrize("field,value", [("number", True), ("flag", 1), ("flag", "true"), ("number", "1")])
def test_type_mismatched_equality_is_not_coerced(collection, field, value):
    equality, params = collection._prepare_filter(Filter(field, "eq", value))
    assert equality.as_string() == "FALSE"
    assert params == []
    inequality, params = collection._prepare_filter(Filter(field, "ne", value))
    assert inequality.as_string() == "(NOT (FALSE))"
    assert params == []


def test_null_and_negative_predicates_are_two_valued(collection):
    assert collection._prepare_filter(Filter("text", "is_null"))[0].as_string().endswith("IS NULL")
    assert collection._prepare_filter(Filter("text", "exists"))[0].as_string() == "TRUE"
    assert collection._prepare_filter(Filter("text", "is_not_null"))[0].as_string().endswith("IS NOT NULL")
    text = collection._prepare_filter(FilterGroup("not", [Filter("number", "gt", 3)]))[0].as_string()
    assert "NOT" in text and "IS TRUE" in text
    text = collection._prepare_filter(Filter("number", "not_in", [1, None]))[0].as_string()
    assert "IS NOT NULL AND" in text and "IS NULL" in text


@pytest.mark.parametrize("op", ["in", "not_in", "contains_any", "contains_all"])
def test_empty_membership(collection, op):
    field = "tags" if op.startswith("contains") else "number"
    condition, params = collection._prepare_filter(Filter(field, op, []))
    assert "%s" not in condition.as_string()
    assert params == []


def test_nested_groups_and_array_membership(collection):
    condition, params = collection._prepare_filter(
        FilterGroup(
            "and",
            [
                Filter("tags", "contains", True),
                FilterGroup("or", [Filter("tags", "contains_all", [None, 2]), Filter("text", "is_null")]),
            ],
        )
    )
    text = condition.as_string()
    assert "jsonb_array_elements" in text and " AND " in text and " OR " in text
    assert [p.obj for p in params] == [True, None, 2]


def test_filter_compiler_preserves_parameter_order_and_isolates_calls(definition_factory):
    compiler = _FilterCompiler(definition_factory())
    condition, params = compiler.compile(
        FilterGroup(
            "and",
            [
                Filter("id", "eq", "one"),
                FilterGroup("or", [Filter("number", "between", [2, 3]), Filter("text", "eq", "last")]),
            ],
        )
    )
    text = condition.as_string()
    assert text.count("%s") == len(params) == 4
    assert text.index('"record_id"') < text.index('"number"') < text.index('"body ""text"""')
    assert params == ["one", 2, 3, "last"]

    next_condition, next_params = compiler.compile(Filter("number", "eq", 4))
    assert next_condition.as_string().count("%s") == 1
    assert next_params == [4]
    assert params == ["one", 2, 3, "last"]

    with pytest.raises(ValueError, match="unknown"):
        compiler.compile(FilterGroup("and", [Filter("id", "eq", "partial"), Filter("unknown", "eq", 5)]))
    _, recovered_params = compiler.compile(Filter("id", "eq", "after-error"))
    assert recovered_params == ["after-error"]


@pytest.mark.parametrize("value", [("tuple",), [("nested",)], {1: "non-string key"}, b"bytes", float("nan")])
def test_json_membership_does_not_silently_coerce_types(collection, value):
    with pytest.raises((TypeError, ValueError)):
        collection._prepare_filter(Filter("tags", "contains", value))


def test_json_equality_rejects_nested_tuple(collection):
    with pytest.raises(TypeError, match="JSON"):
        collection._prepare_filter(Filter("tags", "eq", [("nested",)]))


@pytest.mark.parametrize(
    "expression,error",
    [
        (Filter("text.nested", "eq", 1), NotImplementedError),
        (Filter("unknown", "eq", 1), ValueError),
        (Filter("embedding", "is_null"), NotImplementedError),
        (Filter("text", "postgres.raw", "anything"), NotImplementedError),
        (Filter("number", "starts_with", "1"), TypeError),
        (Filter("text", "contains", "x"), TypeError),
        (Filter("flag", "gt", 1), NotImplementedError),
        (Filter("number", "gt", True), TypeError),
    ],
)
def test_unsupported_filters_fail(collection, expression, error):
    with pytest.raises(error):
        collection._prepare_filter(expression)


def test_order_names_and_directions_validated(collection):
    text = collection._prepare_order_by({"text": False}).as_string()
    assert '"body ""text""" DESC NULLS LAST' in text and '"record_id" ASC' in text
    with pytest.raises(TypeError):
        collection._prepare_order_by({"text": cast(Any, "DESC; DROP TABLE x")})
    with pytest.raises(NotImplementedError):
        collection._prepare_order_by({"tags": True})


@pytest.mark.parametrize("key_type,value", [("int", True), ("int", "1"), ("UUID", 1), ("str", 1)])
async def test_keys_are_strict(definition_factory, record_factory, key_type, value):
    collection = PostgresCollection(
        dict, definition=definition_factory(key_type=key_type), connection_string="host=unused"
    )
    with pytest.raises((TypeError, ValueError)):
        await collection.upsert([record_factory(value)], generate_vectors=False)
    with pytest.raises((TypeError, ValueError)):
        await collection.get([value])


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"connection_string": ""},
        {"connection_string": "x", "client": MagicMock(spec=AsyncConnection)},
        {"client": object()},
    ],
)
def test_client_configuration_rejected(kwargs, monkeypatch):
    monkeypatch.delenv("POSTGRES_CONNECTION_STRING", raising=False)
    with pytest.raises((ValueError, TypeError)):
        PostgresStore(**kwargs)


@pytest.mark.parametrize(
    "options",
    [
        {"dimensions": 2001, "index_kind": "hnsw"},
        {"dimensions": 4001, "index_kind": "hnsw", "annotations": {"postgres.vector_type": "halfvec"}},
        {"dimensions": 16001},
        {"index_kind": "ivf_flat", "distance_function": "manhattan"},
        {"index_kind": "untrusted); DROP TABLE x"},
        {"distance_function": "hamming"},
        {"distance_function": "euclidean_squared_distance"},
        {"annotations": {"postgres.vector_type": "sparsevec"}},
        {"annotations": {"postgres.typo": True}},
        {"index_kind": "hnsw", "annotations": {"postgres.m": "16); DROP TABLE x"}},
        {"index_kind": "hnsw", "annotations": {"postgres.m": 40, "postgres.ef_construction": 64}},
        {"index_kind": "ivf_flat", "annotations": {"postgres.lists": False}},
    ],
)
def test_model_capabilities_rejected_before_io(definition_factory, options):
    with pytest.raises((ValueError, NotImplementedError)):
        PostgresCollection(dict, definition=definition_factory(**options), connection_string="host=unused")


@pytest.mark.parametrize("vector_type", ["int", "float64"])
@pytest.mark.parametrize("annotations", [None, {"postgres.vector_type": "vector"}, {"postgres.vector_type": "halfvec"}])
def test_vector_type_capabilities_rejected_before_client_creation(definition_factory, vector_type, annotations):
    definition = definition_factory(vector_type=vector_type, annotations=annotations)
    with (
        patch("agent_framework_postgres._vector_store.AsyncConnectionPool") as create_pool,
        pytest.raises(ValueError, match=vector_type),
    ):
        PostgresCollection(dict, definition=definition, connection_string="host=unused")
    create_pool.assert_not_called()


def test_inferred_integer_vectors_rejected_before_client_creation():
    @vectorstoremodel(collection_name="integers")
    @dataclass
    class IntegerRecord:
        id: Annotated[str, VectorStoreField("key")]
        embedding: Annotated[list[int] | None, VectorStoreField("vector", dimensions=3)] = None

    with (
        patch("agent_framework_postgres._vector_store.AsyncConnectionPool") as create_pool,
        pytest.raises(ValueError, match="got 'int'"),
    ):
        PostgresCollection(IntegerRecord, connection_string="host=unused")
    create_pool.assert_not_called()


def test_annotations_are_snapshotted_without_copying_generator(definition_factory):
    definition = definition_factory(index_kind="hnsw", annotations={"postgres.m": 12})
    collection = PostgresCollection(dict, definition=definition, connection_string="host=unused")
    definition.vector_fields[0].provider_annotations["postgres.m"] = "untrusted"
    assert "m = 12" in collection._prepare_index(collection._fields[-1]).as_string()


async def test_lifecycle_sql_is_scoped(collection, mock_database):
    connection, _, _ = mock_database
    await collection.ensure_collection_exists()
    statements = [call.args[0].as_string() for call in connection.execute.call_args_list]
    assert 'CREATE TABLE IF NOT EXISTS "public"."documents"' in statements[0]
    assert '"body ""text""" text' in statements[0]
    assert not any("EXTENSION" in statement or "SCHEMA" in statement for statement in statements)
    await collection.ensure_collection_deleted()
    assert connection.execute.call_args.args[0].as_string() == 'DROP TABLE IF EXISTS "public"."documents"'


async def test_sql_upsert_returning_and_duplicate_key_order(collection, mock_database, record_factory):
    _, cursor, _ = mock_database
    cursor.fetchone.side_effect = [("same",), ("same",)]
    assert (
        await collection.upsert([record_factory("same"), record_factory("same")], generate_vectors=False)
        == ["same"] * 2
    )
    statement, params = cursor.executemany.call_args.args
    assert "ON CONFLICT" in statement.as_string() and "RETURNING" in statement.as_string()
    assert len(params) == 2 and params[0][0] == "same"


async def test_generated_insert_does_not_overwrite_on_identity_collision(definition_factory, record_factory):
    collection = PostgresCollection(
        dict, definition=definition_factory(key_type="int", generated=True), connection_string="host=unused"
    )
    connection = MagicMock()
    cursor = MagicMock()
    cursor.executemany = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=(1,))
    connection.cursor.return_value.__aenter__.return_value = cursor
    with patch.object(collection._client, "connection") as acquire:
        acquire.return_value.__aenter__.return_value = connection
        assert await collection.upsert([record_factory(None)], generate_vectors=False) == [1]
    statement = cursor.executemany.call_args.args[0].as_string()
    assert "ON CONFLICT" not in statement


async def test_upsert_missing_returning_key_fails(collection, mock_database, record_factory):
    _, cursor, _ = mock_database
    cursor.fetchone.return_value = None
    with pytest.raises(IntegrationInvalidResponseException):
        await collection.upsert([record_factory()], generate_vectors=False)


async def test_vectors_excluded_from_projection(collection, mock_database):
    _, cursor, _ = mock_database
    await collection.get(["one"])
    assert '"dense vector"' not in cursor.execute.call_args.args[0].as_string()
    await collection.get(["one"], include_vectors=True)
    assert '"dense vector"' in cursor.execute.call_args.args[0].as_string()


@pytest.mark.parametrize("collection", [{"index_kind": "flat"}, {"index_kind": "default"}], indirect=True)
@pytest.mark.parametrize("options", [None, {"exact": True}])
async def test_search_threshold_before_paging_and_alias_collision(collection, mock_database, options):
    _, cursor, _ = mock_database
    results = await collection.search(
        vector=[1, 0, 0],
        filter=Filter("number", "gt", 3),
        score_threshold=0.2,
        top=2,
        skip=1,
        operation_options=options,
    )
    assert results.metadata is not None
    assert results.metadata["approximate"] is False
    query, params = cursor.execute.call_args.args
    text = query.as_string()
    assert text.index("<= %s") < text.index("ORDER BY") < text.index("LIMIT %s OFFSET %s")
    assert " + 0 ASC" in text  # Exact mode deliberately avoids ANN scans.
    assert params[1] == 3 and params[-2:] == [2, 1]
    assert '"dense vector"' not in text.split(" FROM ")[0].split(",")[0]


@pytest.mark.parametrize(
    "collection,adapter",
    [
        ({"annotations": {"postgres.vector_type": "vector"}}, PgVector),
        ({"annotations": {"postgres.vector_type": "halfvec"}}, HalfVector),
    ],
    indirect=["collection"],
)
@pytest.mark.parametrize("vector", [[0, 1, 2], (0, 1, 2), range(3)], ids=["list", "tuple", "range"])
async def test_numeric_sequences_adapted_for_storage_and_search(
    collection, mock_database, record_factory, adapter, vector
):
    adapted = _prepare_value(collection.definition.vector_fields[0], vector)
    assert isinstance(adapted, adapter)
    assert adapted.to_list() == [0.0, 1.0, 2.0]
    await collection.search(vector=vector)
    _, cursor, _ = mock_database
    query_vector = cursor.execute.call_args.args[1][0]
    assert isinstance(query_vector, adapter)
    assert query_vector.to_list() == [0.0, 1.0, 2.0]
    await collection.upsert([record_factory(embedding=tuple(vector))], generate_vectors=False)
    stored_vector = cursor.executemany.call_args.args[1][0][-1]
    assert isinstance(stored_vector, adapter)
    assert stored_vector.to_list() == [0.0, 1.0, 2.0]


async def test_get_and_search_share_filter_preparation(collection, mock_database):
    expression = Filter("number", "gt", 3)
    with patch.object(collection, "_prepare_filter", wraps=collection._prepare_filter) as prepare:
        await collection.get(filter=expression)
        await collection.search(vector=[1, 0, 0], filter=expression)
    assert prepare.call_count == 2
    for call in prepare.call_args_list:
        assert call.args[0] == expression
        assert call.args[0] is not expression


async def test_closed_collection_rejects_empty_batches(collection, mock_database):
    await collection.close()
    with pytest.raises(IntegrationException, match="closed"):
        await collection.upsert([], generate_vectors=False)
    with pytest.raises(IntegrationException, match="closed"):
        await collection.get([])
    with pytest.raises(IntegrationException, match="closed"):
        await collection.delete([])
    mock_database[2].assert_not_called()


@pytest.mark.parametrize("required", [False, True])
async def test_search_tool_param_without_default(collection, mock_database, required):
    parameter = Param("text", str, required=required)
    assert not parameter.has_default
    assert parameter.default is Param("other", str).default
    collection.embedding_generator = MagicMock(
        get_embeddings=AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[1, 0, 0])]))
    )
    search_tool = create_vector_search_tool(
        collection,
        filter=FilterGroup("and", [Filter("id", "eq", "one"), Filter("text", "eq", parameter)]),
    )
    assert ("text" in search_tool.parameters()["required"]) is required

    assert await search_tool.invoke(arguments={"query": "find", "text": "provided"}, skip_parsing=True) == []
    _, cursor, _ = mock_database
    statement, params = cursor.execute.call_args.args
    assert statement.as_string().count("IS NOT DISTINCT FROM") == 2
    assert params[1:3] == ["one", "provided"]

    if not required:
        assert await search_tool.invoke(arguments={"query": "find"}, skip_parsing=True) == []
        statement, params = cursor.execute.call_args.args
        assert statement.as_string().count("IS NOT DISTINCT FROM") == 1
        assert params[1] == "one"


@pytest.mark.parametrize(
    "options,error",
    [
        ({"typo": 1}, NotImplementedError),
        ({"exact": "yes"}, TypeError),
        ({"exact": False}, ValueError),
        ({"hnsw_ef_search": 10}, ValueError),
        ({"ivfflat_probes": 2}, ValueError),
    ],
)
@pytest.mark.parametrize("collection", [{"index_kind": "flat"}, {"index_kind": "default"}], indirect=True)
async def test_unknown_or_inapplicable_search_options(collection, mock_database, options, error):
    with pytest.raises(error):
        await collection.search(vector=[1, 0, 0], operation_options=options)
    mock_database[2].assert_not_called()


async def test_unsupported_query_modes(collection, mock_database):
    with pytest.raises(NotImplementedError):
        await collection.search("text", search_type="keyword_hybrid", vector=[1, 0, 0])
    with pytest.raises(NotImplementedError):
        await collection.search("text")
    with pytest.raises(NotImplementedError):
        await collection.search(vector=[1, 0, 0], additional_property_name="text")
    mock_database[2].assert_not_called()


async def test_core_dimension_rejection_precedes_io(collection, mock_database, record_factory):
    with pytest.raises(ValueError, match="index 1"):
        await collection.upsert([record_factory(), record_factory(embedding=[1])], generate_vectors=False)
    with pytest.raises(ValueError, match="dimensions"):
        await collection.search(vector=[1])
    mock_database[2].assert_not_called()


async def test_empty_batches_do_not_acquire_connection(collection, mock_database):
    assert await collection.upsert([], generate_vectors=False) == []
    assert await collection.get([]) == []
    await collection.delete([])
    mock_database[2].assert_not_called()


async def test_borrowed_client_not_closed_and_driver_errors_chained():
    connection = MagicMock(spec=AsyncConnection)
    connection.close = AsyncMock()
    connection.transaction.return_value.__aenter__.side_effect = OperationalError("broken")
    owner = _Client(None, connection)
    with pytest.raises(IntegrationException) as exc:
        async with owner.connection():
            pytest.fail("Connection acquisition should fail")
    assert isinstance(exc.value.__cause__, OperationalError)
    await owner.close()
    await owner.close()
    connection.close.assert_not_called()
    with pytest.raises(RuntimeError, match="closed"):
        async with owner.connection():
            pytest.fail("Closed wrapper must reject operations")


async def test_store_collection_close_does_not_close_owned_pool(definition_factory):
    store = PostgresStore(connection_string="host=unused")
    collection = store.get_collection(dict, definition=definition_factory())
    assert not collection.managed_client
    with patch.object(store._client.client, "close", new_callable=AsyncMock) as close:
        await collection.close()
        close.assert_not_called()
        await store.close()
        await store.close()
        close.assert_awaited_once()


def test_value_adaptation_and_fulltext_rejection():
    assert _prepare_value(VectorStoreField("key", name="id", type_="UUID"), str(UUID(int=1))) == UUID(int=1)
    with pytest.raises(TypeError):
        _prepare_value(VectorStoreField("vector", name="v", dimensions=3), b"not a dense vector")
    with pytest.raises(ValueError):
        _prepare_value(VectorStoreField("data", name="d", type_="datetime"), "2026-01-01T00:00:00")
    with pytest.raises(NotImplementedError):
        PostgresCollection(
            dict,
            connection_string="host=unused",
            collection_name="data",
            definition=VectorStoreCollectionDefinition([
                VectorStoreField("key", name="id", type_="str"),
                VectorStoreField("data", name="text", type_="str", is_full_text_indexed=True),
            ]),
        )


@vectorstoremodel
@dataclass
class TypedRecord:
    id: Annotated[UUID, VectorStoreField("key", is_auto_generated=True)]
    value: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


def test_decorated_model_infers_key_type():
    collection = PostgresCollection(TypedRecord, collection_name="typed", connection_string="host=unused")
    assert collection.definition.key_field.type_ == "UUID"
    assert isinstance(collection._client.client, AsyncConnectionPool)


def test_normal_float_vectors_restore_typed_models():
    collection = PostgresCollection(TypedRecord, collection_name="typed", connection_string="host=unused")
    field = collection.definition.vector_fields[0]
    assert field.type_ == "float"
    record = collection.deserialize({
        "id": UUID(int=1),
        "value": "text",
        "embedding": _prepare_value(field, [0.1, 1, 0]),
    })
    assert isinstance(record, TypedRecord)
    assert record.id == UUID(int=1)
    assert record.embedding == pytest.approx([0.1, 1, 0])
