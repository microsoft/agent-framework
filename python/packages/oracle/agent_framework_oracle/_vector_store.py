# Copyright (c) Microsoft. All rights reserved.

"""Oracle Database 23ai vector collections and stores."""

from __future__ import annotations

import asyncio
import math
from array import array
from collections.abc import AsyncGenerator, Collection, Mapping, Sequence
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, ClassVar, Generic, Protocol, TypeAlias, cast
from uuid import UUID

import oracledb
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
from typing_extensions import Self, TypedDict, TypeVar

KeyT = TypeVar("KeyT", default=Any)
ModelT = TypeVar("ModelT", default=Any)
OracleClient: TypeAlias = oracledb.AsyncConnection | oracledb.AsyncConnectionPool


class _OracleCursor(Protocol):
    """Typed boundary for python-oracledb's partially annotated async cursor."""

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None: ...
    async def execute(self, statement: str, parameters: Mapping[str, Any] | None = None) -> None: ...
    async def executemany(self, statement: str, parameters: Sequence[Mapping[str, Any]]) -> None: ...
    async def fetchone(self) -> Sequence[Any] | None: ...
    async def fetchall(self) -> list[Sequence[Any]]: ...
    def setinputsizes(self, **kwargs: Any) -> Any: ...


_MAX_IDENTIFIER_BYTES = 128
_MAX_KEY_BYTES = 512
_MAX_TEXT_BYTES = 4000
_BATCH_SIZE = 500
_METRICS = {
    "DEFAULT": "COSINE",
    "cosine_distance": "COSINE",
    "cosine_similarity": "COSINE",
    "euclidean_distance": "EUCLIDEAN",
    "euclidean_squared_distance": "EUCLIDEAN_SQUARED",
    "manhattan": "MANHATTAN",
    "negative_dot_prod": "DOT",
    "dot_prod": "DOT",
}
_ORDER_OPERATORS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


class OracleSettings(TypedDict, total=False):
    """Connection settings resolved from arguments, a selected .env file, or ``ORACLE_`` variables."""

    dsn: str | None
    user: str | None
    password: SecretString | None


def _quote_identifier(name: str) -> str:
    if not isinstance(name, str) or not name or "\0" in name:
        raise ValueError("Oracle identifiers must be nonempty strings without NUL.")
    try:
        length = len(name.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("Oracle identifiers must be valid UTF-8.") from exc
    if length > _MAX_IDENTIFIER_BYTES:
        raise ValueError("Oracle identifiers cannot exceed 128 UTF-8 bytes.")
    return '"' + name.replace('"', '""') + '"'


def _validate_operation_options(options: Mapping[str, Any] | None) -> None:
    if options:
        raise NotImplementedError("Oracle does not support operation_options.")


def _validate_scalar(field: VectorStoreField, value: Any) -> Any:
    if value is None:
        if field.field_type == "key":
            raise ValueError("Oracle keys cannot be null.")
        return None
    kind = field.type_
    if kind == "UUID":
        if not isinstance(value, UUID | str):
            raise TypeError(f"Field '{field.name}' requires a UUID.")
        return str(UUID(str(value)))
    if kind == "str":
        if not isinstance(value, str):
            raise TypeError(f"Field '{field.name}' requires a string.")
        if not value:
            raise ValueError("Oracle cannot store an empty string distinctly from NULL.")
        limit = _MAX_KEY_BYTES if field.field_type == "key" else _MAX_TEXT_BYTES
        if len(value.encode("utf-8")) > limit:
            raise ValueError(f"Field '{field.name}' exceeds {limit} UTF-8 bytes.")
        return value
    if kind == "int":
        if type(value) is not int:
            raise TypeError(f"Field '{field.name}' requires an integer.")
        if not -(2**63) <= value < 2**63:
            raise ValueError(f"Field '{field.name}' exceeds the signed 64-bit integer range.")
        return value
    if kind == "float":
        if type(value) not in (int, float):
            raise TypeError(f"Field '{field.name}' requires a number.")
        try:
            number = float(value)
        except OverflowError as exc:
            raise ValueError(f"Field '{field.name}' requires a finite number.") from exc
        if not math.isfinite(number):
            raise ValueError(f"Field '{field.name}' requires a finite number.")
        return number
    if kind == "bool":
        if type(value) is not bool:
            raise TypeError(f"Field '{field.name}' requires a boolean.")
        return int(value)
    raise NotImplementedError(f"Oracle field type '{kind}' is not supported.")


def _prepare_vector(field: VectorStoreField, value: Any) -> array[Any] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        tolist = getattr(value, "tolist", None)
        value = tolist() if callable(tolist) else value
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"Oracle vector '{field.name}' requires a dense numeric sequence.")
    elements = cast(Sequence[Any], value)
    if len(elements) != field.dimensions:
        raise ValueError(f"Oracle vector '{field.name}' expects {field.dimensions} dimensions; got {len(elements)}.")
    element_type = field.type_ or "float32"
    if element_type == "int8":
        if any(type(item) is not int or not -128 <= item <= 127 for item in elements):
            raise ValueError(f"Oracle vector '{field.name}' requires signed int8 elements.")
        return array("b", elements)
    result: list[float] = []
    for item in elements:
        if type(item) not in (int, float):
            raise TypeError(f"Oracle vector '{field.name}' requires numeric elements, not booleans.")
        try:
            number = float(item)
        except OverflowError as exc:
            raise ValueError(f"Oracle vector '{field.name}' requires finite elements.") from exc
        if not math.isfinite(number):
            raise ValueError(f"Oracle vector '{field.name}' requires finite elements.")
        result.append(number)
    try:
        prepared = array("d" if element_type == "float64" else "f", result)
    except OverflowError as exc:
        raise ValueError(f"Oracle vector '{field.name}' contains out-of-range elements.") from exc
    if not all(math.isfinite(item) for item in prepared):
        raise ValueError(f"Oracle vector '{field.name}' contains out-of-range elements.")
    return prepared


def _column_type(field: VectorStoreField) -> str:
    if field.field_type == "vector":
        dimensions = field.dimensions
        if type(dimensions) is not int or not 1 <= dimensions <= 65535:
            raise ValueError("Oracle vector dimensions must be an integer between 1 and 65535.")
        storage_type = {
            None: "FLOAT32",
            "float": "FLOAT32",
            "float32": "FLOAT32",
            "float64": "FLOAT64",
            "int8": "INT8",
        }[field.type_]
        return f"VECTOR({dimensions}, {storage_type})"
    if field.type_ is None:
        raise ValueError(f"Oracle field '{field.name}' requires an explicit type.")
    if field.field_type == "key":
        return {"str": "VARCHAR2(512 BYTE)", "UUID": "VARCHAR2(36 BYTE)", "int": "NUMBER(19,0)"}[field.type_]
    return {"str": "VARCHAR2(4000 BYTE)", "int": "NUMBER(19,0)", "float": "BINARY_DOUBLE", "bool": "NUMBER(1,0)"}[
        field.type_
    ]


def _bind_type(field: VectorStoreField) -> Any:
    if field.field_type == "vector":
        return cast(Any, oracledb.DB_TYPE_VECTOR)  # pyright: ignore[reportUnknownMemberType]
    if field.type_ in ("str", "UUID"):
        return (
            _MAX_KEY_BYTES
            if field.field_type == "key" and field.type_ == "str"
            else (36 if field.type_ == "UUID" else _MAX_TEXT_BYTES)
        )
    if field.type_ == "float":
        return cast(Any, oracledb.DB_TYPE_BINARY_DOUBLE)  # pyright: ignore[reportUnknownMemberType]
    return cast(Any, oracledb.DB_TYPE_NUMBER)  # pyright: ignore[reportUnknownMemberType]


def _oracle_error_code(exc: oracledb.DatabaseError) -> int | None:
    error = exc.args[0] if exc.args else None
    code = getattr(error, "code", None)
    return code if isinstance(code, int) else None


class _Client:
    """Own a lazy async pool or borrow an async pool/connection."""

    def __init__(
        self,
        *,
        dsn: str | None = None,
        user: str | None = None,
        password: SecretString | None = None,
        client: OracleClient | None = None,
    ) -> None:
        if client is not None:
            if not isinstance(client, (oracledb.AsyncConnection, oracledb.AsyncConnectionPool)):
                raise TypeError("client must be an oracledb AsyncConnection or AsyncConnectionPool.")
            if any(value is not None for value in (dsn, user, password)):
                raise ValueError("An Oracle client cannot be combined with connection settings.")
        else:
            if not isinstance(dsn, str) or not dsn.strip():
                raise ValueError("A nonempty Oracle DSN is required.")
            if not isinstance(user, str) or not user.strip():
                raise ValueError("A nonempty Oracle user is required.")
            if not isinstance(password, SecretString) or not password.get_secret_value():
                raise ValueError("A nonempty Oracle password is required.")
        self._client = client
        self._dsn = dsn
        self._user = user
        self._password = password
        self._pool: oracledb.AsyncConnectionPool | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    def ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("The Oracle client is closed.")

    async def _get_client(self) -> OracleClient:
        self.ensure_open()
        if self._client is not None:
            return self._client
        async with self._lock:
            self.ensure_open()
            if self._pool is None:
                if self._user is None or self._dsn is None or self._password is None:
                    raise RuntimeError("Oracle connection settings are missing.")
                self._pool = oracledb.create_pool_async(
                    user=self._user, password=self._password.get_secret_value(), dsn=self._dsn, min=0, max=4
                )
            return self._pool

    @asynccontextmanager
    async def connection(self, *, write: bool = False) -> AsyncGenerator[oracledb.AsyncConnection]:
        """Commit or roll back pooled writes; a borrowed connection remains caller-transactional."""
        try:
            client = await self._get_client()
            if isinstance(client, oracledb.AsyncConnectionPool):
                async with client.acquire() as connection:  # pyright: ignore[reportUnknownMemberType]
                    try:
                        yield connection
                        if write:
                            await connection.commit()
                    except (Exception, asyncio.CancelledError):
                        if write:
                            await connection.rollback()
                        raise
            else:
                yield client
        except oracledb.Error as exc:
            raise IntegrationException("Oracle operation failed; inspect the chained driver exception.") from exc

    async def close(self) -> None:
        """Close only a connector-created pool; a borrowed client remains open."""
        async with self._lock:
            if not self._closed:
                if self._pool is not None:
                    await self._pool.close()
                self._closed = True


def _create_client(
    *,
    dsn: str | None,
    user: str | None,
    password: str | SecretString | None,
    client: OracleClient | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> _Client:
    if client is not None:
        if any(value is not None for value in (dsn, user, password, env_file_path, env_file_encoding)):
            raise ValueError("client cannot be combined with dsn, user, password, or .env settings.")
        return _Client(client=client)
    settings = load_settings(
        OracleSettings,
        env_prefix="ORACLE_",
        dsn=dsn,
        user=user,
        password=password,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    return _Client(dsn=settings.get("dsn"), user=settings.get("user"), password=settings.get("password"))


def _scalar_field(definition: VectorStoreCollectionDefinition, name: str) -> VectorStoreField:
    if "." in name:
        raise NotImplementedError("Oracle filters do not support nested field paths.")
    field = definition.try_get_field(name)
    if field is None:
        raise ValueError(f"Unknown Oracle field '{name}'.")
    if field.field_type == "vector":
        raise NotImplementedError("Oracle cannot filter or order vector columns.")
    return field


class _FilterCompiler:
    """Compile core-validated scalar filters to two-valued, bound Oracle SQL."""

    def __init__(self, definition: VectorStoreCollectionDefinition) -> None:
        self.definition = definition
        self.binds: dict[str, Any] = {}

    def compile(self, expression: FilterExpression) -> tuple[str, dict[str, Any]]:
        """Compile an expression and its bind values without retaining caller state."""
        self.binds = {}
        return self._condition(expression), self.binds

    def _bind(self, value: Any) -> str:
        name = f"f{len(self.binds)}"
        self.binds[name] = value
        return f":{name}"

    def _equality(self, field: VectorStoreField, value: Any) -> str:
        column = _quote_identifier(field.storage_name or field.name)
        if value is None:
            return f"{column} IS NULL"
        kind = field.type_
        if kind in ("int", "float") and (type(value) in (int, float) or isinstance(value, Decimal)):
            if type(value) is float and not math.isfinite(value):
                raise ValueError("Numeric filter values must be finite.")
            if isinstance(value, Decimal) and not value.is_finite():
                raise ValueError("Numeric filter values must be finite.")
            if kind == "int":
                if not -(2**63) <= value < 2**63 or value != int(value):
                    return "1=0"
                adapted = int(value)
            else:
                try:
                    adapted = float(value)
                except OverflowError:
                    return "1=0"
                if not math.isfinite(adapted):
                    return "1=0"
                if isinstance(value, Decimal) and Decimal.from_float(adapted) != value:
                    return "1=0"
                if type(value) is int:
                    numerator, denominator = adapted.as_integer_ratio()
                    if numerator != value * denominator:
                        return "1=0"
        elif kind == "UUID":
            if not isinstance(value, UUID | str):
                return "1=0"
            try:
                adapted = _validate_scalar(field, value)
            except ValueError:
                return "1=0"
        elif (
            (kind == "bool" and type(value) is not bool)
            or (kind != "bool" and isinstance(value, bool))
            or (kind == "str" and not isinstance(value, str))
            or (kind in ("int", "float") and type(value) not in (int, float, Decimal))
        ):
            return "1=0"
        else:
            adapted = _validate_scalar(field, value)
        return f"({column} IS NOT NULL AND {column} = {self._bind(adapted)})"

    def _condition(self, expression: FilterExpression) -> str:
        if isinstance(expression, FilterGroup):
            parts = [self._condition(child) for child in expression.filters]
            if expression.operator == "not":
                return f"(NOT ({parts[0]}))"
            joiner = " AND " if expression.operator == "and" else " OR "
            return f"({joiner.join(parts)})"
        field = _scalar_field(self.definition, expression.field_name)
        column = _quote_identifier(field.storage_name or field.name)
        op, value = expression.operator, expression.value
        if op == "exists":
            return "1=1"
        if op == "is_null":
            return f"{column} IS NULL"
        if op == "is_not_null":
            return f"{column} IS NOT NULL"
        if op in ("eq", "ne"):
            equality = self._equality(field, value)
            return equality if op == "eq" else f"(NOT ({equality}))"
        if op in ("in", "not_in"):
            parts = [self._equality(field, item) for item in cast(Collection[Any], value)]
            membership = f"({' OR '.join(parts)})" if parts else "1=0"
            if op == "not_in":
                membership = f"(NOT ({membership}))"
            return f"({column} IS NOT NULL AND {membership})"
        if op in _ORDER_OPERATORS or op == "between":
            if field.type_ not in ("int", "float"):
                raise NotImplementedError("Oracle ordered filters support only numeric fields.")
            operands = cast(Sequence[Any], value) if op == "between" else [value]
            adapted: list[Any] = []
            for item in operands:
                if item is None or isinstance(item, bool) or type(item) not in (int, float):
                    raise TypeError("Ordered filter operands must be non-null numbers, not booleans.")
                if type(item) is float and not math.isfinite(item):
                    raise ValueError("Ordered filter numbers must be finite.")
                if field.type_ == "int" and type(item) is float and not item.is_integer():
                    raise NotImplementedError("Oracle integer range filters require integer operands.")
                adapted.append(_validate_scalar(field, int(item) if field.type_ == "int" else item))
            comparison = (
                f"{column} BETWEEN {self._bind(adapted[0])} AND {self._bind(adapted[1])}"
                if op == "between"
                else f"{column} {_ORDER_OPERATORS[op]} {self._bind(adapted[0])}"
            )
            return f"({column} IS NOT NULL AND {comparison})"
        if op in ("starts_with", "ends_with", "contains_text"):
            if field.type_ != "str":
                raise TypeError("Oracle text filtering requires a string column.")
            if not isinstance(value, str):
                raise TypeError("Oracle text filtering requires a string operand.")
            escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            pattern = ("%" if op != "starts_with" else "") + escaped + ("%" if op != "ends_with" else "")
            return f"({column} IS NOT NULL AND {column} LIKE {self._bind(pattern)} ESCAPE '!')"
        raise NotImplementedError(f"Unsupported Oracle filter operator '{op}'.")


class OracleCollection(
    BaseVectorCollection[KeyT, ModelT],
    BaseVectorSearch[KeyT, ModelT],
    Generic[KeyT, ModelT],
):
    """Store typed records and search Oracle Database 23ai native VECTOR columns."""

    supported_key_types: ClassVar[set[str] | None] = {"str", "int", "UUID"}
    supported_vector_types: ClassVar[set[str] | None] = {"float", "float32", "float64", "int8"}
    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        dsn: str | None = None,
        user: str | None = None,
        password: str | SecretString | None = None,
        client: OracleClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        _shared_client: _Client | None = None,
    ) -> None:
        """Initialize a collection with explicit, selected .env, or environment credentials.

        Args:
            record_type: Registered application model, or dict with an explicit definition.
            definition: Explicit dictionary model definition.
            collection_name: Override for the model's table name in the current Oracle schema.
            embedding_generator: Optional local embedding generator.
            dsn: Oracle connect string; defaults to ``ORACLE_DSN``.
            user: Oracle database user; defaults to ``ORACLE_USER``.
            password: Database password or AF SecretString; defaults to ``ORACLE_PASSWORD``.
            client: Borrowed async connection or pool in place of connection settings.
            env_file_path: Optional selected .env file; no implicit discovery.
            env_file_encoding: Encoding of the selected .env file.
        """
        if _shared_client is not None and any(
            item is not None for item in (dsn, user, password, client, env_file_path, env_file_encoding)
        ):
            raise ValueError("Shared Oracle clients cannot be combined with connection settings.")
        super().__init__(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator,
            managed_client=_shared_client is None and client is None,
        )
        self._table = _quote_identifier(self.collection_name)
        self._fields = tuple(self.definition.fields)
        self._client = _shared_client or _create_client(
            dsn=dsn,
            user=user,
            password=password,
            client=client,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        self._shared_client = _shared_client is not None

    def _validate_data_model(self) -> None:
        super()._validate_data_model()
        if not self.definition.vector_fields:
            raise ValueError("Oracle collections require a vector field.")
        for field in self.definition.fields:
            _quote_identifier(field.storage_name or field.name)
            if field.provider_annotations:
                raise NotImplementedError("Oracle provider annotations are not supported.")
            if field.is_full_text_indexed or field.is_indexed:
                raise NotImplementedError("Oracle data and full-text indexes are not supported.")
            if field.is_auto_generated:
                raise NotImplementedError("Oracle requires application-provided keys.")
            if field.field_type == "vector":
                if field.index_kind not in ("default", "flat"):
                    raise NotImplementedError(f"Oracle index kind '{field.index_kind}' is not supported.")
                if field.distance_function not in _METRICS:
                    raise NotImplementedError(f"Oracle distance function '{field.distance_function}' is not supported.")
            elif field.field_type == "key" and field.type_ not in ("str", "int", "UUID"):
                raise NotImplementedError(f"Oracle key type '{field.type_}' is not supported.")
            elif field.field_type == "data" and field.type_ not in ("str", "int", "float", "bool"):
                raise NotImplementedError(f"Oracle data type '{field.type_}' is not supported.")
            _column_type(field)

    async def __aenter__(self) -> Self:
        """Enter the collection context without connecting until first use."""
        return self

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close only a collection-owned pool."""
        await self.close()

    async def close(self) -> None:
        """Release this collection's resources, not a borrowed or store-shared client."""
        if not self._shared_client:
            await self._client.close()

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Check whether the table exists in the current user's schema."""
        _validate_operation_options(operation_options)
        async with self._client.connection() as connection, cast(_OracleCursor, connection.cursor()) as cursor:
            await cursor.execute("SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :name", {"name": self.collection_name})
            return await cursor.fetchone() is not None

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create this table if absent; do not migrate existing tables or create indexes."""
        _validate_operation_options(operation_options)
        columns: list[str] = []
        for field in self._fields:
            column = f"{_quote_identifier(field.storage_name or field.name)} {_column_type(field)}"
            columns.append(column + (" PRIMARY KEY" if field.field_type == "key" else ""))
        async with self._client.connection() as connection, cast(_OracleCursor, connection.cursor()) as cursor:
            await cursor.execute("SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :name", {"name": self.collection_name})
            if await cursor.fetchone() is not None:
                return
            try:
                await cursor.execute(f"CREATE TABLE {self._table} ({', '.join(columns)})")
            except oracledb.DatabaseError as exc:
                if _oracle_error_code(exc) != 955:
                    raise
                await cursor.execute(
                    "SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :name", {"name": self.collection_name}
                )
                if await cursor.fetchone() is None:
                    raise

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Drop only this table, without modifying other database objects."""
        _validate_operation_options(operation_options)
        if await self.collection_exists():
            await _drop_table(self._client, self.collection_name)

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
                    if not isinstance(record[name], array):
                        raise IntegrationInvalidResponseException(f"Oracle returned an invalid vector for '{name}'.")
                    record[name] = record[name].tolist()
        return result

    def _prepare_filter(self, filter: FilterExpression | None) -> tuple[str, dict[str, Any]]:
        return ("1=1", {}) if filter is None else _FilterCompiler(self.definition).compile(filter)

    def _prepare_order_by(self, order_by: Mapping[str, bool] | None) -> str:
        parts: list[str] = []
        ordered_fields: set[str] = set()
        for name, ascending in (order_by or {}).items():
            if type(ascending) is not bool:
                raise TypeError("Oracle order directions must be booleans.")
            field = _scalar_field(self.definition, name)
            parts.append(
                f"{_quote_identifier(field.storage_name or field.name)} {'ASC' if ascending else 'DESC'} NULLS LAST"
            )
            ordered_fields.add(field.name)
        if self.definition.key_name not in ordered_fields:
            parts.append(f"{_quote_identifier(self.definition.key_field_storage_name)} ASC")
        return ", ".join(parts)

    def _prepare_key(self, key: Any) -> Any:
        return _validate_scalar(self.definition.key_field, key)

    def _decode_row(self, fields: Sequence[VectorStoreField], row: Sequence[Any]) -> dict[str, Any]:
        if len(row) != len(fields):
            raise IntegrationInvalidResponseException("Oracle returned an unexpected number of columns.")
        result: dict[str, Any] = {}
        for field, value in zip(fields, row, strict=True):
            if value is not None and field.type_ == "UUID":
                if not isinstance(value, UUID | str):
                    raise IntegrationInvalidResponseException(f"Oracle returned an invalid UUID for '{field.name}'.")
                try:
                    value = UUID(str(value))
                except ValueError as exc:
                    raise IntegrationInvalidResponseException(
                        f"Oracle returned an invalid UUID for '{field.name}'."
                    ) from exc
            elif value is not None and field.type_ == "int":
                if (isinstance(value, Decimal) and value.is_finite() and value == int(value)) or (
                    type(value) is float and math.isfinite(value) and abs(value) <= 2**53 and value.is_integer()
                ):
                    value = int(value)
                if type(value) is not int or not -(2**63) <= value < 2**63:
                    raise IntegrationInvalidResponseException(f"Oracle returned an invalid integer for '{field.name}'.")
            elif value is not None and field.type_ == "float":
                if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
                    raise IntegrationInvalidResponseException(f"Oracle returned an invalid float for '{field.name}'.")
                try:
                    value = float(value)
                except OverflowError as exc:
                    raise IntegrationInvalidResponseException(
                        f"Oracle returned an invalid float for '{field.name}'."
                    ) from exc
                if not math.isfinite(value):
                    raise IntegrationInvalidResponseException(f"Oracle returned an invalid float for '{field.name}'.")
            elif value is not None and field.type_ == "bool":
                if value not in (0, 1):
                    raise IntegrationInvalidResponseException(f"Oracle returned an invalid boolean for '{field.name}'.")
                value = bool(value)
            result[field.storage_name or field.name] = value
        return result

    async def _inner_upsert(
        self, records: Sequence[Any], *, operation_options: Mapping[str, Any] | None = None
    ) -> Sequence[KeyT]:
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        binds: list[dict[str, Any]] = []
        keys: list[KeyT] = []
        key_index = self._fields.index(self.definition.key_field)
        for record in records:
            row: dict[str, Any] = {}
            for index, field in enumerate(self._fields):
                name = field.storage_name or field.name
                row[f"p{index}"] = (
                    _prepare_vector(field, record[name])
                    if field.field_type == "vector"
                    else _validate_scalar(field, record[name])
                )
            key = row[f"p{key_index}"]
            keys.append(cast(KeyT, UUID(key) if self.definition.key_field.type_ == "UUID" else key))
            binds.append(row)
        if not binds:
            return []
        key_column = _quote_identifier(self.definition.key_field_storage_name)
        updates = [
            f"target.{_quote_identifier(field.storage_name or field.name)} = :p{index}"
            for index, field in enumerate(self._fields)
            if index != key_index
        ]
        columns = ", ".join(_quote_identifier(field.storage_name or field.name) for field in self._fields)
        placeholders = ", ".join(f":p{index}" for index in range(len(self._fields)))
        # SQL interpolates only quoted identifiers and fixed fragments; data remains bound.
        statement = (
            f"MERGE INTO {self._table} target USING DUAL "  # ruff: ignore[hardcoded-sql-expression]  # nosec B608
            f"ON (target.{key_column} = :p{key_index}) "
            f"WHEN MATCHED THEN UPDATE SET {', '.join(updates)} "
            f"WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({placeholders})"
        )
        async with (
            self._client.connection(write=True) as connection,
            cast(_OracleCursor, connection.cursor()) as cursor,
        ):
            cursor.setinputsizes(**{f"p{index}": _bind_type(field) for index, field in enumerate(self._fields)})
            for start in range(0, len(binds), _BATCH_SIZE):
                await cursor.executemany(statement, binds[start : start + _BATCH_SIZE])
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
        fields = tuple(field for field in self._fields if include_vectors or field.field_type != "vector")
        columns = ", ".join(_quote_identifier(field.storage_name or field.name) for field in fields)
        if keys is not None:
            if order_by or skip or top != 10:
                raise ValueError("Oracle key lookup cannot be combined with order_by, top, or skip.")
            adapted = [self._prepare_key(key) for key in keys]
            if not adapted:
                return []
            found: dict[Any, dict[str, Any]] = {}
            key_column = _quote_identifier(self.definition.key_field_storage_name)
            async with self._client.connection() as connection, cast(_OracleCursor, connection.cursor()) as cursor:
                for start in range(0, len(adapted), _BATCH_SIZE):
                    chunk = adapted[start : start + _BATCH_SIZE]
                    binds = {f"k{index}": key for index, key in enumerate(chunk)}
                    placeholders = ", ".join(f":{name}" for name in binds)
                    statement = (
                        f"SELECT {columns} FROM {self._table} "  # ruff: ignore[hardcoded-sql-expression]  # nosec B608
                        f"WHERE {key_column} IN ({placeholders})"
                    )
                    await cursor.execute(statement, binds)
                    for row in await cursor.fetchall():
                        decoded = self._decode_row(fields, row)
                        found[self._prepare_key(decoded[self.definition.key_field_storage_name])] = decoded
            return [found[key] for key in adapted if key in found]
        where, binds = self._prepare_filter(filter)
        order = self._prepare_order_by(order_by)
        binds.update(top=top, skip=skip)
        async with self._client.connection() as connection, cast(_OracleCursor, connection.cursor()) as cursor:
            statement = (
                f"SELECT {columns} FROM {self._table} "  # ruff: ignore[hardcoded-sql-expression]  # nosec B608
                f"WHERE {where} ORDER BY {order} "
                "OFFSET :skip ROWS FETCH NEXT :top ROWS ONLY"
            )
            await cursor.execute(statement, binds)
            return [self._decode_row(fields, row) for row in await cursor.fetchall()]

    async def _inner_delete(self, keys: Sequence[KeyT], *, operation_options: Mapping[str, Any] | None = None) -> None:
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        adapted = [self._prepare_key(key) for key in keys]
        if not adapted:
            return
        key_column = _quote_identifier(self.definition.key_field_storage_name)
        async with (
            self._client.connection(write=True) as connection,
            cast(_OracleCursor, connection.cursor()) as cursor,
        ):
            for start in range(0, len(adapted), _BATCH_SIZE):
                chunk = adapted[start : start + _BATCH_SIZE]
                binds = {f"k{index}": key for index, key in enumerate(chunk)}
                placeholders = ", ".join(f":{name}" for name in binds)
                statement = (
                    f"DELETE FROM {self._table} "  # ruff: ignore[hardcoded-sql-expression]  # nosec B608
                    f"WHERE {key_column} IN ({placeholders})"
                )
                await cursor.execute(statement, binds)

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
        _validate_operation_options(operation_options)
        if search_type != "vector" or additional_property_name is not None:
            raise NotImplementedError("Oracle supports dense vector search only, not keyword-hybrid search.")
        if vector is None:
            raise NotImplementedError(
                "Oracle has no server-side vectorization; supply a vector or embedding generator."
            )
        self._client.ensure_open()
        field = self.definition.try_get_vector_field(vector_property_name)
        if field is None:
            raise ValueError("Select a vector_property_name from the collection definition.")
        prepared = _prepare_vector(field, vector)
        column = _quote_identifier(field.storage_name or field.name)
        metric = _METRICS[field.distance_function or "DEFAULT"]
        distance = f"VECTOR_DISTANCE({column}, :query_vector, {metric})"
        score = (
            f"(1 - {distance})"
            if field.distance_function == "cosine_similarity"
            else (f"(-{distance})" if field.distance_function == "dot_prod" else distance)
        )
        where, binds = self._prepare_filter(filter)
        binds["query_vector"] = prepared
        predicate = f"({where}) AND {column} IS NOT NULL"
        if score_threshold is not None:
            if type(score_threshold) not in (int, float):
                raise ValueError("Oracle score_threshold must be a finite number.")
            try:
                score_threshold = float(score_threshold)
            except OverflowError as exc:
                raise ValueError("Oracle score_threshold must be a finite number.") from exc
            if not math.isfinite(score_threshold):
                raise ValueError("Oracle score_threshold must be a finite number.")
            cutoff = (
                1 - score_threshold
                if field.distance_function == "cosine_similarity"
                else -score_threshold
                if field.distance_function == "dot_prod"
                else score_threshold
            )
            binds["threshold"] = cutoff
            predicate += f" AND {distance} <= :threshold"
        binds.update(top=top, skip=skip)
        fields = tuple(item for item in self._fields if include_vectors or item.field_type != "vector")
        columns = ", ".join(_quote_identifier(item.storage_name or item.name) for item in fields)
        statement = (
            f"SELECT {columns}, {score} FROM {self._table} "  # ruff: ignore[hardcoded-sql-expression]  # nosec B608
            f"WHERE {predicate} "
            f"ORDER BY {distance} ASC, {_quote_identifier(self.definition.key_field_storage_name)} ASC "
            "OFFSET :skip ROWS FETCH NEXT :top ROWS ONLY"
        )
        async with self._client.connection() as connection, cast(_OracleCursor, connection.cursor()) as cursor:
            cursor.setinputsizes(query_vector=_bind_type(field))
            await cursor.execute(statement, binds)
            rows = await cursor.fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            record = self._decode_row(fields, row[:-1])
            if row[-1] is None:
                raise IntegrationInvalidResponseException("Oracle returned a null vector distance.")
            score_value = float(row[-1])
            if not math.isfinite(score_value):
                raise IntegrationInvalidResponseException("Oracle returned a nonfinite vector distance.")
            results.append({"record": record, "score": score_value})
        return SearchResults(results, metadata={"distance_function": field.distance_function or "DEFAULT"})

    def _get_record_from_result(self, result: Any) -> Any:
        return result["record"]

    def _get_score_from_result(self, result: Any) -> float | None:
        return result["score"]


async def _drop_table(client: _Client, name: str) -> None:
    async with client.connection() as connection, cast(_OracleCursor, connection.cursor()) as cursor:
        try:
            await cursor.execute(f"DROP TABLE {_quote_identifier(name)} PURGE")
        except oracledb.DatabaseError as exc:
            if _oracle_error_code(exc) != 942:
                raise


class OracleStore(BaseVectorStore):
    """Create Oracle vector collections sharing one async pool or connection."""

    def __init__(
        self,
        *,
        dsn: str | None = None,
        user: str | None = None,
        password: str | SecretString | None = None,
        client: OracleClient | None = None,
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a store without opening its connector-owned pool.

        Args:
            dsn: Oracle connect string; defaults to ``ORACLE_DSN``.
            user: Oracle database user; defaults to ``ORACLE_USER``.
            password: Database password or AF SecretString; defaults to ``ORACLE_PASSWORD``.
            client: Borrowed async connection or pool in place of connection settings.
            embedding_generator: Default local embedding client for child collections.
            env_file_path: Optional selected .env file; no implicit discovery.
            env_file_encoding: Encoding of the selected .env file.
        """
        super().__init__(embedding_generator=embedding_generator, managed_client=client is None)
        self._client = _create_client(
            dsn=dsn,
            user=user,
            password=password,
            client=client,
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
    ) -> OracleCollection[Any, ModelT]:
        """Create a collection borrowing this store's connection lifecycle."""
        return OracleCollection(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator if embedding_generator is not None else self.embedding_generator,
            _shared_client=self._client,
        )

    async def list_collection_names(self, *, operation_options: Mapping[str, Any] | None = None) -> Sequence[str]:
        """List base table names in the current Oracle user schema."""
        _validate_operation_options(operation_options)
        async with self._client.connection() as connection, cast(_OracleCursor, connection.cursor()) as cursor:
            await cursor.execute("SELECT TABLE_NAME FROM USER_TABLES ORDER BY TABLE_NAME")
            names: list[str] = []
            for row in await cursor.fetchall():
                if len(row) != 1 or not isinstance(row[0], str):
                    raise IntegrationInvalidResponseException("Oracle returned an invalid table name.")
                names.append(row[0])
            return names

    async def _inner_ensure_collection_deleted(
        self, collection_name: str, *, operation_options: Mapping[str, Any] | None = None
    ) -> None:
        _validate_operation_options(operation_options)
        await _drop_table(self._client, collection_name)

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close the owned pool when exiting the store context."""
        await self.close()

    async def close(self) -> None:
        """Close the store, leaving injected clients untouched."""
        await self._client.close()
