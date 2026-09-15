# Copyright (c) Microsoft. All rights reserved.

"""Async MongoDB collection lifecycle, BSON storage, filtering, and vector search."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections.abc import AsyncIterator, Collection, Mapping, Sequence
from datetime import datetime
from typing import Any, ClassVar, Generic, TypeAlias, cast

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
from agent_framework._telemetry import FeatureIndex, mark_feature_used
from agent_framework._vector_filters import FilterExpression
from agent_framework._vectors import EmbeddingClient, SearchType, Vector
from agent_framework.exceptions import IntegrationInvalidResponseException
from bson import BSON, ObjectId
from bson.errors import InvalidDocument
from bson.regex import Regex
from pymongo import AsyncMongoClient, ReplaceOne
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import CollectionInvalid, OperationFailure
from pymongo.operations import SearchIndexModel
from typing_extensions import TypedDict, TypeVar

KeyT = TypeVar("KeyT", default=Any)
ModelT = TypeVar("ModelT", default=Any)
MongoDocument: TypeAlias = dict[str, Any]
MongoClient: TypeAlias = AsyncMongoClient[MongoDocument]
MongoDatabase: TypeAlias = AsyncDatabase[MongoDocument]
MongoCollection: TypeAlias = AsyncCollection[MongoDocument]


class MongoDBSettings(TypedDict, total=False):
    """MongoDB settings loaded from explicit values, a selected .env file, or ``MONGODB_`` variables.

    Keys:
        uri: Required MongoDB connection URI from ``MONGODB_URI``, stored as an AF ``SecretString``.
        database_name: Required database from ``MONGODB_DATABASE_NAME``.
        app_name: Optional driver application name from ``MONGODB_APP_NAME``.
    """

    uri: SecretString | None
    database_name: str | None
    app_name: str | None


_BSON_MAX_DOCUMENT_SIZE = 16 * 1024 * 1024
_BSON_INT64_MIN = -(2**63)
_BSON_INT64_MAX = 2**63 - 1
_MAX_NUM_CANDIDATES = 10_000
_SCORE_FIELD = "__af_vector_search_score"
_VECTOR_FILTER_TYPES = frozenset({"str", "int", "float", "bool", "ObjectId", "datetime"})
_LIST_TYPES = frozenset({"list", "tuple", "set", "Sequence"})
_DISTANCES = {
    "DEFAULT": "cosine",
    "cosine_similarity": "cosine",
    "cosine_distance": "cosine",
    "dot_prod": "dotProduct",
    "euclidean_distance": "euclidean",
}
_INDEX_TERMINAL_FAILURES = frozenset({"FAILED", "DELETING"})
_FALSE_EXPRESSION: MongoDocument = {"$literal": False}


def _validate_operation_options(
    options: Mapping[str, Any] | None,
    allowed: set[str] | None = None,
) -> dict[str, Any]:
    result = dict(options or {})
    if unknown := result.keys() - (allowed or set()):
        raise NotImplementedError(f"Unsupported MongoDB operation option(s): {', '.join(sorted(unknown))}.")
    return result


def _validate_non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ValueError(f"{name} must be a non-empty string without NUL characters.")
    return value


def _create_client(
    *,
    uri: str | SecretString | None,
    database_name: str | None,
    app_name: str | None,
    async_client: MongoClient | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> tuple[MongoClient, MongoDatabase, str, bool]:
    if async_client is not None:
        if any(value is not None for value in (uri, app_name, env_file_path, env_file_encoding)):
            raise ValueError("async_client cannot be combined with uri, app_name, env_file_path, or env_file_encoding.")
        resolved_database_name = _validate_non_empty_string(database_name, "database_name")
        return (
            async_client,
            async_client.get_database(resolved_database_name),
            resolved_database_name,
            False,
        )

    settings = load_settings(
        MongoDBSettings,
        env_prefix="MONGODB_",
        uri=uri,
        database_name=database_name,
        app_name=app_name,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    resolved_uri = settings.get("uri")
    if not isinstance(resolved_uri, SecretString) or not resolved_uri.get_secret_value().strip():
        raise ValueError("MongoDB uri is required and must be a non-empty string or SecretString.")
    resolved_database_name = _validate_non_empty_string(settings.get("database_name"), "database_name")
    resolved_app_name = settings.get("app_name")
    if resolved_app_name is not None:
        _validate_non_empty_string(resolved_app_name, "app_name")
    client: MongoClient = AsyncMongoClient(
        resolved_uri.get_secret_value(),
        appname=resolved_app_name,
    )
    return client, client.get_database(resolved_database_name), resolved_database_name, True


def _prepare_int64(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not _BSON_INT64_MIN <= value <= _BSON_INT64_MAX:
        raise ValueError(f"{name} must be a signed 64-bit integer, not a boolean.")
    return value


def _prepare_key(value: Any, key_type: str | None, *, allow_none: bool = False) -> str | int | ObjectId | None:
    if value is None and allow_none:
        return None
    if key_type == "str" and isinstance(value, str):
        return value
    if key_type == "int":
        return _prepare_int64(value, "MongoDB integer keys")
    if key_type == "ObjectId" and isinstance(value, ObjectId):
        return value
    expected = key_type or "str, int, or ObjectId"
    raise TypeError(f"MongoDB key values must match the declared '{expected}' key type.")


def _prepare_bson_value(value: Any, *, name: str) -> Any:
    if value is None or isinstance(value, (str, bool, bytes, ObjectId, datetime)):
        return value
    if isinstance(value, int):
        return _prepare_int64(value, name)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} must not contain non-finite numbers.")
        return value
    if isinstance(value, Mapping):
        result: MongoDocument = {}
        for key, item in cast(Mapping[Any, Any], value).items():
            if not isinstance(key, str) or "\0" in key:
                raise TypeError(f"{name} document keys must be strings without NUL characters.")
            result[key] = _prepare_bson_value(item, name=name)
        return result
    if isinstance(value, Collection) and not isinstance(value, (str, bytes, bytearray, Mapping)):
        return [_prepare_bson_value(item, name=name) for item in cast(Collection[Any], value)]
    raise TypeError(f"{name} contains unsupported BSON value type '{type(cast(object, value)).__name__}'.")


def _prepare_dense_vector(value: Any, name: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"MongoDB vector '{name}' must be a dense numeric sequence.")
    vector: list[float] = []
    for item in cast(Sequence[Any], value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(f"MongoDB vector '{name}' must contain numbers, not booleans.")
        try:
            number = float(item)
        except OverflowError as exc:
            raise ValueError(f"MongoDB vector '{name}' must contain finite numbers.") from exc
        if not math.isfinite(number):
            raise ValueError(f"MongoDB vector '{name}' must contain finite numbers.")
        vector.append(number)
    return vector


def _prepare_data_value(field: VectorStoreField, value: Any) -> Any:
    if value is None:
        return None
    kind = field.type_
    name = f"MongoDB field '{field.name}'"
    if kind == "str":
        if not isinstance(value, str):
            raise TypeError(f"{name} must contain a string.")
        return value
    if kind == "int":
        return _prepare_int64(value, name)
    if kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must contain a number, not a boolean.")
        try:
            number = float(value)
        except OverflowError as exc:
            raise ValueError(f"{name} must contain a finite number.") from exc
        if not math.isfinite(number):
            raise ValueError(f"{name} must contain a finite number.")
        return number
    if kind == "bool":
        if not isinstance(value, bool):
            raise TypeError(f"{name} must contain a boolean.")
        return value
    if kind in _LIST_TYPES:
        if not isinstance(value, Collection) or isinstance(value, (str, bytes, bytearray, Mapping)):
            raise TypeError(f"{name} must contain a collection.")
        return _prepare_bson_value(value, name=name)
    if kind == "dict":
        if not isinstance(value, Mapping):
            raise TypeError(f"{name} must contain a mapping.")
        return _prepare_bson_value(value, name=name)
    if kind == "bytes":
        if not isinstance(value, bytes):
            raise TypeError(f"{name} must contain bytes.")
        return value
    if kind == "ObjectId":
        if not isinstance(value, ObjectId):
            raise TypeError(f"{name} must contain a bson.ObjectId.")
        return value
    if kind == "datetime":
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, datetime):
            raise TypeError(f"{name} must contain a datetime.")
        return value
    return _prepare_bson_value(value, name=name)


def _validate_bson_document(document: MongoDocument, *, record_index: int) -> None:
    try:
        size = len(BSON.encode(document))
    except (InvalidDocument, OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"MongoDB record {record_index} cannot be represented as BSON: {exc}") from exc
    if size > _BSON_MAX_DOCUMENT_SIZE:
        raise ValueError(
            f"MongoDB record {record_index} encodes to {size} bytes and exceeds the 16 MiB BSON document limit."
        )


def _validate_bson_query_value(value: Any, *, name: str) -> Any:
    prepared = _prepare_bson_value(value, name=name)
    try:
        _validate_bson_document({"value": prepared}, record_index=0)
    except ValueError as exc:
        raise ValueError(f"{name} is not a valid MongoDB query value.") from exc
    return prepared


def _field_type_expression(name: str) -> MongoDocument:
    return {"$type": f"${name}"}


def _field_exists_expression(name: str) -> MongoDocument:
    return {"$ne": [_field_type_expression(name), "missing"]}


def _field_type_guard(field: VectorStoreField, name: str) -> MongoDocument:
    kind = field.type_
    if kind == "int":
        return {"$in": [_field_type_expression(name), ["int", "long"]]}
    if kind == "float":
        return {"$eq": [_field_type_expression(name), "double"]}
    if kind == "str":
        return {"$eq": [_field_type_expression(name), "string"]}
    if kind == "bool":
        return {"$eq": [_field_type_expression(name), "bool"]}
    if kind == "bytes":
        return {"$eq": [_field_type_expression(name), "binData"]}
    if kind == "ObjectId":
        return {"$eq": [_field_type_expression(name), "objectId"]}
    if kind == "datetime":
        return {"$eq": [_field_type_expression(name), "date"]}
    if kind == "list":
        return {"$isArray": f"${name}"}
    if kind in _LIST_TYPES:
        raise NotImplementedError(
            f"MongoDB filters require field '{field.name}' to use declared type 'list'; "
            f"'{kind}' loses container identity in BSON."
        )
    if kind == "dict":
        return {"$eq": [_field_type_expression(name), "object"]}
    raise NotImplementedError(f"MongoDB filters require a supported declared type for field '{field.name}'.")


def _literal(value: Any) -> MongoDocument:
    return {"$literal": value}


def _value_matches_field_type(field: VectorStoreField, value: Any) -> bool:
    if value is None:
        return True
    kind = field.type_
    if kind == "str":
        return isinstance(value, str)
    if kind == "int":
        if isinstance(value, int) and not isinstance(value, bool):
            return True
        return isinstance(value, float) and math.isfinite(value) and value.is_integer()
    if kind == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "bytes":
        return isinstance(value, bytes)
    if kind == "ObjectId":
        return isinstance(value, ObjectId)
    if kind == "datetime":
        return isinstance(value, datetime)
    if kind == "list":
        return isinstance(value, list)
    if kind == "dict":
        return isinstance(value, Mapping)
    return False


def _prepare_filter_operand(field: VectorStoreField, value: Any) -> Any:
    prepared = _validate_bson_query_value(value, name=f"Filter value for '{field.name}'")
    if field.type_ == "int" and isinstance(prepared, float):
        if not prepared.is_integer():
            raise TypeError(f"Filter value for integer field '{field.name}' must be an integer.")
        integer = int(prepared)
        if not _BSON_INT64_MIN <= integer <= _BSON_INT64_MAX:
            raise ValueError(f"Filter value for integer field '{field.name}' exceeds signed 64-bit range.")
        return integer
    return prepared


def _prepare_collection_filter_operand(value: Any, *, field_name: str) -> Any:
    if isinstance(value, Mapping):
        raise NotImplementedError(
            f"MongoDB collection filters do not support mapping operands for field '{field_name}' "
            "because BSON document equality is key-order-sensitive."
        )
    if isinstance(value, list):
        return [_prepare_collection_filter_operand(item, field_name=field_name) for item in cast(list[Any], value)]
    if isinstance(value, Collection) and not isinstance(value, (str, bytes, bytearray)):
        raise NotImplementedError(
            f"MongoDB collection filters support only scalar and nested-list operands for field '{field_name}'."
        )
    return _validate_bson_query_value(value, name=f"Filter value for '{field_name}'")


def _prepare_filter_field(
    definition: VectorStoreCollectionDefinition,
    field_name: str,
) -> tuple[VectorStoreField, str]:
    if "." in field_name:
        raise NotImplementedError("MongoDB portable filters support declared top-level fields only.")
    field = definition.try_get_field(field_name)
    if field is None:
        raise ValueError(f"Unknown MongoDB filter field '{field_name}'.")
    if field.field_type == "vector":
        raise NotImplementedError("MongoDB portable filters do not operate on vector fields.")
    return field, "_id" if field.field_type == "key" else field.storage_name or field.name


def _prepare_retrieval_filter_condition(
    expression: Filter,
    definition: VectorStoreCollectionDefinition,
) -> MongoDocument:
    field, name = _prepare_filter_field(definition, expression.field_name)
    operator, value = expression.operator, expression.value
    exists = _field_exists_expression(name)
    actual = f"${name}"

    if operator == "exists":
        return exists
    if operator == "is_null":
        return {"$and": [exists, {"$eq": [actual, None]}]}
    if operator == "is_not_null":
        return {"$and": [exists, {"$ne": [actual, None]}]}

    type_guard = _field_type_guard(field, name)
    if operator in {"eq", "ne"}:
        if value is None:
            equality: MongoDocument = {"$and": [exists, {"$eq": [actual, None]}]}
        elif not _value_matches_field_type(field, value):
            if (
                field.type_ == "list"
                and isinstance(value, Collection)
                and not isinstance(value, (str, bytes, bytearray))
            ):
                _prepare_collection_filter_operand(value, field_name=field.name)
            equality = _FALSE_EXPRESSION
        elif field.type_ == "dict":
            raise NotImplementedError("MongoDB mapping equality does not match portable mapping semantics.")
        else:
            prepared = (
                _prepare_collection_filter_operand(value, field_name=field.name)
                if field.type_ == "list"
                else _prepare_filter_operand(field, value)
            )
            equality = {"$and": [type_guard, {"$eq": [actual, _literal(prepared)]}]}
        return equality if operator == "eq" else {"$and": [exists, {"$not": [equality]}]}

    if operator in {"in", "not_in"}:
        if field.type_ == "dict":
            raise NotImplementedError("MongoDB mapping membership does not match portable mapping semantics.")
        prepared_values: list[Any] = []
        for item in cast(Collection[Any], value):
            if item is None:
                continue
            if field.type_ == "list" and isinstance(item, Collection) and not isinstance(item, (str, bytes, bytearray)):
                prepared_item = _prepare_collection_filter_operand(item, field_name=field.name)
            elif _value_matches_field_type(field, item):
                prepared_item = _prepare_filter_operand(field, item)
            else:
                continue
            if _value_matches_field_type(field, item):
                prepared_values.append(prepared_item)
        membership: MongoDocument = {
            "$and": [
                type_guard,
                {"$in": [actual, _literal(prepared_values)]},
            ]
        }
        return membership if operator == "in" else {"$and": [type_guard, {"$not": [membership]}]}

    if operator in {"gt", "gte", "lt", "lte", "between"}:
        if field.type_ not in {"str", "int", "float", "datetime"}:
            raise NotImplementedError(f"MongoDB ordered filters do not support declared type '{field.type_}'.")
        operands = cast(Sequence[Any], value) if operator == "between" else [value]
        if any(item is None or not _value_matches_field_type(field, item) for item in operands):
            raise TypeError(f"MongoDB ordered filter operands must match field '{field.name}'.")
        prepared = [_prepare_filter_operand(field, item) for item in operands]
        comparison = (
            {
                "$and": [
                    {"$gte": [actual, _literal(prepared[0])]},
                    {"$lte": [actual, _literal(prepared[1])]},
                ]
            }
            if operator == "between"
            else {f"${operator}": [actual, _literal(prepared[0])]}
        )
        return {"$and": [type_guard, comparison]}

    if operator in {"starts_with", "ends_with", "contains_text"}:
        if field.type_ != "str":
            raise TypeError("MongoDB literal text filters require a declared scalar string field.")
        if not isinstance(value, str):
            raise TypeError("MongoDB literal text filters require a string operand.")
        escaped = re.escape(value)
        pattern = f"^{escaped}" if operator == "starts_with" else f"{escaped}$" if operator == "ends_with" else escaped
        return {
            "$cond": [
                type_guard,
                {"$regexMatch": {"input": actual, "regex": Regex(pattern)}},
                False,
            ]
        }

    if operator in {"contains", "contains_any", "contains_all"}:
        if field.type_ != "list":
            raise TypeError("MongoDB collection filters require a field declared as list.")
        operands = [value] if operator == "contains" else list(cast(Collection[Any], value))
        prepared = [_prepare_collection_filter_operand(item, field_name=field.name) for item in operands]
        if operator == "contains_all":
            predicate: MongoDocument = {"$setIsSubset": [_literal(prepared), actual]}
        else:
            predicate = {
                "$anyElementTrue": {
                    "$map": {
                        "input": actual,
                        "as": "item",
                        "in": {"$in": ["$$item", _literal(prepared)]},
                    }
                }
            }
        return {"$cond": [type_guard, predicate, False]}

    raise NotImplementedError(f"Unsupported MongoDB portable filter operator '{operator}'.")


def _prepare_vector_filter_condition(
    expression: FilterExpression,
    definition: VectorStoreCollectionDefinition,
) -> MongoDocument:
    if isinstance(expression, FilterGroup):
        if expression.operator == "not":
            raise NotImplementedError("MongoDB vector prefilters do not support portable NOT semantics.")
        operator = "$and" if expression.operator == "and" else "$or"
        return {operator: [_prepare_vector_filter_condition(item, definition) for item in expression.filters]}

    field, name = _prepare_filter_field(definition, expression.field_name)
    if field.field_type == "data" and not field.is_indexed:
        raise NotImplementedError(f"MongoDB vector prefilter field '{field.name}' must declare is_indexed=True.")
    if field.type_ not in _VECTOR_FILTER_TYPES:
        raise NotImplementedError(f"MongoDB vector prefilters do not support declared type '{field.type_}'.")
    operator, value = expression.operator, expression.value
    if operator not in {"eq", "gt", "gte", "lt", "lte", "between", "in"}:
        raise NotImplementedError(
            f"MongoDB vector prefilters do not faithfully support portable operator '{operator}'."
        )
    if operator == "eq":
        if value is None:
            raise NotImplementedError("MongoDB vector prefilters do not index null values.")
        prepared = _prepare_filter_operand(field, value)
        return {name: {"$eq": prepared}} if _value_matches_field_type(field, value) else {"_id": {"$in": []}}
    if operator == "in":
        values = list(cast(Collection[Any], value))
        if any(item is None for item in values):
            raise NotImplementedError("MongoDB vector prefilters do not index null values.")
        prepared = [_prepare_filter_operand(field, item) for item in values if _value_matches_field_type(field, item)]
        return {name: {"$in": prepared}}
    operands = cast(Sequence[Any], value) if operator == "between" else [value]
    if any(item is None or not _value_matches_field_type(field, item) for item in operands):
        raise TypeError(f"MongoDB ordered vector prefilter operands must match field '{field.name}'.")
    prepared = [_prepare_filter_operand(field, item) for item in operands]
    condition = {"$gte": prepared[0], "$lte": prepared[1]} if operator == "between" else {f"${operator}": prepared[0]}
    return {name: condition}


def _prepare_filter_expression(
    expression: FilterExpression,
    definition: VectorStoreCollectionDefinition,
) -> MongoDocument:
    if isinstance(expression, FilterGroup):
        children = [_prepare_filter_expression(item, definition) for item in expression.filters]
        if expression.operator == "not":
            return {"$not": [children[0]]}
        return {("$and" if expression.operator == "and" else "$or"): children}
    return _prepare_retrieval_filter_condition(expression, definition)


def _default_index_name(collection_name: str, field_name: str) -> str:
    digest = hashlib.sha256(f"{collection_name}\0{field_name}".encode()).hexdigest()[:12]
    readable = re.sub(r"[^A-Za-z0-9_-]", "_", field_name)[:32] or "vector"
    return f"af_{readable}_{digest}"


def _semantic_index_definition(definition: Mapping[str, Any]) -> tuple[tuple[tuple[str, Any], ...], ...]:
    fields = definition.get("fields")
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes, bytearray)):
        raise ValueError("MongoDB vector search index definition must contain a fields array.")
    normalized: list[tuple[tuple[str, Any], ...]] = []
    for raw_field in cast(Sequence[Any], fields):
        if not isinstance(raw_field, Mapping):
            raise ValueError("MongoDB vector search index fields must be documents.")
        field = cast(Mapping[str, Any], raw_field)
        kind = field.get("type")
        path = field.get("path")
        if kind == "filter":
            normalized.append((("path", path), ("type", kind)))
        elif kind == "vector":
            semantic: list[tuple[str, Any]] = [
                ("numDimensions", field.get("numDimensions")),
                ("path", path),
                ("similarity", field.get("similarity")),
                ("type", kind),
            ]
            quantization = field.get("quantization")
            if quantization not in (None, "none"):
                semantic.append(("quantization", quantization))
            normalized.append(tuple(sorted(semantic)))
        else:
            normalized.append(tuple(sorted((str(key), value) for key, value in field.items())))
    return tuple(sorted(normalized, key=repr))


class MongoDBCollection(
    BaseVectorCollection[KeyT, ModelT],
    BaseVectorSearch[KeyT, ModelT],
    Generic[KeyT, ModelT],
):
    """Store BSON documents and search dense vectors with MongoDB Vector Search."""

    supported_key_types: ClassVar[set[str] | None] = {"str", "int", "ObjectId"}
    supported_vector_types: ClassVar[set[str] | None] = {"float", "float16", "float32", "float64"}
    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        uri: str | SecretString | None = None,
        database_name: str | None = None,
        app_name: str | None = None,
        async_client: MongoClient | None = None,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a MongoDB collection without performing network I/O.

        Args:
            record_type: Registered application model, or dict with an explicit definition.
            uri: MongoDB URI override; otherwise loaded from ``MONGODB_URI``.
            database_name: Database name, or ``MONGODB_DATABASE_NAME`` for a connector-created client.
            app_name: Optional driver app name, or ``MONGODB_APP_NAME``.
            async_client: Existing PyMongo async client. It bypasses settings and remains caller-owned.
            definition: Explicit dictionary schema.
            collection_name: Collection name, overriding the model definition.
            embedding_generator: Default local embedding client.
            env_file_path: Optional .env file selected explicitly.
            env_file_encoding: Encoding for the selected .env file.
        """
        super().__init__(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator,
            managed_client=async_client is None,
        )
        self._validate_unique_index_names()
        self.async_client, self._database, self.database_name, self._owns_client = _create_client(
            uri=uri,
            database_name=database_name,
            app_name=app_name,
            async_client=async_client,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        self._collection: MongoCollection = self._database.get_collection(self.collection_name)
        self._closed = False

    def _validate_data_model(self) -> None:
        super()._validate_data_model()
        key = self.definition.key_field
        if key.is_auto_generated and key.type_ != "ObjectId":
            raise NotImplementedError("MongoDB auto-generated keys require a bson.ObjectId key field.")
        for field in self.definition.fields:
            name = field.storage_name or field.name
            if not name or "\0" in name or "." in name or name.startswith("$") or name == _SCORE_FIELD:
                raise ValueError(
                    "MongoDB storage names must be top-level names without NUL, dots, '$' prefixes, or reserved names."
                )
            if field.field_type != "key" and name == "_id":
                raise ValueError("MongoDB reserves storage name '_id' for the key field.")
            annotations = field.provider_annotations
            unknown = annotations.keys() - ({"mongodb.index_name"} if field.field_type == "vector" else set())
            if unknown:
                raise NotImplementedError(f"Unsupported MongoDB field annotation(s): {', '.join(sorted(unknown))}.")
            if field.field_type == "vector":
                if not isinstance(field.dimensions, int) or isinstance(field.dimensions, bool):
                    raise TypeError("MongoDB vector dimensions must be an integer.")
                if not 1 <= field.dimensions <= 8192:
                    raise ValueError("MongoDB vector dimensions must be between 1 and 8192.")
                if field.index_kind not in {"default", "hnsw"}:
                    raise NotImplementedError(f"MongoDB vector index kind '{field.index_kind}' is not supported.")
                if field.distance_function not in _DISTANCES:
                    raise NotImplementedError(
                        f"MongoDB distance function '{field.distance_function}' is not supported."
                    )
                index_name = annotations.get("mongodb.index_name")
                if index_name is not None:
                    _validate_non_empty_string(index_name, "mongodb.index_name")
            elif field.field_type == "data":
                if field.is_full_text_indexed:
                    raise NotImplementedError(
                        "MongoDB Search text indexes and keyword-hybrid search are not supported."
                    )
                if field.is_indexed and field.type_ not in _VECTOR_FILTER_TYPES:
                    raise NotImplementedError(
                        f"MongoDB vector filter indexes do not support declared type '{field.type_}'."
                    )

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close a connector-owned client on context exit."""
        await self.close()

    async def close(self) -> None:
        """Close a connector-created client once, leaving injected clients open."""
        if self._owns_client and not self._closed:
            await self.async_client.close()
            self._closed = True

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Return whether the MongoDB collection exists."""
        _validate_operation_options(operation_options)
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return bool(await self._database.list_collection_names(filter={"name": self.collection_name}))

    def _index_name(self, field: VectorStoreField) -> str:
        configured = field.provider_annotations.get("mongodb.index_name")
        return (
            cast(str, configured)
            if configured is not None
            else _default_index_name(self.collection_name, field.storage_name or field.name)
        )

    def _validate_unique_index_names(self) -> None:
        names = [self._index_name(field) for field in self.definition.vector_fields]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"MongoDB vector index names must be unique: {', '.join(duplicates)}.")

    def _index_definition(self, field: VectorStoreField) -> MongoDocument:
        fields: list[MongoDocument] = [
            {
                "type": "vector",
                "path": field.storage_name or field.name,
                "numDimensions": field.dimensions,
                "similarity": _DISTANCES[cast(str, field.distance_function)],
            },
            {"type": "filter", "path": "_id"},
        ]
        fields.extend(
            {"type": "filter", "path": data_field.storage_name or data_field.name}
            for data_field in self.definition.data_fields
            if data_field.is_indexed
        )
        return {"fields": fields}

    async def _list_search_index(self, name: str) -> Mapping[str, Any] | None:
        cursor = await self._collection.list_search_indexes(name=name)
        indexes = [index async for index in cast(AsyncIterator[Mapping[str, Any]], cursor)]
        if len(indexes) > 1:
            raise IntegrationInvalidResponseException(
                f"MongoDB returned multiple vector search indexes named '{name}'."
            )
        return indexes[0] if indexes else None

    def _validate_search_index(
        self,
        field: VectorStoreField,
        index: Mapping[str, Any],
    ) -> bool:
        name = self._index_name(field)
        if index.get("name") != name or index.get("type") not in (None, "vectorSearch"):
            raise ValueError(f"Existing MongoDB search index '{name}' has an incompatible type.")
        definition = index.get("latestDefinition") or index.get("definition")
        if definition is None:
            return False
        if not isinstance(definition, Mapping) or _semantic_index_definition(
            cast(Mapping[str, Any], definition)
        ) != _semantic_index_definition(self._index_definition(field)):
            raise ValueError(f"Existing MongoDB vector search index '{name}' does not match the model definition.")
        return True

    async def _wait_for_search_index(
        self,
        field: VectorStoreField,
        *,
        timeout: float,
        poll_interval: float,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        name = self._index_name(field)
        while True:
            index = await self._list_search_index(name)
            if index is not None:
                definition_available = self._validate_search_index(field, index)
                if definition_available and index.get("queryable") is True:
                    return
                status = str(index.get("status", "")).upper()
                if status in _INDEX_TERMINAL_FAILURES:
                    raise ValueError(f"MongoDB vector search index '{name}' entered terminal status '{status}'.")
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"MongoDB vector search index '{name}' was not queryable within {timeout} seconds.")
            await asyncio.sleep(min(poll_interval, remaining))

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create the collection and missing vector indexes, validating existing definitions without migration."""
        options = _validate_operation_options(
            operation_options,
            {"create_indexes", "index_timeout", "poll_interval"},
        )
        create_indexes = options.get("create_indexes", True)
        if not isinstance(create_indexes, bool):
            raise TypeError("create_indexes must be a boolean.")
        timeout = options.get("index_timeout", 120.0)
        poll_interval = options.get("poll_interval", 0.5)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("index_timeout must be a positive finite number.")
        if (
            isinstance(poll_interval, bool)
            or not isinstance(poll_interval, (int, float))
            or not math.isfinite(poll_interval)
            or poll_interval <= 0
        ):
            raise ValueError("poll_interval must be a positive finite number.")
        if not await self.collection_exists():
            try:
                await self._database.create_collection(self.collection_name, check_exists=False)
            except (CollectionInvalid, OperationFailure):
                if not await self.collection_exists():
                    raise
        if not create_indexes:
            return
        for field in self.definition.vector_fields:
            name = self._index_name(field)
            existing = await self._list_search_index(name)
            if existing is None:
                model = SearchIndexModel(
                    definition=self._index_definition(field),
                    name=name,
                    type="vectorSearch",
                )
                try:
                    await self._collection.create_search_index(model=model)
                except OperationFailure:
                    existing = await self._list_search_index(name)
                    if existing is None:
                        raise
            if existing is not None:
                self._validate_search_index(field, existing)
            await self._wait_for_search_index(
                field,
                timeout=float(timeout),
                poll_interval=float(poll_interval),
            )

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Drop this collection if it exists."""
        _validate_operation_options(operation_options)
        if await self.collection_exists():
            await self._database.drop_collection(self.collection_name)

    @staticmethod
    def _to_builtin_mapping(record: Any) -> Mapping[str, Any]:
        if isinstance(record, Mapping):
            return dict(cast(Mapping[str, Any], record))
        raise TypeError("MongoDB vector records must serialize to mappings.")

    def _serialize_dicts_to_store_models(
        self,
        records: Sequence[dict[str, Any]],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[MongoDocument]:
        del context
        documents: list[MongoDocument] = []
        key_storage_name = self.definition.key_field_storage_name
        for index, record in enumerate(records):
            document: MongoDocument = {}
            for field in self.definition.fields:
                storage_name = field.storage_name or field.name
                if field.field_type == "key":
                    value = record.get(storage_name)
                    if value is None and field.is_auto_generated:
                        value = ObjectId()
                    document["_id"] = _prepare_key(value, field.type_)
                elif field.field_type == "vector":
                    value = record[storage_name]
                    document[storage_name] = None if value is None else _prepare_dense_vector(value, field.name)
                else:
                    document[storage_name] = _prepare_data_value(field, record[storage_name])
            if key_storage_name != "_id":
                document.pop(key_storage_name, None)
            _validate_bson_document(document, record_index=index)
            documents.append(document)
        return documents

    def _deserialize_store_models_to_dicts(
        self,
        records: Sequence[Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[dict[str, Any]]:
        del context
        result: list[dict[str, Any]] = []
        key_name = self.definition.key_field_storage_name
        for raw_record in records:
            if not isinstance(raw_record, Mapping):
                raise TypeError("MongoDB responses must contain BSON documents.")
            record = dict(cast(Mapping[str, Any], raw_record))
            if "_id" not in record:
                raise IntegrationInvalidResponseException("MongoDB response is missing the '_id' field.")
            record[key_name] = record.pop("_id")
            result.append(record)
        return result

    def _prepare_filter(self, filter: FilterExpression | None) -> MongoDocument:
        if filter is None:
            return {}
        return {"$expr": _prepare_filter_expression(filter, self.definition)}

    def _prepare_vector_filter(self, filter: FilterExpression | None) -> MongoDocument | None:
        if filter is None:
            return None
        return _prepare_vector_filter_condition(filter, self.definition)

    def _prepare_projection(self, include_vectors: bool) -> MongoDocument | None:
        if include_vectors:
            return None
        return {field.storage_name or field.name: 0 for field in self.definition.vector_fields}

    def _prepare_order_by(self, order_by: Mapping[str, bool] | None) -> list[tuple[str, int]]:
        result: list[tuple[str, int]] = []
        for name, ascending in (order_by or {}).items():
            if not isinstance(ascending, bool):
                raise TypeError("MongoDB order directions must be booleans.")
            field, storage_name = _prepare_filter_field(self.definition, name)
            if field.type_ not in _VECTOR_FILTER_TYPES:
                raise NotImplementedError(
                    f"MongoDB deterministic ordering does not support declared type '{field.type_}'."
                )
            result.append((storage_name, 1 if ascending else -1))
        if "_id" not in {name for name, _ in result}:
            result.append(("_id", 1))
        return result

    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[KeyT]:
        options = _validate_operation_options(operation_options, {"ordered", "bypass_document_validation"})
        ordered = options.get("ordered", True)
        bypass_document_validation = options.get("bypass_document_validation")
        if not isinstance(ordered, bool):
            raise TypeError("ordered must be a boolean.")
        if bypass_document_validation is not None and not isinstance(bypass_document_validation, bool):
            raise TypeError("bypass_document_validation must be a boolean or None.")
        documents: list[MongoDocument] = []
        keys: list[KeyT] = []
        for index, raw_record in enumerate(records):
            if not isinstance(raw_record, Mapping):
                raise TypeError("MongoDB upsert records must be BSON documents.")
            document = dict(cast(Mapping[str, Any], raw_record))
            _validate_bson_document(document, record_index=index)
            key = _prepare_key(document.get("_id"), self.definition.key_field.type_)
            document["_id"] = key
            documents.append(document)
            keys.append(cast(KeyT, key))
        if not ordered and len(keys) != len(set(keys)):
            raise ValueError("MongoDB unordered upserts do not support duplicate keys in one batch.")
        if not documents:
            return []
        requests = [
            ReplaceOne({"_id": key}, document, upsert=True) for key, document in zip(keys, documents, strict=True)
        ]
        await self._collection.bulk_write(
            requests,
            ordered=ordered,
            bypass_document_validation=bypass_document_validation,
        )
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
    ) -> Sequence[MongoDocument]:
        _validate_operation_options(operation_options)
        projection = self._prepare_projection(include_vectors)
        if keys is not None:
            if order_by:
                raise ValueError("order_by applies only to filtered retrieval, not key lookup.")
            if skip:
                raise ValueError("MongoDB key retrieval cannot be combined with skip.")
            prepared_keys = [_prepare_key(key, self.definition.key_field.type_) for key in keys]
            if not prepared_keys:
                return []
            cursor = self._collection.find({"_id": {"$in": prepared_keys}}, projection=projection)
            records = [record async for record in cursor]
            by_key = {record["_id"]: record for record in records}
            return [by_key[key] for key in prepared_keys if key in by_key]
        native_filter = self._prepare_filter(filter)
        sort = self._prepare_order_by(order_by)
        if top == 0:
            return []
        cursor = self._collection.find(native_filter, projection=projection).sort(sort).skip(skip).limit(top)
        return [record async for record in cursor]

    async def _inner_delete(
        self,
        keys: Sequence[KeyT],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        _validate_operation_options(operation_options)
        prepared_keys = [_prepare_key(key, self.definition.key_field.type_) for key in keys]
        if prepared_keys:
            await self._collection.delete_many({"_id": {"$in": prepared_keys}})

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
    ) -> SearchResults[MongoDocument]:
        del values
        options = _validate_operation_options(operation_options, {"exact", "num_candidates"})
        if search_type != "vector" or additional_property_name is not None:
            raise NotImplementedError("MongoDB keyword-hybrid search is not supported by this connector.")
        if vector is None:
            raise NotImplementedError(
                "MongoDB has no configured server-side vectorization; supply a vector or embedding generator."
            )
        field = self.definition.try_get_vector_field(vector_property_name)
        if field is None:
            raise ValueError("Select a vector_property_name from the MongoDB collection definition.")
        exact = options.get("exact", False)
        if not isinstance(exact, bool):
            raise TypeError("exact must be a boolean.")
        window = _prepare_int64(skip + top, "MongoDB vector search skip + top")
        has_explicit_num_candidates = "num_candidates" in options
        explicit_num_candidates = options.get("num_candidates")
        if exact and has_explicit_num_candidates:
            raise ValueError("num_candidates cannot be supplied when exact=True.")
        if not exact and window > _MAX_NUM_CANDIDATES:
            raise ValueError(
                "MongoDB ANN search requires skip + top to be at most 10000; use exact=True for a larger window."
            )
        if has_explicit_num_candidates:
            num_candidates = _prepare_int64(explicit_num_candidates, "num_candidates")
            if not 1 <= num_candidates <= _MAX_NUM_CANDIDATES:
                raise ValueError("num_candidates must be between 1 and 10000.")
            if num_candidates < window:
                raise ValueError("num_candidates must be greater than or equal to skip + top.")
        else:
            num_candidates = None if exact else min(20 * window, _MAX_NUM_CANDIDATES)
        if score_threshold is not None:
            if (
                isinstance(score_threshold, bool)
                or not isinstance(score_threshold, (int, float))
                or not math.isfinite(score_threshold)
                or not 0 <= score_threshold <= 1
            ):
                raise ValueError("MongoDB score_threshold must be a finite number between 0 and 1.")
            score_threshold = float(score_threshold)
        query = _prepare_dense_vector(vector, field.name)
        native_filter = self._prepare_vector_filter(filter)
        if top == 0:
            return SearchResults([])
        search: MongoDocument = {
            "index": self._index_name(field),
            "path": field.storage_name or field.name,
            "queryVector": query,
            "limit": window,
        }
        if exact:
            search["exact"] = True
        else:
            search["numCandidates"] = num_candidates
        if native_filter is not None:
            search["filter"] = native_filter
        pipeline: list[MongoDocument] = [
            {"$vectorSearch": search},
            {"$set": {_SCORE_FIELD: {"$meta": "vectorSearchScore"}}},
        ]
        if score_threshold is not None:
            pipeline.append({"$match": {_SCORE_FIELD: {"$gte": score_threshold}}})
        if skip:
            pipeline.append({"$skip": skip})
        pipeline.append({"$limit": top})
        projection = self._prepare_projection(include_vectors)
        if projection:
            pipeline.append({"$project": projection})
        cursor = await self._collection.aggregate(pipeline)
        return SearchResults([record async for record in cursor])

    def _get_record_from_result(self, result: Any) -> MongoDocument:
        if not isinstance(result, Mapping):
            raise IntegrationInvalidResponseException("Expected a MongoDB BSON search result.")
        return dict(cast(Mapping[str, Any], result))

    def _get_score_from_result(self, result: Any) -> float:
        record = self._get_record_from_result(result)
        score = record.get(_SCORE_FIELD)
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise IntegrationInvalidResponseException("MongoDB search result is missing a finite vectorSearchScore.")
        return float(score)


class MongoDBStore(BaseVectorStore):
    """Create MongoDB collection clients sharing one official async PyMongo client."""

    def __init__(
        self,
        *,
        uri: str | SecretString | None = None,
        database_name: str | None = None,
        app_name: str | None = None,
        async_client: MongoClient | None = None,
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a MongoDB vector store.

        Args:
            uri: MongoDB URI override; otherwise loaded from ``MONGODB_URI``.
            database_name: Database name, or ``MONGODB_DATABASE_NAME`` for a connector-created client.
            app_name: Optional driver app name, or ``MONGODB_APP_NAME``.
            async_client: Existing PyMongo async client. It bypasses settings and remains caller-owned.
            embedding_generator: Default embedding client inherited by collections.
            env_file_path: Optional .env file selected explicitly.
            env_file_encoding: Encoding for the selected .env file.
        """
        client, database, resolved_database_name, owns_client = _create_client(
            uri=uri,
            database_name=database_name,
            app_name=app_name,
            async_client=async_client,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        super().__init__(embedding_generator=embedding_generator, managed_client=owns_client)
        self.async_client = client
        self._database = database
        self.database_name = resolved_database_name
        self._owns_client = owns_client
        self._closed = False

    def get_collection(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> MongoDBCollection[Any, ModelT]:
        """Create a collection that borrows this store's resolved client and database."""
        return MongoDBCollection(
            record_type,
            async_client=self.async_client,
            database_name=self.database_name,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator if embedding_generator is not None else self.embedding_generator,
        )

    async def list_collection_names(self, *, operation_options: Mapping[str, Any] | None = None) -> Sequence[str]:
        """List MongoDB collection names in the configured database."""
        _validate_operation_options(operation_options)
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return await self._database.list_collection_names()

    async def collection_exists(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        """Check collection existence without downloading the complete collection list."""
        _validate_operation_options(operation_options)
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return bool(await self._database.list_collection_names(filter={"name": collection_name}))

    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        _validate_operation_options(operation_options)
        await self._database.drop_collection(collection_name)

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close a connector-owned client on context exit."""
        await self.close()

    async def close(self) -> None:
        """Close a connector-created client once, leaving injected clients open."""
        if self._owns_client and not self._closed:
            await self.async_client.close()
            self._closed = True
