# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from agent_framework import Filter, FilterGroup
from agent_framework._vector_filters import validate_filter
from qdrant_client import AsyncQdrantClient

from agent_framework_qdrant import QdrantCollection


@pytest.fixture
def collection(definition):
    client = AsyncMock(spec=AsyncQdrantClient)
    client.init_options = {}
    return QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)


def test_group_and_negation_translation(collection):
    expression = FilterGroup(
        "not",
        [
            FilterGroup("or", [Filter("text", "eq", "x' OR true"), Filter("integer", "eq", 2**63 - 1)]),
        ],
    )
    native = collection._prepare_filter(expression)
    assert native is not None
    assert native.model_dump(exclude_none=True) == {
        "must": [
            {
                "must_not": [
                    {
                        "should": [
                            {"key": "body", "match": {"value": "x' OR true"}},
                            {"key": "integer", "match": {"value": 2**63 - 1}},
                        ]
                    }
                ]
            }
        ]
    }


@pytest.mark.parametrize("operator", ["starts_with", "ends_with", "contains_text", "qdrant.text", "redis.tag"])
def test_reject_literal_text_and_unknown_namespaces(collection, operator):
    expression = Filter("text", operator, "literal*_%'")
    validate_filter(expression, field_names=collection.definition.names)
    with pytest.raises(NotImplementedError, match="operator"):
        collection._prepare_filter(expression)


@pytest.mark.parametrize(
    "expression",
    [
        Filter("tags", "eq", ["one"]),
        Filter("tags", "ne", ["one"]),
        Filter("text", "contains", "one"),
        Filter("text", "gt", "a"),
        Filter("tags", "contains_any", [None]),
        Filter("embedding", "exists"),
        Filter("id", "gt", 3),
    ],
)
def test_reject_non_equivalent_operations(collection, expression):
    with pytest.raises(NotImplementedError):
        collection._prepare_filter(expression)


@pytest.mark.parametrize("value", [2**53, -(2**53), float("inf"), True, pytest.param(10**400, id="oversized-int")])
def test_reject_unsafe_numeric_range(collection, value):
    with pytest.raises((TypeError, ValueError)):
        collection._prepare_filter(Filter("integer", "gt", value))


def test_numeric_equality_preserves_bool_distinction(collection):
    native = collection._prepare_filter(Filter("integer", "eq", True))
    assert native is not None
    assert native.model_dump(exclude_none=True) == {"must": [{"has_id": []}]}
    native = collection._prepare_filter(Filter("integer", "eq", 1.0))
    assert native is not None
    assert native.model_dump(exclude_none=True) == {"must": [{"key": "integer", "match": {"value": 1}}]}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, [1]),
        (1.0, [1]),
        (True, []),
        (False, []),
        (1.5, []),
        (-1, []),
        ("1", []),
        (2**53 + 1, [2**53 + 1]),
        (2**63, [2**63]),
        (float(2**63), [2**63]),
        (2**64 - 1, [2**64 - 1]),
        (float(2**64 - 1), []),
        (2**64, []),
        pytest.param(10**400, [], id="oversized-int"),
    ],
)
@pytest.mark.parametrize("operator", ["eq", "ne", "in", "not_in"])
def test_integer_key_filter_operand_semantics(collection, value, expected, operator):
    expression = Filter("id", operator, [value, True, None, "invalid"] if operator in {"in", "not_in"} else value)
    condition = collection._prepare_filter_condition(expression)
    expected_condition = {"has_id": expected}
    assert condition.model_dump(exclude_none=True) == (
        {"must_not": [expected_condition]} if operator in {"ne", "not_in"} else expected_condition
    )
