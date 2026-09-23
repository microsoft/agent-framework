# Copyright (c) Microsoft. All rights reserved.

"""Asynchronous Agent Framework collections backed by SQL Server VECTOR columns."""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import AsyncGenerator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any, ClassVar, Generic, Protocol, TypeAlias, cast

import aioodbc
import pyodbc
from agent_framework import (
    BaseVectorCollection,
    BaseVectorSearch,
    BaseVectorStore,
    SearchResults,
    SecretString,
    VectorStoreCollectionDefinition,
    load_settings,
)
from agent_framework._vector_filters import FilterExpression
from agent_framework._vectors import EmbeddingClient, SearchType, Vector
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException
from typing_extensions import Self, TypedDict, TypeVar

from ._sql import (
    MAX_PARAMETERS,
    _column_type,  # pyright: ignore[reportPrivateUsage]
    _filter_field,  # pyright: ignore[reportPrivateUsage]
    _FilterCompiler,  # pyright: ignore[reportPrivateUsage]
    _metric_for,  # pyright: ignore[reportPrivateUsage]
    _parse_value,  # pyright: ignore[reportPrivateUsage]
    _prepare_value,  # pyright: ignore[reportPrivateUsage]
    _quote_identifier,  # pyright: ignore[reportPrivateUsage]
)

KeyT = TypeVar("KeyT", default=Any)
ModelT = TypeVar("ModelT", default=Any)
_KEY_BATCH_SIZE = 1000
_SAVEPOINT = "af_vector_operation"
SqlServerClient: TypeAlias = aioodbc.Connection | aioodbc.Pool


class _Cursor(Protocol):
    async def execute(self, sql: str, *parameters: Any) -> Any: ...

    async def fetchone(self) -> Sequence[Any] | None: ...

    async def fetchall(self) -> Sequence[Sequence[Any]]: ...

    async def close(self) -> None: ...


@asynccontextmanager
async def _cursor(connection: aioodbc.Connection) -> AsyncGenerator[_Cursor]:
    # aioodbc's cursor context manager commits its connection on exit, including borrowed transactions.
    cursor = cast(_Cursor, await connection.cursor())  # pyright: ignore[reportUnknownMemberType]
    try:
        yield cursor
    finally:
        await cursor.close()


class SqlServerSettings(TypedDict, total=False):
    """Connection settings resolved from explicit values, a selected .env file, or ``SQL_SERVER_`` variables."""

    connection_string: SecretString | None
    """Driver connection string, resolved from ``SQL_SERVER_CONNECTION_STRING`` and kept masked."""


def _validate_options(options: Mapping[str, Any] | None) -> None:
    if options:
        raise NotImplementedError(f"Unsupported SQL Server operation option(s): {', '.join(sorted(options))}.")


async def _execute(cursor: _Cursor, statement: str, parameters: Sequence[Any] = ()) -> None:
    if parameters:
        await cursor.execute(statement, tuple(parameters))
    else:
        await cursor.execute(statement)


async def _rows(cursor: _Cursor, count: int) -> list[Sequence[Any]]:
    result = list(await cursor.fetchall())
    for row in result:
        if len(row) != count:
            raise IntegrationInvalidResponseException("SQL Server returned a row with an unexpected column count.")
    return result


def _check_parameter_count(parameters: Sequence[Any]) -> None:
    if len(parameters) > MAX_PARAMETERS:
        raise ValueError(f"SQL Server queries support at most {MAX_PARAMETERS} bound parameters.")


class _Client:
    """Own a lazy pool and its dedicated ODBC worker, or borrow an async connection/pool."""

    def __init__(self, connection_string: SecretString | None, client: SqlServerClient | None) -> None:
        if (connection_string is None) == (client is None):
            raise ValueError("Supply exactly one of connection_string or client.")
        if connection_string is not None and not connection_string.get_secret_value().strip():
            raise ValueError("connection_string must not be empty.")
        if client is not None and not isinstance(client, (aioodbc.Connection, aioodbc.Pool)):
            raise TypeError("client must be an aioodbc Connection or Pool.")
        self.connection_string = connection_string
        self.client = client
        self.closed = False
        self._pool: aioodbc.Pool | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._init_lock = asyncio.Lock()
        self._borrowed_lock = asyncio.Lock()

    def ensure_open(self) -> None:
        if self.closed:
            raise RuntimeError("The SQL Server client is closed.")

    async def _owned_pool(self) -> aioodbc.Pool:
        async with self._init_lock:
            self.ensure_open()
            if self._pool is not None:
                return self._pool
            if self.connection_string is None:
                raise RuntimeError("No SQL Server connection string is configured.")
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="af-sql-server")
            try:
                self._pool = await aioodbc.create_pool(
                    dsn=self.connection_string.get_secret_value(),
                    minsize=1,
                    maxsize=1,
                    autocommit=False,
                    executor=executor,
                )
            except BaseException:
                await asyncio.to_thread(executor.shutdown, wait=True)
                raise
            self._executor = executor
            return self._pool

    @asynccontextmanager
    async def _operation(self, connection: aioodbc.Connection, *, managed: bool, write: bool) -> AsyncGenerator[None]:
        if managed:
            try:
                yield
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
            return
        if not write:
            yield
            return
        async with _cursor(connection) as cursor:
            await _execute(cursor, "SELECT @@TRANCOUNT")
            count = await cursor.fetchone()
            if count is None or type(count[0]) is not int:
                raise IntegrationInvalidResponseException("SQL Server did not return a transaction count.")
            started = count[0] == 0
            await _execute(cursor, "BEGIN TRANSACTION" if started else f"SAVE TRANSACTION {_SAVEPOINT}")
        try:
            yield
            if started:
                async with _cursor(connection) as cursor:
                    await _execute(cursor, "COMMIT TRANSACTION")
        except BaseException as exc:
            async with _cursor(connection) as cursor:
                if started:
                    await _execute(cursor, "ROLLBACK TRANSACTION")
                else:
                    await _execute(cursor, "SELECT XACT_STATE()")
                    state = await cursor.fetchone()
                    if state is None or state[0] != 1:
                        raise IntegrationException(
                            "The caller's SQL Server transaction cannot be rolled back to its savepoint; "
                            "the caller must roll back the transaction."
                        ) from exc
                    await _execute(cursor, f"ROLLBACK TRANSACTION {_SAVEPOINT}")
            raise

    @asynccontextmanager
    async def connection(self, *, write: bool = False) -> AsyncGenerator[aioodbc.Connection]:
        """Acquire one connection, keeping borrowed transactions under the caller's control."""
        self.ensure_open()
        try:
            if self.client is None:
                pool = await self._owned_pool()
                async with pool.acquire() as connection, self._operation(connection, managed=True, write=write):
                    yield connection
            elif isinstance(self.client, aioodbc.Pool):
                async with self.client.acquire() as connection:
                    self.ensure_open()
                    if cast(bool, connection.autocommit):  # pyright: ignore[reportUnknownMemberType]
                        raise ValueError("Borrowed aioodbc pools must use autocommit=False for atomic operations.")
                    async with self._operation(connection, managed=True, write=write):
                        yield connection
            else:
                async with self._borrowed_lock, self._operation(self.client, managed=False, write=write):
                    self.ensure_open()
                    yield self.client
        except pyodbc.Error as exc:
            raise IntegrationException("SQL Server operation failed; inspect the chained driver exception.") from exc

    async def close(self) -> None:
        """Close the owned pool and worker, never an injected client or pool."""
        async with self._init_lock:
            if self.closed:
                return
            if isinstance(self.client, aioodbc.Connection):
                async with self._borrowed_lock:
                    self.closed = True
                return
            self.closed = True
            try:
                if self._pool is not None:
                    self._pool.close()
                    await self._pool.wait_closed()
            finally:
                if self._executor is not None:
                    await asyncio.to_thread(self._executor.shutdown, wait=True)


def _create_client(
    connection_string: str | SecretString | None,
    *,
    client: SqlServerClient | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> _Client:
    if client is not None:
        if connection_string is not None or env_file_path is not None or env_file_encoding is not None:
            raise ValueError("client cannot be combined with connection_string, env_file_path, or env_file_encoding.")
        return _Client(None, client)
    settings = load_settings(
        SqlServerSettings,
        env_prefix="SQL_SERVER_",
        connection_string=connection_string,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    resolved = settings.get("connection_string")
    if resolved is not None and not isinstance(resolved, SecretString):
        raise TypeError("connection_string must be a string or SecretString.")
    return _Client(resolved, None)


class SqlServerCollection(
    BaseVectorCollection[KeyT, ModelT],
    BaseVectorSearch[KeyT, ModelT],
    Generic[KeyT, ModelT],
):
    """Store typed rows and perform exact searches on SQL Server native VECTOR columns.

    Tables are created in an existing schema and are never migrated. The owned
    single-connection pool is lazy; injected connections and pools remain caller-owned.
    """

    supported_key_types: ClassVar[set[str] | None] = {"str", "int", "UUID"}
    supported_vector_types: ClassVar[set[str] | None] = {"float", "float32"}
    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        connection_string: str | SecretString | None = None,
        client: SqlServerClient | None = None,
        schema: str = "dbo",
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        _shared_client: _Client | None = None,
    ) -> None:
        """Initialize a collection without connecting to the database.

        Args:
            record_type: Decorated/registered model type, or ``dict``.
            connection_string: Driver connection string for owned connections, or ``SQL_SERVER_CONNECTION_STRING``.
            client: An open caller-owned aioodbc connection or pool instead of a connection string.
            schema: Existing database schema containing the table.
            definition: Explicit field definition for dictionary records.
            collection_name: Table name overriding the model definition.
            embedding_generator: Default local embedding generator.
            env_file_path: Optional .env file; cannot be combined with an injected client.
            env_file_encoding: Encoding of the selected .env file.
            _shared_client: Internal shared client owned by a ``SqlServerStore``.
        """
        super().__init__(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator,
            managed_client=client is None and _shared_client is None,
        )
        self.schema = schema
        self._table = f"{_quote_identifier(schema)}.{_quote_identifier(self.collection_name)}"
        self._fields = tuple(
            replace(field, provider_annotations=field.provider_annotations) for field in self.definition.fields
        )
        for field in self._fields:
            _quote_identifier(field.storage_name or field.name)
            _column_type(field)
            if field.is_full_text_indexed:
                raise NotImplementedError("SQL Server full-text and keyword-hybrid search are not supported.")
            if any(name.startswith("sql_server.") for name in field.provider_annotations):
                raise NotImplementedError("SQL Server provider annotations are not supported.")
            if field.field_type == "vector":
                _metric_for(field)
                if field.index_kind not in ("default", "flat"):
                    raise NotImplementedError("SQL Server approximate vector indexes are not supported.")
            elif field.is_indexed and field.field_type == "data" and field.type_ in ("bytes", "list", "dict"):
                raise NotImplementedError(f"SQL Server cannot index data fields of type '{field.type_}'.")
        if _shared_client is not None:
            if (
                client is not None
                or connection_string is not None
                or env_file_path is not None
                or env_file_encoding is not None
            ):
                raise ValueError("A store's shared client cannot be combined with other connection settings.")
            self._client = _shared_client
        else:
            self._client = _create_client(
                connection_string, client=client, env_file_path=env_file_path, env_file_encoding=env_file_encoding
            )
        self._shared_client = _shared_client is not None

    async def __aenter__(self) -> Self:
        """Enter the collection context."""
        return self

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Release collection-owned resources."""
        await self.close()

    async def close(self) -> None:
        """Close only this collection's client, never a store's or the caller's connection."""
        if not self._shared_client:
            await self._client.close()

    def _column_names(self, include_vectors: bool) -> list[str]:
        return [
            field.storage_name or field.name
            for field in self._fields
            if include_vectors or field.field_type != "vector"
        ]

    def _column_definitions(self) -> str:
        definitions: list[str] = []
        for field in self._fields:
            column = _quote_identifier(field.storage_name or field.name)
            data_type = _column_type(field)
            if field.field_type == "key":
                generated = ""
                if field.is_auto_generated:
                    generated = {
                        "int": " IDENTITY(1,1)",
                        "UUID": " DEFAULT NEWID()",
                        "str": " DEFAULT CONVERT(NVARCHAR(36), NEWID())",
                    }[field.type_ or ""]
                definitions.append(f"{column} {data_type}{generated} NOT NULL PRIMARY KEY")
            else:
                definitions.append(f"{column} {data_type} NULL")
        return ", ".join(definitions)

    @staticmethod
    def _index_name(schema: str, table: str, column: str) -> str:
        digest = hashlib.sha256(f"{schema}\0{table}\0{column}".encode()).hexdigest()[:32]
        return f"af_sql_{digest}"

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create a table and requested scalar indexes, without modifying existing tables."""
        _validate_options(operation_options)
        self._client.ensure_open()
        statement = (
            "IF NOT EXISTS (SELECT 1 FROM sys.tables AS t "  # nosec B608
            "JOIN sys.schemas AS s ON s.schema_id = t.schema_id "
            "WHERE s.name = ? AND t.name = ?) "
            f"BEGIN CREATE TABLE {self._table} ({self._column_definitions()}) END"
        )

        async with self._client.connection(write=True) as connection, _cursor(connection) as cursor:
            await _execute(cursor, statement, [self.schema, self.collection_name])
            for field in self._fields:
                if field.field_type != "data" or not field.is_indexed:
                    continue
                name = field.storage_name or field.name
                index_name = self._index_name(self.schema, self.collection_name, name)
                index_statement = (
                    "IF NOT EXISTS (SELECT 1 FROM sys.indexes AS i "  # nosec B608
                    "JOIN sys.tables AS t ON t.object_id = i.object_id "
                    "JOIN sys.schemas AS s ON s.schema_id = t.schema_id "
                    "WHERE s.name = ? AND t.name = ? AND i.name = ?) "
                    f"CREATE INDEX {_quote_identifier(index_name)} ON {self._table} ({_quote_identifier(name)})"
                )
                await _execute(cursor, index_statement, [self.schema, self.collection_name, index_name])

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Return whether a base table exists in the configured schema."""
        _validate_options(operation_options)

        async with self._client.connection() as connection, _cursor(connection) as cursor:
            await _execute(
                cursor,
                "SELECT 1 FROM sys.tables AS t JOIN sys.schemas AS s ON s.schema_id = t.schema_id "
                "WHERE s.name = ? AND t.name = ?",
                [self.schema, self.collection_name],
            )
            return await cursor.fetchone() is not None

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Drop only the table in this schema; never drop the schema or other tables."""
        _validate_options(operation_options)
        async with self._client.connection(write=True) as connection, _cursor(connection) as cursor:
            await _execute(cursor, f"DROP TABLE IF EXISTS {self._table}")

    def _deserialize_store_models_to_dicts(
        self, records: Sequence[Any], *, context: Mapping[str, Any] | None = None
    ) -> Sequence[dict[str, Any]]:
        result = super()._deserialize_store_models_to_dicts(records, context=context)
        for record in result:
            for field in self._fields:
                name = field.storage_name or field.name
                if name in record:
                    record[name] = _parse_value(field, record[name])
        return result

    def _prepare_key(self, key: Any) -> Any:
        if key is None:
            raise ValueError("SQL Server keys cannot be null.")
        return _prepare_value(self.definition.key_field, key)

    def _parsed_key(self, key: Any) -> Any:
        return _parse_value(self.definition.key_field, key)

    async def _inner_upsert(
        self, records: Sequence[Any], *, operation_options: Mapping[str, Any] | None = None
    ) -> Sequence[KeyT]:
        _validate_options(operation_options)
        self._client.ensure_open()
        prepared: list[dict[str, Any]] = []
        for record in records:
            row: dict[str, Any] = {}
            for field in self._fields:
                name = field.storage_name or field.name
                if name not in record and field.field_type == "key" and field.is_auto_generated:
                    continue
                row[name] = (
                    self._prepare_key(record[name])
                    if field.field_type == "key"
                    else _prepare_value(field, record[name])
                )
            prepared.append(row)
        if not prepared:
            return []
        key_name = self.definition.key_field_storage_name
        key_column = _quote_identifier(key_name)

        async def upsert(cursor: _Cursor) -> list[KeyT]:
            keys: list[KeyT] = []
            for row in prepared:
                names = tuple(row)
                if key_name in row:
                    await _execute(
                        cursor,
                        f"SELECT {key_column} FROM {self._table} WITH (UPDLOCK, HOLDLOCK) WHERE {key_column} = ?",  # nosec B608
                        [row[key_name]],
                    )
                    if await cursor.fetchone() is not None:
                        updates = [name for name in names if name != key_name]
                        assignments = ", ".join(f"{_quote_identifier(name)} = ?" for name in updates)
                        if not assignments:
                            assignments = f"{key_column} = {key_column}"
                        parameters = [*(row[name] for name in updates), row[key_name]]
                        _check_parameter_count(parameters)
                        await _execute(
                            cursor,
                            f"UPDATE {self._table} SET {assignments} OUTPUT INSERTED.{key_column} "  # nosec B608
                            f"WHERE {key_column} = ?",
                            parameters,
                        )
                        result = await cursor.fetchone()
                        if result is None:
                            raise IntegrationInvalidResponseException("SQL Server did not return an updated key.")
                        keys.append(cast(KeyT, self._parsed_key(result[0])))
                        continue
                    if self.definition.key_field.is_auto_generated and self.definition.key_field.type_ == "int":
                        raise NotImplementedError(
                            "SQL Server IDENTITY columns cannot insert an explicit new key; omit it to generate a key."
                        )
                if names:
                    columns = ", ".join(_quote_identifier(name) for name in names)
                    markers = ", ".join("?" for _ in names)
                    statement = f"INSERT INTO {self._table} ({columns}) OUTPUT INSERTED.{key_column} VALUES ({markers})"  # nosec B608
                    parameters = [row[name] for name in names]
                    _check_parameter_count(parameters)
                    await _execute(cursor, statement, parameters)
                else:
                    await _execute(cursor, f"INSERT INTO {self._table} OUTPUT INSERTED.{key_column} DEFAULT VALUES")
                result = await cursor.fetchone()
                if result is None:
                    raise IntegrationInvalidResponseException("SQL Server did not return an inserted key.")
                keys.append(cast(KeyT, self._parsed_key(result[0])))
            return keys

        async with self._client.connection(write=True) as connection, _cursor(connection) as cursor:
            return await upsert(cursor)

    def _order_by(self, order_by: Mapping[str, bool] | None) -> str:
        parts: list[str] = []
        for name, ascending in (order_by or {}).items():
            if type(ascending) is not bool:
                raise TypeError("Order directions must be booleans.")
            field = _filter_field(self.definition, name)
            if field.type_ in ("list", "dict", "bytes"):
                raise NotImplementedError(f"SQL Server ordering is not supported for '{field.type_}'.")
            column = _quote_identifier(field.storage_name or field.name)
            parts.append(f"CASE WHEN {column} IS NULL THEN 1 ELSE 0 END")
            parts.append(f"{column} {'ASC' if ascending else 'DESC'}")
        if self.definition.key_field.name not in (order_by or {}):
            parts.append(f"{_quote_identifier(self.definition.key_field_storage_name)} ASC")
        return ", ".join(parts)

    async def _inner_get(
        self,
        *,
        keys: Sequence[KeyT] | None = None,
        filter: FilterExpression | None = None,
        top: int = 10,
        skip: int = 0,
        order_by: Mapping[str, bool] | None = None,
        include_vectors: bool = False,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[Any]:
        _validate_options(operation_options)
        self._client.ensure_open()
        columns = self._column_names(include_vectors)
        select = f"SELECT {', '.join(_quote_identifier(name) for name in columns)} FROM {self._table}"  # nosec B608
        if keys is not None:
            if order_by:
                raise ValueError("order_by applies only to filtered retrieval, not key lookup.")
            prepared_keys = [self._prepare_key(key) for key in keys]
            if not prepared_keys:
                return []

            async def get_keys(cursor: _Cursor) -> list[dict[str, Any]]:
                found: dict[Any, dict[str, Any]] = {}
                key_column = _quote_identifier(self.definition.key_field_storage_name)
                for offset in range(0, len(prepared_keys), _KEY_BATCH_SIZE):
                    batch = prepared_keys[offset : offset + _KEY_BATCH_SIZE]
                    markers = ", ".join("?" for _ in batch)
                    await _execute(cursor, f"{select} WHERE {key_column} IN ({markers})", batch)
                    for row in await _rows(cursor, len(columns)):
                        record = dict(zip(columns, row, strict=True))
                        found[self._parsed_key(record[self.definition.key_field_storage_name])] = record
                return [found[key] for raw in prepared_keys if (key := self._parsed_key(raw)) in found]

            async with self._client.connection() as connection, _cursor(connection) as cursor:
                return await get_keys(cursor)
        where, parameters = ("1 = 1", []) if filter is None else _FilterCompiler(self.definition).compile(filter)
        parameters.extend((skip, top))
        _check_parameter_count(parameters)
        statement = f"{select} WHERE {where} ORDER BY {self._order_by(order_by)} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"

        async with self._client.connection() as connection, _cursor(connection) as cursor:
            await _execute(cursor, statement, parameters)
            return [dict(zip(columns, row, strict=True)) for row in await _rows(cursor, len(columns))]

    async def _inner_delete(self, keys: Sequence[KeyT], *, operation_options: Mapping[str, Any] | None = None) -> None:
        _validate_options(operation_options)
        self._client.ensure_open()
        prepared = [self._prepare_key(key) for key in keys]
        if not prepared:
            return
        key_column = _quote_identifier(self.definition.key_field_storage_name)

        async with self._client.connection(write=True) as connection, _cursor(connection) as cursor:
            for offset in range(0, len(prepared), _KEY_BATCH_SIZE):
                batch = prepared[offset : offset + _KEY_BATCH_SIZE]
                markers = ", ".join("?" for _ in batch)
                await _execute(cursor, f"DELETE FROM {self._table} WHERE {key_column} IN ({markers})", batch)  # nosec B608

    async def _inner_search(
        self,
        *,
        search_type: SearchType,
        filter: FilterExpression | None = None,
        values: Any | None = None,
        vector: Vector | None = None,
        top: int = 3,
        skip: int = 0,
        include_vectors: bool = False,
        vector_property_name: str | None = None,
        additional_property_name: str | None = None,
        score_threshold: float | None = None,
        operation_options: Mapping[str, Any] | None = None,
    ) -> SearchResults[Any]:
        _validate_options(operation_options)
        if search_type != "vector" or additional_property_name is not None:
            raise NotImplementedError("SQL Server supports dense vector search only, not keyword-hybrid search.")
        if vector is None:
            raise NotImplementedError("SQL Server requires a vector or a local embedding generator.")
        self._client.ensure_open()
        resolved = self.definition.try_get_vector_field(vector_property_name)
        if resolved is None:
            raise ValueError("Select a vector_property_name from the collection definition.")
        field = next(item for item in self._fields if item.name == resolved.name)
        metric, result_kind = _metric_for(field)
        where, filter_params = (
            ("1 = 1", []) if filter is None else _FilterCompiler(self.definition, alias="t.").compile(filter)
        )
        column_names = self._column_names(include_vectors)
        projections = ", ".join(f"t.{_quote_identifier(name)}" for name in column_names)
        vector_column = f"t.{_quote_identifier(field.storage_name or field.name)}"
        key_column = f"t.{_quote_identifier(self.definition.key_field_storage_name)}"
        dimensions = field.dimensions
        statement = (
            f"SELECT {projections}, d.[distance] FROM {self._table} AS t "  # nosec B608
            f"CROSS APPLY (VALUES (VECTOR_DISTANCE('{metric}', CAST(? AS VECTOR({dimensions})), "
            f"{vector_column}))) AS d([distance]) "
            f"WHERE {vector_column} IS NOT NULL AND ({where}) AND d.[distance] IS NOT NULL"
        )
        parameters: list[Any] = [_prepare_value(field, vector), *filter_params]
        if score_threshold is not None:
            if type(score_threshold) not in (int, float):
                raise ValueError("score_threshold must be a finite number.")
            try:
                threshold = float(score_threshold)
            except OverflowError as exc:
                raise ValueError("score_threshold must be a finite number.") from exc
            if not math.isfinite(threshold):
                raise ValueError("score_threshold must be a finite number.")
            cutoff = (
                1 - threshold
                if result_kind == "similarity"
                else (-threshold if result_kind == "negative" else threshold)
            )
            statement += " AND d.[distance] <= ?"
            parameters.append(cutoff)
        statement += f" ORDER BY d.[distance] ASC, {key_column} ASC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        parameters.extend((skip, top))
        _check_parameter_count(parameters)

        async def search(cursor: _Cursor) -> list[dict[str, Any]]:
            await _execute(cursor, statement, parameters)
            results: list[dict[str, Any]] = []
            for row in await _rows(cursor, len(column_names) + 1):
                distance = row[-1]
                if type(distance) not in (float, int) or not math.isfinite(distance):
                    raise IntegrationInvalidResponseException("SQL Server returned a non-finite vector distance.")
                score = (
                    1 - distance
                    if result_kind == "similarity"
                    else -distance
                    if result_kind == "negative"
                    else distance
                )
                results.append({"record": dict(zip(column_names, row[:-1], strict=True)), "score": float(score)})
            return results

        async with self._client.connection() as connection, _cursor(connection) as cursor:
            rows = await search(cursor)
        return SearchResults(
            rows,
            metadata={"distance_function": field.distance_function or "DEFAULT", "approximate": False},
        )

    def _get_record_from_result(self, result: Any) -> Any:
        return result["record"]

    def _get_score_from_result(self, result: Any) -> float | None:
        return cast(float, result["score"])


class SqlServerStore(BaseVectorStore):
    """Create SQL Server collections sharing resolved settings or a caller-owned connection."""

    def __init__(
        self,
        *,
        connection_string: str | SecretString | None = None,
        client: SqlServerClient | None = None,
        schema: str = "dbo",
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a store without connecting to SQL Server.

        Args:
            connection_string: Driver connection string, or ``SQL_SERVER_CONNECTION_STRING``.
            client: An open caller-owned aioodbc connection or pool.
            schema: Existing database schema used by all collections.
            embedding_generator: Default local embedding generator.
            env_file_path: Optional .env file, incompatible with an injected client.
            env_file_encoding: Encoding of the selected .env file.
        """
        super().__init__(embedding_generator=embedding_generator, managed_client=client is None)
        _quote_identifier(schema)
        self.schema = schema
        self._client = _create_client(
            connection_string, client=client, env_file_path=env_file_path, env_file_encoding=env_file_encoding
        )

    def get_collection(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> SqlServerCollection[Any, ModelT]:
        """Create a collection borrowing this store's client and lifecycle."""
        return SqlServerCollection(
            record_type,
            schema=self.schema,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator if embedding_generator is not None else self.embedding_generator,
            _shared_client=self._client,
        )

    async def list_collection_names(self, *, operation_options: Mapping[str, Any] | None = None) -> Sequence[str]:
        """List base tables in the configured schema."""
        _validate_options(operation_options)

        async with self._client.connection() as connection, _cursor(connection) as cursor:
            await _execute(
                cursor,
                "SELECT t.name FROM sys.tables AS t JOIN sys.schemas AS s ON s.schema_id = t.schema_id "
                "WHERE s.name = ? ORDER BY t.name",
                [self.schema],
            )
            names = await _rows(cursor, 1)
            if any(not isinstance(row[0], str) for row in names):
                raise IntegrationInvalidResponseException("SQL Server returned a non-string table name.")
            return [cast(str, row[0]) for row in names]

    async def _inner_ensure_collection_deleted(
        self, collection_name: str, *, operation_options: Mapping[str, Any] | None = None
    ) -> None:
        _validate_options(operation_options)
        table = f"{_quote_identifier(self.schema)}.{_quote_identifier(collection_name)}"
        async with self._client.connection(write=True) as connection, _cursor(connection) as cursor:
            await _execute(cursor, f"DROP TABLE IF EXISTS {table}")

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Release store-owned resources."""
        await self.close()

    async def close(self) -> None:
        """Close the store wrapper without closing caller-owned connections."""
        await self._client.close()
