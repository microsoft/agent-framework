# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import pytest
from agent_framework import Filter, FilterGroup


def test_equality_and_comparisons(collection):
    assert collection._prepare_filter(Filter("text", "eq", "a")) == '(body == "a")'
    assert collection._prepare_filter(Filter("text", "ne", "a")) == '(body != "a")'
    assert collection._prepare_filter(Filter("number", "gt", 1)) == "(price > 1)"
    assert collection._prepare_filter(Filter("number", "gte", 1.5)) == "(price >= 1.5)"
    assert collection._prepare_filter(Filter("number", "lt", 2)) == "(price < 2)"
    assert collection._prepare_filter(Filter("number", "lte", 2)) == "(price <= 2)"


def test_between_in_not_in(collection):
    assert collection._prepare_filter(Filter("number", "between", [1, 3])) == "(price >= 1 and price <= 3)"
    assert collection._prepare_filter(Filter("id", "in", [1, 2])) == "(point_key in [1, 2])"
    assert collection._prepare_filter(Filter("text", "not_in", ["a", "b"])) == '(body not in ["a", "b"])'


def test_bool_literals(collection):
    assert collection._prepare_filter(Filter("flag", "eq", True)) == "(flag == true)"
    assert collection._prepare_filter(Filter("flag", "eq", False)) == "(flag == false)"


def test_string_control_characters_are_escaped(collection):
    # Newlines/quotes/backslashes must not break out of the string literal.
    assert collection._prepare_filter(Filter("text", "eq", 'a"b\nc')) == '(body == "a\\"b\\nc")'


def test_and_or_not_groups(collection):
    expr = FilterGroup("and", [Filter("text", "eq", "a"), Filter("number", "gt", 1)])
    assert collection._prepare_filter(expr) == '((body == "a") and (price > 1))'

    expr = FilterGroup("or", [Filter("text", "eq", "a"), Filter("number", "gt", 1)])
    assert collection._prepare_filter(expr) == '((body == "a") or (price > 1))'

    expr = FilterGroup("not", [Filter("text", "eq", "a")])
    assert collection._prepare_filter(expr) == '(not (body == "a"))'


def test_none_filter_is_empty(collection):
    assert collection._prepare_filter(None) == ""


def test_unsupported_operator(collection):
    with pytest.raises(NotImplementedError):
        collection._prepare_filter(Filter("text", "contains", "a"))


def test_boolean_operand_on_numeric_field_rejected(collection):
    # Filter("number", "eq", True) must not emit `price == true`.
    with pytest.raises(ValueError, match="numeric field"):
        collection._prepare_filter(Filter("number", "eq", True))


def test_type_mismatched_operand_rejected(collection):
    with pytest.raises(ValueError, match="string field"):
        collection._prepare_filter(Filter("text", "eq", 5))


def test_membership_element_type_checked(collection):
    with pytest.raises(ValueError, match="numeric field"):
        collection._prepare_filter(Filter("number", "in", [1, True]))


def test_ordered_comparison_requires_numeric_field(collection):
    with pytest.raises(NotImplementedError, match="ordered comparisons"):
        collection._prepare_filter(Filter("text", "gt", "a"))


def test_unknown_field(collection):
    with pytest.raises(NotImplementedError):
        collection._prepare_filter(Filter("missing", "eq", "a"))


def test_vector_field_rejected(collection):
    with pytest.raises(NotImplementedError):
        collection._prepare_filter(Filter("embedding", "eq", "a"))


def test_non_bmp_string_not_surrogate_escaped(collection):
    # Emoji / supplementary-plane characters must stay literal UTF-8: Milvus parses string
    # literals with Go's strconv.Unquote, which rejects 😀-style surrogate escapes.
    assert collection._prepare_filter(Filter("text", "eq", "hi 😀")) == '(body == "hi 😀")'
    assert collection._prepare_filter(Filter("text", "in", ["😀", "é"])) == '(body in ["😀", "é"])'


def test_integer_field_integral_float_normalized(collection):
    # Integral floats must emit integer literals so Milvus's INT64 parser can match the key.
    assert collection._prepare_filter(Filter("id", "eq", 1.0)) == "(point_key == 1)"
    assert collection._prepare_filter(Filter("id", "ne", 2.0)) == "(point_key != 2)"
    assert collection._prepare_filter(Filter("id", "gt", 2.0)) == "(point_key > 2)"
    assert collection._prepare_filter(Filter("id", "in", [1.0, 2.0])) == "(point_key in [1, 2])"
    assert collection._prepare_filter(Filter("id", "between", [1.0, 3.0])) == "(point_key >= 1 and point_key <= 3)"


def test_integer_field_fractional_float_ordered_translated(collection):
    # Fractional bounds on an INT64 field are rewritten to the exact equivalent integer bound.
    assert collection._prepare_filter(Filter("id", "gt", 1.5)) == "(point_key >= 2)"
    assert collection._prepare_filter(Filter("id", "gte", 1.5)) == "(point_key >= 2)"
    assert collection._prepare_filter(Filter("id", "lt", 1.5)) == "(point_key <= 1)"
    assert collection._prepare_filter(Filter("id", "lte", 1.5)) == "(point_key <= 1)"
    assert collection._prepare_filter(Filter("id", "between", [1.5, 3.5])) == "(point_key >= 2 and point_key <= 3)"


def test_integer_field_fractional_float_equality_rejected(collection):
    # A fractional operand cannot equal any integer key, so equality/membership is rejected.
    with pytest.raises(ValueError, match="integral operand"):
        collection._prepare_filter(Filter("id", "eq", 1.5))
    with pytest.raises(ValueError, match="integral operand"):
        collection._prepare_filter(Filter("id", "in", [1.5]))


def test_float_field_keeps_fractional_operand(collection):
    # Float-declared fields are unaffected by integer normalization.
    assert collection._prepare_filter(Filter("number", "gte", 1.5)) == "(price >= 1.5)"
    assert collection._prepare_filter(Filter("number", "eq", 2.5)) == "(price == 2.5)"
