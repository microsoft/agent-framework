# Copyright (c) Microsoft. All rights reserved.

"""Persistent DuckDB collections with exact dense-vector search."""

from __future__ import annotations

import asyncio
import json
import math
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, ClassVar, Generic, cast
from uuid import UUID, uuid4

import duckdb
from agent_framework import (
    BaseVectorCollection,
    BaseVectorSearch,
    BaseVectorStore,
    Filter,
    FilterGroup,
    SearchResults,
    SecretString,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    load_settings,
)
from agent_framework._vector_filters import FilterExpression
from agent_framework._vectors import EmbeddingClient, SearchType, Vector
from agent_framework.exceptions import IntegrationException
from typing_extensions import TypedDict, TypeVar

KeyT = TypeVar("KeyT", default=Any)
ModelT = TypeVar("ModelT", default=Any)
ResultT = TypeVar("ResultT")

_DEFAULT_DATABASE = "agent-framework.duckdb"
_DATA_TYPES = {
    "str": "VARCHAR",
    "int": "BIGINT",
    "float": "DOUBLE",
    "bool": "BOOLEAN",
    "UUID": "UUID",
    "bytes": "BLOB",
    "date": "DATE",
    "datetime": "TIMESTAMPTZ",
    "list": "JSON",
    "dict": "JSON",
}
_VECTOR_TYPES = {"float": "DOUBLE", "float64": "DOUBLE", "float32": "FLOAT"}
_METRICS = {
    "DEFAULT": ("array_cosine_distance", False),
    "cosine_distance": ("array_cosine_distance", False),
    "cosine_similarity": ("array_cosine_similarity", True),
    "euclidean_distance": ("array_distance", False),
    "dot_prod": ("array_inner_product", True),
    "negative_dot_prod": ("-array_inner_product", False),
}
_ORDER_OPERATORS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
_ASCII_FOLD = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
_TABLE_SCOPE = (
    "FROM information_schema.tables "
    "WHERE table_catalog = current_database() AND table_schema = current_schema() "
    "AND table_type = 'BASE TABLE'"
)
_LIST_TABLES = f"SELECT table_name {_TABLE_SCOPE} ORDER BY table_name"
# DuckDB folds only ASCII identifier case; C collation avoids a connection's Unicode NOCASE setting.
_TABLE_EXISTS = (
    f"SELECT 1 {_TABLE_SCOPE} "
    "AND (translate(table_name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') COLLATE \"C\") = "
    "(translate(?, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') COLLATE \"C\")"
)


class DuckDBSettings(TypedDict, total=False):
    """Connection settings resolved from arguments, a selected .env file, or ``DUCKDB_`` variables."""

    connection_string: SecretString | None
    """Local database filename or DuckDB URI, resolved from ``DUCKDB_CONNECTION_STRING``."""


def _identifier(name: str) -> str:
    if not isinstance(name, str) or not name or "\0" in name:
        raise ValueError("DuckDB identifiers must be nonempty strings without NUL.")
    return '"' + name.replace('"', '""') + '"'


def _check_options(options: Mapping[str, Any] | None) -> None:
    if options:
        raise NotImplementedError(f"Unsupported DuckDB operation option(s): {', '.join(sorted(options))}.")


def _execute_statement(
    connection: duckdb.DuckDBPyConnection,
    statement: str,
    parameters: Sequence[Any] = (),
) -> None:
    connection.execute(statement, parameters)


def _column_type(field: VectorStoreField) -> str:
    if field.field_type == "vector":
        if type(field.dimensions) is not int or field.dimensions <= 0:
            raise ValueError(f"Vector field '{field.name}' needs positive integer dimensions.")
        if field.type_ not in _VECTOR_TYPES:
            raise NotImplementedError(f"Unsupported DuckDB vector type '{field.type_}'.")
        return f"{_VECTOR_TYPES[field.type_]}[{field.dimensions}]"
    if field.type_ not in _DATA_TYPES:
        raise NotImplementedError(f"Field '{field.name}' needs a supported explicit type; got '{field.type_}'.")
    return _DATA_TYPES[field.type_]


def _validate_json(value: Any) -> None:
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON values must contain finite numbers.")
        return
    if type(value) is list:
        for item in cast(list[Any], value):
            _validate_json(item)
        return
    if type(value) is dict:
        for key, item in cast(dict[Any, Any], value).items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings.")
            _validate_json(item)
        return
    raise TypeError("JSON fields require JSON-compatible lists or string-keyed dictionaries.")


def _prepare_vector(field: VectorStoreField, value: Any) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"Vector field '{field.name}' requires a dense numeric sequence.")
    elements = cast(Sequence[Any], value)
    if len(elements) != field.dimensions:
        raise ValueError(f"Vector field '{field.name}' expects {field.dimensions} dimensions; got {len(elements)}.")
    if any(type(item) not in (float, int) or not math.isfinite(item) for item in elements):
        raise ValueError(f"Vector field '{field.name}' requires finite numeric elements without NULLs.")
    if field.distance_function in (None, "DEFAULT", "cosine_distance", "cosine_similarity") and not any(elements):
        raise ValueError(f"Cosine vector field '{field.name}' requires a nonzero vector.")
    return [float(item) for item in elements]


def _prepare_value(field: VectorStoreField, value: Any) -> Any:
    if field.field_type == "vector":
        return _prepare_vector(field, value)
    if value is None:
        if field.field_type == "key":
            raise ValueError("DuckDB keys cannot be null.")
        return None
    kind = field.type_
    if kind == "str" and isinstance(value, str):
        return value
    if kind == "int" and type(value) is int:
        if not -(2**63) <= value < 2**63:
            raise ValueError(f"Field '{field.name}' exceeds the BIGINT range.")
        return value
    if kind == "float" and type(value) in (float, int):
        if not math.isfinite(value):
            raise ValueError(f"Field '{field.name}' requires a finite number.")
        return float(value)
    if kind == "bool" and type(value) is bool:
        return value
    if kind == "UUID" and isinstance(value, (str, UUID)):
        return UUID(str(value))
    if kind == "bytes" and isinstance(value, bytes):
        return value
    if kind == "date" and type(value) is date:
        return value
    if kind == "date" and isinstance(value, str):
        return date.fromisoformat(value)
    if kind == "datetime":
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if isinstance(parsed, datetime):
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError(f"Datetime field '{field.name}' requires a timezone.")
            return parsed
    if kind in ("list", "dict") and type(value) is (list if kind == "list" else dict):
        _validate_json(value)
        return json.dumps(value, allow_nan=False)
    raise TypeError(f"Field '{field.name}' requires a value of type '{kind}'.")


def _create_client(
    connection_string: str | SecretString | None,
    *,
    client: duckdb.DuckDBPyConnection | None,
    config: Mapping[str, str | SecretString] | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> _Client:
    if client is not None:
        if any(value is not None for value in (connection_string, config, env_file_path, env_file_encoding)):
            raise ValueError("client cannot be combined with connection_string, config, or .env options.")
        if not isinstance(client, duckdb.DuckDBPyConnection):
            raise TypeError("client must be a DuckDBPyConnection.")
        return _Client(None, client=client, config=None)
    settings = load_settings(
        DuckDBSettings,
        env_prefix="DUCKDB_",
        connection_string=connection_string,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    address = settings.get("connection_string")
    if address is not None and not isinstance(address, SecretString):
        raise TypeError("connection_string must be a string or SecretString.")
    if address is None:
        address = SecretString(_DEFAULT_DATABASE)
    if not address.get_secret_value().strip():
        raise ValueError("connection_string must not be empty.")
    if config is not None:
        if not isinstance(config, Mapping):
            raise TypeError("config must be a mapping of DuckDB settings.")
        for key, value in config.items():
            if not isinstance(key, str) or not key or not isinstance(value, (str, SecretString)):
                raise TypeError("DuckDB config keys and values must be nonempty string keys and string values.")
    return _Client(address, client=None, config=config)


class _Client:
    """Run every operation on one worker, including connection setup and shutdown."""

    def __init__(
        self,
        address: SecretString | None,
        *,
        client: duckdb.DuckDBPyConnection | None,
        config: Mapping[str, str | SecretString] | None,
    ) -> None:
        self.owned = client is None
        self._address = address
        self._connection = client
        self._config = {key: SecretString(value) for key, value in (config or {}).items()}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="af-duckdb")
        self._lifecycle_lock = threading.Lock()
        self._close_future: Future[None] | None = None

    def _execute(self, operation: Callable[[duckdb.DuckDBPyConnection], ResultT]) -> ResultT:
        connection = self._connection
        if connection is None:
            if self._address is None:
                raise RuntimeError("A DuckDB connection or database path is required.")
            try:
                connection = duckdb.connect(
                    database=self._address.get_secret_value(),
                    config={key: value.get_secret_value() for key, value in self._config.items()},
                )
            except duckdb.Error:
                connection = None
            if connection is None:
                raise IntegrationException("DuckDB connection failed. Verify the connection string and configuration.")
            self._connection = connection
        try:
            return operation(connection)
        except duckdb.Error as exc:
            raise IntegrationException("DuckDB operation failed; inspect the chained driver exception.") from exc

    async def run(self, operation: Callable[[duckdb.DuckDBPyConnection], ResultT]) -> ResultT:
        """Submit one complete database operation without blocking the event loop."""
        with self._lifecycle_lock:
            if self._close_future is not None:
                raise RuntimeError("The DuckDB client is closed.")
            future = self._executor.submit(self._execute, operation)
        return await asyncio.wrap_future(future)

    def _close(self) -> None:
        if self.owned and self._connection is not None:
            try:
                self._connection.close()
            except duckdb.Error as exc:
                raise IntegrationException("DuckDB close failed; inspect the chained driver exception.") from exc

    async def aclose(self) -> None:
        """Wait for queued work, close owned resources, and leave injected connections open."""
        with self._lifecycle_lock:
            if self._close_future is None:
                self._close_future = self._executor.submit(self._close)
                self._executor.shutdown(wait=False)
            close_future = self._close_future
        await asyncio.shield(asyncio.wrap_future(close_future))


class _FilterCompiler:
    """Compile supported portable filters into two-valued, parameterized SQL."""

    def __init__(self, definition: VectorStoreCollectionDefinition) -> None:
        self.definition = definition
        self.parameters: list[Any] = []

    def compile(self, expression: FilterExpression | None) -> tuple[str, list[Any]]:
        """Return a SQL predicate and its bound arguments."""
        if expression is None:
            return "TRUE", []
        return self._condition(expression), self.parameters

    def _equality(self, field: VectorStoreField, column: str, value: Any) -> str:
        if field.type_ in ("list", "dict"):
            raise NotImplementedError("DuckDB JSON equality and collection filters are not supported.")
        if value is None:
            return f"{column} IS NULL"
        if field.type_ in ("int", "float") and type(value) in (int, float):
            if not math.isfinite(value):
                raise ValueError("Numeric filter operands must be finite.")
            adapted = value
        else:
            try:
                adapted = _prepare_value(field, value)
            except TypeError:
                return "FALSE"
        self.parameters.append(adapted)
        return f"{column} IS NOT DISTINCT FROM ?"

    def _condition(self, expression: FilterExpression) -> str:
        if isinstance(expression, FilterGroup):
            parts = [self._condition(child) for child in expression.filters]
            if expression.operator == "not":
                return f"(NOT ({parts[0]}))"
            joiner = " AND " if expression.operator == "and" else " OR "
            return f"({joiner.join(parts)})"
        if not isinstance(expression, Filter):
            raise TypeError("filter must be a Filter or FilterGroup.")
        if "." in expression.field_name:
            raise NotImplementedError("DuckDB does not support nested filter paths.")
        field = self.definition.try_get_field(expression.field_name)
        if field is None:
            raise ValueError(f"Unknown DuckDB field '{expression.field_name}'.")
        if field.field_type == "vector":
            raise NotImplementedError("Filtering vector columns is not supported.")
        column = f"t.{_identifier(field.storage_name or field.name)}"
        op, value = expression.operator, expression.value
        if op == "exists":
            return "TRUE"
        if op == "is_null":
            return f"{column} IS NULL"
        if op == "is_not_null":
            return f"{column} IS NOT NULL"
        if op in ("eq", "ne"):
            equality = self._equality(field, column, value)
            return equality if op == "eq" else f"(NOT ({equality}))"
        if op in ("in", "not_in"):
            parts = [self._equality(field, column, item) for item in value]
            choices = f"({' OR '.join(parts)})" if parts else "FALSE"
            membership = choices if op == "in" else f"(NOT {choices})"
            return f"({column} IS NOT NULL AND {membership})"
        if op in (*_ORDER_OPERATORS, "between"):
            if field.type_ not in ("str", "int", "float", "date", "datetime"):
                raise NotImplementedError(f"Ordered filtering is not supported for '{field.type_}'.")
            operands: Sequence[Any] = value if op == "between" else [value]
            for operand in operands:
                if operand is None or type(operand) is bool:
                    raise TypeError("Ordered filter operands must be non-null scalars of the column's type.")
                if field.type_ in ("int", "float") and type(operand) in (int, float):
                    if not math.isfinite(operand):
                        raise ValueError("Ordered filter numbers must be finite.")
                    self.parameters.append(operand)
                else:
                    self.parameters.append(_prepare_value(field, operand))
            if op == "between":
                return f"({column} BETWEEN ? AND ?) IS TRUE"
            return f"({column} {_ORDER_OPERATORS[op]} ?) IS TRUE"
        if op in ("contains_text", "starts_with", "ends_with"):
            if field.type_ != "str":
                raise TypeError("Text filters require a string field.")
            if not isinstance(value, str):
                raise TypeError("Text filters require a string operand.")
            escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            pattern = ("%" if op != "starts_with" else "") + escaped + ("%" if op != "ends_with" else "")
            self.parameters.append(pattern)
            return f"({column} LIKE ? ESCAPE '!') IS TRUE"
        raise NotImplementedError(f"Unsupported DuckDB filter operator '{op}'.")


class DuckDBCollection(BaseVectorCollection[KeyT, ModelT], BaseVectorSearch[KeyT, ModelT], Generic[KeyT, ModelT]):
    """One DuckDB table with exact dense-vector search and typed record codecs."""

    supported_key_types: ClassVar[set[str] | None] = {"str", "int", "UUID"}
    supported_vector_types: ClassVar[set[str] | None] = set(_VECTOR_TYPES)
    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        connection_string: str | SecretString | None = None,
        client: duckdb.DuckDBPyConnection | None = None,
        config: Mapping[str, str | SecretString] | None = None,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        _shared_client: _Client | None = None,
    ) -> None:
        """Initialize a collection; the first async operation opens an owned connection.

        Args:
            record_type: Registered typed model or ``dict`` with an explicit definition.
            connection_string: Persistent filename or DuckDB URI. Defaults to ``agent-framework.duckdb``.
            client: Borrowed DuckDB connection; mutually exclusive with connection settings.
            config: DuckDB connection settings, optionally wrapping secret values in ``SecretString``.
            definition: Explicit definition for dictionary records.
            collection_name: Table name, overriding the model definition.
            embedding_generator: Local embedding client for generated vectors.
            env_file_path: Optional selected .env file for ``DUCKDB_CONNECTION_STRING``.
            env_file_encoding: Encoding of the selected .env file.
            _shared_client: Internal connection owned by a parent store.
        """
        super().__init__(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator,
            managed_client=client is None and _shared_client is None,
        )
        self._table = _identifier(self.collection_name)
        names = [field.storage_name or field.name for field in self.definition.fields]
        if len({name.translate(_ASCII_FOLD) for name in names}) != len(names):
            raise ValueError("DuckDB column names must be unique ignoring case.")
        self._fields = tuple(self.definition.fields)
        for name in names:
            _identifier(name)
        if _shared_client is not None and any(
            value is not None for value in (connection_string, client, config, env_file_path, env_file_encoding)
        ):
            raise ValueError("A store collection cannot override its shared connection settings.")
        self._client = _shared_client or _create_client(
            connection_string,
            client=client,
            config=config,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        self._owns_wrapper = _shared_client is None

    def _validate_data_model(self) -> None:
        super()._validate_data_model()
        for field in self.definition.fields:
            _column_type(field)
            if field.is_full_text_indexed or field.is_indexed:
                raise NotImplementedError("DuckDB full-text and explicit data indexes are not supported.")
            if field.field_type == "vector":
                if field.index_kind not in ("default", "flat"):
                    raise NotImplementedError(f"Unsupported DuckDB vector index kind '{field.index_kind}'.")
                if field.distance_function not in _METRICS:
                    raise NotImplementedError(f"Unsupported DuckDB distance function '{field.distance_function}'.")
            if any(name.startswith("duckdb.") for name in field.provider_annotations):
                raise NotImplementedError("DuckDB provider annotations are not supported.")
        key = self.definition.key_field
        if key.is_auto_generated and key.type_ == "int":
            raise NotImplementedError("DuckDB auto-generated integer keys are not supported.")

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Release a direct collection's connection; store collections leave ownership to the store."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close this collection's wrapper, leaving injected or store-owned connections open."""
        if self._owns_wrapper:
            await self._client.aclose()

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Check for this table in the active DuckDB database and schema."""
        _check_options(operation_options)
        return await self._client.run(
            lambda connection: connection.execute(_TABLE_EXISTS, [self.collection_name]).fetchone() is not None
        )

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create the table if absent; existing schemas are not modified."""
        _check_options(operation_options)
        columns = [
            f"{_identifier(field.storage_name or field.name)} {_column_type(field)}"
            + (" PRIMARY KEY" if field.field_type == "key" else "")
            for field in self._fields
        ]
        await self._client.run(
            lambda connection: _execute_statement(
                connection, f"CREATE TABLE IF NOT EXISTS {self._table} ({', '.join(columns)})"
            )
        )

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Drop this table if present, without affecting other tables."""
        _check_options(operation_options)
        await self._client.run(lambda connection: _execute_statement(connection, f"DROP TABLE IF EXISTS {self._table}"))

    def _deserialize_store_models_to_dicts(
        self,
        records: Sequence[Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[dict[str, Any]]:
        decoded = super()._deserialize_store_models_to_dicts(records, context=context)
        for record in decoded:
            for field in self._fields:
                name = field.storage_name or field.name
                value = record.get(name)
                if field.field_type == "vector" and isinstance(value, tuple):
                    record[name] = list(cast(tuple[Any, ...], value))
                elif field.type_ in ("list", "dict") and value is not None:
                    record[name] = json.loads(value)
        return decoded

    def _columns(self, include_vectors: bool) -> list[str]:
        return [
            field.storage_name or field.name
            for field in self._fields
            if include_vectors or field.field_type != "vector"
        ]

    def _order_by(self, order_by: Mapping[str, bool] | None) -> str:
        parts: list[str] = []
        for name, ascending in (order_by or {}).items():
            if type(ascending) is not bool:
                raise TypeError("Order directions must be booleans.")
            if "." in name:
                raise NotImplementedError("DuckDB does not support nested order paths.")
            field = self.definition.try_get_field(name)
            if field is None:
                raise ValueError(f"Unknown DuckDB order field '{name}'.")
            if field.field_type == "vector" or field.type_ in ("list", "dict"):
                raise NotImplementedError(f"Ordering field '{name}' is not supported.")
            direction = "ASC" if ascending else "DESC"
            parts.append(f"t.{_identifier(field.storage_name or field.name)} {direction} NULLS LAST")
        if self.definition.key_field.name not in (order_by or {}):
            parts.append(f"t.{_identifier(self.definition.key_field_storage_name)} ASC")
        return ", ".join(parts)

    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[KeyT]:
        _check_options(operation_options)
        key = self.definition.key_field
        key_name = self.definition.key_field_storage_name
        names = [field.storage_name or field.name for field in self._fields]
        rows: list[tuple[Any, ...]] = []
        keys: list[KeyT] = []
        for record in records:
            if key_name not in record:
                if not key.is_auto_generated:
                    raise ValueError(f"Record is missing vector store field '{key.name}'.")
                record = {**record, key_name: str(uuid4()) if key.type_ == "str" else uuid4()}
            row = tuple(_prepare_value(field, record[name]) for field, name in zip(self._fields, names, strict=True))
            rows.append(row)
            keys.append(cast(KeyT, row[names.index(key_name)]))
        if not rows:
            return []
        identifiers = ", ".join(map(_identifier, names))
        placeholders = ", ".join("?" for _ in names)
        updates = [name for name in names if name != key_name]
        conflict = (
            f"DO UPDATE SET {', '.join(f'{_identifier(name)} = EXCLUDED.{_identifier(name)}' for name in updates)}"  # nosec B608
            if updates
            else "DO NOTHING"
        )
        statement = (
            f"INSERT INTO {self._table} ({identifiers}) VALUES ({placeholders}) "  # ruff: ignore[hardcoded-sql-expression]  # nosec B608
            f"ON CONFLICT ({_identifier(key_name)}) {conflict}"
        )

        def write(connection: duckdb.DuckDBPyConnection) -> None:
            if self._client.owned:
                connection.execute("BEGIN TRANSACTION")
            try:
                connection.executemany(statement, rows)
                if self._client.owned:
                    connection.execute("COMMIT")
            except Exception:
                if self._client.owned:
                    connection.execute("ROLLBACK")
                raise

        await self._client.run(write)
        return keys

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
        _check_options(operation_options)
        columns = self._columns(include_vectors)
        selected = ", ".join(f"t.{_identifier(name)}" for name in columns)
        statement = f"SELECT {selected} FROM {self._table} AS t WHERE "  # ruff: ignore[hardcoded-sql-expression]  # nosec B608
        adapted: list[Any] = []
        if keys is not None:
            if order_by:
                raise ValueError("order_by applies only to filtered retrieval, not key lookup.")
            adapted = [_prepare_value(self.definition.key_field, key) for key in keys]
            if not adapted:
                return []
            placeholders = ", ".join("?" for _ in adapted)
            statement += f"t.{_identifier(self.definition.key_field_storage_name)} IN ({placeholders})"
            params: list[Any] = adapted
        else:
            predicate, params = _FilterCompiler(self.definition).compile(filter)
            statement += f"{predicate} ORDER BY {self._order_by(order_by)} LIMIT ? OFFSET ?"
            params.extend((top, skip))

        def read(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
            rows = connection.execute(statement, params).fetchall()
            return [dict(zip(columns, row, strict=True)) for row in rows]

        records = await self._client.run(read)
        if keys is not None:
            key_name = self.definition.key_field_storage_name
            by_key = {record[key_name]: record for record in records}
            return [by_key[key] for key in adapted if key in by_key]
        return records

    async def _inner_delete(self, keys: Sequence[KeyT], *, operation_options: Mapping[str, Any] | None = None) -> None:
        _check_options(operation_options)
        adapted = [_prepare_value(self.definition.key_field, key) for key in keys]
        if adapted:
            statement = (
                f"DELETE FROM {self._table} WHERE {_identifier(self.definition.key_field_storage_name)} "  # ruff: ignore[hardcoded-sql-expression]  # nosec B608
                f"IN ({', '.join('?' for _ in adapted)})"
            )
            await self._client.run(lambda connection: _execute_statement(connection, statement, adapted))

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
        _check_options(operation_options)
        if search_type != "vector" or additional_property_name is not None:
            raise NotImplementedError("DuckDB supports dense vector search only, not keyword-hybrid search.")
        if vector is None:
            raise NotImplementedError("DuckDB cannot vectorize values; supply a vector or embedding generator.")
        field = self.definition.try_get_vector_field(vector_property_name)
        if field is None:
            raise ValueError("Select a vector_property_name from the collection definition.")
        query_vector = _prepare_vector(field, vector)
        metric, descending = _METRICS[field.distance_function or "DEFAULT"]
        column = f"t.{_identifier(field.storage_name or field.name)}"
        distance = f"{metric}({column}, CAST(? AS {_column_type(field)}))"
        if metric in ("array_cosine_distance", "array_cosine_similarity"):
            distance = f"CASE WHEN array_inner_product({column}, {column}) = 0 THEN NULL ELSE {distance} END"
        predicate, filter_params = _FilterCompiler(self.definition).compile(filter)
        columns = self._columns(include_vectors)
        selected = ", ".join(f"t.{_identifier(name)}" for name in columns)
        comparison = ">=" if descending else "<="
        order = "DESC" if descending else "ASC"
        statement = (
            f"SELECT {selected}, scores.value FROM {self._table} AS t "  # ruff: ignore[hardcoded-sql-expression]  # nosec B608
            f"CROSS JOIN LATERAL (SELECT {distance} AS value) AS scores "
            f"WHERE {column} IS NOT NULL AND ({predicate}) AND isfinite(scores.value)"
        )
        parameters: list[Any] = [query_vector, *filter_params]
        if score_threshold is not None:
            if type(score_threshold) not in (float, int) or not math.isfinite(score_threshold):
                raise ValueError("score_threshold must be a finite number.")
            statement += f" AND scores.value {comparison} ?"
            parameters.append(score_threshold)
        statement += (
            f" ORDER BY scores.value {order}, t.{_identifier(self.definition.key_field_storage_name)} ASC "
            "LIMIT ? OFFSET ?"
        )
        parameters.extend((top, skip))

        def search(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
            rows = connection.execute(statement, parameters).fetchall()
            return [{"record": dict(zip(columns, row[:-1], strict=True)), "score": float(row[-1])} for row in rows]

        return SearchResults(
            await self._client.run(search),
            metadata={"distance_function": field.distance_function or "DEFAULT", "approximate": False},
        )

    def _get_record_from_result(self, result: Any) -> Any:
        return result["record"]

    def _get_score_from_result(self, result: Any) -> float | None:
        return float(result["score"])


class DuckDBStore(BaseVectorStore):
    """Create DuckDB collections sharing one serial, worker-owned connection."""

    def __init__(
        self,
        *,
        connection_string: str | SecretString | None = None,
        client: duckdb.DuckDBPyConnection | None = None,
        config: Mapping[str, str | SecretString] | None = None,
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a persistent local store or a DuckDB-client-supported service.

        Args:
            connection_string: On-disk filename or DuckDB URI; defaults to ``agent-framework.duckdb``.
            client: Borrowed DuckDB connection; cannot be combined with other connection settings.
            config: Additional DuckDB connection settings. Wrap credential values in ``SecretString``.
            embedding_generator: Default local embedding client for collections.
            env_file_path: Optional selected .env file for ``DUCKDB_CONNECTION_STRING``.
            env_file_encoding: Encoding of the selected .env file.
        """
        super().__init__(embedding_generator=embedding_generator, managed_client=client is None)
        self._client = _create_client(
            connection_string,
            client=client,
            config=config,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

    def get_collection(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> DuckDBCollection[Any, ModelT]:
        """Create a collection that borrows this store's connection and lifecycle."""
        return DuckDBCollection(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator if embedding_generator is not None else self.embedding_generator,
            _shared_client=self._client,
        )

    async def list_collection_names(self, *, operation_options: Mapping[str, Any] | None = None) -> Sequence[str]:
        """List base tables in the active database and schema."""
        _check_options(operation_options)
        return await self._client.run(
            lambda connection: [str(row[0]) for row in connection.execute(_LIST_TABLES).fetchall()]
        )

    async def collection_exists(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        """Check for a table using DuckDB's case-insensitive identifier semantics."""
        _check_options(operation_options)
        return await self._client.run(
            lambda connection: connection.execute(_TABLE_EXISTS, [collection_name]).fetchone() is not None
        )

    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        _check_options(operation_options)
        table = _identifier(collection_name)
        await self._client.run(lambda connection: _execute_statement(connection, f"DROP TABLE IF EXISTS {table}"))

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close owned connections and wait for the database file to be released."""
        await self.aclose()

    async def aclose(self) -> None:
        """Drain queued work and close only a connector-created connection."""
        await self._client.aclose()
