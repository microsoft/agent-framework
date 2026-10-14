# Copyright (c) Microsoft. All rights reserved.

"""Async Milvus dense-vector collections and stores for Microsoft Agent Framework."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Final, Generic, cast

from agent_framework import (
    BaseVectorCollection,
    BaseVectorSearch,
    BaseVectorStore,
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
from pymilvus import DataType, MilvusClient
from pymilvus.exceptions import MilvusException
from typing_extensions import TypedDict, TypeVar

KeyT = TypeVar("KeyT", default=Any)
ModelT = TypeVar("ModelT", default=Any)

DEFAULT_URI: Final[str] = "http://localhost:19530"
DEFAULT_VARCHAR_LENGTH: Final[int] = 65535

# Milvus metric types, see https://milvus.io/docs/metric.md
_METRICS: Final[dict[str, str]] = {
    "DEFAULT": "COSINE",
    "cosine_similarity": "COSINE",
    "cosine_distance": "COSINE",
    "dot_prod": "IP",
    "euclidean_distance": "L2",
    "euclidean_squared_distance": "L2",
}
# Metrics where a larger score is a closer match; used to interpret score_threshold.
_HIGHER_IS_BETTER: Final[set[str]] = {"COSINE", "IP"}
# Milvus index types, see https://milvus.io/docs/index.md
_INDEX_KINDS: Final[dict[str, str]] = {
    "default": "AUTOINDEX",
    "hnsw": "HNSW",
    "flat": "FLAT",
    "ivf_flat": "IVF_FLAT",
    "disk_ann": "DISKANN",
}
# Data-model scalar types mapped to Milvus field types.
_SCALAR_TYPES: Final[dict[str, DataType]] = {
    "str": DataType.VARCHAR,
    "int": DataType.INT64,
    "float": DataType.DOUBLE,
    "bool": DataType.BOOL,
    "list": DataType.JSON,
    "tuple": DataType.JSON,
    "set": DataType.JSON,
    "Sequence": DataType.JSON,
    "dict": DataType.JSON,
}

_READ_OPTIONS: Final[set[str]] = {"timeout"}
_WRITE_OPTIONS: Final[set[str]] = {"timeout"}
_CREATE_OPTIONS: Final[set[str]] = {"timeout", "consistency_level"}
_SEARCH_OPTIONS: Final[set[str]] = {"timeout", "search_params"}


class MilvusSettings(TypedDict, total=False):
    """Connection settings loaded through Agent Framework's ``load_settings``.

    Explicit constructor arguments take precedence over an explicitly selected
    ``.env`` file, then environment variables prefixed with ``MILVUS_``.

    Keys:
        uri: Server URI from ``MILVUS_URI`` (e.g. ``http://localhost:19530``), or a local
            ``.db`` path for Milvus Lite (requires the ``pymilvus[milvus_lite]`` extra).
            When unset, defaults to ``http://localhost:19530``.
        token: Optional access token from ``MILVUS_TOKEN``, stored as an AF ``SecretString``.
        user: Optional username from ``MILVUS_USER``.
        password: Optional password from ``MILVUS_PASSWORD``, stored as an AF ``SecretString``.
        db_name: Optional database name from ``MILVUS_DB_NAME``.
    """

    uri: str | None
    token: SecretString | None
    user: str | None
    password: SecretString | None
    db_name: str | None


def _validate_operation_options(options: Mapping[str, Any] | None, allowed: set[str]) -> dict[str, Any]:
    result = dict(options or {})
    unknown = result.keys() - allowed
    if unknown:
        raise ValueError(f"Unsupported Milvus operation option(s): {', '.join(sorted(unknown))}.")
    return result


def _create_client(
    *,
    uri: str | None,
    token: str | SecretString | None,
    user: str | None,
    password: str | SecretString | None,
    db_name: str | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> MilvusClient:
    settings = load_settings(
        MilvusSettings,
        env_prefix="MILVUS_",
        uri=uri,
        token=token,
        user=user,
        password=password,
        db_name=db_name,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    resolved_token = settings.get("token")
    resolved_password = settings.get("password")
    client_kwargs: dict[str, Any] = {"uri": settings.get("uri") or DEFAULT_URI}
    if resolved_token is not None:
        client_kwargs["token"] = resolved_token.get_secret_value()
    if settings.get("user"):
        client_kwargs["user"] = settings.get("user")
    if resolved_password is not None:
        client_kwargs["password"] = resolved_password.get_secret_value()
    if settings.get("db_name"):
        client_kwargs["db_name"] = settings.get("db_name")
    try:
        return MilvusClient(**client_kwargs)
    except Exception as exc:  # pragma: no cover - surfaced as an integration error
        raise IntegrationException("Failed to create the Milvus client.") from exc


def _is_already_exists_error(exc: MilvusException) -> bool:
    """Whether a Milvus error indicates the collection already exists (a concurrent create)."""
    message = getattr(exc, "message", None) or str(exc)
    return "already exist" in message.lower()


def _format_scalar(value: Any) -> str:
    """Format a Python scalar as a Milvus boolean-expression literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        # json.dumps escapes quotes, backslashes and control characters (newlines, tabs, …),
        # producing a valid double-quoted Milvus string literal for any stored value.
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return repr(value)
    raise NotImplementedError(f"Milvus filters support only scalar operands, not {type(value).__name__}.")


def _format_list(values: Any) -> str:
    return "[" + ", ".join(_format_scalar(item) for item in values) + "]"


def _check_scalar_operand(field: VectorStoreField, value: Any) -> None:
    """Reject operands whose Python type does not match the field's declared type.

    Booleans are kept distinct from numbers so a filter like ``eq`` on a numeric field with a
    boolean operand is rejected rather than emitting an invalid, type-mismatched comparison.
    """
    kind = field.type_ or "str"
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"Filter on boolean field '{field.name}' requires a boolean operand.")
    elif kind == "str":
        if not isinstance(value, str):
            raise ValueError(f"Filter on string field '{field.name}' requires a string operand.")
    elif kind in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Filter on numeric field '{field.name}' requires a non-boolean numeric operand.")
    else:
        raise NotImplementedError(
            f"Milvus filters do not support equality or membership on '{kind}' field '{field.name}'."
        )


def _check_numeric_field(field: VectorStoreField) -> None:
    if (field.type_ or "str") not in ("int", "float"):
        raise NotImplementedError(
            f"Milvus ordered comparisons require a declared int or float field; '{field.name}' is '{field.type_}'."
        )


class MilvusCollection(BaseVectorCollection[KeyT, ModelT], BaseVectorSearch[KeyT, ModelT], Generic[KeyT, ModelT]):
    """Store and search records with the official Milvus client.

    The data model definition drives the collection schema: the key field becomes the
    primary key (``INT64``/``VARCHAR``), data fields become typed scalar fields, and
    vector fields become ``FLOAT_VECTOR`` fields, each with its own index. The default
    metric is cosine similarity (larger is better); scores retain native Milvus units.

    The synchronous ``MilvusClient`` is used under ``asyncio.to_thread`` so the connector
    presents the framework's async interface while remaining compatible across the
    supported ``pymilvus`` range. Supplied clients remain caller-owned unless managed.
    """

    supported_key_types: ClassVar[set[str] | None] = {"int", "str"}
    supported_vector_types: ClassVar[set[str] | None] = {"float", "float32", "float64"}
    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        client: MilvusClient | None = None,
        uri: str | None = None,
        token: str | SecretString | None = None,
        user: str | None = None,
        password: str | SecretString | None = None,
        db_name: str | None = None,
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
            client: Existing client, borrowed by default. Use this for Milvus Lite or advanced configuration.
            uri: Server URI override; otherwise loaded from MilvusSettings, then defaults to localhost.
            token: Access token override as a string or SecretString; otherwise loaded from MilvusSettings.
            user: Username override; otherwise loaded from MilvusSettings.
            password: Password override as a string or SecretString; otherwise loaded from MilvusSettings.
            db_name: Database name override; otherwise loaded from MilvusSettings.
            managed_client: Whether to close the client. Defaults to True only for connector-created clients.
            env_file_path: Optional .env file to load before process environment variables.
            env_file_encoding: Encoding for the .env file; defaults to UTF-8.
        """
        if client is not None and any(
            value is not None for value in (uri, token, user, password, db_name, env_file_path, env_file_encoding)
        ):
            raise ValueError("Pass client or connection settings, not both.")
        super().__init__(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator,
            managed_client=client is None if managed_client is None else managed_client,
        )
        self.client = (
            client
            if client is not None
            else _create_client(
                uri=uri,
                token=token,
                user=user,
                password=password,
                db_name=db_name,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        )
        self._closed = False
        # pymilvus ships only partial type information, so operational calls go through an
        # Any-typed handle to keep the strict type checker clean; the public ``client`` stays typed.
        self._client: Any = self.client

    @property
    def _key_storage_name(self) -> str:
        return self.definition.key_field_storage_name

    def _validate_data_model(self) -> None:
        super()._validate_data_model()
        if self.definition.key_field.is_auto_generated:
            raise NotImplementedError("Milvus requires application-provided primary keys; it does not generate keys.")
        for field in self.definition.vector_fields:
            if not isinstance(field.dimensions, int) or isinstance(field.dimensions, bool):
                raise TypeError("Milvus vector dimensions must be an integer.")
            if field.distance_function not in _METRICS:
                raise NotImplementedError(f"Milvus distance function '{field.distance_function}' is not supported.")
            if field.index_kind not in _INDEX_KINDS:
                raise NotImplementedError(f"Milvus index kind '{field.index_kind}' is not supported.")
        for field in self.definition.data_fields:
            if (field.type_ or "str") not in _SCALAR_TYPES:
                raise NotImplementedError(f"Milvus data field type '{field.type_}' is not supported.")
            # Scalar and full-text indexing are not created by this connector yet; rejecting the
            # flags avoids silently reporting success for an index that was never built.
            if field.is_indexed:
                raise NotImplementedError(
                    f"Scalar indexing (is_indexed) is not supported by this Milvus connector; field '{field.name}'."
                )
            if field.is_full_text_indexed:
                raise NotImplementedError(
                    f"Full-text indexing is not supported by this Milvus connector; field '{field.name}'."
                )

    def _output_fields(self, include_vectors: bool) -> list[str]:
        fields = [field.storage_name or field.name for field in self.definition.data_fields]
        fields.append(self._key_storage_name)
        if include_vectors:
            fields.extend(field.storage_name or field.name for field in self.definition.vector_fields)
        return fields

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Check whether this collection exists."""
        options = _validate_operation_options(operation_options, _READ_OPTIONS)
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return await asyncio.to_thread(self._client.has_collection, self.collection_name, **options)

    def _build_schema_and_index(self) -> tuple[Any, Any]:
        schema = cast("Any", MilvusClient).create_schema(auto_id=False, enable_dynamic_field=False)
        key_field = self.definition.key_field
        if key_field.type_ == "int":
            schema.add_field(field_name=self._key_storage_name, datatype=DataType.INT64, is_primary=True)
        else:
            schema.add_field(
                field_name=self._key_storage_name,
                datatype=DataType.VARCHAR,
                is_primary=True,
                max_length=DEFAULT_VARCHAR_LENGTH,
            )
        for field in self.definition.data_fields:
            datatype = _SCALAR_TYPES[field.type_ or "str"]
            if datatype == DataType.VARCHAR:
                schema.add_field(
                    field_name=field.storage_name or field.name, datatype=datatype, max_length=DEFAULT_VARCHAR_LENGTH
                )
            else:
                schema.add_field(field_name=field.storage_name or field.name, datatype=datatype)
        index_params = self._client.prepare_index_params()
        for field in self.definition.vector_fields:
            schema.add_field(
                field_name=field.storage_name or field.name,
                datatype=DataType.FLOAT_VECTOR,
                dim=cast(int, field.dimensions),
            )
            index_params.add_index(
                field_name=field.storage_name or field.name,
                index_type=_INDEX_KINDS[cast(str, field.index_kind)],
                metric_type=_METRICS[cast(str, field.distance_function)],
            )
        return schema, index_params

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create the collection and its vector indexes, or validate an existing one.

        When a collection with this name already exists, its schema and vector indexes are
        validated against the data model definition so a stale or unrelated collection is not
        silently accepted; a mismatch raises ``ValueError``.
        """
        options = _validate_operation_options(operation_options, _CREATE_OPTIONS)
        if await self.collection_exists():
            await self._validate_existing_collection()
            return
        schema, index_params = self._build_schema_and_index()
        try:
            await asyncio.to_thread(
                self._client.create_collection,
                collection_name=self.collection_name,
                schema=schema,
                index_params=index_params,
                **options,
            )
            return
        except MilvusException as exc:
            # create_collection creates the collection and then separately builds indexes and
            # loads it. Only swallow a genuine already-exists/concurrent-create error; re-raise
            # every other failure (including index/load failures that leave the collection
            # existing but incomplete) so it is not masked as success.
            if not _is_already_exists_error(exc):
                raise
        # A concurrent creator won the race; validate the existing collection matches.
        await self._validate_existing_collection()

    async def _validate_existing_collection(self) -> None:
        """Validate an existing collection's fields, vector dimensions and metrics."""
        info = cast(
            "Mapping[str, Any]", await asyncio.to_thread(self._client.describe_collection, self.collection_name)
        )
        raw_fields = cast("Sequence[Mapping[str, Any]]", info.get("fields") or [])
        fields: dict[str, Mapping[str, Any]] = {str(field["name"]): field for field in raw_fields}
        key = fields.get(self._key_storage_name)
        if key is None or not key.get("is_primary"):
            raise ValueError(
                f"Existing Milvus collection '{self.collection_name}' has no primary key "
                f"'{self._key_storage_name}' matching the data model."
            )
        for field in self.definition.data_fields:
            if (field.storage_name or field.name) not in fields:
                raise ValueError(
                    f"Existing Milvus collection '{self.collection_name}' is missing field "
                    f"'{field.storage_name or field.name}'."
                )
        for field in self.definition.vector_fields:
            name = field.storage_name or field.name
            existing = fields.get(name)
            if existing is None:
                raise ValueError(
                    f"Existing Milvus collection '{self.collection_name}' is missing vector field '{name}'."
                )
            dimensions = cast("Mapping[str, Any]", existing.get("params") or {}).get("dim")
            if dimensions is not None and int(dimensions) != int(cast(int, field.dimensions)):
                raise ValueError(
                    f"Existing Milvus vector field '{name}' has dimension {dimensions}, expected {field.dimensions}."
                )
            index = await asyncio.to_thread(self._client.describe_index, self.collection_name, name)
            metric = cast("Mapping[str, Any]", index).get("metric_type") if isinstance(index, Mapping) else None
            expected = _METRICS[cast(str, field.distance_function)]
            if metric is not None and metric != expected:
                raise ValueError(f"Existing Milvus vector field '{name}' uses metric {metric}, expected {expected}.")

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Delete this collection if it exists."""
        options = _validate_operation_options(operation_options, _WRITE_OPTIONS)
        if await self.collection_exists():
            await asyncio.to_thread(self._client.drop_collection, self.collection_name, **options)

    async def aclose(self) -> None:
        """Close an owned client once; borrowed clients are left open."""
        if self.managed_client and not self._closed:
            await asyncio.to_thread(self._client.close)
            self._closed = True

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close the owned client on context exit."""
        await self.aclose()

    def _serialize_dicts_to_store_models(
        self,
        records: Sequence[dict[str, Any]],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        for record in records:
            model: dict[str, Any] = {self._key_storage_name: record[self._key_storage_name]}
            for field in self.definition.data_fields:
                name = field.storage_name or field.name
                model[name] = record[name]
            for field in self.definition.vector_fields:
                name = field.storage_name or field.name
                value = record.get(name)
                if value is not None:
                    model[name] = [float(component) for component in value]
            models.append(model)
        return models

    def _deserialize_store_models_to_dicts(
        self,
        records: Sequence[Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in records:
            if not isinstance(row, Mapping):
                raise IntegrationInvalidResponseException("Milvus responses must contain mapping rows.")
            record: dict[str, Any] = {}
            if self._key_storage_name in row:
                record[self._key_storage_name] = row[self._key_storage_name]
            for field in self.definition.data_fields:
                name = field.storage_name or field.name
                if name in row:
                    record[name] = row[name]
            for field in self.definition.vector_fields:
                name = field.storage_name or field.name
                if name in row:
                    record[name] = row[name]
            result.append(record)
        return result

    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[KeyT]:
        options = _validate_operation_options(operation_options, _WRITE_OPTIONS)
        if not records:
            return []
        await asyncio.to_thread(
            self._client.upsert, collection_name=self.collection_name, data=list(records), **options
        )
        return [cast(KeyT, record[self._key_storage_name]) for record in records]

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
    ) -> Sequence[Any] | None:
        options = _validate_operation_options(operation_options, _READ_OPTIONS)
        if order_by:
            raise NotImplementedError("Milvus ordered retrieval is not supported. Omit order_by.")
        output_fields = self._output_fields(include_vectors)
        if keys is not None:
            if skip:
                raise ValueError("Milvus key retrieval cannot be combined with skip.")
            if not keys:
                return []
            return await asyncio.to_thread(
                self._client.get,
                collection_name=self.collection_name,
                ids=list(keys),
                output_fields=output_fields,
                **options,
            )
        return await asyncio.to_thread(
            self._client.query,
            collection_name=self.collection_name,
            filter=self._prepare_filter(filter),
            output_fields=output_fields,
            limit=top,
            offset=skip,
            **options,
        )

    async def _inner_delete(
        self,
        keys: Sequence[KeyT],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        options = _validate_operation_options(operation_options, _WRITE_OPTIONS)
        if not keys:
            return
        await asyncio.to_thread(self._client.delete, collection_name=self.collection_name, ids=list(keys), **options)

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
    ) -> SearchResults[dict[str, Any]]:
        options = _validate_operation_options(operation_options, _SEARCH_OPTIONS)
        if additional_property_name is not None:
            raise NotImplementedError("Milvus keyword-hybrid search is not supported by this connector.")
        if vector is None:
            raise ValueError("Milvus search requires a dense vector or a configured embedding generator.")
        field = self.definition.try_get_vector_field(vector_property_name)
        if field is None:
            raise ValueError("Milvus search requires a declared vector field.")
        if score_threshold is not None:
            if isinstance(score_threshold, bool) or not isinstance(score_threshold, (int, float)):
                raise ValueError("Milvus score_threshold must be a finite number.")
            score_threshold = float(score_threshold)
            if not math.isfinite(score_threshold):
                raise ValueError("Milvus score_threshold must be a finite number.")
        metric = _METRICS[cast(str, field.distance_function)]
        search_params: dict[str, Any] = {"metric_type": metric}
        search_params.update(options.pop("search_params", {}) or {})
        if skip:
            search_params["offset"] = skip
        hits = await asyncio.to_thread(
            self._client.search,
            collection_name=self.collection_name,
            data=[[float(component) for component in vector]],
            anns_field=field.storage_name or field.name,
            limit=top,
            filter=self._prepare_filter(filter),
            output_fields=self._output_fields(include_vectors),
            search_params=search_params,
            **options,
        )
        results = list(hits[0]) if hits else []
        if score_threshold is not None:
            # Milvus has no portable score cutoff across metrics, so enforce it connector-side.
            # For similarity metrics (COSINE/IP) a larger score is closer; for L2 a smaller score is closer.
            keep_higher = metric in _HIGHER_IS_BETTER
            results = [
                hit for hit in results if self._passes_threshold(hit.get("distance", 0.0), score_threshold, keep_higher)
            ]
        return SearchResults(results)

    @staticmethod
    def _passes_threshold(distance: float, threshold: float, keep_higher: bool) -> bool:
        return distance >= threshold if keep_higher else distance <= threshold

    def _get_record_from_result(self, result: Any) -> dict[str, Any]:
        if not isinstance(result, Mapping):
            raise IntegrationInvalidResponseException("Expected a Milvus search hit mapping.")
        hit = cast("Mapping[str, Any]", result)
        record: dict[str, Any] = dict(hit.get("entity") or {})
        if "id" in hit:
            record.setdefault(self._key_storage_name, hit["id"])
        return record

    def _get_score_from_result(self, result: Any) -> float | None:
        if not isinstance(result, Mapping):
            raise IntegrationInvalidResponseException("Expected a Milvus search hit mapping.")
        distance = cast("Mapping[str, Any]", result).get("distance")
        return float(distance) if distance is not None else None

    def _prepare_filter(self, filter: FilterExpression | None) -> str:
        if filter is None:
            return ""
        return self._prepare_filter_condition(filter)

    def _prepare_filter_condition(self, expression: FilterExpression) -> str:
        if isinstance(expression, FilterGroup):
            children = [self._prepare_filter_condition(child) for child in expression.filters]
            if expression.operator == "and":
                return "(" + " and ".join(children) + ")"
            if expression.operator == "or":
                return "(" + " or ".join(children) + ")"
            return f"(not {children[0]})"

        field = self.definition.try_get_field(expression.field_name)
        if field is None or "." in expression.field_name:
            raise NotImplementedError("Milvus filters support declared top-level fields only.")
        if field.field_type == "vector":
            raise NotImplementedError("Milvus filters do not operate on vector fields.")
        name = field.storage_name or field.name
        operator, value = expression.operator, expression.value
        if operator in ("eq", "ne"):
            _check_scalar_operand(field, value)
            return f"({name} {'==' if operator == 'eq' else '!='} {_format_scalar(value)})"
        if operator in ("gt", "gte", "lt", "lte"):
            _check_numeric_field(field)
            _check_scalar_operand(field, value)
            symbol = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[operator]
            return f"({name} {symbol} {_format_scalar(value)})"
        if operator == "between":
            _check_numeric_field(field)
            _check_scalar_operand(field, value[0])
            _check_scalar_operand(field, value[1])
            return f"({name} >= {_format_scalar(value[0])} and {name} <= {_format_scalar(value[1])})"
        if operator in ("in", "not_in"):
            for item in value:
                _check_scalar_operand(field, item)
            keyword = "in" if operator == "in" else "not in"
            return f"({name} {keyword} {_format_list(value)})"
        raise NotImplementedError(f"Milvus does not support portable filter operator '{operator}'.")


class MilvusStore(BaseVectorStore):
    """Create Milvus collection clients sharing one connection."""

    def __init__(
        self,
        *,
        client: MilvusClient | None = None,
        uri: str | None = None,
        token: str | SecretString | None = None,
        user: str | None = None,
        password: str | SecretString | None = None,
        db_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        managed_client: bool | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a store.

        Args:
            client: Existing client; borrowed unless managed_client=True.
            uri: Server URI override; otherwise loaded from MilvusSettings, then defaults to localhost.
            token: Access token override as a string or SecretString; otherwise loaded from MilvusSettings.
            user: Username override; otherwise loaded from MilvusSettings.
            password: Password override as a string or SecretString; otherwise loaded from MilvusSettings.
            db_name: Database name override; otherwise loaded from MilvusSettings.
            embedding_generator: Default embedding client inherited by collections.
            managed_client: Whether to close the client. Defaults to True for connector-created clients.
            env_file_path: Optional .env file to load before process environment variables.
            env_file_encoding: Encoding for the .env file; defaults to UTF-8.
        """
        if client is not None and any(
            value is not None for value in (uri, token, user, password, db_name, env_file_path, env_file_encoding)
        ):
            raise ValueError("Pass client or connection settings, not both.")
        super().__init__(
            embedding_generator=embedding_generator,
            managed_client=client is None if managed_client is None else managed_client,
        )
        self.client = (
            client
            if client is not None
            else _create_client(
                uri=uri,
                token=token,
                user=user,
                password=password,
                db_name=db_name,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        )
        self._closed = False
        # pymilvus ships only partial type information, so operational calls go through an
        # Any-typed handle to keep the strict type checker clean; the public ``client`` stays typed.
        self._client: Any = self.client

    def get_collection(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> MilvusCollection[Any, ModelT]:
        """Create a collection that borrows this store's client."""
        return MilvusCollection(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator if embedding_generator is not None else self.embedding_generator,
            client=self.client,
            managed_client=False,
        )

    async def list_collection_names(self, *, operation_options: Mapping[str, Any] | None = None) -> Sequence[str]:
        """List collection names on the server."""
        options = _validate_operation_options(operation_options, _READ_OPTIONS)
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return await asyncio.to_thread(self._client.list_collections, **options)

    async def collection_exists(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        """Check collection existence without downloading the collection list."""
        options = _validate_operation_options(operation_options, _READ_OPTIONS)
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return await asyncio.to_thread(self._client.has_collection, collection_name, **options)

    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        options = _validate_operation_options(operation_options, _WRITE_OPTIONS)
        await asyncio.to_thread(self._client.drop_collection, collection_name, **options)

    async def aclose(self) -> None:
        """Close an owned client once, leaving borrowed clients open."""
        if self.managed_client and not self._closed:
            await asyncio.to_thread(self._client.close)
            self._closed = True

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close the owned client on context exit."""
        await self.aclose()
