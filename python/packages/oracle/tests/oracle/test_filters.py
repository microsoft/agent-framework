# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from agent_framework import Filter, FilterGroup

from agent_framework_oracle._vector_store import _FilterCompiler, _quote_identifier


@pytest.mark.parametrize("name", ["", "a\0b", "a" * 129, "\u00e9" * 65])
def test_invalid_identifier_fails(name):
    with pytest.raises(ValueError):
        _quote_identifier(name)


def test_identifiers_quote_each_name_and_escape_double_quotes():
    assert _quote_identifier('t"; DROP TABLE users; --') == '"t""; DROP TABLE users; --"'
    assert _quote_identifier("SCHEMA.TABLE") == '"SCHEMA.TABLE"'
    assert _quote_identifier("\u00e9" * 64) == '"' + "\u00e9" * 64 + '"'


def test_text_patterns_escape_literals_and_bind_values(collection):
    value = "%_!'; DROP TABLE AF_DOCUMENTS; --"
    sql, binds = collection._prepare_filter(Filter("text", "contains_text", value))
    assert value not in sql and "DROP TABLE" not in sql
    assert '"body text" LIKE :f0 ESCAPE' in sql
    assert binds == {"f0": "%!%!_!!'; DROP TABLE AF!_DOCUMENTS; --%"}


def test_oracle_empty_string_is_rejected_instead_of_becoming_null(collection):
    with pytest.raises(ValueError, match="empty string"):
        collection._prepare_filter(Filter("text", "eq", ""))


@pytest.mark.parametrize(
    "operator,expected",
    [
        ("is_null", '"number" IS NULL'),
        ("is_not_null", '"number" IS NOT NULL'),
        ("exists", "1=1"),
    ],
)
def test_null_and_exists_predicates(collection, operator, expected):
    condition, binds = collection._prepare_filter(Filter("number", operator))
    assert expected in condition
    assert binds == {}


@pytest.mark.parametrize("value", [True, "1", [], {}])
def test_numeric_equality_does_not_coerce_invalid_values(collection, value):
    sql, binds = collection._prepare_filter(Filter("number", "eq", value))
    assert sql == "1=0" and binds == {}
    sql, binds = collection._prepare_filter(Filter("number", "ne", value))
    assert sql == "(NOT (1=0))" and binds == {}


@pytest.mark.parametrize(
    ("field", "value", "expected_bind"),
    [
        ("number", Decimal("2"), 2),
        ("number", Decimal("2.0"), 2),
        ("number", Decimal("9223372036854775807"), 2**63 - 1),
        ("number", Decimal("2.5"), None),
        ("number", Decimal("9223372036854775808"), None),
        ("text", Decimal("0.5"), 0.5),
        ("text", Decimal("0.1"), None),
        ("text", Decimal("1e1000"), None),
    ],
)
def test_decimal_equality_uses_exact_numeric_comparison(definition_factory, field, value, expected_bind):
    compiler = _FilterCompiler(definition_factory(data_type="float"))
    for operator in ("eq", "ne"):
        sql, binds = compiler.compile(Filter(field, operator, value))
        if expected_bind is None:
            assert sql == ("1=0" if operator == "eq" else "(NOT (1=0))")
            assert binds == {}
        else:
            assert f'"{field if field == "number" else "body text"}" = :f0' in sql
            assert binds == {"f0": expected_bind}


def test_decimal_membership_and_nonfinite_values(collection):
    sql, binds = collection._prepare_filter(Filter("number", "in", [Decimal("2"), Decimal("2.5")]))
    assert '"number" = :f0' in sql
    assert binds == {"f0": 2}
    sql, binds = collection._prepare_filter(Filter("number", "not_in", [Decimal("2.5")]))
    assert sql == '("number" IS NOT NULL AND (NOT ((1=0))))'
    assert binds == {}
    with pytest.raises(ValueError, match="finite"):
        collection._prepare_filter(Filter("number", "eq", Decimal("NaN")))


@pytest.mark.parametrize(
    ("operator", "value", "expected_sql"),
    [
        ("eq", "not-a-uuid", "1=0"),
        ("ne", "not-a-uuid", "(NOT (1=0))"),
        ("in", ["not-a-uuid"], '("doc""id" IS NOT NULL AND (1=0))'),
        ("not_in", ["not-a-uuid"], '("doc""id" IS NOT NULL AND (NOT ((1=0))))'),
    ],
)
def test_malformed_uuid_filter_is_non_equal(definition_factory, operator, value, expected_sql):
    compiler = _FilterCompiler(definition_factory(key_type="UUID"))
    sql, binds = compiler.compile(Filter("id", operator, value))
    assert sql == expected_sql
    assert binds == {}


def test_valid_uuid_filter_values_remain_bound(definition_factory):
    compiler = _FilterCompiler(definition_factory(key_type="UUID"))
    valid = UUID(int=2)
    sql, binds = compiler.compile(Filter("id", "in", ["malformed", valid]))
    assert '"doc""id" = :f0' in sql
    assert binds == {"f0": str(valid)}


def test_boolean_equality_does_not_coerce_numbers(collection):
    sql, binds = collection._prepare_filter(Filter("flag", "eq", True))
    assert '"flag" = :f0' in sql and binds == {"f0": 1}
    sql, binds = collection._prepare_filter(Filter("flag", "eq", 1))
    assert sql == "1=0" and binds == {}


@pytest.mark.parametrize(
    "operator,value,expected",
    [
        ("in", [], "1=0"),
        ("not_in", [], "(NOT (1=0))"),
        ("in", [True, 2, None], "IS NOT NULL"),
        ("not_in", [True, 2, None], "IS NOT NULL"),
    ],
)
def test_membership_has_portable_null_and_empty_semantics(collection, operator, value, expected):
    sql, binds = collection._prepare_filter(Filter("number", operator, value))
    assert expected in sql
    assert list(binds.values()) == ([2] if value else [])


def test_groups_preserve_parameter_order_and_do_not_leak_state(definition_factory):
    compiler = _FilterCompiler(definition_factory())
    sql, binds = compiler.compile(
        FilterGroup(
            "and",
            [
                Filter("id", "eq", "first"),
                FilterGroup("or", [Filter("number", "between", (2, 3)), Filter("text", "eq", "last")]),
            ],
        )
    )
    assert sql.index('"doc""id"') < sql.index('"number"') < sql.index('"body text"')
    assert binds == {"f0": "first", "f1": 2, "f2": 3, "f3": "last"}
    _, next_binds = compiler.compile(Filter("id", "eq", "new"))
    assert next_binds == {"f0": "new"}
    assert binds["f0"] == "first"


@pytest.mark.parametrize(
    "expression,error",
    [
        (Filter("text.name", "eq", "x"), NotImplementedError),
        (Filter("unknown", "eq", "x"), ValueError),
        (Filter("embedding", "is_null"), NotImplementedError),
        (Filter("text", "oracle.raw", "x"), NotImplementedError),
        (Filter("text", "contains", "x"), NotImplementedError),
        (Filter("text", "gt", "x"), NotImplementedError),
        (Filter("number", "gt", True), TypeError),
        (Filter("number", "between", (1, None)), TypeError),
        (Filter("number", "gt", 1.5), NotImplementedError),
    ],
)
def test_unsupported_filters_fail_explicitly(collection, expression, error):
    with pytest.raises(error):
        collection._prepare_filter(expression)


def test_ordering_is_quoted_and_direction_is_checked(collection):
    sql = collection._prepare_order_by({"text": False})
    assert sql == '"body text" DESC NULLS LAST, "doc""id" ASC'
    with pytest.raises(TypeError):
        collection._prepare_order_by({"text": "DESC; DROP TABLE X"})
    with pytest.raises(NotImplementedError):
        collection._prepare_order_by({"embedding": True})


def test_filter_values_are_snapshot_before_translation(collection, mock_database):
    expression = Filter("text", "eq", "original")
    compiled = collection._prepare_filter(expression)
    expression.value = "changed"
    assert compiled[1] == {"f0": "original"}
