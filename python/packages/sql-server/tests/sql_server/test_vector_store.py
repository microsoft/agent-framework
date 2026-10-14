# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from dataclasses import dataclass
from functools import partial
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch

import mssql_python
import pytest
from agent_framework import (
    Embedding,
    Filter,
    FilterGroup,
    GeneratedEmbeddings,
    Param,
    SecretString,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    create_vector_search_tool,
    vectorstoremodel,
)
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException

from agent_framework_sql_server import SqlServerCollection, SqlServerCommittedCleanupException, SqlServerStore
from agent_framework_sql_server import _vector_store as module
from agent_framework_sql_server._vector_store import _Client


@pytest.fixture
def definition() -> VectorStoreCollectionDefinition:
    return VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str", storage_name="record]id"),
            VectorStoreField("data", name="text", type_="str", storage_name="body [text]", is_indexed=True),
            VectorStoreField("data", name="count", type_="int"),
            VectorStoreField("data", name="tags", type_="list"),
            VectorStoreField("vector", name="embedding", type_="float32", dimensions=3, storage_name="vector [one]"),
        ],
        collection_name="documents",
    )


@pytest.fixture
def collection(definition):
    return SqlServerCollection(dict, definition=definition, connection_string="Server=unused;Database=test")


def make_record(key="one", *, text="literal %_[abc]!", count=1, tags=None, embedding=None):
    return {
        "id": key,
        "text": text,
        "count": count,
        "tags": ["tag"] if tags is None else tags,
        "embedding": [1, 0, 0] if embedding is None else embedding,
    }


def fake_connection():
    connection = MagicMock(spec=mssql_python.Connection)
    cursor = MagicMock(spec=mssql_python.Cursor)
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    connection.cursor.return_value = cursor
    return connection, cursor


@pytest.fixture
def mock_io(collection):
    connection, cursor = fake_connection()

    with patch.object(collection._client, "run", side_effect=lambda operation: operation(cursor)) as request:
        yield connection, cursor, request


def test_fields_fail_early_if_unsupported(definition):
    with pytest.raises(NotImplementedError, match="approximate"):
        SqlServerCollection(
            dict,
            connection_string="unused",
            definition=VectorStoreCollectionDefinition(
                [
                    definition.key_field,
                    VectorStoreField("vector", name="v", dimensions=3, index_kind="disk_ann"),
                ],
                collection_name="documents",
            ),
        )
    with pytest.raises(NotImplementedError, match="full-text"):
        SqlServerCollection(
            dict,
            connection_string="unused",
            definition=VectorStoreCollectionDefinition(
                [
                    definition.key_field,
                    VectorStoreField("data", name="text", type_="str", is_full_text_indexed=True),
                ],
                collection_name="documents",
            ),
        )
    with pytest.raises(ValueError, match="must be one"):
        SqlServerCollection(
            dict,
            connection_string="unused",
            definition=VectorStoreCollectionDefinition(
                [
                    VectorStoreField("key", name="id", type_="bool"),
                    VectorStoreField("vector", name="embedding", dimensions=3),
                ],
                collection_name="documents",
            ),
        )


async def test_create_check_drop_use_scoped_quoted_identifiers_and_bound_catalog_values(definition):
    name = "table]'; DROP TABLE dbo.other; --"
    schema = "schema]'; --"
    collection = SqlServerCollection(
        dict, definition=definition, collection_name=name, schema=schema, connection_string="x"
    )
    connection, cursor = fake_connection()

    with patch.object(collection._client, "run", side_effect=lambda operation: operation(cursor)):
        await collection.ensure_collection_exists()
        create, index = cursor.execute.call_args_list
        query, params = create.args
        assert "CREATE TABLE [schema]]'; --].[table]]'; DROP TABLE dbo.other; --]" in query
        assert "[record]]id]" in query and "VECTOR(3)" in query
        assert name not in query and schema not in query
        assert params == (schema, name)
        assert "CREATE INDEX [af_sql_" in index.args[0]
        assert index.args[1][:2] == (schema, name)
        assert await collection.collection_exists() is False
        cursor.fetchone.return_value = (1,)
        assert await collection.collection_exists() is True
        await collection.ensure_collection_deleted()
        assert cursor.execute.call_args.args[0] == f"DROP TABLE IF EXISTS {collection._table}"
        assert "CASCADE" not in cursor.execute.call_args.args[0]


async def test_batch_upsert_preserves_duplicate_key_order_and_binds_json(collection, mock_io):
    _, cursor, acquire = mock_io
    cursor.fetchone.side_effect = [None, ("one",), ("one",), ("one",)]
    keys = await collection.upsert([make_record("one"), make_record("one", text="updated")], generate_vectors=False)
    assert keys == ["one", "one"]
    acquire.assert_awaited_once()
    calls = cursor.execute.call_args_list
    assert len(calls) == 4
    assert "WITH (UPDLOCK, HOLDLOCK)" in calls[0].args[0]
    assert "OUTPUT INSERTED.[record]]id]" in calls[1].args[0]
    assert "OUTPUT INSERTED.[record]]id]" in calls[3].args[0]
    assert "[1.0,0.0,0.0]" in calls[1].args[1]
    assert "literal %_[abc]!" not in calls[1].args[0]
    assert "literal %_[abc]!" in calls[1].args[1]


async def test_generated_key_inserts_without_key_or_prior_lookup():
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="int", is_auto_generated=True),
            VectorStoreField("data", name="text", type_="str"),
            VectorStoreField("vector", name="v", dimensions=3),
        ],
        collection_name="generated",
    )
    collection = SqlServerCollection(dict, definition=definition, connection_string="x")
    connection, cursor = fake_connection()
    cursor.fetchone.return_value = (123,)

    with patch.object(collection._client, "run", side_effect=lambda operation: operation(cursor)):
        assert await collection.upsert([{"text": "a", "v": [1, 0, 0]}], generate_vectors=False) == [123]
        assert cursor.execute.call_count == 1
        assert "INSERT INTO" in cursor.execute.call_args.args[0]
        assert "OUTPUT INSERTED.[id]" in cursor.execute.call_args.args[0]
        assert cursor.execute.call_args.args[1] == ("a", "[1.0,0.0,0.0]")


async def test_generated_identity_refuses_explicit_new_key():
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="int", is_auto_generated=True),
            VectorStoreField("vector", name="v", dimensions=3),
        ],
        collection_name="generated",
    )
    collection = SqlServerCollection(dict, definition=definition, connection_string="x")
    connection, cursor = fake_connection()

    with (
        patch.object(collection._client, "run", side_effect=lambda operation: operation(cursor)),
        pytest.raises(NotImplementedError, match="IDENTITY"),
    ):
        await collection.upsert([{"id": 42, "v": [1, 0, 0]}], generate_vectors=False)
    assert cursor.execute.call_count == 1
    assert "WITH (UPDLOCK, HOLDLOCK)" in cursor.execute.call_args.args[0]


async def test_upsert_missing_key_raises_integration_response_error(collection, mock_io):
    _, cursor, _ = mock_io
    cursor.fetchone.return_value = None
    with pytest.raises(IntegrationInvalidResponseException, match="inserted key"):
        await collection.upsert([make_record()], generate_vectors=False)


async def test_get_keys_preserves_input_order_and_optional_vectors(collection, mock_io):
    _, cursor, _ = mock_io
    cursor.fetchall.return_value = [
        ("two", "second", 2, '["b"]'),
        ("one", "first", 1, '["a"]'),
    ]
    rows = await collection.get(["one", "missing", "two", "one"])
    assert [row["id"] for row in rows] == ["one", "two", "one"]
    assert all("embedding" not in row for row in rows)
    assert rows[0]["tags"] == ["a"]
    assert "[vector [one]]]" not in cursor.execute.call_args.args[0]

    cursor.fetchall.return_value = [("one", "first", 1, '["a"]', "[1.0,0.0,0.0]")]
    rows = await collection.get(["one"], include_vectors=True)
    assert rows[0]["embedding"] == [1.0, 0.0, 0.0]
    assert "[vector [one]]]" in cursor.execute.call_args.args[0]


async def test_get_delete_large_key_batches_do_not_exceed_server_parameter_budget(collection, mock_io):
    _, cursor, _ = mock_io
    keys = [str(index) for index in range(1001)]
    cursor.fetchall.side_effect = [
        [("0", "first", 0, "[]")],
        [("1000", "last", 1000, "[]")],
    ]
    assert [row["id"] for row in await collection.get(keys)] == ["0", "1000"]
    assert [len(call.args[1]) for call in cursor.execute.call_args_list] == [1000, 1]
    cursor.execute.reset_mock()
    await collection.delete(keys)
    assert [len(call.args[1]) for call in cursor.execute.call_args_list] == [1000, 1]
    assert all("DELETE FROM [dbo].[documents]" in call.args[0] for call in cursor.execute.call_args_list)


async def test_filtered_listing_orders_and_pages_on_server(collection, mock_io):
    _, cursor, _ = mock_io
    await collection.get(filter=Filter("count", "gt", 1), order_by={"text": False}, skip=3, top=2)
    sql, params = cursor.execute.call_args.args
    assert "([count] IS NOT NULL AND [count] > ?)" in sql
    assert "CASE WHEN [body [text]]] IS NULL THEN 1 ELSE 0 END" in sql
    assert "[body [text]]] DESC" in sql
    assert sql.endswith("OFFSET ? ROWS FETCH NEXT ? ROWS ONLY")
    assert params == (1, 3, 2)


async def test_exact_search_filters_and_threshold_before_paging(collection, mock_io):
    _, cursor, _ = mock_io
    cursor.fetchall.return_value = [("one", "first", 1, "[]", 0.2)]
    results = await collection.search(
        vector=[1, 0, 0], filter=Filter("count", "gte", 1), score_threshold=0.25, skip=1, top=2
    )
    assert results.metadata == {"distance_function": "DEFAULT", "approximate": False}
    values = [item async for item in results]
    assert values == [{"record": {"id": "one", "text": "first", "count": 1, "tags": []}, "score": 0.2}]
    statement, params = cursor.execute.call_args.args
    assert "VECTOR_DISTANCE('cosine', CAST(? AS VECTOR(3)), t.[vector [one]]])" in statement
    assert statement.index("d.[distance] <= ?") < statement.index("ORDER BY") < statement.index("OFFSET ?")
    assert "t.[count] >= ?" in statement
    assert params == ("[1.0,0.0,0.0]", 1, 0.25, 1, 2)
    assert "[vector [one]]]" not in statement.split(" FROM ")[0]


async def test_multiple_vector_columns_select_requested_dimensions_and_decode_values():
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("vector", name="primary", dimensions=3),
            VectorStoreField("vector", name="secondary", storage_name="other]vector", dimensions=2),
        ],
        collection_name="multi_vectors",
    )
    collection = SqlServerCollection(dict, definition=definition, connection_string="x")
    connection, cursor = fake_connection()
    cursor.fetchall.return_value = [("first", 0.0)]

    with patch.object(collection._client, "run", side_effect=lambda operation: operation(cursor)):
        results = [item async for item in await collection.search(vector=[0, 1], vector_property_name="secondary")]
        assert results[0]["record"] == {"id": "first"}
        assert "CAST(? AS VECTOR(2)), t.[other]]vector]" in cursor.execute.call_args.args[0]
        cursor.fetchall.return_value = [("first", "[1,0,0]", "[0,1]")]
        record = (await collection.get(["first"], include_vectors=True))[0]
    assert record["primary"] == [1.0, 0.0, 0.0]
    assert record["secondary"] == [0.0, 1.0]


@pytest.mark.parametrize(
    "metric,raw_distance,cutoff,expected",
    [
        ("cosine_similarity", 0.2, 0.2, 0.8),
        ("dot_prod", -0.8, -0.8, 0.8),
        ("negative_dot_prod", -0.8, -0.8, -0.8),
        ("euclidean_distance", 0.2, 0.2, 0.2),
    ],
)
async def test_metric_score_direction_and_threshold(metric, raw_distance, cutoff, expected):
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str"),
            VectorStoreField("vector", name="v", dimensions=3, distance_function=metric),
        ],
        collection_name="metrics",
    )
    collection = SqlServerCollection(dict, definition=definition, connection_string="x")
    connection, cursor = fake_connection()
    cursor.fetchall.return_value = [("first", raw_distance)]

    with patch.object(collection._client, "run", side_effect=lambda operation: operation(cursor)):
        results = [item async for item in await collection.search(vector=[1, 0, 0], score_threshold=expected)]
    assert results[0]["score"] == pytest.approx(expected)
    sql, params = cursor.execute.call_args.args
    assert "d.[distance] <= ?" in sql
    assert params[1] == pytest.approx(cutoff)


async def test_search_tool_resolves_filter_parameters_on_backend(collection, mock_io):
    _, cursor, _ = mock_io
    collection.embedding_generator = MagicMock(
        get_embeddings=AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[1, 0, 0])]))
    )
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup(
            "and",
            [
                Filter("id", "eq", "one"),
                Filter("text", "contains_text", Param("needle", str | None, default=None, omit_if_none=True)),
            ],
        ),
    )
    assert await tool.invoke(arguments={"query": "sample", "needle": "[%_]"}, skip_parsing=True) == []
    sql, params = cursor.execute.call_args.args
    assert "CONVERT(VARBINARY(MAX)" in sql
    assert params[1:3] == ("one", "%[[]!%!_]%")
    assert await tool.invoke(arguments={"query": "sample"}, skip_parsing=True) == []
    sql, params = cursor.execute.call_args.args
    assert "LIKE" not in sql
    assert params[1] == "one"


async def test_invalid_options_and_dimension_fail_before_io(collection, mock_io):
    _, cursor, acquire = mock_io
    with pytest.raises(NotImplementedError):
        await collection.search(vector=[1, 0, 0], operation_options={"approximate": True})
    with pytest.raises(NotImplementedError):
        await collection.search(vector=[1, 0, 0], search_type="keyword_hybrid", values="query")
    with pytest.raises(ValueError, match="dimensions"):
        await collection.search(vector=[1, 0])
    with pytest.raises(ValueError, match="finite"):
        await collection.search(vector=[1, 0, 0], score_threshold=10**1000)
    with pytest.raises(ValueError, match="index 1"):
        await collection.upsert([make_record(), make_record(embedding=[1])], generate_vectors=False)
    assert not acquire.called and not cursor.execute.called


async def test_closed_collection_rejects_empty_operations(collection, mock_io):
    _, cursor, acquire = mock_io
    await collection.close()
    with pytest.raises(IntegrationException, match="closed"):
        await collection.get([])
    with pytest.raises(IntegrationException, match="closed"):
        await collection.upsert([], generate_vectors=False)
    with pytest.raises(IntegrationException, match="closed"):
        await collection.delete([])
    assert not acquire.called and not cursor.execute.called


@pytest.fixture(params=["collection", "store"])
def constructor(request, definition, monkeypatch):
    monkeypatch.delenv("SQL_SERVER_CONNECTION_STRING", raising=False)
    return (
        partial(SqlServerCollection, dict, definition=definition) if request.param == "collection" else SqlServerStore
    )


def test_settings_priority_and_secret_masking(constructor, monkeypatch, tmp_path):
    monkeypatch.setenv("SQL_SERVER_CONNECTION_STRING", "environment-secret")
    env_file = tmp_path / "settings.env"
    env_file.write_text("SQL_SERVER_CONNECTION_STRING='file-secret'\n", encoding="utf-8")
    value = SecretString("explicit-secret")
    instance = constructor(connection_string=value, env_file_path=str(env_file))
    assert instance._client.connection_string is value
    assert "explicit-secret" not in repr(value) and str(value) == "**********"
    assert constructor(env_file_path=str(env_file))._client.connection_string.get_secret_value() == "file-secret"
    assert constructor()._client.connection_string.get_secret_value() == "environment-secret"


def test_settings_require_explicit_file_or_environment(constructor, monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("SQL_SERVER_CONNECTION_STRING=implicit\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="required"):
        constructor()
    with pytest.raises(ValueError, match="must not be empty"):
        constructor(connection_string="")
    with pytest.raises(FileNotFoundError):
        constructor(env_file_path=str(tmp_path / "missing.env"), connection_string="explicit")


def test_public_api_has_no_borrowed_connection_or_factory(constructor):
    connection, _ = fake_connection()
    for api in (SqlServerStore, SqlServerCollection):
        parameters = inspect.signature(api).parameters
        assert "client" not in parameters
        assert "client_factory" not in parameters
        assert "_shared_client" not in parameters
    assert "SqlServerClient" not in module.__dict__
    with pytest.raises(TypeError, match="client"):
        constructor(connection_string="Server=unused", client=connection)


@pytest.mark.parametrize("timeout", [-1, True, 1.5, "30"])
def test_query_timeout_requires_non_negative_integer(constructor, timeout):
    with pytest.raises(ValueError, match="query_timeout"):
        constructor(connection_string="Server=unused", query_timeout=timeout)


async def test_store_deletion_quotes_supplied_table_name(definition):
    store = SqlServerStore(connection_string="x")
    connection, cursor = fake_connection()

    with patch.object(store._client, "run", side_effect=lambda operation: operation(cursor)):
        cursor.fetchall.return_value = [("table]'; --",)]
        await store.ensure_collection_deleted("table]'; --")
    assert cursor.execute.call_args.args[0] == "DROP TABLE IF EXISTS [dbo].[table]]'; --]"
    assert "CASCADE" not in cursor.execute.call_args.args[0]


async def test_connection_and_all_operations_stay_on_one_worker():
    connection, cursor = fake_connection()
    client = _Client(SecretString("Server=unused;Database=test"), query_timeout=30)
    caller_thread = threading.get_ident()
    worker_threads: list[int] = []

    def record_thread(*args, **kwargs):
        worker_threads.append(threading.get_ident())

    def open_connection(*args, **kwargs):
        record_thread()
        return connection

    def open_cursor():
        record_thread()
        return cursor

    def fetchone():
        record_thread()
        return ("found",)

    connection.cursor.side_effect = open_cursor
    connection.commit.side_effect = record_thread
    connection.close.side_effect = record_thread
    cursor.execute.side_effect = record_thread
    cursor.fetchone.side_effect = fetchone
    cursor.close.side_effect = record_thread
    with patch.object(module.mssql_python, "connect", side_effect=open_connection) as connect:
        assert client._executor is None
        try:

            def operation(raw):
                module._execute(raw, "SELECT ?", ["O'Brien"])
                return raw.fetchone()

            assert await client.run(operation) == ("found",)
            assert await client.run(operation) == ("found",)
            executor = client._executor
            assert executor is not None and executor._max_workers == 1
            assert cursor.execute.call_args.args == ("SELECT ?", ("O'Brien",))
            assert connect.call_count == 2
            assert connect.call_args.args == ("Server=unused;Database=test",)
            assert connect.call_args.kwargs == {"autocommit": False}
            assert connection.timeout == 30
            assert len(set(worker_threads)) == 1 and worker_threads[0] != caller_thread
            assert connection.commit.call_count == connection.close.call_count == cursor.close.call_count == 2
            connection.rollback.assert_not_called()
        finally:
            await client.close()
            await client.close()
    assert executor._shutdown
    with pytest.raises(RuntimeError, match="closed"):
        await client.run(operation)


async def test_store_children_share_ownership_without_closing_worker(definition):
    connection, cursor = fake_connection()
    cursor.fetchall.return_value = [("existing",)]
    with patch.object(module.mssql_python, "connect", return_value=connection):
        async with SqlServerStore(connection_string="Server=unused;Database=test", query_timeout=5) as store:
            collection = store.get_collection(dict, definition=definition)
            assert collection._client is store._client
            assert collection._client.query_timeout == 5
            assert not collection.managed_client
            assert store.managed_client
            assert await store.list_collection_names() == ["existing"]
            executor = store._client._executor
            assert executor is not None
            await collection.close()
            assert not executor._shutdown
        assert executor._shutdown
    connection.commit.assert_called_once()
    connection.close.assert_called_once()


async def test_cancelled_operation_and_close_wait_for_worker_cleanup():
    connection, cursor = fake_connection()
    started, release = threading.Event(), threading.Event()

    def slow_execute(*args):
        started.set()
        assert release.wait(timeout=10)

    cursor.execute.side_effect = slow_execute
    client = _Client(SecretString("Server=unused;Database=test"))
    with patch.object(module.mssql_python, "connect", return_value=connection):
        try:
            operation = asyncio.create_task(client.run(lambda raw: module._execute(raw, "SELECT 1")))
            assert await asyncio.to_thread(started.wait, 5)
            operation.cancel()
            closing = asyncio.create_task(client.close())
            await asyncio.sleep(0)
            assert not operation.done() and not closing.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await operation
        await closing
    connection.commit.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
    assert client._executor is not None and client._executor._shutdown


async def test_cancelled_failing_operation_preserves_cancellation_until_worker_cleanup(caplog):
    connection, cursor = fake_connection()
    started, release = threading.Event(), threading.Event()
    driver_error = mssql_python.OperationalError("query failed", "worker failure")

    def fail_after_cancellation(*args):
        started.set()
        assert release.wait(timeout=10)
        raise driver_error

    cursor.execute.side_effect = fail_after_cancellation
    client = _Client(SecretString("Server=unused;Database=test"))
    with (
        patch.object(module.mssql_python, "connect", return_value=connection),
        caplog.at_level(logging.WARNING, logger=module.__name__),
    ):
        try:
            operation = asyncio.create_task(client.run(lambda raw: module._execute(raw, "SELECT 1")))
            assert await asyncio.to_thread(started.wait, 5)
            operation.cancel()
            await asyncio.sleep(0)
            operation.cancel()
            closing = asyncio.create_task(client.close())
            await asyncio.sleep(0)
            assert not operation.done() and not closing.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await operation
        await closing
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
    assert any(
        "worker failed after caller cancellation" in record.message
        and record.exc_info is not None
        and isinstance(record.exc_info[1], IntegrationException)
        and record.exc_info[1].__cause__ is driver_error
        for record in caplog.records
    )


async def test_driver_error_is_chained_and_owned_connection_rolled_back():
    connection, cursor = fake_connection()
    cursor.execute.side_effect = [
        None,
        mssql_python.OperationalError("constraint violation", "bad record"),
    ]
    client = _Client(SecretString("Server=unused;Database=test"))

    def batch(raw):
        module._execute(raw, "INSERT INTO [notes] ([id]) VALUES (?)", ["first"])
        module._execute(raw, "INSERT INTO [notes] ([id]) VALUES (?)", ["invalid"])

    try:
        with (
            patch.object(module.mssql_python, "connect", return_value=connection),
            pytest.raises(IntegrationException) as error,
        ):
            await client.run(batch)
    finally:
        await client.close()
    assert isinstance(error.value.__cause__, mssql_python.OperationalError)
    assert cursor.execute.call_count == 2
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


async def test_commit_failure_rolls_back_and_closes_connection():
    connection, cursor = fake_connection()
    connection.commit.side_effect = mssql_python.OperationalError("commit failed", "database unavailable")
    client = _Client(SecretString("Server=unused;Database=test"))
    try:
        with (
            patch.object(module.mssql_python, "connect", return_value=connection),
            pytest.raises(IntegrationException) as error,
        ):
            await client.run(lambda raw: module._execute(raw, "SELECT 1"))
    finally:
        await client.close()
    assert isinstance(error.value.__cause__, mssql_python.OperationalError)
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


async def test_committed_generated_key_is_distinguishable_from_failed_upsert():
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="int", is_auto_generated=True),
            VectorStoreField("data", name="text", type_="str"),
        ],
        collection_name="generated",
    )
    collection = SqlServerCollection(dict, definition=definition, connection_string="Server=unused;Database=test")
    connection, cursor = fake_connection()
    cursor.fetchone.return_value = (42,)
    cleanup_error = mssql_python.OperationalError("close failed", "connection cleanup error")
    connection.close.side_effect = cleanup_error
    try:
        with (
            patch.object(module.mssql_python, "connect", return_value=connection),
            pytest.raises(SqlServerCommittedCleanupException) as error,
        ):
            await collection.upsert([{"text": "created"}], generate_vectors=False)
    finally:
        await collection.close()
    assert "committed" in str(error.value)
    assert "do not retry" in str(error.value)
    assert error.value.__cause__ is cleanup_error
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


async def test_cleanup_failure_during_rollback_preserves_original_error(caplog):
    connection, cursor = fake_connection()
    operation_error = mssql_python.OperationalError("query failed", "operation error")
    cursor.execute.side_effect = operation_error
    connection.close.side_effect = mssql_python.OperationalError("close failed", "cleanup error")
    client = _Client(SecretString("Server=unused;Database=test"))
    try:
        with (
            patch.object(module.mssql_python, "connect", return_value=connection),
            caplog.at_level(logging.WARNING, logger=module.__name__),
            pytest.raises(IntegrationException) as error,
        ):
            await client.run(lambda raw: module._execute(raw, "INSERT INTO [notes] ([id]) VALUES (?)", ["first"]))
    finally:
        await client.close()
    assert not isinstance(error.value, SqlServerCommittedCleanupException)
    assert error.value.__cause__ is operation_error
    assert any("cleanup also failed" in record.message for record in caplog.records)
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()


async def test_connection_failure_is_chained_and_worker_shuts_down():
    client = _Client(SecretString("Server=unused;Database=test"))
    try:
        with (
            patch.object(
                module.mssql_python,
                "connect",
                side_effect=mssql_python.OperationalError("connect failed", "server unavailable"),
            ),
            pytest.raises(IntegrationException) as error,
        ):
            await client.run(lambda raw: module._execute(raw, "SELECT 1"))
    finally:
        await client.close()
    assert isinstance(error.value.__cause__, mssql_python.OperationalError)
    assert client._executor is not None and client._executor._shutdown


@vectorstoremodel(collection_name="typed_sql_notes")
@dataclass
class TypedNote:
    id: Annotated[str, VectorStoreField("key")]
    title: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def test_decorated_records_round_trip_without_vectors_by_default():
    collection = SqlServerCollection(TypedNote, connection_string="x")
    connection, cursor = fake_connection()
    cursor.fetchall.return_value = [("one", "title")]

    with patch.object(collection._client, "run", side_effect=lambda operation: operation(cursor)):
        assert await collection.get(["one"]) == [TypedNote("one", "title", None)]
