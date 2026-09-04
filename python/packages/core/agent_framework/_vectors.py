# Copyright (c) Microsoft. All rights reserved.

"""Core vector store abstractions."""

from __future__ import annotations

import operator
from abc import ABC, abstractmethod
from ast import AST, Lambda, NodeVisitor, expr, parse
from collections.abc import AsyncIterable, AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, is_dataclass, replace
from inspect import Parameter, getsource, signature
from types import UnionType
from typing import (
    Annotated,
    Any,
    ClassVar,
    Final,
    Generic,
    Literal,
    Protocol,
    TypeAlias,
    TypeGuard,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
    runtime_checkable,
)

import msgspec
from pydantic import BaseModel
from typing_extensions import Self, TypedDict, TypeVar

from ._clients import SupportsGetEmbeddings
from ._feature_stage import ExperimentalFeature, experimental
from ._telemetry import FeatureIndex, mark_feature_used
from ._tools import FunctionTool
from ._types import Content, EmbeddingGenerationOptions
from .exceptions import IntegrationException, IntegrationInvalidResponseException

ModelT = TypeVar("ModelT", default=Any)
KeyT = TypeVar("KeyT", default=Any)
FilterT = TypeVar("FilterT")
ResultT = TypeVar("ResultT")
DecoratedModelT = TypeVar("DecoratedModelT")

SearchType: TypeAlias = Literal["vector", "keyword_hybrid"]
FieldTypes: TypeAlias = Literal["key", "vector", "data"]
IndexKind: TypeAlias = Literal["hnsw", "flat", "ivf_flat", "disk_ann", "quantized_flat", "dynamic", "default"]
DistanceFunction: TypeAlias = Literal[
    "cosine_similarity",
    "cosine_distance",
    "dot_prod",
    "euclidean_distance",
    "euclidean_squared_distance",
    "manhattan",
    "hamming",
    "DEFAULT",
]
Vector: TypeAlias = Sequence[float | int]
RecordFilter: TypeAlias = Callable[[Any], bool] | str
RecordFilters: TypeAlias = RecordFilter | Sequence[RecordFilter]
EmbeddingClient: TypeAlias = SupportsGetEmbeddings[Any, Any, Any]
VectorModelEncoder: TypeAlias = Callable[[Any], Mapping[str, Any]]
VectorModelDecoder: TypeAlias = Callable[[Mapping[str, Any]], Any]

_DEFAULT_SEARCH_TOOL_NAME: Final[str] = "search"
_DEFAULT_SEARCH_TOOL_DESCRIPTION: Final[str] = (
    "Perform a vector search for data in a vector store using the provided query."
)
_INDEX_KINDS: Final[tuple[str, ...]] = (
    "hnsw",
    "flat",
    "ivf_flat",
    "disk_ann",
    "quantized_flat",
    "dynamic",
    "default",
)
_DISTANCE_FUNCTIONS: Final[tuple[str, ...]] = (
    "cosine_similarity",
    "cosine_distance",
    "dot_prod",
    "euclidean_distance",
    "euclidean_squared_distance",
    "manhattan",
    "hamming",
    "DEFAULT",
)


DISTANCE_FUNCTION_DIRECTION_HELPER: Final[Mapping[DistanceFunction, Callable[[float | int, float | int], bool]]] = {
    "cosine_similarity": operator.ge,
    "cosine_distance": operator.le,
    "dot_prod": operator.ge,
    "euclidean_distance": operator.le,
    "euclidean_squared_distance": operator.le,
    "manhattan": operator.le,
    "hamming": operator.le,
}


def _msgspec_enc_hook(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        return to_list()
    if hasattr(value, "__dict__"):
        return cast(dict[str, Any], vars(value))
    raise NotImplementedError(f"Objects of type {type(value).__name__!r} are not supported.")


def _normalize_vector(value: Any) -> Vector:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return cast(Vector, value)
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        converted = to_list()
        if isinstance(converted, Sequence) and not isinstance(converted, (str, bytes, bytearray)):
            return cast(Vector, converted)
    raise TypeError("The embedding client returned an unsupported vector type.")


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
@dataclass(frozen=True, slots=True, init=False)
class VectorStoreField:
    """Describe one field in a vector store model."""

    field_type: FieldTypes
    name: str
    type_: str | None
    storage_name: str | None
    is_indexed: bool | None
    is_full_text_indexed: bool | None
    dimensions: int | None
    index_kind: IndexKind | None
    distance_function: DistanceFunction | None
    embedding_generator: EmbeddingClient | None

    @overload
    def __init__(
        self,
        field_type: Literal["key"],
        *,
        name: str | None = None,
        type_: str | None = None,
        storage_name: str | None = None,
    ) -> None:
        """Initialize a key field.

        Args:
            field_type: The key field type.
            name: The model field name. The decorator supplies this when omitted.
            type_: The scalar type name used by the backing store.
            storage_name: The field name used by the backing store.
        """
        ...

    @overload
    def __init__(
        self,
        field_type: Literal["data"] = "data",
        *,
        name: str | None = None,
        type_: str | None = None,
        storage_name: str | None = None,
        is_indexed: bool | None = None,
        is_full_text_indexed: bool | None = None,
    ) -> None:
        """Initialize a data field with optional indexing.

        Args:
            field_type: The data field type.
            name: The model field name. The decorator supplies this when omitted.
            type_: The scalar type name used by the backing store.
            storage_name: The field name used by the backing store.
            is_indexed: Whether the field should be indexed.
            is_full_text_indexed: Whether the field should have a full-text index.
        """
        ...

    @overload
    def __init__(
        self,
        field_type: Literal["vector"],
        *,
        name: str | None = None,
        type_: str | None = None,
        storage_name: str | None = None,
        dimensions: int,
        index_kind: IndexKind | None = None,
        distance_function: DistanceFunction | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> None:
        """Initialize a vector field with required dimensions.

        Args:
            field_type: The vector field type.
            name: The model field name. The decorator supplies this when omitted.
            type_: The vector element type name used by the backing store.
            storage_name: The field name used by the backing store.
            dimensions: The number of vector dimensions.
            index_kind: The vector index kind.
            distance_function: The vector distance function.
            embedding_generator: An optional client used to generate this field's embeddings.

        Raises:
            ValueError: If dimensions or vector options are invalid.
        """
        ...

    def __init__(
        self,
        field_type: FieldTypes = "data",
        *,
        name: str | None = None,
        type_: str | None = None,
        storage_name: str | None = None,
        is_indexed: bool | None = None,
        is_full_text_indexed: bool | None = None,
        dimensions: int | None = None,
        index_kind: IndexKind | None = None,
        distance_function: DistanceFunction | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> None:
        """Initialize a vector store field.

        Args:
            field_type: The field's role in the vector store model.
            name: The model field name. The decorator supplies this when omitted.
            type_: The scalar type name used by the backing store.
            storage_name: The field name used by the backing store.
            is_indexed: Whether a data field should be indexed.
            is_full_text_indexed: Whether a data field should have a full-text index.
            dimensions: The number of vector dimensions. Required for vector fields.
            index_kind: The vector index kind.
            distance_function: The vector distance function.
            embedding_generator: An optional client used to generate this field's embeddings.

        Raises:
            ValueError: If field options are invalid.
        """
        if field_type not in ("key", "vector", "data"):
            raise ValueError(f"Unknown vector store field type '{field_type}'.")
        resolved_dimensions: int | None = None
        resolved_index_kind: IndexKind | None = None
        resolved_distance_function: DistanceFunction | None = None
        resolved_embedding_generator: EmbeddingClient | None = None
        if field_type == "vector":
            if dimensions is None or dimensions <= 0:
                raise ValueError("Vector fields must specify a positive number of dimensions.")
            if index_kind is not None and index_kind not in _INDEX_KINDS:
                raise ValueError(f"Unknown vector index kind '{index_kind}'.")
            if distance_function is not None and distance_function not in _DISTANCE_FUNCTIONS:
                raise ValueError(f"Unknown vector distance function '{distance_function}'.")
            resolved_dimensions = dimensions
            resolved_index_kind = index_kind or "default"
            resolved_distance_function = distance_function or "DEFAULT"
            resolved_embedding_generator = embedding_generator
        elif any(value is not None for value in (dimensions, index_kind, distance_function, embedding_generator)):
            raise ValueError("Vector-only options can only be set on vector fields.")

        object.__setattr__(self, "field_type", field_type)
        object.__setattr__(self, "name", name or "")
        object.__setattr__(self, "type_", type_)
        object.__setattr__(self, "storage_name", storage_name)
        object.__setattr__(self, "is_indexed", is_indexed)
        object.__setattr__(self, "is_full_text_indexed", is_full_text_indexed)
        object.__setattr__(self, "dimensions", resolved_dimensions)
        object.__setattr__(self, "index_kind", resolved_index_kind)
        object.__setattr__(self, "distance_function", resolved_distance_function)
        object.__setattr__(self, "embedding_generator", resolved_embedding_generator)


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
@dataclass(frozen=True, slots=True, init=False)
class VectorStoreCollectionDefinition:
    """Describe the records stored in a vector collection.

    Most users should not create this class directly. Applying
    :func:`vectorstoremodel` to a typed model derives and registers its
    collection definition automatically.

    Create a definition explicitly for schema-less records such as dictionaries,
    or when adapting an externally owned model through
    :func:`register_vectorstoremodel`.
    """

    fields: tuple[VectorStoreField, ...]
    collection_name: str | None
    key_name: str

    def __init__(
        self,
        fields: Sequence[VectorStoreField],
        *,
        collection_name: str | None = None,
    ) -> None:
        """Initialize a vector store collection definition.

        Args:
            fields: The key, data, and vector fields in each record.
            collection_name: The collection name associated with the model.

        Raises:
            ValueError: If field names or key fields are invalid.
        """
        object.__setattr__(self, "fields", tuple(fields))
        object.__setattr__(self, "collection_name", collection_name)
        object.__setattr__(self, "key_name", self._validate())

    def _validate(self) -> str:
        if not self.fields:
            raise ValueError("A vector store definition must contain at least one field.")
        if any(not field.name for field in self.fields):
            raise ValueError("Vector store field names must not be empty.")

        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("Vector store field names must be unique.")
        storage_names = [field.storage_name or field.name for field in self.fields]
        if len(storage_names) != len(set(storage_names)):
            raise ValueError("Vector store field storage names must be unique.")

        key_fields = [field for field in self.fields if field.field_type == "key"]
        if len(key_fields) != 1:
            raise ValueError("A vector store definition must contain exactly one key field.")
        return key_fields[0].name

    @property
    def names(self) -> list[str]:
        """Get the model field names."""
        return [field.name for field in self.fields]

    @property
    def storage_names(self) -> list[str]:
        """Get the backing store field names."""
        return [field.storage_name or field.name for field in self.fields]

    @property
    def key_field(self) -> VectorStoreField:
        """Get the key field."""
        return next(field for field in self.fields if field.field_type == "key")

    @property
    def key_field_storage_name(self) -> str:
        """Get the key field's backing store name."""
        return self.key_field.storage_name or self.key_field.name

    @property
    def vector_fields(self) -> list[VectorStoreField]:
        """Get the vector fields."""
        return [field for field in self.fields if field.field_type == "vector"]

    @property
    def data_fields(self) -> list[VectorStoreField]:
        """Get the data fields."""
        return [field for field in self.fields if field.field_type == "data"]

    @property
    def vector_field_names(self) -> list[str]:
        """Get the vector field names."""
        return [field.name for field in self.vector_fields]

    @property
    def data_field_names(self) -> list[str]:
        """Get the data field names."""
        return [field.name for field in self.data_fields]

    def try_get_vector_field(self, field_name: str | None = None) -> VectorStoreField | None:
        """Get a vector field by model or storage name, defaulting to the first vector field."""
        if field_name is None:
            return self.vector_fields[0] if self.vector_fields else None
        return next(
            (field for field in self.vector_fields if field.name == field_name or field.storage_name == field_name),
            None,
        )

    def get_names(self, *, include_vector_fields: bool = True, include_key_field: bool = True) -> list[str]:
        """Get selected model field names."""
        return [
            field.name
            for field in self.fields
            if field.field_type == "data"
            or (field.field_type == "vector" and include_vector_fields)
            or (field.field_type == "key" and include_key_field)
        ]

    def get_storage_names(self, *, include_vector_fields: bool = True, include_key_field: bool = True) -> list[str]:
        """Get selected backing store field names."""
        return [
            field.storage_name or field.name
            for field in self.fields
            if field.field_type == "data"
            or (field.field_type == "vector" and include_vector_fields)
            or (field.field_type == "key" and include_key_field)
        ]


@dataclass(frozen=True, slots=True)
class _VectorModelRegistration:
    record_type: type[Any]
    definition: VectorStoreCollectionDefinition
    encoder: VectorModelEncoder
    decoder: VectorModelDecoder


_VECTOR_MODEL_REGISTRY: dict[type[Any], _VectorModelRegistration] = {}


def _default_vector_model_encoder(record_type: type[Any]) -> VectorModelEncoder:
    def encode(value: Any) -> Mapping[str, Any]:
        if not isinstance(value, record_type):
            raise TypeError(f"Expected {record_type.__name__}, got {type(value).__name__}.")
        converted = msgspec.to_builtins(value, str_keys=True, enc_hook=_msgspec_enc_hook)
        if not isinstance(converted, Mapping):
            raise TypeError(f"Vector model {record_type.__name__!r} must serialize to a mapping.")
        return cast(Mapping[str, Any], converted)

    return encode


def _default_vector_model_decoder(record_type: type[Any]) -> VectorModelDecoder:
    if issubclass(record_type, BaseModel):

        def decode_pydantic(value: Mapping[str, Any]) -> Any:
            validation_value = {
                field.validation_alias
                if isinstance(field.validation_alias, str)
                else field.alias
                if isinstance(field.alias, str)
                else name: value[name]
                for name, field in record_type.model_fields.items()
                if name in value
            }
            return record_type.model_validate(validation_value)

        return decode_pydantic
    if is_dataclass(record_type) or issubclass(record_type, msgspec.Struct):
        return lambda value: msgspec.convert(value, record_type)
    return lambda value: record_type(**value)


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
def register_vectorstoremodel(
    record_type: type[ModelT],
    *,
    definition: VectorStoreCollectionDefinition,
    encoder: Callable[[ModelT], Mapping[str, Any]] | None = None,
    decoder: Callable[[Mapping[str, Any]], ModelT] | None = None,
) -> None:
    """Register one vector store definition and codec pair for a model type.

    Args:
        record_type: The model type to register.
        definition: The vector store collection definition for the model.
        encoder: Optional callback that converts a model instance to a mapping.
        decoder: Optional callback that reconstructs a model instance from a mapping.
            This can restore array-like fields such as NumPy arrays without requiring
            Agent Framework to depend on NumPy.

    Raises:
        ValueError: If the model type is already registered differently.
    """
    existing = _VECTOR_MODEL_REGISTRY.get(record_type)
    if existing is not None:
        if existing.definition is not definition:
            raise ValueError(f"Vector model {record_type.__name__!r} is already registered with another definition.")
        if encoder is not None and existing.encoder is not encoder:
            raise ValueError(f"Vector model {record_type.__name__!r} is already registered with another encoder.")
        if decoder is not None and existing.decoder is not decoder:
            raise ValueError(f"Vector model {record_type.__name__!r} is already registered with another decoder.")
        return
    if decoder is None:
        required_vector_fields = [
            field.name for field in definition.vector_fields if not _has_default(record_type, field.name)
        ]
        if required_vector_fields:
            raise ValueError(
                "Vector fields omitted by include_vectors=False must declare defaults when using the default decoder. "
                f"Add defaults or supply a custom decoder for: {', '.join(required_vector_fields)}."
            )
    resolved_encoder = (
        cast(VectorModelEncoder, encoder) if encoder is not None else _default_vector_model_encoder(record_type)
    )
    resolved_decoder = (
        cast(VectorModelDecoder, decoder) if decoder is not None else _default_vector_model_decoder(record_type)
    )
    registration = _VectorModelRegistration(
        record_type=record_type,
        definition=definition,
        encoder=resolved_encoder,
        decoder=resolved_decoder,
    )
    _VECTOR_MODEL_REGISTRY[record_type] = registration


def _has_default(record_type: type[Any], field_name: str) -> bool:
    if issubclass(record_type, BaseModel) and field_name in record_type.model_fields:
        return not record_type.model_fields[field_name].is_required()
    try:
        parameter = signature(record_type).parameters.get(field_name)
    except (TypeError, ValueError):
        parameter = None
    if parameter is not None:
        return parameter.default is not Parameter.empty
    return hasattr(record_type, field_name)


def _unwrap_annotation(annotation: Any) -> Any:
    if get_origin(annotation) is Annotated:
        return get_args(annotation)[0]
    return annotation


def _without_none(annotation: Any) -> tuple[Any, ...]:
    args = get_args(annotation)
    if get_origin(annotation) in (UnionType, Union):
        return tuple(arg for arg in args if arg is not type(None))
    return (annotation,)


def _infer_type_name(annotation: Any, *, vector: bool) -> str | None:
    candidates = _without_none(_unwrap_annotation(annotation))
    if vector:
        for candidate in candidates:
            origin = get_origin(candidate)
            args = get_args(candidate)
            if origin is not None and args:
                candidate = next((arg for arg in args if arg is not Ellipsis), candidate)
                return getattr(candidate, "__name__", str(candidate))
    candidate = candidates[0] if candidates else annotation
    origin = get_origin(candidate)
    return getattr(origin or candidate, "__name__", None)


def _parse_model_definition(
    record_type: type[Any],
    *,
    collection_name: str | None,
) -> VectorStoreCollectionDefinition:
    try:
        annotations = get_type_hints(record_type, include_extras=True)
    except (NameError, TypeError) as exc:
        raise ValueError(f"Unable to resolve annotations for {record_type.__name__}: {exc}") from exc
    uses_init_annotations = not any(
        any(isinstance(metadata, VectorStoreField) for metadata in get_args(annotation)[1:])
        for annotation in annotations.values()
        if get_origin(annotation) is Annotated
    )
    init_parameters: Mapping[str, Parameter] = {}
    if uses_init_annotations:
        try:
            annotations = {
                name: annotation
                for name, annotation in get_type_hints(record_type.__init__, include_extras=True).items()
                if name not in {"self", "return"}
            }
            init_parameters = signature(record_type.__init__).parameters
        except (NameError, TypeError, ValueError) as exc:
            raise ValueError(f"Unable to resolve constructor annotations for {record_type.__name__}: {exc}") from exc
    if not annotations:
        raise ValueError("A vector store model must declare at least one annotated field or constructor parameter.")

    fields: list[VectorStoreField] = []
    for name, annotation in annotations.items():
        metadata = get_args(annotation)[1:] if get_origin(annotation) is Annotated else ()
        field = next((item for item in metadata if isinstance(item, VectorStoreField)), None)
        if field is None:
            has_default = (
                init_parameters[name].default is not Parameter.empty
                if uses_init_annotations
                else _has_default(record_type, name)
            )
            if not has_default:
                raise ValueError(f"Field '{name}' must use VectorStoreField metadata or declare a default value.")
            continue

        parsed_field = replace(
            field,
            name=name,
            type_=field.type_ or _infer_type_name(annotation, vector=field.field_type == "vector"),
        )
        fields.append(parsed_field)
    return VectorStoreCollectionDefinition(fields, collection_name=collection_name)


class _VectorStoreModelDecorator(Protocol):
    def __call__(self, record_type: type[DecoratedModelT]) -> type[DecoratedModelT]:
        """Decorate a model while preserving its concrete type."""
        ...


@overload
def vectorstoremodel(cls: type[ModelT]) -> type[ModelT]:
    """Decorate a vector store model without arguments.

    Args:
        cls: The class to decorate.

    Returns:
        The original class with vector store model metadata attached.

    Raises:
        ValueError: If the model definition is invalid.
    """
    ...


@overload
def vectorstoremodel(
    cls: None = None,
    *,
    collection_name: str | None = None,
    encoder: Callable[[Any], Mapping[str, Any]] | None = None,
    decoder: Callable[[Mapping[str, Any]], Any] | None = None,
) -> _VectorStoreModelDecorator:
    """Create a vector store model decorator with a collection name.

    Args:
        cls: The empty decorator target used when calling the decorator with arguments.
        collection_name: The collection name associated with the model.
        encoder: Optional callback that converts a model instance to a mapping.
        decoder: Optional callback that reconstructs a model instance from a mapping.
            This can restore array-like fields such as NumPy arrays without requiring
            Agent Framework to depend on NumPy.

    Returns:
        A decorator that attaches vector store model metadata.

    Raises:
        ValueError: When the returned decorator receives an invalid model definition.
    """
    ...


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
def vectorstoremodel(
    cls: type[Any] | None = None,
    *,
    collection_name: str | None = None,
    encoder: Callable[[Any], Mapping[str, Any]] | None = None,
    decoder: Callable[[Mapping[str, Any]], Any] | None = None,
) -> type[Any] | _VectorStoreModelDecorator:
    """Mark a class as a vector store model.

    Class fields or constructor parameters use ``Annotated`` metadata to describe their
    vector store role. Dataclasses, Pydantic models, and plain classes are supported.
    Dictionaries use an explicit :class:`VectorStoreCollectionDefinition` instead.

    Args:
        cls: The class to decorate.
        collection_name: The collection name associated with the model.
        encoder: Optional callback that converts a model instance to a mapping.
        decoder: Optional callback that reconstructs a model instance from a mapping.

    Returns:
        The original class with vector store model metadata attached.

    Raises:
        ValueError: If the model definition is invalid.
    """

    def wrap(record_type: type[DecoratedModelT]) -> type[DecoratedModelT]:
        definition = _parse_model_definition(record_type, collection_name=collection_name)
        register_vectorstoremodel(
            record_type,
            definition=definition,
            encoder=encoder,
            decoder=decoder,
        )
        decorated_type = cast(Any, record_type)
        decorated_type.__vectorstoremodel__ = True
        decorated_type.__vectorstoremodel_definition__ = definition
        return record_type

    return wrap if cls is None else wrap(cls)


def _validate_paging(*, top: int, skip: int) -> None:
    if not isinstance(top, int) or isinstance(top, bool):
        raise TypeError("top must be an integer.")
    if not isinstance(skip, int) or isinstance(skip, bool):
        raise TypeError("skip must be an integer.")
    if top <= 0:
        raise ValueError("top must be greater than zero.")
    if skip < 0:
        raise ValueError("skip must not be negative.")


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class SearchResponse(TypedDict, Generic[ModelT]):
    """One vector search result."""

    record: ModelT
    score: float | None


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class SearchResults(Generic[ResultT]):
    """A lazily consumed set of vector search results.

    Connector-native counts may be placed in ``metadata`` together with enough
    provider-specific context to explain their scope.
    """

    def __init__(
        self,
        results: AsyncIterable[ResultT] | Sequence[ResultT],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize search results."""
        self.results = _as_async_iterable(results)
        self.metadata = metadata

    def __aiter__(self) -> AsyncIterator[ResultT]:
        """Iterate over results regardless of whether their source was synchronous or asynchronous."""
        return self.results.__aiter__()


class _VectorStoreRecordHandler(Generic[KeyT, ModelT]):
    """Serialize and deserialize application records for a vector store."""

    supported_key_types: ClassVar[set[str] | None] = None
    supported_vector_types: ClassVar[set[str] | None] = None

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> None:
        """Initialize a vector store record handler.

        Args:
            record_type: The application record type.
            definition: The collection definition. Decorated models supply this automatically.
            embedding_generator: The default client used for local vector generation.

        Raises:
            ValueError: If no model registration or explicit dictionary definition is available.
        """
        registration = _VECTOR_MODEL_REGISTRY.get(record_type)
        if record_type is dict:
            if definition is None:
                raise ValueError("Dictionary record types require an explicit VectorStoreCollectionDefinition.")
            resolved_definition = definition
        else:
            if registration is None:
                raise ValueError(
                    f"Record type {record_type.__name__!r} must be registered with "
                    "@vectorstoremodel or register_vectorstoremodel()."
                )
            if definition is not None and definition is not registration.definition:
                raise ValueError(f"Record type {record_type.__name__!r} is registered with another definition.")
            resolved_definition = registration.definition
        self.record_type = record_type
        self.definition = resolved_definition
        self._model_registration = registration
        self.embedding_generator = embedding_generator
        self._validate_data_model()

    def _validate_data_model(self) -> None:
        key_type = self.definition.key_field.type_
        if self.supported_key_types and key_type and key_type not in self.supported_key_types:
            raise ValueError(f"Key field type must be one of {self.supported_key_types}; got '{key_type}'.")
        if not self.supported_vector_types:
            return
        for field in self.definition.vector_fields:
            if field.type_ and field.type_ not in self.supported_vector_types:
                raise ValueError(
                    f"Vector field '{field.name}' type must be one of {self.supported_vector_types}; "
                    f"got '{field.type_}'."
                )

    def _serialize_dicts_to_store_models(
        self,
        records: Sequence[dict[str, Any]],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[Any]:
        """Convert dictionaries to store-specific records."""
        return records

    def _deserialize_store_models_to_dicts(
        self,
        records: Sequence[Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Sequence[dict[str, Any]]:
        """Convert store-specific records to dictionaries."""
        dict_records: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, Mapping):
                raise TypeError("Store records must be mappings unless the collection overrides deserialization.")
            dict_records.append(dict(cast(Mapping[str, Any], record)))
        return dict_records

    async def serialize(
        self,
        records: ModelT | Sequence[ModelT],
        *,
        generate_vectors: bool = True,
        context: Mapping[str, Any] | None = None,
    ) -> Any:
        """Serialize one or more application records for the backing store.

        Args:
            records: One application record or a sequence of records.
            generate_vectors: Whether to generate vector values, overwriting any supplied values. When ``False``,
                supplied values are preserved.
            context: Connector-specific serialization context.

        Raises:
            TypeError: If a record cannot be converted to a mapping.
            ValueError: If required record data is missing, has an invalid shape, or a vector field has no generator.
            IntegrationInvalidResponseException: If embedding generation returns an unexpected result count.
        """
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        is_batch = _is_non_string_sequence(records)
        input_records = list(cast(Sequence[ModelT], records)) if is_batch else [cast(ModelT, records)]
        dict_records = [self._serialize_record_to_dict(record) for record in input_records]

        if generate_vectors:
            await self._add_vectors_to_records(dict_records)
        store_models = list(self._serialize_dicts_to_store_models(dict_records, context=context))

        if len(store_models) != len(dict_records):
            raise IntegrationInvalidResponseException(
                f"Expected {len(dict_records)} serialized records, but the connector returned {len(store_models)}."
            )
        if is_batch:
            return store_models
        if len(store_models) != 1:
            raise ValueError(f"Expected one serialized record, but the serializer returned {len(store_models)}.")
        return store_models[0]

    def _serialize_record_to_dict(self, record: ModelT) -> dict[str, Any]:
        if self.record_type is dict:
            source = self._to_builtin_mapping(record)
        else:
            if self._model_registration is None:
                raise RuntimeError(f"Vector model {self.record_type.__name__!r} is not registered.")
            source = self._to_builtin_mapping(self._model_registration.encoder(record))
        return self._serialize_mapping_to_store(source)

    @staticmethod
    def _to_builtin_mapping(record: Any) -> Mapping[str, Any]:
        converted = msgspec.to_builtins(record, str_keys=True, enc_hook=_msgspec_enc_hook)
        if not isinstance(converted, Mapping):
            raise TypeError("Vector records must serialize to mappings.")
        return cast(Mapping[str, Any], converted)

    def _serialize_mapping_to_store(self, source: Mapping[str, Any]) -> dict[str, Any]:
        serialized: dict[str, Any] = {}
        for field in self.definition.fields:
            if field.name in source:
                value = source[field.name]
            elif field.storage_name is not None and field.storage_name in source:
                value = source[field.storage_name]
            else:
                raise ValueError(f"Record is missing vector store field '{field.name}'.")
            serialized[field.storage_name or field.name] = value
        return serialized

    async def _add_vectors_to_records(self, records: Sequence[dict[str, Any]]) -> None:
        field_generators: list[tuple[VectorStoreField, EmbeddingClient]] = []
        for field in self.definition.vector_fields:
            embedding_generator = field.embedding_generator or self.embedding_generator
            if embedding_generator is None:
                raise ValueError(
                    f"Vector field '{field.name}' has no embedding generator. "
                    "Set generate_vectors=False to preserve supplied vector values."
                )
            field_generators.append((field, embedding_generator))

        for field, embedding_generator in field_generators:
            storage_name = field.storage_name or field.name
            values = [record.get(storage_name) for record in records]
            if any(value is None for value in values):
                raise ValueError(
                    f"Vector field '{field.name}' cannot be embedded because at least one value is missing."
                )
            options: EmbeddingGenerationOptions = {}
            if field.dimensions is not None:
                options["dimensions"] = field.dimensions
            embeddings = await embedding_generator.get_embeddings(values, options=options)
            if len(embeddings) != len(records):
                raise IntegrationInvalidResponseException(
                    f"Embedding client returned {len(embeddings)} vectors for {len(records)} records."
                )
            for record, embedding in zip(records, embeddings, strict=True):
                record[storage_name] = _normalize_vector(embedding.vector)

    def deserialize(
        self,
        records: Any | Sequence[Any],
        *,
        include_vectors: bool = True,
        context: Mapping[str, Any] | None = None,
    ) -> ModelT | Sequence[ModelT] | None:
        """Deserialize one or more backing store records.

        Raises:
            TypeError: If a store record has an unsupported type.
            ValueError: If records cannot be reconstructed into the requested model shape.
        """
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        if records is None:
            return None
        is_batch = _is_non_string_sequence(records)
        input_records = list(records) if is_batch else [records]
        dict_records = self._deserialize_store_models_to_dicts(input_records, context=context)
        if not dict_records:
            return [] if is_batch else None
        deserialized = [
            self._deserialize_dict_to_record(record, include_vectors=include_vectors) for record in dict_records
        ]
        return deserialized if is_batch else deserialized[0]

    def _deserialize_dict_to_record(
        self,
        record: Mapping[str, Any],
        *,
        include_vectors: bool,
    ) -> ModelT:
        logical_record = self._deserialize_dict_to_mapping(record, include_vectors=include_vectors)
        if self.record_type is dict:
            return cast(ModelT, logical_record)
        if self._model_registration is None:
            raise RuntimeError(f"Vector model {self.record_type.__name__!r} is not registered.")
        return cast(ModelT, self._model_registration.decoder(logical_record))

    def _deserialize_dict_to_mapping(
        self,
        record: Mapping[str, Any],
        *,
        include_vectors: bool,
    ) -> dict[str, Any]:
        logical_record: dict[str, Any] = {}
        for field in self.definition.fields:
            if not include_vectors and field.field_type == "vector":
                continue
            storage_name = field.storage_name or field.name
            if storage_name not in record:
                raise IntegrationInvalidResponseException(
                    f"Vector store response is missing required field '{storage_name}'."
                )
            logical_record[field.name] = record[storage_name]
        return logical_record


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class BaseVectorCollection(_VectorStoreRecordHandler[KeyT, ModelT], ABC):
    """Base class for vector store collection CRUD operations."""

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
        managed_client: bool = True,
    ) -> None:
        """Initialize a vector store collection."""
        super().__init__(
            record_type,
            definition=definition,
            embedding_generator=embedding_generator,
        )
        self.collection_name = collection_name or self.definition.collection_name or ""
        if not self.collection_name:
            raise ValueError("A collection name is required when the model definition does not provide one.")
        self.managed_client = managed_client

    async def __aenter__(self) -> Self:
        """Enter the collection context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Exit the collection context manager."""

    @abstractmethod
    async def ensure_collection_exists(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Create the collection when it does not exist."""
        ...

    @abstractmethod
    async def collection_exists(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        """Check whether the collection exists."""
        ...

    @abstractmethod
    async def ensure_collection_deleted(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Delete the collection when it exists."""
        ...

    @abstractmethod
    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[KeyT]:
        """Upsert serialized records and return their keys."""
        ...

    @abstractmethod
    async def _inner_get(
        self,
        *,
        keys: Sequence[KeyT] | None = None,
        top: int = 10,
        skip: int = 0,
        order_by: Mapping[str, bool] | None = None,
        include_vectors: bool = False,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[Any] | None:
        """Retrieve store-specific records."""
        ...

    @abstractmethod
    async def _inner_delete(
        self,
        keys: Sequence[KeyT],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Delete records by key."""
        ...

    async def upsert(
        self,
        records: Sequence[ModelT],
        *,
        generate_vectors: bool = True,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[KeyT]:
        """Upsert a batch of records.

        Args:
            records: A sequence of models.
            generate_vectors: Whether to generate vector values, overwriting any supplied values. When ``False``,
                supplied values are preserved.
            operation_options: Store-specific operation options.

        Returns:
            The keys of all upserted records.

        Raises:
            TypeError: If record serialization encounters an unsupported type.
            ValueError: If record data or returned keys have an invalid shape, or a vector field has no generator.
            IntegrationException: If the backing store operation fails.
            IntegrationInvalidResponseException: If the backing store returns an unexpected key count.
        """
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        if not _is_non_string_sequence(records):
            raise TypeError("records must be a sequence.")
        try:
            serialized = await self.serialize(records, generate_vectors=generate_vectors)
            store_records = list(serialized) if _is_non_string_sequence(serialized) else [serialized]
            keys = list(await self._inner_upsert(store_records, operation_options=operation_options))
        except (TypeError, ValueError):
            raise
        except IntegrationException:
            raise
        except Exception as exc:
            raise IntegrationException(
                f"Error upserting records into collection '{self.collection_name}': {exc}"
            ) from exc
        if len(keys) != len(store_records):
            raise IntegrationInvalidResponseException(
                f"Expected {len(store_records)} upserted keys, but the store returned {len(keys)}."
            )
        return keys

    async def get(
        self,
        keys: Sequence[KeyT] | None = None,
        *,
        top: int = 10,
        skip: int = 0,
        order_by: Mapping[str, bool] | None = None,
        include_vectors: bool = False,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[ModelT]:
        """Get records by keys or list a page of records.

        Args:
            keys: A sequence of keys, or ``None`` to list a page of records.
            top: The maximum number of records returned when listing.
            skip: The number of records skipped when listing.
            order_by: Field names mapped to ascending (``True``) or descending (``False``) order.
            include_vectors: Whether returned records include vector fields.
            operation_options: Store-specific operation options.

        Returns:
            A sequence of models. Keys that do not exist are omitted.

        Raises:
            ValueError: If paging arguments are invalid.
            TypeError: If keys or a returned record has an unsupported type.
            IntegrationException: If retrieval fails.
        """
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        _validate_paging(top=top, skip=skip)
        if keys is not None and not _is_non_string_sequence(keys):
            raise TypeError("keys must be a sequence.")
        try:
            records = await self._inner_get(
                keys=keys,
                top=top,
                skip=skip,
                order_by=order_by,
                include_vectors=include_vectors,
                operation_options=operation_options,
            )
        except IntegrationException:
            raise
        except Exception as exc:
            raise IntegrationException(
                f"Error getting records from collection '{self.collection_name}': {exc}"
            ) from exc
        if not records:
            return []
        deserialized = self.deserialize(records, include_vectors=include_vectors)
        return [] if deserialized is None else cast(Sequence[ModelT], deserialized)

    async def delete(
        self,
        keys: Sequence[KeyT],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Delete a batch of records by key.

        Args:
            keys: The keys to delete.
            operation_options: Store-specific operation options.

        Raises:
            TypeError: If keys is not a sequence.
            IntegrationException: If the backing store operation fails.
        """
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        if not _is_non_string_sequence(keys):
            raise TypeError("keys must be a sequence.")
        try:
            await self._inner_delete(keys, operation_options=operation_options)
        except IntegrationException:
            raise
        except Exception as exc:
            raise IntegrationException(
                f"Error deleting records from collection '{self.collection_name}': {exc}"
            ) from exc


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class BaseVectorStore(ABC):
    """Base class for vector stores that create collection clients."""

    def __init__(
        self,
        *,
        embedding_generator: EmbeddingClient | None = None,
        managed_client: bool = True,
    ) -> None:
        """Initialize a vector store."""
        self.embedding_generator = embedding_generator
        self.managed_client = managed_client

    async def __aenter__(self) -> Self:
        """Enter the vector store context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Exit the vector store context manager."""

    @abstractmethod
    def get_collection(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> BaseVectorCollection[Any, ModelT]:
        """Create a collection client tied to this store."""
        ...

    @abstractmethod
    async def list_collection_names(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[str]:
        """List collection names."""
        ...

    async def collection_exists(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        """Check whether a collection exists."""
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return collection_name in await self.list_collection_names(operation_options=operation_options)

    async def ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Delete a collection when it exists."""
        if not await self.collection_exists(collection_name, operation_options=operation_options):
            return
        await self._inner_ensure_collection_deleted(
            collection_name,
            operation_options=operation_options,
        )

    @abstractmethod
    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Delete a collection by name."""
        ...


class _LambdaVisitor(NodeVisitor, Generic[FilterT]):
    def __init__(self, lambda_parser: Callable[[expr], FilterT]) -> None:
        self.lambda_parser = lambda_parser
        self.output_filters: list[FilterT] = []

    def visit_Lambda(self, node: Lambda) -> None:
        self.output_filters.append(self.lambda_parser(node.body))


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class BaseVectorSearch(_VectorStoreRecordHandler[KeyT, ModelT], ABC):
    """Base class for vector and keyword-hybrid search."""

    supported_search_types: ClassVar[set[SearchType]] = {"vector"}

    @abstractmethod
    async def _inner_search(
        self,
        *,
        search_type: SearchType,
        filter: Any | list[Any] | None = None,
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
        """Execute a search and return raw connector results."""
        ...

    @abstractmethod
    def _get_record_from_result(self, result: Any) -> Any:
        """Extract a store record from one raw search result."""
        ...

    @abstractmethod
    def _get_score_from_result(self, result: Any) -> float | None:
        """Extract a score from one raw search result."""
        ...

    @abstractmethod
    def _lambda_parser(self, node: AST) -> Any:
        """Translate one lambda expression body into a store filter."""
        ...

    @overload
    async def search(
        self,
        values: Any,
        *,
        search_type: SearchType = "vector",
        vector: Vector | None = None,
        filter: RecordFilters | None = None,
        top: int = 3,
        skip: int = 0,
        include_vectors: bool = False,
        vector_property_name: str | None = None,
        additional_property_name: str | None = None,
        score_threshold: float | None = None,
        operation_options: Mapping[str, Any] | None = None,
    ) -> SearchResults[SearchResponse[ModelT]]:
        """Search from a value, optionally with a precomputed vector.

        Args:
            values: The value to search for or vectorize.
            search_type: Whether to perform vector or keyword-hybrid search.
            vector: An optional precomputed query vector.
            filter: One or more lambda filters.
            top: The maximum number of results.
            skip: The number of results to skip.
            include_vectors: Whether returned records include vector fields.
            vector_property_name: The vector field used for search.
            additional_property_name: The data field used for keyword-hybrid search.
            score_threshold: The minimum similarity or maximum distance accepted.
                Results without scores remain included.
            operation_options: Store-specific operation options.

        Returns:
            Lazily consumed search results.

        Raises:
            ValueError: If paging or search arguments are invalid.
            NotImplementedError: If the search type is unsupported.
            IntegrationException: If vector generation or search fails.
        """
        ...

    @overload
    async def search(
        self,
        *,
        search_type: Literal["vector"] = "vector",
        vector: Vector,
        filter: RecordFilters | None = None,
        top: int = 3,
        skip: int = 0,
        include_vectors: bool = False,
        vector_property_name: str | None = None,
        additional_property_name: str | None = None,
        score_threshold: float | None = None,
        operation_options: Mapping[str, Any] | None = None,
    ) -> SearchResults[SearchResponse[ModelT]]:
        """Search from a required precomputed vector.

        Args:
            search_type: The vector search type.
            vector: The precomputed query vector.
            filter: One or more lambda filters.
            top: The maximum number of results.
            skip: The number of results to skip.
            include_vectors: Whether returned records include vector fields.
            vector_property_name: The vector field used for search.
            additional_property_name: The data field used for keyword-hybrid search.
            score_threshold: The minimum similarity or maximum distance accepted.
                Results without scores remain included.
            operation_options: Store-specific operation options.

        Returns:
            Lazily consumed search results.

        Raises:
            ValueError: If paging or search arguments are invalid.
            NotImplementedError: If vector search is unsupported.
            IntegrationException: If search execution fails.
        """
        ...

    async def search(
        self,
        values: Any | None = None,
        *,
        search_type: SearchType = "vector",
        vector: Vector | None = None,
        filter: RecordFilters | None = None,
        top: int = 3,
        skip: int = 0,
        include_vectors: bool = False,
        vector_property_name: str | None = None,
        additional_property_name: str | None = None,
        score_threshold: float | None = None,
        operation_options: Mapping[str, Any] | None = None,
    ) -> SearchResults[SearchResponse[ModelT]]:
        """Search the vector store.

        Args:
            values: The value to search for or vectorize.
            search_type: Whether to perform vector or keyword-hybrid search.
            vector: A precomputed query vector.
            filter: One or more lambda filters.
            top: The maximum number of results.
            skip: The number of results to skip.
            include_vectors: Whether returned records include vector fields.
            vector_property_name: The vector field used for search.
            additional_property_name: The data field used for keyword-hybrid search.
            score_threshold: The minimum similarity or maximum distance accepted.
                Results without scores remain included.
            operation_options: Store-specific operation options.

        Returns:
            Lazily consumed search results.

        Raises:
            ValueError: If paging or search arguments are invalid.
            NotImplementedError: If the search type is unsupported.
            IntegrationException: If the backing store search fails.
        """
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        if search_type not in ("vector", "keyword_hybrid"):
            raise ValueError(f"Unknown search type '{search_type}'.")
        if search_type not in self.supported_search_types:
            raise NotImplementedError(f"Search type '{search_type}' is not supported by {type(self).__name__}.")
        if values is None and vector is None:
            raise ValueError("Search requires values or a precomputed vector.")
        if search_type == "keyword_hybrid" and values is None:
            raise ValueError("Keyword-hybrid search requires values.")

        _validate_paging(top=top, skip=skip)
        try:
            self._validate_score_threshold(
                score_threshold=score_threshold,
                vector_property_name=vector_property_name,
            )
            resolved_vector = vector
            if resolved_vector is None and values is not None:
                resolved_vector = await self._generate_vector_from_values(
                    values,
                    vector_property_name=vector_property_name,
                )
            translated_filter = self._build_filter(filter)
            raw_results = await self._inner_search(
                search_type=search_type,
                filter=translated_filter,
                values=values,
                vector=resolved_vector,
                top=top,
                skip=skip,
                include_vectors=include_vectors,
                vector_property_name=vector_property_name,
                additional_property_name=additional_property_name,
                score_threshold=score_threshold,
                operation_options=operation_options,
            )
            return SearchResults(
                self._get_search_results_from_results(
                    raw_results.results,
                    include_vectors=include_vectors,
                    vector_property_name=vector_property_name,
                    score_threshold=score_threshold,
                ),
                metadata=raw_results.metadata,
            )
        except (TypeError, ValueError):
            raise
        except IntegrationException:
            raise
        except Exception as exc:
            raise IntegrationException(f"Vector search failed: {exc}") from exc

    def _validate_score_threshold(
        self,
        *,
        score_threshold: float | None,
        vector_property_name: str | None,
    ) -> None:
        if score_threshold is None:
            return
        vector_field = self.definition.try_get_vector_field(vector_property_name)
        if vector_field is None:
            raise ValueError("A score threshold requires a vector field.")
        if vector_field.distance_function == "DEFAULT":
            raise ValueError("A score threshold requires an explicit distance function on the vector field.")

    async def _generate_vector_from_values(
        self,
        values: Any,
        *,
        vector_property_name: str | None,
    ) -> Vector | None:
        vector_field = self.definition.try_get_vector_field(vector_property_name)
        if vector_field is None:
            if vector_property_name is not None:
                raise ValueError(f"Vector field '{vector_property_name}' was not found in the collection definition.")
            return None
        embedding_generator = vector_field.embedding_generator or self.embedding_generator
        if embedding_generator is None:
            return None
        embedding_options: EmbeddingGenerationOptions = {}
        if vector_field.dimensions is not None:
            embedding_options["dimensions"] = vector_field.dimensions
        embeddings = await embedding_generator.get_embeddings([values], options=embedding_options)
        if len(embeddings) != 1:
            raise IntegrationInvalidResponseException(
                f"Embedding client returned {len(embeddings)} vectors for one search value."
            )
        generated_vector = embeddings[0].vector
        return _normalize_vector(generated_vector)

    def _build_filter(self, search_filter: RecordFilters | None) -> Any | list[Any] | None:
        """Translate lambda filters with the connector's AST parser."""
        if not search_filter:
            return None
        filters: list[RecordFilter]
        if _is_non_string_sequence(search_filter) and not callable(search_filter):
            filters = cast(list[RecordFilter], list(search_filter))
        else:
            filters = [cast(RecordFilter, search_filter)]
        visitor = _LambdaVisitor(self._lambda_parser)
        try:
            for filter_item in filters:
                source = (
                    filter_item
                    if isinstance(filter_item, str)
                    else getsource(cast(Callable[..., Any], filter_item)).strip()
                )
                visitor.visit(parse(source))
        except (OSError, SyntaxError, TypeError) as exc:
            raise ValueError(f"Unable to parse vector search filter: {exc}") from exc
        if not visitor.output_filters:
            raise ValueError("No lambda expression was found in the vector search filter.")
        return visitor.output_filters[0] if len(visitor.output_filters) == 1 else visitor.output_filters

    def _get_search_results_from_results(
        self,
        results: AsyncIterable[Any] | Sequence[Any],
        *,
        include_vectors: bool,
        vector_property_name: str | None,
        score_threshold: float | None,
    ) -> AsyncIterable[SearchResponse[ModelT]]:
        """Convert raw connector results into deserialized search responses."""

        async def generate() -> AsyncIterator[SearchResponse[ModelT]]:
            try:
                async for result in _as_async_iterable(results):
                    try:
                        record = self.deserialize(
                            self._get_record_from_result(result),
                            include_vectors=include_vectors,
                        )
                        if record is None or _is_non_string_sequence(record):
                            if record is None:
                                continue
                            raise IntegrationInvalidResponseException(
                                "A search result must deserialize to exactly one record."
                            )
                        score = self._get_score_from_result(result)
                        if not self._meets_score_threshold(
                            score,
                            score_threshold=score_threshold,
                            vector_property_name=vector_property_name,
                        ):
                            continue
                        yield SearchResponse(record=cast(ModelT, record), score=score)
                    except IntegrationException:
                        raise
                    except Exception as exc:
                        raise IntegrationInvalidResponseException(
                            f"Vector search result conversion failed: {exc}"
                        ) from exc
            except IntegrationException:
                raise
            except Exception as exc:
                raise IntegrationException(f"Vector search iteration failed: {exc}") from exc

        return generate()

    def _meets_score_threshold(
        self,
        score: float | None,
        *,
        score_threshold: float | None,
        vector_property_name: str | None,
    ) -> bool:
        """Apply a threshold when a result includes a comparable score.

        Results without scores remain included because the threshold cannot be
        evaluated for them.
        """
        if score_threshold is None or score is None:
            return True
        vector_field = self.definition.try_get_vector_field(vector_property_name)
        if vector_field is None or vector_field.distance_function is None:
            return True
        comparison = DISTANCE_FUNCTION_DIRECTION_HELPER.get(vector_field.distance_function)
        return comparison(score, score_threshold) if comparison is not None else True


@runtime_checkable
@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class SupportsVectorUpsert(Protocol[KeyT, ModelT]):
    """Protocol for vector collection CRUD operations."""

    collection_name: str
    record_type: type[ModelT]
    definition: VectorStoreCollectionDefinition

    async def upsert(
        self,
        records: Sequence[ModelT],
        *,
        generate_vectors: bool = True,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[KeyT]:
        """Upsert a batch of records, generating embeddings by default."""
        ...

    async def get(
        self,
        keys: Sequence[KeyT] | None = None,
        *,
        top: int = 10,
        skip: int = 0,
        order_by: Mapping[str, bool] | None = None,
        include_vectors: bool = False,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[ModelT]:
        """Get records by keys or list a page of records, excluding vectors by default."""
        ...

    async def delete(
        self,
        keys: Sequence[KeyT],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Delete a batch of records by key."""
        ...


@runtime_checkable
@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class SupportsVectorSearch(Protocol[ModelT]):
    """Protocol for vector and keyword-hybrid search."""

    @overload
    async def search(
        self,
        values: Any,
        *,
        search_type: SearchType = "vector",
        vector: Vector | None = None,
        filter: RecordFilters | None = None,
        top: int = 3,
        skip: int = 0,
        include_vectors: bool = False,
        vector_property_name: str | None = None,
        additional_property_name: str | None = None,
        score_threshold: float | None = None,
        operation_options: Mapping[str, Any] | None = None,
    ) -> SearchResults[SearchResponse[ModelT]]:
        """Search from a value, optionally with a precomputed vector.

        Args:
            values: The value to search for or vectorize.
            search_type: Whether to perform vector or keyword-hybrid search.
            vector: An optional precomputed query vector.
            filter: One or more lambda filters.
            top: The maximum number of results.
            skip: The number of results to skip.
            include_vectors: Whether returned records include vector fields.
            vector_property_name: The vector field used for search.
            additional_property_name: The data field used for keyword-hybrid search.
            score_threshold: The minimum similarity or maximum distance accepted.
                Results without scores remain included.
            operation_options: Store-specific operation options.

        Returns:
            Lazily consumed search results.

        Raises:
            ValueError: If paging or search arguments are invalid.
            NotImplementedError: If the search type is unsupported.
            IntegrationException: If vector generation or search fails.
        """
        ...

    @overload
    async def search(
        self,
        *,
        search_type: Literal["vector"] = "vector",
        vector: Vector,
        filter: RecordFilters | None = None,
        top: int = 3,
        skip: int = 0,
        include_vectors: bool = False,
        vector_property_name: str | None = None,
        additional_property_name: str | None = None,
        score_threshold: float | None = None,
        operation_options: Mapping[str, Any] | None = None,
    ) -> SearchResults[SearchResponse[ModelT]]:
        """Search from a required precomputed vector.

        Args:
            search_type: The vector search type.
            vector: The precomputed query vector.
            filter: One or more lambda filters.
            top: The maximum number of results.
            skip: The number of results to skip.
            include_vectors: Whether returned records include vector fields.
            vector_property_name: The vector field used for search.
            additional_property_name: The data field used for keyword-hybrid search.
            score_threshold: The minimum similarity or maximum distance accepted.
                Results without scores remain included.
            operation_options: Store-specific operation options.

        Returns:
            Lazily consumed search results.

        Raises:
            ValueError: If paging or search arguments are invalid.
            NotImplementedError: If vector search is unsupported.
            IntegrationException: If search execution fails.
        """
        ...


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
def create_vector_search_tool(
    search: SupportsVectorSearch[ModelT],
    *,
    name: str = _DEFAULT_SEARCH_TOOL_NAME,
    description: str = _DEFAULT_SEARCH_TOOL_DESCRIPTION,
    approval_mode: Literal["always_require", "never_require"] = "never_require",
    search_type: SearchType = "vector",
    parameters: type[BaseModel] | Mapping[str, Any] | None = None,
    top: int = 5,
    skip: int = 0,
    filter: RecordFilters | None = None,
    filter_mapper: Callable[[RecordFilters | None, Mapping[str, Any]], RecordFilters | None] | None = None,
    result_mapper: Callable[[SearchResponse[ModelT]], str | Content | Sequence[Content]] | None = None,
) -> FunctionTool:
    """Create an agent-usable tool backed by vector search.

    Args:
        search: The vector search capability invoked by the tool.
        name: The tool name.
        description: The tool description shown to the model.
        approval_mode: Whether the tool requires approval before invocation.
        search_type: Whether the tool performs vector or keyword-hybrid search.
        parameters: A Pydantic model or JSON schema declaring the tool parameters.
            It must declare ``query`` as a required string. A custom schema can
            expose ``top`` and ``skip`` as integers with finite ``maximum`` values;
            additional fields are passed to ``filter_mapper``.
        top: The default result limit and the maximum when ``parameters`` does not expose ``top``.
        skip: The default offset and the maximum when ``parameters`` does not expose ``skip``.
        filter: A fixed filter applied to each tool invocation.
        filter_mapper: Maps additional declared tool arguments to search filters.
            The default creates equality filters for each additional argument.
        result_mapper: Maps each search response to text or one or more multimodal content items.

    Returns:
        A function tool with only a ``query`` parameter by default. Custom parameters can expose
        ``top``, ``skip``, and fields mapped into filters by ``filter_mapper``.

    Raises:
        ValueError: If parameters or paging limits are invalid.
        NotImplementedError: If the search type is unsupported.
    """
    _validate_paging(top=top, skip=skip)
    map_filter = filter_mapper or _default_search_filter_mapper
    map_result = result_mapper or _default_search_result_mapper
    input_model = parameters if parameters is not None else _default_search_tool_parameters()
    max_top, max_skip = _validate_search_tool_parameters(
        input_model,
        default_top=top,
        default_skip=skip,
    )

    async def search_tool(**arguments: Any) -> list[Content]:
        query = arguments.pop("query")
        if not isinstance(query, str):
            raise TypeError("The search tool 'query' argument must be a string.")
        invocation_top = arguments.pop("top", top)
        invocation_skip = arguments.pop("skip", skip)
        _validate_paging(top=invocation_top, skip=invocation_skip)
        if invocation_top > max_top:
            raise ValueError(f"top must not exceed the configured maximum of {max_top}.")
        if invocation_skip > max_skip:
            raise ValueError(f"skip must not exceed the configured maximum of {max_skip}.")
        dynamic_filter = map_filter(filter, arguments)
        results = await search.search(
            query,
            search_type=search_type,
            filter=dynamic_filter,
            top=invocation_top,
            skip=invocation_skip,
        )
        mapped_results: list[Content] = []
        consumed_results = 0
        async for result in results:
            if consumed_results >= invocation_top:
                break
            consumed_results += 1
            mapped = map_result(result)
            if isinstance(mapped, str):
                mapped_results.append(Content.from_text(mapped))
            elif isinstance(mapped, Content):
                mapped_results.append(mapped)
            else:
                mapped_results.extend(mapped)
        return mapped_results

    return FunctionTool(
        name=name,
        description=description,
        approval_mode=approval_mode,
        func=search_tool,
        input_model=input_model,
    )


def _is_non_string_sequence(value: Any) -> TypeGuard[Sequence[Any]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, Mapping))


async def _as_async_iterable(
    values: AsyncIterable[ResultT] | Sequence[ResultT],
) -> AsyncIterator[ResultT]:
    if isinstance(values, AsyncIterable):
        async for value in values:
            yield value
        return
    for value in values:
        yield value


def _default_search_tool_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The query to search for.",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }


def _validate_search_tool_parameters(
    parameters: type[BaseModel] | Mapping[str, Any],
    *,
    default_top: int,
    default_skip: int,
) -> tuple[int, int]:
    schema: Mapping[str, Any] = parameters.model_json_schema() if isinstance(parameters, type) else parameters
    raw_properties = schema.get("properties")
    if not isinstance(raw_properties, Mapping):
        raise ValueError("Search tool parameters must define object properties.")
    properties = cast(Mapping[str, Any], raw_properties)
    query_schema = properties.get("query")
    required = schema.get("required")
    query_type = cast(Mapping[str, Any], query_schema).get("type") if isinstance(query_schema, Mapping) else None
    if (
        not isinstance(query_schema, Mapping)
        or query_type != "string"
        or not _is_non_string_sequence(required)
        or "query" not in required
    ):
        raise ValueError("Search tool parameters must define 'query' as a required string.")

    limits = {"top": default_top, "skip": default_skip}
    for name, minimum in (("top", 1), ("skip", 0)):
        parameter_schema = properties.get(name)
        if parameter_schema is None:
            continue
        if not isinstance(parameter_schema, Mapping):
            raise ValueError(f"Search tool parameter '{name}' must be an integer.")
        typed_parameter_schema = cast(Mapping[str, Any], parameter_schema)
        if typed_parameter_schema.get("type") != "integer":
            raise ValueError(f"Search tool parameter '{name}' must be an integer.")
        maximum = typed_parameter_schema.get("maximum")
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < minimum:
            raise ValueError(f"Search tool parameter '{name}' must declare an integer maximum of at least {minimum}.")
        configured_default = default_top if name == "top" else default_skip
        if configured_default > maximum:
            raise ValueError(f"Configured {name}={configured_default} exceeds the parameter maximum of {maximum}.")
        limits[name] = maximum
    return limits["top"], limits["skip"]


def _default_search_filter_mapper(
    search_filter: RecordFilters | None,
    arguments: Mapping[str, Any],
) -> RecordFilters | None:
    dynamic_filters: list[RecordFilter] = []
    for name, value in arguments.items():
        if not name.isidentifier():
            raise ValueError(f"Search tool parameter '{name}' cannot be mapped to a model field.")
        dynamic_filters.append(f"lambda record: record.{name} == {value!r}")
    if not dynamic_filters:
        return search_filter
    if search_filter is None:
        return dynamic_filters
    if _is_non_string_sequence(search_filter) and not callable(search_filter):
        return [*cast(Sequence[RecordFilter], search_filter), *dynamic_filters]
    return [cast(RecordFilter, search_filter), *dynamic_filters]


def _default_search_result_mapper(response: SearchResponse[Any]) -> str:
    return msgspec.json.encode(
        response,
        enc_hook=_msgspec_enc_hook,
    ).decode()
