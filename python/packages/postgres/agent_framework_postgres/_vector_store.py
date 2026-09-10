# Copyright (c) Microsoft. All rights reserved.

"""Async PostgreSQL collection lifecycle, batch operations, and pgvector search."""

from __future__ import annotations

import hashlib
import math
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date, datetime
from itertools import groupby
from typing import Any, ClassVar, Generic, TypeAlias, cast
from uuid import UUID

from agent_framework import (
    BaseVectorCollection,
    BaseVectorSearch,
    BaseVectorStore,
    FilterGroup,
    SearchResults,
    SecretString,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    load_settings,
)
from agent_framework._vector_filters import FilterExpression
from agent_framework._vectors import EmbeddingClient, SearchType, Vector
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException
from pgvector import HalfVector
from pgvector import Vector as PgVector
from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection, Error, sql
from psycopg.rows import dict_row, tuple_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from typing_extensions import Self, TypedDict, TypeVar

KeyT = TypeVar("KeyT", default=Any)
ModelT = TypeVar("ModelT", default=Any)
PostgresClient: TypeAlias = AsyncConnection[Any] | AsyncConnectionPool[AsyncConnection[Any]]


class PostgresSettings(TypedDict, total=False):
    """Connection settings loaded by AF from explicit values, a selected .env file, or ``POSTGRES_`` variables."""

    connection_string: SecretString | None
    """Psycopg conninfo or URI, resolved from ``POSTGRES_CONNECTION_STRING`` and masked until passed to Psycopg."""


def _validate_operation_options(options: Mapping[str, Any] | None, allowed: set[str] | None = None) -> dict[str, Any]:
    result = dict(options or {})
    if unknown := result.keys() - (allowed or set()):
        raise NotImplementedError(f"Unsupported Postgres operation option(s): {', '.join(sorted(unknown))}.")
    return result


def _validate_integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")
    return value


class _Client:
    """Own a lazy pool or borrow a caller's pool/connection without closing it."""

    def __init__(self, connection_string: SecretString | None, client: PostgresClient | None) -> None:
        if (connection_string is None) == (client is None):
            raise ValueError("Supply exactly one of connection_string or client.")
        if client is not None and not isinstance(client, (AsyncConnection, AsyncConnectionPool)):
            raise TypeError("client must be a Psycopg AsyncConnection or AsyncConnectionPool.")
        self.owned = client is None
        self.client: PostgresClient
        if connection_string is not None:
            conninfo = connection_string.get_secret_value()
            if not conninfo.strip():
                raise ValueError("connection_string must not be empty.")
            self.client = AsyncConnectionPool(
                conninfo, open=False, min_size=1, max_size=10, kwargs={"autocommit": True}
            )
        elif client is not None:
            self.client = client
        self.closed = False

    def ensure_open(self) -> None:
        if self.closed:
            raise RuntimeError("The Postgres client is closed.")

    @asynccontextmanager
    async def connection(self, *, vectors: bool = False) -> AsyncGenerator[AsyncConnection[Any]]:
        self.ensure_open()
        try:
            if isinstance(self.client, AsyncConnectionPool):
                if self.owned:
                    await self.client.open()
                async with self.client.connection() as connection, connection.transaction():
                    if vectors and connection.adapters.types.get("vector") is None:
                        await register_vector_async(connection)
                    yield connection
            else:
                # A transaction on a borrowed connection becomes a savepoint when already in a transaction.
                async with self.client.transaction():
                    if vectors and self.client.adapters.types.get("vector") is None:
                        await register_vector_async(self.client)
                    yield self.client
        except Error as exc:
            raise IntegrationException("PostgreSQL operation failed; inspect the chained driver exception.") from exc

    async def close(self) -> None:
        if not self.closed:
            if self.owned:
                await self.client.close()
            self.closed = True


def _create_client(
    connection_string: str | SecretString | None,
    *,
    client: PostgresClient | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> _Client:
    if client is not None:
        if connection_string is not None or env_file_path is not None or env_file_encoding is not None:
            raise ValueError("client cannot be combined with connection_string, env_file_path, or env_file_encoding.")
        return _Client(None, client)
    settings = load_settings(
        PostgresSettings,
        env_prefix="POSTGRES_",
        connection_string=connection_string,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    resolved_connection_string = settings.get("connection_string")
    if resolved_connection_string is not None and not isinstance(resolved_connection_string, SecretString):
        raise TypeError("connection_string must be a string or SecretString.")
    return _Client(resolved_connection_string, None)


_TYPES = {
    "str": sql.SQL('text COLLATE "C"'),
    "int": sql.SQL("bigint"),
    "float": sql.SQL("double precision"),
    "bool": sql.SQL("boolean"),
    "UUID": sql.SQL("uuid"),
    "bytes": sql.SQL("bytea"),
    "date": sql.SQL("date"),
    "datetime": sql.SQL("timestamp with time zone"),
    "list": sql.SQL("jsonb"),
    "dict": sql.SQL("jsonb"),
}
_METRICS = {
    "DEFAULT": (sql.SQL("<=>"), "cosine"),
    "cosine_distance": (sql.SQL("<=>"), "cosine"),
    "cosine_similarity": (sql.SQL("<=>"), "cosine"),
    "dot_prod": (sql.SQL("<#>"), "ip"),
    "negative_dot_prod": (sql.SQL("<#>"), "ip"),
    "euclidean_distance": (sql.SQL("<->"), "l2"),
    "manhattan": (sql.SQL("<+>"), "l1"),
}
_ORDER_OPERATORS = {"gt": sql.SQL(">"), "gte": sql.SQL(">="), "lt": sql.SQL("<"), "lte": sql.SQL("<=")}


def _prepare_identifier(name: str) -> sql.Identifier:
    """Quote a single identifier, rejecting truncation and NUL."""
    if not isinstance(name, str) or not name or "\0" in name or len(name.encode("utf-8")) > 63:
        raise ValueError("Postgres identifiers must contain 1-63 UTF-8 bytes and no NUL.")
    return sql.Identifier(name)


def _prepare_vector_type(field: VectorStoreField) -> str:
    value = field.provider_annotations.get("postgres.vector_type", "halfvec" if field.type_ == "float16" else "vector")
    if value not in ("vector", "halfvec"):
        raise NotImplementedError("postgres.vector_type supports only 'vector' and 'halfvec'.")
    return cast(str, value)


def _prepare_metric(field: VectorStoreField) -> tuple[sql.SQL, str]:
    try:
        return _METRICS[field.distance_function or "DEFAULT"]
    except KeyError:
        raise NotImplementedError(f"Unsupported Postgres distance function '{field.distance_function}'.") from None


def _prepare_column_type(field: VectorStoreField) -> sql.Composable:
    if field.field_type == "vector":
        storage = _prepare_vector_type(field)
        return sql.SQL("{}({})").format(_prepare_identifier(storage), sql.Literal(field.dimensions))
    if field.type_ not in _TYPES:
        raise NotImplementedError(f"Field '{field.name}' needs a supported explicit type; got '{field.type_}'.")
    return _TYPES[field.type_]


def _prepare_value(field: VectorStoreField, value: Any) -> Any:
    """Adapt normalized records without silently coercing bools, strings or binary vectors."""
    if value is None:
        return None
    if field.field_type == "vector":
        if isinstance(value, (str, bytes, bytearray)):
            raise TypeError(f"Vector field '{field.name}' requires a dense numeric vector, not text or bytes.")
        if isinstance(value, list):
            value = cast(list[float | int], value)
        elif isinstance(value, Sequence):
            value = list(cast(Sequence[float | int], value))
        return HalfVector(value) if _prepare_vector_type(field) == "halfvec" else PgVector(value)
    kind = field.type_
    if kind == "UUID":
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            return UUID(value)
    elif kind == "date":
        if type(value) is date:
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
    elif kind == "datetime":
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if isinstance(parsed, datetime):
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError(f"Datetime field '{field.name}' requires a timezone.")
            return parsed
    elif kind == "float" and type(value) in (int, float):
        if not math.isfinite(value):
            raise ValueError(f"Field '{field.name}' requires a finite number.")
        return float(value)
    elif kind == "int" and type(value) is int:
        if not -(2**63) <= value < 2**63:
            raise ValueError(f"Field '{field.name}' exceeds the PostgreSQL bigint range.")
        return value
    elif (
        (kind == "str" and isinstance(value, str))
        or (kind == "bool" and type(value) is bool)
        or (kind == "bytes" and isinstance(value, bytes))
    ):
        return value
    elif (kind == "list" and isinstance(value, list)) or (kind == "dict" and isinstance(value, dict)):
        return Jsonb(value)
    raise TypeError(f"Field '{field.name}' requires a value of type '{kind}'.")


def _validate_json_filter(value: Any) -> None:
    # JSON encoding must not turn tuples into lists or non-string keys into strings.
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON filter numbers must be finite.")
        return
    if isinstance(value, list):
        for item in cast(list[Any], value):
            _validate_json_filter(item)
        return
    if isinstance(value, dict):
        for key, item in cast(dict[Any, Any], value).items():
            if not isinstance(key, str):
                raise TypeError("JSON filter object keys must be strings.")
            _validate_json_filter(item)
        return
    raise TypeError("JSON filters support only JSON scalars, lists, and string-keyed dictionaries.")


def _prepare_filter_field(definition: VectorStoreCollectionDefinition, name: str) -> VectorStoreField:
    # Core supports paths structurally, but this connector exposes only declared columns.
    if "." in name:
        raise NotImplementedError("Postgres filters and ordering do not support nested field paths.")
    field = definition.try_get_field(name)
    if field is None:
        raise ValueError(f"Unknown Postgres field '{name}'.")
    if field.field_type == "vector":
        raise NotImplementedError("Filtering and ordering vector columns is not supported.")
    return field


class _FilterCompiler:
    """Translate a core-validated snapshot into total-boolean, parameterized SQL."""

    def __init__(self, definition: VectorStoreCollectionDefinition) -> None:
        self.definition = definition
        self._parameters: list[Any] = []

    def compile(self, expression: FilterExpression) -> tuple[sql.Composable, list[Any]]:
        """Return SQL and its parameters in placeholder order for one expression."""
        self._parameters = []
        condition = self._prepare_filter_condition(expression)
        return condition, self._parameters

    def _prepare_parameter(self, value: Any) -> sql.Placeholder:
        self._parameters.append(value)
        return sql.Placeholder()

    def _prepare_equality(self, field: VectorStoreField, column: sql.Composable, value: Any) -> sql.Composable:
        if value is None:
            return sql.SQL("{} IS NULL").format(column)
        kind = field.type_
        if (kind == "bool" and type(value) is not bool) or (kind != "bool" and isinstance(value, bool)):
            return sql.SQL("FALSE")
        if kind in ("int", "float") and type(value) in (int, float):
            if not math.isfinite(value):
                raise ValueError("Numeric filter values must be finite.")
            adapted = value
        else:
            # Do not let Postgres coerce, e.g., string '1' into an integer or boolean.
            expected_types = {"str": str, "int": int, "float": float, "bytes": bytes, "list": list, "dict": dict}
            expected = expected_types.get(kind or "")
            if expected is not None and not isinstance(value, expected):
                return sql.SQL("FALSE")
            if kind in ("list", "dict"):
                _validate_json_filter(value)
            adapted = _prepare_value(field, value)
        return sql.SQL("{} IS NOT DISTINCT FROM {}").format(column, self._prepare_parameter(adapted))

    def _prepare_filter_group(self, expression: FilterGroup) -> sql.Composable:
        parts = [self._prepare_filter_condition(child) for child in expression.filters]
        if expression.operator == "not":
            return sql.SQL("(NOT ({}))").format(parts[0])
        joiner = sql.SQL(" AND ") if expression.operator == "and" else sql.SQL(" OR ")
        return sql.SQL("({})").format(joiner.join(parts))

    def _prepare_filter_condition(self, expression: FilterExpression) -> sql.Composable:
        if isinstance(expression, FilterGroup):
            return self._prepare_filter_group(expression)
        field = _prepare_filter_field(self.definition, expression.field_name)
        column: sql.Composable = _prepare_identifier(field.storage_name or field.name)
        if field.type_ == "str":
            column = sql.SQL('{} COLLATE "C"').format(column)
        op, value = expression.operator, expression.value
        if op == "exists":
            # Declared SQL columns are present in every row, even when their value is NULL.
            return sql.SQL("TRUE")
        if op == "is_null":
            return sql.SQL("{} IS NULL").format(column)
        if op == "is_not_null":
            return sql.SQL("{} IS NOT NULL").format(column)
        if op in ("eq", "ne"):
            equality = self._prepare_equality(field, column, value)
            return equality if op == "eq" else sql.SQL("(NOT ({}))").format(equality)
        if op in ("in", "not_in"):
            parts = [self._prepare_equality(field, column, item) for item in value]
            choices = sql.SQL(" OR ").join(parts) if parts else sql.SQL("FALSE")
            membership = sql.SQL("({})").format(choices)
            if op == "not_in":
                membership = sql.SQL("(NOT {})").format(membership)
            # Portable membership, unlike eq/ne, never matches a null field.
            return sql.SQL("({} IS NOT NULL AND {})").format(column, membership)
        if op in _ORDER_OPERATORS or op == "between":
            if field.type_ in ("list", "dict", "bool", "bytes"):
                raise NotImplementedError(f"Ordered filtering is not supported for '{field.type_}'.")
            operands: Sequence[Any] = value if op == "between" else [value]
            if any(item is None or isinstance(item, bool) for item in operands):
                raise TypeError("Ordered filter operands must be non-null scalars of the column's type.")
            if any(isinstance(item, float) and not math.isfinite(item) for item in operands):
                raise ValueError("Ordered filter numbers must be finite.")
            params = [
                self._prepare_parameter(
                    item
                    if field.type_ in ("int", "float") and type(item) in (int, float)
                    else _prepare_value(field, item)
                )
                for item in operands
            ]
            comparison = (
                sql.SQL("{} BETWEEN {} AND {}").format(column, *params)
                if op == "between"
                else sql.SQL("{} {} {}").format(column, _ORDER_OPERATORS[op], params[0])
            )
            return sql.SQL("({}) IS TRUE").format(comparison)
        if op in ("contains_text", "starts_with", "ends_with"):
            if field.type_ != "str":
                raise TypeError(f"Text filtering requires a string column, not '{field.type_}'.")
            if not isinstance(value, str):
                raise TypeError("Text filtering requires a string operand.")
            # Use ! as the explicit escape character; % and _ remain literal input.
            escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            pattern = ("%" if op != "starts_with" else "") + escaped + ("%" if op != "ends_with" else "")
            return sql.SQL("({} LIKE {} ESCAPE '!') IS TRUE").format(column, self._prepare_parameter(pattern))
        if op in ("contains", "contains_any", "contains_all"):
            if field.type_ != "list":
                raise TypeError("Collection membership requires a list column.")
            operands = [value] if op == "contains" else value
            for operand in operands:
                _validate_json_filter(operand)
            parts = [
                sql.SQL("EXISTS (SELECT 1 FROM jsonb_array_elements({}) AS item(value) WHERE item.value = {})").format(
                    column, self._prepare_parameter(Jsonb(item))
                )
                for item in operands
            ]
            joiner = sql.SQL(" AND ") if op == "contains_all" else sql.SQL(" OR ")
            combined = joiner.join(parts) if parts else sql.SQL("TRUE" if op == "contains_all" else "FALSE")
            return sql.SQL("({} IS NOT NULL AND ({}))").format(column, combined)
        raise NotImplementedError(f"Unsupported Postgres filter operator '{op}'.")


class PostgresCollection(
    BaseVectorCollection[KeyT, ModelT],
    BaseVectorSearch[KeyT, ModelT],
    Generic[KeyT, ModelT],
):
    """Store typed rows and search dense vectors using PostgreSQL and pgvector.

    The schema and pgvector extension must already exist. The connector never
    enables extensions, creates schemas, or migrates existing tables. See the
    package README for metric units, index limits, and ANN recall limitations.
    Batch writes are transactional; an enclosing caller transaction retains
    control over commit. Injected connections and pools remain caller-owned.
    """

    supported_key_types: ClassVar[set[str] | None] = {"str", "int", "UUID"}
    supported_vector_types: ClassVar[set[str] | None] = {"float", "float16", "float32"}
    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        connection_string: str | SecretString | None = None,
        client: PostgresClient | None = None,
        schema: str = "public",
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a collection without connecting to PostgreSQL.

        Args:
            record_type: Decorated/registered model type, or ``dict``.
            connection_string: Psycopg conninfo or URI for an owned lazy pool. Falls back to
                ``POSTGRES_CONNECTION_STRING`` in the selected .env file or process environment.
            client: An open caller-owned async connection or pool, instead of conninfo.
            schema: Existing PostgreSQL schema containing the table.
            definition: Explicit field definition for dictionary records.
            collection_name: Table name, overriding the model's collection name.
            embedding_generator: Default local embedding client.
            env_file_path: Optional .env file to read; cannot be combined with an injected client.
            env_file_encoding: Encoding of the .env file; cannot be combined with an injected client.
        """
        super().__init__(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator,
            managed_client=client is None,
        )
        self.schema = schema
        self._table = sql.SQL("{}.{}").format(_prepare_identifier(schema), _prepare_identifier(self.collection_name))
        # Snapshot connector annotations: mutating a model must not change SQL halfway through an operation.
        self._fields = tuple(
            replace(field, provider_annotations=field.provider_annotations) for field in self.definition.fields
        )
        for field in self._fields:
            _prepare_identifier(field.storage_name or field.name)
            _prepare_column_type(field)
            if field.is_full_text_indexed:
                raise NotImplementedError("Postgres full-text indexes and keyword-hybrid search are not supported.")
            if field.field_type == "vector":
                self._validate_vector_field(field)
            elif any(name.startswith("postgres.") for name in field.provider_annotations):
                raise NotImplementedError("Postgres provider annotations are supported only on vector fields.")
        self._client = _create_client(
            connection_string, client=client, env_file_path=env_file_path, env_file_encoding=env_file_encoding
        )
        self._shared_client = False

    @staticmethod
    def _validate_vector_field(field: VectorStoreField) -> None:
        _validate_integer(field.dimensions, "dimensions", 1, 16000)
        _, ops = _prepare_metric(field)
        if field.index_kind not in ("default", "flat", "hnsw", "ivf_flat"):
            raise NotImplementedError(f"Unsupported Postgres index kind '{field.index_kind}'.")
        annotations = field.provider_annotations
        allowed = {"postgres.vector_type"}
        if field.index_kind == "hnsw":
            allowed.update(("postgres.m", "postgres.ef_construction"))
            m = _validate_integer(annotations.get("postgres.m", 16), "postgres.m", 2, 100)
            _validate_integer(annotations.get("postgres.ef_construction", 64), "postgres.ef_construction", 2 * m, 1000)
        if field.index_kind == "ivf_flat":
            allowed.add("postgres.lists")
            _validate_integer(annotations.get("postgres.lists", 100), "postgres.lists", 1, 32768)
            if ops == "l1":
                raise NotImplementedError("IVFFlat does not support Manhattan distance.")
        if unknown := {name for name in annotations if name.startswith("postgres.")} - allowed:
            raise NotImplementedError(f"Unsupported Postgres provider annotation(s): {', '.join(sorted(unknown))}.")
        if field.index_kind in ("hnsw", "ivf_flat"):
            limit = 4000 if _prepare_vector_type(field) == "halfvec" else 2000
            _validate_integer(field.dimensions, "indexed vector dimensions", 1, limit)

    async def __aenter__(self) -> Self:
        """Enter the client context; connections open on the first operation."""
        return self

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close resources owned by this collection."""
        await self.close()

    async def close(self) -> None:
        """Close an owned pool, never a borrowed client or a store's shared pool."""
        if not self._shared_client:
            await self._client.close()

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create a table and requested indexes, without altering an existing schema.

        ``operation_options={"create_indexes": False}`` explicitly creates only
        the table. Use this before loading IVFFlat training data, then call this
        method again with the default options to create the requested indexes.
        IVFFlat creation on an empty table is rejected.
        """
        options = _validate_operation_options(operation_options, {"create_indexes"})
        self._client.ensure_open()
        create_indexes = options.get("create_indexes", True)
        if not isinstance(create_indexes, bool):
            raise TypeError("create_indexes must be a boolean.")
        columns: list[sql.Composable] = []
        for field in self._fields:
            suffix = sql.SQL("")
            if field.field_type == "key":
                suffix = sql.SQL(" PRIMARY KEY")
                if field.is_auto_generated:
                    suffix = {
                        "int": sql.SQL(" GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"),
                        "UUID": sql.SQL(" DEFAULT pg_catalog.gen_random_uuid() PRIMARY KEY"),
                        "str": sql.SQL(" DEFAULT pg_catalog.gen_random_uuid()::text PRIMARY KEY"),
                    }[field.type_ or ""]
            columns.append(
                sql.SQL("{} {}{}").format(
                    _prepare_identifier(field.storage_name or field.name), _prepare_column_type(field), suffix
                )
            )
        async with self._client.connection(vectors=bool(self.definition.vector_fields)) as connection:
            await connection.execute(
                sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(self._table, sql.SQL(", ").join(columns))
            )
            if create_indexes:
                for field in self._fields:
                    if field.field_type == "vector" and field.index_kind in ("hnsw", "ivf_flat"):
                        if field.index_kind == "ivf_flat":
                            cursor = await connection.execute(
                                sql.SQL("SELECT 1 FROM {} WHERE {} IS NOT NULL LIMIT 1").format(
                                    self._table, _prepare_identifier(field.storage_name or field.name)
                                )
                            )
                            if await cursor.fetchone() is None:
                                raise ValueError(
                                    "IVFFlat requires training data. Create with create_indexes=False, "
                                    "upsert vectors, then call ensure_collection_exists() again."
                                )
                        await connection.execute(self._prepare_index(field))
                    elif field.field_type == "data" and field.is_indexed:
                        await connection.execute(self._prepare_index(field))

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Return whether the table exists in the configured schema."""
        _validate_operation_options(operation_options)
        async with self._client.connection() as connection:
            cursor = await connection.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s AND table_type = 'BASE TABLE'",
                (self.schema, self.collection_name),
            )
            return await cursor.fetchone() is not None

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Drop only this table, without CASCADE or schema/extension cleanup."""
        _validate_operation_options(operation_options)
        async with self._client.connection() as connection:
            await connection.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(self._table))

    def _deserialize_store_models_to_dicts(
        self,
        records: Sequence[Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[dict[str, Any]]:
        result = super()._deserialize_store_models_to_dicts(records, context=context)
        for record in result:
            for field in self._fields:
                name = field.storage_name or field.name
                if field.field_type == "vector" and record.get(name) is not None:
                    record[name] = record[name].to_list()
        return result

    def _prepare_filter(self, filter: FilterExpression | None) -> tuple[sql.Composable, list[Any]]:
        if filter is None:
            return sql.SQL("TRUE"), []
        return _FilterCompiler(self.definition).compile(filter)

    def _prepare_order_by(self, order_by: Mapping[str, bool] | None) -> sql.Composable:
        parts: list[sql.Composable] = []
        for name, ascending in (order_by or {}).items():
            if not isinstance(ascending, bool):
                raise TypeError("Order directions must be booleans.")
            field = _prepare_filter_field(self.definition, name)
            if field.type_ in ("list", "dict"):
                raise NotImplementedError("Ordering JSON columns is not supported.")
            parts.append(
                sql.SQL("{} {} NULLS LAST").format(
                    _prepare_identifier(field.storage_name or field.name),
                    sql.SQL("ASC") if ascending else sql.SQL("DESC"),
                )
            )
        if self.definition.key_field.name not in (order_by or {}):
            parts.append(sql.SQL("{} ASC").format(_prepare_identifier(self.definition.key_field_storage_name)))
        return sql.SQL(", ").join(parts)

    def _prepare_index(self, field: VectorStoreField) -> sql.Composed:
        storage_name = field.storage_name or field.name
        digest = hashlib.sha256(f"{self.schema}\0{self.collection_name}\0{storage_name}".encode()).hexdigest()[:32]
        name = _prepare_identifier(f"af_vector_{digest}")
        column = _prepare_identifier(storage_name)
        if field.field_type != "vector":
            return sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} ({})").format(name, self._table, column)
        kind = sql.SQL("hnsw") if field.index_kind == "hnsw" else sql.SQL("ivfflat")
        _, ops = _prepare_metric(field)
        opclass = _prepare_identifier(f"{_prepare_vector_type(field)}_{ops}_ops")
        annotations = field.provider_annotations
        options = (
            sql.SQL("m = {}, ef_construction = {}").format(
                sql.Literal(annotations.get("postgres.m", 16)),
                sql.Literal(annotations.get("postgres.ef_construction", 64)),
            )
            if field.index_kind == "hnsw"
            else sql.SQL("lists = {}").format(sql.Literal(annotations.get("postgres.lists", 100)))
        )
        return sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING {} ({} {}) WITH ({})").format(
            name, self._table, kind, column, opclass, options
        )

    def _prepare_columns(self, include_vectors: bool) -> list[str]:
        return [
            field.storage_name or field.name
            for field in self._fields
            if include_vectors or field.field_type != "vector"
        ]

    def _prepare_key(self, value: Any) -> Any:
        if value is None:
            raise ValueError("Postgres keys cannot be null.")
        return _prepare_value(self.definition.key_field, value)

    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[KeyT]:
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        key_name = self.definition.key_field_storage_name
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
        keys: list[KeyT] = []
        async with (
            self._client.connection(vectors=bool(self.definition.vector_fields)) as connection,
            connection.cursor(row_factory=tuple_row) as cursor,
        ):
            # Group adjacent row shapes only, preserving both input order and repeated-key semantics.
            for names, group in groupby(prepared, key=tuple):
                rows = list(group)
                if names:
                    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                        self._table,
                        sql.SQL(", ").join(map(_prepare_identifier, names)),
                        sql.SQL(", ").join(sql.Placeholder() for _ in names),
                    )
                else:
                    statement = sql.SQL("INSERT INTO {} DEFAULT VALUES").format(self._table)
                if key_name in names:
                    updates = [name for name in names if name != key_name] or [key_name]
                    statement += sql.SQL(" ON CONFLICT ({}) DO UPDATE SET {}").format(
                        _prepare_identifier(key_name),
                        sql.SQL(", ").join(
                            sql.SQL("{} = EXCLUDED.{}").format(_prepare_identifier(name), _prepare_identifier(name))
                            for name in updates
                        ),
                    )
                statement += sql.SQL(" RETURNING {}").format(_prepare_identifier(key_name))
                await cursor.executemany(
                    statement, [tuple(row[name] for name in names) for row in rows], returning=True
                )
                for index in range(len(rows)):
                    result = await cursor.fetchone()
                    if result is None:
                        raise IntegrationInvalidResponseException("PostgreSQL did not return an upserted key.")
                    keys.append(cast(KeyT, result[0]))
                    if index < len(rows) - 1 and not cursor.nextset():
                        raise IntegrationInvalidResponseException("PostgreSQL returned too few upsert result sets.")
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
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        columns = self._prepare_columns(include_vectors)
        adapted: list[Any] = []
        statement = sql.SQL("SELECT {} FROM {} WHERE ").format(
            sql.SQL(", ").join(map(_prepare_identifier, columns)), self._table
        )
        if keys is not None:
            if order_by:
                raise ValueError("order_by applies only to filtered retrieval, not key lookup.")
            if not keys:
                return []
            adapted = [self._prepare_key(key) for key in keys]
            statement += sql.SQL("{} = ANY(%s)").format(_prepare_identifier(self.definition.key_field_storage_name))
            params: list[Any] = [adapted]
        else:
            where, filter_params = self._prepare_filter(filter)
            statement += where
            statement += sql.SQL(" ORDER BY {} LIMIT %s OFFSET %s").format(self._prepare_order_by(order_by))
            params = [*filter_params, top, skip]
        async with (
            self._client.connection(vectors=include_vectors and bool(self.definition.vector_fields)) as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(statement, params)
            rows = await cursor.fetchall()
        if keys is not None:
            by_key = {row[self.definition.key_field_storage_name]: row for row in rows}
            return [by_key[key] for key in adapted if key in by_key]
        return rows

    async def _inner_delete(self, keys: Sequence[KeyT], *, operation_options: Mapping[str, Any] | None = None) -> None:
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        adapted = [self._prepare_key(key) for key in keys]
        if not adapted:
            return
        async with self._client.connection() as connection:
            await connection.execute(
                sql.SQL("DELETE FROM {} WHERE {} = ANY(%s)").format(
                    self._table, _prepare_identifier(self.definition.key_field_storage_name)
                ),
                [adapted],
            )

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
        options = _validate_operation_options(operation_options, {"exact", "hnsw_ef_search", "ivfflat_probes"})
        if search_type != "vector" or additional_property_name is not None:
            raise NotImplementedError("Postgres supports dense vector search only, not keyword-hybrid search.")
        if vector is None:
            raise NotImplementedError(
                "Postgres has no server-side vectorization; supply a vector or embedding generator."
            )
        self._client.ensure_open()
        resolved = self.definition.try_get_vector_field(vector_property_name)
        if resolved is None:
            raise ValueError("Select a vector_property_name from the collection definition.")
        field = next(field for field in self._fields if field.name == resolved.name)
        exact = options.get("exact", field.index_kind in ("flat", "default"))
        if not isinstance(exact, bool):
            raise TypeError("exact must be a boolean.")
        if not exact and field.index_kind not in ("hnsw", "ivf_flat"):
            raise ValueError("Approximate search requires an HNSW or IVFFlat vector field.")
        settings: list[tuple[str, str]] = []
        if "hnsw_ef_search" in options:
            if exact or field.index_kind != "hnsw":
                raise ValueError("hnsw_ef_search requires an HNSW approximate search.")
            settings.append((
                "hnsw.ef_search",
                str(_validate_integer(options["hnsw_ef_search"], "hnsw_ef_search", 1, 1000)),
            ))
        if "ivfflat_probes" in options:
            if exact or field.index_kind != "ivf_flat":
                raise ValueError("ivfflat_probes requires an IVFFlat approximate search.")
            settings.append((
                "ivfflat.probes",
                str(_validate_integer(options["ivfflat_probes"], "ivfflat_probes", 1, 32768)),
            ))
        if not exact:
            settings.append(("hnsw.iterative_scan", "strict_order"))
            settings.append(("ivfflat.iterative_scan", "off"))
        query_vector = _prepare_value(field, vector)
        operator, _ = _prepare_metric(field)
        distance = sql.SQL("{} {} %s").format(_prepare_identifier(field.storage_name or field.name), operator)
        score = distance
        if field.distance_function == "cosine_similarity":
            score = sql.SQL("1 - ({})").format(distance)
        elif field.distance_function == "dot_prod":
            score = sql.SQL("-({})").format(distance)
        where, filter_params = self._prepare_filter(filter)
        columns = self._prepare_columns(include_vectors)
        statement = sql.SQL("SELECT {}, {} FROM {} WHERE ({}) AND ({}) < 'Infinity'::double precision").format(
            sql.SQL(", ").join(map(_prepare_identifier, columns)), score, self._table, where, distance
        )
        params = [query_vector, *filter_params, query_vector]
        if score_threshold is not None:
            if type(score_threshold) not in (int, float) or not math.isfinite(score_threshold):
                raise ValueError("score_threshold must be a finite number.")
            cutoff = score_threshold
            if field.distance_function == "cosine_similarity":
                cutoff = 1 - cutoff
            elif field.distance_function == "dot_prod":
                cutoff = -cutoff
            statement += sql.SQL(" AND ({}) <= %s").format(distance)
            params.extend((query_vector, cutoff))
        # Adding zero explicitly prevents ANN ordering for exact queries without disabling data indexes.
        ranking = sql.SQL("({}) + 0").format(distance) if exact else distance
        statement += sql.SQL(" ORDER BY {} ASC LIMIT %s OFFSET %s").format(ranking)
        params.extend((query_vector, top, skip))
        async with (
            self._client.connection(vectors=True) as connection,
            # Rolling back this read-only savepoint also restores settings inside a caller's outer transaction.
            connection.transaction(force_rollback=True),
        ):
            for setting, value in settings:
                await connection.execute("SELECT set_config(%s, %s, true)", (setting, value))
            async with connection.cursor(row_factory=tuple_row) as cursor:
                await cursor.execute(statement, params)
                rows = await cursor.fetchall()
        return SearchResults(
            [{"record": dict(zip(columns, row[:-1], strict=True)), "score": row[-1]} for row in rows],
            metadata={"distance_function": field.distance_function or "DEFAULT", "approximate": not exact},
        )

    def _get_record_from_result(self, result: Any) -> Any:
        return result["record"]

    def _get_score_from_result(self, result: Any) -> float | None:
        return float(result["score"])


class PostgresStore(BaseVectorStore):
    """Create collection clients sharing a PostgreSQL pool or connection."""

    def __init__(
        self,
        *,
        connection_string: str | SecretString | None = None,
        client: PostgresClient | None = None,
        schema: str = "public",
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a store without connecting to PostgreSQL.

        Args:
            connection_string: Psycopg conninfo or URI for an owned lazy pool. Falls back to
                ``POSTGRES_CONNECTION_STRING`` in the selected .env file or process environment.
            client: An open caller-owned async connection or pool.
            schema: Existing schema used by all collection clients.
            embedding_generator: Default embedding generator for collections.
            env_file_path: Optional .env file to read; cannot be combined with an injected client.
            env_file_encoding: Encoding of the .env file; cannot be combined with an injected client.
        """
        super().__init__(embedding_generator=embedding_generator, managed_client=client is None)
        _prepare_identifier(schema)
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
    ) -> PostgresCollection[Any, ModelT]:
        """Create a collection borrowing this store's client and lifecycle."""
        collection = PostgresCollection(
            record_type,
            client=self._client.client,
            schema=self.schema,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator if embedding_generator is not None else self.embedding_generator,
        )
        collection._client = self._client  # pyright: ignore[reportPrivateUsage]
        collection._shared_client = True  # pyright: ignore[reportPrivateUsage]
        return collection

    async def list_collection_names(self, *, operation_options: Mapping[str, Any] | None = None) -> Sequence[str]:
        """List base tables in this store's schema, including externally created tables."""
        _validate_operation_options(operation_options)
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name",
                [self.schema],
            )
            return [row[0] for row in await cursor.fetchall()]

    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        table = sql.SQL("{}.{}").format(_prepare_identifier(self.schema), _prepare_identifier(collection_name))
        async with self._client.connection() as connection:
            await connection.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(table))

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Release the store's owned pool."""
        await self.close()

    async def close(self) -> None:
        """Close the store and its owned resources; injected clients remain open."""
        await self._client.close()
