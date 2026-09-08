# Copyright (c) Microsoft. All rights reserved.

"""Dependency-free in-memory vector store."""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, ClassVar, Generic, cast
from uuid import UUID, uuid4

from typing_extensions import TypeVar

from ._feature_stage import ExperimentalFeature, experimental
from ._telemetry import FeatureIndex, mark_feature_used
from ._vector_filters import (
    Filter,
    FilterExpression,
    FilterGroup,
    filter_values_equal,
    require_filter_collection,
    require_filter_string,
    validate_filter,
)
from ._vectors import (
    DISTANCE_FUNCTION_DIRECTION_HELPER,
    BaseVectorCollection,
    BaseVectorSearch,
    BaseVectorStore,
    DistanceFunction,
    EmbeddingClient,
    SearchResults,
    SearchType,
    Vector,
    VectorStoreCollectionDefinition,
    _validate_vector_dimensions,  # pyright: ignore[reportPrivateUsage]
)
from .exceptions import IntegrationException

KeyT = TypeVar("KeyT", default=Any)
ModelT = TypeVar("ModelT", default=Any)

_IN_MEMORY_FILTER_OPERATORS = frozenset({
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "in",
    "not_in",
    "is_null",
    "is_not_null",
    "exists",
    "contains",
    "contains_any",
    "contains_all",
    "starts_with",
    "ends_with",
    "contains_text",
})
_SCALAR_FILTER_TYPES = (str, int, float, bool, bytes, date, datetime, time, timedelta, Decimal, UUID)
_DESCENDING_DISTANCE_FUNCTIONS = frozenset({"cosine_similarity", "dot_prod"})
_IN_MEMORY_DISTANCE_FUNCTIONS = frozenset({
    "cosine_similarity",
    "cosine_distance",
    "dot_prod",
    "negative_dot_prod",
    "euclidean_distance",
    "euclidean_squared_distance",
    "manhattan",
    "hamming",
    "DEFAULT",
})


@dataclass(slots=True)
class _InMemoryCollectionState:
    definition: VectorStoreCollectionDefinition
    records: dict[Any, dict[str, Any]]
    exists: bool = False


def _numeric_vector(value: Any, *, field_name: str) -> tuple[float, ...]:
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        value = to_list()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"Vector field '{field_name}' must contain a numeric sequence.")
    vector: list[float] = []
    for item in cast(Sequence[Any], value):
        if not isinstance(item, int | float) or isinstance(item, bool):
            raise TypeError(f"Vector field '{field_name}' must contain only numbers.")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError(f"Vector field '{field_name}' must contain only finite numbers.")
        vector.append(number)
    if not vector:
        raise ValueError(f"Vector field '{field_name}' cannot be empty.")
    return tuple(vector)


def _paired_vectors(left: Vector, right: Vector) -> tuple[tuple[float, ...], tuple[float, ...]]:
    normalized_left = _numeric_vector(left, field_name="query")
    normalized_right = _numeric_vector(right, field_name="stored")
    if len(normalized_left) != len(normalized_right):
        raise ValueError(
            f"Query and stored vectors must have the same length; "
            f"got {len(normalized_left)} and {len(normalized_right)}."
        )
    return normalized_left, normalized_right


def _calculate_score(left: Vector, right: Vector, distance_function: DistanceFunction) -> float:
    left_values, right_values = _paired_vectors(left, right)
    if distance_function in ("cosine_similarity", "cosine_distance", "DEFAULT"):
        left_scale = max(abs(value) for value in left_values)
        right_scale = max(abs(value) for value in right_values)
        if left_scale == 0 or right_scale == 0:
            raise ValueError("Cosine distance is undefined for zero-magnitude vectors.")
        left_scaled = tuple(value / left_scale for value in left_values)
        right_scaled = tuple(value / right_scale for value in right_values)
        dot_product = math.fsum(a * b for a, b in zip(left_scaled, right_scaled, strict=True))
        left_norm = math.sqrt(math.fsum(value * value for value in left_scaled))
        right_norm = math.sqrt(math.fsum(value * value for value in right_scaled))
        similarity = dot_product / (left_norm * right_norm)
        if not math.isfinite(similarity):
            raise ValueError("Cosine similarity must be finite.")
        similarity = max(-1.0, min(1.0, similarity))
        score = similarity if distance_function == "cosine_similarity" else 1 - similarity
    elif distance_function == "dot_prod":
        score = sum(a * b for a, b in zip(left_values, right_values, strict=True))
    elif distance_function == "negative_dot_prod":
        score = -sum(a * b for a, b in zip(left_values, right_values, strict=True))
    elif distance_function == "euclidean_distance":
        score = math.dist(left_values, right_values)
    elif distance_function == "euclidean_squared_distance":
        score = sum((a - b) * (a - b) for a, b in zip(left_values, right_values, strict=True))
    elif distance_function == "manhattan":
        score = sum(abs(a - b) for a, b in zip(left_values, right_values, strict=True))
    elif distance_function == "hamming":
        score = sum(a != b for a, b in zip(left_values, right_values, strict=True)) / len(left_values)
    else:
        raise NotImplementedError(f"Distance function '{distance_function}' is not supported by InMemoryCollection.")
    if not math.isfinite(score):
        raise ValueError(f"Distance function '{distance_function}' produced a non-finite score.")
    return score


def _validate_in_memory_filter_value(value: Any) -> None:
    if value is None or isinstance(value, _SCALAR_FILTER_TYPES):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("In-memory filter values must be finite.")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError("In-memory filter values must be finite.")
        return
    if isinstance(value, Mapping):
        raise TypeError("InMemoryCollection does not support mapping filter values.")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in cast(Sequence[Any], value):
            _validate_in_memory_filter_value(item)
        return
    raise TypeError(f"InMemoryCollection does not support filter values of type '{type(value).__name__}'.")


def _resolve_record_value(
    record: Mapping[str, Any],
    filter_: Filter,
    definition: VectorStoreCollectionDefinition,
) -> tuple[bool, Any]:
    if "." in filter_.field_name:
        raise NotImplementedError("InMemoryCollection does not support nested filter field paths.")
    field = definition.try_get_field(filter_.field_name)
    if field is None:
        raise ValueError(f"Filter field '{filter_.field_name}' is not part of the vector store definition.")
    storage_name = field.storage_name or field.name
    return storage_name in record, record.get(storage_name)


def _evaluate_filter(
    expression: FilterExpression,
    record: Mapping[str, Any],
    definition: VectorStoreCollectionDefinition,
) -> bool:
    if isinstance(expression, FilterGroup):
        values = (_evaluate_filter(item, record, definition) for item in expression.filters)
        match expression.operator:
            case "and":
                return all(values)
            case "or":
                return any(values)
            case "not":
                return not next(values)
            case _:
                raise ValueError(f"Unknown filter group operator '{expression.operator}'.")

    exists, actual = _resolve_record_value(record, expression, definition)
    operator = expression.operator
    expected = expression.value
    if operator == "exists":
        return exists
    if operator == "is_null":
        return exists and actual is None
    if operator == "is_not_null":
        return exists and actual is not None
    if not exists:
        return False
    if actual is None and operator not in ("eq", "ne"):
        return False

    try:
        match operator:
            case "eq":
                return filter_values_equal(actual, expected)
            case "ne":
                return not filter_values_equal(actual, expected)
            case "gt":
                return actual > expected
            case "gte":
                return actual >= expected
            case "lt":
                return actual < expected
            case "lte":
                return actual <= expected
            case "between":
                lower, upper = cast(Sequence[Any], expected)
                return lower <= actual <= upper
            case "in":
                return any(filter_values_equal(actual, item) for item in cast(Collection[Any], expected))
            case "not_in":
                return all(not filter_values_equal(actual, item) for item in cast(Collection[Any], expected))
            case "contains":
                return any(filter_values_equal(item, expected) for item in require_filter_collection(actual))
            case "contains_any":
                collection = require_filter_collection(actual)
                return any(
                    filter_values_equal(item, value) for value in cast(Sequence[Any], expected) for item in collection
                )
            case "contains_all":
                collection = require_filter_collection(actual)
                return all(
                    any(filter_values_equal(item, value) for item in collection)
                    for value in cast(Sequence[Any], expected)
                )
            case "starts_with":
                return require_filter_string(actual).startswith(require_filter_string(expected))
            case "ends_with":
                return require_filter_string(actual).endswith(require_filter_string(expected))
            case "contains_text":
                return require_filter_string(expected) in require_filter_string(actual)
            case _:
                raise NotImplementedError(f"Filter operator '{operator}' is not supported by InMemoryCollection.")
    except TypeError as exc:
        raise ValueError(
            f"Filter operator '{operator}' cannot compare field '{expression.field_name}' with value {expected!r}."
        ) from exc


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class InMemoryCollection(
    BaseVectorCollection[KeyT, ModelT],
    BaseVectorSearch[KeyT, ModelT],
    Generic[KeyT, ModelT],
):
    """Store and search vector records in process memory.

    This implementation is intended for tests and development. It is
    nonpersistent, uses linear scans, and is not thread-safe.

    Scoring, filtering, and score thresholds are applied locally before paging.
    The default metric is cosine distance, so its threshold is a maximum distance.
    Hamming scores are the proportion of unequal dimensions, between zero and
    one, not a mismatch count. Non-finite scores are rejected. Records are
    normalized by the shared serializer before storage; custom codecs and
    connector overrides remain trusted Python code, not sandboxed execution.
    """

    supported_search_types: ClassVar[set[SearchType]] = {"vector"}
    supported_vector_types: ClassVar[set[str] | None] = {
        "float",
        "float16",
        "float32",
        "float64",
        "int",
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
    }

    def __init__(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> None:
        """Initialize an in-memory collection.

        Args:
            record_type: The application record type.
            definition: An explicit definition for dictionary or externally owned records.
            collection_name: The collection name, overriding the model definition.
            embedding_generator: The default client used to generate vectors.
        """
        super().__init__(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator,
        )
        self._state = _InMemoryCollectionState(self.definition, {})

    def _require_collection(self) -> None:
        if not self._state.exists:
            raise IntegrationException(f"Collection '{self.collection_name}' does not exist.")

    async def ensure_collection_exists(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Create the collection when it does not exist."""
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        self._state.exists = True

    async def collection_exists(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return whether the collection exists."""
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return self._state.exists

    async def ensure_collection_deleted(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Delete all records and mark the collection as absent."""
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        self._state.records.clear()
        self._state.exists = False

    async def _inner_upsert(
        self,
        records: Sequence[Any],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[KeyT]:
        self._require_collection()
        keys: list[KeyT] = []
        for record in records:
            if not isinstance(record, dict):
                raise TypeError("In-memory records must serialize to dictionaries.")
            stored_record = deepcopy(cast(dict[str, Any], record))
            key_field = self.definition.key_field
            key_storage_name = self.definition.key_field_storage_name
            if key_storage_name not in stored_record:
                if not key_field.is_auto_generated:
                    raise ValueError(f"Record is missing key field '{key_field.name}'.")
                if key_field.type_ == "str":
                    stored_record[key_storage_name] = str(uuid4())
                else:
                    raise NotImplementedError("InMemoryCollection can auto-generate only string keys.")
            key = stored_record[key_storage_name]
            try:
                hash(key)
            except TypeError as exc:
                raise TypeError("In-memory record keys must be hashable.") from exc
            self._state.records[key] = stored_record
            keys.append(cast(KeyT, key))
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
    ) -> Sequence[Any] | None:
        self._require_collection()
        if keys is not None:
            return [deepcopy(self._state.records[key]) for key in keys if key in self._state.records]
        records = list(self._state.records.values())
        if filter is not None:
            _validate_in_memory_filter(filter, self.definition)
            records = [record for record in records if _evaluate_filter(filter, record, self.definition)]
        if order_by:
            for field_name, ascending in reversed(tuple(order_by.items())):
                if not isinstance(ascending, bool):
                    raise TypeError(f"Order direction for field '{field_name}' must be a boolean.")
                field = self.definition.try_get_field(field_name)
                if field is None:
                    raise ValueError(f"Order field '{field_name}' is not part of the vector store definition.")
                storage_name = field.storage_name or field.name
                try:
                    records_with_values = [record for record in records if record[storage_name] is not None]
                    records_without_values = [record for record in records if record[storage_name] is None]
                    records_with_values.sort(key=lambda record: record[storage_name], reverse=not ascending)
                    records[:] = [*records_with_values, *records_without_values]
                except (KeyError, TypeError) as exc:
                    raise ValueError(f"Records cannot be ordered by field '{field_name}'.") from exc
        return deepcopy(records[skip : skip + top])

    async def _inner_delete(
        self,
        keys: Sequence[KeyT],
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        self._require_collection()
        for key in keys:
            self._state.records.pop(key, None)

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
        self._require_collection()
        if search_type != "vector":
            raise NotImplementedError("InMemoryCollection supports only vector search.")
        if vector is None:
            raise ValueError("InMemoryCollection vector search requires a query vector or embedding generator.")
        query_vector = _numeric_vector(vector, field_name="query")
        vector_field = self.definition.try_get_vector_field(vector_property_name)
        if vector_field is None:
            raise ValueError("InMemoryCollection vector search requires a vector field.")
        _validate_vector_dimensions(query_vector, vector_field)
        if filter is not None:
            _validate_in_memory_filter(filter, self.definition)

        distance_function = vector_field.distance_function or "DEFAULT"
        if distance_function == "DEFAULT":
            distance_function = "cosine_distance"
        if distance_function not in _IN_MEMORY_DISTANCE_FUNCTIONS:
            raise NotImplementedError(
                f"Distance function '{distance_function}' is not supported by InMemoryCollection."
            )
        comparison = DISTANCE_FUNCTION_DIRECTION_HELPER[distance_function]
        storage_name = vector_field.storage_name or vector_field.name
        results: list[dict[str, Any]] = []
        key_storage_name = self.definition.key_field_storage_name
        for record in self._state.records.values():
            if filter is not None and not _evaluate_filter(filter, record, self.definition):
                continue
            stored_vector = record.get(storage_name)
            if stored_vector is None:
                continue
            try:
                score = _calculate_score(query_vector, stored_vector, distance_function)
            except TypeError as exc:
                raise TypeError(
                    f"Record {record.get(key_storage_name)!r} has an invalid vector in field '{storage_name}': {exc}"
                ) from exc
            except ValueError as exc:
                raise ValueError(
                    f"Record {record.get(key_storage_name)!r} has an invalid vector in field '{storage_name}': {exc}"
                ) from exc
            if score_threshold is not None and not comparison(score, score_threshold):
                continue
            results.append({"record": deepcopy(record), "score": score})
        results.sort(
            key=lambda result: cast(float, result["score"]),
            reverse=distance_function in _DESCENDING_DISTANCE_FUNCTIONS,
        )
        total_count = len(results)
        return SearchResults(
            results[skip : skip + top],
            metadata={"in_memory_total_count": total_count},
        )

    def _get_record_from_result(self, result: Any) -> Any:
        if not isinstance(result, Mapping):
            raise TypeError("In-memory search results must be mappings.")
        return cast(Mapping[str, Any], result)["record"]

    def _get_score_from_result(self, result: Any) -> float | None:
        if not isinstance(result, Mapping):
            raise TypeError("In-memory search results must be mappings.")
        score = cast(Mapping[str, Any], result).get("score")
        return cast(float | None, score)


def _walk_filters(expression: FilterExpression) -> tuple[Filter, ...]:
    if isinstance(expression, Filter):
        return (expression,)
    return tuple(item for child in expression.filters for item in _walk_filters(child))


def _validate_in_memory_filter(
    expression: FilterExpression,
    definition: VectorStoreCollectionDefinition,
) -> None:
    validate_filter(expression, field_names=definition.names)
    for item in _walk_filters(expression):
        if item.operator not in _IN_MEMORY_FILTER_OPERATORS:
            raise NotImplementedError(f"Filter operator '{item.operator}' is not supported by InMemoryCollection.")
        if "." in item.field_name:
            raise NotImplementedError("InMemoryCollection does not support nested filter field paths.")
        _validate_in_memory_filter_value(item.value)


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
class InMemoryStore(BaseVectorStore):
    """Create in-memory collection clients that share process-local state."""

    def __init__(
        self,
        *,
        embedding_generator: EmbeddingClient | None = None,
    ) -> None:
        """Initialize an in-memory vector store.

        Args:
            embedding_generator: The default client used by collection search and upsert operations.
        """
        super().__init__(embedding_generator=embedding_generator)
        self._collections: dict[str, _InMemoryCollectionState] = {}

    def get_collection(
        self,
        record_type: type[ModelT],
        *,
        definition: VectorStoreCollectionDefinition | None = None,
        collection_name: str | None = None,
        embedding_generator: EmbeddingClient | None = None,
    ) -> InMemoryCollection[Any, ModelT]:
        """Create a collection client tied to shared in-memory state.

        Args:
            record_type: The application record type.
            definition: An explicit definition for dictionary or externally owned records.
            collection_name: The collection name, overriding the model definition.
            embedding_generator: A collection-specific embedding client.

        Returns:
            A collection client sharing state with other clients for the same name.

        Raises:
            ValueError: If the collection name is already associated with another definition.
        """
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        collection = InMemoryCollection(
            record_type,
            definition=definition,
            collection_name=collection_name,
            embedding_generator=embedding_generator if embedding_generator is not None else self.embedding_generator,
        )
        state = self._collections.get(collection.collection_name)
        if state is None:
            self._collections[collection.collection_name] = collection._state  # pyright: ignore[reportPrivateUsage]
            return collection
        if state.definition != collection.definition:
            raise ValueError(
                f"Collection '{collection.collection_name}' is already registered with another definition."
            )
        collection._state = state  # pyright: ignore[reportPrivateUsage]
        return collection

    async def list_collection_names(
        self,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> Sequence[str]:
        """List existing in-memory collection names."""
        mark_feature_used(FeatureIndex.CORE_VECTOR_STORES)
        return sorted(name for name, state in self._collections.items() if state.exists)

    async def _inner_ensure_collection_deleted(
        self,
        collection_name: str,
        *,
        operation_options: Mapping[str, Any] | None = None,
    ) -> None:
        state = self._collections[collection_name]
        state.records.clear()
        state.exists = False
