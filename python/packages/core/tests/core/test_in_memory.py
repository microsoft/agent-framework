# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import ast
import inspect
import math
import warnings
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, getcontext, localcontext
from typing import Annotated, Any, cast
from uuid import UUID

import pytest

from agent_framework import (
    BaseEmbeddingClient,
    DistanceFunction,
    Embedding,
    EmbeddingGenerationOptions,
    Filter,
    FilterGroup,
    GeneratedEmbeddings,
    InMemoryCollection,
    InMemoryStore,
    Param,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    create_vector_search_tool,
    register_vectorstoremodel,
    vectorstoremodel,
)
from agent_framework import _in_memory as in_memory_module
from agent_framework._feature_stage import ExperimentalWarning
from agent_framework.exceptions import IntegrationException

pytestmark = pytest.mark.filterwarnings("ignore::agent_framework._feature_stage.ExperimentalWarning")

with warnings.catch_warnings():
    warnings.simplefilter("ignore", ExperimentalWarning)

    @vectorstoremodel(collection_name="documents")
    @dataclass
    class Document:
        id: Annotated[str, VectorStoreField("key")]
        text: Annotated[str, VectorStoreField("data")]
        category: Annotated[str, VectorStoreField("data")]
        rating: Annotated[int, VectorStoreField("data")]
        tags: Annotated[list[str], VectorStoreField("data")]
        optional: Annotated[str | None, VectorStoreField("data")]
        vector: Annotated[
            list[float] | None,
            VectorStoreField("vector", dimensions=2, distance_function="cosine_similarity"),
        ] = None


DOCUMENTS = (
    Document("one", "Luxury hotel", "travel", 5, ["wifi", "pool"], "featured", [1.0, 0.0]),
    Document("two", "Budget hostel", "work", 3, ["wifi"], None, [0.0, 1.0]),
)


class QueryEmbeddingClient(BaseEmbeddingClient[str, list[float], EmbeddingGenerationOptions]):
    async def get_embeddings(
        self,
        values: Sequence[str],
        *,
        options: EmbeddingGenerationOptions | None = None,
    ) -> GeneratedEmbeddings[list[float], EmbeddingGenerationOptions]:
        return GeneratedEmbeddings([Embedding(vector=[1.0, 0.0]) for _ in values], options=options)


async def _create_collection() -> InMemoryCollection[str, Document]:
    collection = InMemoryCollection(Document)
    await collection.ensure_collection_exists()
    await collection.upsert(DOCUMENTS, generate_vectors=False)
    return collection


async def _result_ids(
    collection: InMemoryCollection[str, Document],
    filter_: Filter | FilterGroup,
) -> list[str]:
    results = await collection.search(vector=[1.0, 0.0], filter=filter_, top=10)
    return [result["record"].id async for result in results]


async def test_in_memory_store_shares_collection_state_and_lifecycle() -> None:
    store = InMemoryStore()
    first = store.get_collection(Document)
    second = store.get_collection(Document)

    assert not await first.collection_exists()
    assert await store.list_collection_names() == []

    await first.ensure_collection_exists()
    await first.upsert([DOCUMENTS[0]], generate_vectors=False)

    assert await store.list_collection_names() == ["documents"]
    assert await second.get(["one"], include_vectors=True) == [DOCUMENTS[0]]

    await store.ensure_collection_deleted("documents")
    assert not await first.collection_exists()
    with pytest.raises(IntegrationException, match="does not exist"):
        await second.get(["one"])


def test_in_memory_store_rejects_conflicting_collection_definitions() -> None:
    store = InMemoryStore()
    store.get_collection(Document)
    other_definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="other_id"),
            VectorStoreField("vector", name="vector", dimensions=2),
        ],
        collection_name="documents",
    )

    with pytest.raises(ValueError, match="another definition"):
        store.get_collection(dict, definition=other_definition)


async def test_in_memory_collection_requires_creation() -> None:
    collection: InMemoryCollection[str, Document] = InMemoryCollection(Document)

    with pytest.raises(IntegrationException, match="does not exist"):
        await collection.get()


async def test_in_memory_crud_listing_ordering_and_defensive_copies() -> None:
    collection = await _create_collection()

    assert await collection.get(["one"]) == [
        Document("one", "Luxury hotel", "travel", 5, ["wifi", "pool"], "featured"),
    ]
    assert await collection.get(order_by={"rating": False}, top=1) == [
        Document("one", "Luxury hotel", "travel", 5, ["wifi", "pool"], "featured"),
    ]
    assert await collection.get(order_by={"rating": True}, skip=1, top=1) == [
        Document("one", "Luxury hotel", "travel", 5, ["wifi", "pool"], "featured"),
    ]
    assert await collection.get(order_by={"optional": True}) == [
        Document("one", "Luxury hotel", "travel", 5, ["wifi", "pool"], "featured"),
        Document("two", "Budget hostel", "work", 3, ["wifi"], None),
    ]
    with pytest.raises(ValueError, match="not part of the vector store definition"):
        await collection.get(order_by={"missing": True})
    with pytest.raises(TypeError, match="must be a boolean"):
        await collection.get(order_by=cast(Any, {"rating": "descending"}))

    fetched = (await collection.get(["one"], include_vectors=True))[0]
    cast(list[float], fetched.vector)[0] = 99.0
    assert (await collection.get(["one"], include_vectors=True))[0].vector == [1.0, 0.0]

    await collection.delete(["one", "missing"])
    assert await collection.get(["one"]) == []


async def test_in_memory_get_filters_before_ordering_and_paging() -> None:
    collection = await _create_collection()

    results = await collection.get(
        filter=Filter("category", "eq", "travel"),
        order_by={"rating": False},
        top=1,
    )

    assert results == [Document("one", "Luxury hotel", "travel", 5, ["wifi", "pool"], "featured")]


@pytest.mark.parametrize("include_vectors", [False, True])
async def test_in_memory_search_page_is_detached_from_stored_records(include_vectors: bool) -> None:
    collection = await _create_collection()
    results = await collection.search(vector=[1.0, 0.0], skip=1, top=1, include_vectors=include_vectors)

    assert results.metadata == {"in_memory_total_count": 2}
    rows = [result async for result in results]
    assert len(rows) == 1
    record = rows[0]["record"]
    assert record.id == "two"
    assert rows[0]["score"] == 0.0
    record.tags.append("changed")
    if include_vectors:
        assert record.vector is not None
        assert record.vector == [0.0, 1.0]
        record.vector[0] = 99.0
    else:
        assert record.vector is None

    assert await collection.get(["two"], include_vectors=True) == [DOCUMENTS[1]]
    next_results = await collection.search(vector=[1.0, 0.0], skip=1, top=1, include_vectors=True)
    assert [result["record"] async for result in next_results] == [DOCUMENTS[1]]


async def test_in_memory_generates_missing_string_keys() -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id", type_="str", is_auto_generated=True),
            VectorStoreField("data", name="text"),
            VectorStoreField("vector", name="vector", dimensions=2),
        ],
        collection_name="generated-keys",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(dict, definition=definition)
    await collection.ensure_collection_exists()

    keys = await collection.upsert(
        [{"text": "generated", "vector": [1.0, 0.0]}],
        generate_vectors=False,
    )

    assert len(keys) == 1
    assert isinstance(keys[0], str)
    assert await collection.get(keys, include_vectors=True) == [
        {"id": keys[0], "text": "generated", "vector": [1.0, 0.0]}
    ]


@pytest.mark.parametrize(
    ("filter_", "expected"),
    [
        (Filter("category", "eq", "travel"), ["one"]),
        (Filter("category", "ne", "travel"), ["two"]),
        (Filter("rating", "gt", 4), ["one"]),
        (Filter("rating", "gte", 5), ["one"]),
        (Filter("rating", "lt", 4), ["two"]),
        (Filter("rating", "lte", 3), ["two"]),
        (Filter("rating", "between", (4, 5)), ["one"]),
        (Filter("category", "in", ("travel",)), ["one"]),
        (Filter("category", "not_in", ("travel",)), ["two"]),
        (Filter("optional", "is_null"), ["two"]),
        (Filter("optional", "is_not_null"), ["one"]),
        (Filter("optional", "exists"), ["one", "two"]),
        (Filter("optional", "starts_with", "feat"), ["one"]),
        (Filter("tags", "contains", "pool"), ["one"]),
        (Filter("tags", "contains_any", ("pool", "missing")), ["one"]),
        (Filter("tags", "contains_all", ("wifi", "pool")), ["one"]),
        (Filter("text", "starts_with", "Luxury"), ["one"]),
        (Filter("text", "ends_with", "hostel"), ["two"]),
        (Filter("text", "contains_text", "hotel"), ["one"]),
        (Filter("rating", "eq", True), []),
        (Filter("rating", "in", (True,)), []),
        (FilterGroup("not", (Filter("category", "eq", "travel"),)), ["two"]),
    ],
)
async def test_in_memory_filter_operators(
    filter_: Filter | FilterGroup,
    expected: list[str],
) -> None:
    assert await _result_ids(await _create_collection(), filter_) == expected


@pytest.mark.parametrize(
    ("operator", "operand", "expected"),
    [
        ("eq", [[1]], {"integer", "float"}),
        ("eq", [[True]], {"boolean"}),
        ("ne", [[1]], {"boolean", "zero"}),
        ("ne", [[True]], {"integer", "float", "zero"}),
        ("in", ([[1]],), {"integer", "float"}),
        ("in", ([[True]],), {"boolean"}),
        ("not_in", ([[1]],), {"boolean", "zero"}),
        ("not_in", ([[True]],), {"integer", "float", "zero"}),
        ("contains", [1], {"integer", "float"}),
        ("contains", [True], {"boolean"}),
        ("contains_any", ([1],), {"integer", "float"}),
        ("contains_any", ([True],), {"boolean"}),
        ("contains_all", ([1],), {"integer", "float"}),
        ("contains_all", ([True],), {"boolean"}),
    ],
)
async def test_in_memory_filters_distinguish_nested_booleans_from_numbers(
    operator: str,
    operand: Any,
    expected: set[str],
) -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("data", name="value"),
            VectorStoreField("vector", name="vector", dimensions=2),
        ],
        collection_name="nested-values",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(dict, definition=definition)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [
            {"id": "integer", "value": [[1]], "vector": [1.0, 0.0]},
            {"id": "float", "value": [[1.0]], "vector": [1.0, 0.0]},
            {"id": "boolean", "value": [[True]], "vector": [1.0, 0.0]},
            {"id": "zero", "value": [[0]], "vector": [1.0, 0.0]},
        ],
        generate_vectors=False,
    )
    filter_ = Filter("value", operator, operand)

    records = await collection.get(filter=filter_)
    assert {record["id"] for record in records} == expected
    results = await collection.search(vector=[1.0, 0.0], filter=filter_)
    assert {result["record"]["id"] async for result in results} == expected


async def test_in_memory_filter_groups_use_explicit_and_or_semantics() -> None:
    collection = await _create_collection()
    tenant_scope = Filter("category", "eq", "travel")
    model_filter = Filter("id", "eq", "two")

    assert await _result_ids(collection, FilterGroup("and", (tenant_scope, model_filter))) == []
    assert await _result_ids(collection, FilterGroup("or", (tenant_scope, model_filter))) == ["one", "two"]


async def test_in_memory_search_tool_resolves_params_without_weakening_fixed_filter() -> None:
    collection: InMemoryCollection[str, Document] = InMemoryCollection(
        Document,
        embedding_generator=QueryEmbeddingClient(),
    )
    await collection.ensure_collection_exists()
    await collection.upsert(DOCUMENTS, generate_vectors=False)
    record_id = Param("record_id", str)
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup(
            "and",
            (
                Filter("category", "eq", "travel"),
                Filter("id", "eq", record_id),
            ),
        ),
    )

    assert len(await tool(query="hotel", record_id="one")) == 1
    assert await tool(query="hotel", record_id="two") == []
    assert len(await tool(query="hotel")) == 1


async def test_in_memory_search_tool_omits_null_text_condition_in_and_group() -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("data", name="description"),
            VectorStoreField("data", name="rating"),
            VectorStoreField("vector", name="vector", dimensions=2),
        ],
        collection_name="optional-text",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(
        dict, definition=definition, embedding_generator=QueryEmbeddingClient()
    )
    await collection.ensure_collection_exists()
    records = [
        {"id": "text", "rating": 5, "description": "Pool hotel"},
        {"id": "empty", "rating": 5, "description": ""},
        {"id": "star", "rating": 5, "description": "5* hotel"},
        {"id": "null", "rating": 5, "description": None},
        {"id": "low", "rating": 3, "description": "Pool hotel"},
    ]
    await collection.upsert(
        [{**record, "vector": [1.0, 0.0]} for record in records],
        generate_vectors=False,
    )
    tool = create_vector_search_tool(
        collection,
        top=10,
        filter=FilterGroup(
            "and",
            (
                Filter("rating", "gte", 4),
                Filter(
                    "description",
                    "contains_text",
                    Param("text", str | None, default=None, omit_if_none=True),
                ),
            ),
        ),
        result_mapper=lambda response: response["record"]["id"],
    )

    assert {item.text for item in await tool(query="hotel")} == {"text", "empty", "star", "null"}
    assert {item.text for item in await tool(query="hotel", text=None)} == {"text", "empty", "star", "null"}
    assert {item.text for item in await tool(query="hotel", text="Pool")} == {"text"}
    assert {item.text for item in await tool(query="hotel", text="")} == {"text", "empty", "star"}
    assert {item.text for item in await tool(query="hotel", text="*")} == {"star"}


@pytest.mark.parametrize(
    ("distance_function", "expected_scores"),
    [
        ("cosine_similarity", (1.0, 0.0)),
        ("cosine_distance", (0.0, 1.0)),
        ("dot_prod", (1.0, 0.0)),
        ("negative_dot_prod", (-1.0, 0.0)),
        ("euclidean_distance", (0.0, math.sqrt(2))),
        ("euclidean_squared_distance", (0.0, 2.0)),
        ("manhattan", (0.0, 2.0)),
        ("hamming", (0.0, 1.0)),
        ("DEFAULT", (0.0, 1.0)),
    ],
)
async def test_in_memory_distance_functions(
    distance_function: DistanceFunction,
    expected_scores: tuple[float, float],
) -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField(
                "vector",
                name="vector",
                dimensions=2,
                distance_function=distance_function,
            ),
        ],
        collection_name=f"distance-{distance_function}",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(dict, definition=definition)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [
            {"id": "same", "vector": [1.0, 0.0]},
            {"id": "other", "vector": [0.0, 1.0]},
        ],
        generate_vectors=False,
    )

    results = await collection.search(vector=[1.0, 0.0], top=2)
    responses = [result async for result in results]

    assert [response["record"]["id"] for response in responses] == ["same", "other"]
    assert [cast(float, response["score"]) for response in responses] == pytest.approx(expected_scores)
    assert results.metadata == {"in_memory_total_count": 2}


@pytest.mark.parametrize("scale", [1e308, 1e-308, 5e-324])
@pytest.mark.parametrize("similarity", [1.0, 0.0, -1.0])
@pytest.mark.parametrize("distance_function", ["cosine_similarity", "cosine_distance", "DEFAULT"])
def test_cosine_scoring_handles_extreme_finite_magnitudes(
    scale: float, similarity: float, distance_function: DistanceFunction
) -> None:
    left = [scale, 0.0]
    right = [scale, 0.0] if similarity == 1.0 else [-scale, 0.0] if similarity == -1.0 else [0.0, scale]
    expected = similarity if distance_function == "cosine_similarity" else 1 - similarity

    assert in_memory_module._calculate_score(left, right, distance_function) == pytest.approx(expected)


async def test_large_opposing_vectors_are_not_misranked() -> None:
    collection = InMemoryCollection(Document)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [
            Document("opposed", "text", "travel", 5, [], None, [-1e308, 0.0]),
            Document("aligned", "text", "travel", 5, [], None, [1e308, 0.0]),
        ],
        generate_vectors=False,
    )
    results = await collection.search(vector=[1e308, 0.0], score_threshold=0.5)

    assert [result["record"].id async for result in results] == ["aligned"]


@pytest.mark.parametrize(
    ("right", "expected"),
    [([1e-308, 1e-308], 1.0), ([-1e-308, -1e-308], -1.0), ([1e-308, -1e-308], 0.0)],
)
def test_cosine_scales_each_vector_independently(right: list[float], expected: float) -> None:
    assert in_memory_module._calculate_score([1e308, 1e308], right, "cosine_similarity") == pytest.approx(expected)


async def test_non_finite_score_reports_the_record_context() -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("vector", name="vector", dimensions=2, distance_function="dot_prod"),
        ],
        collection_name="non-finite-score",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(dict, definition=definition)
    await collection.ensure_collection_exists()
    await collection.upsert([{"id": "overflow", "vector": [1e308, 0.0]}], generate_vectors=False)

    with pytest.raises(ValueError, match="Record 'overflow'.*non-finite score"):
        await collection.search(vector=[1e308, 0.0])


@pytest.mark.parametrize(
    ("distance_function", "left", "right"),
    [
        ("dot_prod", [1e308, 0.0], [1e308, 0.0]),
        ("dot_prod", [1e308, 1e308], [1e308, -1e308]),
        ("negative_dot_prod", [1e308, 0.0], [1e308, 0.0]),
        ("euclidean_distance", [1e308, 0.0], [-1e308, 0.0]),
        ("euclidean_squared_distance", [1e200, 0.0], [0.0, 0.0]),
        ("manhattan", [1e308, 0.0], [-1e308, 0.0]),
    ],
)
def test_distance_functions_reject_non_finite_scores(
    distance_function: DistanceFunction, left: list[float], right: list[float]
) -> None:
    with pytest.raises(ValueError, match="non-finite score"):
        in_memory_module._calculate_score(left, right, distance_function)


def test_distance_functions_do_not_compute_unnecessary_squares() -> None:
    assert in_memory_module._calculate_score([1e200, 0], [0, 0], "euclidean_distance") == 1e200
    assert in_memory_module._calculate_score([1e308, 0], [-1e308, 0], "hamming") == 0.5


async def test_hamming_scores_and_thresholds_use_mismatch_proportions() -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("vector", name="vector", dimensions=2, distance_function="hamming"),
        ],
        collection_name="normalized-hamming",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(dict, definition=definition)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [
            {"id": "same", "vector": [0, 0]},
            {"id": "partial", "vector": [1, 0]},
            {"id": "different", "vector": [1, 1]},
        ],
        generate_vectors=False,
    )
    results = await collection.search(vector=[0, 0], score_threshold=0.5)

    assert [(result["record"]["id"], result["score"]) async for result in results] == [
        ("same", 0.0),
        ("partial", 0.5),
    ]


@pytest.mark.parametrize(
    ("vector_type", "coordinate"),
    [("int64", 2**53), ("int64", -(2**53) - 1), ("uint64", 2**64 - 2)],
)
@pytest.mark.parametrize("threshold", [None, 0.0])
async def test_hamming_preserves_large_integer_coordinates(
    vector_type: str, coordinate: int, threshold: float | None
) -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("vector", name="vector", type_=vector_type, dimensions=2, distance_function="hamming"),
        ],
        collection_name="integer-hamming",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(dict, definition=definition)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [
            {"id": "different", "vector": [coordinate + 1, 0]},
            {"id": "same", "vector": [coordinate, 0]},
        ],
        generate_vectors=False,
    )

    results = await collection.search(vector=[coordinate, 0], score_threshold=threshold)

    expected = [("same", 0.0)]
    if threshold is None:
        expected.append(("different", 0.5))
    assert [(result["record"]["id"], result["score"]) async for result in results] == expected


@pytest.mark.parametrize("contents", ["empty", "missing_vector", "filtered_out"])
@pytest.mark.parametrize("score_threshold", [None, 0.5])
async def test_unsupported_distance_is_rejected_independently_of_records(
    contents: str, score_threshold: float | None
) -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("vector", name="vector", dimensions=2, distance_function="provider.unsupported"),
        ],
        collection_name="unsupported-distance",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(dict, definition=definition)
    await collection.ensure_collection_exists()
    if contents != "empty":
        await collection.upsert(
            [{"id": "one", "vector": None if contents == "missing_vector" else [1.0, 0.0]}],
            generate_vectors=False,
        )
    with pytest.raises(NotImplementedError, match="provider.unsupported"):
        await collection.search(
            vector=[1.0, 0.0],
            filter=Filter("id", "eq", "absent") if contents == "filtered_out" else None,
            score_threshold=score_threshold,
        )


@pytest.mark.parametrize(
    ("distance_function", "threshold"),
    [("DEFAULT", 1.0), ("cosine_distance", 1.0), ("cosine_similarity", 0.0)],
)
async def test_in_memory_owns_filtering_and_thresholds_before_paging(
    distance_function: DistanceFunction, threshold: float
) -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("data", name="category"),
            VectorStoreField("vector", name="vector", dimensions=2, distance_function=distance_function),
        ],
        collection_name="threshold-paging",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(dict, definition=definition)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [
            {"id": "threshold-excluded", "category": "keep", "vector": [-1.0, 0.0]},
            {"id": "filter-excluded", "category": "exclude", "vector": [1.0, 0.0]},
            {"id": "best", "category": "keep", "vector": [1.0, 0.0]},
            {"id": "boundary", "category": "keep", "vector": [0.0, 1.0]},
        ],
        generate_vectors=False,
    )

    results = await collection.search(
        vector=[1.0, 0.0],
        filter=Filter("category", "eq", "keep"),
        score_threshold=threshold,
        skip=1,
        top=1,
    )

    assert [(result["record"]["id"], result["score"]) async for result in results] == [("boundary", threshold)]
    assert results.metadata == {"in_memory_total_count": 2}


@pytest.mark.parametrize("has_records", [False, True])
async def test_in_memory_default_threshold_accepts_zero_distance(has_records: bool) -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("vector", name="vector", dimensions=2),
        ],
        collection_name="default-threshold",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(dict, definition=definition)
    await collection.ensure_collection_exists()
    if has_records:
        await collection.upsert(
            [
                {"id": "same", "vector": [1.0, 0.0]},
                {"id": "different", "vector": [0.0, 1.0]},
            ],
            generate_vectors=False,
        )

    results = await collection.search(vector=[1.0, 0.0], score_threshold=0.0)

    assert [(result["record"]["id"], result["score"]) async for result in results] == (
        [("same", 0.0)] if has_records else []
    )


@pytest.mark.parametrize("operator", ["starts_with", "ends_with", "contains_text"])
async def test_invalid_string_operand_is_rejected_for_empty_collection(operator: str) -> None:
    collection = InMemoryCollection(Document)
    await collection.ensure_collection_exists()
    expression = Filter("text", operator, "valid")
    expression.value = 1

    with pytest.raises(TypeError, match="must be a string"):
        await collection.search(vector=[1.0, 0.0], filter=expression)


@pytest.mark.parametrize("custom_codec", [False, True])
async def test_stored_values_are_normalized_before_filter_comparisons(custom_codec: bool) -> None:
    class ComparisonProbe:
        def __init__(self) -> None:
            self.value = 1

        def __eq__(self, other: object) -> bool:
            raise AssertionError("Custom equality must not execute during filtering.")

    class ComparisonList(list[Any]):
        def __eq__(self, other: object) -> bool:
            raise AssertionError("Custom list equality must not execute during filtering.")

        def __iter__(self) -> Iterator[Any]:
            raise AssertionError("Custom iteration must not execute during filtering.")

    @dataclass
    class EncodedRecord:
        id: str
        payload: Any
        vector: list[float] | None = None

    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("data", name="payload"),
            VectorStoreField("vector", name="vector", dimensions=2),
        ],
        collection_name="normalized-records",
    )
    payload = ComparisonList([ComparisonProbe()])
    collection: InMemoryCollection[str, Any]
    if custom_codec:
        register_vectorstoremodel(
            EncodedRecord,
            definition=definition,
            encoder=lambda record: {"id": record.id, "payload": record.payload, "vector": record.vector},
        )
        collection = InMemoryCollection(EncodedRecord)
        await collection.ensure_collection_exists()
        await collection.upsert([EncodedRecord("one", payload, [1.0, 0.0])], generate_vectors=False)
    else:
        collection = InMemoryCollection(dict, definition=definition)
        await collection.ensure_collection_exists()
        await collection.upsert([{"id": "one", "payload": payload, "vector": [1.0, 0.0]}], generate_vectors=False)
    fetched = (await collection.get(["one"]))[0]
    stored = fetched.payload if isinstance(fetched, EncodedRecord) else fetched["payload"]

    assert type(stored) is list
    assert stored == [{"value": 1}]
    assert await collection.get(filter=Filter("payload", "eq", [1])) == []
    assert await collection.get(filter=Filter("payload", "contains", 1)) == []


async def test_in_memory_rejects_unsafe_or_unsupported_filters() -> None:
    collection = await _create_collection()

    with pytest.raises(TypeError, match="Filter or FilterGroup"):
        await collection.search(vector=[1.0, 0.0], filter=cast(Any, "lambda record: True"))
    with pytest.raises(NotImplementedError, match="python.eval"):
        await collection.search(
            vector=[1.0, 0.0],
            filter=Filter("text", "python.eval", "__import__('os').system('echo unsafe')"),
        )
    with pytest.raises(NotImplementedError, match="nested"):
        await collection.search(vector=[1.0, 0.0], filter=Filter("text.value", "eq", "unsafe"))
    with pytest.raises(ValueError, match="more than 64 nodes"):
        await collection.search(vector=[1.0, 0.0], filter=Filter("id", "in", tuple(str(i) for i in range(65))))
    with pytest.raises(ValueError, match="must be resolved"):
        await collection.search(vector=[1.0, 0.0], filter=Filter("category", "eq", Param("category", str)))
    with pytest.raises(ValueError, match="must be finite"):
        await collection.search(vector=[1.0, 0.0], filter=Filter("rating", "ne", float("nan")))


@pytest.mark.parametrize(
    "payload",
    [
        "x.__class__.__mro__[-1].__subclasses__()",
        "x.__init__.__globals__",
        "__import__('os').system('echo unsafe')",
        "x.clear()",
        "x['a']['b']()",
    ],
)
async def test_in_memory_treats_filter_payloads_only_as_data(payload: str) -> None:
    collection = await _create_collection()

    assert await _result_ids(collection, Filter("text", "eq", payload)) == []


async def test_in_memory_rejects_invalid_vectors() -> None:
    collection = await _create_collection()

    with pytest.raises(TypeError, match="field 'query'.*numeric sequence"):
        await collection.search(vector=b"\x01\x02")
    with pytest.raises(ValueError, match="Query vector field 'vector' expects 2 dimensions; got 1"):
        await collection.search(vector=[1.0])
    with pytest.raises(ValueError, match="zero-magnitude"):
        await collection.search(vector=[0.0, 0.0])

    await collection.upsert(
        [Document("no-vector", "No vector", "travel", 5, [], None)],
        generate_vectors=False,
    )
    results = await collection.search(vector=[1.0, 0.0], top=10)
    assert [result["record"].id async for result in results] == ["one", "two"]

    await collection.upsert(
        [Document("bad-vector", "Bad vector", "travel", 5, [], None, cast(Any, ["bad", 0.0]))],
        generate_vectors=False,
    )
    with pytest.raises(TypeError, match="Record 'bad-vector'.*field 'vector'"):
        await collection.search(vector=[1.0, 0.0], top=10)

    binary_definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("vector", name="vector", dimensions=8, type_="bytes"),
        ],
        collection_name="binary",
    )
    with pytest.raises(ValueError, match="type must be one of"):
        InMemoryCollection(dict, definition=binary_definition)


@pytest.mark.parametrize("vector", [[], [1.0], [1.0, 0.0, 0.0]])
async def test_in_memory_dimension_mismatch_rejects_batch_without_writes(vector: list[float]) -> None:
    collection = InMemoryCollection(Document)
    await collection.ensure_collection_exists()

    with pytest.raises(
        ValueError, match=f"Record at index 1, vector field 'vector' expects 2 dimensions; got {len(vector)}"
    ):
        await collection.upsert(
            [DOCUMENTS[0], Document("invalid", "text", "travel", 5, [], None, vector)],
            generate_vectors=False,
        )

    assert await collection.get() == []


@pytest.mark.parametrize("has_records", [False, True])
@pytest.mark.parametrize("dimensions", [1, 2, 3])
async def test_in_memory_checks_normalized_array_query_dimensions(has_records: bool, dimensions: int) -> None:
    class ArrayLike:
        def tolist(self) -> list[float]:
            return [1.0] * dimensions

    collection = InMemoryCollection(Document)
    await collection.ensure_collection_exists()
    if has_records:
        await collection.upsert(DOCUMENTS, generate_vectors=False)

    if dimensions != 2:
        with pytest.raises(ValueError, match=f"Query vector field 'vector' expects 2 dimensions; got {dimensions}"):
            await collection.search(vector=cast(Any, ArrayLike()))
    else:
        results = await collection.search(vector=cast(Any, ArrayLike()))
        assert len([result async for result in results]) == (2 if has_records else 0)


def test_in_memory_retains_pairwise_vector_length_check() -> None:
    with pytest.raises(ValueError, match="Query and stored vectors must have the same length"):
        in_memory_module._calculate_score([1.0, 0.0], [1.0], "cosine_similarity")


async def test_in_memory_contains_rejects_mapping_fields() -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="id"),
            VectorStoreField("data", name="metadata"),
            VectorStoreField("vector", name="vector", dimensions=2),
        ],
        collection_name="mapping-values",
    )
    collection: InMemoryCollection[str, dict[str, Any]] = InMemoryCollection(dict, definition=definition)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [{"id": "one", "metadata": {"wifi": True}, "vector": [1.0, 0.0]}],
        generate_vectors=False,
    )

    with pytest.raises(ValueError, match="cannot compare field 'metadata'"):
        await collection.search(vector=[1.0, 0.0], filter=Filter("metadata", "contains", "wifi"))


def test_in_memory_filter_implementation_does_not_compile_or_evaluate_source() -> None:
    tree = ast.parse(inspect.getsource(in_memory_module))
    called_names = {
        node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert called_names.isdisjoint({"compile", "eval", "exec"})


def test_in_memory_and_filter_apis_are_experimental() -> None:
    for api in (Filter, FilterGroup, Param, InMemoryCollection, InMemoryStore):
        assert getattr(api, "__feature_stage__", None) == "experimental"


@vectorstoremodel(collection_name="scalar_filter_records")
@dataclass
class ScalarFilterRecord:
    id: Annotated[str, VectorStoreField("key")]
    created: Annotated[datetime, VectorStoreField("data")]
    day: Annotated[date, VectorStoreField("data")]
    token: Annotated[UUID, VectorStoreField("data")]
    amount: Annotated[Decimal, VectorStoreField("data")]
    span: Annotated[timedelta, VectorStoreField("data")]
    label: Annotated[str, VectorStoreField("data")]
    count: Annotated[int, VectorStoreField("data")]
    flag: Annotated[bool, VectorStoreField("data")]
    vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=2)] = None


_SCALAR_FILTER_RECORD = ScalarFilterRecord(
    "one",
    datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc),
    date(2026, 10, 16),
    UUID("00000000-0000-0000-0000-000000000001"),
    Decimal("1.5"),
    timedelta(hours=2),
    "featured",
    5,
    True,
    [1.0, 0.0],
)


async def _scalar_filter_collection() -> InMemoryCollection[str, ScalarFilterRecord]:
    collection = InMemoryCollection(ScalarFilterRecord)
    await collection.ensure_collection_exists()
    await collection.upsert([_SCALAR_FILTER_RECORD], generate_vectors=False)
    return collection


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("created", datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)),
        ("day", date(2026, 10, 16)),
        ("token", UUID("00000000-0000-0000-0000-000000000001")),
        ("amount", Decimal("1.5")),
        ("span", timedelta(hours=2)),
    ],
)
async def test_in_memory_filter_matches_a_native_scalar_against_the_stored_value(
    field_name: str,
    value: Any,
) -> None:
    """A native scalar filter must match the record it was stored from.

    The stored value is the serialized form of the field, so the operand has to
    be compared in the same representation.
    """
    collection = await _scalar_filter_collection()

    matched = await collection.get(filter=Filter(field_name, "eq", value))

    assert [record.id for record in matched] == ["one"]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("label", "featured"),
        ("count", 5),
        ("flag", True),
    ],
)
async def test_in_memory_filter_still_matches_the_scalars_it_stored_unchanged(
    field_name: str,
    value: Any,
) -> None:
    """The controls the issue lists as working must keep working."""
    collection = await _scalar_filter_collection()

    matched = await collection.get(filter=Filter(field_name, "eq", value))

    assert [record.id for record in matched] == ["one"]


async def test_in_memory_vector_search_matches_a_native_scalar_filter() -> None:
    """The search path compares the operands the same way as the get path."""
    collection = await _scalar_filter_collection()
    value = datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)

    results = await collection.search(vector=[1.0, 0.0], filter=Filter("created", "eq", value), top=10)

    assert [result["record"].id async for result in results] == ["one"]


async def test_in_memory_ordered_filter_compares_a_native_scalar() -> None:
    """An ordered comparison on a native scalar must compare, not raise."""
    collection = await _scalar_filter_collection()
    value = datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)

    matched = await collection.get(filter=Filter("created", "gte", value))

    assert [record.id for record in matched] == ["one"]


def _new_york_zone() -> Any:
    """Return America/New_York, skipping where no IANA time zone database is installed."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        return ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        pytest.skip("No IANA time zone database is available for ZoneInfo.")


async def _repeated_hour_collection(zone: Any) -> InMemoryCollection[str, ScalarFilterRecord]:
    """Three instants in America/New_York's 2026 fall-back repeated hour.

    The two folds share the wall clock 01:30 and are one hour apart in UTC;
    ``after`` is a third distinct instant in the same zone.
    """
    collection = InMemoryCollection(ScalarFilterRecord)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [
            ScalarFilterRecord(
                id="fold",
                created=datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1),
                day=date(2026, 11, 1),
                token=UUID("00000000-0000-0000-0000-0000000000f1"),
                amount=Decimal("1"),
                span=timedelta(hours=1),
                label="repeated",
                count=1,
                flag=True,
                vector=[1.0, 0.0],
            ),
            ScalarFilterRecord(
                id="fold0",
                created=datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0),
                day=date(2026, 11, 1),
                token=UUID("00000000-0000-0000-0000-0000000000f0"),
                amount=Decimal("1"),
                span=timedelta(hours=1),
                label="repeated",
                count=2,
                flag=True,
                vector=[1.0, 0.0],
            ),
            ScalarFilterRecord(
                id="after",
                created=datetime(2026, 11, 1, 3, 30, tzinfo=zone),
                day=date(2026, 11, 1),
                token=UUID("00000000-0000-0000-0000-0000000000f2"),
                amount=Decimal("1"),
                span=timedelta(hours=1),
                label="repeated",
                count=3,
                flag=True,
                vector=[1.0, 0.0],
            ),
        ],
        generate_vectors=False,
    )
    return collection


async def test_in_memory_repeated_hour_matches_by_instant_through_get() -> None:
    """Equality, inequality and membership on a repeated-hour instant name the stored record."""
    zone = _new_york_zone()
    collection = await _repeated_hour_collection(zone)
    fold = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)

    assert [record.id for record in await collection.get(filter=Filter("created", "eq", fold))] == ["fold"]
    assert [record.id for record in await collection.get(filter=Filter("created", "ne", fold))] == [
        "fold0",
        "after",
    ]
    assert [record.id for record in await collection.get(filter=Filter("created", "in", (fold,)))] == ["fold"]


async def test_in_memory_repeated_hour_matches_the_earlier_fold_through_get() -> None:
    """The first fold of the repeated hour keeps naming its own instant."""
    zone = _new_york_zone()
    collection = await _repeated_hour_collection(zone)
    fold0 = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)

    assert [record.id for record in await collection.get(filter=Filter("created", "eq", fold0))] == ["fold0"]
    assert [record.id for record in await collection.get(filter=Filter("created", "in", (fold0,)))] == ["fold0"]


async def test_in_memory_repeated_hour_matches_a_utc_equivalent_operand() -> None:
    """An aware operand at the same instant in another zone matches the record."""
    zone = _new_york_zone()
    collection = await _repeated_hour_collection(zone)
    utc_equivalent = datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)

    assert [record.id for record in await collection.get(filter=Filter("created", "eq", utc_equivalent))] == ["fold"]


async def test_in_memory_repeated_hour_matches_by_instant_through_search() -> None:
    """The vector search path applies the same instant semantics."""
    zone = _new_york_zone()
    collection = await _repeated_hour_collection(zone)
    fold = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)

    results = await collection.search(vector=[1.0, 0.0], filter=Filter("created", "eq", fold), top=10)

    assert [result["record"].id async for result in results] == ["fold"]


async def _scalar_amount_collection() -> InMemoryCollection[str, ScalarFilterRecord]:
    """Two records whose amounts and timestamps sort the other way round as text."""
    collection = InMemoryCollection(ScalarFilterRecord)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [
            ScalarFilterRecord(
                id="two",
                created=datetime(2026, 10, 16, 23, 0, tzinfo=timezone(timedelta(hours=2))),
                day=date(2026, 10, 16),
                token=UUID("00000000-0000-0000-0000-000000000002"),
                amount=Decimal("2"),
                span=timedelta(hours=2),
                label="small",
                count=2,
                flag=True,
                vector=[1.0, 0.0],
            ),
            ScalarFilterRecord(
                id="ten",
                created=datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc),
                day=date(2026, 10, 17),
                token=UUID("00000000-0000-0000-0000-000000000010"),
                amount=Decimal("10"),
                span=timedelta(hours=10),
                label="large",
                count=10,
                flag=True,
                vector=[0.0, 1.0],
            ),
        ],
        generate_vectors=False,
    )
    return collection


async def test_in_memory_ordered_filter_compares_decimals_numerically() -> None:
    """An ordered comparison on a decimal must compare numbers, not digits.

    The stored form of the two values sorts the other way round as text, so a
    comparison on the serialized form would pick the wrong record.
    """
    collection = await _scalar_amount_collection()

    matched = await collection.get(filter=Filter("amount", "gte", Decimal("10")))

    assert [record.id for record in matched] == ["ten"]


async def test_in_memory_filter_does_not_match_a_different_native_scalar() -> None:
    """A different value must still not match."""
    collection = await _scalar_filter_collection()

    matched = await collection.get(filter=Filter("created", "eq", datetime(2025, 1, 1, tzinfo=timezone.utc)))

    assert matched == []


async def test_in_memory_filter_does_not_match_a_different_decimal() -> None:
    """A different decimal must not match the stored one."""
    collection = await _scalar_amount_collection()

    matched = await collection.get(filter=Filter("amount", "eq", Decimal("2")))

    assert [record.id for record in matched] == ["two"]


async def test_in_memory_filter_matches_the_same_instant_written_in_another_offset() -> None:
    """The same instant written with another UTC offset is still the same value."""
    collection = await _scalar_filter_collection()
    value = datetime(2026, 10, 16, 3, 0, tzinfo=timezone(timedelta(hours=2)))

    matched = await collection.get(filter=Filter("created", "eq", value))

    assert [record.id for record in matched] == ["one"]


async def test_in_memory_ordered_filter_compares_timestamps_written_in_another_offset() -> None:
    """The order of two timestamps must not depend on their UTC offsets.

    The stored form of the earlier timestamp sorts after the later one as text,
    so a comparison on the serialized form would pick the wrong record.
    """
    collection = await _scalar_amount_collection()
    value = datetime(2026, 10, 16, 22, 0, tzinfo=timezone.utc)

    matched = await collection.get(filter=Filter("created", "gte", value))

    assert [record.id for record in matched] == ["ten"]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("created", "2026-10-16T01:00:00+00:00"),
        ("day", datetime(2026, 10, 16)),
        ("amount", 1.5),
        ("span", 7200),
        ("token", "00000000-0000-0000-0000-000000000001"),
    ],
)
async def test_in_memory_filter_rejects_an_operand_of_another_type(field_name: str, value: Any) -> None:
    """An operand that cannot be compared in the field's own type is rejected.

    The operand validator accepts every one of these operands, so without a
    rejection the filter would quietly match no record at all.
    """
    collection = await _scalar_filter_collection()

    with pytest.raises(TypeError, match="cannot compare field"):
        await collection.get(filter=Filter(field_name, "eq", value))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("label", datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)),
    ],
)
async def test_in_memory_filter_rejects_a_native_scalar_operand_for_another_field_type(
    field_name: str,
    value: Any,
) -> None:
    """A native scalar operand only fits the field that declares it."""
    collection = await _scalar_filter_collection()

    with pytest.raises(TypeError, match="cannot compare field"):
        await collection.get(filter=Filter(field_name, "eq", value))


@pytest.mark.parametrize(
    ("operator", "value"),
    [
        ("eq", Decimal("5")),
        ("gte", Decimal("5")),
        ("lte", Decimal("5")),
    ],
)
async def test_in_memory_numeric_operand_compares_exactly_with_a_native_numeric_field(
    operator: str,
    value: Any,
) -> None:
    """A numeric operand compares exactly with a field stored as a native number.

    ``5 == Decimal("5")`` and its ordering are exact in Python, and the issue
    lists integer filters among the comparisons that worked before.
    """
    collection = await _scalar_filter_collection()

    matched = await collection.get(filter=Filter("count", operator, value))

    assert [record.id for record in matched] == ["one"]


@pytest.mark.parametrize(
    ("operator", "value", "expected"),
    [
        ("eq", 2, ["two"]),
        ("gte", 10, ["ten"]),
        ("lte", 2, ["two"]),
    ],
)
async def test_in_memory_int_operand_compares_exactly_with_a_decimal_field(
    operator: str,
    value: Any,
    expected: list[str],
) -> None:
    """An int operand fits a Decimal field: the comparison is exact.

    The restore turns the stored text into a ``Decimal``, and ``Decimal``
    compares exactly with ``int`` in both equality and ordering.
    """
    collection = await _scalar_amount_collection()

    matched = await collection.get(filter=Filter("amount", operator, value))

    assert [record.id for record in matched] == expected


async def test_in_memory_search_rejects_an_operand_of_another_type() -> None:
    """The search path rejects the operands the get path rejects."""
    collection = await _scalar_filter_collection()

    with pytest.raises(TypeError, match="cannot compare field"):
        await collection.search(vector=[1.0, 0.0], filter=Filter("created", "eq", "2026-10-16"), top=10)


async def test_in_memory_filter_rejects_an_incompatible_operand_inside_a_collection() -> None:
    """Every operand of a collection filter is checked."""
    collection = await _scalar_filter_collection()
    value = datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)

    with pytest.raises(TypeError, match="cannot compare field"):
        await collection.get(filter=Filter("created", "in", (value, "2026-10-16")))
    with pytest.raises(TypeError, match="cannot compare field"):
        await collection.get(filter=Filter("created", "between", (value, "2026-10-17")))


async def test_in_memory_filter_rejects_an_incompatible_operand_inside_a_group() -> None:
    """Every operand of a filter group is checked."""
    collection = await _scalar_filter_collection()

    with pytest.raises(TypeError, match="cannot compare field"):
        await collection.get(
            filter=FilterGroup(
                "and",
                (Filter("label", "eq", "featured"), Filter("created", "eq", "2026-10-16")),
            )
        )


async def test_in_memory_filter_still_matches_a_collection_of_native_scalars() -> None:
    """A collection of operands that fit the field still matches."""
    collection = await _scalar_filter_collection()
    value = datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)

    matched = await collection.get(filter=Filter("created", "in", (value,)))

    assert [record.id for record in matched] == ["one"]


@vectorstoremodel(collection_name="time_filter_records")
@dataclass
class TimeFilterRecord:
    id: Annotated[str, VectorStoreField("key")]
    starts: Annotated[time, VectorStoreField("data")]
    vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=2)] = None


async def _time_filter_collection() -> InMemoryCollection[str, TimeFilterRecord]:
    collection = InMemoryCollection(TimeFilterRecord)
    await collection.ensure_collection_exists()
    await collection.upsert([TimeFilterRecord("one", time(12, 30, tzinfo=timezone.utc))], generate_vectors=False)
    return collection


async def test_in_memory_filter_matches_a_utc_time_stored_with_a_z_suffix() -> None:
    """A UTC time is stored with a trailing "Z" and must still match.

    ``time.fromisoformat`` accepts the "Z" suffix only from Python 3.11, so
    the restore normalizes it the way the datetime restore does.
    """
    collection = await _time_filter_collection()

    matched = await collection.get(filter=Filter("starts", "eq", time(12, 30, tzinfo=timezone.utc)))

    assert [record.id for record in matched] == ["one"]


async def test_in_memory_text_operator_compares_the_stored_scalar_string() -> None:
    """A text operator reads the stored string, not the restored scalar.

    The serialized timestamp is what the text operators have always compared
    these fields by.
    """
    collection = await _scalar_filter_collection()

    matched = await collection.get(filter=Filter("created", "starts_with", "2026-10-16T01"))

    assert [record.id for record in matched] == ["one"]


async def test_in_memory_group_mixes_a_text_operator_and_a_native_comparison() -> None:
    """One field can carry a text operator and a native comparison in a group.

    The two leaves need different forms of the stored value: the text operator
    reads the serialized string while the comparison restores the scalar.
    """
    collection = await _scalar_amount_collection()

    matched = await collection.get(
        filter=FilterGroup(
            "and",
            (
                Filter("created", "starts_with", "2026-10-17"),
                Filter("created", "gte", datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc)),
            ),
        )
    )

    assert [record.id for record in matched] == ["ten"]


async def _long_span_collection(span: timedelta) -> InMemoryCollection[str, ScalarFilterRecord]:
    collection = InMemoryCollection(ScalarFilterRecord)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [
            ScalarFilterRecord(
                id="long",
                created=datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc),
                day=date(2026, 10, 16),
                token=UUID("00000000-0000-0000-0000-000000000001"),
                amount=Decimal("1.5"),
                span=span,
                label="long",
                count=1,
                flag=True,
            )
        ],
        generate_vectors=False,
    )
    return collection


async def test_in_memory_restores_a_large_duration_exactly() -> None:
    """A microsecond inside a large duration survives the restore.

    Summing the duration through ``float`` loses this microsecond, so the
    equality would quietly match nothing.
    """
    collection = await _long_span_collection(timedelta(days=100_000, microseconds=1))

    matched = await collection.get(filter=Filter("span", "eq", timedelta(days=100_000, microseconds=1)))

    assert [record.id for record in matched] == ["long"]


async def test_in_memory_distinguishes_durations_a_microsecond_apart() -> None:
    """Two durations a microsecond apart must not collapse into one."""
    collection = await _long_span_collection(timedelta(days=100_000, microseconds=1))

    matched = await collection.get(filter=Filter("span", "eq", timedelta(days=100_000, microseconds=2)))

    assert matched == []


async def test_in_memory_restores_the_largest_duration_exactly() -> None:
    """``timedelta.max`` is restored, not rounded out of the type's range.

    A ``float`` of the total seconds rounds the stored duration past the
    largest span ``timedelta`` supports.
    """
    collection = await _long_span_collection(timedelta.max)

    matched = await collection.get(filter=Filter("span", "eq", timedelta.max))

    assert [record.id for record in matched] == ["long"]


@vectorstoremodel(collection_name="tag_filter_records")
@dataclass
class TagFilterRecord:
    id: Annotated[str, VectorStoreField("key")]
    tags: Annotated[list[UUID], VectorStoreField("data")]
    vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=2)] = None


async def _tag_filter_collection() -> InMemoryCollection[str, TagFilterRecord]:
    collection = InMemoryCollection(TagFilterRecord)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [TagFilterRecord("one", [UUID("00000000-0000-0000-0000-000000000001")])],
        generate_vectors=False,
    )
    return collection


async def test_in_memory_collection_field_rejects_a_native_element_operand() -> None:
    """A native element operand can never match the stored text elements.

    A ``list[UUID]`` field is stored as a list of strings, so a ``UUID``
    operand quietly matched nothing; it now fails loudly like the scalar case.
    """
    collection = await _tag_filter_collection()

    with pytest.raises(TypeError, match="cannot compare field"):
        await collection.get(filter=Filter("tags", "contains", UUID("00000000-0000-0000-0000-000000000001")))


async def test_in_memory_collection_field_still_matches_a_string_element_operand() -> None:
    """The stored form of the element keeps matching, as it did before."""
    collection = await _tag_filter_collection()

    matched = await collection.get(filter=Filter("tags", "contains", "00000000-0000-0000-0000-000000000001"))

    assert [record.id for record in matched] == ["one"]


async def test_in_memory_restores_a_duration_under_a_reduced_decimal_precision() -> None:
    """The caller's Decimal context must not change what a duration filter matches.

    The restore runs its arithmetic in an isolated context: a caller running
    inside ``localcontext(prec=6)`` gets the same records as at the default
    precision, and the caller's own context survives the call.
    """
    collection = await _scalar_filter_collection()
    default_prec = getcontext().prec

    with localcontext() as ctx:
        ctx.prec = 6
        matched = await collection.get(filter=Filter("span", "eq", timedelta(hours=2)))

        assert [record.id for record in matched] == ["one"]
        assert getcontext().prec == 6

    assert getcontext().prec == default_prec


@vectorstoremodel(collection_name="uuid_key_records")
@dataclass
class UUIDKeyRecord:
    id: Annotated[UUID, VectorStoreField("key")]
    name: Annotated[str, VectorStoreField("data")]
    vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=2)] = None


async def _uuid_key_collection() -> InMemoryCollection[str, UUIDKeyRecord]:
    collection = InMemoryCollection(UUIDKeyRecord)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [UUIDKeyRecord(UUID("00000000-0000-0000-0000-000000000001"), "one")],
        generate_vectors=False,
    )
    return collection


async def test_in_memory_uuid_key_field_accepts_a_canonical_string_operand() -> None:
    """A canonical string operand matches a UUID key field.

    Scoped tools address UUID keys through their canonical string form
    (``key_from_json``), so the operand normalizes to the field's own type
    for the compatibility check and the comparison.
    """
    collection = await _uuid_key_collection()

    matched = await collection.get(filter=Filter("id", "in", ("00000000-0000-0000-0000-000000000001",)))

    assert [record.id for record in matched] == [UUID("00000000-0000-0000-0000-000000000001")]


async def test_in_memory_uuid_key_field_matches_a_native_uuid_operand() -> None:
    """A native UUID operand keeps matching the restored key."""
    collection = await _uuid_key_collection()

    matched = await collection.get(filter=Filter("id", "eq", UUID("00000000-0000-0000-0000-000000000001")))

    assert [record.id for record in matched] == [UUID("00000000-0000-0000-0000-000000000001")]


async def test_in_memory_uuid_key_field_rejects_a_non_canonical_string_operand() -> None:
    """A string that is not a canonical UUID is still rejected loudly."""
    collection = await _uuid_key_collection()

    with pytest.raises(TypeError, match="cannot compare field"):
        await collection.get(filter=Filter("id", "in", ("not-a-uuid",)))


@pytest.mark.parametrize(
    ("operator", "operand"),
    [
        ("starts_with", "00000000-0000-0000-0000-000000000001"),
        ("ends_with", "00000000-0000-0000-0000-000000000001"),
        ("contains_text", "00000000-0000-0000-0000-000000000001"),
    ],
)
async def test_in_memory_uuid_key_text_operators_keep_the_canonical_string(
    operator: str,
    operand: str,
) -> None:
    """Text operators on a UUID key field compare the canonical string.

    Normalizing the operand to UUID would make the string comparison raise
    instead of matching.
    """
    collection = await _uuid_key_collection()

    matched = await collection.get(filter=Filter("id", operator, operand))

    assert [record.id for record in matched] == [UUID("00000000-0000-0000-0000-000000000001")]
