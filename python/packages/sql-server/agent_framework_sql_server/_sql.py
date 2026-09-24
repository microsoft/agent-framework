# Copyright (c) Microsoft. All rights reserved.

"""SQL Server identifiers, values, and portable filter translation."""

# pyright: reportUnusedFunction=false, reportUnusedClass=false
# Package-private helpers are consumed by the sibling vector-store module.

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any, cast
from uuid import UUID

from agent_framework import FilterGroup, VectorStoreCollectionDefinition, VectorStoreField
from agent_framework._vector_filters import FilterExpression
from agent_framework.exceptions import IntegrationInvalidResponseException

MAX_PARAMETERS = 2000  # SQL Server's limit is 2100; leave room for paging and search arguments.
_FLOAT32_MAX = 3.4028234663852886e38
_COLLATION = "Latin1_General_100_BIN2"
_ORDER_OPERATORS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
_METRICS = {
    "DEFAULT": ("cosine", "distance"),
    "cosine_distance": ("cosine", "distance"),
    "cosine_similarity": ("cosine", "similarity"),
    "euclidean_distance": ("euclidean", "distance"),
    "dot_prod": ("dot", "negative"),
    "negative_dot_prod": ("dot", "distance"),
}


def _quote_identifier(name: str) -> str:
    """Quote one SQL identifier; data values must be passed as bound parameters."""
    if not isinstance(name, str) or not name or "\0" in name or len(name.encode("utf-16-le")) // 2 > 128:
        raise ValueError("SQL Server identifiers must contain 1-128 UTF-16 code units and no NUL.")
    return f"[{name.replace(']', ']]')}]"


def _metric_for(field: VectorStoreField) -> tuple[str, str]:
    try:
        return _METRICS[field.distance_function or "DEFAULT"]
    except KeyError:
        raise NotImplementedError(f"Unsupported SQL Server distance function '{field.distance_function}'.") from None


def _column_type(field: VectorStoreField) -> str:
    if field.field_type == "vector":
        dimensions = field.dimensions
        if type(dimensions) is not int or not 1 <= dimensions <= 1998:
            raise ValueError("SQL Server vector dimensions must be an integer between 1 and 1998.")
        if field.type_ not in (None, "float", "float32"):
            raise NotImplementedError("SQL Server VECTOR columns support float32 vectors only.")
        return f"VECTOR({dimensions})"
    types = {
        "int": "BIGINT",
        "float": "FLOAT(53)",
        "bool": "BIT",
        "UUID": "UNIQUEIDENTIFIER",
        "bytes": "VARBINARY(MAX)",
        "date": "DATE",
        "datetime": "DATETIME2(7)",
        "list": "NVARCHAR(MAX)",
        "dict": "NVARCHAR(MAX)",
    }
    if field.type_ == "str":
        width = "450" if field.field_type == "key" or field.is_indexed else "MAX"
        return f"NVARCHAR({width}) COLLATE {_COLLATION}"
    if field.type_ not in types:
        raise NotImplementedError(f"Field '{field.name}' needs a supported explicit type; got '{field.type_}'.")
    return types[field.type_]


def _validate_json(value: Any) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON values must be finite.")
        return
    if isinstance(value, list):
        for item in cast(list[Any], value):
            _validate_json(item)
        return
    if isinstance(value, dict):
        for key, item in cast(dict[Any, Any], value).items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings.")
            _validate_json(item)
        return
    raise TypeError("JSON fields support only JSON scalars, lists, and string-keyed dictionaries.")


def _prepare_vector(field: VectorStoreField, value: Any) -> str:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"Vector field '{field.name}' requires a dense numeric sequence.")
    vector = cast(Sequence[float | int], value)
    if len(vector) != field.dimensions:
        raise ValueError(f"Vector field '{field.name}' requires {field.dimensions} dimensions.")
    components: list[float] = []
    for element in vector:
        if type(element) not in (float, int):
            raise TypeError(f"Vector field '{field.name}' requires numeric elements, not booleans or strings.")
        try:
            component = float(element)
        except OverflowError as exc:
            raise ValueError(f"Vector field '{field.name}' has an element outside the float32 range.") from exc
        if not math.isfinite(component) or abs(component) > _FLOAT32_MAX:
            raise ValueError(f"Vector field '{field.name}' requires finite float32 elements.")
        components.append(component)
    return json.dumps(components, separators=(",", ":"), allow_nan=False)


def _prepare_value(field: VectorStoreField, value: Any) -> Any:
    if value is None:
        return None
    if field.field_type == "vector":
        return _prepare_vector(field, value)
    kind = field.type_
    if kind == "UUID" and isinstance(value, (str, UUID)):
        return str(UUID(str(value)))
    if kind == "int" and type(value) is int:
        if not -(2**63) <= value < 2**63:
            raise ValueError(f"Field '{field.name}' exceeds the SQL Server bigint range.")
        return value
    if kind == "float" and type(value) in (float, int):
        try:
            number = float(value)
        except OverflowError as exc:
            raise ValueError(f"Field '{field.name}' requires a finite number.") from exc
        if not math.isfinite(number):
            raise ValueError(f"Field '{field.name}' requires a finite number.")
        return number
    if kind == "bool" and type(value) is bool:
        return value
    if kind == "str" and isinstance(value, str):
        if (field.field_type == "key" or field.is_indexed) and len(value.encode("utf-16-le")) // 2 > 450:
            raise ValueError(f"Field '{field.name}' exceeds the indexed NVARCHAR(450) limit.")
        if field.field_type == "key" and value.endswith(" "):
            raise ValueError(
                "SQL Server string keys cannot end in a space; SQL Server ignores trailing spaces in keys."
            )
        return value
    if kind == "bytes" and isinstance(value, bytes):
        return value
    if kind == "date" and (type(value) is date or isinstance(value, str)):
        return date.fromisoformat(value) if isinstance(value, str) else value
    if kind == "datetime" and isinstance(value, (datetime, str)):
        resolved = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if resolved.tzinfo is None or resolved.utcoffset() is None:
            raise ValueError(f"Datetime field '{field.name}' requires a timezone.")
        return resolved.astimezone(timezone.utc).replace(tzinfo=None)
    if (kind == "list" and isinstance(value, list)) or (kind == "dict" and isinstance(value, dict)):
        _validate_json(value)
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    raise TypeError(f"Field '{field.name}' requires a value of type '{kind}'.")


def _parse_value(field: VectorStoreField, value: Any) -> Any:
    if value is None:
        return None
    kind = field.type_
    if field.field_type == "vector" or kind in ("list", "dict"):
        if not isinstance(value, str):
            raise IntegrationInvalidResponseException(f"SQL Server returned a non-JSON value for '{field.name}'.")
        try:
            parsed: Any = json.loads(value)
        except json.JSONDecodeError as exc:
            raise IntegrationInvalidResponseException(f"SQL Server returned invalid JSON for '{field.name}'.") from exc
        if field.field_type == "vector":
            if not isinstance(parsed, list):
                raise IntegrationInvalidResponseException(f"SQL Server returned an invalid vector for '{field.name}'.")
            vector_values = cast(list[Any], parsed)
            if len(vector_values) != field.dimensions:
                raise IntegrationInvalidResponseException(f"SQL Server returned an invalid vector for '{field.name}'.")
            components: list[float] = []
            for item in vector_values:
                if type(item) not in (int, float):
                    raise IntegrationInvalidResponseException(
                        f"SQL Server returned invalid vector elements for '{field.name}'."
                    )
                try:
                    number = float(item)
                except OverflowError as exc:
                    raise IntegrationInvalidResponseException(
                        f"SQL Server returned invalid vector elements for '{field.name}'."
                    ) from exc
                if not math.isfinite(number) or abs(number) > _FLOAT32_MAX:
                    raise IntegrationInvalidResponseException(
                        f"SQL Server returned invalid vector elements for '{field.name}'."
                    )
                components.append(number)
            return components
        if not isinstance(parsed, list if kind == "list" else dict):
            raise IntegrationInvalidResponseException(f"SQL Server returned the wrong JSON type for '{field.name}'.")
        return cast(list[Any] | dict[str, Any], parsed)
    if kind == "UUID":
        try:
            return UUID(str(value))
        except ValueError as exc:
            raise IntegrationInvalidResponseException(
                f"SQL Server returned an invalid UUID for '{field.name}'."
            ) from exc
    if kind == "datetime":
        if not isinstance(value, datetime):
            raise IntegrationInvalidResponseException(f"SQL Server returned an invalid datetime for '{field.name}'.")
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if kind == "bool" and type(value) is int and value in (0, 1):
        return bool(value)
    return value


def _filter_field(definition: VectorStoreCollectionDefinition, name: str) -> VectorStoreField:
    if "." in name:
        raise NotImplementedError("SQL Server filters and ordering do not support nested field paths.")
    field = definition.try_get_field(name)
    if field is None:
        raise ValueError(f"Unknown SQL Server field '{name}'.")
    if field.field_type == "vector":
        raise NotImplementedError("Filtering and ordering vector columns is not supported.")
    return field


def _numeric_filter_value(value: int | float) -> int | float:
    try:
        if not math.isfinite(value):
            raise ValueError("Numeric filter values must be finite.")
    except OverflowError as exc:
        raise ValueError("Numeric filter values must fit in the SQL Server numeric range.") from exc
    if type(value) is int and not -(2**63) <= value < 2**63:
        raise ValueError("Integer filter values must fit in the SQL Server bigint range.")
    return value


def _prepare_numeric_filter_value(field: VectorStoreField, value: int | float) -> int | float:
    return _numeric_filter_value(value) if field.type_ == "int" else _prepare_value(field, value)


class _FilterCompiler:
    """Compile bounded data-only filter expressions into parameterized two-valued T-SQL."""

    def __init__(self, definition: VectorStoreCollectionDefinition, *, alias: str = "") -> None:
        self.definition = definition
        self.alias = alias
        self.parameters: list[Any] = []

    def compile(self, expression: FilterExpression) -> tuple[str, list[Any]]:
        """Compile one filter with its parameters in placeholder order."""
        self.parameters = []
        return self._condition(expression), self.parameters

    def _bind(self, value: Any) -> str:
        if len(self.parameters) >= MAX_PARAMETERS:
            raise ValueError(f"SQL Server queries support at most {MAX_PARAMETERS} bound parameters.")
        self.parameters.append(value)
        return "?"

    def _equality(self, field: VectorStoreField, column: str, value: Any) -> str:
        if value is None:
            return f"{column} IS NULL"
        kind = field.type_
        if kind in ("list", "dict"):
            raise NotImplementedError("Equality filtering JSON fields is not supported.")
        if kind == "bool" and type(value) is not bool:
            return "1 = 0"
        if kind != "bool" and isinstance(value, bool):
            return "1 = 0"
        if kind in ("int", "float") and type(value) in (int, float):
            adapted = _prepare_numeric_filter_value(field, value)
        elif (
            (kind == "str" and isinstance(value, str))
            or (kind == "bytes" and isinstance(value, bytes))
            or (kind == "UUID" and isinstance(value, (UUID, str)))
            or (kind == "date" and (type(value) is date or isinstance(value, str)))
            or (kind == "datetime" and isinstance(value, (datetime, str)))
            or (kind == "bool" and type(value) is bool)
        ):
            adapted = _prepare_value(field, value)
        else:
            return "1 = 0"
        if kind == "str":
            # SQL Server pads trailing spaces even with binary collations; compare bytes instead.
            return (
                f"({column} IS NOT NULL AND CONVERT(VARBINARY(MAX), {column}) = "
                f"CONVERT(VARBINARY(MAX), CONVERT(NVARCHAR(MAX), {self._bind(adapted)})))"
            )
        return f"({column} IS NOT NULL AND {column} = {self._bind(adapted)})"

    def _condition(self, expression: FilterExpression) -> str:
        if isinstance(expression, FilterGroup):
            conditions = [self._condition(child) for child in expression.filters]
            if expression.operator == "not":
                return f"(NOT ({conditions[0]}))"
            joiner = " AND " if expression.operator == "and" else " OR "
            return f"({joiner.join(conditions)})"
        field = _filter_field(self.definition, expression.field_name)
        column = f"{self.alias}{_quote_identifier(field.storage_name or field.name)}"
        op, value = expression.operator, expression.value
        if op == "exists":
            return "1 = 1"  # SQL columns exist even when their values are NULL.
        if op == "is_null":
            return f"{column} IS NULL"
        if op == "is_not_null":
            return f"{column} IS NOT NULL"
        if op in ("eq", "ne"):
            equality = self._equality(field, column, value)
            return equality if op == "eq" else f"(NOT ({equality}))"
        if op in ("in", "not_in"):
            choices = " OR ".join(self._equality(field, column, item) for item in value) or "1 = 0"
            membership = f"({choices})" if op == "in" else f"(NOT ({choices}))"
            return f"({column} IS NOT NULL AND {membership})"
        if op in _ORDER_OPERATORS or op == "between":
            if field.type_ not in ("int", "float", "date", "datetime"):
                raise NotImplementedError(f"Ordered SQL Server filtering is not supported for '{field.type_}'.")
            values: Sequence[Any] = value if op == "between" else [value]
            if any(item is None or isinstance(item, bool) for item in values):
                raise TypeError("Ordered filter operands must be non-null scalars of the column's type.")
            adapted = [
                _prepare_numeric_filter_value(field, item)
                if field.type_ in ("int", "float") and type(item) in (int, float)
                else _prepare_value(field, item)
                for item in values
            ]
            comparison = (
                f"{column} BETWEEN {self._bind(adapted[0])} AND {self._bind(adapted[1])}"
                if op == "between"
                else f"{column} {_ORDER_OPERATORS[op]} {self._bind(adapted[0])}"
            )
            return f"({column} IS NOT NULL AND {comparison})"
        if op in ("contains_text", "starts_with", "ends_with"):
            if field.type_ != "str":
                raise TypeError("Text filtering requires a string column.")
            if not isinstance(value, str):
                raise TypeError("Text filtering requires a string operand.")
            if "\0" in value:
                raise ValueError("SQL Server LIKE does not support NUL characters.")
            escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_").replace("[", "[[]")
            pattern = ("%" if op != "starts_with" else "") + escaped + ("%" if op != "ends_with" else "")
            if len(pattern.encode("utf-16-le")) > 8000:
                raise ValueError("SQL Server LIKE patterns cannot exceed 8000 bytes.")
            return f"({column} IS NOT NULL AND {column} COLLATE {_COLLATION} LIKE {self._bind(pattern)} ESCAPE '!')"
        raise NotImplementedError(f"Unsupported SQL Server filter operator '{op}'.")
