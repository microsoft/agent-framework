# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import ast
import inspect
import math
import warnings
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, cast

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
