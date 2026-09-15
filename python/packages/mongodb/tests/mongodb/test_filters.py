# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import math

import pytest
from agent_framework import Filter, FilterGroup, VectorStoreCollectionDefinition, VectorStoreField
from bson import ObjectId
from bson.regex import Regex


def test_scalar_equality_uses_expr_type_and_existence_guards(collection):
    integer = collection._prepare_filter(Filter("integer", "eq", 1.0))
    assert integer == {
        "$expr": {
            "$and": [
                {"$in": [{"$type": "$integer"}, ["int", "long"]]},
                {"$eq": ["$integer", {"$literal": 1}]},
            ]
        }
    }
    boolean = collection._prepare_filter(Filter("integer", "eq", True))
    assert boolean == {"$expr": {"$literal": False}}


def test_null_missing_and_negation_are_distinct(collection):
    assert collection._prepare_filter(Filter("text", "is_null")) == {
        "$expr": {
            "$and": [
                {"$ne": [{"$type": "$body"}, "missing"]},
                {"$eq": ["$body", None]},
            ]
        }
    }
    not_equal = collection._prepare_filter(Filter("text", "ne", "x"))
    assert not_equal == {
        "$expr": {
            "$and": [
                {"$ne": [{"$type": "$body"}, "missing"]},
                {
                    "$not": [
                        {
                            "$and": [
                                {"$eq": [{"$type": "$body"}, "string"]},
                                {"$eq": ["$body", {"$literal": "x"}]},
                            ]
                        }
                    ]
                },
            ]
        }
    }
    assert collection._prepare_filter(Filter("text", "exists")) == {"$expr": {"$ne": [{"$type": "$body"}, "missing"]}}


def test_list_whole_equality_and_membership_remain_separate(collection):
    whole = collection._prepare_filter(Filter("tags", "eq", ["one"]))
    assert whole == {
        "$expr": {
            "$and": [
                {"$isArray": "$tags"},
                {"$eq": ["$tags", {"$literal": ["one"]}]},
            ]
        }
    }
    contains = collection._prepare_filter(Filter("tags", "contains", "one"))
    assert contains == {
        "$expr": {
            "$cond": [
                {"$isArray": "$tags"},
                {
                    "$anyElementTrue": {
                        "$map": {
                            "input": "$tags",
                            "as": "item",
                            "in": {"$in": ["$$item", {"$literal": ["one"]}]},
                        }
                    }
                },
                False,
            ]
        }
    }
    assert collection._prepare_filter(Filter("tags", "contains_all", [])) == {
        "$expr": {
            "$cond": [
                {"$isArray": "$tags"},
                {"$setIsSubset": [{"$literal": []}, "$tags"]},
                False,
            ]
        }
    }


@pytest.mark.parametrize("field_type", ["tuple", "set", "Sequence"])
def test_non_list_collection_fields_reject_filters(mongo_mocks, field_type):
    client, _, native_collection = mongo_mocks
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("data", name="items", type_=field_type),
    ])
    from agent_framework_mongodb import MongoDBCollection

    collection = MongoDBCollection(
        dict,
        definition=definition,
        collection_name="collection_shapes",
        async_client=client,
        database_name="vectors",
    )
    with pytest.raises(NotImplementedError, match="container identity"):
        collection._prepare_filter(Filter("items", "eq", ["one"]))
    native_collection.find.assert_not_called()


@pytest.mark.parametrize(
    "expression",
    [
        Filter("tags", "eq", [{"b": 2, "a": 1}]),
        Filter("tags", "in", [[{"a": 1}]]),
        Filter("tags", "contains", {"a": 1}),
        Filter("tags", "contains", ("one",)),
        Filter("tags", "contains_any", [{"a": 1}]),
    ],
)
async def test_collection_filters_reject_lossy_operand_shapes(collection, mongo_mocks, expression):
    _, _, native_collection = mongo_mocks
    with pytest.raises(NotImplementedError):
        await collection.get(filter=expression)
    native_collection.find.assert_not_called()


def test_in_not_in_ignore_null_and_incompatible_operands(collection):
    assert collection._prepare_filter(Filter("integer", "in", [1, 1.0, True, None, "1"])) == {
        "$expr": {
            "$and": [
                {"$in": [{"$type": "$integer"}, ["int", "long"]]},
                {"$in": ["$integer", {"$literal": [1, 1]}]},
            ]
        }
    }
    not_in = collection._prepare_filter(Filter("integer", "not_in", []))
    assert not_in["$expr"]["$and"][0] == {"$in": [{"$type": "$integer"}, ["int", "long"]]}


@pytest.mark.parametrize(
    ("operator", "value", "pattern"),
    [
        ("starts_with", "^.*[x]$", r"^\^\.\*\[x\]\$"),
        ("ends_with", "^.*[x]$", r"\^\.\*\[x\]\$$"),
        ("contains_text", "^.*[x]$", r"\^\.\*\[x\]\$"),
    ],
)
def test_literal_text_uses_escaped_regex(collection, operator, value, pattern):
    native = collection._prepare_filter(Filter("text", operator, value))
    regex = native["$expr"]["$cond"][1]["$regexMatch"]["regex"]
    assert isinstance(regex, Regex)
    assert regex.pattern == pattern


def test_groups_preserve_whole_not_semantics(collection):
    expression = FilterGroup(
        "not",
        [FilterGroup("or", [Filter("text", "eq", "x"), Filter("integer", "gt", 2)])],
    )
    native = collection._prepare_filter(expression)
    assert "$not" in native["$expr"]
    assert "$or" in native["$expr"]["$not"][0]


@pytest.mark.parametrize("value", [2**63, -(2**63) - 1, math.inf, math.nan])
async def test_invalid_query_numbers_fail_before_io(collection, mongo_mocks, value):
    _, _, native_collection = mongo_mocks
    with pytest.raises(ValueError):
        await collection.get(filter=Filter("integer", "eq", value))
    native_collection.find.assert_not_called()


@pytest.mark.parametrize(
    "expression",
    [
        Filter("tags", "eq", ["one"]),
        Filter("tags", "contains", "one"),
        Filter("text", "contains_text", "one"),
        Filter("text", "is_null"),
        Filter("text", "exists"),
        Filter("text", "ne", "one"),
        Filter("text", "not_in", ["one"]),
        FilterGroup("not", [Filter("text", "eq", "one")]),
    ],
)
def test_vector_prefilter_rejects_non_equivalent_operations(collection, expression):
    with pytest.raises(NotImplementedError):
        collection._prepare_vector_filter(expression)


def test_vector_prefilter_requires_indexed_scalar_field(collection):
    with pytest.raises(NotImplementedError, match="is_indexed"):
        collection._prepare_vector_filter(Filter("text", "eq", "hello"))
    assert collection._prepare_vector_filter(Filter("number", "between", [1, 3])) == {"number": {"$gte": 1, "$lte": 3}}
    assert collection._prepare_vector_filter(Filter("integer", "eq", True)) == {"_id": {"$in": []}}


def test_object_id_filter_keeps_native_identity(mongo_mocks):
    client, _, _ = mongo_mocks
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="ObjectId"),
        VectorStoreField("vector", name="vector", dimensions=2),
    ])
    from agent_framework_mongodb import MongoDBCollection

    collection = MongoDBCollection(
        dict,
        definition=definition,
        collection_name="objects",
        async_client=client,
        database_name="vectors",
    )
    key = ObjectId()
    assert collection._prepare_filter(Filter("id", "eq", key))["$expr"]["$and"][1] == {
        "$eq": ["$_id", {"$literal": key}]
    }
