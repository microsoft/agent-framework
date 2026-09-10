# Copyright (c) Microsoft. All rights reserved.

"""Async Qdrant dense-vector collections and stores."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Generic, cast
from uuid import UUID

from agent_framework import (
    BaseVectorCollection,
    BaseVectorSearch,
    BaseVectorStore,
    Filter,
    FilterGroup,
    SearchResults,
    SearchType,
    SecretString,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    load_settings,
)
from agent_framework._telemetry import FeatureIndex, mark_feature_used
from agent_framework._vector_filters import FilterExpression
from agent_framework._vectors import EmbeddingClient, Vector
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException
from grpc import StatusCode
from grpc.aio import AioRpcError
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from typing_extensions import TypedDict, TypeVar

KeyT = TypeVar("KeyT", default=Any)
ModelT = TypeVar("ModelT", default=Any)


class QdrantSettings(TypedDict, total=False):
    """Connection settings loaded through Agent Framework's ``load_settings``.

    Explicit constructor arguments take precedence over an explicitly selected
    ``.env`` file, then environment variables prefixed with ``QDRANT_``.

    Keys:
        url: Server URL from ``QDRANT_URL``. When unset, the SDK defaults to localhost.
        api_key: Optional API key from ``QDRANT_API_KEY``, stored as an AF ``SecretString``.
    """

    url: str | None
    api_key: SecretString | None


def _create_client(
    *,
    url: str | None,
    api_key: str | SecretString | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> AsyncQdrantClient:
    settings = load_settings(
        QdrantSettings,
        env_prefix="QDRANT_",
        url=url,
        api_key=api_key,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    resolved_api_key = settings.get("api_key")
    return AsyncQdrantClient(
        url=settings.get("url"),
        api_key=resolved_api_key.get_secret_value() if resolved_api_key is not None else None,
    )


_DISTANCES = {
    "DEFAULT": models.Distance.COSINE,
    "cosine_similarity": models.Distance.COSINE,
    "dot_prod": models.Distance.DOT,
    "euclidean_distance": models.Distance.EUCLID,
    "manhattan": models.Distance.MANHATTAN,
}
_PAYLOAD_INDEXES = {
    "str": models.PayloadSchemaType.KEYWORD,
    "int": models.PayloadSchemaType.INTEGER,
    "float": models.PayloadSchemaType.FLOAT,
    "bool": models.PayloadSchemaType.BOOL,
}
_READ_OPTIONS = {"consistency", "shard_key_selector", "timeout"}
_WRITE_OPTIONS = {"ordering", "shard_key_selector", "timeout"}
_BATCH_SIZE = 256
_MAX_EXACT_INTEGER = 2**53 - 1
_CREATE_OPTIONS = {
    "shard_number",
    "replication_factor",
    "write_consistency_factor",
    "on_disk_payload",
    "optimizers_config",
    "wal_config",
    "timeout",
}


def _validate_operation_options(options: Mapping[str, Any] | None, allowed: set[str]) -> dict[str, Any]:
    result = dict(options or {})
    unknown = result.keys() - allowed
    if unknown:
        raise ValueError(f"Unsupported Qdrant operation option(s): {', '.join(sorted(unknown))}.")
    return result


def _prepare_point_id(value: Any) -> int | str:
    """Validate and canonicalize a Qdrant point ID without hashing or coercing numbers."""
    if isinstance(value, int) and not isinstance(value, bool):
        if 0 <= value <= 2**64 - 1:
            return value
        raise ValueError("Qdrant integer keys must be unsigned 64-bit integers.")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        try:
            return str(UUID(value))
        except ValueError as exc:
            raise ValueError("Qdrant string keys must be UUIDs; arbitrary strings are not supported.") from exc
    raise TypeError("Qdrant keys must be unsigned 64-bit integers or UUIDs, not booleans.")


def _prepare_dense_vector(value: Any, name: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(
            f"Qdrant vector '{name}' must be a dense numeric sequence; sparse and binary vectors are unsupported."
        )
    result: list[float] = []
    for item in cast(Sequence[Any], value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(f"Qdrant vector '{name}' must contain numbers, not booleans.")
        try:
            number = float(item)
        except OverflowError as exc:
            raise ValueError(f"Qdrant vector '{name}' must contain finite float32 values.") from exc
        if not math.isfinite(number) or abs(number) > 3.4028234663852886e38:
            raise ValueError(f"Qdrant vector '{name}' must contain finite float32 values.")
        result.append(number)
    return result


def _prepare_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if not -(2**63) <= value < 2**63:
            raise ValueError("Qdrant integer payloads must be signed 64-bit integers.")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Qdrant payload numbers must be finite.")
        return value
    if isinstance(value, (list, tuple)):
        return [_prepare_payload(item) for item in cast(Sequence[Any], value)]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in cast(dict[Any, Any], value).items():
            if not isinstance(key, str):
                raise TypeError("Qdrant payload object keys must be strings.")
            result[key] = _prepare_payload(item)
        return result
    raise TypeError(f"Qdrant payloads must be JSON-compatible, not {type(value).__name__}.")


def _prepare_field_payload(field: VectorStoreField, value: Any) -> Any:
    value = _prepare_payload(value)
    if value is None or field.type_ is None:
        return value
    types: dict[str, tuple[type[Any], ...]] = {
        "str": (str,),
        "int": (int,),
        "float": (int, float),
        "bool": (bool,),
        "list": (list,),
        "tuple": (list,),
        "set": (list,),
        "Sequence": (list,),
        "dict": (dict,),
    }
    expected = types.get(field.type_)
    if expected is None:
        raise NotImplementedError(f"Qdrant payload field type '{field.type_}' is not supported.")
    if not isinstance(value, expected) or (field.type_ in {"int", "float"} and isinstance(value, bool)):
        raise TypeError(f"Qdrant payload field '{field.name}' must have declared type '{field.type_}'.")
    return value


def _prepare_payload_index(field: VectorStoreField) -> models.PayloadSchemaType | None:
    configured = field.provider_annotations.get("qdrant.payload_index")
    if configured is not None:
        schema = models.PayloadSchemaType(configured)
        if schema not in _PAYLOAD_INDEXES.values():
            raise NotImplementedError("Qdrant supports keyword, integer, float and bool payload indexes here.")
        if field.is_indexed is False:
            raise ValueError("qdrant.payload_index cannot be combined with is_indexed=False.")
        expected = _PAYLOAD_INDEXES.get(field.type_ or "")
        if expected is not None and schema != expected:
            raise ValueError(f"Qdrant payload index for '{field.name}' must match its declared type.")
        return schema
    if field.is_indexed:
        if field.type_ not in _PAYLOAD_INDEXES:
            raise ValueError(
                f"Indexed field '{field.name}' requires a scalar type or a qdrant.payload_index annotation."
            )
        return _PAYLOAD_INDEXES[field.type_]
    return None


def _validate_update_result(result: models.UpdateResult) -> None:
    if result.status != models.UpdateStatus.COMPLETED:
        raise IntegrationInvalidResponseException(f"Qdrant write did not complete: {result.status}.")


def _prepare_false_condition() -> models.HasIdCondition:
    return models.HasIdCondition(has_id=[])


def _prepare_presence_condition(name: str) -> models.FieldCondition:
    # Unlike is_empty, the server's values_count distinguishes missing from null and [].
    return models.FieldCondition(key=name, values_count=models.ValuesCount(gte=0))


def _prepare_null_condition(name: str) -> models.IsNullCondition:
    return models.IsNullCondition(is_null=models.PayloadField(key=name))


def _prepare_non_null_condition(name: str) -> models.Filter:
    return models.Filter(must=[_prepare_presence_condition(name)], must_not=[_prepare_null_condition(name)])


def _prepare_range_operand(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Qdrant ordered filters require numeric operands, not booleans.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Qdrant numeric filter operands must be finite.")
    if abs(value) > _MAX_EXACT_INTEGER:
        raise ValueError("Qdrant numeric range operands must be within +/- (2**53-1) to compare integers exactly.")
    return float(value)


def _prepare_equality_condition(
    name: str,
    value: Any,
    field: VectorStoreField,
    *,
    element: bool = False,
) -> models.Condition:
    if value is None:
        if element:
            raise NotImplementedError("Qdrant collection membership with a null operand is not supported.")
        return _prepare_null_condition(name)
    if not isinstance(value, (str, bool, int, float)):
        raise NotImplementedError("Qdrant equality and membership operands must be JSON scalars.")
    kind = field.type_
    if not element:
        if kind not in {"str", "bool", "int", "float"}:
            raise NotImplementedError(
                f"Qdrant scalar equality requires a str, bool, int or float field type; '{field.name}' has {kind!r}."
            )
        if isinstance(value, bool):
            if kind != "bool":
                return _prepare_false_condition()
        elif isinstance(value, str):
            if kind != "str":
                return _prepare_false_condition()
        elif kind not in {"int", "float"}:
            return _prepare_false_condition()
    if isinstance(value, (str, bool)):
        return models.FieldCondition(key=name, match=models.MatchValue(value=value))
    if kind == "int" and not element:
        if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
            return _prepare_false_condition()
        integer = int(value)
        if not -(2**63) <= integer < 2**63:
            return _prepare_false_condition()
        return models.FieldCondition(key=name, match=models.MatchValue(value=integer))
    number = _prepare_range_operand(value)
    # Range also matches equal integer/float values, but never bools on the server.
    return models.FieldCondition(key=name, range=models.Range(gte=number, lte=number))


def _prepare_key_filter_id(value: Any, kind: str | None) -> int | str | None:
    if isinstance(value, bool):
        return None
    if kind in {None, "int"} and isinstance(value, (int, float)):
        if isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                return None
            value = int(value)
        return value if 0 <= value <= 2**64 - 1 else None
    if kind in {None, "str", "UUID"} and isinstance(value, (str, UUID)):
        try:
            return _prepare_point_id(value)
        except ValueError:
            return None
    return None


def _prepare_key_filter_condition(expression: Filter, field: VectorStoreField) -> models.Condition:
    operator, value = expression.operator, expression.value
    if operator in {"exists", "is_not_null"}:
        return models.Filter(must_not=[_prepare_false_condition()])
    if operator == "is_null" or (operator == "eq" and value is None):
        return _prepare_false_condition()
    if operator == "ne" and value is None:
        return models.Filter(must_not=[_prepare_false_condition()])
    if operator in {"eq", "ne"}:
        key = _prepare_key_filter_id(value, field.type_)
        condition = models.HasIdCondition(has_id=[] if key is None else [key])
    elif operator in {"in", "not_in"}:
        condition = models.HasIdCondition(
            has_id=[key for item in value if (key := _prepare_key_filter_id(item, field.type_)) is not None]
        )
    else:
        raise NotImplementedError(f"Qdrant key filters do not support '{operator}'.")
    return models.Filter(must_not=[condition]) if operator in {"ne", "not_in"} else condition


class QdrantCollection(BaseVectorCollection[KeyT, ModelT], BaseVectorSearch[KeyT, ModelT], Generic[KeyT, ModelT]):
    """Store and search records with the official async Qdrant client.

    All dense fields are named vectors. The default metric is cosine similarity
    (larger is better), not cosine distance. Scores and thresholds retain native
    Qdrant units. Supplied clients remain caller-owned unless explicitly managed.

    Portable filters require a server: Qdrant's local emulator has different
    null/missing and numeric matching behavior across supported SDK versions.
    Local mode supports unfiltered CRUD and dense search. Ordered retrieval is unsupported.
    """

    supported_key_types: ClassVar[set[str] | None] = {"int", "str", "UUID"}
    supported_vector_types: ClassVar[set[str] | None] = {"float", "float16", "float32", "float64"}
    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        async_client: AsyncQdrantClient | None = None,
        url: str | None = None,
        api_key: str | SecretString | None = None,
        managed_client: bool | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a collection.

        Args:
            record_type: Registered application model, or dict with an explicit definition.
            definition: Explicit dictionary schema.
            collection_name: Collection name, overriding the model name.
            embedding_generator: Default local embedding client.
            async_client: Existing async client, borrowed by default. Use this for local mode or advanced configuration.
            url: Server URL override; otherwise loaded from QdrantSettings, then the SDK defaults to localhost.
            api_key: API key override as a string or SecretString; otherwise loaded from QdrantSettings.
            managed_client: Whether to close the client. Defaults to True only for connector-created clients.
            env_file_path: Optional .env file to load before process environment variables.
            env_file_encoding: Encoding for the .env file; defaults to UTF-8.
        """
        if async_client is not None and any(
            value is not None for value in (url, api_key, env_file_path, env_file_encoding)
        ):
            raise ValueError("Pass async_client or connection settings, not both.")
        super().__init__(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator,
            managed_client=async_client is None if managed_client is None else managed_client,
        )
        self.async_client = (
            async_client
            if async_client is not None
            else _create_client(
                url=url,
                api_key=api_key,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        )
        self._closed = False

    @property
    def _is_local(self) -> bool:
        options = self.async_client.init_options
        return options.get("location") == ":memory:" or options.get("path") is not None

    def _validate_data_model(self) -> None:
        super()._validate_data_model()
        if self.definition.key_field.is_auto_generated:
            raise NotImplementedError("Qdrant requires application-provided point IDs; it does not generate keys.")
        for field in self.definition.fields:
            unknown = field.provider_annotations.keys() - {"qdrant.payload_index"}
            if unknown:
                raise NotImplementedError(f"Unsupported Qdrant field annotation(s): {', '.join(sorted(unknown))}.")
            if field.field_type == "vector":
                if not isinstance(field.dimensions, int) or isinstance(field.dimensions, bool):
                    raise TypeError("Qdrant vector dimensions must be an integer.")
                if field.distance_function not in _DISTANCES:
                    raise NotImplementedError(f"Qdrant distance function '{field.distance_function}' is not supported.")
                if field.index_kind not in {"default", "hnsw", "flat"}:
                    raise NotImplementedError(f"Qdrant index kind '{field.index_kind}' is not supported.")
                if field.provider_annotations:
                    raise ValueError("qdrant.payload_index applies only to data fields.")
            elif field.field_type == "data":
                name = field.storage_name or field.name
                if any(character in name for character in '.[]"\\') or not name:
                    raise ValueError("Qdrant payload storage names cannot contain JSON-path punctuation.")
                if field.is_full_text_indexed:
                    raise NotImplementedError("Qdrant full-text indexes are not part of this dense-vector connector.")
                _prepare_payload_index(field)
            elif field.provider_annotations:
                raise ValueError("qdrant.payload_index applies only to data fields.")

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Check whether this collection exists."""
        _validate_operation_options(operation_options, set())
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return await self.async_client.collection_exists(self.collection_name)

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create the collection and payload indexes, or validate an existing dense schema."""
        options = _validate_operation_options(operation_options, _CREATE_OPTIONS)
        if not await self.collection_exists():
            vectors = {
                field.storage_name or field.name: models.VectorParams(
                    size=cast(int, field.dimensions),
                    distance=_DISTANCES[cast(str, field.distance_function)],
                    hnsw_config=models.HnswConfigDiff(m=0) if field.index_kind == "flat" else None,
                )
                for field in self.definition.vector_fields
            }
            try:
                created = await self.async_client.create_collection(
                    collection_name=self.collection_name, vectors_config=vectors, **options
                )
            except UnexpectedResponse as exc:
                if exc.status_code != 409:
                    raise
            except AioRpcError as exc:
                if exc.code() != StatusCode.ALREADY_EXISTS:
                    raise
            except ValueError as exc:
                if not self._is_local or str(exc) != f"Collection {self.collection_name} already exists":
                    raise
            else:
                if not created and not await self.collection_exists():
                    raise IntegrationException(f"Qdrant did not create collection '{self.collection_name}'.")
        info = await self.async_client.get_collection(self.collection_name)
        configured = info.config.params.vectors
        if not isinstance(configured, dict):
            raise ValueError("QdrantCollection requires named vectors, not an unnamed-vector collection.")
        for field in self.definition.vector_fields:
            vector = configured.get(field.storage_name or field.name)
            if (
                vector is None
                or vector.size != field.dimensions
                or vector.distance != _DISTANCES[cast(str, field.distance_function)]
                or vector.multivector_config is not None
                or vector.datatype not in {None, models.Datatype.FLOAT32}
            ):
                raise ValueError(f"Existing Qdrant vector '{field.name}' does not match the collection definition.")
            index_m = info.config.hnsw_config.m
            if vector.hnsw_config is not None and vector.hnsw_config.m is not None:
                index_m = vector.hnsw_config.m
            if field.index_kind == "flat" and index_m != 0:
                raise ValueError(f"Existing Qdrant vector '{field.name}' does not use a flat index.")
            if field.index_kind == "hnsw" and index_m == 0:
                raise ValueError(f"Existing Qdrant vector '{field.name}' does not use an HNSW index.")
        for field in self.definition.data_fields:
            schema = _prepare_payload_index(field)
            if schema is not None:
                name = field.storage_name or field.name
                existing = info.payload_schema.get(name)
                if existing is not None and existing.data_type != schema:
                    raise ValueError(f"Existing Qdrant payload index '{name}' has a different type.")
                if existing is None:
                    _validate_update_result(
                        await self.async_client.create_payload_index(
                            self.collection_name,
                            field_name=name,
                            field_schema=schema,
                            wait=True,
                        )
                    )

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Delete this collection if it exists."""
        options = _validate_operation_options(operation_options, {"timeout"})
        if await self.collection_exists() and not await self.async_client.delete_collection(
            self.collection_name, **options
        ):
            raise IntegrationException(f"Qdrant did not delete collection '{self.collection_name}'.")

    async def aclose(self) -> None:
        """Close an owned client once; borrowed clients are left open."""
        if self.managed_client and not self._closed:
            await self.async_client.close()
            self._closed = True

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close the owned client on context exit."""
        await self.aclose()

    def _serialize_dicts_to_store_models(
        self,
        records: Sequence[dict[str, Any]],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[models.PointStruct]:
        points: list[models.PointStruct] = []
        for record in records:
            key = _prepare_point_id(record[self.definition.key_field_storage_name])
            kind = self.definition.key_field.type_
            if (kind == "int" and not isinstance(key, int)) or (kind in {"str", "UUID"} and not isinstance(key, str)):
                raise TypeError(f"Qdrant key must match declared type '{kind}'.")
            payload: dict[str, Any] = {}
            for field in self.definition.data_fields:
                name = field.storage_name or field.name
                payload[name] = _prepare_field_payload(field, record[name])
            vectors: dict[str, models.Vector] = {
                field.storage_name or field.name: _prepare_dense_vector(
                    record[field.storage_name or field.name], field.name
                )
                for field in self.definition.vector_fields
                if record[field.storage_name or field.name] is not None
            }
            points.append(models.PointStruct(id=key, payload=payload, vector=vectors))
        return points

    def _deserialize_store_models_to_dicts(
        self,
        records: Sequence[Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for point in records:
            if not isinstance(point, (models.Record, models.ScoredPoint)):
                raise TypeError("Qdrant responses must contain Record or ScoredPoint values.")
            record = dict(point.payload or {})
            record[self.definition.key_field_storage_name] = self._prepare_result_key(point.id)
            if point.vector is not None:
                if not isinstance(point.vector, dict):
                    raise IntegrationInvalidResponseException("Expected named vectors in the Qdrant response.")
                for field in self.definition.vector_fields:
                    name = field.storage_name or field.name
                    record[name] = point.vector.get(name)
            result.append(record)
        return result

    def _prepare_result_key(self, key: Any) -> KeyT:
        return cast(KeyT, UUID(str(key)) if self.definition.key_field.type_ == "UUID" else key)

    def _prepare_filter(self, filter: FilterExpression | None) -> models.Filter | None:
        if filter is None:
            return None
        if self._is_local:
            raise NotImplementedError(
                "Portable filters require a Qdrant server; local mode differs for missing/null and numeric values."
            )
        return models.Filter(must=[self._prepare_filter_condition(filter)])

    def _prepare_filter_condition(self, expression: FilterExpression) -> models.Condition:
        if isinstance(expression, FilterGroup):
            children = [self._prepare_filter_condition(child) for child in expression.filters]
            if expression.operator == "and":
                return models.Filter(must=children)
            if expression.operator == "or":
                return models.Filter(should=children)
            # NOT applies to the entire child, not separately to its constituent leaves.
            return models.Filter(must_not=children)

        field = self.definition.try_get_field(expression.field_name)
        if field is None or "." in expression.field_name:
            raise NotImplementedError("Qdrant filters support declared top-level logical fields only.")
        if field.field_type == "key":
            return _prepare_key_filter_condition(expression, field)
        if field.field_type == "vector":
            raise NotImplementedError("Portable Qdrant filters do not operate on vector fields.")
        name = field.storage_name or field.name
        operator, value = expression.operator, expression.value
        if operator == "exists":
            return _prepare_presence_condition(name)
        if operator == "is_null":
            return _prepare_null_condition(name)
        if operator == "is_not_null":
            return _prepare_non_null_condition(name)
        if operator in {"eq", "ne"}:
            condition = _prepare_equality_condition(name, value, field)
            return (
                models.Filter(must=[_prepare_presence_condition(name)], must_not=[condition])
                if operator == "ne"
                else condition
            )
        if operator in {"gt", "gte", "lt", "lte", "between"}:
            if field.type_ not in {"int", "float"}:
                raise NotImplementedError("Qdrant ordered comparisons require a declared int or float field.")
            bounds = (
                {"gte": _prepare_range_operand(value[0]), "lte": _prepare_range_operand(value[1])}
                if operator == "between"
                else {operator: _prepare_range_operand(value)}
            )
            return models.FieldCondition(key=name, range=models.Range(**bounds))
        if operator in {"in", "not_in"}:
            condition = (
                models.Filter(should=[_prepare_equality_condition(name, item, field) for item in value])
                if value
                else _prepare_false_condition()
            )
            if operator == "not_in":
                return models.Filter(must=[_prepare_non_null_condition(name)], must_not=[condition])
            return models.Filter(must=[_prepare_non_null_condition(name), condition])
        if operator in {"contains", "contains_any", "contains_all"}:
            if field.type_ not in {"list", "tuple", "set", "Sequence"}:
                raise NotImplementedError("Qdrant collection membership requires a declared collection field type.")
            operands: Sequence[Any] = [value] if operator == "contains" else value
            conditions = [_prepare_equality_condition(name, item, field, element=True) for item in operands]
            if operator == "contains_all":
                return models.Filter(must=[_prepare_non_null_condition(name), *conditions])
            return models.Filter(should=conditions) if conditions else _prepare_false_condition()
        raise NotImplementedError(
            f"Qdrant does not support portable filter operator '{operator}'. "
            "Literal text operations are not equivalent to tokenized full-text search."
        )

    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[KeyT]:
        options = _validate_operation_options(operation_options, _WRITE_OPTIONS)
        if not records:
            return []
        for start in range(0, len(records), _BATCH_SIZE):
            points = list(records[start : start + _BATCH_SIZE])
            result = await self.async_client.upsert(
                self.collection_name,
                points=points,
                wait=True,
                **options,
            )
            _validate_update_result(result)
        return [self._prepare_result_key(point.id) for point in records]

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
    ) -> Sequence[models.Record]:
        options = _validate_operation_options(operation_options, _READ_OPTIONS)
        if order_by:
            raise NotImplementedError(
                "Qdrant ordered retrieval is not supported. Omit order_by to use unordered retrieval."
            )
        if keys is not None:
            if skip:
                raise ValueError("Qdrant key retrieval cannot be combined with skip.")
            ids = [_prepare_point_id(key) for key in keys]
            result: list[models.Record] = []
            for start in range(0, len(ids), _BATCH_SIZE):
                page = await self.async_client.retrieve(
                    self.collection_name,
                    ids=ids[start : start + _BATCH_SIZE],
                    with_payload=True,
                    with_vectors=include_vectors,
                    **options,
                )
                result.extend(page)
            return result
        native_filter = self._prepare_filter(filter)
        records: list[models.Record] = []
        offset = None
        remaining_skip = skip
        while len(records) < top:
            page, offset = await self.async_client.scroll(
                self.collection_name,
                scroll_filter=native_filter,
                offset=offset,
                limit=min(_BATCH_SIZE, remaining_skip + top - len(records)),
                with_payload=True,
                with_vectors=include_vectors,
                **options,
            )
            discarded = min(remaining_skip, len(page))
            remaining_skip -= discarded
            records.extend(page[discarded:])
            if offset is None:
                break
        return records

    async def _inner_delete(
        self,
        keys: Sequence[KeyT],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        options = _validate_operation_options(operation_options, _WRITE_OPTIONS)
        ids: list[models.ExtendedPointId] = [_prepare_point_id(key) for key in keys]
        for start in range(0, len(ids), _BATCH_SIZE):
            selector = models.PointIdsList(points=ids[start : start + _BATCH_SIZE])
            result = await self.async_client.delete(
                self.collection_name,
                points_selector=selector,
                wait=True,
                **options,
            )
            _validate_update_result(result)

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
    ) -> SearchResults[models.ScoredPoint]:
        options = _validate_operation_options(operation_options, _READ_OPTIONS | {"search_params"})
        if additional_property_name is not None:
            raise NotImplementedError("Qdrant keyword-hybrid search is not supported by this connector.")
        if vector is None:
            raise ValueError("Qdrant search requires a dense vector or a configured embedding generator.")
        field = self.definition.try_get_vector_field(vector_property_name)
        if field is None:
            raise ValueError("Qdrant search requires a declared vector field.")
        if score_threshold is not None:
            if isinstance(score_threshold, bool) or not isinstance(score_threshold, (int, float)):
                raise ValueError("Qdrant score_threshold must be a finite number.")
            try:
                score_threshold = float(score_threshold)
            except OverflowError as exc:
                raise ValueError("Qdrant score_threshold must be a finite number.") from exc
            if not math.isfinite(score_threshold):
                raise ValueError("Qdrant score_threshold must be a finite number.")
        query = _prepare_dense_vector(vector, field.name)
        native_filter = self._prepare_filter(filter)
        response = await self.async_client.query_points(
            self.collection_name,
            query=query,
            using=field.storage_name or field.name,
            query_filter=native_filter,
            limit=top,
            offset=skip,
            with_payload=True,
            with_vectors=include_vectors,
            score_threshold=score_threshold,
            **options,
        )
        return SearchResults(response.points)

    def _get_record_from_result(self, result: Any) -> models.ScoredPoint:
        if not isinstance(result, models.ScoredPoint):
            raise IntegrationInvalidResponseException("Expected a Qdrant ScoredPoint.")
        return result

    def _get_score_from_result(self, result: Any) -> float:
        return self._get_record_from_result(result).score


class QdrantStore(BaseVectorStore):
    """Create Qdrant collection clients sharing one async connection."""

    def __init__(
        self,
        *,
        async_client: AsyncQdrantClient | None = None,
        url: str | None = None,
        api_key: str | SecretString | None = None,
        embedding_generator: EmbeddingClient | None = None,
        managed_client: bool | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a store.

        Args:
            async_client: Existing async client; borrowed unless managed_client=True.
            url: Server URL override; otherwise loaded from QdrantSettings, then the SDK defaults to localhost.
            api_key: API key override as a string or SecretString; otherwise loaded from QdrantSettings.
            embedding_generator: Default embedding client inherited by collections.
            managed_client: Whether to close the client. Defaults to True for connector-created clients.
            env_file_path: Optional .env file to load before process environment variables.
            env_file_encoding: Encoding for the .env file; defaults to UTF-8.
        """
        if async_client is not None and any(
            value is not None for value in (url, api_key, env_file_path, env_file_encoding)
        ):
            raise ValueError("Pass async_client or connection settings, not both.")
        super().__init__(
            embedding_generator=embedding_generator,
            managed_client=async_client is None if managed_client is None else managed_client,
        )
        self.async_client = (
            async_client
            if async_client is not None
            else _create_client(
                url=url,
                api_key=api_key,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        )
        self._closed = False

    def get_collection(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> QdrantCollection[Any, ModelT]:
        """Create a collection that borrows this store's client."""
        return QdrantCollection(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator if embedding_generator is not None else self.embedding_generator,
            async_client=self.async_client,
            managed_client=False,
        )

    async def list_collection_names(self, *, operation_options: Mapping[str, Any] | None = None) -> Sequence[str]:
        """List collection names on the server."""
        _validate_operation_options(operation_options, set())
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return [collection.name for collection in (await self.async_client.get_collections()).collections]

    async def collection_exists(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        """Check collection existence without downloading the collection list."""
        _validate_operation_options(operation_options, set())
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return await self.async_client.collection_exists(collection_name)

    async def ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Delete a collection if it exists, applying timeout only to deletion."""
        options = _validate_operation_options(operation_options, {"timeout"})
        if await self.collection_exists(collection_name):
            await self._inner_ensure_collection_deleted(collection_name, operation_options=options)

    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        options = _validate_operation_options(operation_options, {"timeout"})
        if not await self.async_client.delete_collection(collection_name, **options):
            raise IntegrationException(f"Qdrant did not delete collection '{collection_name}'.")

    async def aclose(self) -> None:
        """Close an owned client once, leaving borrowed clients open."""
        if self.managed_client and not self._closed:
            await self.async_client.close()
            self._closed = True

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close the owned client on context exit."""
        await self.aclose()
