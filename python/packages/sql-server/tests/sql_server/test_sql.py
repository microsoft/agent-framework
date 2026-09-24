# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from agent_framework import Filter, FilterGroup, VectorStoreCollectionDefinition, VectorStoreField
from agent_framework.exceptions import IntegrationInvalidResponseException

from agent_framework_sql_server._sql import (
    MAX_PARAMETERS,
    _column_type,
    _FilterCompiler,
    _metric_for,
    _parse_value,
    _prepare_value,
    _quote_identifier,
)
from agent_framework_sql_server._vector_store import _check_parameter_count


@pytest.fixture
def definition() -> VectorStoreCollectionDefinition:
    return VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str", storage_name="record]id"),
            VectorStoreField("data", name="text", type_="str", storage_name="body [text]"),
            VectorStoreField("data", name="count", type_="int"),
            VectorStoreField("data", name="ratio", type_="float"),
            VectorStoreField("data", name="flag", type_="bool"),
            VectorStoreField("data", name="tags", type_="list"),
            VectorStoreField("vector", name="embedding", type_="float32", dimensions=3),
        ],
        collection_name="documents",
    )


@pytest.mark.parametrize("name", ["", "no\0identifier", "a" * 129, "\U0001f680" * 65])
def test_identifier_rejects_invalid_or_truncated_names(name):
    with pytest.raises(ValueError):
        _quote_identifier(name)


def test_identifier_quotes_each_segment_including_embedded_brackets():
    assert _quote_identifier("s]; DROP TABLE dbo.users;--") == "[s]]; DROP TABLE dbo.users;--]"
    assert _quote_identifier("dbo.documents") == "[dbo.documents]"
    assert _quote_identifier("it's") == "[it's]"


def test_vector_uses_native_type_and_json_values():
    field = VectorStoreField("vector", name="embedding", type_="float32", dimensions=3)
    assert _column_type(field) == "VECTOR(3)"
    assert _prepare_value(field, [1, 0.25, -0.5]) == "[1.0,0.25,-0.5]"
    assert _parse_value(field, "[1.0,0.25,-0.5]") == [1.0, 0.25, -0.5]
    for invalid in ([1, True, 2], [1, float("nan"), 2], [1, 2], b"vector", [1e40, 0, 0]):
        with pytest.raises((TypeError, ValueError)):
            _prepare_value(field, invalid)
    for invalid_json in ('"not a vector"', "[1,2]", "[1,true,3]", "[1e99,2,3]", b"[1,2,3]"):
        with pytest.raises(IntegrationInvalidResponseException):
            _parse_value(field, invalid_json)


def test_vector_types_metrics_and_dimensions_are_restricted():
    for dimensions in (0, 1999):
        with pytest.raises(ValueError):
            _column_type(VectorStoreField("vector", name="v", dimensions=dimensions))
    with pytest.raises(NotImplementedError):
        _column_type(VectorStoreField("vector", name="v", type_="float16", dimensions=3))
    assert _metric_for(VectorStoreField("vector", name="v", dimensions=3, distance_function="dot_prod")) == (
        "dot",
        "negative",
    )
    with pytest.raises(NotImplementedError):
        _metric_for(VectorStoreField("vector", name="v", dimensions=3, distance_function="manhattan"))


def test_typed_values_and_json_do_not_coerce_invalid_data():
    string_key = VectorStoreField("key", name="id", type_="str")
    with pytest.raises(ValueError, match="end in a space"):
        _prepare_value(string_key, "alias ")
    assert _prepare_value(VectorStoreField("data", name="enabled", type_="bool"), False) is False
    with pytest.raises(TypeError):
        _prepare_value(VectorStoreField("data", name="enabled", type_="bool"), 0)
    with pytest.raises(TypeError):
        _prepare_value(VectorStoreField("data", name="number", type_="int"), True)
    with pytest.raises(ValueError):
        _prepare_value(VectorStoreField("data", name="number", type_="int"), 2**63)
    with pytest.raises(ValueError):
        _prepare_value(VectorStoreField("data", name="when", type_="datetime"), "2026-01-01T00:00:00")
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    datetime_field = VectorStoreField("data", name="when", type_="datetime")
    assert _column_type(datetime_field) == "DATETIME2(7)"
    assert _prepare_value(datetime_field, when.astimezone(timezone(timedelta(hours=2)))) == when.replace(tzinfo=None)
    assert _parse_value(datetime_field, when.replace(tzinfo=None)) == when
    uid = UUID(int=1)
    assert _prepare_value(VectorStoreField("key", name="id", type_="UUID"), str(uid)) == str(uid)
    assert _parse_value(VectorStoreField("key", name="id", type_="UUID"), str(uid)) == uid
    tags = VectorStoreField("data", name="tags", type_="list")
    assert _parse_value(tags, _prepare_value(tags, [1, True, None])) == [1, True, None]
    with pytest.raises(TypeError):
        _prepare_value(tags, [("nested",)])
    with pytest.raises(TypeError):
        _prepare_value(VectorStoreField("data", name="meta", type_="dict"), {1: "bad"})


def test_filter_values_bound_and_sql_server_wildcards_escaped(definition):
    injection = "'; DROP TABLE [dbo].[users]; --%_[abc]^!"
    condition, params = _FilterCompiler(definition, alias="t.").compile(Filter("text", "contains_text", injection))
    assert injection not in condition
    assert "t.[body [text]]]" in condition and "ESCAPE '!'" in condition
    assert params == ["%'; DROP TABLE [[]dbo].[[]users]; --!%!_[[]abc]^!!%"]


@pytest.mark.parametrize("operator", ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "between"])
def test_scalar_filters_bind_values_in_order(definition, operator):
    value = [1, 2] if operator in ("in", "not_in", "between") else 3
    condition, params = _FilterCompiler(definition).compile(Filter("count", operator, value))
    assert condition.count("?") == len(params) == (2 if isinstance(value, list) else 1)
    assert params == (value if isinstance(value, list) else [value])


def test_filter_groups_and_nullable_membership_are_two_valued(definition):
    expression = FilterGroup(
        "not",
        [FilterGroup("and", [Filter("id", "ne", "a"), Filter("count", "not_in", [1, None])])],
    )
    condition, params = _FilterCompiler(definition).compile(expression)
    assert "NOT" in condition and "IS NOT NULL AND" in condition and "IS NULL" in condition
    assert params == ["a", 1]
    assert "CONVERT(VARBINARY(MAX)" in condition
    assert _FilterCompiler(definition).compile(Filter("count", "in", []))[0].endswith("(1 = 0))")
    assert _FilterCompiler(definition).compile(Filter("count", "not_in", []))[0].endswith("(NOT (1 = 0)))")


@pytest.mark.parametrize("name,value", [("flag", 1), ("count", True), ("count", "1")])
def test_equality_does_not_coerce_mismatched_types(definition, name, value):
    condition, params = _FilterCompiler(definition).compile(Filter(name, "eq", value))
    assert condition == "1 = 0" and params == []
    condition, params = _FilterCompiler(definition).compile(Filter(name, "ne", value))
    assert condition == "(NOT (1 = 0))" and params == []


@pytest.mark.parametrize("operator", ["eq", "ne", "gt", "gte", "lt", "lte"])
def test_float_filters_accept_integral_values_outside_bigint_range(definition, operator):
    _, params = _FilterCompiler(definition).compile(Filter("ratio", operator, 10**20))
    assert params == [1e20]


@pytest.mark.parametrize("operator", ["in", "not_in", "between"])
def test_float_multi_value_filters_accept_integral_values_outside_bigint_range(definition, operator):
    _, params = _FilterCompiler(definition).compile(Filter("ratio", operator, [10**20, 10**21]))
    assert params == [1e20, 1e21]


@pytest.mark.parametrize("operator", ["eq", "gt"])
def test_integer_filters_reject_values_outside_bigint_range(definition, operator):
    with pytest.raises(ValueError, match="bigint"):
        _FilterCompiler(definition).compile(Filter("count", operator, 10**20))


@pytest.mark.parametrize(("field", "error"), [("count", "range"), ("ratio", "finite")])
@pytest.mark.parametrize("operator", ["eq", "gt"])
def test_out_of_range_numeric_filter_rejected(definition, field, error, operator):
    with pytest.raises(ValueError, match=error):
        _FilterCompiler(definition).compile(Filter(field, operator, 10**1000))


@pytest.mark.parametrize(
    "expression,error",
    [
        (Filter("text.subfield", "eq", "a"), NotImplementedError),
        (Filter("unknown", "eq", 1), ValueError),
        (Filter("embedding", "is_null"), NotImplementedError),
        (Filter("tags", "contains", 1), NotImplementedError),
        (Filter("text", "gt", "a"), NotImplementedError),
        (Filter("text", "contains_text", "\0"), ValueError),
        (Filter("flag", "between", [False, True]), NotImplementedError),
        (Filter("text", "sql.raw", "'; DROP TABLE x;--"), NotImplementedError),
    ],
)
def test_unsupported_filters_fail_explicitly(definition, expression, error):
    with pytest.raises(error):
        _FilterCompiler(definition).compile(expression)


def test_query_parameter_budget_rejects_oversized_statements():
    with pytest.raises(ValueError, match=str(MAX_PARAMETERS)):
        _check_parameter_count([None] * (MAX_PARAMETERS + 1))
