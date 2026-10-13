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


def test_unknown_field(collection):
    with pytest.raises(NotImplementedError):
        collection._prepare_filter(Filter("missing", "eq", "a"))


def test_vector_field_rejected(collection):
    with pytest.raises(NotImplementedError):
        collection._prepare_filter(Filter("embedding", "eq", "a"))
