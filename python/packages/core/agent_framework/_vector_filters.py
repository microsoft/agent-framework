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
- ``starts_with`` / ``ends_with`` / ``contains_text`` require string operands.

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
from decimal import Decimal
from itertools import islice
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
_TEXT_VALUE_OPERATORS: Final[frozenset[str]] = frozenset({"starts_with", "ends_with", "contains_text"})
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
_MAX_FILTER_DEPTH: Final[int] = 8
_MAX_FILTER_NODES: Final[int] = 64


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
    """Compare validated scalars, sequences, and mappings without equating booleans to numbers."""
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if _is_non_string_sequence(left) and _is_non_string_sequence(right):
        # Preserve native container semantics, such as lists not equaling tuples.
        return left == right and all(
            filter_values_equal(left_item, right_item)
            for left_item, right_item in zip(cast(Sequence[Any], left), cast(Sequence[Any], right), strict=True)
        )
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        left_mapping = cast(Mapping[str, Any], left)
        right_mapping = cast(Mapping[str, Any], right)
        return left_mapping == right_mapping and all(
            filter_values_equal(item, right_mapping[key]) for key, item in left_mapping.items()
        )
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
    omitted. Otherwise, the supplied value or declared default is substituted
    before the filter reaches the vector store. A missing required parameter
    raises an error.

    Set ``omit_if_none=True`` to remove the containing filter when the resolved
    value is ``None`` (JSON ``null``). This requires a nullable ``value_type``
    and an explicit ``default=None``, for example
    ``Param("text", str | None, default=None, omit_if_none=True)``. Both an
    absent argument and an explicit ``None`` then omit the filter. Non-None
    values still undergo the declared type and constraint checks.

    Omission removes the entire leaf, not the field value and not a boolean
    ``True`` substitute. AND/OR groups evaluate their remaining children;
    empty groups, including NOT groups whose child was removed, are removed
    recursively. If the whole tree is removed, search receives no filter.
    Fixed filters are retained. See ``FilterGroup`` for composition examples.

    With ``omit_if_none=False`` (the default), ``None`` is an ordinary supplied
    value subject to type and operator validation, not an omission request.
    Null omission is only supported for filter parameters, not paging options.

    Defaults and supplied mutable values are copied for each filter invocation.
    Parameter data is bounded before copying or type validation.
    """

    name: str
    value_type: Any
    required: bool
    _default: Any
    omit_if_none: bool
    description: str | None
    minimum: float | int | None
    maximum: float | int | None
    min_length: int | None
    max_length: int | None

    def __init__(
        self,
        name: str,
        value_type: Any,
        *,
        required: bool = False,
        default: Any = _PARAM_UNSET,
        omit_if_none: bool = False,
        description: str | None = None,
        minimum: float | int | None = None,
        maximum: float | int | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
    ) -> None:
        """Initialize a parameter reference.

        Args:
            name: The tool parameter name exposed to the model.
            value_type: The Python type used for schema generation and validation.
                Must accept ``None``, such as ``str | None``, when ``omit_if_none=True``.
            required: Whether the model must supply the parameter.
            default: The value used when an optional parameter is omitted.
                Must be explicitly set to ``None`` when ``omit_if_none=True``.
            omit_if_none: Whether a resolved ``None`` removes the containing filter.
                Requires a nullable type and ``default=None``; not supported for paging.
            description: The parameter description shown to the model.
            minimum: The inclusive minimum for numeric values.
            maximum: The inclusive maximum for numeric values.
            min_length: The minimum length for string, array, or object values.
            max_length: The maximum length for string, array, or object values.

        Raises:
            TypeError: If the annotation is unsupported or ``omit_if_none`` is not a boolean.
            ValueError: If the name or constraints are invalid, a required parameter declares a default,
                or ``omit_if_none=True`` is used without a nullable type and explicit ``default=None``.
        """
        _validate_name(name, kind="Parameter name", allow_path=False)
        if name == "query":
            raise ValueError("'query' is reserved by vector search tools.")
        if required and default is not _PARAM_UNSET:
            raise ValueError("A required parameter cannot declare a default.")
        if not isinstance(omit_if_none, bool):
            raise TypeError("Param omit_if_none must be a boolean.")
        if omit_if_none and default is not None:
            raise ValueError("Param omit_if_none=True requires an explicit default=None.")
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
        if default is not _PARAM_UNSET:
            _validate_param_data(default)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "value_type", value_type)
        object.__setattr__(self, "required", required)
        object.__setattr__(self, "_default", deepcopy(default))
        object.__setattr__(self, "omit_if_none", omit_if_none)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "min_length", min_length)
        object.__setattr__(self, "max_length", max_length)
        param_schema(self)

    @property
    def has_default(self) -> bool:
        """Return whether the parameter declares a default value."""
        return self._default is not _PARAM_UNSET

    @property
    def default(self) -> Any:
        """Return an independent copy of the default value."""
        return deepcopy(self._default)

    def __deepcopy__(self, memo: dict[int, Any]) -> Param:
        return self


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
        json_types: list[str] = []
        for value in values:
            json_type = _json_type(type(value))
            if json_type is None:
                raise TypeError("Param Literal values must be JSON-compatible scalar values.")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Param Literal numbers must be finite.")
            if json_type not in json_types:
                json_types.append(json_type)
        schema: dict[str, Any] = {"enum": values}
        if len(json_types) == 1:
            schema["type"] = json_types[0]
        else:
            schema["anyOf"] = [{"type": json_type} for json_type in json_types]
        return schema
    if origin in (Union, UnionType):
        return {"anyOf": [_schema_for_type(item) for item in get_args(value_type)]}
    if origin is tuple:
        args = get_args(value_type)
        if len(args) != 2 or args[1] is not Ellipsis:
            raise TypeError("Param tuple types must use the homogeneous tuple[T, ...] form.")
        item_type = args[0]
        return {"type": "array", "items": _schema_for_type(item_type)}
    if origin in (list, Sequence):
        args = get_args(value_type)
        item_type = args[0] if args else Any
        return {"type": "array", "items": _schema_for_type(item_type)}
    if origin in (dict, Mapping):
        args = get_args(value_type)
        key_annotation, value_annotation = args if len(args) == 2 else (Any, Any)
        if key_annotation is not str:
            raise TypeError("Param mapping keys must use the str type.")
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
    schema_types = _schema_types(schema)
    if param.omit_if_none and "null" not in schema_types:
        raise ValueError("Param omit_if_none=True requires a value type that accepts None.")
    non_null_schema_types = schema_types - {"null"}
    if (param.minimum is not None or param.maximum is not None) and (
        not non_null_schema_types or not non_null_schema_types <= {"integer", "number"}
    ):
        raise ValueError("Param numeric constraints require numeric value types.")
    if param.description is not None:
        schema["description"] = param.description
    if param.has_default:
        schema["default"] = param.default
    if param.minimum is not None:
        schema["minimum"] = param.minimum
    if param.maximum is not None:
        schema["maximum"] = param.maximum
    if (param.min_length is not None or param.max_length is not None) and len(non_null_schema_types) != 1:
        raise ValueError("Param length constraints require one string, array, or object type.")
    schema_type = next(iter(non_null_schema_types), None)
    if schema_type not in (None, "string", "array", "object") and (
        param.min_length is not None or param.max_length is not None
    ):
        raise ValueError("Param length constraints require a string, array, or object type.")
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
    if origin is tuple:
        if not _is_non_string_sequence(value):
            return False
        args = get_args(value_type)
        if len(args) != 2 or args[1] is not Ellipsis:
            return False
        return all(_matches_param_type(item, args[0]) for item in cast(Sequence[Any], value))
    if origin in (list, Sequence):
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


@dataclass(slots=True)
class _ParamDataValidator:
    max_depth: int = 16
    max_nodes: int = 256
    node_count: int = 0

    def validate(self, value: Any, *, seen: set[int] | None = None, depth: int = 0) -> None:
        self.node_count += 1
        if self.node_count > self.max_nodes:
            raise ValueError(f"Search parameter values cannot contain more than {self.max_nodes} nodes.")
        if depth > self.max_depth:
            raise ValueError(f"Search parameter values cannot exceed a depth of {self.max_depth}.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Filter and search parameter numbers must be finite.")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError("Filter and search parameter numbers must be finite.")
        if seen is None:
            seen = set()
        if isinstance(value, Mapping):
            mapping = cast(Mapping[Any, Any], value)
            if id(mapping) in seen:
                raise ValueError("Search parameter values cannot contain cycles.")
            seen.add(id(mapping))
            try:
                for item in mapping.values():
                    self.validate(item, seen=seen, depth=depth + 1)
            finally:
                seen.remove(id(mapping))
        elif _is_non_string_sequence(value):
            sequence = cast(Sequence[Any], value)
            if id(sequence) in seen:
                raise ValueError("Search parameter values cannot contain cycles.")
            seen.add(id(sequence))
            try:
                for item in sequence:
                    self.validate(item, seen=seen, depth=depth + 1)
            finally:
                seen.remove(id(sequence))


def _validate_param_data(value: Any) -> None:
    _ParamDataValidator().validate(value)


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
    return cast(Any, value)


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
@dataclass(slots=True, init=False)
class Filter:
    """Describe one data-only vector store filter.

    A ``Param`` must be the complete value of a leaf. In a search tool,
    ``Filter("description", "contains_text",
    Param("text", str | None, default=None, omit_if_none=True))`` is omitted
    when ``text`` is absent or explicitly ``None`` (JSON ``null``).
    ``omit_if_none=True`` requires both a nullable parameter type and an
    explicit ``default=None``. Non-None arguments use normal operator
    semantics; strings such as ``"*"`` are not special omission values.

    Omission removes this leaf from its group rather than making it match
    every record. Remaining AND/OR children still apply; a NOT group is
    removed if its child is removed. Empty groups are removed recursively,
    and removing the whole tree means search receives no filter.

    With ``omit_if_none=False`` (the default), a supplied ``None`` is validated
    as a value, not omitted. A literal ``Filter(..., value=None)`` does not
    opt into omission either; use ``is_null`` to test for a null field.

    Nested parameters are forbidden in collection members and mapping keys as
    well as mapping values. Structural depth/node limits apply during parameter
    inspection and before operation snapshots are copied; oversized inputs may
    therefore fail at construction as well as at operation time.
    """

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
            TypeError: If the field name or operator is not a string, or an operand has an invalid shape.
            ValueError: If the field name or operator is invalid, an operator that takes no value receives one,
                an operator that requires a value receives ``None``, ``between`` does not receive two boundaries,
                a ``Param`` is nested inside a larger value, or structural limits are exceeded.
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
        self.field_name = field_name
        self.operator = operator
        self.value = value
        _validate_filter_value_shape(self, allow_params=True)


@experimental(feature_id=ExperimentalFeature.VECTOR_STORES)
@dataclass(slots=True, init=False)
class FilterGroup:
    """Combine vector store filters with explicit boolean semantics.

    Search tools resolve parameters before evaluating the group. An absent
    optional parameter without a default removes its leaf. A parameter such
    as ``Param("text", str | None, default=None, omit_if_none=True)`` also
    removes its leaf for an explicit ``None`` (JSON ``null``). This opt-in
    requires a nullable type and an explicit ``default=None``.

    After omission, ``"and"`` requires all remaining children to match, and
    ``"or"`` requires any remaining child to match. For example, combining
    ``Filter("rating", "gte", 4)`` with an omitted text filter leaves only
    the rating condition in either group. The omitted leaf is not replaced
    with ``True``, which would make an OR group match every record.

    A ``"not"`` group negates its remaining child; if that child is removed,
    the NOT group is removed too. Any group left with no children is removed
    recursively. If the whole tree disappears, search receives no filter;
    other search options still apply. Fixed children are never omitted.

    With ``omit_if_none=False`` (the default), explicit ``None`` values retain
    normal type and operator validation rather than removing a child.
    """

    operator: FilterGroupOperator
    filters: tuple[Filter | FilterGroup, ...]

    def __init__(self, operator: FilterGroupOperator, filters: Sequence[Filter | FilterGroup]) -> None:
        """Initialize a filter group.

        Args:
            operator: ``"and"``, ``"or"``, or unary ``"not"``.
            filters: The filters combined by the operator.

        Raises:
            TypeError: If the operator or filters have unsupported types.
            ValueError: If the operator or number of filters is invalid, including structural limits.
        """
        if not isinstance(operator, str):
            raise TypeError("Filter group operator must be a string.")
        if operator not in _GROUP_OPERATORS:
            raise ValueError(f"Unknown filter group operator '{operator}'.")
        if not _is_non_string_sequence(filters):
            raise TypeError("FilterGroup filters must be a sequence.")
        resolved_filters = tuple(islice(filters, _MAX_FILTER_NODES))
        if len(resolved_filters) >= _MAX_FILTER_NODES:
            raise ValueError(f"Filters cannot contain more than {_MAX_FILTER_NODES} nodes.")
        if not resolved_filters:
            raise ValueError("FilterGroup requires at least one filter.")
        if operator == "not" and len(resolved_filters) != 1:
            raise ValueError("A 'not' FilterGroup requires exactly one filter.")
        if any(not isinstance(item, Filter | FilterGroup) for item in resolved_filters):
            raise TypeError("FilterGroup entries must be Filter or FilterGroup instances.")
        self.operator = operator
        self.filters = resolved_filters


FilterExpression: TypeAlias = Filter | FilterGroup


def _snapshot_filter(filter_: FilterExpression, *, active: set[int]) -> FilterExpression:
    if id(filter_) in active:
        raise ValueError("Filter expressions cannot contain cycles.")
    active.add(id(filter_))
    try:
        if isinstance(filter_, Filter):
            value = (
                _snapshot_filter(filter_.value, active=active)
                if isinstance(filter_.value, Filter | FilterGroup)
                else deepcopy(filter_.value)
            )
            return Filter(filter_.field_name, filter_.operator, value)
        if isinstance(filter_, FilterGroup):
            return FilterGroup(
                filter_.operator,
                tuple(_snapshot_filter(item, active=active) for item in filter_.filters),
            )
    finally:
        active.remove(id(filter_))
    raise TypeError("filter must be a Filter or FilterGroup.")


def snapshot_filter(filter_: FilterExpression) -> FilterExpression:
    """Bound and validate the filter structure before copying it for one operation."""
    validate_filter(filter_, allow_params=True)
    return _snapshot_filter(filter_, active=set())


def _value_contains_param(value: Any) -> bool:
    active: set[int] = set()
    node_count = 0

    def visit(value: Any, depth: int) -> bool:
        nonlocal node_count
        node_count += 1
        if node_count > _MAX_FILTER_NODES:
            raise ValueError(f"Filters cannot contain more than {_MAX_FILTER_NODES} nodes.")
        if depth > _MAX_FILTER_DEPTH:
            raise ValueError(f"Filter values cannot exceed a depth of {_MAX_FILTER_DEPTH}.")
        if isinstance(value, Param):
            return True
        if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Filter | FilterGroup | Collection):
            return False
        identity = id(cast(object, value))
        if identity in active:
            raise ValueError("Filter values cannot contain cycles.")
        active.add(identity)
        try:
            if isinstance(value, Filter):
                return visit(value.value, depth + 1)
            if isinstance(value, FilterGroup):
                return any(visit(item, depth + 1) for item in value.filters)
            if isinstance(value, Mapping):
                return any(
                    (not isinstance(key, str) and visit(key, depth + 1)) or visit(item, depth + 1)
                    for key, item in cast(Mapping[Any, Any], value).items()
                )
            return any(visit(item, depth + 1) for item in cast(Collection[Any], value))
        finally:
            active.remove(identity)

    return visit(value, 1)


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
    if filter_.operator in _TEXT_VALUE_OPERATORS and not has_param:
        require_filter_string(value)
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
            resolved = arguments[value.name]
        elif value.has_default:
            resolved = value.default
        elif value.required:
            raise TypeError(f"Missing required search parameter '{value.name}'.")
        else:
            return _OMIT_FILTER
        return _OMIT_FILTER if value.omit_if_none and resolved is None else deepcopy(resolved)
    return deepcopy(value)


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
    field_names: Collection[str] | None
    allow_params: bool
    max_depth: int
    max_nodes: int
    node_count: int = 0

    def validate_value(self, value: Any, *, depth: int, active: set[int]) -> None:
        if depth > self.max_depth:
            raise ValueError(f"Filter values cannot exceed a depth of {self.max_depth}.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Filter numbers must be finite.")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError("Filter numbers must be finite.")
        if isinstance(value, Param):
            raise ValueError("Param must be the entire Filter value, not nested inside a collection or mapping.")
        if isinstance(value, Filter | FilterGroup):
            self.validate_expression(value, depth=depth, relative_fields=True, active=active)
            return
        if isinstance(value, Mapping):
            mapping = cast(Mapping[Any, Any], value)
            if id(mapping) in active:
                raise ValueError("Filter values cannot contain cycles.")
            active.add(id(mapping))
            try:
                for key, item in mapping.items():
                    if not isinstance(key, str):
                        raise TypeError("Filter mapping keys must be strings.")
                    self.count_node()
                    self.validate_value(item, depth=depth + 1, active=active)
            finally:
                active.remove(id(mapping))
            return
        if isinstance(value, Collection) and not isinstance(value, (str, bytes, bytearray)):
            collection = cast(Collection[Any], value)
            if id(collection) in active:
                raise ValueError("Filter values cannot contain cycles.")
            active.add(id(collection))
            try:
                for item in collection:
                    self.count_node()
                    self.validate_value(item, depth=depth + 1, active=active)
            finally:
                active.remove(id(collection))

    def validate_expression(
        self,
        expression: FilterExpression,
        *,
        depth: int,
        relative_fields: bool,
        active: set[int],
    ) -> None:
        if depth > self.max_depth:
            raise ValueError(f"Filters cannot exceed a depth of {self.max_depth}.")
        if id(expression) in active:
            raise ValueError("Filter expressions cannot contain cycles.")
        active.add(id(expression))
        try:
            self.count_node()
            if isinstance(expression, Filter):
                if (
                    not relative_fields
                    and self.field_names is not None
                    and expression.field_name.split(".", maxsplit=1)[0] not in self.field_names
                ):
                    raise ValueError(
                        f"Filter field '{expression.field_name}' is not part of the vector store definition."
                    )
                if not isinstance(expression.value, Param):
                    self.validate_value(expression.value, depth=depth + 1, active=active)
                _validate_filter_value_shape(expression, allow_params=self.allow_params)
                return
            if not isinstance(expression, FilterGroup):
                raise TypeError("filter must be a Filter or FilterGroup.")
            for item in expression.filters:
                self.validate_expression(
                    item,
                    depth=depth + 1,
                    relative_fields=relative_fields,
                    active=active,
                )
        finally:
            active.remove(id(expression))

    def count_node(self) -> None:
        self.node_count += 1
        if self.node_count > self.max_nodes:
            raise ValueError(f"Filters cannot contain more than {self.max_nodes} nodes.")


def validate_filter(
    filter_: FilterExpression,
    *,
    field_names: Collection[str] | None = None,
    allow_params: bool = False,
    max_depth: int = _MAX_FILTER_DEPTH,
    max_nodes: int = _MAX_FILTER_NODES,
) -> None:
    _FilterValidator(
        field_names=field_names,
        allow_params=allow_params,
        max_depth=max_depth,
        max_nodes=max_nodes,
    ).validate_expression(filter_, depth=1, relative_fields=False, active=set())
