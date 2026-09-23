# Copyright (c) Microsoft. All rights reserved.

"""Redis HASH and JSON vector collections using Redis Search."""

from __future__ import annotations

import math
import re
from codecs import lookup
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Generic, Literal, cast
from uuid import uuid4
from weakref import WeakSet

import msgspec
import numpy as np
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
from agent_framework._feature_stage import ExperimentalFeature, experimental
from agent_framework._telemetry import mark_feature_used
from agent_framework._vector_filters import FilterExpression
from agent_framework._vectors import EmbeddingClient, Vector
from agent_framework.exceptions import (
    IntegrationException,
    IntegrationInitializationError,
    IntegrationInvalidResponseException,
)
from redis.asyncio import Redis
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from redis.exceptions import RedisError, ResponseError
from redisvl.exceptions import RedisSearchError
from redisvl.index import AsyncSearchIndex
from redisvl.schema import IndexSchema
from redisvl.utils.token_escaper import TokenEscaper
from typing_extensions import TypedDict, TypeVar

from ._feature_usage import FeatureIndex

ModelT = TypeVar("ModelT", default=Any)
_METRICS = {
    "DEFAULT": "COSINE",
    "cosine_distance": "COSINE",
    "euclidean_squared_distance": "L2",
    "redis.ip": "IP",
}
_DTYPES = {"float": "<f4", "float32": "<f4", "float64": "<f8", "bytes": "<f4"}
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_BATCH_SIZE = 100
_TAG_SEPARATOR = "\x1f"
_ESCAPER = TokenEscaper(re.compile(r"[^\w]", re.UNICODE))
_INDEXED_TYPES = {"str", "bool", "int", "float", "list", "tuple"}


class RedisSettings(TypedDict, total=False):
    """Connection settings resolved by the shared settings loader.

    Explicit overrides take precedence over an explicitly supplied .env file,
    then environment variables with the ``REDIS_`` prefix.

    Keys:
        url: Redis connection URL, including optional credentials. Loaded from
            ``REDIS_URL`` and masked as a SecretString.
    """

    url: SecretString | None


def _create_client(
    redis_url: str | SecretString | None,
    redis_client: Redis | None,
    *,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> Redis:
    if redis_client is None:
        settings = load_settings(
            RedisSettings,
            env_prefix="REDIS_",
            url=redis_url,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        url = settings.get("url")
        redis_client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            url.get_secret_value() if url is not None else "redis://localhost:6379",
            decode_responses=False,
            protocol=2,
        )
    if not isinstance(redis_client, Redis):
        raise TypeError("Redis vector stores require a standalone redis.asyncio.Redis client.")
    kwargs = cast(dict[str, Any], redis_client.connection_pool.connection_kwargs)  # pyright: ignore[reportUnknownMemberType]
    if kwargs.get("decode_responses", False) or kwargs.get("protocol", 2) != 2:
        raise ValueError("Redis vector stores require decode_responses=False and RESP protocol=2.")
    try:
        encoding = lookup(kwargs.get("encoding", "utf-8")).name
    except LookupError as exc:
        raise ValueError("Redis vector stores require strict UTF-8 encoding.") from exc
    if encoding != "utf-8" or kwargs.get("encoding_errors", "strict") != "strict":
        raise ValueError("Redis vector stores require strict UTF-8 encoding.")
    if kwargs.get("db", 0) != 0:
        raise ValueError("Redis vector stores require database 0; Redis Search cannot index other databases.")
    return redis_client


def _validate_operation_options(options: Mapping[str, Any] | None) -> None:
    if options:
        raise NotImplementedError("Redis vector stores do not support operation_options.")


def _prepare_namespace_component(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise ValueError("Redis namespace and collection names must contain 1 to 256 UTF-8 bytes.")
    return value.encode("utf-8").hex()


class _RedisNamespaceNames:
    """Encode and parse persisted collection names within one Redis namespace."""

    def __init__(self, namespace: str) -> None:
        base = f"af:vector:{_prepare_namespace_component(namespace)}:"
        self._index_prefix = f"{base}index:"
        self._data_prefix = f"{base}data:"

    def for_collection(self, collection_name: str) -> tuple[str, str]:
        """Return the index name and document prefix for a collection."""
        collection = _prepare_namespace_component(collection_name)
        return f"{self._index_prefix}{collection}", f"{self._data_prefix}{collection}:"

    def try_parse_index_name(self, index_name: bytes) -> str | None:
        """Return a canonical collection name, or None for foreign/malformed index names."""
        prefix = self._index_prefix.encode("ascii")
        if not index_name.startswith(prefix):
            return None
        encoded_name = index_name[len(prefix) :]
        if not 2 <= len(encoded_name) <= 512:
            return None
        try:
            name = bytes.fromhex(encoded_name.decode("ascii")).decode("utf-8")
            canonical_index, _ = self.for_collection(name)
        except ValueError:
            return None
        return name if index_name == canonical_index.encode("ascii") else None


def _prepare_vector(value: Any, field: VectorStoreField) -> np.ndarray[Any, np.dtype[Any]]:
    dtype = np.dtype(_DTYPES[field.type_ or "float32"])
    if field.dimensions is None:
        raise ValueError("Redis vector fields require dimensions.")
    if isinstance(value, (bytes, bytearray)):
        if len(value) != field.dimensions * dtype.itemsize:
            raise ValueError(f"Binary vector '{field.name}' has an invalid byte length.")
        result = np.frombuffer(value, dtype=dtype)
    else:
        source = np.asarray(value)
        if isinstance(value, Sequence) and any(isinstance(item, bool) for item in cast(Sequence[Any], value)):
            raise TypeError(f"Vector '{field.name}' must not contain booleans.")
        if source.dtype.kind not in ("i", "u", "f"):
            raise TypeError(f"Vector '{field.name}' must contain numbers, not booleans or strings.")
        with np.errstate(over="ignore"):
            result = source.astype(dtype)
    if result.ndim != 1 or result.size != field.dimensions:
        raise ValueError(f"Vector '{field.name}' must contain exactly {field.dimensions} dimensions.")
    if not np.isfinite(result).all():
        raise ValueError(f"Vector '{field.name}' must contain only finite values representable in its datatype.")
    if _METRICS[field.distance_function or "DEFAULT"] == "COSINE" and not np.any(result):
        raise ValueError(f"Cosine vector '{field.name}' must have a nonzero magnitude.")
    return result


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Redis JSON data must contain finite numbers.")
        return
    if isinstance(value, list):
        for item in cast(list[Any], value):
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in cast(dict[Any, Any], value).items():
            if not isinstance(key, str):
                raise TypeError("Redis JSON object keys must be strings.")
            _validate_json_value(item)
        return
    raise TypeError("Redis JSON data must be JSON-compatible; use HASH or a custom codec for binary data.")


def _prepare_schema_signature(schema: IndexSchema) -> dict[str, Any]:
    data = schema.to_dict()
    return {
        "prefix": data["index"]["prefix"],
        "storage_type": data["index"]["storage_type"],
        "fields": {
            field["name"]: {
                "path": field.get("path") or field["name"],
                "type": field["type"],
                "attrs": field.get("attrs", {}),
            }
            for field in data["fields"]
        },
    }


def _prepare_numeric_value(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Redis numeric filters and indexed values require numbers, not booleans.")
    if (isinstance(value, int) and abs(value) > 2**53) or not math.isfinite(value):
        raise ValueError("Redis indexed numbers must be finite; integers must be within [-2**53, 2**53].")
    return float(value)


def _prepare_tag_value(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("Redis string TAG values must be strings.")
    if value != value.strip() or _TAG_SEPARATOR in value or "\x00" in value:
        raise ValueError("Indexed Redis strings cannot have surrounding whitespace, NUL, or the TAG separator U+001F.")
    if len(value.encode("utf-8")) > 4096:
        raise ValueError("Redis TAG values cannot exceed the native 4096-byte term limit.")
    return value


def _prepare_tag_filter(name: str, value: str) -> str:
    # RedisVL's Tag equality turns an empty string into '*'; INDEXEMPTY needs an explicit empty TAG.
    return f'@{name}:{{""}}' if value == "" else f"@{name}:{{{_ESCAPER.escape(value)}}}"


def _prepare_filter_and(parts: Sequence[str]) -> str:
    return "(" + " ".join(parts) + ")" if parts else "*"


def _prepare_filter_or(parts: Sequence[str]) -> str:
    if not parts:
        raise ValueError("Redis OR expressions require at least one operand.")
    return "(" + " | ".join(parts) + ")"


def _prepare_filter_not(part: str) -> str:
    return f"(-({part}))"


def _prepare_filter_false(name: str) -> str:
    return f"(ismissing(@{name}) -ismissing(@{name}))"


def _prepare_non_null_filter(name: str, kind: str, storage_type: str) -> str:
    if storage_type == "hash":
        return _prepare_filter_not(f"ismissing(@{name})")
    if kind in ("int", "float"):
        return f"@{name}:[-inf +inf]"
    if kind == "bool":
        return f"@{name}:{{true|false}}"
    raise NotImplementedError(
        "Redis JSON TAG indexes cannot distinguish null from all non-null string/collection values "
        "without enumerating terms; this operator is unsupported."
    )


def _prepare_filter_equality(name: str, kind: str, value: Any) -> str:
    if value is None:
        raise ValueError("Use is_null/is_not_null instead of equality with None.")
    if kind in ("list", "tuple"):
        raise NotImplementedError("Redis supports string collection membership, not whole-collection equality.")
    if kind in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return _prepare_filter_false(name)
        number = _prepare_numeric_value(value)
        return f"@{name}:[{number} {number}]"
    if kind == "bool":
        return _prepare_tag_filter(name, str(value).lower()) if isinstance(value, bool) else _prepare_filter_false(name)
    return (
        _prepare_tag_filter(name, _prepare_tag_value(value)) if isinstance(value, str) else _prepare_filter_false(name)
    )


def _prepare_filter_condition(filter: Filter, field: VectorStoreField, storage_type: str) -> str:
    name = field.storage_name or field.name
    kind = field.type_ or "str"
    op, value = filter.operator, filter.value
    present = _prepare_filter_not(f"ismissing(@{name})")
    if op == "exists":
        return present
    if op in ("is_null", "is_not_null"):
        nonnull = _prepare_non_null_filter(name, kind, storage_type)
        return nonnull if op == "is_not_null" else _prepare_filter_and([present, _prepare_filter_not(nonnull)])
    if op in ("eq", "ne"):
        equals = _prepare_filter_equality(name, kind, value)
        return equals if op == "eq" else _prepare_filter_and([present, _prepare_filter_not(equals)])
    if op in ("in", "not_in"):
        # Portable membership never matches an actual null, including when None is in the supplied sequence.
        parts = [_prepare_filter_equality(name, kind, item) for item in cast(Sequence[Any], value) if item is not None]
        matches = _prepare_filter_or(parts) if parts else _prepare_filter_false(name)
        return (
            matches
            if op == "in"
            else _prepare_filter_and([_prepare_non_null_filter(name, kind, storage_type), _prepare_filter_not(matches)])
        )
    if op in ("gt", "gte", "lt", "lte", "between"):
        if kind not in ("int", "float"):
            raise NotImplementedError("Redis ordered comparisons require a numeric indexed field.")
        if op == "between":
            lower, upper = cast(Sequence[Any], value)
            return f"@{name}:[{_prepare_numeric_value(lower)} {_prepare_numeric_value(upper)}]"
        number = _prepare_numeric_value(value)
        match op:
            case "gt":
                return f"@{name}:[({number} +inf]"
            case "gte":
                return f"@{name}:[{number} +inf]"
            case "lt":
                return f"@{name}:[-inf ({number}]"
            case _:
                return f"@{name}:[-inf {number}]"
    if op in ("contains", "contains_any", "contains_all"):
        if kind not in ("list", "tuple"):
            raise NotImplementedError("Redis collection membership requires an indexed list or tuple of strings.")
        values = [value] if op == "contains" else cast(Sequence[Any], value)
        if not values and op == "contains_all":
            raise NotImplementedError("Redis cannot distinguish null from an empty TAG array for contains_all=[].")
        parts = [_prepare_tag_filter(name, _prepare_tag_value(item)) for item in values]
        if not parts:
            return _prepare_filter_false(name)
        return _prepare_filter_and(parts) if op == "contains_all" else _prepare_filter_or(parts)
    raise NotImplementedError(
        f"Redis does not support portable operator '{op}'; TEXT tokenization is not literal string matching."
    )


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class RedisCollection(BaseVectorCollection[str, ModelT], BaseVectorSearch[str, ModelT], Generic[ModelT]):
    """Store and search records in Redis HASH or JSON documents.

    Tested with Redis 8.0.3+ including Search and, for JSON, RedisJSON.
    Index creation requires INDEXMISSING and INDEXEMPTY support.
    Fields use native Redis types, with JSON encoding for unindexed HASH containers.
    Clients must use database 0, strict UTF-8 encoding, and RESP2 with binary responses.
    Caller-provided clients are borrowed.

    Scores are native distances, lower is better: DEFAULT/cosine_distance use
    COSINE, euclidean_squared_distance uses L2, and redis.ip uses 1 - dot product.
    Score thresholds are maximum distances, executed as native vector ranges.
    Keyword-hybrid and literal text filters are deliberately unsupported.
    """

    supported_key_types: ClassVar[set[str] | None] = {"str"}
    supported_vector_types: ClassVar[set[str] | None] = set(_DTYPES)
    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        redis_url: str | SecretString | None = None,
        redis_client: Redis | None = None,
        storage_type: Literal["hash", "json"] = "hash",
        namespace: str = "default",
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a collection without connecting or creating an index.

        Args:
            record_type: Registered model type, or dict with an explicit definition.
            definition: Collection schema for dictionary records.
            collection_name: Name overriding the model's collection name.
            embedding_generator: Optional local embedding generator.
            redis_url: Connection URL override. Otherwise resolved from REDIS_URL in an explicit .env file or the
                environment, then defaults to redis://localhost:6379. Used only when no client is supplied.
            redis_client: Borrowed async Redis client; the caller owns its lifetime.
            storage_type: Use binary-vector HASH documents or JSON vector arrays.
            namespace: Isolates index names and document prefixes from other stores.
            env_file_path: Optional .env file for connection settings when creating a client.
            env_file_encoding: Encoding for the .env file; defaults to UTF-8.
        """
        super().__init__(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator,
            managed_client=redis_client is None,
        )
        if storage_type not in ("hash", "json"):
            raise ValueError("storage_type must be 'hash' or 'json'.")
        self.storage_type: Literal["hash", "json"] = storage_type
        self.namespace = namespace
        self.index_name, self.key_prefix = _RedisNamespaceNames(namespace).for_collection(self.collection_name)
        self._indexed_fields: dict[str, VectorStoreField] = {}
        for field in self.definition.fields:
            name = field.storage_name or field.name
            if not _IDENTIFIER.fullmatch(name) or name.startswith("_af_"):
                raise ValueError("Redis storage names must be ASCII identifiers (up to 128 chars), excluding '_af_'.")
            if field.is_full_text_indexed:
                raise NotImplementedError("RedisCollection does not expose tokenized full-text or hybrid search.")
            if field.provider_annotations:
                raise NotImplementedError("RedisCollection does not support provider_annotations.")
            if field.field_type == "vector":
                if field.index_kind not in ("default", "flat", "hnsw"):
                    raise NotImplementedError(f"Redis does not support index kind '{field.index_kind}'.")
                if field.distance_function not in _METRICS:
                    raise NotImplementedError(f"Redis does not support distance function '{field.distance_function}'.")
            else:
                if field.type_ not in (None, "str", "bool", "int", "float", "list", "tuple", "dict", "bytes"):
                    raise NotImplementedError(f"Redis does not support data type '{field.type_}'.")
                if field.field_type == "key" or field.is_indexed:
                    if (field.type_ or "str") not in _INDEXED_TYPES:
                        raise NotImplementedError(f"Redis cannot index field '{field.name}' of type '{field.type_}'.")
                    self._indexed_fields[field.name] = field
        self.redis_client = _create_client(
            redis_url, redis_client, env_file_path=env_file_path, env_file_encoding=env_file_encoding
        )
        self._closed = False
        self._index = AsyncSearchIndex(self._prepare_schema(), redis_client=self.redis_client)

    def _prepare_schema(self) -> IndexSchema:
        fields: list[dict[str, Any]] = []

        def add(name: str, kind: str, attrs: dict[str, Any]) -> None:
            item: dict[str, Any] = {"name": name, "type": kind, "attrs": attrs}
            if self.storage_type == "json":
                item["path"] = f"$.{name}"
            fields.append(item)

        for indexed in self._indexed_fields.values():
            name = indexed.storage_name or indexed.name
            if indexed.type_ in ("int", "float"):
                add(name, "numeric", {"sortable": True, "index_missing": True})
            else:
                add(
                    name,
                    "tag",
                    {
                        "case_sensitive": True,
                        "separator": _TAG_SEPARATOR,
                        "sortable": indexed.type_ not in ("list", "tuple"),
                        "index_missing": True,
                        "index_empty": True,
                    },
                )
        for field in self.definition.vector_fields:
            add(
                field.storage_name or field.name,
                "vector",
                {
                    "algorithm": "hnsw" if field.index_kind == "default" else field.index_kind,
                    "dims": field.dimensions,
                    "distance_metric": _METRICS[field.distance_function or "DEFAULT"],
                    "datatype": "float64" if field.type_ == "float64" else "float32",
                },
            )
        return IndexSchema.from_dict({
            "index": {
                "name": self.index_name,
                "prefix": self.key_prefix,
                "key_separator": "",
                "storage_type": self.storage_type,
            },
            "fields": fields,
        })

    def _check_open(self, options: Mapping[str, Any] | None) -> None:
        _validate_operation_options(options)
        if self._closed:
            raise RuntimeError("The Redis collection is closed.")
        mark_feature_used(FeatureIndex.REDIS)

    async def _validate_schema(self) -> None:
        existing = await AsyncSearchIndex.from_existing(  # pyright: ignore[reportUnknownMemberType]
            self.index_name, redis_client=self.redis_client
        )
        if _prepare_schema_signature(existing.schema) != _prepare_schema_signature(self._index.schema):
            raise ValueError(f"Redis index '{self.index_name}' has an incompatible schema or document prefix.")

    async def _require_index(self) -> None:
        # Observe completed external lifecycle changes; validation and subsequent I/O are not atomic.
        if not await self._index.exists():
            raise IntegrationException("Redis collection does not exist; call ensure_collection_exists() first.")
        await self._validate_schema()

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create or validate the index; never overwrite an existing index."""
        self._check_open(operation_options)
        try:
            if self.storage_type == "json":
                # Read-only capability probe; PING alone does not establish RedisJSON support.
                await self.redis_client.execute_command(  # pyright: ignore[reportUnknownMemberType]
                    "JSON.TYPE", self.key_prefix + "_af_capability_probe", "$"
                )
            if not await self._index.exists():
                fields = self._index.schema.redis_fields
                for field in fields:
                    # RedisVL 0.11 emits these after SORTABLE, which Redis's parser rejects.
                    early = {"INDEXEMPTY", "INDEXMISSING"}
                    suffix = cast(list[str], field.args_suffix)  # pyright: ignore[reportUnknownMemberType]
                    field.args_suffix = [arg for arg in suffix if arg in early] + [
                        arg for arg in suffix if arg not in early
                    ]
                try:
                    await self.redis_client.ft(self.index_name).create_index(  # pyright: ignore[reportUnknownMemberType]
                        fields,
                        definition=IndexDefinition(
                            prefix=[self.key_prefix],
                            index_type=IndexType.HASH if self.storage_type == "hash" else IndexType.JSON,
                        ),
                    )
                except ResponseError as exc:
                    if str(exc) != "Index already exists":
                        raise
            await self._validate_schema()
        except (RedisError, RedisSearchError) as exc:
            raise IntegrationInitializationError(
                "Redis vector index initialization failed. Requires Redis Search with INDEXMISSING/INDEXEMPTY "
                "and RedisJSON for JSON storage (tested minimum Redis 8.0.3)."
            ) from exc

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Check index existence using Redis Search, not merely server connectivity."""
        self._check_open(operation_options)
        return await self._index.exists()

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Delete a compatible index and its documents; do not touch other prefixes."""
        self._check_open(operation_options)
        if await self._index.exists():
            await self._validate_schema()
            await self._index.delete(drop=True)

    async def close(self) -> None:
        """Close this handle and its client only when the client is owned."""
        if not self._closed:
            self._closed = True
            if self.managed_client:
                await self.redis_client.aclose()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close the collection without deleting its data."""
        await self.close()

    def _prepare_key(self, key: str) -> str:
        if not isinstance(key, str) or not key:
            raise ValueError("Redis record keys must be nonempty strings.")
        return self.key_prefix + key

    def _serialize_dicts_to_store_models(
        self,
        records: Sequence[dict[str, Any]],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[dict[str, Any]]:
        _validate_operation_options(context)
        prepared: list[dict[str, Any]] = []
        for source in records:
            record = dict(source)
            key_name = self.definition.key_field_storage_name
            if key_name not in record and self.definition.key_field.is_auto_generated:
                record[key_name] = str(uuid4())
            self._prepare_key(record[key_name])
            document: dict[str, Any] = {}
            for field in self.definition.fields:
                name = field.storage_name or field.name
                if name not in record:
                    continue
                value = record[name]
                if field.field_type == "vector" and value is not None:
                    array = _prepare_vector(value, field)
                    value = array.tobytes() if self.storage_type == "hash" else array.tolist()
                else:
                    value = self._prepare_data_value(value, field)
                document[name] = value
            prepared.append(document)
        return prepared

    def _prepare_data_value(self, value: Any, field: VectorStoreField) -> Any:
        if value is None:
            if self.storage_type == "hash":
                raise NotImplementedError("Redis HASH has no native null value; use JSON storage for nullable fields.")
            return None
        kind = field.type_ or "str"
        expected = {
            "str": (str,),
            "bool": (bool,),
            "int": (int,),
            "float": (int, float),
            "list": (list, tuple),
            "tuple": (list, tuple),
            "dict": (dict,),
            "bytes": (bytes,),
        }
        if field.field_type != "vector" and type(value) not in expected[kind]:
            raise TypeError(f"Redis field '{field.name}' requires {kind} values.")
        if field.name in self._indexed_fields:
            if kind in ("int", "float"):
                _prepare_numeric_value(value)
            elif kind == "str":
                _prepare_tag_value(value)
            elif kind in ("list", "tuple"):
                value = [_prepare_tag_value(item) for item in value]
                if self.storage_type == "hash":
                    if not value or any(item == "" for item in value):
                        raise NotImplementedError(
                            "Redis HASH TAG arrays cannot preserve empty arrays or empty elements."
                        )
                    return _TAG_SEPARATOR.join(value)
        if self.storage_type == "json":
            _validate_json_value(value)
            return value
        if kind == "bool":
            return str(value).lower()
        if kind in ("list", "tuple", "dict"):
            _validate_json_value(value)
            return msgspec.json.encode(value)
        return value

    def _deserialize_store_models_to_dicts(
        self, records: Sequence[Any], *, context: Mapping[str, Any] | None = None
    ) -> Sequence[dict[str, Any]]:
        _validate_operation_options(context)
        decoded: list[dict[str, Any]] = []
        for source in records:
            record: dict[str, Any] = {}
            for field in self.definition.fields:
                name = field.storage_name or field.name
                if name not in source:
                    continue
                value = source[name]
                if field.field_type == "vector":
                    value = self._decode_vector(value, field)
                elif self.storage_type == "hash":
                    value = self._decode_hash_data(value, field)
                record[name] = value
            decoded.append(record)
        return decoded

    def _decode_vector(self, value: Any, field: VectorStoreField) -> Any:
        if value is None:
            return None
        array = _prepare_vector(value, field)
        return array.tobytes() if field.type_ == "bytes" else array.tolist()

    def _decode_hash_data(self, value: Any, field: VectorStoreField) -> Any:
        kind = field.type_ or "str"
        if kind == "bytes":
            return value
        text = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        if kind == "str":
            return text
        if kind == "int":
            return int(text)
        if kind == "float":
            return float(text)
        if kind == "bool":
            if text not in ("true", "false"):
                raise IntegrationInvalidResponseException("Redis boolean HASH fields must contain 'true' or 'false'.")
            return text == "true"
        if field.name in self._indexed_fields:
            return text.split(_TAG_SEPARATOR)
        return msgspec.json.decode(value)

    def _prepare_filter(self, filter: FilterExpression | None) -> str:
        """Validate Redis filter support and translate the core snapshot into a native query."""
        if filter is None:
            return "*"
        if isinstance(filter, FilterGroup):
            parts = [self._prepare_filter(child) for child in filter.filters]
            match filter.operator:
                case "and":
                    return _prepare_filter_and(parts)
                case "or":
                    return _prepare_filter_or(parts)
                case "not":
                    return _prepare_filter_not(parts[0])
                case _:
                    raise ValueError(f"Unknown filter group operator '{filter.operator}'.")
        field = self._indexed_fields.get(filter.field_name)
        if field is None:
            raise NotImplementedError(
                f"Redis filters require a declared, indexed, non-vector field; got '{filter.field_name}'."
            )
        return _prepare_filter_condition(filter, field, self.storage_type)

    async def _execute_query(self, query: Query, params: Mapping[str, Any] | None = None) -> list[Any]:
        args: list[Any] = ["FT.SEARCH", self.index_name, *query.get_args()]
        if params:
            args.extend(["PARAMS", 2 * len(params)])
            for name, value in params.items():
                args.extend([name, value])
        return cast(list[Any], await self.redis_client.execute_command(*args))  # pyright: ignore[reportUnknownMemberType]

    async def _fetch_records(self, keys: Sequence[str], *, include_vectors: bool) -> list[dict[str, Any] | None]:
        fields = [f for f in self.definition.fields if include_vectors or f.field_type != "vector"]
        names = [field.storage_name or field.name for field in fields]
        records: list[dict[str, Any] | None] = []
        for start in range(0, len(keys), _BATCH_SIZE):
            async with self.redis_client.pipeline(transaction=False) as pipeline:
                for key in keys[start : start + _BATCH_SIZE]:
                    if not key.startswith(self.key_prefix):
                        raise IntegrationInvalidResponseException("Redis returned a key outside the collection prefix.")
                    if self.storage_type == "hash":
                        pipeline.exists(key)
                        pipeline.hmget(key, names)  # pyright: ignore[reportUnknownMemberType]
                    else:
                        pipeline.execute_command(  # pyright: ignore[reportUnknownMemberType]
                            "JSON.GET", key, *[f"$.{name}" for name in names]
                        )
                responses = await pipeline.execute()
            if self.storage_type == "hash":
                responses = [
                    values if exists else None for exists, values in zip(responses[::2], responses[1::2], strict=True)
                ]
            for response in responses:
                if response is None:
                    records.append(None)
                    continue
                record: dict[str, Any] = {}
                if self.storage_type == "hash":
                    record = {name: value for name, value in zip(names, response, strict=True) if value is not None}
                else:
                    values = msgspec.json.decode(response)
                    if len(names) == 1:
                        values = {f"$.{names[0]}": values}
                    for name in names:
                        matches = values.get(f"$.{name}", [])
                        if matches:
                            record[name] = matches[0]
                records.append(record)
        return records

    async def _inner_upsert(
        self, records: Sequence[Any], *, operation_options: Mapping[str, Any] | None = None
    ) -> Sequence[str]:
        self._check_open(operation_options)
        if not records:
            return []
        keys = [record[self.definition.key_field_storage_name] for record in records]
        redis_keys = [self._prepare_key(key) for key in keys]
        await self._require_index()
        for start in range(0, len(records), _BATCH_SIZE):
            async with self.redis_client.pipeline(transaction=True) as pipeline:
                for key, record in zip(
                    redis_keys[start : start + _BATCH_SIZE], records[start : start + _BATCH_SIZE], strict=True
                ):
                    if self.storage_type == "hash":
                        pipeline.delete(key)
                        pipeline.hset(key, mapping=record)  # pyright: ignore[reportUnknownMemberType]
                    else:
                        pipeline.execute_command(  # pyright: ignore[reportUnknownMemberType]
                            "JSON.SET", key, "$", msgspec.json.encode(record)
                        )
                await pipeline.execute()
        return keys

    async def _inner_get(
        self,
        *,
        keys: Sequence[str] | None = None,
        filter: FilterExpression | None = None,
        top: int = 10,
        skip: int = 0,
        order_by: Mapping[str, bool] | None = None,
        include_vectors: bool = False,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[Any]:
        self._check_open(operation_options)
        if keys is not None and not keys:
            return []
        query: Query | None = None
        redis_keys: list[str] = []
        if keys is not None:
            if order_by:
                raise NotImplementedError(
                    "Redis key lookup preserves input order; order_by requires filtered retrieval."
                )
            redis_keys = [self._prepare_key(key) for key in keys]
        else:
            ordering = order_by or {self.definition.key_field.name: True}
            if len(ordering) != 1:
                raise NotImplementedError("Redis filtered retrieval supports exactly one order_by field.")
            name, ascending = next(iter(ordering.items()))
            field = self._indexed_fields.get(name)
            if field is None or field.type_ in ("list", "tuple"):
                raise NotImplementedError("Redis ordering requires an indexed scalar field.")
            if not isinstance(ascending, bool):
                raise TypeError("order_by values must be booleans.")
            query = Query(self._prepare_filter(filter)).no_content().paging(skip, top)
            query.sort_by(field.storage_name or field.name, asc=ascending)
        await self._require_index()
        if query is not None:
            response = await self._execute_query(query)
            redis_keys = [key.decode("utf-8") for key in response[1:]]
        return [
            record
            for record in await self._fetch_records(redis_keys, include_vectors=include_vectors)
            if record is not None
        ]

    async def _inner_delete(self, keys: Sequence[str], *, operation_options: Mapping[str, Any] | None = None) -> None:
        self._check_open(operation_options)
        redis_keys = [self._prepare_key(key) for key in keys]
        if redis_keys:
            await self._require_index()
        for start in range(0, len(redis_keys), _BATCH_SIZE):
            await self.redis_client.delete(*redis_keys[start : start + _BATCH_SIZE])

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
        self._check_open(operation_options)
        if search_type != "vector" or additional_property_name is not None:
            raise NotImplementedError("RedisCollection supports dense vector search only.")
        field = self.definition.try_get_vector_field(vector_property_name)
        if field is None or vector is None:
            raise ValueError("Redis search requires a vector field and a vector or local embedding generator.")
        name = field.storage_name or field.name
        params: dict[str, Any] = {"vector": _prepare_vector(vector, field).tobytes()}
        predicate = self._prepare_filter(filter)
        if score_threshold is None:
            query_text = f"({predicate})=>[KNN {top + skip} @{name} $vector AS _af_distance]"
        else:
            if isinstance(score_threshold, bool) or not math.isfinite(score_threshold):
                raise ValueError("Redis score_threshold must be a finite distance.")
            if score_threshold < 0:
                raise NotImplementedError("Redis VECTOR_RANGE requires a non-negative distance threshold.")
            params["radius"] = score_threshold
            range_query = f"@{name}:[VECTOR_RANGE $radius $vector]=>{{$yield_distance_as: _af_distance}}"
            query_text = range_query if predicate == "*" else f"({range_query} {predicate})"
        query = Query(query_text).return_fields("_af_distance").sort_by("_af_distance").paging(skip, top)  # pyright: ignore[reportUnknownMemberType]
        await self._require_index()
        response = await self._execute_query(query, params)
        keys: list[str] = []
        scores: list[float] = []
        for position in range(1, len(response), 2):
            keys.append(response[position].decode("utf-8"))
            attributes = response[position + 1]
            attributes = dict(zip(attributes[::2], attributes[1::2], strict=True))
            score = float(attributes[b"_af_distance"])
            if not math.isfinite(score):
                raise IntegrationInvalidResponseException("Redis returned a non-finite vector distance.")
            scores.append(score)
        records = await self._fetch_records(keys, include_vectors=include_vectors)
        return SearchResults(
            [
                {"record": record, "score": score}
                for record, score in zip(records, scores, strict=True)
                if record is not None
            ],
            metadata={"distance_metric": _METRICS[field.distance_function or "DEFAULT"], "score_direction": "lower"},
        )

    def _get_record_from_result(self, result: Any) -> Any:
        return result["record"]

    def _get_score_from_result(self, result: Any) -> float:
        return result["score"]


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class RedisStore(BaseVectorStore):
    """Factory for Redis collections sharing an isolated namespace and async client."""

    def __init__(
        self,
        *,
        redis_url: str | SecretString | None = None,
        redis_client: Redis | None = None,
        storage_type: Literal["hash", "json"] = "hash",
        namespace: str = "default",
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a store; a supplied client is borrowed, never closed by the store.

        Args:
            redis_url: Connection URL override. Otherwise resolved from REDIS_URL in an explicit .env file or the
                environment, then defaults to redis://localhost:6379. Used only when no client is supplied.
            redis_client: Borrowed standalone async Redis client.
            storage_type: Default HASH or JSON format for collection handles.
            namespace: Isolates collection indexes and document keys.
            embedding_generator: Default local embedding generator for collections.
            env_file_path: Optional .env file for connection settings when creating a client.
            env_file_encoding: Encoding for the .env file; defaults to UTF-8.
        """
        super().__init__(embedding_generator=embedding_generator, managed_client=redis_client is None)
        if storage_type not in ("hash", "json"):
            raise ValueError("storage_type must be 'hash' or 'json'.")
        _prepare_namespace_component(namespace)
        self.storage_type: Literal["hash", "json"] = storage_type
        self.namespace = namespace
        self.redis_client = _create_client(
            redis_url, redis_client, env_file_path=env_file_path, env_file_encoding=env_file_encoding
        )
        self._closed = False
        self._collections: WeakSet[RedisCollection[Any]] = WeakSet()

    def get_collection(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        storage_type: Literal["hash", "json"] | None = None,
    ) -> RedisCollection[ModelT]:
        """Create a borrowed collection handle, optionally overriding the store's storage format."""
        if self._closed:
            raise RuntimeError("The Redis store is closed.")
        collection = RedisCollection(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=self.embedding_generator if embedding_generator is None else embedding_generator,
            redis_client=self.redis_client,
            namespace=self.namespace,
            storage_type=self.storage_type if storage_type is None else storage_type,
        )
        self._collections.add(collection)
        return collection

    async def list_collection_names(self, *, operation_options: Mapping[str, Any] | None = None) -> Sequence[str]:
        """List canonical collection index names in this namespace, ignoring foreign index names."""
        _validate_operation_options(operation_options)
        if self._closed:
            raise RuntimeError("The Redis store is closed.")
        mark_feature_used(FeatureIndex.REDIS)
        namespace_names = _RedisNamespaceNames(self.namespace)
        names: list[str] = []
        indexes = cast(list[bytes], await self.redis_client.execute_command("FT._LIST"))  # pyright: ignore[reportUnknownMemberType]
        for index_name in indexes:
            name = namespace_names.try_parse_index_name(index_name)
            if name is not None:
                names.append(name)
        return sorted(names)

    async def _inner_ensure_collection_deleted(
        self, collection_name: str, *, operation_options: Mapping[str, Any] | None = None
    ) -> None:
        _validate_operation_options(operation_options)
        index_name, key_prefix = _RedisNamespaceNames(self.namespace).for_collection(collection_name)
        existing = await AsyncSearchIndex.from_existing(  # pyright: ignore[reportUnknownMemberType]
            index_name, redis_client=self.redis_client
        )
        if existing.schema.index.prefix != key_prefix:
            raise ValueError("Refusing to delete a Redis index with a different document prefix.")
        await existing.delete(drop=True)

    async def close(self) -> None:
        """Close the store's owned client without deleting collections."""
        if not self._closed:
            self._closed = True
            for collection in self._collections:
                await collection.close()
            self._collections.clear()
            if self.managed_client:
                await self.redis_client.aclose()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close the store on context exit."""
        await self.close()
