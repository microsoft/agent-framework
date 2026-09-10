# Copyright (c) Microsoft. All rights reserved.

"""Async Azure DocumentDB collection lifecycle, CRUD, filters, and vector search."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, ClassVar, Generic, cast

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
from agent_framework._telemetry import FeatureIndex, mark_feature_used
from agent_framework._vector_filters import FilterExpression
from agent_framework._vectors import EmbeddingClient, SearchType, Vector
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException
from bson import BSON
from bson.errors import InvalidDocument
from pymongo import AsyncMongoClient, ReplaceOne
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import CollectionInvalid, OperationFailure, PyMongoError
from typing_extensions import Self, TypedDict, TypeVar

KeyT = TypeVar("KeyT", default=Any)
ModelT = TypeVar("ModelT", default=Any)

_Document = dict[str, Any]
_ClientType = AsyncMongoClient[_Document]
_DatabaseType = AsyncDatabase[_Document]
_CollectionType = AsyncCollection[_Document]

_MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
_MAX_ID_BYTES = 2 * 1024
_MAX_INDEX_PATH_BYTES = 256
_MAX_WRITES_PER_BATCH = 25_000
_KEY_BATCH_SIZE = 1_000
_INDEX_RACE_CODES = {68, 85, 86}
_INDEX_RACE_NAMES = {"IndexAlreadyExists", "IndexKeySpecsConflict", "IndexOptionsConflict"}
_NATIVE_SCORE_FIELD = "_af_documentdb_score"
_CLIENT_OPTION_NAMES = {"appname", "retryWrites", "tls"}
_INDEX_KINDS = {
    "default": "vector-ivf",
    "ivf_flat": "vector-ivf",
    "hnsw": "vector-hnsw",
    "disk_ann": "vector-diskann",
}
_METRICS = {
    "DEFAULT": "COS",
    "cosine_similarity": "COS",
    "dot_prod": "IP",
    "euclidean_distance": "L2",
}
_DATA_TYPES = {"str", "int", "float", "bool", "bytes", "list", "dict"}


class AzureDocumentDBSettings(TypedDict, total=False):
    """Connection settings resolved from explicit values, a selected file, or the process environment."""

    connection_string: SecretString | None
    """Azure DocumentDB MongoDB connection string from ``AZURE_DOCUMENTDB_CONNECTION_STRING``."""

    database_name: str | None
    """Database name from ``AZURE_DOCUMENTDB_DATABASE_NAME``."""


def _validate_operation_options(
    options: Mapping[str, Any] | None,
    allowed: set[str] | None = None,
) -> dict[str, Any]:
    result = dict(options or {})
    if unknown := result.keys() - (allowed or set()):
        raise NotImplementedError(f"Unsupported Azure DocumentDB operation option(s): {', '.join(sorted(unknown))}.")
    return result


def _validate_integer(value: Any, name: str, minimum: int, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        requirement = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise ValueError(f"{name} must be an integer {requirement}.")
    return value


def _validate_database_name(name: Any) -> str:
    if not isinstance(name, str) or not name or len(name.encode("utf-8")) > 63:
        raise ValueError("database_name must contain 1-63 UTF-8 bytes.")
    if any(character in name for character in '/\\."$*<>:|?\0'):
        raise ValueError("database_name contains a character unsupported by Azure DocumentDB.")
    return name


def _validate_collection_name(name: Any) -> str:
    if not isinstance(name, str) or not name or len(name.encode("utf-8")) > 255:
        raise ValueError("collection_name must contain 1-255 UTF-8 bytes.")
    if "\0" in name or "$" in name or name.startswith("system."):
        raise ValueError("collection_name contains a reserved Azure DocumentDB name or character.")
    return name


def _validate_storage_name(name: str, *, indexed: bool) -> str:
    encoded = name.encode("utf-8")
    if not name or "\0" in name or "." in name or name.startswith("$"):
        raise ValueError("Azure DocumentDB fields must be non-empty top-level names without '.', '$' prefixes, or NUL.")
    if indexed and len(encoded) > _MAX_INDEX_PATH_BYTES:
        raise ValueError(f"Azure DocumentDB indexed field paths cannot exceed {_MAX_INDEX_PATH_BYTES} UTF-8 bytes.")
    return name


def _validate_client_options(options: Mapping[str, Any] | None) -> dict[str, Any]:
    result = dict(options or {})
    if unknown := result.keys() - _CLIENT_OPTION_NAMES:
        raise NotImplementedError(f"Unsupported Azure DocumentDB client option(s): {', '.join(sorted(unknown))}.")
    if "tls" in result and result["tls"] is not True:
        raise ValueError("Azure DocumentDB requires client_options['tls'] to be True.")
    if "retryWrites" in result and result["retryWrites"] is not False:
        raise ValueError("Azure DocumentDB requires client_options['retryWrites'] to be False.")
    if "appname" in result:
        app_name = result["appname"]
        if not isinstance(app_name, str) or not app_name or "\0" in app_name or len(app_name.encode()) > 128:
            raise ValueError("client_options['appname'] must contain 1-128 UTF-8 bytes and no NUL.")
    return {"tls": True, "retryWrites": False, "appname": "agent-framework-azure-documentdb", **result}


class _Client:
    """Own one connector-created client or borrow a caller's resolved database."""

    def __init__(self, client: _ClientType, database: _DatabaseType, *, owned: bool) -> None:
        self.client = client
        self.database = database
        self.owned = owned
        self.closed = False

    def ensure_open(self) -> None:
        if self.closed:
            raise RuntimeError("The Azure DocumentDB client is closed.")

    async def close(self) -> None:
        if not self.closed:
            if self.owned:
                await self.client.close()
            self.closed = True


def _create_client(
    connection_string: str | SecretString | None,
    database_name: str | None,
    *,
    client: _ClientType | None,
    database: _DatabaseType | None,
    client_options: Mapping[str, Any] | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> _Client:
    if database is not None:
        if any(
            value is not None
            for value in (
                connection_string,
                database_name,
                client,
                client_options,
                env_file_path,
                env_file_encoding,
            )
        ):
            raise ValueError("database cannot be combined with a client or connection settings.")
        if not isinstance(database, AsyncDatabase):
            raise TypeError("database must be a PyMongo AsyncDatabase.")
        return _Client(database.client, database, owned=False)
    if client is not None:
        if any(value is not None for value in (connection_string, client_options, env_file_path, env_file_encoding)):
            raise ValueError("client cannot be combined with connection settings or client_options.")
        if not isinstance(client, AsyncMongoClient):
            raise TypeError("client must be a PyMongo AsyncMongoClient.")
        if database_name is None:
            raise ValueError("database_name is required with an injected client.")
        resolved_database_name = _validate_database_name(database_name)
        return _Client(client, client[resolved_database_name], owned=False)

    settings = load_settings(
        AzureDocumentDBSettings,
        env_prefix="AZURE_DOCUMENTDB_",
        connection_string=connection_string,
        database_name=database_name,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    resolved_connection_string = settings.get("connection_string")
    if (
        not isinstance(resolved_connection_string, SecretString)
        or not resolved_connection_string.get_secret_value().strip()
    ):
        raise ValueError("A non-empty Azure DocumentDB connection_string is required.")
    resolved_database_name = _validate_database_name(settings.get("database_name"))
    created_client: _ClientType = AsyncMongoClient(
        resolved_connection_string.get_secret_value(),
        **_validate_client_options(client_options),
    )
    return _Client(created_client, created_client[resolved_database_name], owned=True)


def _prepare_key(value: Any, expected_type: str | None) -> str | int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise TypeError("Azure DocumentDB keys must be strings or signed 64-bit integers, not booleans.")
    if expected_type == "str" and not isinstance(value, str):
        raise TypeError("Azure DocumentDB key must match its declared string type.")
    if expected_type == "int" and type(value) is not int:
        raise TypeError("Azure DocumentDB key must match its declared integer type.")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > _MAX_ID_BYTES:
            raise ValueError(f"Azure DocumentDB string keys cannot exceed {_MAX_ID_BYTES} UTF-8 bytes.")
    elif not -(2**63) <= value < 2**63:
        raise ValueError("Azure DocumentDB integer keys must fit a signed 64-bit BSON integer.")
    return value


def _prepare_untyped_bson_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (str, bytes, bool)):
        return value
    if isinstance(value, int):
        if not -(2**63) <= value < 2**63:
            raise ValueError(f"Field '{path}' contains an integer outside the signed 64-bit BSON range.")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Field '{path}' contains a non-finite number.")
        return value
    if isinstance(value, list):
        return [_prepare_untyped_bson_value(item, path=f"{path}[]") for item in cast(list[Any], value)]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in cast(dict[Any, Any], value).items():
            if not isinstance(key, str) or not key or "\0" in key or "." in key or key.startswith("$"):
                raise TypeError(
                    f"Field '{path}' requires non-empty string object keys without '.', '$' prefixes, or NUL."
                )
            result[key] = _prepare_untyped_bson_value(item, path=f"{path}.{key}")
        return result
    raise TypeError(f"Field '{path}' contains unsupported BSON value type '{type(value).__name__}'.")


def _prepare_field_value(field: VectorStoreField, value: Any) -> Any:
    if value is None:
        return None
    kind = field.type_
    if kind == "str" and isinstance(value, str):
        return value
    if kind == "int" and type(value) is int:
        return _prepare_untyped_bson_value(value, path=field.name)
    if kind == "float" and type(value) in (int, float):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"Field '{field.name}' requires a finite number.")
        return number
    if kind == "bool" and type(value) is bool:
        return value
    if kind == "bytes" and isinstance(value, bytes):
        return value
    if kind == "list" and isinstance(value, list):
        return _prepare_untyped_bson_value(value, path=field.name)
    if kind == "dict" and isinstance(value, dict):
        return _prepare_untyped_bson_value(value, path=field.name)
    raise TypeError(f"Azure DocumentDB field '{field.name}' requires declared type '{kind}'.")


def _prepare_dense_vector(value: Any, field: VectorStoreField) -> list[float | int] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"Vector field '{field.name}' requires a dense numeric sequence.")
    result: list[float | int] = []
    for item in cast(Sequence[Any], value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(f"Vector field '{field.name}' must contain numbers, not booleans.")
        if isinstance(item, int):
            if not -(2**63) <= item < 2**63:
                raise ValueError(f"Vector field '{field.name}' contains an integer outside the BSON range.")
            result.append(item)
        elif not math.isfinite(item):
            raise ValueError(f"Vector field '{field.name}' must contain finite numbers.")
        else:
            result.append(item)
    return result


def _validate_bson_document(document: _Document) -> None:
    try:
        encoded = BSON.encode(document)
    except (InvalidDocument, OverflowError) as exc:
        raise TypeError("Azure DocumentDB records must be BSON encodable.") from exc
    if len(encoded) > _MAX_DOCUMENT_BYTES:
        raise ValueError(f"Azure DocumentDB records cannot exceed {_MAX_DOCUMENT_BYTES} encoded BSON bytes.")


def _prepare_filter_field(
    fields: Sequence[VectorStoreField],
    definition: VectorStoreCollectionDefinition,
    name: str,
) -> tuple[VectorStoreField, str]:
    if "." in name:
        raise NotImplementedError("Azure DocumentDB filters support declared top-level logical fields only.")
    logical_field = definition.try_get_field(name)
    if logical_field is None:
        raise ValueError(f"Unknown Azure DocumentDB field '{name}'.")
    field = next(field for field in fields if field.name == logical_field.name)
    if field.field_type == "vector":
        raise NotImplementedError("Azure DocumentDB portable filters do not operate on vector fields.")
    if field.field_type == "key":
        return field, "_id"
    if field.type_ == "dict":
        raise NotImplementedError(
            "Azure DocumentDB filters do not support dictionary fields because "
            "BSON document equality is order-sensitive."
        )
    if field.is_indexed is not True:
        raise NotImplementedError(f"Azure DocumentDB filter field '{field.name}' must declare is_indexed=True.")
    return field, field.storage_name or field.name


def _prepare_filter_operand(field: VectorStoreField, value: Any, *, ordered: bool = False) -> Any:
    if value is None:
        if ordered:
            raise TypeError("Ordered Azure DocumentDB filter operands cannot be null.")
        return None
    kind = field.type_
    if kind == "float" and type(value) in (int, float):
        if not math.isfinite(value):
            raise ValueError("Azure DocumentDB numeric filter operands must be finite.")
        return value
    if kind == "int" and type(value) in (int, float):
        if isinstance(value, int) and not -(2**63) <= value < 2**63:
            raise ValueError("Azure DocumentDB integer filter operands must fit signed 64-bit BSON integers.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Azure DocumentDB numeric filter operands must be finite.")
        return value
    if ordered and kind not in {"str", "int", "float"}:
        raise NotImplementedError("Ordered Azure DocumentDB filters require a string, int, or float field.")
    if kind == "str" and isinstance(value, str):
        return value
    if kind == "bool" and type(value) is bool:
        return value
    if kind == "bytes" and isinstance(value, bytes):
        return value
    if kind == "list" and isinstance(value, list):
        return _prepare_untyped_bson_value(value, path=field.name)
    if kind == "dict" and isinstance(value, dict):
        return _prepare_untyped_bson_value(value, path=field.name)
    return _TYPE_MISMATCH


class _TypeMismatch:
    pass


_TYPE_MISMATCH = _TypeMismatch()


class _FilterCompiler:
    """Translate a core filter snapshot to a BSON query without string interpolation."""

    def __init__(
        self,
        fields: Sequence[VectorStoreField],
        definition: VectorStoreCollectionDefinition,
    ) -> None:
        self.fields = fields
        self.definition = definition

    def compile(self, expression: FilterExpression) -> _Document:
        return self._prepare_filter_condition(expression)

    @staticmethod
    def _false_filter() -> _Document:
        return {"_id": {"$exists": False}}

    def _prepare_filter_group(self, expression: FilterGroup) -> _Document:
        children = [self._prepare_filter_condition(child) for child in expression.filters]
        if expression.operator == "and":
            return {"$and": children}
        if expression.operator == "or":
            return {"$or": children}
        return {"$nor": children}

    def _prepare_filter_condition(self, expression: FilterExpression) -> _Document:
        if isinstance(expression, FilterGroup):
            return self._prepare_filter_group(expression)
        field, name = _prepare_filter_field(self.fields, self.definition, expression.field_name)
        operator, value = expression.operator, expression.value
        if operator == "exists":
            return {name: {"$exists": True}}
        if operator == "is_null":
            return {"$and": [{name: {"$exists": True}}, {name: {"$eq": None}}]}
        if operator == "is_not_null":
            return {"$and": [{name: {"$exists": True}}, {name: {"$ne": None}}]}
        if operator in {"eq", "ne"}:
            operand = _prepare_filter_operand(field, value)
            if operand is _TYPE_MISMATCH:
                if operator == "eq":
                    return self._false_filter()
                return {name: {"$exists": True}}
            condition = {name: {f"${operator}": operand}}
            if operator == "ne" or operand is None:
                return {"$and": [{name: {"$exists": True}}, condition]}
            return condition
        if operator in {"gt", "gte", "lt", "lte"}:
            operand = _prepare_filter_operand(field, value, ordered=True)
            if operand is _TYPE_MISMATCH:
                raise TypeError(f"Ordered filter operand does not match field '{field.name}'.")
            return {name: {f"${operator}": operand}}
        if operator == "between":
            lower = _prepare_filter_operand(field, value[0], ordered=True)
            upper = _prepare_filter_operand(field, value[1], ordered=True)
            if lower is _TYPE_MISMATCH or upper is _TYPE_MISMATCH:
                raise TypeError(f"Between operands do not match field '{field.name}'.")
            return {name: {"$gte": lower, "$lte": upper}}
        if operator in {"in", "not_in"}:
            if field.type_ == "list":
                raise NotImplementedError(
                    "Use contains, contains_any, or contains_all for Azure DocumentDB list fields."
                )
            operands = [_prepare_filter_operand(field, item) for item in value]
            operands = [item for item in operands if item is not _TYPE_MISMATCH]
            if not operands:
                if operator == "in":
                    return self._false_filter()
                return {"$and": [{name: {"$exists": True}}, {name: {"$ne": None}}]}
            condition = {name: {"$in" if operator == "in" else "$nin": operands}}
            if operator == "not_in" or None in operands:
                guards: list[_Document] = [{name: {"$exists": True}}]
                if operator == "not_in":
                    guards.append({name: {"$ne": None}})
                guards.append(condition)
                return {"$and": guards}
            return condition
        if operator in {"contains", "contains_any", "contains_all"}:
            if field.type_ != "list":
                raise TypeError("Azure DocumentDB collection membership requires a declared list field.")
            operands = [value] if operator == "contains" else list(value)
            if any(isinstance(item, (list, dict)) for item in operands):
                raise NotImplementedError("Nested collection membership has ambiguous MongoDB array semantics.")
            prepared = [_prepare_untyped_bson_value(item, path=f"{field.name}[]") for item in operands]
            if not prepared:
                return (
                    {"$and": [{name: {"$exists": True}}, {name: {"$ne": None}}]}
                    if operator == "contains_all"
                    else self._false_filter()
                )
            native_operator = "$all" if operator == "contains_all" else "$in"
            return {
                "$and": [
                    {name: {"$exists": True}},
                    {name: {"$ne": None}},
                    {name: {native_operator: prepared}},
                ]
            }
        raise NotImplementedError(
            f"Azure DocumentDB does not support portable filter operator '{operator}' in this connector. "
            "Literal text operations are not equivalent to regular-expression or analyzed search."
        )


def _index_name(collection_name: str, field_name: str, kind: str) -> str:
    digest = hashlib.sha256(f"{collection_name}\0{field_name}\0{kind}".encode()).hexdigest()[:32]
    return f"af_{kind}_{digest}"


def _vector_index_options(field: VectorStoreField) -> _Document:
    kind = _INDEX_KINDS[cast(str, field.index_kind)]
    annotations = field.provider_annotations
    options: _Document = {
        "kind": kind,
        "dimensions": field.dimensions,
        "similarity": _METRICS[cast(str, field.distance_function)],
    }
    if kind == "vector-ivf":
        options["numLists"] = annotations.get("azure_documentdb.num_lists", 1)
    elif kind == "vector-hnsw":
        options["m"] = annotations.get("azure_documentdb.m", 16)
        options["efConstruction"] = annotations.get("azure_documentdb.ef_construction", 64)
    else:
        options["maxDegree"] = annotations.get("azure_documentdb.max_degree", 32)
        options["lBuild"] = annotations.get("azure_documentdb.l_build", 50)
    return options


def _vector_index_spec(collection_name: str, field: VectorStoreField) -> _Document:
    path = field.storage_name or field.name
    return {
        "name": _index_name(collection_name, path, "vector"),
        "key": {path: "cosmosSearch"},
        "cosmosSearchOptions": _vector_index_options(field),
    }


def _data_index_spec(collection_name: str, field: VectorStoreField) -> _Document:
    path = field.storage_name or field.name
    return {"name": _index_name(collection_name, path, "filter"), "key": {path: 1}}


def _canonical_vector_options(value: Mapping[str, Any]) -> _Document:
    raw_kind = value.get("kind")
    kind = raw_kind if isinstance(raw_kind, str) else None
    common: set[str] = {"kind", "dimensions", "similarity"}
    options_by_kind: Mapping[str, set[str]] = {
        "vector-ivf": {"numLists"},
        "vector-hnsw": {"m", "efConstruction"},
        "vector-diskann": {"maxDegree", "lBuild"},
    }
    algorithm_options = options_by_kind.get(kind, set[str]()) if kind is not None else set[str]()
    if unknown := value.keys() - common - algorithm_options:
        raise ValueError(
            f"Existing Azure DocumentDB vector index has unsupported option(s): {', '.join(sorted(unknown))}."
        )
    result: _Document = {
        "kind": kind,
        "dimensions": value.get("dimensions"),
        "similarity": str(value.get("similarity", "")).upper(),
    }
    if kind == "vector-ivf":
        result["numLists"] = value.get("numLists")
    elif kind == "vector-hnsw":
        result["m"] = value.get("m", 16)
        result["efConstruction"] = value.get("efConstruction", 64)
    elif kind == "vector-diskann":
        result["maxDegree"] = value.get("maxDegree", 32)
        result["lBuild"] = value.get("lBuild", 50)
    return result


def _matching_index(indexes: Sequence[Mapping[str, Any]], expected: Mapping[str, Any]) -> bool:
    expected_name = expected["name"]
    expected_key = expected["key"]
    is_vector = "cosmosSearchOptions" in expected
    for index in indexes:
        same_name = index.get("name") == expected_name
        same_key = index.get("key") == expected_key
        if not same_name and not same_key:
            continue
        if not same_key:
            raise ValueError(f"Existing Azure DocumentDB index '{expected_name}' has an incompatible key.")
        if is_vector:
            raw_options = index.get("cosmosSearch") or index.get("cosmosSearchOptions")
            if not isinstance(raw_options, Mapping):
                raise ValueError("Existing Azure DocumentDB vector index is missing cosmosSearch options.")
            if _canonical_vector_options(cast(Mapping[str, Any], raw_options)) != _canonical_vector_options(
                cast(Mapping[str, Any], expected["cosmosSearchOptions"])
            ):
                raise ValueError(
                    f"Existing Azure DocumentDB vector index on '{next(iter(cast(Mapping[str, Any], expected_key)))}' "
                    "is incompatible with the collection definition."
                )
        elif (
            index.get("unique", False) is not False
            or index.get("sparse", False) is not False
            or "partialFilterExpression" in index
            or "expireAfterSeconds" in index
            or "collation" in index
        ):
            raise ValueError(
                f"Existing Azure DocumentDB filter index on "
                f"'{next(iter(cast(Mapping[str, Any], expected_key)))}' has incompatible options."
            )
        return True
    return False


class AzureDocumentDBCollection(
    BaseVectorCollection[KeyT, ModelT],
    BaseVectorSearch[KeyT, ModelT],
    Generic[KeyT, ModelT],
):
    """Store typed BSON documents and search vectors through ``$search.cosmosSearch``.

    Keys are explicit string or signed 64-bit integer ``_id`` values. Generated
    ObjectIds are intentionally unsupported because converting them to a core key
    type would not preserve identity. Scores retain Azure DocumentDB's native
    ``searchScore`` units, where larger values rank first.
    """

    supported_key_types: ClassVar[set[str] | None] = {"str", "int"}
    supported_vector_types: ClassVar[set[str] | None] = {"float", "float32", "float64"}
    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        connection_string: str | SecretString | None = None,
        database_name: str | None = None,
        client: _ClientType | None = None,
        database: _DatabaseType | None = None,
        collection: _CollectionType | None = None,
        client_options: Mapping[str, Any] | None = None,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Azure DocumentDB collection without performing network I/O.

        Args:
            record_type: Registered model type, or ``dict`` with an explicit definition.
            connection_string: MongoDB connection string for a connector-owned client.
            database_name: Database selected for a created or injected client.
            client: Caller-owned PyMongo async client. Requires ``database_name``.
            database: Caller-owned resolved PyMongo async database.
            collection: Caller-owned resolved PyMongo async collection.
            client_options: Created-client options limited to ``tls``, ``retryWrites``, and ``appname``.
            definition: Explicit dictionary schema.
            collection_name: Collection name overriding the model definition.
            embedding_generator: Default local embedding generator.
            env_file_path: Optional selected settings file.
            env_file_encoding: Encoding of the selected settings file.
        """
        if collection is not None:
            if not isinstance(collection, AsyncCollection):
                raise TypeError("collection must be a PyMongo AsyncCollection.")
            if collection_name is not None and collection_name != collection.name:
                raise ValueError("collection_name must match the injected collection.")
            if any(
                value is not None
                for value in (
                    connection_string,
                    database_name,
                    client,
                    database,
                    client_options,
                    env_file_path,
                    env_file_encoding,
                )
            ):
                raise ValueError("collection cannot be combined with a client, database, or connection settings.")
            resolved_collection_name = collection.name
        else:
            resolved_collection_name = collection_name
        super().__init__(
            record_type,
            definition=definition,
            collection_name=resolved_collection_name,
            embedding_generator=embedding_generator,
            managed_client=collection is None and client is None and database is None,
        )
        _validate_collection_name(self.collection_name)
        self._fields = tuple(
            replace(field, provider_annotations=field.provider_annotations) for field in self.definition.fields
        )
        if collection is not None:
            self._client = _Client(collection.database.client, collection.database, owned=False)
            self.collection = collection
        else:
            self._client = _create_client(
                connection_string,
                database_name,
                client=client,
                database=database,
                client_options=client_options,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
            self.collection = self._client.database[self.collection_name]
        self._shared_client = False

    def _validate_data_model(self) -> None:
        super()._validate_data_model()
        if self.definition.key_field.is_auto_generated:
            raise NotImplementedError(
                "Azure DocumentDB generated ObjectId keys are unsupported; provide an explicit string or integer key."
            )
        for field in self.definition.fields:
            name = "_id" if field.field_type == "key" else field.storage_name or field.name
            _validate_storage_name(name, indexed=field.field_type == "vector" or field.is_indexed is True)
            if field.field_type != "key" and name == "_id":
                raise ValueError("Only the key field can map to Azure DocumentDB '_id'.")
            if field.field_type != "key" and name == _NATIVE_SCORE_FIELD:
                raise ValueError(f"Azure DocumentDB field name '{_NATIVE_SCORE_FIELD}' is reserved.")
            if field.field_type == "data":
                if field.type_ not in _DATA_TYPES:
                    raise NotImplementedError(
                        f"Azure DocumentDB data field '{field.name}' needs a supported explicit type; "
                        f"got '{field.type_}'."
                    )
                if field.is_full_text_indexed:
                    raise NotImplementedError("Azure DocumentDB full-text and hybrid search are not supported.")
                if field.provider_annotations:
                    raise NotImplementedError("Azure DocumentDB provider annotations apply only to vector fields.")
                continue
            if field.field_type == "key":
                if field.provider_annotations:
                    raise NotImplementedError("Azure DocumentDB key provider annotations are unsupported.")
                continue
            if type(field.dimensions) is not int or not 1 <= field.dimensions <= 2000:
                raise ValueError("Azure DocumentDB standard vector dimensions must be an integer from 1 to 2000.")
            if field.index_kind not in _INDEX_KINDS:
                raise NotImplementedError(f"Unsupported Azure DocumentDB index kind '{field.index_kind}'.")
            if field.distance_function not in _METRICS:
                raise NotImplementedError(
                    f"Unsupported Azure DocumentDB distance function '{field.distance_function}'."
                )
            annotations = field.provider_annotations
            kind = _INDEX_KINDS[field.index_kind]
            allowed: set[str]
            if kind == "vector-ivf":
                allowed = {"azure_documentdb.num_lists"}
                _validate_integer(
                    annotations.get("azure_documentdb.num_lists", 1),
                    "azure_documentdb.num_lists",
                    1,
                )
            elif kind == "vector-hnsw":
                allowed = {"azure_documentdb.m", "azure_documentdb.ef_construction"}
                m = _validate_integer(annotations.get("azure_documentdb.m", 16), "azure_documentdb.m", 2, 100)
                _validate_integer(
                    annotations.get("azure_documentdb.ef_construction", 64),
                    "azure_documentdb.ef_construction",
                    2 * m,
                    1000,
                )
            else:
                allowed = {"azure_documentdb.max_degree", "azure_documentdb.l_build"}
                _validate_integer(
                    annotations.get("azure_documentdb.max_degree", 32),
                    "azure_documentdb.max_degree",
                    20,
                    2048,
                )
                _validate_integer(
                    annotations.get("azure_documentdb.l_build", 50),
                    "azure_documentdb.l_build",
                    10,
                    500,
                )
            if unknown := annotations.keys() - allowed:
                raise NotImplementedError(
                    f"Unsupported Azure DocumentDB vector annotation(s): {', '.join(sorted(unknown))}."
                )

    async def __aenter__(self) -> Self:
        """Enter the collection context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close resources owned directly by this collection."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close a directly owned client, never an injected or store-shared client."""
        if not self._shared_client:
            await self._client.close()

    async def _list_indexes(self) -> list[_Document]:
        cursor = await self.collection.list_indexes()
        return [dict(index) async for index in cursor]

    async def _ensure_index(self, expected: _Document, *, max_time_ms: int | None) -> None:
        indexes = await self._list_indexes()
        if _matching_index(indexes, expected):
            return
        command: _Document = {"createIndexes": self.collection_name, "indexes": [expected]}
        if max_time_ms is not None:
            command["maxTimeMS"] = max_time_ms
        try:
            await self._client.database.command(command)
        except OperationFailure as exc:
            details: Mapping[str, Any] = exc.details if isinstance(exc.details, Mapping) else {}
            if exc.code not in _INDEX_RACE_CODES and details.get("codeName") not in _INDEX_RACE_NAMES:
                raise
        indexes = await self._list_indexes()
        if not _matching_index(indexes, expected):
            raise IntegrationInvalidResponseException(
                f"Azure DocumentDB did not expose the requested index '{expected['name']}'."
            )

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create the collection and reconcile compatible vector/filter indexes."""
        options = _validate_operation_options(operation_options, {"create_indexes", "max_time_ms"})
        self._client.ensure_open()
        create_indexes = options.get("create_indexes", True)
        if not isinstance(create_indexes, bool):
            raise TypeError("create_indexes must be a boolean.")
        max_time_ms = options.get("max_time_ms")
        if max_time_ms is not None:
            max_time_ms = _validate_integer(max_time_ms, "max_time_ms", 1)
        if not await self.collection_exists():
            try:
                await self._client.database.create_collection(self.collection_name)
            except CollectionInvalid:
                if not await self.collection_exists():
                    raise
            except OperationFailure as exc:
                if exc.code != 48 or not await self.collection_exists():
                    raise
        if not create_indexes:
            return
        for field in self._fields:
            if field.field_type == "vector":
                await self._ensure_index(_vector_index_spec(self.collection_name, field), max_time_ms=max_time_ms)
            elif field.field_type == "data" and field.is_indexed:
                await self._ensure_index(_data_index_spec(self.collection_name, field), max_time_ms=max_time_ms)

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Return whether the configured collection exists."""
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        return self.collection_name in await self._client.database.list_collection_names()

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Drop only the configured collection when it exists."""
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        if await self.collection_exists():
            await self._client.database.drop_collection(self.collection_name)

    def _serialize_dicts_to_store_models(
        self,
        records: Sequence[dict[str, Any]],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[_Document]:
        result: list[_Document] = []
        for record in records:
            document: _Document = {}
            for field in self._fields:
                source_name = field.storage_name or field.name
                if source_name not in record:
                    raise ValueError(f"Record is missing Azure DocumentDB field '{field.name}'.")
                if field.field_type == "key":
                    document["_id"] = _prepare_key(record[source_name], field.type_)
                elif field.field_type == "vector":
                    document[source_name] = _prepare_dense_vector(record[source_name], field)
                else:
                    document[source_name] = _prepare_field_value(field, record[source_name])
            _validate_bson_document(document)
            result.append(document)
        return result

    def _deserialize_store_models_to_dicts(
        self,
        records: Sequence[Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        key_name = self.definition.key_field_storage_name
        for item in records:
            if not isinstance(item, Mapping):
                raise IntegrationInvalidResponseException("Azure DocumentDB returned a non-document record.")
            document = dict(cast(Mapping[str, Any], item))
            if "_id" not in document:
                raise IntegrationInvalidResponseException("Azure DocumentDB returned a document without '_id'.")
            document[key_name] = _prepare_key(document.pop("_id"), self.definition.key_field.type_)
            result.append(document)
        return result

    def _prepare_filter(self, filter: FilterExpression | None) -> _Document:
        if filter is None:
            return {}
        result = _FilterCompiler(self._fields, self.definition).compile(filter)
        try:
            encoded = BSON.encode(result)
        except (InvalidDocument, OverflowError) as exc:
            raise TypeError("Azure DocumentDB filters must be BSON encodable.") from exc
        if len(encoded) > _MAX_DOCUMENT_BYTES:
            raise ValueError(f"Azure DocumentDB filters cannot exceed {_MAX_DOCUMENT_BYTES} encoded BSON bytes.")
        return result

    def _projection(self, *, include_vectors: bool, score: bool = False) -> _Document:
        projection: _Document = {"_id": 1}
        for field in self._fields:
            if field.field_type != "key" and (include_vectors or field.field_type != "vector"):
                projection[field.storage_name or field.name] = 1
        if score:
            projection[_NATIVE_SCORE_FIELD] = {"$meta": "searchScore"}
        return projection

    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[KeyT]:
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        documents = [dict(cast(Mapping[str, Any], record)) for record in records]
        for document in documents:
            _validate_bson_document(document)
            _prepare_key(document.get("_id"), self.definition.key_field.type_)
        if not documents:
            return []
        completed = 0
        try:
            for start in range(0, len(documents), _MAX_WRITES_PER_BATCH):
                batch = documents[start : start + _MAX_WRITES_PER_BATCH]
                await self.collection.bulk_write(
                    [ReplaceOne({"_id": document["_id"]}, document, upsert=True) for document in batch],
                    ordered=True,
                )
                completed += len(batch)
        except PyMongoError as exc:
            raise IntegrationException(
                "Azure DocumentDB upsert failed. "
                f"{completed} records in earlier batches were applied; the failing batch may be partially applied."
            ) from exc
        return [cast(KeyT, document["_id"]) for document in documents]

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
    ) -> Sequence[_Document]:
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        if order_by:
            raise NotImplementedError("Azure DocumentDB ordered retrieval is not supported.")
        projection = self._projection(include_vectors=include_vectors)
        if keys is None:
            native_filter = self._prepare_filter(filter)
            cursor = self.collection.find(native_filter, projection=projection).skip(skip).limit(top)
            return [document async for document in cursor]
        if skip:
            raise ValueError("Azure DocumentDB key retrieval cannot be combined with skip.")
        prepared_keys = [_prepare_key(key, self.definition.key_field.type_) for key in keys]
        if not prepared_keys:
            return []
        documents: list[_Document] = []
        for start in range(0, len(prepared_keys), _KEY_BATCH_SIZE):
            cursor = self.collection.find(
                {"_id": {"$in": prepared_keys[start : start + _KEY_BATCH_SIZE]}},
                projection=projection,
            )
            documents.extend([document async for document in cursor])
        by_key = {document["_id"]: document for document in documents}
        return [by_key[key] for key in prepared_keys if key in by_key]

    async def _inner_delete(
        self,
        keys: Sequence[KeyT],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        prepared_keys = [_prepare_key(key, self.definition.key_field.type_) for key in keys]
        completed = 0
        try:
            for start in range(0, len(prepared_keys), _KEY_BATCH_SIZE):
                batch = prepared_keys[start : start + _KEY_BATCH_SIZE]
                await self.collection.delete_many({"_id": {"$in": batch}})
                completed += len(batch)
        except PyMongoError as exc:
            raise IntegrationException(
                "Azure DocumentDB delete failed. "
                f"{completed} keys in earlier batches were attempted; the failing batch may be partially applied."
            ) from exc

    def _search_options(
        self,
        field: VectorStoreField,
        *,
        top: int,
        skip: int,
        operation_options: Mapping[str, Any] | None,
    ) -> tuple[_Document, int | None]:
        options = _validate_operation_options(
            operation_options,
            {"ef_search", "k", "l_search", "max_time_ms", "n_probes"},
        )
        minimum_k = top + skip
        k = _validate_integer(options.get("k", minimum_k), "k", minimum_k)
        query: _Document = {"k": k}
        kind = _INDEX_KINDS[cast(str, field.index_kind)]
        if kind == "vector-ivf":
            if "ef_search" in options or "l_search" in options:
                raise ValueError("IVF search supports n_probes, not ef_search or l_search.")
            if "n_probes" in options:
                num_lists = cast(int, field.provider_annotations.get("azure_documentdb.num_lists", 1))
                query["nProbes"] = _validate_integer(options["n_probes"], "n_probes", 1, num_lists)
        elif kind == "vector-hnsw":
            if "n_probes" in options or "l_search" in options:
                raise ValueError("HNSW search supports ef_search, not n_probes or l_search.")
            if "ef_search" in options:
                query["efSearch"] = _validate_integer(options["ef_search"], "ef_search", 1)
        else:
            if "n_probes" in options or "ef_search" in options:
                raise ValueError("DiskANN search supports l_search, not n_probes or ef_search.")
            l_search = _validate_integer(options.get("l_search", max(40, k)), "l_search", 10, 1000)
            if k > l_search:
                raise ValueError("DiskANN search requires k to be less than or equal to l_search.")
            query["lSearch"] = l_search
        max_time_ms = options.get("max_time_ms")
        if max_time_ms is not None:
            max_time_ms = _validate_integer(max_time_ms, "max_time_ms", 1)
        return query, max_time_ms

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
        if search_type != "vector" or additional_property_name is not None:
            raise NotImplementedError("Azure DocumentDB supports dense vector search only.")
        if vector is None:
            raise ValueError("Azure DocumentDB search requires a vector or configured embedding generator.")
        self._client.ensure_open()
        resolved = self.definition.try_get_vector_field(vector_property_name)
        if resolved is None:
            raise ValueError("Select a vector_property_name from the Azure DocumentDB collection definition.")
        field = next(field for field in self._fields if field.name == resolved.name)
        query_vector = _prepare_dense_vector(vector, field)
        if query_vector is None:
            raise ValueError("Azure DocumentDB query vectors cannot be null.")
        native_options, max_time_ms = self._search_options(
            field,
            top=top,
            skip=skip,
            operation_options=operation_options,
        )
        cosmos_search: _Document = {
            "path": field.storage_name or field.name,
            "vector": query_vector,
            **native_options,
        }
        native_filter = self._prepare_filter(filter)
        if native_filter:
            cosmos_search["filter"] = native_filter
        metric = _METRICS[cast(str, field.distance_function)]
        threshold_operator = "$lte" if metric == "L2" else "$gte"
        threshold_direction = "maximum" if metric == "L2" else "minimum"
        pipeline: list[_Document] = [
            {"$search": {"cosmosSearch": cosmos_search}},
            {"$project": self._projection(include_vectors=include_vectors, score=True)},
        ]
        if score_threshold is not None:
            if isinstance(score_threshold, bool) or not isinstance(score_threshold, (int, float)):
                raise TypeError("Azure DocumentDB score_threshold must be a finite number.")
            if not math.isfinite(score_threshold):
                raise ValueError("Azure DocumentDB score_threshold must be a finite number.")
            pipeline.append({"$match": {_NATIVE_SCORE_FIELD: {threshold_operator: score_threshold}}})
        if skip:
            pipeline.append({"$skip": skip})
        pipeline.append({"$limit": top})
        cursor = (
            await self.collection.aggregate(pipeline, maxTimeMS=max_time_ms)
            if max_time_ms is not None
            else await self.collection.aggregate(pipeline)
        )
        return SearchResults(
            cursor,
            metadata={
                "candidate_window": cosmos_search["k"],
                "distance_function": field.distance_function or "DEFAULT",
                "index_kind": field.index_kind,
                "metric": metric,
                "score_threshold_direction": threshold_direction,
            },
        )

    def _get_record_from_result(self, result: Any) -> _Document:
        if not isinstance(result, Mapping):
            raise IntegrationInvalidResponseException("Azure DocumentDB returned a non-document search result.")
        document = dict(cast(Mapping[str, Any], result))
        if _NATIVE_SCORE_FIELD not in document:
            raise IntegrationInvalidResponseException("Azure DocumentDB search result is missing searchScore.")
        document.pop(_NATIVE_SCORE_FIELD)
        return document

    def _get_score_from_result(self, result: Any) -> float:
        if not isinstance(result, Mapping):
            raise IntegrationInvalidResponseException("Azure DocumentDB returned a non-document search result.")
        score = cast(Mapping[str, Any], result).get(_NATIVE_SCORE_FIELD)
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise IntegrationInvalidResponseException("Azure DocumentDB returned an invalid searchScore.")
        return float(score)


class AzureDocumentDBStore(BaseVectorStore):
    """Create collection clients that share one resolved Azure DocumentDB database."""

    def __init__(
        self,
        *,
        connection_string: str | SecretString | None = None,
        database_name: str | None = None,
        client: _ClientType | None = None,
        database: _DatabaseType | None = None,
        client_options: Mapping[str, Any] | None = None,
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a store without performing network I/O.

        Args:
            connection_string: MongoDB connection string for a connector-owned client.
            database_name: Database selected for a created or injected client.
            client: Caller-owned PyMongo async client. Requires ``database_name``.
            database: Caller-owned resolved PyMongo async database.
            client_options: Created-client options limited to ``tls``, ``retryWrites``, and ``appname``.
            embedding_generator: Default embedding generator for child collections.
            env_file_path: Optional selected settings file.
            env_file_encoding: Encoding of the selected settings file.
        """
        super().__init__(
            embedding_generator=embedding_generator,
            managed_client=client is None and database is None,
        )
        self._client = _create_client(
            connection_string,
            database_name,
            client=client,
            database=database,
            client_options=client_options,
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
    ) -> AzureDocumentDBCollection[Any, ModelT]:
        """Create a collection that borrows this store's resolved database."""
        collection = AzureDocumentDBCollection(
            record_type,
            database=self._client.database,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator if embedding_generator is not None else self.embedding_generator,
        )
        collection._client = self._client  # pyright: ignore[reportPrivateUsage]
        collection._shared_client = True  # pyright: ignore[reportPrivateUsage]
        return collection

    async def list_collection_names(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[str]:
        """List collection names in the resolved database."""
        _validate_operation_options(operation_options)
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        self._client.ensure_open()
        return await self._client.database.list_collection_names()

    async def collection_exists(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return whether one collection exists."""
        _validate_operation_options(operation_options)
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        self._client.ensure_open()
        _validate_collection_name(collection_name)
        return collection_name in await self._client.database.list_collection_names()

    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        _validate_operation_options(operation_options)
        self._client.ensure_open()
        _validate_collection_name(collection_name)
        await self._client.database.drop_collection(collection_name)

    async def aclose(self) -> None:
        """Close the connector-owned client once, leaving injected clients open."""
        await self._client.close()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close the connector-owned client on context exit."""
        await self.aclose()
