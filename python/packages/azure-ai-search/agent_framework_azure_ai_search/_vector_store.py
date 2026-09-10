# Copyright (c) Microsoft. All rights reserved.

"""Async Azure AI Search vector collections and stores."""

from __future__ import annotations

import inspect
import json
import math
import re
from collections import Counter
from collections.abc import AsyncIterable, Callable, Mapping, Sequence
from contextlib import AsyncExitStack
from datetime import date
from functools import partial
from typing import Any, ClassVar, cast
from urllib.parse import parse_qs, urlsplit

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
from agent_framework._feature_stage import ExperimentalFeature, experimental
from agent_framework._telemetry import get_user_agent, mark_feature_used
from agent_framework._vector_filters import FilterExpression
from agent_framework._vectors import EmbeddingClient, ModelT, SearchType, Vector
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException, SettingNotFoundError
from azure.core.credentials import AzureKeyCredential, TokenCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.core.serialization import AzureJSONEncoder
from azure.search.documents import models as query_models
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    ExhaustiveKnnAlgorithmConfiguration,
    ExhaustiveKnnParameters,
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchAlias,
    SearchField,
    SearchIndex,
    VectorSearch,
    VectorSearchAlgorithmConfiguration,
    VectorSearchProfile,
)
from azure.search.documents.models import IndexingResult, VectorizableTextQuery, VectorizedQuery, VectorQuery

from ._context_provider import AzureAISearchSettings
from ._feature_usage import FeatureIndex

_SCALAR_TYPES = {"str": "Edm.String", "bool": "Edm.Boolean", "int": "Edm.Int64", "float": "Edm.Double"}
_VECTOR_RANGES: dict[str, tuple[int | float, int | float]] = {
    "Collection(Edm.Single)": (-3.4028234663852886e38, 3.4028234663852886e38),
    "Collection(Edm.Half)": (-65504.0, 65504.0),
    "Collection(Edm.Int16)": (-32768, 32767),
    "Collection(Edm.SByte)": (-128, 127),
}
_MAX_BATCH_ACTIONS = 1000
_MAX_BATCH_BYTES = 16 * 1024 * 1024
_BATCH_ENVELOPE_BYTES = len('{"value": []}')
_UPLOAD_ACTION_BYTES = len('"@search.action": "upload", ')
_PREVIEW_FIELD_OPTIONS = {
    "permission_filter",
    "sensitivity_label_id",
    "sensitivity_label_name",
    "source_document_id",
    "sharepoint_site_url",
}
_PREVIEW_INDEX_OPTIONS = {"permission_filter_option", "purview_enabled", "share_point_connector_app_registration"}
_METRICS = {
    "DEFAULT": "cosine",
    "cosine_similarity": "cosine",
    "cosine_distance": "cosine",
    "dot_prod": "dotProduct",
    "euclidean_distance": "euclidean",
}
_FIELD_OPTIONS = {
    "type",
    "sortable",
    "facetable",
    "analyzer_name",
    "search_analyzer_name",
    "index_analyzer_name",
    "synonym_map_names",
    "vector_search_profile_name",
    "stored",
    "retrievable",
}
_SEARCH_OPTIONS = {
    "exhaustive",
    "weight",
    "oversampling",
    "k_nearest_neighbors",
    "vector_filter_mode",
    "vector_threshold",
    "hybrid_search",
    "query_type",
    "semantic_configuration_name",
    "search_mode",
}
_PREVIEW_SCOPE = "https://search.azure.com/.default"
_PREVIEW_API_MINIMUMS = {
    # Supported SDK 12.x API shapes, not the service's historical introduction dates.
    "vector_threshold": "2026-05-01",
    "hybrid_search": "2026-05-01",
    "strict_post_filter": "2026-05-01",
    "query_identity": "2026-05-01",
    "permission_schema": "2026-08-01",
    "index_listing": "2026-08-01",
}


def _validate_operation_options(options: Mapping[str, Any] | None, allowed: set[str]) -> dict[str, Any]:
    result = dict(options or {})
    if unknown := result.keys() - allowed:
        raise ValueError(f"Unsupported Azure Search option(s): {', '.join(sorted(unknown))}.")
    return result


def _require_preview_request(request: Any, *, capabilities: Sequence[str]) -> None:
    # Inspect the actual SDK-selected API, including caller-supplied clients.
    url: str = request.http_request.url
    versions = parse_qs(urlsplit(url).query).get("api-version", [])
    if len(versions) != 1 or not versions[0].endswith("-preview"):
        raise NotImplementedError(
            "This option requires a preview API; the connector never overrides the SDK API version."
        )
    api_date = date.fromisoformat(versions[0].removesuffix("-preview"))
    for capability in capabilities:
        minimum = _PREVIEW_API_MINIMUMS[capability]
        if api_date < date.fromisoformat(minimum):
            raise NotImplementedError(
                f"'{capability}' requires the supported API shape {minimum}-preview or newer; "
                "the connector never overrides the SDK API version."
            )


def _model_fields(model: type[Any]) -> set[str]:
    return {name for cls in model.__mro__ for name in getattr(cls, "__annotations__", {}) if not name.startswith("_")}


def _prepare_field_type(field: VectorStoreField) -> str:
    type_ = field.type_ or "str"
    if field.field_type == "vector":
        return "Collection(Edm.Single)"
    if type_ in _SCALAR_TYPES:
        return _SCALAR_TYPES[type_]
    if type_ == "datetime":
        return "Edm.DateTimeOffset"
    if type_.startswith("list[") and type_.endswith("]") and type_[5:-1] in _SCALAR_TYPES:
        return f"Collection({_SCALAR_TYPES[type_[5:-1]]})"
    raise NotImplementedError(f"Azure Search does not support inferred field type '{type_}'; use an explicit EDM type.")


def _create_index_client(
    *,
    endpoint: str | None,
    credential: AsyncTokenCredential | AzureKeyCredential | None,
    api_key: str | SecretString | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> SearchIndexClient:
    if credential is not None and api_key is not None:
        raise ValueError("Provide credential or api_key, not both.")
    settings = load_settings(
        AzureAISearchSettings,
        env_prefix="AZURE_SEARCH_",
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
        endpoint=endpoint,
        api_key=api_key,
    )
    resolved_endpoint = settings.get("endpoint")
    if not resolved_endpoint:
        raise SettingNotFoundError("Provide endpoint or AZURE_SEARCH_ENDPOINT.")
    key = settings.get("api_key")
    if credential is None:
        if key is None:
            raise SettingNotFoundError("Provide credential, api_key, or AZURE_SEARCH_API_KEY.")
        credential = AzureKeyCredential(key.get_secret_value())
    return SearchIndexClient(resolved_endpoint, credential, user_agent=get_user_agent())


def _prepare_field_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
        raise ValueError("Azure Search field storage names must be simple ASCII identifiers.")
    return name


def _validate_vector(vector: Any, type_: str) -> None:
    if not isinstance(vector, Sequence) or isinstance(vector, (str, bytes, bytearray)):
        raise TypeError("Azure Search vectors must be dense numeric sequences, not source text/binary/sparse data.")
    minimum, maximum = _VECTOR_RANGES[type_]
    integral = isinstance(minimum, int)
    for value in cast(Sequence[object], vector):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or (integral and not isinstance(value, int)):
            raise TypeError(
                f"Azure Search {type_} vectors require non-boolean {'integer' if integral else 'numeric'} values."
            )
        if not minimum <= value <= maximum:
            raise ValueError(f"Azure Search {type_} vector values must be finite and within [{minimum}, {maximum}].")


def _prepare_filter_literal(value: Any) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("Azure Search filter numbers must be finite.")
        return str(value)
    raise TypeError("Azure Search filters require string, boolean, or finite numeric values.")


def _prepare_filter_condition(name: str, operator: str, value: Any, type_: str) -> str:
    if value is None:
        raise NotImplementedError("Azure Search cannot distinguish missing fields from explicit nulls.")
    compatible = (
        (type_ == "Edm.String" and isinstance(value, str))
        or (type_ == "Edm.Boolean" and isinstance(value, bool))
        or (type_ in ("Edm.Int32", "Edm.Int64", "Edm.Double") and type(value) in (int, float))
    )
    if not compatible:
        if operator == "eq" and isinstance(value, (str, bool, int, float)):
            return "false"
        raise TypeError("Filter value is incompatible with the Azure Search field type.")
    if operator != "eq" and type_ in ("Edm.String", "Edm.Boolean"):
        raise NotImplementedError("Azure Search only supports portable ordered comparisons on numeric fields.")
    return f"{name} {operator} {_prepare_filter_literal(value)}"


async def _close_clients(clients: Sequence[SearchClient | SearchIndexClient]) -> None:
    async with AsyncExitStack() as stack:
        for client in clients:
            stack.push_async_callback(client.close)


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class AzureAISearchCollection(BaseVectorCollection[str, ModelT], BaseVectorSearch[str, ModelT]):
    """An Azure Search index with batch CRUD and vector/keyword-hybrid retrieval.

    Credentials are always caller-owned. Clients created here are closed by ``close()``
    or the async context manager; injected clients are borrowed unless ``managed_client=True``.
    Existing indexes are never updated by ``ensure_collection_exists``.
    """

    supported_key_types: ClassVar[set[str] | None] = {"str"}
    supported_vector_types: ClassVar[set[str] | None] = {"float", "int"}
    supported_search_types: ClassVar[set[SearchType]] = {"vector", "keyword_hybrid"}

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        endpoint: str | None = None,
        credential: AsyncTokenCredential | AzureKeyCredential | None = None,
        api_key: str | SecretString | None = None,
        search_client: SearchClient | None = None,
        index_client: SearchIndexClient | None = None,
        managed_client: bool | None = None,
        vector_search: VectorSearch | None = None,
        index_options: Mapping[str, Any] | None = None,
        is_alias: bool = False,
        allow_preview: bool = False,
        query_source_credential: TokenCredential | AsyncTokenCredential | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Configure an index client without contacting the service.

        Args:
            record_type: Registered model type, or dict with an explicit definition.
            definition: Optional dictionary model definition.
            collection_name: Index name (or an existing alias when is_alias=True).
            embedding_generator: Optional local embedding client.
            endpoint: Service endpoint, falling back to AZURE_SEARCH_ENDPOINT.
            credential: Caller-owned async Azure token or key credential.
            api_key: API key, falling back to AZURE_SEARCH_API_KEY.
            search_client: Borrowed document client; may be used without an index client.
                Injected clients bypass settings and cannot be combined with connection or file overrides.
            index_client: Borrowed index administration client, mutually exclusive with connection/file overrides.
            managed_client: Explicitly take ownership of injected clients when True.
            vector_search: Native SDK profiles, algorithms, vectorizers and compression.
            index_options: Native SDK SearchIndex configuration, excluding name/fields/vector_search.
            is_alias: Use an existing index alias; disallow index creation/deletion.
            allow_preview: Explicitly enable preview controls when the installed SDK supports them.
            query_source_credential: Caller identity for permission-filtered reads; requires preview SDK support.
            env_file_path: Optional settings file.
            env_file_encoding: Settings file encoding (defaults to UTF-8).
        """
        if query_source_credential is not None and not callable(getattr(query_source_credential, "get_token", None)):
            raise TypeError("query_source_credential must be an Azure TokenCredential or AsyncTokenCredential.")
        if (index_client is not None or search_client is not None) and any(
            value is not None for value in (endpoint, credential, api_key, env_file_path, env_file_encoding)
        ):
            raise ValueError(
                "Injected clients cannot be combined with endpoint, credential, api_key, or env_file options."
            )
        super().__init__(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator,
            managed_client=managed_client if managed_client is not None else False,
        )
        if self.definition.key_field.is_auto_generated:
            raise NotImplementedError("Azure Search requires application-provided string keys.")
        self._vector_search = vector_search
        self._index_options = dict(index_options or {})
        self._preview_schema = bool(self._index_options.keys() & _PREVIEW_INDEX_OPTIONS)
        if self._preview_schema and not allow_preview:
            raise NotImplementedError("Permission-aware index configuration requires allow_preview=True.")
        if self._index_options.keys() & {"name", "fields", "vector_search"}:
            raise ValueError("index_options cannot replace name, fields, or vector_search.")
        unknown = self._index_options.keys() - SearchIndex.__annotations__.keys()
        if unknown:
            raise ValueError(f"Unknown SearchIndex options: {', '.join(sorted(unknown))}.")
        self.is_alias = is_alias
        self.allow_preview = allow_preview
        self.query_source_credential = query_source_credential
        self._field_types: dict[str, str] = {}
        self._fields = self._prepare_fields()
        self._closed = False
        self._on_close: Callable[[AzureAISearchCollection[ModelT]], None] | None = None
        self._owned_clients: list[SearchClient | SearchIndexClient] = []
        if index_client is None and search_client is None:
            index_client = _create_index_client(
                endpoint=endpoint,
                credential=credential,
                api_key=api_key,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
            self._owned_clients.append(index_client)
        elif index_client is not None and managed_client:
            self._owned_clients.append(index_client)
        self.index_client = index_client
        if search_client is None:
            if index_client is None:
                raise ValueError("An index_client or search_client is required.")
            search_client = index_client.get_search_client(self.collection_name, user_agent=get_user_agent())
            self._owned_clients.append(search_client)
        elif managed_client:
            self._owned_clients.append(search_client)
        self.search_client = search_client
        self.managed_client = bool(self._owned_clients)

    def _prepare_fields(self) -> list[SearchField]:
        fields: list[SearchField] = []
        for field in self.definition.fields:
            name = _prepare_field_name(field.storage_name or field.name)
            options = _validate_operation_options(
                field.provider_annotations.get("azure_ai_search"), _FIELD_OPTIONS | _PREVIEW_FIELD_OPTIONS
            )
            for option in options.keys() & _PREVIEW_FIELD_OPTIONS:
                if not self.allow_preview or option not in _model_fields(SearchField):
                    raise NotImplementedError(f"'{option}' requires preview opt-in and a supporting Search SDK.")
                self._preview_schema = True
            type_ = options.pop("type", None) or _prepare_field_type(field)
            if not isinstance(type_, str):
                raise TypeError("Azure Search field type must be an EDM type string.")
            if field.field_type == "key" and type_ != "Edm.String":
                raise ValueError("Azure Search keys must use Edm.String.")
            if field.field_type != "vector" and options.get("retrievable") is False:
                raise ValueError("Key and data fields must be retrievable to reconstruct records.")
            if field.field_type == "vector":
                if type_ not in _VECTOR_RANGES:
                    raise NotImplementedError(
                        "Azure Search vector fields require a supported dense numeric collection."
                    )
                if (
                    field.is_indexed
                    or options.get("sortable")
                    or options.get("facetable")
                    or options.get("synonym_map_names")
                    or any(
                        options.get(option) is not None
                        for option in (
                            "analyzer_name",
                            "search_analyzer_name",
                            "index_analyzer_name",
                        )
                    )
                ):
                    raise ValueError(
                        "Azure Search vector fields cannot be filterable, sortable, facetable, or analyzed."
                    )
                if options.get("retrievable") is None:
                    options["retrievable"] = options.get("stored") is not False
                if options.get("stored") is False and options["retrievable"] is not False:
                    raise ValueError("Azure Search vector fields with stored=False require retrievable=False.")
                if field.index_kind not in ("default", "hnsw", "flat"):
                    raise NotImplementedError(f"Unsupported Azure Search vector index kind '{field.index_kind}'.")
                if field.distance_function not in _METRICS:
                    raise NotImplementedError(f"Unsupported Azure Search metric '{field.distance_function}'.")
                options.setdefault("vector_search_profile_name", f"{name}_profile")
                options["vector_search_dimensions"] = field.dimensions
            elif type_ not in {
                *_SCALAR_TYPES.values(),
                "Edm.Int32",
                "Edm.DateTimeOffset",
                *(f"Collection({t})" for t in _SCALAR_TYPES.values()),
            }:
                raise NotImplementedError(f"Unsupported Azure Search data field type '{type_}'.")
            self._field_types[name] = type_
            fields.append(
                SearchField(
                    name=name,
                    type=type_,
                    key=field.field_type == "key",
                    searchable=field.field_type == "vector" or bool(field.is_full_text_indexed),
                    filterable=field.field_type == "key" or bool(field.is_indexed),
                    **options,
                )
            )
        return fields

    def build_index(self) -> SearchIndex:
        """Build the SDK index schema; no remote index is modified."""
        vector_search = self._vector_search
        if vector_search is None and self.definition.vector_fields:
            algorithms: list[VectorSearchAlgorithmConfiguration] = []
            profiles: list[VectorSearchProfile] = []
            for field in self.definition.vector_fields:
                name = field.storage_name or field.name
                metric = _METRICS[field.distance_function or "DEFAULT"]
                algorithm = (
                    ExhaustiveKnnAlgorithmConfiguration(
                        name=f"{name}_algorithm", parameters=ExhaustiveKnnParameters(metric=metric)
                    )
                    if field.index_kind == "flat"
                    else HnswAlgorithmConfiguration(name=f"{name}_algorithm", parameters=HnswParameters(metric=metric))
                )
                algorithms.append(algorithm)
                profiles.append(
                    VectorSearchProfile(name=f"{name}_profile", algorithm_configuration_name=algorithm.name)
                )
            vector_search = VectorSearch(algorithms=algorithms, profiles=profiles)
        if vector_search is not None:
            profiles_by_name = {p.name for p in vector_search.profiles or []}
            for field in self._fields:
                if field.vector_search_profile_name and field.vector_search_profile_name not in profiles_by_name:
                    raise ValueError(f"Missing vector search profile '{field.vector_search_profile_name}'.")
        return SearchIndex(
            name=self.collection_name, fields=self._fields, vector_search=vector_search, **self._index_options
        )

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Azure Search collection is closed.")
        mark_feature_used(FeatureIndex.AZURE_AI_SEARCH)

    def _require_index_client(self, *, mutate: bool = False) -> SearchIndexClient:
        self._require_open()
        if mutate and self.is_alias:
            raise NotImplementedError("Index lifecycle operations through an alias are not supported.")
        if self.index_client is None:
            raise NotImplementedError("Index lifecycle operations require an index_client.")
        return self.index_client

    async def collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> bool:
        """Check the index or explicitly selected alias without listing the service."""
        _validate_operation_options(operation_options, set())
        client = self._require_index_client()
        try:
            if self.is_alias:
                await client.get_alias(self.collection_name)
            else:
                await client.get_index(self.collection_name)
        except ResourceNotFoundError:
            return False
        return True

    async def ensure_collection_exists(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Create an absent index; never update an existing index."""
        _validate_operation_options(operation_options, set())
        client = self._require_index_client(mutate=True)
        if await self.collection_exists():
            return
        try:
            options: dict[str, Any] = (
                {"raw_request_hook": partial(_require_preview_request, capabilities=("permission_schema",))}
                if self._preview_schema
                else {}
            )
            await client.create_index(self.build_index(), **options)
        except ResourceExistsError:
            # A concurrent creator won; do not overwrite its schema.
            return

    async def ensure_collection_deleted(self, *, operation_options: Mapping[str, Any] | None = None) -> None:
        """Delete an index, treating an already absent index as success."""
        _validate_operation_options(operation_options, set())
        client = self._require_index_client(mutate=True)
        try:
            await client.delete_index(self.collection_name)
        except ResourceNotFoundError:
            return

    async def close(self) -> None:
        """Close owned clients, but never caller-owned credentials."""
        if not self._closed:
            self._closed = True
            try:
                await _close_clients(self._owned_clients)
            finally:
                on_close, self._on_close = self._on_close, None
                if on_close is not None:
                    on_close(self)

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        await self.close()

    def _serialize_dicts_to_store_models(
        self,
        records: Sequence[dict[str, Any]],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[Any]:
        vector_names = [f.storage_name or f.name for f in self.definition.vector_fields]
        for record in records:
            self._validate_key(record[self.definition.key_field_storage_name])
            for name in vector_names:
                value = record.get(name)
                if value is not None:
                    _validate_vector(value, self._field_types[name])
        return records

    @staticmethod
    def _validate_key(key: Any) -> None:
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_=-]{1,1024}", key) or key.startswith("_"):
            raise ValueError(
                "Azure Search keys must contain 1-1024 ASCII letters, digits, '-', '_', or '=', "
                "and cannot start with '_'."
            )

    def _prepare_filter(self, filter: FilterExpression | None) -> str | None:
        if filter is None:
            return None
        if isinstance(filter, FilterGroup):
            children = [self._prepare_filter(child) for child in filter.filters]
            if filter.operator == "not":
                return f"not ({children[0]})"
            return "(" + f" {filter.operator} ".join(str(child) for child in children) + ")"

        field = self.definition.try_get_field(filter.field_name)
        if field is None:
            raise NotImplementedError("Azure Search does not support nested portable field paths.")
        name = _prepare_field_name(field.storage_name or field.name)
        op, value = filter.operator, filter.value
        if op == "azure_ai_search.match":
            if not field.is_full_text_indexed or not isinstance(value, str):
                raise ValueError("azure_ai_search.match requires a full-text-indexed string field and string query.")
            return f"search.ismatch({_prepare_filter_literal(value)}, {_prepare_filter_literal(name)}, 'simple', 'any')"
        if field.field_type == "vector" or (field.field_type != "key" and not field.is_indexed):
            raise ValueError(f"Field '{field.name}' must be filterable for portable filtering.")
        if op in ("exists", "is_null", "is_not_null", "ne"):
            raise NotImplementedError(
                f"Portable '{op}' cannot preserve missing-versus-null semantics in Azure Search. "
                "Use explicit NOT groups for negation, whose missing-field semantics differ from 'ne'."
            )
        if op in ("starts_with", "ends_with", "contains_text"):
            raise NotImplementedError(
                f"Azure Search cannot implement literal '{op}'. "
                "Use azure_ai_search.match for tokenized full-text search."
            )
        type_ = self._field_types[name]
        if type_ == "Edm.DateTimeOffset":
            raise NotImplementedError("Portable date comparisons are not supported by AzureAISearchCollection.")
        if op in ("contains", "contains_any", "contains_all"):
            if type_ != "Collection(Edm.String)":
                raise NotImplementedError("Portable collection membership supports only string collection fields.")
            values = [value] if op == "contains" else value
            if not values:
                if op == "contains_all":
                    raise NotImplementedError(
                        "Empty contains_all cannot distinguish an absent collection from an empty one."
                    )
                return "false"
            comparisons = [_prepare_filter_condition("v", "eq", item, "Edm.String") for item in values]
            clauses = [
                f"{name}/any(v: {comparison})" if comparison != "false" else "false" for comparison in comparisons
            ]
            return "(" + (" and " if op == "contains_all" else " or ").join(clauses) + ")"
        if type_.startswith("Collection("):
            raise NotImplementedError("Azure Search collection fields support membership, not scalar comparisons.")
        if op in ("eq", "gt", "gte", "lt", "lte"):
            return _prepare_filter_condition(name, {"gte": "ge", "lte": "le"}.get(op, op), value, type_)
        if op == "between":
            lower = _prepare_filter_condition(name, "ge", value[0], type_)
            upper = _prepare_filter_condition(name, "le", value[1], type_)
            return f"({lower} and {upper})"
        if op in ("in", "not_in"):
            comparisons = [_prepare_filter_condition(name, "eq", item, type_) for item in value]
            contained = "(" + " or ".join(comparisons) + ")" if comparisons else "false"
            return contained if op == "in" else f"({name} ne null and not ({contained}))"
        raise NotImplementedError(f"Azure Search does not support filter operator '{op}'.")

    def _prepare_projection(self, include_vectors: bool) -> list[str]:
        if include_vectors and any(f.retrievable is False for f in self._fields):
            raise ValueError("include_vectors=True requires retrievable fields.")
        return self.definition.get_storage_names(include_vector_fields=include_vectors)

    async def _prepare_identity_options(self, capabilities: Sequence[str] = ()) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if capabilities:
            options["raw_request_hook"] = partial(_require_preview_request, capabilities=tuple(capabilities))
        if self.query_source_credential is None:
            return options
        if (
            not self.allow_preview
            or "query_source_authorization" not in inspect.signature(SearchClient.search).parameters
        ):
            raise NotImplementedError("Query identity requires allow_preview=True and a supporting preview Search SDK.")
        token = self.query_source_credential.get_token(_PREVIEW_SCOPE)
        if inspect.isawaitable(token):
            token = await token
        if not token.token:
            raise ValueError("query_source_credential returned an empty authorization token.")
        return {
            "query_source_authorization": token.token,
            "raw_request_hook": partial(_require_preview_request, capabilities=(*capabilities, "query_identity")),
        }

    @staticmethod
    def _check_batch(results: Sequence[IndexingResult], expected: Sequence[str]) -> None:
        if len(results) != len(expected) or Counter(r.key for r in results) != Counter(expected):
            raise IntegrationInvalidResponseException("Azure Search returned an unexpected set of indexing results.")
        if failures := [r for r in results if not r.succeeded]:
            # Do not include server messages, which can echo document contents.
            details = ", ".join(str(r.status_code) for r in failures)
            raise IntegrationException(
                f"Azure Search partially failed {len(failures)}/{len(results)} indexing actions "
                f"(status codes: {details}). The batch is not atomic; retry with the same application keys."
            )

    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[str]:
        self._require_open()
        _validate_operation_options(operation_options, set())
        keys: list[str] = []
        batch_ends: list[int] = []
        start = 0
        batch_size = _BATCH_ENVELOPE_BYTES
        # Match SDK JSON spacing/escaping and action metadata without copying vector payloads.
        # ensure_ascii=True makes character counts identical to UTF-8 byte counts.
        for index, record in enumerate(records):
            action_size = len(json.dumps(record, cls=AzureJSONEncoder, ensure_ascii=True)) + _UPLOAD_ACTION_BYTES
            if action_size + _BATCH_ENVELOPE_BYTES > _MAX_BATCH_BYTES:
                raise ValueError(f"Azure Search document at position {index} exceeds the 16 MiB indexing limit.")
            if (
                index - start == _MAX_BATCH_ACTIONS
                or batch_size + action_size + (2 if index > start else 0) > _MAX_BATCH_BYTES
            ):
                batch_ends.append(index)
                start, batch_size = index, _BATCH_ENVELOPE_BYTES
            batch_size += action_size + (2 if index > start else 0)
            keys.append(record[self.definition.key_field_storage_name])
        if records:
            batch_ends.append(len(records))
        # Complete size preflight before the first upload, including later oversized documents.
        start = 0
        for end in batch_ends:
            batch = list(records[start:end])
            results = await self.search_client.upload_documents(batch)  # pyright: ignore[reportUnknownMemberType]
            self._check_batch(results, keys[start:end])
            start = end
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
        self._require_open()
        _validate_operation_options(operation_options, set())
        select = self._prepare_projection(include_vectors)
        if keys is not None:
            if order_by or skip:
                raise ValueError("Key lookup preserves input order and cannot use order_by or skip.")
            for key in keys:
                self._validate_key(key)
            identity = await self._prepare_identity_options()
            found: dict[str, Any] = {}
            # Search (rather than lookup) applies document permission filtering and batches keys.
            for offset in range(0, len(keys), 100):
                key_filter = " or ".join(
                    f"{self.definition.key_field_storage_name} eq {_prepare_filter_literal(key)}"
                    for key in keys[offset : offset + 100]
                )
                results = cast(
                    AsyncIterable[dict[str, Any]],
                    await self.search_client.search(
                        search_text="*", filter=key_filter, select=select, top=100, **identity
                    ),
                )
                async for record in results:
                    found[record[self.definition.key_field_storage_name]] = record
            return [found[key] for key in keys if key in found]
        if skip > 100000:
            raise ValueError("Azure Search skip cannot exceed 100000.")
        order: list[str] = []
        for name, ascending in (order_by or {}).items():
            if not isinstance(ascending, bool):
                raise TypeError(f"Order direction for field '{name}' must be a boolean.")
            field = self.definition.try_get_field(name)
            if field is None:
                raise ValueError(f"Unknown ordering field '{name}'.")
            storage_name = field.storage_name or field.name
            sdk_field = next(f for f in self._fields if f.name == storage_name)
            if not sdk_field.sortable:
                raise ValueError(f"Ordering field '{name}' must be configured sortable.")
            order.append(f"{storage_name} {'asc' if ascending else 'desc'}")
        prepared_filter = self._prepare_filter(filter)
        identity = await self._prepare_identity_options()
        results = cast(
            AsyncIterable[dict[str, Any]],
            await self.search_client.search(
                search_text="*",
                filter=prepared_filter,
                top=top,
                skip=skip,
                select=select,
                order_by=order or None,
                **identity,
            ),
        )
        return [record async for record in results]

    async def _inner_delete(self, keys: Sequence[str], *, operation_options: Mapping[str, Any] | None = None) -> None:
        self._require_open()
        _validate_operation_options(operation_options, set())
        for key in keys:
            self._validate_key(key)
        for offset in range(0, len(keys), _MAX_BATCH_ACTIONS):
            batch = keys[offset : offset + _MAX_BATCH_ACTIONS]
            results = await self.search_client.delete_documents(  # pyright: ignore[reportUnknownMemberType]
                [{self.definition.key_field_storage_name: key} for key in batch]
            )
            self._check_batch(results, batch)

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
        self._require_open()
        options = _validate_operation_options(operation_options, _SEARCH_OPTIONS)
        preview_capabilities: list[str] = []
        field = self.definition.try_get_vector_field(vector_property_name)
        if field is None:
            raise ValueError("Azure Search requires a configured vector field.")
        if skip + top > 10000:
            raise ValueError("Azure Search vector result window cannot exceed 10000.")
        k = options.pop("k_nearest_neighbors", max(1, top + skip))
        if type(k) is not int or k < max(1, top + skip) or k > 10000:
            raise ValueError("k_nearest_neighbors must be between max(1, top + skip) and 10000.")
        query_options = {key: options.pop(key) for key in ("exhaustive", "weight", "oversampling") if key in options}
        if "exhaustive" in query_options and not isinstance(query_options["exhaustive"], bool):
            raise TypeError("exhaustive must be a boolean.")
        if "query_type" in options and options["query_type"] not in ("simple", "full", "semantic"):
            raise ValueError("query_type must be simple, full, or semantic.")
        if "search_mode" in options and options["search_mode"] not in ("any", "all"):
            raise ValueError("search_mode must be any or all.")
        for name, minimum in (("weight", 0), ("oversampling", 1)):
            if name in query_options:
                value = query_options[name]
                if type(value) not in (int, float) or not math.isfinite(value) or value < minimum or value == 0:
                    raise ValueError(f"Invalid Azure Search {name}.")
        native_threshold = options.pop("vector_threshold", None)
        if score_threshold is not None:
            if native_threshold is not None:
                raise ValueError("score_threshold and vector_threshold cannot be combined.")
            if search_type != "vector" or options.get("query_type") == "semantic":
                raise NotImplementedError("score_threshold is only supported for a single pure-vector query.")
            if type(score_threshold) not in (int, float) or not math.isfinite(score_threshold):
                raise ValueError("score_threshold must be finite.")
            threshold_type = getattr(query_models, "SearchScoreThreshold", None)
            if threshold_type is None:
                raise NotImplementedError("Native score thresholds require a supporting preview Search SDK.")
            native_threshold = threshold_type(value=score_threshold)
        if native_threshold is not None:
            threshold_base = getattr(query_models, "VectorThreshold", None)
            if not self.allow_preview or threshold_base is None or "threshold" not in _model_fields(VectorQuery):
                raise NotImplementedError("Vector thresholds require allow_preview=True and a supporting preview SDK.")
            threshold_types = tuple(
                cls
                for name in ("SearchScoreThreshold", "VectorSimilarityThreshold")
                if (cls := getattr(query_models, name, None)) is not None
            )
            if not isinstance(native_threshold, threshold_types):
                raise TypeError("vector_threshold must be an SDK SearchScoreThreshold or VectorSimilarityThreshold.")
            if type(native_threshold.value) not in (int, float) or not math.isfinite(native_threshold.value):
                raise ValueError("vector_threshold must contain a finite numeric value.")
            query_options["threshold"] = native_threshold
            preview_capabilities.append("vector_threshold")
        mode = options.setdefault("vector_filter_mode", "preFilter")
        if mode not in ("preFilter", "postFilter", "strictPostFilter"):
            raise ValueError("Unsupported vector_filter_mode.")
        if mode == "strictPostFilter" and (not self.allow_preview or "threshold" not in _model_fields(VectorQuery)):
            raise NotImplementedError("strictPostFilter requires explicit preview opt-in and a preview Search SDK.")
        if mode == "strictPostFilter":
            preview_capabilities.append("strict_post_filter")
        if "hybrid_search" in options:
            hybrid_type = getattr(query_models, "HybridSearch", None)
            if (
                not self.allow_preview
                or hybrid_type is None
                or "hybrid_search" not in inspect.signature(SearchClient.search).parameters
            ):
                raise NotImplementedError("hybrid_search requires explicit preview opt-in and a supporting SDK.")
            if search_type != "keyword_hybrid" or not isinstance(options["hybrid_search"], hybrid_type):
                raise ValueError("hybrid_search requires keyword_hybrid and an Azure SDK HybridSearch model.")
            preview_capabilities.append("hybrid_search")
        if vector is not None:
            _validate_vector(vector, "Collection(Edm.Single)")
            query: VectorQuery = VectorizedQuery(
                vector=list(vector), fields=field.storage_name or field.name, k_nearest_neighbors=k, **query_options
            )
        else:
            if not isinstance(values, str):
                raise TypeError("Integrated Azure Search query vectorization requires text.")
            query = VectorizableTextQuery(
                text=values, fields=field.storage_name or field.name, k_nearest_neighbors=k, **query_options
            )
        search_fields: list[str] | None = None
        if search_type == "keyword_hybrid":
            if not isinstance(values, str):
                raise TypeError("Keyword-hybrid search requires text values.")
            if additional_property_name is not None:
                text_field = self.definition.try_get_field(additional_property_name)
                if text_field is None or not text_field.is_full_text_indexed:
                    raise ValueError("additional_property_name must identify a full-text-indexed field.")
                search_fields = [text_field.storage_name or text_field.name]
            else:
                search_fields = [
                    f.storage_name or f.name for f in self.definition.data_fields if f.is_full_text_indexed
                ]
                if not search_fields:
                    raise ValueError("Keyword-hybrid search requires a full-text-indexed data field.")
        elif additional_property_name is not None:
            raise ValueError("additional_property_name is only supported for keyword-hybrid search.")
        prepared_filter = self._prepare_filter(filter)
        select = self._prepare_projection(include_vectors)
        identity = await self._prepare_identity_options(preview_capabilities)
        options.update(identity)
        results = cast(
            AsyncIterable[dict[str, Any]],
            await self.search_client.search(
                search_text=values if search_type == "keyword_hybrid" else None,
                vector_queries=[query],
                filter=prepared_filter,
                top=top,
                skip=skip,
                select=select,
                search_fields=search_fields,
                **options,
            ),
        )
        return SearchResults(
            results, metadata={"score_kind": "rrf" if search_type == "keyword_hybrid" else "search_score"}
        )

    def _get_record_from_result(self, result: Any) -> Any:
        return result

    def _get_score_from_result(self, result: Any) -> float | None:
        score = result.get("@search.score")
        if score is None or type(score) not in (int, float) or not math.isfinite(score):
            raise IntegrationInvalidResponseException("Azure Search returned a missing or invalid @search.score.")
        return float(score)


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class AzureAISearchStore(BaseVectorStore):
    """Factory and index administration for an Azure AI Search service.

    Closing a store closes its collection clients and its owned index client.
    Injected index clients and credentials remain caller-owned by default.
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        credential: AsyncTokenCredential | AzureKeyCredential | None = None,
        api_key: str | SecretString | None = None,
        index_client: SearchIndexClient | None = None,
        embedding_generator: EmbeddingClient | None = None,
        managed_client: bool | None = None,
        allow_preview: bool = False,
        query_source_credential: TokenCredential | AsyncTokenCredential | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Create a store using explicit credentials, environment settings, or a borrowed SDK client.

        Args:
            endpoint: Service URL, or AZURE_SEARCH_ENDPOINT.
            credential: Caller-owned async token or key credential.
            api_key: Plain or masked key, or AZURE_SEARCH_API_KEY.
            index_client: Borrowed SDK index client, mutually exclusive with connection/file overrides.
                Bypasses environment and file settings.
            embedding_generator: Default local embedding client for collections.
            managed_client: Take ownership of an injected index client when True.
            allow_preview: Permit explicitly requested, SDK-supported preview capabilities.
            query_source_credential: Caller identity forwarded on every collection read.
            env_file_path: Optional settings file.
            env_file_encoding: Settings file encoding (defaults to UTF-8).
        """
        if query_source_credential is not None and not callable(getattr(query_source_credential, "get_token", None)):
            raise TypeError("query_source_credential must be an Azure TokenCredential or AsyncTokenCredential.")
        if index_client is not None and any(
            value is not None for value in (endpoint, credential, api_key, env_file_path, env_file_encoding)
        ):
            raise ValueError(
                "Injected clients cannot be combined with endpoint, credential, api_key, or env_file options."
            )
        owned = index_client is None or managed_client is True
        super().__init__(embedding_generator=embedding_generator, managed_client=owned)
        self.index_client = (
            index_client
            if index_client is not None
            else _create_index_client(
                endpoint=endpoint,
                credential=credential,
                api_key=api_key,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        )
        self.allow_preview = allow_preview
        self.query_source_credential = query_source_credential
        self._collections: dict[AzureAISearchCollection[Any], None] = {}
        self._closed = False

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Azure Search store is closed.")
        mark_feature_used(FeatureIndex.AZURE_AI_SEARCH)

    def get_collection(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        vector_search: VectorSearch | None = None,
        index_options: Mapping[str, Any] | None = None,
        is_alias: bool = False,
    ) -> AzureAISearchCollection[ModelT]:
        """Create a collection using this store's index client and defaults."""
        self._require_open()
        collection = AzureAISearchCollection(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator or self.embedding_generator,
            index_client=self.index_client,
            vector_search=vector_search,
            index_options=index_options,
            is_alias=is_alias,
            allow_preview=self.allow_preview,
            query_source_credential=self.query_source_credential,
        )
        self._collections[collection] = None
        collection._on_close = lambda closed: self._collections.pop(closed, None)  # pyright: ignore[reportPrivateUsage]
        return collection

    async def list_collection_names(self, *, operation_options: Mapping[str, Any] | None = None) -> Sequence[str]:
        """Consume the SDK's complete index-name iterator, including continuation pages."""
        self._require_open()
        options = _validate_operation_options(operation_options, {"search", "page_size", "search_type"})
        if options and not set(options) <= inspect.signature(SearchIndexClient.list_index_names).parameters.keys():
            raise NotImplementedError("Filtered index listing requires a supporting Search SDK.")
        if options:
            if not self.allow_preview:
                raise NotImplementedError("Filtered index listing requires allow_preview=True.")
            options["raw_request_hook"] = partial(_require_preview_request, capabilities=("index_listing",))
        return [name async for name in self.index_client.list_index_names(**options)]

    async def collection_exists(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        """Check one index directly rather than listing every index."""
        self._require_open()
        _validate_operation_options(operation_options, set())
        try:
            await self.index_client.get_index(collection_name)
        except ResourceNotFoundError:
            return False
        return True

    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        self._require_open()
        _validate_operation_options(operation_options, set())
        try:
            await self.index_client.delete_index(collection_name)
        except ResourceNotFoundError:
            return

    async def create_or_update_alias(self, alias_name: str, collection_name: str) -> None:
        """Explicitly create or repoint a native index alias; never mutate the target index."""
        self._require_open()
        await self.index_client.create_or_update_alias(SearchAlias(name=alias_name, indexes=[collection_name]))

    async def delete_alias(self, alias_name: str) -> None:
        """Delete only the alias, leaving its target index intact."""
        self._require_open()
        try:
            await self.index_client.delete_alias(alias_name)
        except ResourceNotFoundError:
            return

    async def close(self) -> None:
        """Close all factory-created clients, leaving borrowed credentials and clients open."""
        if not self._closed:
            self._closed = True
            async with AsyncExitStack() as stack:
                if self.managed_client:
                    stack.push_async_callback(self.index_client.close)
                for collection in self._collections:
                    stack.push_async_callback(collection.close)
            self._collections.clear()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        await self.close()
