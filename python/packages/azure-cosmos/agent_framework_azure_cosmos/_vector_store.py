# Copyright (c) Microsoft. All rights reserved.

"""Azure Cosmos DB for NoSQL vector collections and stores."""

from __future__ import annotations

import json
import math
import re
from collections.abc import AsyncIterable, AsyncIterator, Callable, Mapping, Sequence
from contextlib import suppress
from typing import Any, ClassVar, Generic, TypeAlias, cast
from weakref import WeakSet

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
from agent_framework._telemetry import get_user_agent, mark_feature_used
from agent_framework._vector_filters import FilterExpression
from agent_framework._vectors import EmbeddingClient, SearchType, Vector
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.serialization import AzureJSONEncoder
from azure.cosmos import PartitionKey
from azure.cosmos.aio import ContainerProxy, CosmosClient, DatabaseProxy
from azure.cosmos.exceptions import (
    CosmosHttpResponseError,
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)
from typing_extensions import TypedDict, TypeVar

from ._feature_usage import FeatureIndex

ModelT = TypeVar("ModelT", default=Any)
AzureCredentialTypes: TypeAlias = TokenCredential | AsyncTokenCredential

_ITEM_SIZE_LIMIT = 2 * 1024 * 1024
_ID_BYTE_LIMIT = 1023
_MAX_SAFE_INTEGER = 2**53 - 1
_MAX_JSON_DEPTH = 128
_VECTOR_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_VECTOR_TYPES = {
    None: "float32",
    "float": "float32",
    "float32": "float32",
    "int8": "int8",
    "uint8": "uint8",
}
_VECTOR_RANGES: dict[str, tuple[int | float, int | float, bool]] = {
    "float32": (-3.4028234663852886e38, 3.4028234663852886e38, False),
    "int8": (-128, 127, True),
    "uint8": (0, 255, True),
}
_DISTANCES = {
    "DEFAULT": "cosine",
    "cosine": "cosine",
    "cosine_similarity": "cosine",
    "dotproduct": "dotproduct",
    "dot_prod": "dotproduct",
    "euclidean": "euclidean",
    "euclidean_distance": "euclidean",
}
_INDEX_KINDS = {
    "default": "quantizedFlat",
    "flat": "flat",
    "quantized_flat": "quantizedFlat",
    "quantizedFlat": "quantizedFlat",
    "disk_ann": "diskANN",
    "diskANN": "diskANN",
}
_FIELD_ANNOTATIONS = {
    "data_type",
    "quantizer_type",
    "quantization_byte_size",
    "indexing_search_list_size",
}
_SEARCH_OPTIONS = {
    "search_list_size_multiplier",
    "quantized_vector_list_multiplier",
    "filter_priority",
    "brute_force",
}
_FILTER_SCALAR_TYPES = (str, bool, int, float)


class AzureCosmosSettings(TypedDict, total=False):
    """Cosmos connection settings resolved from explicit values, a selected .env file, or the environment."""

    endpoint: str | None
    database_name: str | None
    container_name: str | None
    key: SecretString | None


def _validate_operation_options(options: Mapping[str, Any] | None, allowed: set[str]) -> dict[str, Any]:
    result = dict(options or {})
    if unknown := result.keys() - allowed:
        raise ValueError(f"Unsupported Azure Cosmos DB option(s): {', '.join(sorted(unknown))}.")
    return result


def _validate_resource_name(value: str, kind: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise ValueError(f"Cosmos {kind} name must contain 1-255 characters.")
    return value


def _validate_credential(credential: str | SecretString | AzureCredentialTypes | None) -> None:
    if (
        credential is not None
        and not isinstance(credential, (str, SecretString))
        and not callable(getattr(credential, "get_token", None))
    ):
        raise TypeError("credential must be a key string, SecretString, TokenCredential, or AsyncTokenCredential.")


def _load_connection_settings(
    *,
    endpoint: str | None,
    database_name: str | None,
    container_name: str | None,
    credential: str | SecretString | AzureCredentialTypes | None,
    require_container: bool,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> tuple[CosmosClient, str, str | None]:
    _validate_credential(credential)
    required_fields = ["endpoint", "database_name"]
    if require_container:
        required_fields.append("container_name")
    if credential is None:
        required_fields.append("key")
    settings = load_settings(
        AzureCosmosSettings,
        env_prefix="AZURE_COSMOS_",
        required_fields=required_fields,
        endpoint=endpoint,
        database_name=database_name,
        container_name=container_name,
        key=credential if isinstance(credential, (str, SecretString)) else None,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    resolved_endpoint = settings.get("endpoint")
    resolved_database = settings.get("database_name")
    resolved_container = settings.get("container_name")
    if not isinstance(resolved_endpoint, str):
        raise TypeError("endpoint must be a string.")
    if not isinstance(resolved_database, str):
        raise TypeError("database_name must be a string.")
    _validate_resource_name(resolved_database, "database")
    if resolved_container is not None:
        _validate_resource_name(resolved_container, "container")
    resolved_credential: str | AzureCredentialTypes
    if isinstance(credential, SecretString):
        resolved_credential = credential.get_secret_value()
    elif credential is not None:
        resolved_credential = credential
    else:
        key = settings.get("key")
        if not isinstance(key, SecretString):
            raise TypeError("key must be a string or SecretString.")
        resolved_credential = key.get_secret_value()
    client = CosmosClient(
        url=resolved_endpoint,
        credential=resolved_credential,  # type: ignore[arg-type]
        user_agent_suffix=get_user_agent(),
    )
    return client, resolved_database, resolved_container


class _CosmosConnection:
    """Share one database proxy while closing only a client created by this connector."""

    def __init__(
        self,
        *,
        cosmos_client: CosmosClient | None,
        database_client: DatabaseProxy | None,
        database_name: str,
        owns_client: bool,
        create_database: bool,
    ) -> None:
        self.cosmos_client = cosmos_client
        self.database_client = database_client
        self.database_name = database_name
        self.owns_client = owns_client
        self.create_database = create_database
        self.closed = False
        self._database_ready = False

    def ensure_open(self) -> None:
        if self.closed:
            raise RuntimeError("Azure Cosmos DB vector store is closed.")

    async def get_database(self) -> DatabaseProxy:
        self.ensure_open()
        if self.database_client is not None:
            if not self._database_ready:
                await self.database_client.read()
                self._database_ready = True
            return self.database_client
        if self.cosmos_client is None:
            raise RuntimeError("Cosmos client is not initialized.")
        if self.create_database:
            try:
                self.database_client = await self.cosmos_client.create_database(id=self.database_name)
            except CosmosResourceExistsError:
                self.database_client = self.cosmos_client.get_database_client(self.database_name)
                await self.database_client.read()
        else:
            self.database_client = self.cosmos_client.get_database_client(self.database_name)
            await self.database_client.read()
        self._database_ready = True
        return self.database_client

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            if self.owns_client and self.cosmos_client is not None:
                await self.cosmos_client.close()


def _connection_from_clients(
    *,
    endpoint: str | None,
    database_name: str | None,
    credential: str | SecretString | AzureCredentialTypes | None,
    cosmos_client: CosmosClient | None,
    database_client: DatabaseProxy | None,
    create_database: bool,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> _CosmosConnection:
    if cosmos_client is not None and database_client is not None:
        raise ValueError("Provide at most one of cosmos_client or database_client.")
    if database_client is not None:
        if any(value is not None for value in (endpoint, database_name, credential, env_file_path, env_file_encoding)):
            raise ValueError(
                "database_client cannot be combined with endpoint, database_name, credential, or env_file options."
            )
        if create_database:
            raise ValueError("create_database cannot be used with an injected database_client.")
        resolved_name = getattr(database_client, "id", None)
        if not isinstance(resolved_name, str) or not resolved_name:
            raise ValueError("Injected database_client must expose a non-empty string id.")
        return _CosmosConnection(
            cosmos_client=None,
            database_client=database_client,
            database_name=resolved_name,
            owns_client=False,
            create_database=False,
        )
    if cosmos_client is not None:
        if any(value is not None for value in (endpoint, credential, env_file_path, env_file_encoding)):
            raise ValueError("cosmos_client cannot be combined with endpoint, credential, or env_file options.")
        if database_name is None:
            raise ValueError("database_name is required with an injected cosmos_client.")
        return _CosmosConnection(
            cosmos_client=cosmos_client,
            database_client=None,
            database_name=_validate_resource_name(database_name, "database"),
            owns_client=False,
            create_database=create_database,
        )
    client, resolved_database, _ = _load_connection_settings(
        endpoint=endpoint,
        database_name=database_name,
        container_name=None,
        credential=credential,
        require_container=False,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    return _CosmosConnection(
        cosmos_client=client,
        database_client=None,
        database_name=resolved_database,
        owns_client=True,
        create_database=create_database,
    )


def _property_access(name: str) -> str:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise ValueError("Cosmos field storage names must be non-empty strings without NUL.")
    return f"c[{json.dumps(name, ensure_ascii=True)}]"


def _object_projection(names: Sequence[str]) -> str:
    return "{" + ", ".join(f"{json.dumps(name, ensure_ascii=True)}: {_property_access(name)}" for name in names) + "}"


def _policy_path(name: str, suffix: str = "") -> str:
    if _VECTOR_NAME.fullmatch(name):
        return f"/{name}{suffix}"
    escaped = json.dumps(name, ensure_ascii=True)
    return f"/{escaped}{suffix}"


def _normalize_policy_path(path: Any) -> str:
    if not isinstance(path, str):
        raise ValueError("Cosmos policy paths must be strings.")
    if not path.startswith('/"'):
        return path
    escaped = False
    for index in range(2, len(path)):
        char = path[index]
        if char == '"' and not escaped:
            segment = json.loads(path[1 : index + 1])
            suffix = path[index + 1 :]
            if isinstance(segment, str) and _VECTOR_NAME.fullmatch(segment):
                return f"/{segment}{suffix}"
            return f"/{json.dumps(segment, ensure_ascii=True)}{suffix}"
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    raise ValueError(f"Invalid Cosmos policy path '{path}'.")


def _field_annotations(field: VectorStoreField) -> dict[str, Any]:
    raw = field.provider_annotations.get("azure_cosmos")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise TypeError("Vector field azure_cosmos annotations must be a mapping.")
    options = dict(cast(Mapping[str, Any], raw))
    if any(not isinstance(name, str) for name in options):
        raise TypeError("Vector field azure_cosmos annotation names must be strings.")
    if unknown := options.keys() - _FIELD_ANNOTATIONS:
        raise ValueError(f"Unsupported Azure Cosmos DB field annotation(s): {', '.join(sorted(unknown))}.")
    return options


def _prepare_vector_config(field: VectorStoreField) -> dict[str, Any]:
    storage_name = field.storage_name or field.name
    if not _VECTOR_NAME.fullmatch(storage_name):
        raise ValueError("Cosmos vector storage names must be top-level ASCII identifiers.")
    options = _field_annotations(field)
    declared_type = options.pop("data_type", field.type_)
    if declared_type is not None and not isinstance(declared_type, str):
        raise TypeError("Cosmos vector data_type must be a string.")
    if declared_type not in _VECTOR_TYPES:
        raise NotImplementedError(f"Cosmos vector field '{field.name}' requires float32, int8, or uint8 elements.")
    data_type = _VECTOR_TYPES[declared_type]
    try:
        distance = _DISTANCES[field.distance_function or "DEFAULT"]
    except KeyError:
        raise NotImplementedError(f"Unsupported Cosmos vector distance '{field.distance_function}'.") from None
    try:
        index_kind = _INDEX_KINDS[field.index_kind or "default"]
    except KeyError:
        raise NotImplementedError(f"Unsupported Cosmos vector index kind '{field.index_kind}'.") from None
    dimensions = field.dimensions
    maximum = 505 if index_kind == "flat" else 4096
    if dimensions is None or dimensions > maximum:
        raise ValueError(f"Cosmos {index_kind} vector field '{field.name}' supports at most {maximum} dimensions.")
    index_options: dict[str, Any] = {}
    quantizer_type = options.pop("quantizer_type", None)
    if quantizer_type is not None:
        if index_kind == "flat":
            raise ValueError("quantizer_type is only supported by quantizedFlat and diskANN indexes.")
        if quantizer_type not in ("product", "spherical"):
            raise ValueError("quantizer_type must be 'product' or 'spherical'.")
        index_options["quantizerType"] = quantizer_type
    quantization_bytes = options.pop("quantization_byte_size", None)
    if quantization_bytes is not None:
        if index_kind == "flat":
            raise ValueError("quantization_byte_size is only supported by quantizedFlat and diskANN indexes.")
        maximum_quantization_bytes = min(512, dimensions)
        if type(quantization_bytes) is not int or not 4 <= quantization_bytes <= maximum_quantization_bytes:
            raise ValueError(f"quantization_byte_size must be an integer between 4 and {maximum_quantization_bytes}.")
        index_options["quantizationByteSize"] = quantization_bytes
    indexing_list_size = options.pop("indexing_search_list_size", None)
    if indexing_list_size is not None:
        if index_kind != "diskANN":
            raise ValueError("indexing_search_list_size is only supported by diskANN indexes.")
        if type(indexing_list_size) is not int or not 25 <= indexing_list_size <= 500:
            raise ValueError("indexing_search_list_size must be an integer between 25 and 500.")
        index_options["indexingSearchListSize"] = indexing_list_size
    return {
        "field": field,
        "storage_name": storage_name,
        "path": f"/{storage_name}",
        "data_type": data_type,
        "distance": distance,
        "index_kind": index_kind,
        "index_options": index_options,
    }


def _prepare_schema(
    definition: VectorStoreCollectionDefinition,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    key = definition.key_field
    if key.storage_name != "id" and key.name != "id":
        raise ValueError("Cosmos vector collections require the key storage name 'id'.")
    if definition.key_field_storage_name != "id":
        raise ValueError("Cosmos vector collections require the key storage name 'id'.")
    if key.type_ != "str":
        raise ValueError("Cosmos vector collections require string keys.")
    if key.is_auto_generated:
        raise NotImplementedError("Cosmos vector collections require application-provided keys.")
    if not definition.vector_fields:
        raise ValueError("Cosmos vector collections require at least one vector field.")
    configs: dict[str, dict[str, Any]] = {}
    embeddings: list[dict[str, Any]] = []
    vector_indexes: list[dict[str, Any]] = []
    excluded_paths: list[dict[str, str]] = [{"path": "/_etag/?"}]
    for field in definition.fields:
        if field.field_type != "vector":
            if field.provider_annotations.get("azure_cosmos") is not None:
                raise ValueError("azure_cosmos field annotations are supported only on vector fields.")
            if field.is_full_text_indexed:
                raise NotImplementedError("CosmosCollection does not provide full-text or hybrid search.")
            if field.field_type == "data" and field.is_indexed is False:
                excluded_paths.append({"path": _policy_path(field.storage_name or field.name, "/*")})
            continue
        config = _prepare_vector_config(field)
        configs[field.name] = config
        embeddings.append({
            "path": config["path"],
            "dataType": config["data_type"],
            "distanceFunction": config["distance"],
            "dimensions": field.dimensions,
        })
        vector_indexes.append({
            "path": config["path"],
            "type": config["index_kind"],
            **config["index_options"],
        })
        excluded_paths.append({"path": f"{config['path']}/*"})
    vector_policy = {"vectorEmbeddings": embeddings}
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": excluded_paths,
        "vectorIndexes": vector_indexes,
    }
    return vector_policy, indexing_policy, configs


def _required_indexed_paths(definition: VectorStoreCollectionDefinition) -> set[str]:
    paths: set[str] = set()
    for field in definition.data_fields:
        if field.is_indexed is False:
            continue
        storage_name = field.storage_name or field.name
        paths.add(_normalize_policy_path(_policy_path(storage_name, "/*")))
        paths.add(_normalize_policy_path(_policy_path(storage_name, "/?")))
    return paths


def _policy_entries(policy: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    entries = policy.get(name)
    if not isinstance(entries, list):
        raise ValueError(f"Existing Cosmos policy has an invalid '{name}' value.")
    typed_entries: list[Any] = entries  # pyright: ignore[reportUnknownVariableType]
    if not all(isinstance(entry, Mapping) for entry in typed_entries):
        raise ValueError(f"Existing Cosmos policy has an invalid '{name}' value.")
    return [cast(Mapping[str, Any], entry) for entry in typed_entries]


def _validate_existing_policies(
    properties: Mapping[str, Any],
    *,
    vector_policy: Mapping[str, Any],
    indexing_policy: Mapping[str, Any],
    required_indexed_paths: set[str],
) -> None:
    partition = properties.get("partitionKey")
    if not isinstance(partition, Mapping):
        raise ValueError("Existing Cosmos container is missing its partition-key policy.")
    typed_partition = cast(Mapping[str, Any], partition)
    paths = typed_partition.get("paths")
    kind = typed_partition.get("kind")
    if paths != ["/id"] or not isinstance(kind, str) or kind.lower() != "hash":
        raise ValueError("Existing Cosmos container must use the single Hash partition key path '/id'.")

    actual_vector = properties.get("vectorEmbeddingPolicy")
    if not isinstance(actual_vector, Mapping):
        raise ValueError("Existing Cosmos container has no vector embedding policy.")
    expected_embeddings = {
        (
            _normalize_policy_path(entry.get("path")),
            str(entry.get("dataType", "")).lower(),
            str(entry.get("distanceFunction", "")).lower(),
            entry.get("dimensions"),
        )
        for entry in _policy_entries(vector_policy, "vectorEmbeddings")
    }
    actual_embeddings = {
        (
            _normalize_policy_path(entry.get("path")),
            str(entry.get("dataType", "")).lower(),
            str(entry.get("distanceFunction", "")).lower(),
            entry.get("dimensions"),
        )
        for entry in _policy_entries(cast(Mapping[str, Any], actual_vector), "vectorEmbeddings")
    }
    if actual_embeddings != expected_embeddings:
        raise ValueError("Existing Cosmos vector embedding policy is incompatible with the collection definition.")

    actual_indexing = properties.get("indexingPolicy")
    if not isinstance(actual_indexing, Mapping):
        raise ValueError("Existing Cosmos container has no indexing policy.")
    typed_indexing = cast(Mapping[str, Any], actual_indexing)
    mode = typed_indexing.get("indexingMode", "consistent")
    if not isinstance(mode, str) or mode.lower() != "consistent" or typed_indexing.get("automatic", True) is not True:
        raise ValueError("Existing Cosmos container must use automatic consistent indexing.")
    included = {_normalize_policy_path(entry.get("path")) for entry in _policy_entries(typed_indexing, "includedPaths")}
    if "/*" not in included:
        raise ValueError("Existing Cosmos indexing policy must include the root path '/*'.")
    expected_excluded = {
        _normalize_policy_path(entry.get("path")) for entry in _policy_entries(indexing_policy, "excludedPaths")
    }
    actual_excluded = {
        _normalize_policy_path(entry.get("path")) for entry in _policy_entries(typed_indexing, "excludedPaths")
    }
    if not expected_excluded <= actual_excluded:
        raise ValueError("Existing Cosmos indexing policy does not exclude all required vector paths.")
    if actual_excluded & required_indexed_paths:
        raise ValueError("Existing Cosmos indexing policy excludes a data field that must remain indexed.")

    expected_indexes = {
        _normalize_policy_path(entry.get("path")): entry for entry in _policy_entries(indexing_policy, "vectorIndexes")
    }
    actual_indexes = {
        _normalize_policy_path(entry.get("path")): entry for entry in _policy_entries(typed_indexing, "vectorIndexes")
    }
    if actual_indexes.keys() != expected_indexes.keys():
        raise ValueError("Existing Cosmos vector index paths are incompatible with the collection definition.")
    for path, expected in expected_indexes.items():
        actual = actual_indexes[path]
        if str(actual.get("type", "")).lower() != str(expected.get("type", "")).lower():
            raise ValueError(f"Existing Cosmos vector index type for '{path}' is incompatible.")
        for option in ("quantizerType", "quantizationByteSize", "indexingSearchListSize"):
            if option in expected and actual.get(option) != expected[option]:
                raise ValueError(f"Existing Cosmos vector index option '{option}' for '{path}' is incompatible.")
        actual_quantizer = actual.get("quantizerType")
        if "quantizerType" not in expected and actual_quantizer not in (None, "product"):
            raise ValueError(f"Existing Cosmos vector index quantizer for '{path}' is incompatible.")


def _validate_key(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("Cosmos item keys must be strings.")
    size = len(value.encode("utf-8"))
    if not value or size > _ID_BYTE_LIMIT or any(char in value for char in "/\\?#"):
        raise ValueError("Cosmos item keys must contain 1-1023 UTF-8 bytes and cannot contain '/', '\\', '?', or '#'.")
    return value


def _validate_json(value: Any, *, path: str, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError(f"{path} exceeds Cosmos DB's maximum JSON nesting depth of {_MAX_JSON_DEPTH}.")
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if not -_MAX_SAFE_INTEGER <= value <= _MAX_SAFE_INTEGER:
            raise ValueError(f"{path} must fit exactly in an IEEE 754 binary64 JSON number.")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite JSON numbers.")
        return
    if isinstance(value, list):
        items: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
        for index, item in enumerate(items):
            _validate_json(item, path=f"{path}[{index}]", depth=depth + 1)
        return
    if isinstance(value, dict):
        mapping: dict[Any, Any] = value  # pyright: ignore[reportUnknownVariableType]
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} object keys must be strings.")
            _validate_json(item, path=f"{path}.{key}", depth=depth + 1)
        return
    raise TypeError(f"{path} must be JSON-compatible, not {type(value).__name__}.")


def _validate_data_field(field: VectorStoreField, value: Any) -> None:
    if value is None or field.type_ is None:
        return
    kind = field.type_
    valid = (
        (kind == "str" and isinstance(value, str))
        or (kind == "bool" and type(value) is bool)
        or (kind == "int" and type(value) is int)
        or (kind == "float" and type(value) in (int, float))
        or (kind in ("list", "tuple", "set", "Sequence") and isinstance(value, list))
        or (kind == "dict" and isinstance(value, dict))
    )
    if not valid:
        raise TypeError(f"Cosmos field '{field.name}' requires a value of declared type '{kind}'.")


def _validate_vector(value: Any, config: dict[str, Any]) -> None:
    field = cast(VectorStoreField, config["field"])
    data_type = cast(str, config["data_type"])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"Cosmos vector '{field.name}' must be a dense numeric sequence.")
    typed_value: Sequence[Any] = value  # pyright: ignore[reportUnknownVariableType]
    if len(typed_value) != field.dimensions:
        raise ValueError(f"Cosmos vector '{field.name}' requires exactly {field.dimensions} dimensions.")
    minimum, maximum, integral = _VECTOR_RANGES[data_type]
    for item in typed_value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or (integral and type(item) is not int):
            raise TypeError(
                f"Cosmos {data_type} vector '{field.name}' requires "
                f"{'integer' if integral else 'numeric'} elements without booleans."
            )
        if not math.isfinite(item) or not minimum <= item <= maximum:
            raise ValueError(
                f"Cosmos {data_type} vector '{field.name}' values must be finite and within [{minimum}, {maximum}]."
            )


def _filter_value_compatible(field: VectorStoreField, value: Any) -> bool:
    if field.field_type == "key":
        return isinstance(value, str)
    return (
        field.type_ is None
        or (field.type_ == "str" and isinstance(value, str))
        or (field.type_ == "bool" and type(value) is bool)
        or (field.type_ == "int" and type(value) is int)
        or (field.type_ == "float" and type(value) in (int, float))
    )


def _validate_filter_scalar(value: Any, *, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, _FILTER_SCALAR_TYPES):
        raise NotImplementedError("Cosmos filters support only scalar string, boolean, and numeric literals.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Cosmos numeric filter values must be finite.")
    if isinstance(value, int) and not isinstance(value, bool) and not -_MAX_SAFE_INTEGER <= value <= _MAX_SAFE_INTEGER:
        raise ValueError("Cosmos integer filter values must fit exactly in IEEE 754 binary64.")


def _add_parameter(parameters: list[dict[str, Any]], value: Any, prefix: str = "filter") -> str:
    name = f"@{prefix}_{len(parameters)}"
    parameters.append({"name": name, "value": value})
    return name


def _query_metadata_hook(metadata: dict[str, Any]) -> Callable[[Mapping[str, str], Any], None]:
    def response_hook(headers: Mapping[str, str], _: Any) -> None:
        charge = headers.get("x-ms-request-charge")
        if charge is not None:
            try:
                metadata["request_charge"] = float(metadata["request_charge"]) + float(charge)
            except (TypeError, ValueError) as exc:
                raise IntegrationInvalidResponseException(
                    "Cosmos query returned an invalid request-charge header."
                ) from exc
        activity_id = headers.get("x-ms-activity-id")
        if activity_id:
            metadata["activity_id"] = activity_id
        metadata["has_more_results"] = bool(headers.get("x-ms-continuation"))

    return response_hook


async def _skip_results(
    results: AsyncIterable[Mapping[str, Any]],
    skip: int,
) -> AsyncIterator[Mapping[str, Any]]:
    index = 0
    async for result in results:
        if index < skip:
            index += 1
            continue
        yield result


class CosmosCollection(BaseVectorCollection[str, ModelT], BaseVectorSearch[str, ModelT], Generic[ModelT]):
    """An Azure Cosmos DB for NoSQL container with vector indexing and search."""

    supported_key_types: ClassVar[set[str] | None] = {"str"}
    supported_vector_types: ClassVar[set[str] | None] = {"float", "float32", "int8", "uint8"}
    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        endpoint: str | None = None,
        database_name: str | None = None,
        credential: str | SecretString | AzureCredentialTypes | None = None,
        cosmos_client: CosmosClient | None = None,
        database_client: DatabaseProxy | None = None,
        container_client: ContainerProxy | None = None,
        create_database: bool = False,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        _connection: _CosmosConnection | None = None,
    ) -> None:
        """Configure a Cosmos vector collection without contacting the service.

        Args:
            record_type: Registered vector model type, or dict with an explicit definition.
            definition: Optional collection definition for dictionary records.
            collection_name: Container name, or ``AZURE_COSMOS_CONTAINER_NAME``.
            embedding_generator: Optional local embedding client.
            endpoint: Cosmos account endpoint, or ``AZURE_COSMOS_ENDPOINT``.
            database_name: Database name, or ``AZURE_COSMOS_DATABASE_NAME``.
            credential: Caller-owned Azure credential or key, falling back to ``AZURE_COSMOS_KEY``.
            cosmos_client: Caller-owned asynchronous Cosmos account client.
            database_client: Caller-owned asynchronous Cosmos database proxy.
            container_client: Caller-owned asynchronous Cosmos container proxy.
            create_database: Allow explicit database creation during the first service operation.
            env_file_path: Optional settings file used only when no SDK client is injected.
            env_file_encoding: Settings file encoding.
        """
        if sum(client is not None for client in (cosmos_client, database_client, container_client)) > 1:
            raise ValueError("Provide at most one of cosmos_client, database_client, or container_client.")
        if _connection is not None and any(
            value is not None
            for value in (
                endpoint,
                database_name,
                credential,
                cosmos_client,
                database_client,
                container_client,
                env_file_path,
                env_file_encoding,
            )
        ):
            raise ValueError("A store-provided connection cannot be combined with connection settings or clients.")
        if _connection is not None and create_database:
            raise ValueError("Store-created collections inherit database ownership from the store.")

        resolved_name = collection_name
        owns_connection = False
        if container_client is not None:
            if (
                any(
                    value is not None
                    for value in (endpoint, database_name, credential, env_file_path, env_file_encoding)
                )
                or create_database
            ):
                raise ValueError(
                    "container_client cannot be combined with connection, database, env_file, or creation options."
                )
            client_name = getattr(container_client, "id", None)
            if isinstance(client_name, str) and client_name:
                if resolved_name is not None and resolved_name != client_name:
                    raise ValueError("collection_name must match the injected container_client id.")
                resolved_name = client_name
            self._connection = None
        elif _connection is not None:
            self._connection = _connection
        elif cosmos_client is not None or database_client is not None:
            self._connection = _connection_from_clients(
                endpoint=endpoint,
                database_name=database_name,
                credential=credential,
                cosmos_client=cosmos_client,
                database_client=database_client,
                create_database=create_database,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        else:
            registered_definition = definition or getattr(record_type, "__vectorstoremodel_definition__", None)
            configured_name = resolved_name or getattr(registered_definition, "collection_name", None)
            client, resolved_database, settings_name = _load_connection_settings(
                endpoint=endpoint,
                database_name=database_name,
                container_name=configured_name,
                credential=credential,
                require_container=True,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
            resolved_name = settings_name
            self._connection = _CosmosConnection(
                cosmos_client=client,
                database_client=None,
                database_name=resolved_database,
                owns_client=True,
                create_database=create_database,
            )
            owns_connection = True

        super().__init__(
            record_type,
            definition=definition,
            collection_name=resolved_name,
            embedding_generator=embedding_generator,
            managed_client=owns_connection,
        )
        _validate_resource_name(self.collection_name, "container")
        self._vector_policy, self._indexing_policy, self._vector_configs = _prepare_schema(self.definition)
        self._container_client = container_client
        self._container_validated = False
        self._owns_connection = owns_connection
        self._closed = False
        self._on_close: Callable[[CosmosCollection[ModelT]], None] | None = None
        self._on_delete: Callable[[str], None] | None = None

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Cosmos collection is closed.")
        if self._connection is not None:
            self._connection.ensure_open()
        mark_feature_used(FeatureIndex.AZURE_COSMOS)

    async def _get_database(self) -> DatabaseProxy:
        self._require_open()
        if self._connection is None:
            raise NotImplementedError("ContainerProxy injection does not provide database lifecycle operations.")
        return await self._connection.get_database()

    async def _read_and_validate_container(self, container: ContainerProxy) -> ContainerProxy:
        properties = await container.read()
        _validate_existing_policies(
            cast(Mapping[str, Any], properties),
            vector_policy=self._vector_policy,
            indexing_policy=self._indexing_policy,
            required_indexed_paths=_required_indexed_paths(self.definition),
        )
        self._container_validated = True
        return container

    async def _get_container(self) -> ContainerProxy:
        self._require_open()
        if self._container_client is None:
            database = await self._get_database()
            self._container_client = database.get_container_client(self.collection_name)
        if not self._container_validated:
            await self._read_and_validate_container(self._container_client)
        return self._container_client

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Check whether the configured container exists."""
        _validate_operation_options(operation_options, set())
        self._require_open()
        container = self._container_client
        if container is None:
            database = await self._get_database()
            container = database.get_container_client(self.collection_name)
        try:
            await container.read()
        except CosmosResourceNotFoundError:
            return False
        return True

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create an absent container and validate an existing container without updating it."""
        _validate_operation_options(operation_options, set())
        self._require_open()
        if self._container_client is not None and self._connection is None:
            await self._read_and_validate_container(self._container_client)
            return
        database = await self._get_database()
        container = database.get_container_client(self.collection_name)
        try:
            await container.read()
        except CosmosResourceNotFoundError:
            try:
                container = await database.create_container(
                    id=self.collection_name,
                    partition_key=PartitionKey(path="/id"),
                    indexing_policy=self._indexing_policy,
                    vector_embedding_policy=self._vector_policy,
                )
            except CosmosResourceExistsError:
                container = database.get_container_client(self.collection_name)
        self._container_client = await self._read_and_validate_container(container)

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Delete the configured container when a database proxy is available."""
        _validate_operation_options(operation_options, set())
        database = await self._get_database()
        with suppress(CosmosResourceNotFoundError):
            await database.delete_container(self.collection_name)
        self._invalidate_container()
        if self._on_delete is not None:
            self._on_delete(self.collection_name)

    def _invalidate_container(self) -> None:
        self._container_client = None
        self._container_validated = False

    def _serialize_dicts_to_store_models(
        self,
        records: Sequence[dict[str, Any]],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[Any]:
        del context
        storage_fields = {field.storage_name or field.name: field for field in self.definition.fields}
        for index, record in enumerate(records):
            missing = storage_fields.keys() - record.keys()
            if missing:
                raise ValueError(
                    f"Cosmos record at position {index} is missing field(s): {', '.join(sorted(missing))}."
                )
            _validate_key(record["id"])
            for storage_name, field in storage_fields.items():
                value = record[storage_name]
                if field.field_type == "vector":
                    if value is not None:
                        _validate_vector(value, self._vector_configs[field.name])
                else:
                    _validate_data_field(field, value)
                _validate_json(value, path=f"record[{index}].{storage_name}")
            encoded = json.dumps(
                record,
                cls=AzureJSONEncoder,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(encoded) > _ITEM_SIZE_LIMIT:
                raise ValueError(f"Cosmos record at position {index} exceeds the 2 MiB item limit.")
        return records

    def _project_item(self, item: Mapping[str, Any], include_vectors: bool) -> dict[str, Any]:
        names = self.definition.get_storage_names(include_vector_fields=include_vectors)
        try:
            return {name: item[name] for name in names}
        except KeyError as exc:
            raise IntegrationInvalidResponseException(
                f"Cosmos response is missing required field '{exc.args[0]}'."
            ) from exc

    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[str]:
        _validate_operation_options(operation_options, set())
        container = await self._get_container()
        typed_records = cast(Sequence[dict[str, Any]], records)
        keys = [cast(str, record["id"]) for record in typed_records]
        for index, record in enumerate(typed_records):
            try:
                await container.upsert_item(body=record)
            except CosmosHttpResponseError as exc:
                raise IntegrationException(
                    f"Cosmos upsert partially completed {index}/{len(records)} records; "
                    f"the failure corresponds to input index {index}. Retry with the same application keys."
                ) from exc
        return keys

    def _resolve_filter_field(self, expression: Any) -> VectorStoreField:
        if "." in expression.field_name:
            raise NotImplementedError("CosmosCollection does not support nested portable filter paths.")
        field = self.definition.try_get_field(expression.field_name)
        if field is None:
            raise ValueError(f"Unknown Cosmos filter field '{expression.field_name}'.")
        if field.field_type == "vector":
            raise NotImplementedError("Cosmos vector fields cannot be used in portable filters.")
        if field.field_type != "key" and field.is_indexed is False:
            raise ValueError(f"Cosmos filter field '{field.name}' is excluded from indexing.")
        return field

    def _translate_filter(
        self,
        expression: FilterExpression,
        parameters: list[dict[str, Any]],
    ) -> str:
        if isinstance(expression, FilterGroup):
            children = [self._translate_filter(child, parameters) for child in expression.filters]
            if expression.operator == "not":
                return f"(NOT {children[0]})"
            delimiter = " AND " if expression.operator == "and" else " OR "
            return "(" + delimiter.join(children) + ")"

        field = self._resolve_filter_field(expression)
        access = _property_access(field.storage_name or field.name)
        operator = expression.operator
        value = expression.value
        if operator == "exists":
            return f"IS_DEFINED({access})"
        if operator == "is_null":
            return f"(IS_DEFINED({access}) AND IS_NULL({access}))"
        if operator == "is_not_null":
            return f"(IS_DEFINED({access}) AND NOT IS_NULL({access}))"
        if operator in ("eq", "ne"):
            _validate_filter_scalar(value)
            if not _filter_value_compatible(field, value):
                return "false" if operator == "eq" else f"IS_DEFINED({access})"
            parameter = _add_parameter(parameters, value)
            if operator == "eq":
                return f"(IS_DEFINED({access}) AND {access} = {parameter})"
            return f"(IS_DEFINED({access}) AND (IS_NULL({access}) OR {access} != {parameter}))"
        if operator in ("gt", "gte", "lt", "lte", "between"):
            if field.type_ not in ("str", "int", "float"):
                raise NotImplementedError("Cosmos ordered filters require a declared string or numeric field.")
            values = list(value) if operator == "between" else [value]
            for item in values:
                _validate_filter_scalar(item)
                if not _filter_value_compatible(field, item):
                    raise TypeError(f"Cosmos ordered filter value is incompatible with field '{field.name}'.")
            if operator == "between":
                lower = _add_parameter(parameters, values[0])
                upper = _add_parameter(parameters, values[1])
                return (
                    f"(IS_DEFINED({access}) AND NOT IS_NULL({access}) AND {access} >= {lower} AND {access} <= {upper})"
                )
            parameter = _add_parameter(parameters, value)
            sql_operator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[operator]
            return f"(IS_DEFINED({access}) AND NOT IS_NULL({access}) AND {access} {sql_operator} {parameter})"
        if operator in ("in", "not_in"):
            values = list(cast(Sequence[Any], value))
            for item in values:
                _validate_filter_scalar(item, allow_none=True)
            if not values:
                return "false" if operator == "in" else f"(IS_DEFINED({access}) AND NOT IS_NULL({access}))"
            parameter = _add_parameter(parameters, values)
            contained = f"ARRAY_CONTAINS({parameter}, {access})"
            if operator == "in":
                return f"(IS_DEFINED({access}) AND NOT IS_NULL({access}) AND {contained})"
            return f"(IS_DEFINED({access}) AND NOT IS_NULL({access}) AND NOT {contained})"
        if operator in ("contains", "contains_any", "contains_all"):
            if field.type_ not in ("list", "tuple", "set", "Sequence"):
                raise NotImplementedError("Cosmos collection membership filters require a declared collection field.")
            values = [value] if operator == "contains" else list(cast(Sequence[Any], value))
            for item in values:
                _validate_filter_scalar(item, allow_none=True)
            if not values:
                return f"IS_ARRAY({access})" if operator == "contains_all" else "false"
            clauses = [f"ARRAY_CONTAINS({access}, {_add_parameter(parameters, item)})" for item in values]
            delimiter = " AND " if operator == "contains_all" else " OR "
            return f"(IS_ARRAY({access}) AND ({delimiter.join(clauses)}))"
        if operator in ("starts_with", "ends_with", "contains_text"):
            if field.type_ != "str":
                raise NotImplementedError("Cosmos string filters require a declared string field.")
            if not isinstance(value, str):
                raise TypeError("Cosmos string filter values must be strings.")
            parameter = _add_parameter(parameters, value)
            function = {
                "starts_with": "STARTSWITH",
                "ends_with": "ENDSWITH",
                "contains_text": "CONTAINS",
            }[operator]
            return f"(IS_STRING({access}) AND {function}({access}, {parameter}))"
        raise NotImplementedError(f"CosmosCollection does not support filter operator '{operator}'.")

    def _prepare_filter(self, expression: FilterExpression | None) -> tuple[str | None, list[dict[str, Any]]]:
        if expression is None:
            return None, []
        parameters: list[dict[str, Any]] = []
        return self._translate_filter(expression, parameters), parameters

    def _prepare_order_by(self, order_by: Mapping[str, bool] | None) -> str | None:
        if not order_by:
            return None
        if len(order_by) > 1:
            raise NotImplementedError("CosmosCollection supports one order_by field without a composite index.")
        name, ascending = next(iter(order_by.items()))
        if not isinstance(ascending, bool):
            raise TypeError(f"Order direction for field '{name}' must be a boolean.")
        field = self.definition.try_get_field(name)
        if field is None:
            raise ValueError(f"Unknown Cosmos order_by field '{name}'.")
        if field.field_type == "vector" or (field.field_type != "key" and field.is_indexed is False):
            raise ValueError(f"Cosmos order_by field '{name}' must be an indexed key or data field.")
        return f"{_property_access(field.storage_name or field.name)} {'ASC' if ascending else 'DESC'}"

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
        _validate_operation_options(operation_options, set())
        if keys is not None:
            if order_by or skip:
                raise ValueError("Cosmos point reads preserve input order and cannot use order_by or skip.")
            validated_keys = [_validate_key(key) for key in keys]
            container = await self._get_container()
            records: list[dict[str, Any]] = []
            for key in validated_keys:
                try:
                    item = await container.read_item(item=key, partition_key=key)
                except CosmosResourceNotFoundError:
                    continue
                records.append(self._project_item(cast(Mapping[str, Any], item), include_vectors))
            return records

        where, parameters = self._prepare_filter(filter)
        order = self._prepare_order_by(order_by)
        names = self.definition.get_storage_names(include_vector_fields=include_vectors)
        # Every composed expression comes from the validated collection definition.
        query = f"SELECT VALUE {_object_projection(names)} FROM c"  # nosec B608  # ruff: ignore[hardcoded-sql-expression]
        if where is not None:
            query += f" WHERE {where}"
        if order is not None:
            query += f" ORDER BY {order}"
        parameters.extend([
            {"name": "@skip", "value": skip},
            {"name": "@top", "value": top},
        ])
        query += " OFFSET @skip LIMIT @top"
        container = await self._get_container()
        items = cast(
            AsyncIterable[Mapping[str, Any]],
            container.query_items(query=query, parameters=parameters),
        )
        return [dict(item) async for item in items]

    async def _inner_delete(
        self,
        keys: Sequence[str],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        _validate_operation_options(operation_options, set())
        validated_keys = [_validate_key(key) for key in keys]
        container = await self._get_container()
        for index, key in enumerate(validated_keys):
            try:
                await container.delete_item(item=key, partition_key=key)
            except CosmosResourceNotFoundError:
                continue
            except CosmosHttpResponseError as exc:
                raise IntegrationException(
                    f"Cosmos delete partially completed {index}/{len(keys)} records; "
                    f"the failure corresponds to input index {index}. Retry with the same application keys."
                ) from exc

    def _prepare_search_options(
        self,
        config: dict[str, Any],
        operation_options: Mapping[str, Any] | None,
        parameters: list[dict[str, Any]],
    ) -> str:
        options = _validate_operation_options(operation_options, _SEARCH_OPTIONS)
        brute_force = options.pop("brute_force", False)
        if not isinstance(brute_force, bool):
            raise TypeError("brute_force must be a boolean.")
        native_options: dict[str, Any] = {}
        for name, native_name in (
            ("search_list_size_multiplier", "searchListSizeMultiplier"),
            ("quantized_vector_list_multiplier", "quantizedVectorListMultiplier"),
        ):
            value = options.pop(name, None)
            if value is not None:
                if type(value) is not int or value <= 0:
                    raise ValueError(f"{name} must be a positive integer.")
                if name == "search_list_size_multiplier" and config["index_kind"] != "diskANN":
                    raise ValueError("search_list_size_multiplier requires a diskANN vector index.")
                if config["index_kind"] == "flat":
                    raise ValueError(f"{name} is not supported by a flat vector index.")
                native_options[native_name] = value
        filter_priority = options.pop("filter_priority", None)
        if filter_priority is not None:
            if (
                type(filter_priority) not in (int, float)
                or not math.isfinite(filter_priority)
                or not 0 <= filter_priority <= 1
            ):
                raise ValueError("filter_priority must be a finite number between 0 and 1.")
            if config["index_kind"] != "diskANN":
                raise ValueError("filter_priority requires a diskANN vector index.")
            native_options["filterPriority"] = filter_priority
        if not native_options and not brute_force:
            return ""
        brute_force_parameter = _add_parameter(parameters, brute_force, "brute_force")
        options_parameter = _add_parameter(parameters, native_options, "vector_options")
        return f", {brute_force_parameter}, {options_parameter}"

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
        del values
        if search_type != "vector":
            raise NotImplementedError("CosmosCollection supports vector search only.")
        if additional_property_name is not None:
            raise ValueError("additional_property_name is only supported for keyword-hybrid search.")
        field = self.definition.try_get_vector_field(vector_property_name)
        if field is None:
            raise ValueError("Cosmos vector search requires a configured vector field.")
        if vector is None:
            raise NotImplementedError("CosmosCollection does not support server-side embedding generation.")
        config = self._vector_configs[field.name]
        if score_threshold is not None and config["distance"] == "euclidean":
            raise NotImplementedError(
                "Euclidean score_threshold is not supported because direct Cosmos VectorDistance predicates "
                "do not reliably enforce Euclidean cutoffs. Omit score_threshold to use Euclidean search."
            )
        _validate_vector(vector, config)
        parameters: list[dict[str, Any]] = [{"name": "@vector", "value": list(vector)}]
        option_arguments = self._prepare_search_options(config, operation_options, parameters)
        distance = f"VectorDistance({_property_access(config['storage_name'])}, @vector{option_arguments})"
        where, filter_parameters = self._prepare_filter(filter)
        parameters.extend(filter_parameters)
        if score_threshold is not None:
            if type(score_threshold) not in (int, float) or not math.isfinite(score_threshold):
                raise ValueError("score_threshold must be a finite number.")
            threshold_parameter = _add_parameter(parameters, score_threshold, "threshold")
            threshold = f"{distance} >= {threshold_parameter}"
            where = threshold if where is None else f"({where} AND {threshold})"
        names = self.definition.get_storage_names(include_vector_fields=include_vectors)
        result_projection = '{"record": ' + _object_projection(names) + f', "score": {distance}' + "}"
        parameters.append({"name": "@top", "value": top + skip})
        query = f"SELECT TOP @top VALUE {result_projection} FROM c"  # nosec B608  # ruff: ignore[hardcoded-sql-expression]
        if where is not None:
            query += f" WHERE {where}"
        query += f" ORDER BY {distance}"
        metadata: dict[str, Any] = {
            "score_kind": (f"{config['distance']}_{'distance' if config['distance'] == 'euclidean' else 'similarity'}"),
            "score_direction": "lower_is_better" if config["distance"] == "euclidean" else "higher_is_better",
            "request_charge": 0.0,
            "activity_id": None,
            "has_more_results": False,
        }
        container = await self._get_container()
        items = cast(
            AsyncIterable[Mapping[str, Any]],
            container.query_items(
                query=query,
                parameters=parameters,
                response_hook=_query_metadata_hook(metadata),
            ),
        )
        return SearchResults(_skip_results(items, skip), metadata=metadata)

    def _get_record_from_result(self, result: Any) -> Any:
        if not isinstance(result, Mapping):
            raise IntegrationInvalidResponseException("Cosmos vector search returned an invalid record projection.")
        typed_result = cast(Mapping[str, Any], result)
        record = typed_result.get("record")
        if not isinstance(record, Mapping):
            raise IntegrationInvalidResponseException("Cosmos vector search returned an invalid record projection.")
        return cast(Mapping[str, Any], record)

    def _get_score_from_result(self, result: Any) -> float | None:
        if not isinstance(result, Mapping):
            raise IntegrationInvalidResponseException("Cosmos vector search returned an invalid result.")
        score = cast(Mapping[str, Any], result).get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score):
            raise IntegrationInvalidResponseException("Cosmos vector search returned a missing or invalid score.")
        return float(score)

    async def close(self) -> None:
        """Close only a Cosmos client created by this collection."""
        if not self._closed:
            self._closed = True
            try:
                if self._owns_connection and self._connection is not None:
                    await self._connection.close()
            finally:
                on_close, self._on_close = self._on_close, None
                self._on_delete = None
                if on_close is not None:
                    on_close(self)

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        await self.close()


class CosmosStore(BaseVectorStore):
    """Factory and database administration for Azure Cosmos DB for NoSQL vector containers."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        database_name: str | None = None,
        credential: str | SecretString | AzureCredentialTypes | None = None,
        cosmos_client: CosmosClient | None = None,
        database_client: DatabaseProxy | None = None,
        create_database: bool = False,
        embedding_generator: EmbeddingClient | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Create a store from settings or a caller-owned asynchronous SDK client.

        Args:
            endpoint: Cosmos account endpoint, or ``AZURE_COSMOS_ENDPOINT``.
            database_name: Database name, or ``AZURE_COSMOS_DATABASE_NAME``.
            credential: Caller-owned Azure credential or key, falling back to ``AZURE_COSMOS_KEY``.
            cosmos_client: Caller-owned asynchronous Cosmos account client.
            database_client: Caller-owned asynchronous Cosmos database proxy.
            create_database: Allow explicit database creation during the first service operation.
            embedding_generator: Default local embedding client for child collections.
            env_file_path: Optional settings file used only when no SDK client is injected.
            env_file_encoding: Settings file encoding.
        """
        connection = _connection_from_clients(
            endpoint=endpoint,
            database_name=database_name,
            credential=credential,
            cosmos_client=cosmos_client,
            database_client=database_client,
            create_database=create_database,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        super().__init__(embedding_generator=embedding_generator, managed_client=connection.owns_client)
        self._connection = connection
        self.database_name = connection.database_name
        self._collections: WeakSet[CosmosCollection[Any]] = WeakSet()
        self._closed = False

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Cosmos store is closed.")
        self._connection.ensure_open()
        mark_feature_used(FeatureIndex.AZURE_COSMOS)

    def get_collection(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> CosmosCollection[ModelT]:
        """Create a child collection that borrows the store's resolved database connection."""
        self._require_open()
        collection = CosmosCollection(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator or self.embedding_generator,
            _connection=self._connection,
        )
        self._collections.add(collection)
        collection._on_close = self._collections.discard  # pyright: ignore[reportPrivateUsage]
        collection._on_delete = self._invalidate_collections  # pyright: ignore[reportPrivateUsage]
        return collection

    def _invalidate_collections(self, collection_name: str) -> None:
        for collection in list(self._collections):
            if collection.collection_name == collection_name:
                collection._invalidate_container()  # pyright: ignore[reportPrivateUsage]

    async def list_collection_names(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[str]:
        """List every container in the configured database."""
        _validate_operation_options(operation_options, set())
        self._require_open()
        database = await self._connection.get_database()
        return [
            item["id"]
            async for item in database.list_containers()  # pyright: ignore[reportUnknownMemberType]
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        ]

    async def collection_exists(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        """Check one container directly without listing the database."""
        _validate_operation_options(operation_options, set())
        self._require_open()
        database = await self._connection.get_database()
        try:
            await database.get_container_client(collection_name).read()
        except CosmosResourceNotFoundError:
            return False
        return True

    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        _validate_operation_options(operation_options, set())
        self._require_open()
        database = await self._connection.get_database()
        with suppress(CosmosResourceNotFoundError):
            await database.delete_container(collection_name)
        self._invalidate_collections(collection_name)

    async def close(self) -> None:
        """Close child collections and the owned Cosmos client, leaving injected objects open."""
        if not self._closed:
            self._closed = True
            for collection in list(self._collections):
                await collection.close()
            self._collections.clear()
            await self._connection.close()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        await self.close()
