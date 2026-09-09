# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Annotated, Any, cast
from unittest.mock import AsyncMock

import pytest
from agent_framework import (
    Embedding,
    Filter,
    GeneratedEmbeddings,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    register_vectorstoremodel,
    vectorstoremodel,
)
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException
from bson import ObjectId
from pymongo import ReplaceOne
from pymongo.errors import OperationFailure

from agent_framework_mongodb import MongoDBCollection, MongoDBStore
from agent_framework_mongodb._vector_store import _BSON_INT64_MAX, _semantic_index_definition


def _ready_index(collection: MongoDBCollection[Any, Any], field_name: str) -> dict[str, Any]:
    field = collection.definition.try_get_vector_field(field_name)
    assert field is not None
    return {
        "name": collection._index_name(field),
        "type": "vectorSearch",
        "queryable": True,
        "status": "READY",
        "latestDefinition": collection._index_definition(field),
        "extraStatusMetadata": {"ignored": True},
    }


def test_model_validation_and_index_mapping(collection):
    assert collection._index_name(collection.definition.vector_fields[0]) == "text_vector_index"
    generated = collection._index_name(collection.definition.vector_fields[1])
    assert generated.startswith("af_dense_image_")
    first = collection._index_definition(collection.definition.vector_fields[0])
    assert first == {
        "fields": [
            {
                "type": "vector",
                "path": "dense_text",
                "numDimensions": 3,
                "similarity": "cosine",
            },
            {"type": "filter", "path": "_id"},
            {"type": "filter", "path": "number"},
            {"type": "filter", "path": "integer"},
            {"type": "filter", "path": "flag"},
        ]
    }


@pytest.mark.parametrize("field_type", ["data", "vector"])
def test_non_key_fields_cannot_use_reserved_id_storage_name(mongo_mocks, field_type):
    client, _, native_collection = mongo_mocks
    field = (
        VectorStoreField("data", name="value", type_="str", storage_name="_id")
        if field_type == "data"
        else VectorStoreField("vector", name="value", dimensions=2, storage_name="_id")
    )
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        field,
    ])
    with pytest.raises(ValueError, match="reserves storage name '_id'"):
        MongoDBCollection(
            dict,
            definition=definition,
            collection_name="reserved_id",
            async_client=client,
            database_name="vectors",
        )
    native_collection.bulk_write.assert_not_awaited()


def test_invalid_dimensions_rejected(mongo_mocks):
    client, _, native_collection = mongo_mocks
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="str"),
        VectorStoreField("vector", name="vector", dimensions=8193),
    ])
    with pytest.raises(ValueError, match="dimensions"):
        MongoDBCollection(
            dict,
            definition=definition,
            collection_name="test",
            async_client=client,
            database_name="vectors",
        )
    native_collection.create_search_index.assert_not_awaited()


def test_index_semantics_ignore_order_and_status_metadata(collection):
    expected = collection._index_definition(collection.definition.vector_fields[0])
    reordered = {"fields": list(reversed(expected["fields"]))}
    assert _semantic_index_definition(expected) == _semantic_index_definition(reordered)
    index = _ready_index(collection, "embedding")
    index["latestDefinition"] = reordered
    assert collection._validate_search_index(collection.definition.vector_fields[0], index)


def test_incompatible_index_rejected(collection):
    index = _ready_index(collection, "embedding")
    index["latestDefinition"]["fields"][0]["numDimensions"] = 42
    with pytest.raises(ValueError, match="does not match"):
        collection._validate_search_index(collection.definition.vector_fields[0], index)


async def test_create_collection_and_indexes_with_readiness_poll(collection, mongo_mocks):
    _, database, native_collection = mongo_mocks
    database.list_collection_names.side_effect = [[], ["test"]]
    ready_indexes = [_ready_index(collection, "embedding"), _ready_index(collection, "image")]
    collection._list_search_index = AsyncMock(side_effect=[None, ready_indexes[0], None, ready_indexes[1]])
    await collection.ensure_collection_exists(operation_options={"poll_interval": 0.001})
    database.create_collection.assert_awaited_once_with("test", check_exists=False)
    assert native_collection.create_search_index.await_count == 2
    models = [call.kwargs["model"].document for call in native_collection.create_search_index.await_args_list]
    assert [model["name"] for model in models] == [
        "text_vector_index",
        collection._index_name(collection.definition.vector_fields[1]),
    ]


async def test_collection_and_index_races_are_reconciled(collection, mongo_mocks):
    _, database, native_collection = mongo_mocks
    database.list_collection_names.side_effect = [[], ["test"]]
    database.create_collection.side_effect = OperationFailure("namespace exists", code=48)
    ready = _ready_index(collection, "embedding")
    collection.definition = VectorStoreCollectionDefinition(
        collection.definition.fields[:6] + (collection.definition.fields[6],)
    )
    collection._list_search_index = AsyncMock(side_effect=[None, ready, ready])
    native_collection.create_search_index.side_effect = OperationFailure("index exists", code=68)
    await collection.ensure_collection_exists(operation_options={"poll_interval": 0.001})
    native_collection.create_search_index.assert_awaited_once()


async def test_index_readiness_timeout_is_bounded(collection):
    collection.definition = VectorStoreCollectionDefinition(
        collection.definition.fields[:6] + (collection.definition.fields[6],)
    )
    collection._list_search_index = AsyncMock(
        return_value={
            **_ready_index(collection, "embedding"),
            "queryable": False,
            "status": "BUILDING",
        }
    )
    with pytest.raises(TimeoutError, match="not queryable"):
        await collection.ensure_collection_exists(operation_options={"index_timeout": 0.002, "poll_interval": 0.001})


async def test_index_terminal_failure_stops_polling(collection):
    field = collection.definition.vector_fields[0]
    collection._list_search_index = AsyncMock(
        return_value={
            **_ready_index(collection, "embedding"),
            "queryable": False,
            "status": "FAILED",
        }
    )
    with pytest.raises(ValueError, match="terminal status"):
        await collection._wait_for_search_index(field, timeout=1, poll_interval=0.001)


async def test_late_invalid_batch_has_no_write(collection, mongo_mocks, record):
    _, _, native_collection = mongo_mocks
    with pytest.raises(ValueError):
        await collection.upsert(
            [record(1), record(2, integer=2**63)],
            generate_vectors=False,
        )
    native_collection.bulk_write.assert_not_awaited()


@pytest.mark.parametrize("key", [True, 1.5, 2**63, "1", None])
async def test_strict_crud_keys_fail_before_io(collection, mongo_mocks, record, key):
    _, _, native_collection = mongo_mocks
    with pytest.raises((TypeError, ValueError)):
        await collection.upsert([record(1), record(key)], generate_vectors=False)
    with pytest.raises((TypeError, ValueError)):
        await collection.get([key])
    with pytest.raises(IntegrationException):
        await collection.delete([key])
    native_collection.bulk_write.assert_not_awaited()
    native_collection.find.assert_not_called()
    native_collection.delete_many.assert_not_awaited()


async def test_oversized_document_has_no_write(collection, mongo_mocks, record):
    _, _, native_collection = mongo_mocks
    with pytest.raises(ValueError, match="16 MiB"):
        await collection.upsert(
            [record(1), record(2, text="x" * (16 * 1024 * 1024))],
            generate_vectors=False,
        )
    native_collection.bulk_write.assert_not_awaited()


@pytest.mark.parametrize("vector", [[1, 2], [math.nan, 0, 0], [True, 0, 0], b"abc"])
async def test_invalid_vectors_fail_before_dispatch(collection, mongo_mocks, record, vector):
    _, _, native_collection = mongo_mocks
    with pytest.raises((TypeError, ValueError)):
        await collection.upsert([record(1), record(2, embedding=vector)], generate_vectors=False)
    native_collection.bulk_write.assert_not_awaited()


async def test_bulk_upsert_aliases_and_options(collection, mongo_mocks, record):
    _, _, native_collection = mongo_mocks
    records = [record(1), record(2)]
    assert await collection.upsert(
        records,
        generate_vectors=False,
        operation_options={"ordered": False, "bypass_document_validation": True},
    ) == [1, 2]
    requests = native_collection.bulk_write.await_args.args[0]
    assert len(requests) == 2 and all(isinstance(request, ReplaceOne) for request in requests)
    assert native_collection.bulk_write.await_args.kwargs == {
        "ordered": False,
        "bypass_document_validation": True,
    }
    replacement = requests[0]._doc
    assert replacement["_id"] == 1
    assert "document_key" not in replacement
    assert replacement["body"] == "hello"
    assert set(replacement) >= {"dense_text", "dense_image"}


async def test_unordered_duplicate_keys_rejected(collection, mongo_mocks, record):
    _, _, native_collection = mongo_mocks
    with pytest.raises(ValueError, match="duplicate keys"):
        await collection.upsert(
            [record(1), record(1, text="replacement")],
            generate_vectors=False,
            operation_options={"ordered": False},
        )
    native_collection.bulk_write.assert_not_awaited()


async def test_selective_embedding_generation(collection, mongo_mocks, record):
    _, _, native_collection = mongo_mocks
    generator = AsyncMock()
    generator.get_embeddings.return_value = GeneratedEmbeddings([Embedding(vector=[2.0, 0, 0])])
    collection.embedding_generator = generator
    value = record(1, embedding="source", image=[0, 1, 0])
    await collection.upsert([value], generate_vectors=["embedding"])
    generator.get_embeddings.assert_awaited_once_with(["source"], options={"dimensions": 3})
    replacement = native_collection.bulk_write.await_args.args[0][0]._doc
    assert replacement["dense_text"] == [2, 0, 0]
    assert replacement["dense_image"] == [0, 1, 0]
    assert value["embedding"] == "source"


async def test_generated_object_id_dict_crud_and_projection(mongo_mocks, cursor_factory):
    client, _, native_collection = mongo_mocks
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="ObjectId", is_auto_generated=True),
        VectorStoreField("data", name="text", type_="str"),
        VectorStoreField("vector", name="vector", dimensions=2),
    ])
    collection = MongoDBCollection(
        dict,
        definition=definition,
        collection_name="objects",
        async_client=client,
        database_name="vectors",
    )
    keys = await collection.upsert([{"text": "hello", "vector": [1, 0]}], generate_vectors=False)
    assert len(keys) == 1 and isinstance(keys[0], ObjectId)
    native_collection.find.return_value = cursor_factory([{"_id": keys[0], "text": "hello"}])
    assert await collection.get(keys) == [{"id": keys[0], "text": "hello"}]
    assert native_collection.find.call_args.kwargs["projection"] == {"vector": 0}
    await collection.delete(keys)
    native_collection.delete_many.assert_awaited_once_with({"_id": {"$in": keys}})


async def test_typed_object_id_requires_and_supports_custom_codec(mongo_mocks, cursor_factory):
    client, _, native_collection = mongo_mocks

    @dataclass
    class Document:
        id: ObjectId | None
        text: str
        vector: list[float] | None = None

    register_vectorstoremodel(
        Document,
        definition=VectorStoreCollectionDefinition([
            VectorStoreField("key", name="id", type_="ObjectId", is_auto_generated=True),
            VectorStoreField("data", name="text", type_="str"),
            VectorStoreField("vector", name="vector", dimensions=2),
        ]),
        encoder=lambda item: {"id": item.id, "text": item.text, "vector": item.vector},
        decoder=lambda item: Document(item["id"], item["text"], item.get("vector")),
    )
    collection = MongoDBCollection(
        Document,
        collection_name="typed_objects",
        async_client=client,
        database_name="vectors",
    )
    key = (await collection.upsert([Document(None, "hello", [1, 0])], generate_vectors=False))[0]
    native_collection.find.return_value = cursor_factory([{"_id": key, "text": "hello", "vector": [1.0, 0.0]}])
    assert (await collection.get([key], include_vectors=True))[0] == Document(key, "hello", [1.0, 0.0])


async def test_default_typed_object_id_codec_fails_before_write(mongo_mocks):
    client, _, native_collection = mongo_mocks

    @vectorstoremodel
    @dataclass
    class Document:
        id: Annotated[ObjectId, VectorStoreField("key")]
        text: Annotated[str, VectorStoreField("data")]

    collection = MongoDBCollection(
        Document,
        collection_name="default_objects",
        async_client=client,
        database_name="vectors",
    )
    with pytest.raises(NotImplementedError):
        await collection.upsert([Document(ObjectId(), "hello")], generate_vectors=False)
    native_collection.bulk_write.assert_not_awaited()


async def test_get_preserves_key_order_and_vector_projection(collection, mongo_mocks, cursor_factory):
    _, _, native_collection = mongo_mocks
    native_collection.find.return_value = cursor_factory([
        {
            "_id": 2,
            "body": "two",
            "number": 2.0,
            "integer": 2,
            "flag": True,
            "tags": [],
        },
        {
            "_id": 1,
            "body": "one",
            "number": 1.0,
            "integer": 1,
            "flag": False,
            "tags": [],
        },
    ])
    values = await collection.get([1, 2])
    assert [value["id"] for value in values] == [1, 2]
    assert native_collection.find.call_args.kwargs["projection"] == {"dense_text": 0, "dense_image": 0}


async def test_filtered_get_uses_native_sort_skip_limit(collection, mongo_mocks, cursor_factory):
    _, _, native_collection = mongo_mocks
    cursor = cursor_factory([])
    native_collection.find.return_value = cursor
    await collection.get(filter=Filter("text", "eq", "hello"), order_by={"number": False}, skip=7, top=4)
    assert cursor.sort_spec == [("number", -1), ("_id", 1)]
    assert cursor.skip_count == 7 and cursor.limit_count == 4


async def test_search_ann_default_pipeline_and_threshold_order(collection, mongo_mocks, cursor_factory):
    _, _, native_collection = mongo_mocks
    native_collection.aggregate.return_value = cursor_factory([])
    await collection._inner_search(
        search_type="vector",
        vector=[1, 0, 0],
        filter=Filter("integer", "eq", 1),
        top=3,
        skip=2,
        score_threshold=0.75,
    )
    pipeline = native_collection.aggregate.await_args.args[0]
    assert pipeline[0] == {
        "$vectorSearch": {
            "index": "text_vector_index",
            "path": "dense_text",
            "queryVector": [1.0, 0.0, 0.0],
            "limit": 5,
            "numCandidates": 100,
            "filter": {"integer": {"$eq": 1}},
        }
    }
    assert [next(iter(stage)) for stage in pipeline] == [
        "$vectorSearch",
        "$set",
        "$match",
        "$skip",
        "$limit",
        "$project",
    ]


async def test_search_exact_omits_num_candidates(collection, mongo_mocks, cursor_factory):
    _, _, native_collection = mongo_mocks
    native_collection.aggregate.return_value = cursor_factory([])
    await collection._inner_search(
        search_type="vector",
        vector=[1, 0, 0],
        top=3,
        skip=1,
        operation_options={"exact": True},
    )
    search = native_collection.aggregate.await_args.args[0][0]["$vectorSearch"]
    assert search["exact"] is True
    assert "numCandidates" not in search


async def test_search_explicit_max_num_candidates(collection, mongo_mocks, cursor_factory):
    _, _, native_collection = mongo_mocks
    native_collection.aggregate.return_value = cursor_factory([])
    window = 501
    await collection._inner_search(
        search_type="vector",
        vector=[1, 0, 0],
        top=window,
        operation_options={"num_candidates": 10_000},
    )
    search = native_collection.aggregate.await_args.args[0][0]["$vectorSearch"]
    assert search["limit"] == window and search["numCandidates"] == 10_000


async def test_search_default_num_candidates_is_capped(collection, mongo_mocks, cursor_factory):
    _, _, native_collection = mongo_mocks
    native_collection.aggregate.return_value = cursor_factory([])
    await collection._inner_search(search_type="vector", vector=[1, 0, 0], top=501)
    search = native_collection.aggregate.await_args.args[0][0]["$vectorSearch"]
    assert search["limit"] == 501 and search["numCandidates"] == 10_000


async def test_search_exact_allows_large_representable_window(collection, mongo_mocks, cursor_factory):
    _, _, native_collection = mongo_mocks
    native_collection.aggregate.return_value = cursor_factory([])
    window = 2**55
    await collection._inner_search(
        search_type="vector",
        vector=[1, 0, 0],
        top=window,
        operation_options={"exact": True},
    )
    search = native_collection.aggregate.await_args.args[0][0]["$vectorSearch"]
    assert search["limit"] == window and search["exact"] is True
    assert "numCandidates" not in search


async def test_zero_top_search_validates_but_does_not_aggregate(collection, mongo_mocks):
    _, _, native_collection = mongo_mocks
    results = await collection._inner_search(
        search_type="vector",
        vector=[1, 0, 0],
        top=0,
        operation_options={"exact": True},
    )
    assert [item async for item in results] == []
    native_collection.aggregate.assert_not_awaited()


@pytest.mark.parametrize(
    ("top", "skip", "options", "message"),
    [
        (3, 0, {"exact": True, "num_candidates": 60}, "cannot be supplied"),
        (3, 0, {"exact": True, "num_candidates": None}, "cannot be supplied"),
        (3, 2, {"num_candidates": 4}, "greater than or equal"),
        (3, 0, {"num_candidates": None}, "signed 64-bit"),
        (3, 0, {"num_candidates": 0}, "between 1 and 10000"),
        (3, 0, {"num_candidates": 10_001}, "between 1 and 10000"),
        (10_001, 0, {}, "at most 10000"),
        (_BSON_INT64_MAX, 1, {"exact": True}, "signed 64-bit"),
    ],
)
async def test_search_window_validation_before_aggregation(collection, mongo_mocks, top, skip, options, message):
    _, _, native_collection = mongo_mocks
    with pytest.raises(ValueError, match=message):
        await collection._inner_search(
            search_type="vector",
            vector=[1, 0, 0],
            top=top,
            skip=skip,
            operation_options=options,
        )
    native_collection.aggregate.assert_not_awaited()


async def test_search_result_score_and_record(collection):
    key = 1
    result = {
        "_id": key,
        "body": "hello",
        "number": 1.0,
        "integer": 1,
        "flag": True,
        "tags": [],
        "__af_vector_search_score": 0.9,
    }
    assert collection._get_score_from_result(result) == 0.9
    assert collection._get_record_from_result(result) == result
    with pytest.raises(IntegrationInvalidResponseException):
        collection._get_score_from_result({**result, "__af_vector_search_score": math.nan})


async def test_store_lifecycle(mongo_mocks, definition):
    client, database, _ = mongo_mocks
    store = MongoDBStore(async_client=client, database_name="vectors")
    database.list_collection_names.side_effect = [["one", "two"], ["one"], ["one"], []]
    assert await store.list_collection_names() == ["one", "two"]
    assert await store.collection_exists("one")
    await store.ensure_collection_deleted("one")
    database.drop_collection.assert_awaited_once_with("one")
    await store.ensure_collection_deleted("missing")
    collection = store.get_collection(dict, definition=definition, collection_name="test")
    assert collection.async_client is client
    await store.close()
    cast(AsyncMock, client.close).assert_not_awaited()
