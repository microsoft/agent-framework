# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import math
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from agent_framework import Filter, FilterGroup, VectorStoreCollectionDefinition
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException
from bson import ObjectId
from pymongo.errors import OperationFailure, PyMongoError

from agent_framework_azure_documentdb import AzureDocumentDBCollection, AzureDocumentDBStore
from agent_framework_azure_documentdb._vector_store import (
    _data_index_spec,
    _FilterCompiler,
    _matching_index,
    _vector_index_spec,
)


class AsyncCursor:
    def __init__(self, values: Sequence[dict[str, Any]]) -> None:
        self.values = list(values)
        self.skip_value = 0
        self.limit_value: int | None = None

    def skip(self, value: int) -> AsyncCursor:
        self.skip_value = value
        return self

    def limit(self, value: int) -> AsyncCursor:
        self.limit_value = value
        return self

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        async def iterate() -> AsyncIterator[dict[str, Any]]:
            end = None if self.limit_value is None else self.skip_value + self.limit_value
            for value in self.values[self.skip_value : end]:
                yield value

        return iterate()


def test_model_supports_multiple_vectors_and_aliases(definition_factory, pymongo_objects):
    connector = AzureDocumentDBCollection(
        dict,
        definition=definition_factory(second_vector=True),
        collection=pymongo_objects[2],
    )
    assert [field.storage_name for field in connector._fields[-2:]] == ["contentVector", "titleVector"]


def test_reserved_score_alias_rejected(definition_factory, pymongo_objects):
    definition = definition_factory()
    fields = [
        replace(field, storage_name="_af_documentdb_score" if field.name == "text" else field.storage_name)
        for field in definition.fields
    ]
    with pytest.raises(ValueError, match="reserved"):
        AzureDocumentDBCollection(
            dict,
            definition=VectorStoreCollectionDefinition(fields, collection_name="documents"),
            collection=pymongo_objects[2],
        )


@pytest.mark.parametrize(
    "options",
    [
        {"generated": True},
        {"key_type": "UUID"},
        {"dimensions": 0},
        {"dimensions": 2001},
        {"dimensions": True},
        {"index_kind": "flat"},
        {"distance_function": "cosine_distance"},
        {"distance_function": "hamming"},
        {"annotations": {"azure_documentdb.unknown": 1}},
        {"index_kind": "ivf_flat", "annotations": {"azure_documentdb.num_lists": 0}},
        {"index_kind": "hnsw", "annotations": {"azure_documentdb.m": 101}},
        {
            "index_kind": "hnsw",
            "annotations": {"azure_documentdb.m": 40, "azure_documentdb.ef_construction": 64},
        },
        {"index_kind": "disk_ann", "annotations": {"azure_documentdb.max_degree": 19}},
        {"index_kind": "disk_ann", "annotations": {"azure_documentdb.l_build": 501}},
    ],
)
def test_model_capabilities_rejected_before_io(definition_factory, pymongo_objects, options):
    with pytest.raises((ValueError, NotImplementedError)):
        AzureDocumentDBCollection(
            dict,
            definition=definition_factory(**options),
            collection=pymongo_objects[2],
        )


def test_key_and_data_storage_names_are_mapped(definition_factory, pymongo_objects, record_factory):
    connector = AzureDocumentDBCollection(
        dict,
        definition=definition_factory(),
        collection=pymongo_objects[2],
    )
    stored = connector._serialize_dicts_to_store_models([connector._serialize_record_to_dict(record_factory())])[0]
    assert stored["_id"] == "one"
    assert "record_id" not in stored
    assert stored["body"] == "Azure DocumentDB"
    restored = connector._deserialize_store_models_to_dicts([stored])[0]
    assert restored["record_id"] == "one"


@pytest.mark.parametrize("key", [True, 1.5, object(), 2**63, -(2**63) - 1, "x" * 2049])
async def test_keys_are_strict_before_io(collection, pymongo_objects, record_factory, key):
    with pytest.raises((TypeError, ValueError, NotImplementedError)):
        await collection.upsert([record_factory(cast(Any, key))], generate_vectors=False)
    with pytest.raises((TypeError, ValueError)):
        await collection.get([cast(Any, key)])
    pymongo_objects[2].bulk_write.assert_not_awaited()
    pymongo_objects[2].find.assert_not_called()


def test_object_id_response_is_not_implicitly_encoded(collection):
    with pytest.raises(TypeError, match="strings or signed"):
        collection._deserialize_store_models_to_dicts([{"_id": ObjectId()}])


@pytest.mark.parametrize(
    "field,value",
    [
        ("number", True),
        ("number", 2**63),
        ("ratio", float("nan")),
        ("flag", 1),
        ("tags", ("tuple",)),
        ("text", b"bytes"),
    ],
)
async def test_record_values_are_type_checked_before_io(
    collection,
    pymongo_objects,
    record_factory,
    field,
    value,
):
    with pytest.raises((TypeError, ValueError)):
        await collection.upsert([record_factory(**{field: value})], generate_vectors=False)
    pymongo_objects[2].bulk_write.assert_not_awaited()


@pytest.mark.parametrize(
    "vector",
    [
        "not-a-vector",
        b"bytes",
        [1, True, 0],
        [1, "0", 0],
        [1, float("nan"), 0],
        [1, 2**63, 0],
    ],
)
async def test_vectors_are_validated_before_io(collection, pymongo_objects, record_factory, vector):
    with pytest.raises((TypeError, ValueError)):
        await collection.upsert([record_factory(embedding=vector)], generate_vectors=False)
    pymongo_objects[2].bulk_write.assert_not_awaited()


async def test_late_invalid_batch_performs_no_io(collection, pymongo_objects, record_factory):
    with pytest.raises(TypeError):
        await collection.upsert(
            [record_factory("valid"), record_factory("invalid", embedding=[1, "invalid", 0])],
            generate_vectors=False,
        )
    pymongo_objects[2].bulk_write.assert_not_awaited()


async def test_document_size_preflight_performs_no_io(collection, pymongo_objects, record_factory):
    with (
        patch("agent_framework_azure_documentdb._vector_store._MAX_DOCUMENT_BYTES", 100),
        pytest.raises(ValueError, match="encoded BSON"),
    ):
        await collection.upsert([record_factory(text="x" * 1_000)], generate_vectors=False)
    pymongo_objects[2].bulk_write.assert_not_awaited()


async def test_upsert_chunks_and_reports_partial_writes(collection, pymongo_objects, record_factory):
    pymongo_objects[2].bulk_write.side_effect = [None, PyMongoError("failed")]
    with (
        patch("agent_framework_azure_documentdb._vector_store._MAX_WRITES_PER_BATCH", 2),
        pytest.raises(IntegrationException, match="2 records in earlier batches"),
    ):
        await collection.upsert(
            [record_factory(str(index)) for index in range(3)],
            generate_vectors=False,
        )
    assert pymongo_objects[2].bulk_write.await_count == 2


async def test_upsert_preserves_order_and_duplicate_keys(collection, pymongo_objects, record_factory):
    keys = await collection.upsert(
        [record_factory("same"), record_factory("same")],
        generate_vectors=False,
    )
    assert keys == ["same", "same"]
    requests = pymongo_objects[2].bulk_write.call_args.args[0]
    assert len(requests) == 2


@pytest.mark.parametrize(
    "expression,expected",
    [
        (Filter("category", "eq", "database"), {"category": {"$eq": "database"}}),
        (
            Filter("category", "ne", "database"),
            {"$and": [{"category": {"$exists": True}}, {"category": {"$ne": "database"}}]},
        ),
        (
            Filter("category", "is_null"),
            {"$and": [{"category": {"$exists": True}}, {"category": {"$eq": None}}]},
        ),
        (
            Filter("category", "is_not_null"),
            {"$and": [{"category": {"$exists": True}}, {"category": {"$ne": None}}]},
        ),
        (Filter("category", "exists"), {"category": {"$exists": True}}),
        (Filter("number", "between", [1, 3]), {"number": {"$gte": 1, "$lte": 3}}),
        (
            Filter("number", "not_in", [1, 2]),
            {
                "$and": [
                    {"number": {"$exists": True}},
                    {"number": {"$ne": None}},
                    {"number": {"$nin": [1, 2]}},
                ]
            },
        ),
        (
            Filter("tags", "contains", "azure"),
            {
                "$and": [
                    {"tags": {"$exists": True}},
                    {"tags": {"$ne": None}},
                    {"tags": {"$in": ["azure"]}},
                ]
            },
        ),
        (
            Filter("tags", "contains_all", ["azure", 1]),
            {
                "$and": [
                    {"tags": {"$exists": True}},
                    {"tags": {"$ne": None}},
                    {"tags": {"$all": ["azure", 1]}},
                ]
            },
        ),
    ],
)
def test_filter_compilation_uses_mongo_wire_operators(collection, expression, expected):
    assert collection._prepare_filter(expression) == expected
    assert "$neq" not in repr(expected)


def test_filter_groups_and_values_remain_bson_documents(collection):
    payload = "'; drop collection documents; --"
    expression = FilterGroup(
        "and",
        [
            Filter("category", "eq", payload),
            FilterGroup("not", [Filter("flag", "eq", False)]),
        ],
    )
    assert collection._prepare_filter(expression) == {
        "$and": [
            {"category": {"$eq": payload}},
            {"$nor": [{"flag": {"$eq": False}}]},
        ]
    }


def test_filter_bson_size_is_checked_before_io(collection):
    with (
        patch("agent_framework_azure_documentdb._vector_store._MAX_DOCUMENT_BYTES", 100),
        pytest.raises(ValueError, match="filters cannot exceed"),
    ):
        collection._prepare_filter(Filter("category", "eq", "x" * 1_000))


@pytest.mark.parametrize(
    "expression,error",
    [
        (Filter("text", "eq", "not-indexed"), NotImplementedError),
        (Filter("embedding", "is_null"), NotImplementedError),
        (Filter("category.nested", "eq", "x"), NotImplementedError),
        (Filter("category", "contains_text", "x"), NotImplementedError),
        (Filter("category", "starts_with", "x"), NotImplementedError),
        (Filter("category", "azure_documentdb.regex", "^x"), NotImplementedError),
        (Filter("tags", "contains", ["nested"]), NotImplementedError),
        (Filter("tags", "in", [["azure"]]), NotImplementedError),
        (Filter("flag", "gt", True), NotImplementedError),
    ],
)
def test_unsupported_filters_fail_before_io(collection, expression, error):
    with pytest.raises(error):
        collection._prepare_filter(expression)


def test_empty_membership_semantics(collection):
    assert collection._prepare_filter(Filter("number", "in", [])) == {"_id": {"$exists": False}}
    assert collection._prepare_filter(Filter("number", "not_in", [])) == {
        "$and": [{"number": {"$exists": True}}, {"number": {"$ne": None}}]
    }
    assert collection._prepare_filter(Filter("tags", "contains_any", [])) == {"_id": {"$exists": False}}
    assert collection._prepare_filter(Filter("tags", "contains_all", [])) == {
        "$and": [{"tags": {"$exists": True}}, {"tags": {"$ne": None}}]
    }


def test_filter_type_mismatches_preserve_bool_number_distinction(collection):
    assert collection._prepare_filter(Filter("number", "eq", True)) == {"_id": {"$exists": False}}
    assert collection._prepare_filter(Filter("flag", "eq", 1)) == {"_id": {"$exists": False}}
    assert collection._prepare_filter(Filter("number", "ne", True)) == {"number": {"$exists": True}}


async def test_filtered_get_uses_prepared_filter_and_server_paging(collection, pymongo_objects):
    cursor = AsyncCursor([
        {"_id": "zero", "body": "0", "category": "database", "number": 0, "ratio": 0.0, "flag": True, "tags": []},
        {"_id": "one", "body": "1", "category": "database", "number": 1, "ratio": 1.0, "flag": True, "tags": []},
        {"_id": "two", "body": "2", "category": "database", "number": 2, "ratio": 2.0, "flag": True, "tags": []},
    ])
    pymongo_objects[2].find.return_value = cursor
    records = await collection.get(filter=Filter("category", "eq", "database"), skip=1, top=1)
    assert [record["id"] for record in records] == ["one"]
    assert pymongo_objects[2].find.call_args.args[0] == {"category": {"$eq": "database"}}
    assert cursor.skip_value == 1 and cursor.limit_value == 1


async def test_key_get_preserves_input_order_and_omits_missing(collection, pymongo_objects):
    pymongo_objects[2].find.return_value = AsyncCursor([
        {"_id": "two", "body": "2", "category": "db", "number": 2, "ratio": 2.0, "flag": True, "tags": []},
        {"_id": "one", "body": "1", "category": "db", "number": 1, "ratio": 1.0, "flag": True, "tags": []},
    ])
    records = await collection.get(["one", "missing", "two", "one"])
    assert [record["id"] for record in records] == ["one", "two", "one"]


async def test_empty_key_batches_perform_no_io(collection, pymongo_objects):
    assert await collection.get([]) == []
    await collection.delete([])
    pymongo_objects[2].find.assert_not_called()
    pymongo_objects[2].delete_many.assert_not_awaited()


async def test_delete_preflights_all_keys_before_io(collection, pymongo_objects):
    with pytest.raises(IntegrationException):
        await collection.delete(["valid", cast(Any, True)])
    pymongo_objects[2].delete_many.assert_not_awaited()


async def test_delete_reports_partial_batches(collection, pymongo_objects):
    pymongo_objects[2].delete_many.side_effect = [None, PyMongoError("failed")]
    with (
        patch("agent_framework_azure_documentdb._vector_store._KEY_BATCH_SIZE", 2),
        pytest.raises(IntegrationException, match="2 keys in earlier batches"),
    ):
        await collection.delete(["one", "two", "three"])


async def test_search_pipeline_threshold_before_paging_and_vector_projection(
    collection,
    pymongo_objects,
):
    pymongo_objects[2].aggregate.return_value = AsyncCursor([
        {
            "_id": "one",
            "body": "Azure",
            "category": "database",
            "number": 1,
            "ratio": 1.0,
            "flag": True,
            "tags": [],
            "_af_documentdb_score": 0.9,
        }
    ])
    results = await collection.search(
        vector=[1, 0, 0],
        filter=Filter("category", "eq", "database"),
        score_threshold=0.8,
        top=2,
        skip=1,
        operation_options={"k": 10, "n_probes": 1, "max_time_ms": 5000},
    )
    pipeline = pymongo_objects[2].aggregate.call_args.args[0]
    assert pipeline[0] == {
        "$search": {
            "cosmosSearch": {
                "path": "contentVector",
                "vector": [1, 0, 0],
                "k": 10,
                "nProbes": 1,
                "filter": {"category": {"$eq": "database"}},
            }
        }
    }
    assert pipeline[1]["$project"]["_af_documentdb_score"] == {"$meta": "searchScore"}
    assert "contentVector" not in pipeline[1]["$project"]
    assert pipeline[2] == {"$match": {"_af_documentdb_score": {"$gte": 0.8}}}
    assert pipeline[3:] == [{"$skip": 1}, {"$limit": 2}]
    assert pymongo_objects[2].aggregate.call_args.kwargs == {"maxTimeMS": 5000}
    assert results.metadata is not None and results.metadata["candidate_window"] == 10
    responses = [response async for response in results]
    assert len(responses) == 1 and responses[0]["score"] == 0.9
    assert responses[0]["record"]["id"] == "one"


async def test_empty_search_results_are_supported(collection, pymongo_objects):
    results = await collection.search(vector=[1, 0, 0])
    assert [result async for result in results] == []


@pytest.mark.parametrize(
    "definition_options,operation_options",
    [
        ({"index_kind": "ivf_flat"}, {"ef_search": 10}),
        ({"index_kind": "ivf_flat"}, {"n_probes": 2}),
        ({"index_kind": "hnsw"}, {"n_probes": 1}),
        ({"index_kind": "disk_ann"}, {"ef_search": 40}),
        ({"index_kind": "disk_ann"}, {"k": 1001}),
        ({"index_kind": "disk_ann"}, {"k": 50, "l_search": 40}),
        ({"index_kind": "disk_ann"}, {"l_search": 9}),
    ],
)
async def test_search_option_bounds_fail_before_io(
    definition_factory,
    pymongo_objects,
    definition_options,
    operation_options,
):
    connector = AzureDocumentDBCollection(
        dict,
        definition=definition_factory(**definition_options),
        collection=pymongo_objects[2],
    )
    with pytest.raises(ValueError):
        await connector.search(vector=[1, 0, 0], operation_options=operation_options)
    pymongo_objects[2].aggregate.assert_not_awaited()


async def test_hnsw_and_diskann_search_options_use_service_names(definition_factory, pymongo_objects):
    hnsw = AzureDocumentDBCollection(
        dict,
        definition=definition_factory(index_kind="hnsw"),
        collection=pymongo_objects[2],
    )
    await hnsw.search(vector=[1, 0, 0], operation_options={"ef_search": 75})
    assert pymongo_objects[2].aggregate.call_args.args[0][0]["$search"]["cosmosSearch"]["efSearch"] == 75

    diskann = AzureDocumentDBCollection(
        dict,
        definition=definition_factory(index_kind="disk_ann"),
        collection=pymongo_objects[2],
    )
    await diskann.search(vector=[1, 0, 0], operation_options={"l_search": 80})
    assert pymongo_objects[2].aggregate.call_args.args[0][0]["$search"]["cosmosSearch"]["lSearch"] == 80


def test_index_specs_use_documentdb_commands(definition_factory):
    definition = definition_factory(
        index_kind="hnsw",
        distance_function="dot_prod",
        annotations={"azure_documentdb.m": 12, "azure_documentdb.ef_construction": 48},
    )
    vector_spec = _vector_index_spec("documents", definition.vector_fields[0])
    assert vector_spec["key"] == {"contentVector": "cosmosSearch"}
    assert vector_spec["cosmosSearchOptions"] == {
        "kind": "vector-hnsw",
        "dimensions": 3,
        "similarity": "IP",
        "m": 12,
        "efConstruction": 48,
    }
    assert _data_index_spec("documents", definition.data_fields[1])["key"] == {"category": 1}


def test_index_compatibility_canonicalizes_documented_defaults(definition_factory):
    expected = _vector_index_spec(
        "documents",
        definition_factory(index_kind="hnsw").vector_fields[0],
    )
    existing: list[dict[str, Any]] = [
        {
            "name": "administrator_name",
            "key": {"contentVector": "cosmosSearch"},
            "cosmosSearch": {
                "kind": "vector-hnsw",
                "dimensions": 3,
                "similarity": "cos",
            },
        }
    ]
    assert _matching_index(existing, expected)
    cast(dict[str, Any], existing[0]["cosmosSearch"])["m"] = 32
    with pytest.raises(ValueError, match="incompatible"):
        _matching_index(existing, expected)


def test_filter_index_compatibility_rejects_semantic_options(definition_factory):
    expected = _data_index_spec("documents", definition_factory().data_fields[1])
    assert _matching_index([{"name": "existing", "key": {"category": 1}}], expected)
    for option in (
        {"unique": True},
        {"sparse": True},
        {"partialFilterExpression": {"category": {"$exists": True}}},
        {"expireAfterSeconds": 60},
        {"collation": {"locale": "en"}},
    ):
        with pytest.raises(ValueError, match="incompatible options"):
            _matching_index([{"name": "existing", "key": {"category": 1}, **option}], expected)


async def test_ensure_index_command_and_narrow_race_revalidation(
    collection,
    pymongo_objects,
    definition_factory,
):
    expected = _vector_index_spec("documents", definition_factory().vector_fields[0])
    existing = {
        "name": expected["name"],
        "key": expected["key"],
        "cosmosSearch": expected["cosmosSearchOptions"],
    }
    pymongo_objects[2].list_indexes.side_effect = [
        AsyncCursor([{"name": "_id_", "key": {"_id": 1}}]),
        AsyncCursor([{"name": "_id_", "key": {"_id": 1}}, existing]),
    ]
    pymongo_objects[1].command.side_effect = OperationFailure(
        "index raced",
        code=85,
        details={"codeName": "IndexOptionsConflict"},
    )
    await collection._ensure_index(expected, max_time_ms=5000)
    assert pymongo_objects[1].command.call_args.args[0] == {
        "createIndexes": "documents",
        "indexes": [expected],
        "maxTimeMS": 5000,
    }


async def test_unrelated_index_failure_is_not_suppressed(
    collection,
    pymongo_objects,
    definition_factory,
):
    expected = _vector_index_spec("documents", definition_factory().vector_fields[0])
    pymongo_objects[1].command.side_effect = OperationFailure("forbidden", code=13)
    with pytest.raises(OperationFailure):
        await collection._ensure_index(expected, max_time_ms=None)


async def test_ensure_collection_reconciles_each_vector_and_filter_index(
    definition_factory,
    pymongo_objects,
):
    connector = AzureDocumentDBCollection(
        dict,
        definition=definition_factory(second_vector=True),
        collection=pymongo_objects[2],
    )
    with patch.object(connector, "_ensure_index", new_callable=AsyncMock) as ensure:
        await connector.ensure_collection_exists()
    specs = [call.args[0] for call in ensure.call_args_list]
    assert [spec["key"] for spec in specs if "cosmosSearchOptions" in spec] == [
        {"contentVector": "cosmosSearch"},
        {"titleVector": "cosmosSearch"},
    ]
    assert {"category": 1} in [spec["key"] for spec in specs]


async def test_incompatible_existing_index_is_not_replaced(
    collection,
    pymongo_objects,
    definition_factory,
):
    expected = _vector_index_spec("documents", definition_factory().vector_fields[0])
    pymongo_objects[2].list_indexes.return_value = AsyncCursor([
        {
            "name": "existing",
            "key": expected["key"],
            "cosmosSearch": {
                **expected["cosmosSearchOptions"],
                "dimensions": 4,
            },
        }
    ])
    with pytest.raises(ValueError, match="incompatible"):
        await collection._ensure_index(expected, max_time_ms=None)
    pymongo_objects[1].command.assert_not_awaited()


async def test_store_lifecycle_is_database_scoped(definition_factory, pymongo_objects):
    store = AzureDocumentDBStore(database=pymongo_objects[1])
    assert await store.list_collection_names() == ["documents"]
    assert await store.collection_exists("documents")
    await store.ensure_collection_deleted("documents")
    pymongo_objects[1].drop_collection.assert_awaited_once_with("documents")


async def test_invalid_search_result_is_reported_during_iteration(collection, pymongo_objects):
    pymongo_objects[2].aggregate.return_value = AsyncCursor([
        {"_id": "one", "body": "text", "category": "db", "number": 1, "ratio": 1.0, "flag": True, "tags": []}
    ])
    results = await collection.search(vector=[1, 0, 0])
    with pytest.raises(IntegrationInvalidResponseException, match="searchScore"):
        _ = [result async for result in results]


def test_filter_compiler_calls_are_isolated(definition_factory):
    definition = definition_factory()
    compiler = _FilterCompiler(definition.fields, definition)
    first = compiler.compile(Filter("number", "eq", 1))
    second = compiler.compile(Filter("number", "eq", 2))
    assert first == {"number": {"$eq": 1}}
    assert second == {"number": {"$eq": 2}}


@pytest.mark.parametrize("score", [True, float("nan"), float("inf"), "0.5"])
async def test_invalid_native_scores_rejected(collection, pymongo_objects, score):
    pymongo_objects[2].aggregate.return_value = AsyncCursor([
        {
            "_id": "one",
            "body": "text",
            "category": "db",
            "number": 1,
            "ratio": 1.0,
            "flag": True,
            "tags": [],
            "_af_documentdb_score": score,
        }
    ])
    results = await collection.search(vector=[1, 0, 0])
    with pytest.raises(IntegrationInvalidResponseException):
        _ = [result async for result in results]


def test_score_threshold_requires_finite_number(collection):
    for threshold in (True, float("nan"), float("inf"), "0.5"):
        with pytest.raises(IntegrationInvalidResponseException):
            collection._get_score_from_result({"_af_documentdb_score": threshold})
    assert math.isclose(collection._get_score_from_result({"_af_documentdb_score": 0.5}), 0.5)
