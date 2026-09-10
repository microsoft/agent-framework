# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Annotated
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from agent_framework import (
    Embedding,
    Filter,
    GeneratedEmbeddings,
    SecretString,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    register_vectorstoremodel,
    vectorstoremodel,
)
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException
from grpc import StatusCode
from grpc.aio import AioRpcError, Metadata
from httpx import Headers
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from agent_framework_qdrant import QdrantCollection, QdrantStore


async def test_lifecycle_crud_aliases_vectors(collection_factory, client, record):
    collection = collection_factory()
    store = QdrantStore(async_client=client)
    assert not await collection.collection_exists()
    assert await collection.get([]) == []
    assert await collection.upsert([], generate_vectors=False) == []
    await collection.delete([])
    await collection.ensure_collection_deleted()
    await collection.ensure_collection_exists()
    await collection.ensure_collection_exists()
    assert await store.collection_exists(collection.collection_name)
    assert collection.collection_name in await store.list_collection_names()
    assert await collection.get() == []
    assert [item async for item in await collection.search(vector=[1, 0, 0])] == []
    values = [record(1), record(2, text="' OR 1=1; [x] \\\\ \"* % _")]
    assert await collection.upsert(values, generate_vectors=False) == [1, 2]
    loaded = sorted(await collection.get([1, 2, 999], include_vectors=True), key=lambda item: item["id"])
    assert loaded == values
    assert all("embedding" not in item and "image" not in item for item in await collection.get([1, 2]))
    raw = (await client.retrieve(collection.collection_name, [1], with_vectors=True))[0]
    assert "body" in raw.payload and "text" not in raw.payload and "point_key" not in raw.payload
    assert set(raw.vector) == {"dense_text", "dense_image"}
    await collection.upsert([record(1, text="replacement")], generate_vectors=False)
    assert (await collection.get([1]))[0]["text"] == "replacement"
    await collection.delete([1, 999])
    assert await collection.get([1]) == []
    await store.ensure_collection_deleted(collection.collection_name, operation_options={"timeout": 10})
    await store.ensure_collection_deleted(collection.collection_name)
    assert not await collection.collection_exists()


async def test_multiple_vectors_search_and_paging(collection_factory, record):
    collection = collection_factory()
    await collection.ensure_collection_exists()
    await collection.upsert(
        [
            record(1, embedding=[3.0, 0, 0], image=[0.0, 1.0, 0.0]),
            record(2, embedding=[2.0, 0, 0], image=[0.0, 2.0, 0.0]),
            record(3, embedding=[1.0, 0, 0], image=[0.0, 3.0, 0.0]),
        ],
        generate_vectors=False,
    )
    first = [item async for item in await collection.search(vector=[1, 0, 0], top=2, skip=1, include_vectors=True)]
    assert [item["record"]["id"] for item in first] == [2, 3]
    assert [item["score"] for item in first] == [2, 1]
    assert first[0]["record"]["embedding"] == [2, 0, 0]
    second = [
        item
        async for item in await collection.search(
            vector=[0, 1, 0],
            vector_property_name="image",
            score_threshold=2.5,
        )
    ]
    assert [item["record"]["id"] for item in second] == [3]
    assert "image" not in second[0]["record"]
    alias = [
        item async for item in await collection.search(vector=[0, 1, 0], vector_property_name="dense_image", top=1)
    ]
    assert alias[0]["record"]["id"] == 3
    assert [item["id"] for item in await collection.get(top=1, skip=1)] == [2]
    assert await collection.get(top=5, skip=999) == []
    with pytest.raises(NotImplementedError, match="Omit order_by"):
        await collection.get(order_by={"number": False}, top=1, skip=1)
    with pytest.raises(ValueError, match="vector field|Vector field"):
        await collection.search(vector=[1, 0, 0], vector_property_name="unknown")


@pytest.mark.parametrize(
    ("metric", "query", "threshold", "expected_score"),
    [
        ("DEFAULT", [1, 0, 0], 0.9, 1.0),
        ("cosine_similarity", [1, 0, 0], 0.9, 1.0),
        ("dot_prod", [1, 0, 0], 1.5, 2.0),
        ("euclidean_distance", [1, 0, 0], 1.1, 1.0),
        ("manhattan", [1, 0, 0], 1.1, 1.0),
    ],
)
async def test_native_metrics_and_threshold_direction(collection_factory, metric, query, threshold, expected_score):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("vector", name="v", dimensions=3, distance_function=metric, index_kind="flat"),
    ])
    collection = collection_factory(definition=definition)
    await collection.ensure_collection_exists()
    await collection.upsert([{"id": 1, "v": [2.0, 0, 0]}, {"id": 2, "v": [-3.0, 0, 0]}], generate_vectors=False)
    results = [item async for item in await collection.search(vector=query, score_threshold=threshold)]
    assert len(results) == 1 and results[0]["record"]["id"] == 1
    assert results[0]["score"] == pytest.approx(expected_score)


@pytest.mark.parametrize("key_type", ["int", "str", "UUID"])
async def test_key_types_and_limits(collection_factory, key_type):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="key", storage_name="physical_key", type_=key_type),
        VectorStoreField("data", name="text", type_="str"),
    ])
    collection = collection_factory(definition=definition)
    await collection.ensure_collection_exists()
    ids: list[int | str | UUID] = [0, 2**64 - 1] if key_type == "int" else [uuid4(), uuid4()]
    if key_type == "str":
        ids = [str(value) for value in ids]
    assert await collection.upsert([{"key": key, "text": "test"} for key in ids], generate_vectors=False) == ids
    assert {value["key"] for value in await collection.get(ids)} == set(ids)
    await collection.delete(ids)
    assert await collection.get() == []


@pytest.mark.parametrize("invalid", [-1, 2**64, True, False, 1.0, "arbitrary", "123", None])
async def test_invalid_keys_reject_whole_batch(definition, record, invalid):
    client = AsyncMock(spec=AsyncQdrantClient)
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    with pytest.raises((TypeError, ValueError)):
        await collection.upsert([record(1), record(invalid)], generate_vectors=False)
    client.upsert.assert_not_awaited()
    with pytest.raises((TypeError, ValueError)):
        await collection.get([invalid])
    client.retrieve.assert_not_awaited()
    with pytest.raises(IntegrationException):
        await collection.delete([invalid])
    client.delete.assert_not_awaited()


@pytest.mark.parametrize("vector", [[1, 2], [math.nan, 0, 0], [math.inf, 0, 0], [True, 0, 0], b"abc", {"indices": [0]}])
async def test_invalid_dense_vectors_before_dispatch(definition, record, vector):
    client = AsyncMock(spec=AsyncQdrantClient)
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    with pytest.raises((TypeError, ValueError)):
        await collection.upsert([record(1), record(2, embedding=vector)], generate_vectors=False)
    with pytest.raises((TypeError, ValueError)):
        await collection.search(vector=vector)
    client.upsert.assert_not_awaited()
    client.query_points.assert_not_awaited()


async def test_missing_vectors_and_selective_embeddings(collection_factory, record):
    generator = AsyncMock()
    generator.get_embeddings.return_value = GeneratedEmbeddings([Embedding(vector=[2.0, 0, 0])])
    collection = collection_factory(embedding_generator=generator)
    await collection.ensure_collection_exists()
    value = record(1, embedding="source text", image=None)
    await collection.upsert([value], generate_vectors=["embedding"])
    generator.get_embeddings.assert_awaited_once_with(["source text"], options={"dimensions": 3})
    assert value["embedding"] == "source text"
    loaded = (await collection.get([1], include_vectors=True))[0]
    assert loaded["embedding"] == [2, 0, 0] and loaded["image"] is None
    assert len([item async for item in await collection.search("query", top=1)]) == 1
    assert generator.get_embeddings.await_args.args == (["query"],)


@pytest.mark.parametrize(
    "vector_type",
    ["int", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"],
)
def test_integer_vector_declarations_rejected_before_io(vector_type):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("vector", name="v", type_=vector_type, dimensions=2),
    ])
    client = AsyncMock(spec=AsyncQdrantClient)
    with pytest.raises(ValueError, match="must be one of"):
        QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    client.create_collection.assert_not_awaited()
    client.upsert.assert_not_awaited()


async def test_integer_values_round_trip_for_float_vector_field(collection_factory):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("vector", name="v", type_="float", dimensions=2, distance_function="dot_prod"),
    ])
    collection = collection_factory(definition=definition)
    await collection.ensure_collection_exists()
    await collection.upsert([{"id": 1, "v": [16_777_217, 0]}], generate_vectors=False)
    assert await collection.get([1], include_vectors=True) == [{"id": 1, "v": [16_777_216.0, 0.0]}]


async def test_registered_models_and_custom_codecs(collection_factory):
    @vectorstoremodel
    @dataclass
    class Document:
        key: Annotated[UUID, VectorStoreField("key")]
        text: Annotated[str, VectorStoreField("data", storage_name="content")]
        vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=2)] = None

    collection = collection_factory(Document)
    await collection.ensure_collection_exists()
    key = uuid4()
    assert await collection.upsert([Document(key, "hi", [1.0, 0.0])], generate_vectors=False) == [key]
    assert (await collection.get([key]))[0] == Document(key, "hi")
    assert (await collection.get([key], include_vectors=True))[0].vector == [1, 0]

    class External:
        def __init__(self, key, text):
            self.key, self.text = key, text

    register_vectorstoremodel(
        External,
        definition=VectorStoreCollectionDefinition([
            VectorStoreField("key", name="key", type_="int"),
            VectorStoreField("data", name="text", type_="str"),
        ]),
        encoder=lambda item: {"key": item.key, "text": item.text},
        decoder=lambda item: External(item["key"], item["text"]),
    )
    external = collection_factory(External)
    await external.ensure_collection_exists()
    await external.upsert([External(7, "custom")], generate_vectors=False)
    assert (await external.get([7]))[0].text == "custom"


async def test_tuple_payload_round_trip_and_input_ownership(collection_factory):
    @vectorstoremodel
    @dataclass
    class Document:
        id: Annotated[int, VectorStoreField("key")]
        tags: Annotated[tuple[str, ...], VectorStoreField("data")]
        nested: Annotated[dict[str, tuple[int, ...]], VectorStoreField("data")]

    collection = collection_factory(Document)
    await collection.ensure_collection_exists()
    document = Document(1, ("one", "two"), {"values": (1, 2)})
    await collection.upsert([document], generate_vectors=False)
    assert (await collection.get([1]))[0] == document
    assert isinstance(document.tags, tuple) and isinstance(document.nested["values"], tuple)
    raw = (await collection.async_client.retrieve(collection.collection_name, [1]))[0]
    assert raw.payload == {"tags": ["one", "two"], "nested": {"values": [1, 2]}}


@pytest.mark.parametrize("field_type", ["tuple", "Sequence"])
async def test_dictionary_tuple_payloads(collection_factory, field_type):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("data", name="values", type_=field_type),
        VectorStoreField("data", name="nested", type_="dict"),
    ])
    collection = collection_factory(definition=definition)
    await collection.ensure_collection_exists()
    value = {"id": 1, "values": ("one", (2, None)), "nested": {"items": [(True, 3.0)]}}
    await collection.upsert([value], generate_vectors=False)
    assert await collection.get([1]) == [{"id": 1, "values": ["one", [2, None]], "nested": {"items": [[True, 3.0]]}}]
    assert value == {"id": 1, "values": ("one", (2, None)), "nested": {"items": [(True, 3.0)]}}


@pytest.mark.parametrize("invalid", [b"binary", math.inf, 2**63])
async def test_nested_tuple_validation_rejects_batch_before_write(definition, record, invalid):
    client = AsyncMock(spec=AsyncQdrantClient)
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    with pytest.raises((TypeError, ValueError)):
        await collection.upsert([record(1), record(2, tags=("valid", (invalid,)))], generate_vectors=False)
    client.upsert.assert_not_awaited()


async def test_large_batch_multi_1536_vectors(collection_factory):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("vector", name="text", dimensions=1536, distance_function="dot_prod"),
        VectorStoreField("vector", name="image", dimensions=1536, distance_function="dot_prod"),
    ])
    collection = collection_factory(definition=definition)
    await collection.ensure_collection_exists()
    values = [
        {"id": index, "text": [float(index + 1), *([0.0] * 1535)], "image": [0.0, 1.0, *([0.0] * 1534)]}
        for index in range(1000)
    ]
    assert await collection.upsert(values, generate_vectors=False) == list(range(1000))
    assert len(await collection.get(list(range(1000)))) == 1000
    results = [item async for item in await collection.search(vector=[1, *([0.0] * 1535)], top=1)]
    assert results[0]["record"]["id"] == 999
    page = await collection.get(top=4, skip=510)
    assert [item["id"] for item in page] == [510, 511, 512, 513]
    await collection.delete(list(range(1000)))
    assert await collection.get() == []


async def test_client_ownership(definition):
    client = AsyncMock(spec=AsyncQdrantClient)
    async with (
        QdrantStore(async_client=client) as store,
        store.get_collection(dict, definition=definition, collection_name="test"),
    ):
        pass
    client.close.assert_not_awaited()
    async with QdrantStore(async_client=client, managed_client=True) as owner:
        pass
    await owner.aclose()
    client.close.assert_awaited_once()
    client.reset_mock()
    with patch("agent_framework_qdrant._vector_store.AsyncQdrantClient", return_value=client):
        async with QdrantCollection(
            dict, definition=definition, collection_name="test", url="http://localhost:6333"
        ) as c:
            pass
        await c.aclose()
    client.close.assert_awaited_once()


@pytest.mark.parametrize("route", ["collection", "store"])
@pytest.mark.parametrize(
    ("api_key", "expected"),
    [
        pytest.param(None, None, id="none"),
        pytest.param("test-api-key", "test-api-key", id="string"),
        pytest.param(SecretString("test-api-key"), "test-api-key", id="framework-secret"),
        pytest.param("", "", id="empty-string"),
        pytest.param(SecretString(""), "", id="empty-framework-secret"),
    ],
)
async def test_api_key_unwrapped_at_sdk_boundary(
    definition,
    route: str,
    api_key: str | SecretString | None,
    expected: str | None,
):
    client = AsyncMock(spec=AsyncQdrantClient)
    with patch("agent_framework_qdrant._vector_store.AsyncQdrantClient", return_value=client) as factory:
        connector: QdrantCollection | QdrantStore
        if route == "collection":
            connector = QdrantCollection(
                dict,
                definition=definition,
                collection_name="test",
                url="https://qdrant.example",
                api_key=api_key,
            )
        else:
            connector = QdrantStore(url="https://qdrant.example", api_key=api_key)
        factory.assert_called_once_with(url="https://qdrant.example", api_key=expected)
        assert connector.async_client is client
        await connector.aclose()
        client.close.assert_awaited_once()


@pytest.mark.parametrize("route", ["collection", "store"])
@pytest.mark.parametrize("api_key", [SecretString("test-api-key"), SecretString("")])
def test_api_key_rejected_with_supplied_client(definition, route: str, api_key: SecretString):
    client = AsyncMock(spec=AsyncQdrantClient)
    with (
        patch("agent_framework_qdrant._vector_store.AsyncQdrantClient") as factory,
        pytest.raises(ValueError, match="connection settings"),
    ):
        if route == "collection":
            QdrantCollection(
                dict,
                definition=definition,
                collection_name="test",
                async_client=client,
                api_key=api_key,
            )
        else:
            QdrantStore(async_client=client, api_key=api_key)
    factory.assert_not_called()


async def test_failed_and_partial_batches(definition, record):
    client = AsyncMock(spec=AsyncQdrantClient)
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    client.upsert.return_value = models.UpdateResult(status=models.UpdateStatus.ACKNOWLEDGED, operation_id=1)
    with pytest.raises(IntegrationInvalidResponseException, match="did not complete"):
        await collection.upsert([record()], generate_vectors=False)
    client.upsert.side_effect = [
        models.UpdateResult(status=models.UpdateStatus.COMPLETED, operation_id=1),
        RuntimeError("server batch failure"),
    ]
    client.upsert.reset_mock()
    with pytest.raises(IntegrationException, match="server batch failure"):
        await collection.upsert([record(index) for index in range(300)], generate_vectors=False)
    assert client.upsert.await_count == 2
    assert all(call.kwargs["wait"] for call in client.upsert.await_args_list)


async def test_local_filters_rejected_even_on_empty_collection(definition):
    async with QdrantCollection(
        dict,
        definition=definition,
        collection_name="test",
        async_client=AsyncQdrantClient(":memory:"),
        managed_client=True,
    ) as collection:
        await collection.ensure_collection_exists()
        with pytest.raises(NotImplementedError, match="server"):
            await collection.get(filter=Filter("text", "eq", "hi"))
        with pytest.raises(NotImplementedError, match="server"):
            await collection.search(vector=[1, 0, 0], filter=Filter("integer", "eq", 1))


@pytest.mark.parametrize("init_options", [{}, {"location": ":memory:"}, {"path": "local-storage"}])
@pytest.mark.parametrize("skip", [0, 1_000_000])
@pytest.mark.parametrize("keys", [None, [1]])
async def test_ordering_rejected_before_io(definition, init_options, skip, keys):
    client = AsyncMock(spec=AsyncQdrantClient)
    client.init_options = init_options
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    with pytest.raises(NotImplementedError, match="Omit order_by"):
        await collection.get(keys, order_by={"number": True}, skip=skip, top=600)
    client.scroll.assert_not_awaited()
    client.query_points.assert_not_awaited()
    client.retrieve.assert_not_awaited()


async def test_empty_order_by_preserves_unordered_reads(collection_factory, record):
    collection = collection_factory()
    await collection.ensure_collection_exists()
    await collection.upsert([record(index) for index in range(3)], generate_vectors=False)
    assert await collection.get(order_by={}, top=1, skip=1) == await collection.get(top=1, skip=1)
    assert await collection.get([1], order_by={}) == await collection.get([1])


@pytest.mark.parametrize("value", [pytest.param(10**400, id="positive"), pytest.param(-(10**400), id="negative")])
@pytest.mark.parametrize(
    "operation", ["upsert", "search", "range_get", "range_search", "equality", "contains", "threshold"]
)
async def test_oversized_numeric_inputs_raise_validation_errors(definition, record, value, operation):
    client = AsyncMock(spec=AsyncQdrantClient)
    client.init_options = {}
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    with pytest.raises(ValueError):
        if operation == "upsert":
            await collection.upsert([record(1), record(2, embedding=[value, 0, 0])], generate_vectors=False)
        elif operation == "search":
            await collection.search(vector=[value, 0, 0])
        elif operation == "range_get":
            await collection.get(filter=Filter("integer", "gte", value))
        elif operation == "range_search":
            await collection.search(vector=[1, 0, 0], filter=Filter("integer", "between", (0, value)))
        elif operation == "equality":
            await collection.get(filter=Filter("number", "eq", value))
        elif operation == "contains":
            await collection.get(filter=Filter("tags", "contains", value))
        else:
            await collection.search(vector=[1, 0, 0], score_threshold=value)
    client.upsert.assert_not_awaited()
    client.query_points.assert_not_awaited()
    client.scroll.assert_not_awaited()


async def test_unsupported_options_and_schema(definition):
    client = AsyncMock(spec=AsyncQdrantClient)
    client.init_options = {}
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    with pytest.raises(NotImplementedError):
        await collection.search("query", search_type="keyword_hybrid")
    with pytest.raises(ValueError, match="dense vector"):
        await collection.search("query")
    with pytest.raises(ValueError, match="Unsupported"):
        await collection.get(operation_options={"with_payload": False})
    with pytest.raises(NotImplementedError, match="order_by"):
        await collection.get([1], order_by={"number": True})
    with pytest.raises(NotImplementedError):
        await collection.get(order_by={"number": True, "integer": True})
    with pytest.raises(NotImplementedError):
        await collection.get(order_by={"text": True})
    with pytest.raises(NotImplementedError, match="order_by"):
        await collection.get(order_by={"integer": True})
    with pytest.raises(ValueError, match="finite"):
        await collection.search(vector=[1, 0, 0], score_threshold=math.nan)
    with pytest.raises(ValueError, match="connection settings"):
        QdrantStore(async_client=client, url="http://localhost")
    with pytest.raises(ValueError, match="connection settings"):
        QdrantCollection(
            dict, definition=definition, collection_name="test", async_client=client, url="http://localhost"
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"distance_function": "cosine_distance"},
        {"distance_function": "euclidean_squared_distance"},
        {"distance_function": "negative_dot_prod"},
        {"distance_function": "hamming"},
        {"index_kind": "ivf_flat"},
        {"type_": "bytes"},
        {"provider_annotations": {"qdrant.fusion": True}},
    ],
)
def test_unsupported_vector_definitions(kwargs):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id"),
        VectorStoreField("vector", name="v", dimensions=3, **kwargs),
    ])
    with pytest.raises((ValueError, NotImplementedError)):
        QdrantCollection(dict, definition=definition, collection_name="test")


async def test_existing_collection_mismatch(collection_factory, client):
    collection = collection_factory()
    await client.create_collection(
        collection.collection_name,
        vectors_config={"dense_text": models.VectorParams(size=4, distance=models.Distance.DOT)},
    )
    with pytest.raises(ValueError, match="does not match"):
        await collection.ensure_collection_exists()


@pytest.mark.parametrize("matching_schema", [True, False])
async def test_concurrent_collection_creation_validates_winning_schema(collection_factory, client, matching_schema):
    def definition(dimensions):
        return VectorStoreCollectionDefinition([
            VectorStoreField("key", name="id", type_="int"),
            VectorStoreField("vector", name="v", dimensions=dimensions),
        ])

    first = collection_factory(definition=definition(2))
    second = QdrantCollection(
        dict,
        definition=definition(2 if matching_schema else 3),
        collection_name=first.collection_name,
        async_client=client,
    )
    exists = client.collection_exists
    ready = asyncio.Event()
    count = 0

    async def check_together(name):
        nonlocal count
        present = await exists(name)
        if not present and count < 2:
            count += 1
            if count == 2:
                ready.set()
            await ready.wait()
        return present

    with patch.object(client, "collection_exists", side_effect=check_together):
        results = await asyncio.gather(
            first.ensure_collection_exists(), second.ensure_collection_exists(), return_exceptions=True
        )
    if matching_schema:
        assert results == [None, None]
    else:
        assert sum(result is None for result in results) == 1
        assert sum(isinstance(result, ValueError) and "does not match" in str(result) for result in results) == 1


@pytest.mark.parametrize("outcome", ["rest_conflict", "grpc_conflict", "false"])
async def test_create_race_revalidates_existing_collection(collection_factory, client, outcome):
    collection = collection_factory()
    await collection.ensure_collection_exists()
    error = (
        UnexpectedResponse(409, "Conflict", b"collection already exists", Headers())
        if outcome == "rest_conflict"
        else AioRpcError(StatusCode.ALREADY_EXISTS, Metadata(), Metadata(), "collection already exists")
    )
    with (
        patch.object(client, "collection_exists", side_effect=[False, True]),
        patch.object(
            client, "create_collection", return_value=False, side_effect=None if outcome == "false" else error
        ),
        patch.object(client, "get_collection", wraps=client.get_collection) as get_collection,
    ):
        await collection.ensure_collection_exists()
        get_collection.assert_awaited_once_with(collection.collection_name)


@pytest.mark.parametrize(
    "error",
    [
        UnexpectedResponse(403, "Forbidden", b"not authorized", Headers()),
        UnexpectedResponse(500, "Internal Server Error", b"failed", Headers()),
        AioRpcError(StatusCode.PERMISSION_DENIED, Metadata(), Metadata(), "not authorized"),
        AioRpcError(StatusCode.DEADLINE_EXCEEDED, Metadata(), Metadata(), "timed out"),
        ValueError("invalid configuration"),
        TimeoutError("connection timed out"),
    ],
)
async def test_create_errors_are_not_reconciled(definition, error):
    client = AsyncMock(spec=AsyncQdrantClient)
    client.init_options = {}
    client.collection_exists.return_value = False
    client.create_collection.side_effect = error
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    with pytest.raises(type(error)) as result:
        await collection.ensure_collection_exists()
    assert result.value is error
    client.get_collection.assert_not_awaited()


async def test_conflict_does_not_hide_missing_collection(definition):
    client = AsyncMock(spec=AsyncQdrantClient)
    client.collection_exists.return_value = False
    client.create_collection.side_effect = UnexpectedResponse(409, "Conflict", b"already exists", Headers())
    missing = UnexpectedResponse(404, "Not Found", b"collection is absent", Headers())
    client.get_collection.side_effect = missing
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    with pytest.raises(UnexpectedResponse) as result:
        await collection.ensure_collection_exists()
    assert result.value is missing


@pytest.mark.parametrize("configuration", ["uint8", "flat"])
async def test_existing_vector_datatype_and_index_mismatch(collection_factory, client, configuration):
    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("vector", name="v", dimensions=3, distance_function="dot_prod", index_kind="hnsw"),
    ])
    collection = collection_factory(definition=definition)
    await client.create_collection(
        collection.collection_name,
        vectors_config={
            "v": models.VectorParams(
                size=3,
                distance=models.Distance.DOT,
                datatype=models.Datatype.UINT8 if configuration == "uint8" else None,
                hnsw_config=models.HnswConfigDiff(m=0) if configuration == "flat" else None,
            )
        },
    )
    with pytest.raises(ValueError, match="does not"):
        await collection.ensure_collection_exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("integer", 2**63),
        ("integer", True),
        ("number", math.nan),
        ("flag", 1),
        ("tags", "not an array"),
        ("text", b"binary"),
    ],
)
async def test_payload_validation_before_any_write(definition, record, field, value):
    client = AsyncMock(spec=AsyncQdrantClient)
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    with pytest.raises((TypeError, ValueError)):
        await collection.upsert([record(1), record(2, **{field: value})], generate_vectors=False)
    client.upsert.assert_not_awaited()


async def test_json_objects_arrays_and_array_like_vectors(collection_factory):
    import numpy as np

    definition = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="id", type_="int"),
        VectorStoreField("data", name="data", type_="dict"),
        VectorStoreField("vector", name="v", dimensions=2, distance_function="dot_prod"),
    ])
    collection = collection_factory(definition=definition)
    await collection.ensure_collection_exists()
    payload = {"nested": [None, True, 2**63 - 1, "literal'_%*"], "empty": {}}
    await collection.upsert([{"id": 1, "data": payload, "v": np.array([1.0, 0.0])}], generate_vectors=False)
    assert await collection.get([1], include_vectors=True) == [{"id": 1, "data": payload, "v": [1.0, 0.0]}]


async def test_missing_collection_errors(collection_factory):
    collection = collection_factory()
    with pytest.raises((ValueError, IntegrationException)):
        await collection.get([1])
    with pytest.raises((ValueError, IntegrationException)):
        await collection.search(vector=[1, 0, 0])


@pytest.mark.parametrize(
    "field",
    [
        VectorStoreField("key", name="id", is_auto_generated=True),
        VectorStoreField("data", name="text", is_full_text_indexed=True),
        VectorStoreField("data", name="text", storage_name="nested.path"),
        VectorStoreField("data", name="text", is_indexed=True),
        VectorStoreField("data", name="text", type_="str", provider_annotations={"qdrant.payload_index": "integer"}),
        VectorStoreField(
            "data", name="text", type_="str", is_indexed=False, provider_annotations={"qdrant.payload_index": "keyword"}
        ),
    ],
)
def test_invalid_data_and_key_schema(field):
    fields = [field] if field.field_type == "key" else [VectorStoreField("key", name="id"), field]
    with pytest.raises((NotImplementedError, ValueError)):
        QdrantCollection(dict, definition=VectorStoreCollectionDefinition(fields), collection_name="test")


async def test_lifecycle_failed_responses_and_options(definition):
    client = AsyncMock(spec=AsyncQdrantClient)
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    client.collection_exists.return_value = False
    client.create_collection.return_value = False
    with pytest.raises(IntegrationException, match="did not create"):
        await collection.ensure_collection_exists()
    client.collection_exists.return_value = True
    client.delete_collection.return_value = False
    with pytest.raises(IntegrationException, match="did not delete"):
        await collection.ensure_collection_deleted()
    store = QdrantStore(async_client=client)
    with pytest.raises(IntegrationException, match="did not delete"):
        await store.ensure_collection_deleted("test")
    with pytest.raises(ValueError, match="Unsupported"):
        await store.collection_exists("test", operation_options={"timeout": 1})
    with pytest.raises(ValueError, match="Unsupported"):
        await collection.ensure_collection_exists(operation_options={"vectors_config": {}})


async def test_read_request_native_options(definition, record):
    client = AsyncMock(spec=AsyncQdrantClient)
    client.init_options = {}
    client.query_points.return_value.points = []
    collection = QdrantCollection(dict, definition=definition, collection_name="test", async_client=client)
    params = models.SearchParams(exact=True)
    await collection.search(
        vector=[1, 0, 0],
        top=7,
        skip=3,
        score_threshold=-0.5,
        include_vectors=True,
        filter=Filter("integer", "eq", 1),
        operation_options={"search_params": params, "timeout": 10},
    )
    call = client.query_points.await_args.kwargs
    assert call["limit"] == 7 and call["offset"] == 3 and call["score_threshold"] == -0.5
    assert call["with_payload"] is True and call["with_vectors"] is True
    assert call["search_params"] is params and call["timeout"] == 10
    assert call["query_filter"] is not None and call["using"] == "dense_text"
