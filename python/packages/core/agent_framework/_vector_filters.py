# Copyright (c) Microsoft. All rights reserved.

"""Portable vector store filter expressions.

Common operator semantics:

- ``eq`` / ``ne`` compare one field value and treat booleans as distinct from numbers.
- ``gt`` / ``gte`` / ``lt`` / ``lte`` perform ordered scalar comparisons.
- ``between`` is inclusive and accepts exactly ``(lower, upper)``.
- ``in`` / ``not_in`` test whether the field value occurs in the supplied sequence.
- ``contains`` tests whether a non-mapping collection field contains one supplied value.
- ``contains_any`` / ``contains_all`` test collection fields against supplied sequences.
- ``is_null`` / ``is_not_null`` require the field to exist; use ``exists`` to test presence alone.
- ``starts_with`` / ``ends_with`` / ``contains_text`` operate on strings.

A missing field returns ``False`` for every operator except ``exists``. Use
``FilterGroup`` for explicit AND, OR, and NOT composition. Provider-specific
operators must be namespaced and are interpreted only by their connector.
"""

from __future__ import annotations

import keyword
import math
import re
from collections.abc import Collection, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from types import UnionType
from typing import Any, Final, Literal, TypeAlias, Union, cast, get_args, get_origin

from typing_extensions import Sentinel

from ._feature_stage import ExperimentalFeature, experimental

FilterOperator: TypeAlias = (
    Literal[
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
    ]
    | str
)
FilterGroupOperator: TypeAlias = Literal["and", "or", "not"]

_STANDARD_FILTER_OPERATORS: Final[frozenset[str]] = frozenset({
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
_NO_VALUE_OPERATORS: Final[frozenset[str]] = frozenset({"is_null", "is_not_null", "exists"})
_SEQUENCE_VALUE_OPERATORS: Final[frozenset[str]] = frozenset({
    "between",
    "in",
    "not_in",
    "contains_any",
    "contains_all",
})
_GROUP_OPERATORS: Final[frozenset[str]] = frozenset({"and", "or", "not"})
_PROVIDER_OPERATOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
_PARAM_UNSET = Sentinel("_PARAM_UNSET")
_OMIT_FILTER = Sentinel("_OMIT_FILTER")


def _is_non_string_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def require_filter_collection(value: Any) -> Collection[Any]:
    """Return a non-string, non-mapping collection filter value."""
    if not isinstance(value, Collection) or isinstance(value, (str, bytes, bytearray, Mapping)):
        raise TypeError("Filter value must be a non-string, non-mapping collection.")
    return cast(Collection[Any], value)


def require_filter_string(value: Any) -> str:
    """Return a string filter value."""
    if not isinstance(value, str):
        raise TypeError("Filter value must be a string.")
    return value


def filter_values_equal(left: Any, right: Any) -> bool:
    """Compare filter values while keeping booleans distinct from numbers."""
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    return left == right


def _validate_name(name: str, *, kind: str, allow_path: bool) -> None:
    if not name:
        raise ValueError(f"{kind} cannot be empty.")
    segments = name.split(".") if allow_path else [name]
    for segment in segments:
        if (
            not segment.isidentifier()
            or keyword.iskeyword(segment)
            or (segment.startswith("__") and segment.endswith("__"))
        ):
            raise ValueError(f"Invalid {kind.lower()} '{name}'.")


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
@dataclass(frozen=True, slots=True, init=False)
class Param:
    """Reference one model-set search-tool parameter.

    An optional parameter without a default removes the containing filter when
    omitted. Required parameters and parameters with defaults are substituted
    before the filter reaches the vector store.
    """

    name: str
    value_type: Any
    required: bool
    _default: Any
    description: str | None
    minimum: float | int | None
    maximum: float | int | None
    min_length: int | None
    max_length: int | None
    pattern: str | None

    def __init__(
        self,
        name: str,
        value_type: Any,
        *,
        required: bool = False,
        default: Any = _PARAM_UNSET,
        description: str | None = None,
        minimum: float | int | None = None,
        maximum: float | int | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        pattern: str | None = None,
    ) -> None:
        """Initialize a parameter reference.

        Args:
            name: The tool parameter name exposed to the model.
            value_type: The Python type used for schema generation and validation.
            required: Whether the model must supply the parameter.
            default: The value used when an optional parameter is omitted.
            description: The parameter description shown to the model.
            minimum: The inclusive minimum for numeric values.
            maximum: The inclusive maximum for numeric values.
            min_length: The minimum length for string, array, or object values.
            max_length: The maximum length for string, array, or object values.
            pattern: A full-match regular expression. String values that do not match are rejected.

        Raises:
            ValueError: If the name is invalid or a required parameter declares a default.
        """
        _validate_name(name, kind="Parameter name", allow_path=False)
        if name == "query":
            raise ValueError("'query' is reserved by vector search tools.")
        if required and default is not _PARAM_UNSET:
            raise ValueError("A required parameter cannot declare a default.")
        if minimum is not None and (isinstance(minimum, bool) or not math.isfinite(minimum)):
            raise ValueError("Param minimum must be a finite number.")
        if maximum is not None and (isinstance(maximum, bool) or not math.isfinite(maximum)):
            raise ValueError("Param maximum must be a finite number.")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("Param minimum cannot exceed maximum.")
        if min_length is not None and (
            not isinstance(min_length, int) or isinstance(min_length, bool) or min_length < 0
        ):
            raise ValueError("Param min_length must be a non-negative integer.")
        if max_length is not None and (
            not isinstance(max_length, int) or isinstance(max_length, bool) or max_length < 0
        ):
            raise ValueError("Param max_length must be a non-negative integer.")
        if min_length is not None and max_length is not None and min_length > max_length:
            raise ValueError("Param min_length cannot exceed max_length.")
        if pattern is not None:
            if max_length is None:
                raise ValueError("A Param pattern requires max_length to bound validation work.")
            if max_length > 2048:
                raise ValueError("A Param pattern requires max_length of at most 2048.")
            if len(pattern) > 512:
                raise ValueError("Param patterns cannot exceed 512 characters.")
            re.compile(pattern)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "value_type", value_type)
        object.__setattr__(self, "required", required)
        object.__setattr__(self, "_default", deepcopy(default))
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "min_length", min_length)
        object.__setattr__(self, "max_length", max_length)
        object.__setattr__(self, "pattern", pattern)
        param_schema(self)

    @property
    def has_default(self) -> bool:
        """Return whether the parameter declares a default value."""
        return self._default is not _PARAM_UNSET

    @property
    def default(self) -> Any:
        """Return an independent copy of the default value."""
        return deepcopy(self._default)


def _json_type(value_type: Any) -> str | None:
    if value_type is str:
        return "string"
    if value_type is int:
        return "integer"
    if value_type is float:
        return "number"
    if value_type is bool:
        return "boolean"
    if value_type is type(None):
        return "null"
    return None


def _schema_for_type(value_type: Any) -> dict[str, Any]:
    origin = get_origin(value_type)
    if origin is Literal:
        values = list(get_args(value_type))
        schema: dict[str, Any] = {"enum": values}
        json_types = {_json_type(type(value)) for value in values}
        if len(json_types) == 1 and None not in json_types:
            schema["type"] = json_types.pop()
        return schema
    if origin in (Union, UnionType):
        return {"anyOf": [_schema_for_type(item) for item in get_args(value_type)]}
    if origin in (list, tuple, Sequence):
        args = get_args(value_type)
        item_type = args[0] if args else Any
        return {"type": "array", "items": _schema_for_type(item_type)}
    if origin in (dict, Mapping):
        args = get_args(value_type)
        value_annotation = args[1] if len(args) == 2 else Any
        return {"type": "object", "additionalProperties": _schema_for_type(value_annotation)}
    if value_type is Any:
        raise TypeError("Param requires an explicit JSON-compatible value type.")
    schema_type = _json_type(value_type)
    if schema_type is not None:
        return {"type": schema_type}
    raise TypeError(f"Param type '{value_type}' cannot be represented as JSON Schema.")


def param_schema(param: Param) -> dict[str, Any]:
    """Build a JSON Schema property for a parameter without Pydantic."""
    schema = _schema_for_type(param.value_type)
    if param.description is not None:
        schema["description"] = param.description
    if param.has_default:
        schema["default"] = param.default
    if param.minimum is not None:
        schema["minimum"] = param.minimum
    if param.maximum is not None:
        schema["maximum"] = param.maximum
    schema_types = _schema_types(schema)
    non_null_schema_types = schema_types - {"null"}
    if (param.min_length is not None or param.max_length is not None or param.pattern is not None) and len(
        non_null_schema_types
    ) != 1:
        raise ValueError("Param length and pattern constraints require one string, array, or object type.")
    schema_type = next(iter(non_null_schema_types), None)
    if schema_type not in (None, "string", "array", "object") and (
        param.min_length is not None or param.max_length is not None or param.pattern is not None
    ):
        raise ValueError("Param length and pattern constraints require a string, array, or object type.")
    if param.pattern is not None and schema_type != "string":
        raise ValueError("Param pattern requires a string value type.")
    if param.min_length is not None:
        length_key = (
            "minLength" if schema_type == "string" else "minProperties" if schema_type == "object" else "minItems"
        )
        _set_schema_constraint(schema, schema_type, length_key, param.min_length)
    if param.max_length is not None:
        length_key = (
            "maxLength" if schema_type == "string" else "maxProperties" if schema_type == "object" else "maxItems"
        )
        _set_schema_constraint(schema, schema_type, length_key, param.max_length)
    if param.pattern is not None:
        _set_schema_constraint(schema, "string", "pattern", param.pattern)
    return schema


def _schema_types(schema: Mapping[str, Any]) -> set[str]:
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        return {schema_type}
    variants = schema.get("anyOf")
    if not isinstance(variants, Sequence):
        return set()
    return {
        item_type
        for variant in cast(Sequence[Any], variants)
        if isinstance(variant, Mapping)
        for item_type in _schema_types(cast(Mapping[str, Any], variant))
    }


def _set_schema_constraint(
    schema: dict[str, Any],
    schema_type: str | None,
    key: str,
    value: Any,
) -> None:
    if schema.get("type") == schema_type:
        schema[key] = value
        return
    for variant in cast(Sequence[Any], schema.get("anyOf", ())):
        if isinstance(variant, dict):
            typed_variant = cast(dict[str, Any], variant)
            if typed_variant.get("type") == schema_type:
                typed_variant[key] = value


def _matches_param_type(value: Any, value_type: Any) -> bool:
    origin = get_origin(value_type)
    if origin is Literal:
        return any(filter_values_equal(value, item) for item in get_args(value_type))
    if origin in (Union, UnionType):
        return any(_matches_param_type(value, item) for item in get_args(value_type))
    if origin in (list, tuple, Sequence):
        if not _is_non_string_sequence(value):
            return False
        args = get_args(value_type)
        item_type = args[0] if args else Any
        return all(_matches_param_type(item, item_type) for item in cast(Sequence[Any], value))
    if origin in (dict, Mapping):
        if not isinstance(value, Mapping):
            return False
        args = get_args(value_type)
        key_type, item_type = args if len(args) == 2 else (Any, Any)
        mapping = cast(Mapping[Any, Any], value)
        return all(
            _matches_param_type(key, key_type) and _matches_param_type(item, item_type) for key, item in mapping.items()
        )
    if value_type is Any:
        return True
    if value_type is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type is float:
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, value_type)


def _validate_param_data(
    value: Any,
    *,
    seen: set[int] | None = None,
    depth: int = 0,
) -> None:
    if depth > 16:
        raise ValueError("Search parameter values cannot exceed a depth of 16.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Filter and search parameter numbers must be finite.")
    if seen is None:
        seen = set()
    if isinstance(value, Mapping):
        mapping = cast(Mapping[Any, Any], value)
        if len(mapping) > 256:
            raise ValueError("Search parameter mappings cannot contain more than 256 entries.")
        if id(mapping) in seen:
            raise ValueError("Search parameter values cannot contain cycles.")
        seen.add(id(mapping))
        try:
            for item in mapping.values():
                _validate_param_data(item, seen=seen, depth=depth + 1)
        finally:
            seen.remove(id(mapping))
    elif _is_non_string_sequence(value):
        sequence = cast(Sequence[Any], value)
        if len(sequence) > 256:
            raise ValueError("Search parameter sequences cannot contain more than 256 values.")
        if id(sequence) in seen:
            raise ValueError("Search parameter values cannot contain cycles.")
        seen.add(id(sequence))
        try:
            for item in sequence:
                _validate_param_data(item, seen=seen, depth=depth + 1)
        finally:
            seen.remove(id(sequence))


def validate_param_value(param: Param, value: Any) -> Any:
    """Validate one parameter value with native type and constraint checks."""
    _validate_param_data(value)
    if not _matches_param_type(value, param.value_type):
        raise TypeError(f"Search parameter '{param.name}' does not match {param.value_type}.")
    if isinstance(value, int | float) and not isinstance(value, bool):
        if param.minimum is not None and value < param.minimum:
            raise ValueError(f"Search parameter '{param.name}' must be at least {param.minimum}.")
        if param.maximum is not None and value > param.maximum:
            raise ValueError(f"Search parameter '{param.name}' must be at most {param.maximum}.")
    if isinstance(value, str | Sequence | Mapping):
        sized_value = cast(str | Sequence[Any] | Mapping[Any, Any], value)
        if param.min_length is not None and len(sized_value) < param.min_length:
            raise ValueError(f"Search parameter '{param.name}' is shorter than {param.min_length}.")
        if param.max_length is not None and len(sized_value) > param.max_length:
            raise ValueError(f"Search parameter '{param.name}' is longer than {param.max_length}.")
    if param.pattern is not None and isinstance(value, str) and re.fullmatch(param.pattern, value) is None:
        raise ValueError(f"Search parameter '{param.name}' does not match the required pattern.")
    return cast(Any, value)


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
@dataclass(frozen=True, slots=True, init=False)
class Filter:
    """Describe one data-only vector store filter."""

    field_name: str
    operator: FilterOperator
    value: Any

    def __init__(self, field_name: str, operator: FilterOperator, value: Any = None) -> None:
        """Initialize a filter.

        Args:
            field_name: The logical model field, optionally followed by a provider-supported path.
            operator: A standard operator or a namespaced provider operator.
            value: The structured value consumed by the operator.

        Raises:
            TypeError: If the field name or operator is not a string.
            ValueError: If the field name or operator is invalid, an operator that takes no value receives one,
                an operator that requires a value receives ``None``, ``between`` does not receive two boundaries,
                or a ``Param`` is nested inside a larger value instead of being the complete value.
        """
        if not isinstance(field_name, str):
            raise TypeError("Filter field_name must be a string.")
        if not isinstance(operator, str):
            raise TypeError("Filter operator must be a string.")
        _validate_name(field_name, kind="Filter field name", allow_path=True)
        if operator not in _STANDARD_FILTER_OPERATORS and not _PROVIDER_OPERATOR_PATTERN.fullmatch(operator):
            raise ValueError(
                f"Unknown filter operator '{operator}'. Provider-specific operators must use a namespaced name."
            )
        object.__setattr__(self, "field_name", field_name)
        object.__setattr__(self, "operator", operator)
        object.__setattr__(self, "value", value)
        _validate_filter_value_shape(self, allow_params=True)


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
@dataclass(frozen=True, slots=True, init=False)
class FilterGroup:
    """Combine vector store filters with explicit boolean semantics."""

    operator: FilterGroupOperator
    filters: tuple[Filter | FilterGroup, ...]

    def __init__(self, operator: FilterGroupOperator, filters: Sequence[Filter | FilterGroup]) -> None:
        """Initialize a filter group.

        Args:
            operator: ``"and"``, ``"or"``, or unary ``"not"``.
            filters: The filters combined by the operator.

        Raises:
            TypeError: If the operator or filters have unsupported types.
            ValueError: If the operator or number of filters is invalid.
        """
        if not isinstance(operator, str):
            raise TypeError("Filter group operator must be a string.")
        if operator not in _GROUP_OPERATORS:
            raise ValueError(f"Unknown filter group operator '{operator}'.")
        if not _is_non_string_sequence(filters):
            raise TypeError("FilterGroup filters must be a sequence.")
        resolved_filters = tuple(filters)
        if not resolved_filters:
            raise ValueError("FilterGroup requires at least one filter.")
        if operator == "not" and len(resolved_filters) != 1:
            raise ValueError("A 'not' FilterGroup requires exactly one filter.")
        if any(not isinstance(item, Filter | FilterGroup) for item in resolved_filters):
            raise TypeError("FilterGroup entries must be Filter or FilterGroup instances.")
        object.__setattr__(self, "operator", operator)
        object.__setattr__(self, "filters", resolved_filters)


FilterExpression: TypeAlias = Filter | FilterGroup


def _value_contains_param(value: Any, *, seen: set[int] | None = None) -> bool:
    if isinstance(value, Param):
        return True
    if isinstance(value, Filter):
        return _value_contains_param(value.value, seen=seen)
    if isinstance(value, FilterGroup):
        return any(_value_contains_param(item, seen=seen) for item in value.filters)
    if seen is None:
        seen = set()
    if isinstance(value, Mapping):
        mapping = cast(Mapping[Any, Any], value)
        if id(mapping) in seen:
            raise ValueError("Filter values cannot contain cycles.")
        seen.add(id(mapping))
        try:
            return any(_value_contains_param(item, seen=seen) for item in mapping.values())
        finally:
            seen.remove(id(mapping))
    if _is_non_string_sequence(value):
        sequence = cast(Sequence[Any], value)
        if id(sequence) in seen:
            raise ValueError("Filter values cannot contain cycles.")
        seen.add(id(sequence))
        try:
            return any(_value_contains_param(item, seen=seen) for item in sequence)
        finally:
            seen.remove(id(sequence))
    return False


def _validate_filter_value_shape(filter_: Filter, *, allow_params: bool) -> None:
    value = filter_.value
    has_param = _value_contains_param(value)
    if has_param and not isinstance(value, Param):
        raise ValueError("Param must be the entire Filter value, not nested inside a collection or mapping.")
    if has_param and not allow_params:
        raise ValueError("Param references must be resolved before searching.")
    if filter_.operator not in _STANDARD_FILTER_OPERATORS:
        return
    if filter_.operator in _NO_VALUE_OPERATORS:
        if value is not None:
            raise ValueError(f"Filter operator '{filter_.operator}' does not accept a value.")
        return
    if value is None:
        raise ValueError(f"Filter operator '{filter_.operator}' requires a value.")
    if filter_.operator not in _SEQUENCE_VALUE_OPERATORS or has_param:
        return
    if not _is_non_string_sequence(value):
        raise TypeError(f"Filter operator '{filter_.operator}' requires a sequence value.")
    if filter_.operator == "between" and len(cast(Sequence[Any], value)) != 2:
        raise ValueError("'between' requires exactly two boundary values.")


def iter_filter_params(value: Any) -> tuple[Param, ...]:
    if isinstance(value, Param):
        return (value,)
    if isinstance(value, Filter):
        filter_value: Any = value.value
        return (filter_value,) if isinstance(filter_value, Param) else ()
    if isinstance(value, FilterGroup):
        return tuple(param for item in value.filters for param in iter_filter_params(item))
    return ()


def _resolve_param_value(
    value: Any,
    arguments: Mapping[str, Any],
) -> Any:
    if isinstance(value, Param):
        if value.name in arguments:
            return arguments[value.name]
        if value.has_default:
            return value.default
        if value.required:
            raise TypeError(f"Missing required search parameter '{value.name}'.")
        return _OMIT_FILTER
    return value


def resolve_filter_params(
    filter_: FilterExpression,
    arguments: Mapping[str, Any],
) -> FilterExpression | None:
    if isinstance(filter_, Filter):
        value = _resolve_param_value(filter_.value, arguments)
        if value is _OMIT_FILTER:
            return None
        return Filter(filter_.field_name, filter_.operator, value)
    resolved_filters = tuple(
        resolved for item in filter_.filters if (resolved := resolve_filter_params(item, arguments)) is not None
    )
    if not resolved_filters:
        return None
    if filter_.operator == "not" and len(resolved_filters) != 1:
        return None
    return FilterGroup(filter_.operator, resolved_filters)


@dataclass(slots=True)
class _FilterValidator:
    field_names: Collection[str]
    allow_params: bool
    max_depth: int
    max_nodes: int
    node_count: int = 0

    def validate_value(self, value: Any, *, depth: int, seen: set[int]) -> None:
        if depth > self.max_depth:
            raise ValueError(f"Filter values cannot exceed a depth of {self.max_depth}.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Filter numbers must be finite.")
        if isinstance(value, Param):
            raise ValueError("Param must be the entire Filter value, not nested inside a collection or mapping.")
        if isinstance(value, Filter | FilterGroup):
            self.validate_expression(value, depth=depth, relative_fields=True)
            return
        if isinstance(value, Mapping):
            mapping = cast(Mapping[Any, Any], value)
            if id(mapping) in seen:
                raise ValueError("Filter values cannot contain cycles.")
            seen.add(id(mapping))
            try:
                for key, item in mapping.items():
                    if not isinstance(key, str):
                        raise TypeError("Filter mapping keys must be strings.")
                    self.count_node()
                    self.validate_value(item, depth=depth + 1, seen=seen)
            finally:
                seen.remove(id(mapping))
            return
        if _is_non_string_sequence(value):
            sequence = cast(Sequence[Any], value)
            if id(sequence) in seen:
                raise ValueError("Filter values cannot contain cycles.")
            seen.add(id(sequence))
            try:
                for item in sequence:
                    self.count_node()
                    self.validate_value(item, depth=depth + 1, seen=seen)
            finally:
                seen.remove(id(sequence))

    def validate_expression(
        self,
        expression: FilterExpression,
        *,
        depth: int,
        relative_fields: bool,
    ) -> None:
        if depth > self.max_depth:
            raise ValueError(f"Filters cannot exceed a depth of {self.max_depth}.")
        self.count_node()
        if isinstance(expression, Filter):
            if not relative_fields and expression.field_name.split(".", maxsplit=1)[0] not in self.field_names:
                raise ValueError(f"Filter field '{expression.field_name}' is not part of the vector store definition.")
            _validate_filter_value_shape(expression, allow_params=self.allow_params)
            if not isinstance(expression.value, Param):
                self.validate_value(expression.value, depth=depth + 1, seen=set())
            return
        if not isinstance(expression, FilterGroup):
            raise TypeError("filter must be a Filter or FilterGroup.")
        for item in expression.filters:
            self.validate_expression(item, depth=depth + 1, relative_fields=relative_fields)

    def count_node(self) -> None:
        self.node_count += 1
        if self.node_count > self.max_nodes:
            raise ValueError(f"Filters cannot contain more than {self.max_nodes} nodes.")


def validate_filter(
    filter_: FilterExpression,
    *,
    field_names: Collection[str],
    allow_params: bool = False,
    max_depth: int = 8,
    max_nodes: int = 64,
) -> None:
    _FilterValidator(
        field_names=field_names,
        allow_params=allow_params,
        max_depth=max_depth,
        max_nodes=max_nodes,
    ).validate_expression(filter_, depth=1, relative_fields=False)
