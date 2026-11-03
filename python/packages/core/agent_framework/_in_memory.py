# Copyright (c) Microsoft. All rights reserved.

"""Dependency-free in-memory vector store."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any, ClassVar, Generic, cast
from uuid import UUID, uuid4

from typing_extensions import TypeVar

from ._feature_stage import ExperimentalFeature, experimental
from ._telemetry import FeatureIndex, mark_feature_used
from ._vector_filters import (
    _TEXT_VALUE_OPERATORS,  # pyright: ignore[reportPrivateUsage]
    Filter,
    FilterExpression,
    FilterGroup,
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
    _evaluate_filter,  # pyright: ignore[reportPrivateUsage]
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
        vector.append(item)
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
    if distance_function == "hamming":
        # Compare coordinates before float conversion can round distinct large integers to the same value.
        return sum(a != b for a, b in zip(left_values, right_values, strict=True)) / len(left_values)
    left_values = tuple(float(value) for value in left_values)
    right_values = tuple(float(value) for value in right_values)
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
    else:
        raise NotImplementedError(f"Distance function '{distance_function}' is not supported by InMemoryCollection.")
    if not math.isfinite(score):
        raise ValueError(f"Distance function '{distance_function}' produced a non-finite score.")
    return score


_DURATION_PATTERN = re.compile(
    r"^(?P<sign>-)?P(?:(?P<days>[0-9]+(?:\.[0-9]+)?)D)?"
    r"(?:T(?:(?P<hours>[0-9]+(?:\.[0-9]+)?)H)?(?:(?P<minutes>[0-9]+(?:\.[0-9]+)?)M)?"
    r"(?:(?P<seconds>[0-9]+(?:\.[0-9]+)?)S)?)?$"
)


def _restore_datetime(value: str) -> datetime:
    """Parse a timestamp the shared serializer wrote."""
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    restored = datetime.fromisoformat(value)
    if restored.tzinfo is not None:
        # Aware values compare by instant, and CPython only guarantees that
        # when both sides name their time the same way: in a repeated DST
        # hour a zone datetime is unequal to the fixed-offset form parsed
        # back from the record even at the same instant.
        return restored.astimezone(timezone.utc)
    return restored


def _restore_timedelta(value: str) -> timedelta:
    """Parse the ISO 8601 duration the shared serializer wrote.

    The components are summed as exact decimals of microseconds: the string
    the serializer writes carries every microsecond, while a ``float`` of the
    total seconds loses them on the largest durations (``timedelta.max`` even
    rounds past the range the type supports). The arithmetic runs in an
    isolated context with ample precision, so an application that lowers the
    ambient Decimal precision cannot change what a duration filter matches.
    """
    match = _DURATION_PATTERN.match(value)
    if match is None:
        raise ValueError(f"Unsupported duration '{value}'.")
    parts = match.groupdict()
    with localcontext() as ctx:
        ctx.prec = 40
        microseconds = (
            Decimal(parts["days"] or "0") * 86_400_000_000
            + Decimal(parts["hours"] or "0") * 3_600_000_000
            + Decimal(parts["minutes"] or "0") * 60_000_000
            + Decimal(parts["seconds"] or "0") * 1_000_000
        )
        micros = int(microseconds.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    delta = timedelta(microseconds=micros)
    return -delta if parts["sign"] else delta


def _restore_time(value: str) -> time:
    """Parse a time of day the shared serializer wrote."""
    if value.endswith("Z"):
        # The serializer writes a UTC time with a trailing "Z", which
        # ``time.fromisoformat`` accepts only from Python 3.11.
        value = f"{value[:-1]}+00:00"
    return time.fromisoformat(value)


_RESTORE_IN_MEMORY_VALUE_TYPES: dict[str, Callable[[str], Any]] = {
    "datetime": _restore_datetime,
    "date": date.fromisoformat,
    "time": _restore_time,
    "timedelta": _restore_timedelta,
    "UUID": UUID,
    "Decimal": Decimal,
}
_SERIALIZED_SCALAR_TYPE_NAMES = frozenset(_RESTORE_IN_MEMORY_VALUE_TYPES)
_TEXT_STORED_TYPE_NAMES = _SERIALIZED_SCALAR_TYPE_NAMES - {"Decimal"}
_COMPARISON_OPERATORS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte"})
_SEQUENCE_OPERAND_OPERATORS = frozenset({"between", "in", "not_in"})
_COLLECTION_OPERATORS = frozenset({"contains", "contains_any", "contains_all"})


def _restore_in_memory_value(value: Any, type_tag: str | None) -> Any:
    """Return a stored value in the type its field declares.

    In-memory records are stored through the shared serializer, so a native
    scalar such as a datetime is held as its serialized value. A filter
    operand arrives native, so the stored value is restored before the
    comparison and the comparison keeps the field's semantics.
    """
    if not isinstance(value, str) or type_tag is None:
        return value
    restore = _RESTORE_IN_MEMORY_VALUE_TYPES.get(type_tag)
    if restore is None:
        return value
    try:
        return restore(value)
    except (TypeError, ValueError):
        return value


def _evaluate_in_memory_filter(
    expression: FilterExpression,
    record: Mapping[str, Any],
    definition: VectorStoreCollectionDefinition,
) -> bool:
    """Evaluate a filter against the record as it is stored, one leaf at a time.

    A comparison operator restores its own leaf's field to the type the field
    declares, so the native operand compares in the field's semantics. Aware
    datetimes are named in UTC on both sides of the comparison so an operand
    in any zone matches the instant that was stored. The text operators stay
    on the stored string, which lets one group mix a text operator and a
    native comparison over the same field.
    """
    if isinstance(expression, FilterGroup):
        values = (_evaluate_in_memory_filter(item, record, definition) for item in expression.filters)
        match expression.operator:
            case "and":
                return all(values)
            case "or":
                return any(values)
            case "not":
                return not next(values)
            case _:
                raise ValueError(f"Unknown filter group operator '{expression.operator}'.")
    field = definition.try_get_field(expression.field_name)
    if (
        field is None
        or field.type_ not in _SERIALIZED_SCALAR_TYPE_NAMES
        or expression.operator in _TEXT_VALUE_OPERATORS
    ):
        return _evaluate_filter(_normalized_in_memory_leaf(expression, field), record, definition)
    restored = dict(record)
    storage_name = field.storage_name or field.name
    if storage_name in restored:
        restored[storage_name] = _restore_in_memory_value(restored[storage_name], field.type_)
    return _evaluate_filter(_normalized_in_memory_leaf(expression, field), restored, definition)


def _normalized_key_operand(field: Any, operand: Any) -> Any:
    """Return a UUID key operand in the field's native comparison form.

    Scoped tools address UUID keys through their canonical string form
    (``key_from_json``), so a canonical string operand normalizes to UUID for
    the compatibility check and the comparison instead of being rejected by
    the exact-type match. Anything else passes through unchanged.
    """
    if field.field_type == "key" and field.type_ == "UUID" and isinstance(operand, str):
        try:
            return UUID(operand)
        except ValueError:
            return operand
    return operand


def _normalized_key_leaf(expression: Filter, field: Any) -> Filter:
    """Return the leaf with its UUID key operands normalized when present.

    Text operators keep string operands unchanged: they compare against the
    stored key exactly as the canonical string was written, and a normalized
    UUID would make ``starts_with`` and friends raise.
    """
    if (
        field is None
        or field.field_type != "key"
        or field.type_ != "UUID"
        or expression.operator in _TEXT_VALUE_OPERATORS
    ):
        return expression
    value = expression.value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = cast("Sequence[Any]", value)
        normalized: Any = [_normalized_key_operand(field, item) for item in items]
    else:
        normalized = _normalized_key_operand(field, value)
    if normalized == value:
        return expression
    return Filter(expression.field_name, expression.operator, normalized)


def _normalized_datetime_operand(field: Any, operand: Any) -> Any:
    """Return aware datetime operands as the common instant in UTC.

    CPython compares aware datetimes that carry different tzinfo objects per
    wall clock, so in a repeated DST hour a zone datetime is unequal to the
    fixed-offset form a record is restored to even at the same instant.
    Naming UTC on both sides pins equality, ordering and membership to
    instants. Naive datetimes and anything else pass through unchanged.
    """
    if field is None or field.type_ != "datetime":
        return operand
    if isinstance(operand, datetime):
        return operand.astimezone(timezone.utc) if operand.tzinfo is not None else operand
    if isinstance(operand, Sequence) and not isinstance(operand, (str, bytes, bytearray)):
        items = cast("Sequence[Any]", operand)
        return [_normalized_datetime_operand(field, item) for item in items]
    return operand


def _normalized_in_memory_leaf(expression: Filter, field: Any) -> Filter:
    """Return the leaf with key and datetime operands in comparison form.

    Key operands normalize so a canonical string compares against the UUID
    that was stored, and aware datetime operands normalize to UTC so both
    sides of the comparison name the same instant. Text operators keep their
    operands verbatim: they address the stored string.
    """
    if field is None or field.type_ != "datetime" or expression.operator in _TEXT_VALUE_OPERATORS:
        return _normalized_key_leaf(expression, field)
    leaf = _normalized_key_leaf(expression, field)
    return Filter(leaf.field_name, leaf.operator, _normalized_datetime_operand(field, leaf.value))


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
            _reject_incompatible_filter_operands(filter, self.definition)
            records = [record for record in records if _evaluate_in_memory_filter(filter, record, self.definition)]
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
            _reject_incompatible_filter_operands(filter, self.definition)

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
            if filter is not None and not _evaluate_in_memory_filter(filter, record, self.definition):
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
            results.append({"record": record, "score": score})
        results.sort(
            key=lambda result: cast(float, result["score"]),
            reverse=distance_function in _DESCENDING_DISTANCE_FUNCTIONS,
        )
        total_count = len(results)
        return SearchResults(
            deepcopy(results[skip : skip + top]),
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


def _filter_operand_values(item: Filter) -> tuple[Any, ...]:
    """Return the operands a filter compares against the field value.

    The collection operators compare their operands element by element, so
    their values count as operands too.
    """
    if item.operator in _COMPARISON_OPERATORS:
        return (item.value,)
    if item.operator in _SEQUENCE_OPERAND_OPERATORS or item.operator in _COLLECTION_OPERATORS:
        value = item.value
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return tuple(cast(Sequence[Any], value))
        return (value,)
    return ()


def _operand_matches_field_type(field_type: str, operand: Any) -> bool:
    """Return True when the operand can be compared in the type the field declares.

    A field stored as a native value compares exactly with Python's own numeric
    equality and ordering, so numeric operands fit any of those fields; only
    the types the serializer writes as text can never be compared against them.
    An ``int`` operand also fits a ``Decimal`` field: the restore compares the
    two exactly, in equality and in ordering.
    """
    if operand is None:
        return True
    operand_type = type(operand).__name__
    if field_type in _SERIALIZED_SCALAR_TYPE_NAMES:
        return operand_type == field_type or (field_type == "Decimal" and operand_type == "int")
    return operand_type not in _TEXT_STORED_TYPE_NAMES


def _reject_incompatible_filter_operands(
    expression: FilterExpression,
    definition: VectorStoreCollectionDefinition,
) -> None:
    """Reject an operand that cannot be compared in the type the field declares.

    A record is stored through the shared serializer, so the scalar types it
    writes as text are restored before the comparison. An operand of another
    type cannot be compared in the field's own semantics, so it is rejected
    instead of quietly matching no record. The text operators are exempt:
    they compare the stored string itself, and their operand is already
    required to be a string by the shared filter validation. A collection
    field stores its elements as the serializer writes them, so an operand
    element of a text-stored type can never match there and is rejected too.
    """
    for item in _walk_filters(expression):
        field = definition.try_get_field(item.field_name)
        if field is None or field.type_ is None:
            continue
        if item.operator in _TEXT_VALUE_OPERATORS:
            continue
        for operand in _filter_operand_values(item):
            if _operand_matches_field_type(field.type_, _normalized_key_operand(field, operand)):
                continue
            raise TypeError(
                f"InMemoryCollection cannot compare field '{item.field_name}' of type '{field.type_}' "
                f"with a filter operand of type '{type(operand).__name__}'. The in-memory connector "
                "compares native scalars in the type the field declares."
            )


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
