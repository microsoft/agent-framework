# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated, Literal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import msgspec
import numpy as np
import pytest
from agent_framework import (
    Embedding,
    Filter,
    FilterGroup,
    GeneratedEmbeddings,
    Param,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    create_vector_search_tool,
    vectorstoremodel,
)
from agent_framework.exceptions import (
    IntegrationException,
    IntegrationInitializationError,
    IntegrationInvalidResponseException,
)
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from agent_framework_redis import RedisCollection, RedisContextProvider, RedisHistoryProvider, RedisStore
from agent_framework_redis._vector_store import _RedisNamespaceNames


def definition(*, dimensions=2, metric="DEFAULT", vector_type="float32", index_kind="flat"):
    return VectorStoreCollectionDefinition(
        fields=[
            VectorStoreField("key", name="id", type_="str", storage_name="record_id"),
            VectorStoreField("data", name="text", type_="str", storage_name="content", is_indexed=True),
            VectorStoreField("data", name="number", type_="float", is_indexed=True),
            VectorStoreField("data", name="enabled", type_="bool", is_indexed=True),
            VectorStoreField("data", name="tags", type_="list", is_indexed=True),
            VectorStoreField("data", name="payload", type_="dict"),
            VectorStoreField(
                "vector",
                name="vector",
                storage_name="embedding",
                type_=vector_type,
                dimensions=dimensions,
                index_kind=index_kind,
                distance_function=metric,
            ),
            VectorStoreField(
                "vector",
                name="other_vector",
                type_="float64",
                dimensions=dimensions,
                index_kind=index_kind,
                distance_function="euclidean_squared_distance",
            ),
        ]
    )


def record(key="one", **overrides):
    return {
        "id": key,
        "text": "Hello, world*",
        "number": 1.5,
        "enabled": True,
        "tags": ["red", "blue"],
        "payload": {"nested": [True, None, 1]},
        "vector": [1.0, 0.0],
        "other_vector": [0.0, 1.0],
        **overrides,
    }


@pytest.fixture(params=["hash", "json"])
def storage_type(request):
    return request.param


@pytest.fixture
def noncanonical_index_suffixes():
    return [
        b"",
        b"not-hex",
        b"6",
        b"6F6E65",
        b"6f 6e65",
        b"6f6e65 ",
        b"  ",
        b"ff",
        b"\xff",
        b"eda080",
        b"20" * 257,
    ]


@pytest.fixture
async def collection(storage_type):
    async with RedisCollection(dict, definition=definition(), collection_name="unit", storage_type=storage_type) as c:
        yield c


async def test_native_codecs_and_multiple_vectors(collection, storage_type):
    source = record()
    native = await collection.serialize([source], generate_vectors=False)
    assert set(native[0]) == set(collection.definition.storage_names)
    assert native[0]["content"] == source["text"]
    assert native[0]["number"] == 1.5
    assert native[0]["enabled"] == ("true" if storage_type == "hash" else True)
    if storage_type == "hash":
        assert np.frombuffer(native[0]["embedding"], dtype="<f4").tolist() == [1.0, 0.0]
        assert np.frombuffer(native[0]["other_vector"], dtype="<f8").tolist() == [0.0, 1.0]
        assert msgspec.json.decode(native[0]["payload"]) == source["payload"]
    else:
        assert native[0]["embedding"] == [1.0, 0.0]
        assert native[0]["other_vector"] == [0.0, 1.0]
    assert collection.deserialize(native) == [source]
    assert collection.deserialize(native, include_vectors=False) == [
        {k: v for k, v in source.items() if k not in ("vector", "other_vector")}
    ]
    assert source == record()


async def test_binary_vectors_both_storage_types(storage_type):
    async with RedisCollection(
        dict, definition=definition(vector_type="bytes"), collection_name="binary", storage_type=storage_type
    ) as c:
        raw = np.asarray([1.0, 0.0], dtype="<f4").tobytes()
        native = await c.serialize([record(vector=raw)], generate_vectors=False)
        deserialized = c.deserialize(native)
        assert deserialized is not None
        assert deserialized[0]["vector"] == raw
        with pytest.raises(ValueError, match="byte length"):
            await c.serialize([record(vector=b"bad")], generate_vectors=False)


@pytest.mark.parametrize(
    "vector",
    [[True, 0.0], ["1", "0"], [float("nan"), 0], [float("inf"), 0], [1e100, 0], [0.0, 0.0], [1.0], [[1.0, 0.0]]],
)
async def test_invalid_vectors_reject_entire_batch(collection, vector):
    collection._inner_upsert = AsyncMock()
    with pytest.raises((ValueError, TypeError)):
        await collection.upsert([record(), record("two", vector=vector)], generate_vectors=False)
    collection._inner_upsert.assert_not_awaited()


async def test_selected_embedding_generation(collection):
    generator = MagicMock()
    generator.get_embeddings = AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[0.5, 0.5])]))
    collection.embedding_generator = generator
    encoded = await collection.serialize([record(vector="source")], generate_vectors=["vector"])
    result = collection.deserialize(encoded)[0]
    assert result["vector"] == [0.5, 0.5]
    assert result["other_vector"] == [0.0, 1.0]
    generator.get_embeddings.assert_awaited_once_with(["source"], options={"dimensions": 2})
    generator.get_embeddings.reset_mock()
    await collection.serialize([record()], generate_vectors=True)
    assert generator.get_embeddings.await_count == 2
    generator.get_embeddings.reset_mock()
    await collection.serialize([record()], generate_vectors=False)
    generator.get_embeddings.assert_not_awaited()


@pytest.mark.parametrize("value", [" leading", "trailing ", "\x00", "a\x1fb", "a" * 4097])
async def test_lossy_tag_values_rejected(collection, value):
    with pytest.raises(ValueError):
        await collection.serialize([record(text=value)], generate_vectors=False)


@pytest.mark.parametrize(
    "field,value",
    [("number", True), ("number", 2**53 + 1), ("number", float("nan")), ("enabled", 1), ("tags", ["ok", 1])],
)
async def test_indexed_field_types_reject_lossy_values(collection, field, value):
    with pytest.raises((TypeError, ValueError)):
        await collection.serialize([record(**{field: value})], generate_vectors=False)


async def test_json_null_and_hash_rejection(collection, storage_type):
    if storage_type == "hash":
        with pytest.raises(NotImplementedError, match="no native null"):
            await collection.serialize([record(text=None)], generate_vectors=False)
    else:
        encoded = await collection.serialize(
            [record(text=None, number=None, enabled=None, vector=None)], generate_vectors=False
        )
        assert collection.deserialize(encoded)[0]["text"] is None
        assert collection.deserialize(encoded)[0]["vector"] is None
    with pytest.raises(ValueError, match="missing"):
        await collection.serialize([{"id": "missing"}], generate_vectors=False)
    with pytest.raises(IntegrationInvalidResponseException, match="missing"):
        collection.deserialize([{"record_id": b"missing"}])


async def test_unindexed_data_is_not_subject_to_tag_restrictions(collection):
    value = {"text": " whitespace\x1f", "large": "x" * 8000}
    assert (
        collection.deserialize(await collection.serialize([record(payload=value)], generate_vectors=False))[0][
            "payload"
        ]
        == value
    )


def test_native_schema_and_names(collection, storage_type):
    schema = collection._index.schema.to_dict()
    fields = {field["name"]: field for field in schema["fields"]}
    assert set(fields) == {"record_id", "content", "number", "enabled", "tags", "embedding", "other_vector"}
    assert fields["content"]["attrs"]["case_sensitive"] is True
    assert fields["content"]["attrs"]["index_empty"] is True
    assert fields["content"]["attrs"]["index_missing"] is True
    assert fields["embedding"]["attrs"]["distance_metric"] == "cosine"
    assert fields["other_vector"]["attrs"]["distance_metric"] == "l2"
    if storage_type == "json":
        assert fields["embedding"]["path"] == "$.embedding"
    assert collection._prepare_key("key:with:separators").startswith(collection.key_prefix)
    assert collection.key_prefix.endswith(":")


@pytest.mark.parametrize(
    "expression,fragment",
    [
        (Filter("text", "eq", "Hello,*|{a}\\$"), r"@content:{Hello\,\*\|\{a\}\\\$}"),
        (Filter("text", "eq", ""), '@content:{""}'),
        (Filter("number", "eq", True), "ismissing(@number) -ismissing(@number)"),
        (Filter("enabled", "eq", 1), "ismissing(@enabled) -ismissing(@enabled)"),
        (Filter("enabled", "eq", True), "@enabled:{true}"),
        (Filter("number", "gt", 1), "@number:[(1.0 +inf]"),
        (Filter("number", "between", [1, 2]), "@number:[1.0 2.0]"),
        (Filter("text", "exists"), "ismissing(@content)"),
        (Filter("text", "ne", "red"), "ismissing(@content)"),
        (Filter("tags", "contains", "red"), "@tags:{red}"),
    ],
)
def test_prepare_filter(collection, expression, fragment):
    assert fragment in collection._prepare_filter(expression)


@pytest.mark.parametrize("op", ["starts_with", "ends_with", "contains_text", "redis.raw"])
def test_unsupported_text_and_native_filters(collection, op):
    with pytest.raises(NotImplementedError):
        collection._prepare_filter(Filter("text", op, "*"))


@pytest.mark.parametrize("op,value", [("is_null", None), ("is_not_null", None), ("not_in", ["red"])])
async def test_json_string_null_dependent_filters_rejected(op, value):
    async with RedisCollection(dict, definition=definition(), collection_name="filters", storage_type="json") as c:
        with pytest.raises(NotImplementedError, match="cannot distinguish null"):
            c._prepare_filter(Filter("text", op, value))


async def test_query_shape_threshold_and_paging(collection):
    collection._require_index = AsyncMock()
    collection._execute_query = AsyncMock(return_value=[0])
    collection._fetch_records = AsyncMock(return_value=[])
    await collection.search(vector=[1.0, 0.0], top=4, skip=3)
    query, params = collection._execute_query.call_args.args
    assert "KNN 7 @embedding $vector" in query.query_string()
    assert query.get_args()[-3:] == ["LIMIT", 3, 4]
    assert params["vector"] == np.asarray([1.0, 0.0], dtype="<f4").tobytes()
    await collection.search(
        vector=[0.0, 1.0],
        vector_property_name="other_vector",
        top=4,
        skip=3,
        score_threshold=2,
        filter=Filter("number", "gte", 1),
    )
    query, params = collection._execute_query.call_args.args
    assert "VECTOR_RANGE $radius $vector" in query.query_string()
    assert "@other_vector" in query.query_string()
    assert "@number:[1.0 +inf]" in query.query_string()
    assert params["radius"] == 2
    assert query.get_args()[-3:] == ["LIMIT", 3, 4]


async def test_unsupported_operations_fail_explicitly(collection):
    collection._require_index = AsyncMock()
    with pytest.raises(NotImplementedError):
        await collection.search("keyword", search_type="keyword_hybrid", vector=[1.0, 0.0])
    with pytest.raises(NotImplementedError):
        await collection.search(vector=[1.0, 0.0], score_threshold=-1)
    with pytest.raises(ValueError):
        await collection.search(vector=[1.0, 0.0], score_threshold=float("nan"))
    with pytest.raises(ValueError):
        await collection.search("no generator")
    with pytest.raises(NotImplementedError):
        await collection.get(order_by={"text": True, "number": False})
    with pytest.raises(NotImplementedError):
        await collection.get(operation_options={"ignored": True})


@pytest.mark.parametrize("operation", ["get", "search"])
async def test_unsupported_filters_fail_before_redis_io(collection, operation):
    collection._require_index = AsyncMock()
    with pytest.raises(NotImplementedError, match="contains_text"):
        if operation == "get":
            await collection.get(filter=Filter("text", "contains_text", "word"))
        else:
            await collection.search(vector=[1.0, 0.0], filter=Filter("text", "contains_text", "word"))
    collection._require_index.assert_not_awaited()


async def test_owned_and_borrowed_client_lifecycle():
    borrowed = Redis()
    with patch.object(borrowed, "aclose", new_callable=AsyncMock) as close:
        async with RedisStore(redis_client=borrowed) as store:
            handle = store.get_collection(dict, definition=definition(), collection_name="owned")
            async with handle:
                assert handle.redis_client is borrowed
            close.assert_not_awaited()
            another = store.get_collection(dict, definition=definition(), collection_name="another")
        close.assert_not_awaited()
    with pytest.raises(RuntimeError, match="closed"):
        await another.collection_exists()
    with pytest.raises(RuntimeError, match="closed"):
        store.get_collection(dict, definition=definition(), collection_name="late")
    owned = RedisStore()
    with patch.object(owned.redis_client, "aclose", new_callable=AsyncMock) as owned_close:
        async with owned:
            pass
        owned_close.assert_awaited_once()
        await owned.close()
        owned_close.assert_awaited_once()


async def test_collection_overrides_only_default_when_none(storage_type):
    default_generator = MagicMock()
    falsey_generator = MagicMock()
    falsey_generator.__bool__.return_value = False
    async with RedisStore(storage_type=storage_type, embedding_generator=default_generator) as store:
        inherited = store.get_collection(
            dict, definition=definition(), collection_name="inherited", embedding_generator=None, storage_type=None
        )
        assert inherited.embedding_generator is default_generator
        assert inherited.storage_type == storage_type
        override_type: Literal["hash", "json"] = "json" if storage_type == "hash" else "hash"
        overridden = store.get_collection(
            dict,
            definition=definition(),
            collection_name="overridden",
            embedding_generator=falsey_generator,
            storage_type=override_type,
        )
        assert overridden.embedding_generator is falsey_generator
        assert overridden.storage_type == override_type
        default_generator.get_embeddings.assert_not_called()
        falsey_generator.get_embeddings.assert_not_called()


@pytest.mark.parametrize("override", [""])
async def test_empty_collection_storage_override_is_rejected(override):
    async with RedisStore() as store:
        with pytest.raises(ValueError, match="storage_type"):
            store.get_collection(dict, definition=definition(), collection_name="invalid", storage_type=override)


@pytest.mark.parametrize("kwargs", [{"decode_responses": True}, {"protocol": 3}])
def test_incompatible_borrowed_clients(kwargs):
    with pytest.raises(ValueError, match="RESP"):
        RedisStore(redis_client=Redis(**kwargs))


@pytest.mark.parametrize(
    "field",
    [
        VectorStoreField("data", name="bad", storage_name="field.with.path"),
        VectorStoreField("data", name="bad", is_full_text_indexed=True),
        VectorStoreField("data", name="bad", type_="dict", is_indexed=True),
        VectorStoreField("data", name="bad", provider_annotations={"unhandled": True}),
        VectorStoreField("vector", name="bad", dimensions=2, distance_function="cosine_similarity"),
        VectorStoreField("vector", name="bad", dimensions=2, index_kind="ivf_flat"),
    ],
)
def test_invalid_schema_fails_without_connecting(field):
    with pytest.raises((ValueError, NotImplementedError)):
        RedisCollection(
            dict,
            collection_name="bad",
            definition=VectorStoreCollectionDefinition(fields=[VectorStoreField("key", name="id", type_="str"), field]),
        )


async def test_failed_pipeline_is_not_reported_as_success(collection):
    collection._require_index = AsyncMock()
    pipeline = MagicMock()
    pipeline.__aenter__ = AsyncMock(return_value=pipeline)
    pipeline.__aexit__ = AsyncMock(return_value=False)
    pipeline.execute = AsyncMock(side_effect=ResponseError("partial EXEC failure"))
    with (
        patch.object(collection.redis_client, "pipeline", return_value=pipeline),
        pytest.raises(IntegrationException, match="partial EXEC"),
    ):
        await collection.upsert([record()], generate_vectors=False)


async def test_search_tool_resolves_and_prunes_params(collection):
    generator = MagicMock()
    generator.get_embeddings = AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[1.0, 0.0])]))
    collection.embedding_generator = generator
    collection._require_index = AsyncMock()
    collection._execute_query = AsyncMock(return_value=[0])
    collection._fetch_records = AsyncMock(return_value=[])
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup(
            "and",
            [
                Filter("enabled", "eq", True),
                Filter("text", "eq", Param("text", str | None, default=None, omit_if_none=True)),
            ],
        ),
    )
    await tool.invoke(arguments={"query": "query", "text": None})
    query = collection._execute_query.call_args.args[0].query_string()
    assert "@enabled:{true}" in query
    assert "@content" not in query
    await tool.invoke(arguments={"query": "query", "text": "a|b"})
    assert r"@content:{a\|b}" in collection._execute_query.call_args.args[0].query_string()


@pytest.mark.parametrize("required", [False, True])
async def test_search_tool_params_without_defaults(collection, required):
    generator = MagicMock()
    generator.get_embeddings = AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[1.0, 0.0])]))
    collection.embedding_generator = generator
    collection._require_index = AsyncMock()
    collection._execute_query = AsyncMock(return_value=[0])
    collection._fetch_records = AsyncMock(return_value=[])
    parameter = Param("text", str, required=required)
    assert not parameter.has_default
    assert parameter.default is Param("independent", str).default
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup("and", [Filter("enabled", "eq", True), Filter("text", "eq", parameter)]),
    )
    await tool(query="query", text="a|b")
    query = collection._execute_query.call_args.args[0].query_string()
    assert "@enabled:{true}" in query
    assert r"@content:{a\|b}" in query
    collection._execute_query.reset_mock()
    if required:
        with pytest.raises(TypeError, match=r"Missing required argument\(s\) for 'search': text"):
            await tool(query="query")
        collection._execute_query.assert_not_awaited()
    else:
        await tool(query="query")
        query = collection._execute_query.call_args.args[0].query_string()
        assert "@enabled:{true}" in query
        assert "@content" not in query


def mock_pipeline(responses):
    pipeline = MagicMock()
    pipeline.__aenter__ = AsyncMock(return_value=pipeline)
    pipeline.__aexit__ = AsyncMock(return_value=False)
    pipeline.execute = AsyncMock(return_value=responses)
    return pipeline


async def test_fetch_native_results_excludes_vector_payloads(collection, storage_type):
    collection._require_index = AsyncMock()
    native = (await collection.serialize([record()], generate_vectors=False))[0]
    names = collection.definition.get_storage_names(include_vector_fields=False)
    if storage_type == "hash":
        native = {name: value if isinstance(value, bytes) else str(value).encode() for name, value in native.items()}
        pipeline = mock_pipeline([1, [native[n] for n in names], 0, [None] * len(names)])
    else:
        pipeline = mock_pipeline([msgspec.json.encode({f"$.{name}": [native[name]] for name in names}), None])
    with patch.object(collection.redis_client, "pipeline", return_value=pipeline):
        result = await collection.get(["one", "missing"])
    assert result == [{k: v for k, v in record().items() if k not in ("vector", "other_vector")}]
    if storage_type == "hash":
        assert "embedding" not in pipeline.hmget.call_args.args[1]
    else:
        assert "$.embedding" not in pipeline.execute_command.call_args.args


async def test_missing_required_fields_are_not_silently_omitted(collection, storage_type):
    collection._require_index = AsyncMock()
    names = collection.definition.get_storage_names(include_vector_fields=False)
    responses = [1, [None] * len(names)] if storage_type == "hash" else [b"{}"]
    with (
        patch.object(collection.redis_client, "pipeline", return_value=mock_pipeline(responses)),
        pytest.raises(IntegrationInvalidResponseException, match="missing"),
    ):
        await collection.get(["malformed"])


async def test_search_distance_stays_attached_to_record_after_concurrent_delete(collection):
    collection._require_index = AsyncMock()
    native = (await collection.serialize([record("two")], generate_vectors=False))[0]
    collection._fetch_records = AsyncMock(return_value=[None, native])
    response = [
        2,
        (collection.key_prefix + "gone").encode(),
        [b"_af_distance", b"0.0"],
        (collection.key_prefix + "two").encode(),
        [b"_af_distance", b"0.5"],
    ]
    with patch.object(collection.redis_client, "execute_command", AsyncMock(return_value=response)) as execute:
        results = [r async for r in await collection.search(vector=[1.0, 0.0], include_vectors=True)]
    assert results == [{"record": record("two"), "score": 0.5}]
    assert execute.call_args.args[-4:] == ("PARAMS", 2, "vector", np.asarray([1.0, 0.0], dtype="<f4").tobytes())


async def test_index_initialization_schema_validation_and_cleanup(collection):
    collection._index.exists = AsyncMock(return_value=False)
    search = MagicMock()
    search.create_index = AsyncMock()
    with (
        patch.object(collection.redis_client, "ft", return_value=search),
        patch.object(collection.redis_client, "execute_command", AsyncMock(return_value=None)),
        patch(
            "agent_framework_redis._vector_store.AsyncSearchIndex.from_existing",
            AsyncMock(return_value=collection._index),
        ),
    ):
        await collection.ensure_collection_exists()
        for field in search.create_index.call_args.args[0]:
            suffix = field.args_suffix
            if "SORTABLE" in suffix and "INDEXMISSING" in suffix:
                assert suffix.index("INDEXMISSING") < suffix.index("SORTABLE")
        collection._index.exists.return_value = True
        assert await collection.collection_exists()
        collection._index.delete = AsyncMock()
        await collection.ensure_collection_deleted()
        collection._index.delete.assert_awaited_once_with(drop=True)
    collection._index.exists.return_value = False
    with pytest.raises(IntegrationException, match="does not exist"):
        await collection.get()


@pytest.mark.parametrize("change", ["deleted", "replaced"])
async def test_index_validation_is_not_cached(collection, change):
    with (
        patch.object(collection._index, "exists", AsyncMock(return_value=True)) as exists,
        patch.object(collection, "_validate_schema", new_callable=AsyncMock) as validate,
    ):
        await collection._require_index()
        if change == "replaced":
            validate.side_effect = ValueError("incompatible")
        else:
            exists.return_value = False
        error = ValueError if change == "replaced" else IntegrationException
        message = "incompatible" if change == "replaced" else "does not exist"
        with pytest.raises(error, match=message):
            await collection._require_index()
        assert exists.await_count == 2
        assert validate.await_count == (2 if change == "replaced" else 1)


async def test_missing_server_capability_fails_at_initialization(collection):
    collection._index.exists = AsyncMock(side_effect=ResponseError("unknown command FT._LIST"))
    with (
        patch.object(collection.redis_client, "execute_command", AsyncMock(side_effect=ResponseError("JSON.TYPE"))),
        pytest.raises(IntegrationInitializationError, match="INDEXMISSING"),
    ):
        await collection.ensure_collection_exists()


async def test_key_delete_is_batched_and_validated_before_io(collection):
    collection._require_index = AsyncMock()
    with patch.object(collection.redis_client, "delete", new_callable=AsyncMock) as delete:
        await collection.delete([str(i) for i in range(201)])
        assert delete.await_count == 3
        assert all(key.startswith(collection.key_prefix) for call in delete.call_args_list for key in call.args)
        delete.reset_mock()
        with pytest.raises(IntegrationException, match="nonempty strings"):
            await collection.delete(["valid", ""])
        delete.assert_not_awaited()


async def test_store_lists_and_deletes_only_its_namespace(noncanonical_index_suffixes):
    async with RedisStore(namespace="scope") as store:
        c = store.get_collection(dict, definition=definition(), collection_name="one")
        c._index.delete = AsyncMock()
        prefix = c.index_name.rsplit(":", 1)[0].encode() + b":"
        with (
            patch.object(
                store.redis_client,
                "execute_command",
                AsyncMock(
                    return_value=[
                        c.index_name.encode(),
                        b"unrelated:\xff",
                        *(prefix + suffix for suffix in noncanonical_index_suffixes),
                    ]
                ),
            ),
            patch(
                "agent_framework_redis._vector_store.AsyncSearchIndex.from_existing", AsyncMock(return_value=c._index)
            ) as from_existing,
        ):
            assert await store.list_collection_names() == ["one"]
            assert await store.collection_exists("one")
            assert not await store.collection_exists("missing")
            await store.ensure_collection_deleted("one")
            from_existing.assert_awaited_once_with(c.index_name, redis_client=store.redis_client)
            c._index.delete.assert_awaited_once_with(drop=True)


@pytest.mark.parametrize(
    "namespace,name,index_name,key_prefix",
    [
        ("scope", "one", "af:vector:73636f7065:index:6f6e65", "af:vector:73636f7065:data:6f6e65:"),
        ("a:b", "\u00e9", "af:vector:613a62:index:c3a9", "af:vector:613a62:data:c3a9:"),
        ("\u00e9", "a:b", "af:vector:c3a9:index:613a62", "af:vector:c3a9:data:613a62:"),
    ],
)
def test_namespace_names_preserve_persisted_format(namespace, name, index_name, key_prefix):
    names = _RedisNamespaceNames(namespace)
    assert names.for_collection(name) == (index_name, key_prefix)
    assert names.try_parse_index_name(index_name.encode()) == name
    assert names.try_parse_index_name(key_prefix.encode()) is None
    assert _RedisNamespaceNames(namespace + "other").try_parse_index_name(index_name.encode()) is None


@pytest.mark.parametrize("namespace", ["default", "a:b", "\u00e9"])
@pytest.mark.parametrize("name", ["one", "\u00e9", "a" * 256, "\u00e9" * 128])
async def test_store_lists_canonical_unicode_and_boundary_names(namespace, name):
    names = _RedisNamespaceNames(namespace)
    index_name, key_prefix = names.for_collection(name)
    assert names.try_parse_index_name(index_name.encode()) == name
    async with RedisStore(namespace=namespace) as store:
        collection = store.get_collection(dict, definition=definition(), collection_name=name)
        assert (collection.index_name, collection.key_prefix) == (index_name, key_prefix)
        with patch.object(
            store.redis_client, "execute_command", AsyncMock(return_value=[collection.index_name.encode()])
        ):
            assert await store.list_collection_names() == [name]


async def test_store_listing_propagates_redis_errors():
    async with RedisStore() as store:
        with (
            patch.object(store.redis_client, "execute_command", AsyncMock(side_effect=ResponseError("denied"))),
            pytest.raises(ResponseError, match="denied"),
        ):
            await store.list_collection_names()


async def test_large_batch_codec_without_embedding_calls(collection):
    generator = MagicMock(get_embeddings=AsyncMock())
    async with RedisCollection(
        dict,
        definition=definition(dimensions=1536),
        collection_name="large",
        storage_type=collection.storage_type,
        embedding_generator=generator,
    ) as c:
        vector = [0.01] * 1536
        native = await c.serialize(
            [record(str(i), vector=vector, other_vector=vector) for i in range(1000)], generate_vectors=False
        )
        assert len(native) == 1000
        deserialized = c.deserialize([native[999]])
        assert deserialized is not None
        assert len(deserialized[0]["other_vector"]) == 1536
        assert len(native[0]["embedding"]) == (1536 * 4 if c.storage_type == "hash" else 1536)
        generator.get_embeddings.assert_not_awaited()


async def test_empty_batches_do_not_contact_redis(collection):
    with patch.object(collection, "_require_index", new_callable=AsyncMock) as require:
        assert await collection.upsert([], generate_vectors=False) == []
        assert await collection.get([]) == []
        await collection.delete([])
        require.assert_not_awaited()


def test_public_namespace_and_existing_providers():
    from agent_framework.redis import RedisCollection as LazyCollection
    from agent_framework.redis import RedisStore as LazyStore

    assert LazyCollection is RedisCollection
    assert LazyStore is RedisStore
    assert RedisContextProvider is not None
    assert RedisHistoryProvider is not None


@vectorstoremodel
@dataclass
class VectorRecord:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data", is_indexed=True)]
    vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=2)] = None


async def test_decorated_model_roundtrip_and_generated_keys(storage_type):
    async with RedisCollection(VectorRecord, collection_name="models", storage_type=storage_type) as c:
        native = await c.serialize([VectorRecord("one", "Text", [1.0, 0.0])], generate_vectors=False)
        assert c.deserialize(native) == [VectorRecord("one", "Text", [1.0, 0.0])]
        assert c.deserialize(native, include_vectors=False) == [VectorRecord("one", "Text")]
    async with RedisCollection(
        dict,
        collection_name="generated",
        storage_type=storage_type,
        definition=VectorStoreCollectionDefinition(
            fields=[VectorStoreField("key", name="id", type_="str", is_auto_generated=True)]
        ),
    ) as generated:
        native = await generated.serialize([{}, {}], generate_vectors=False)
        assert native[0]["id"] != native[1]["id"]


@pytest.fixture
async def live_store(storage_type):
    url = os.getenv("REDIS_VECTOR_TEST_URL")
    if not url:
        pytest.skip("Set REDIS_VECTOR_TEST_URL to a disposable Redis Search 2.10+ and RedisJSON server.")
    async with RedisStore(redis_url=url, storage_type=storage_type, namespace="af-test-" + uuid4().hex) as store:
        try:
            # A configured but insufficient server must fail, not be silently skipped.
            await store.list_collection_names()
            yield store
        finally:
            for name in await store.list_collection_names():
                await store.ensure_collection_deleted(name)


@pytest.mark.integration
async def test_live_crud_native_storage_and_isolation(live_store, storage_type):
    c = live_store.get_collection(dict, definition=definition(), collection_name="one")
    neighbor = live_store.get_collection(dict, definition=definition(), collection_name="one:two")
    assert not await c.collection_exists()
    await c.ensure_collection_exists()
    await c.ensure_collection_exists()
    await neighbor.ensure_collection_exists()
    assert await c.upsert([record("same"), record("two")], generate_vectors=False) == ["same", "two"]
    await neighbor.upsert([record("same", text="Neighbor")], generate_vectors=False)
    assert [r["id"] for r in await c.get(["two", "missing", "same"])] == ["two", "same"]
    assert "vector" not in (await c.get(["same"]))[0]
    assert (await c.get(["same"], include_vectors=True))[0] == record("same")
    assert (await neighbor.get(["same"]))[0]["text"] == "Neighbor"
    if storage_type == "hash":
        raw = await c.redis_client.hgetall(c.key_prefix + "same")
        assert raw[b"content"] == b"Hello, world*"
        assert raw[b"enabled"] == b"true"
        assert {key.decode() for key in raw} == set(c.definition.storage_names)
    else:
        raw = msgspec.json.decode(await c.redis_client.execute_command("JSON.GET", c.key_prefix + "same"))
        assert raw["embedding"] == [1.0, 0.0]
        assert raw["enabled"] is True
    await c.upsert([record("same", text="Replaced")], generate_vectors=False)
    assert not await c.get(filter=Filter("text", "eq", "Hello, world*"), top=1, skip=1)
    await c.delete(["two", "missing"])
    assert not await c.get(["two"])
    await c.ensure_collection_deleted()
    assert await neighbor.collection_exists()
    assert await neighbor.get(["same"])


@pytest.mark.integration
async def test_live_native_filters_and_literal_escaping(live_store, storage_type):
    c = live_store.get_collection(dict, definition=definition(), collection_name="filters")
    await c.ensure_collection_exists()
    values = ["", "Case", "case", "a,b|c{}[]()@:$!\\*?~-'\"+=<>/%#", "inside space", "é漢字"]
    await c.upsert(
        [record(str(i), text=text, number=i, enabled=i % 2 == 0) for i, text in enumerate(values)],
        generate_vectors=False,
    )
    for i, text in enumerate(values):
        assert [r["id"] for r in await c.get(filter=Filter("text", "eq", text))] == [str(i)]
    assert not await c.get(filter=Filter("number", "eq", True))
    assert not await c.get(filter=Filter("enabled", "eq", 1))
    assert len(await c.get(filter=Filter("enabled", "eq", True))) == 3
    assert [r["id"] for r in await c.get(filter=Filter("number", "between", [1, 3]))] == ["1", "2", "3"]
    assert [r["id"] for r in await c.get(filter=Filter("number", "in", [None, 1, 3]))] == ["1", "3"]
    assert [r["id"] for r in await c.get(filter=Filter("number", "not_in", [1, 3]))] == ["0", "2", "4", "5"]
    group = FilterGroup(
        "and",
        [
            FilterGroup("or", [Filter("number", "lt", 1), Filter("number", "gt", 3)]),
            FilterGroup("not", [Filter("enabled", "eq", False)]),
        ],
    )
    assert [r["id"] for r in await c.get(filter=group)] == ["0", "4"]
    assert len(await c.get(filter=Filter("tags", "contains_all", ["red", "blue"]))) == len(values)
    assert not await c.get(filter=Filter("tags", "contains_any", []))
    assert len(await c.get(filter=Filter("text", "exists"))) == len(values)
    if storage_type == "json":
        await c.upsert([record("null", text=None, number=None, enabled=None)], generate_vectors=False)
        assert [r["id"] for r in await c.get(filter=Filter("number", "is_null"))] == ["null"]
        assert [r["id"] for r in await c.get(filter=Filter("enabled", "is_null"))] == ["null"]
        assert len(await c.get(filter=Filter("number", "is_not_null"))) == len(values)
        assert len(await c.get(filter=Filter("text", "exists"))) == len(values) + 1
        assert "null" in [r["id"] for r in await c.get(filter=Filter("text", "ne", "Case"))]


@pytest.mark.integration
async def test_live_missing_fields_are_not_null(live_store, storage_type):
    c = live_store.get_collection(dict, definition=definition(), collection_name="missing")
    await c.ensure_collection_exists()
    await c.upsert([record("complete"), record("missing")], generate_vectors=False)
    if storage_type == "hash":
        await c.redis_client.hdel(c.key_prefix + "missing", "number")
    else:
        await c.redis_client.execute_command("JSON.DEL", c.key_prefix + "missing", "$.number")
    assert [r["id"] for r in await c.get(filter=Filter("number", "exists"))] == ["complete"]
    assert [r["id"] for r in await c.get(filter=Filter("number", "ne", 999))] == ["complete"]
    assert not await c.get(filter=Filter("number", "is_null"))
    with pytest.raises(IntegrationInvalidResponseException, match="missing"):
        await c.get(["missing"])


@pytest.mark.integration
@pytest.mark.parametrize(
    "metric,expected",
    [
        ("DEFAULT", [0.0, 0.292893218, 1.0]),
        ("cosine_distance", [0.0, 0.292893218, 1.0]),
        ("euclidean_squared_distance", [0.0, 1.0, 2.0]),
        ("redis.ip", [0.0, 0.0, 1.0]),
    ],
)
async def test_live_scores_thresholds_and_paging(live_store, metric, expected):
    c = live_store.get_collection(dict, definition=definition(metric=metric), collection_name="scores")
    await c.ensure_collection_exists()
    await c.upsert(
        [
            record("one", vector=[1.0, 0.0], number=0),
            record("two", vector=[1.0, 1.0], number=1),
            record("three", vector=[0.0, 1.0], number=2),
        ],
        generate_vectors=False,
    )
    results = [r async for r in await c.search(vector=[1.0, 0.0], top=10)]
    assert [r["score"] for r in results] == pytest.approx(expected)
    page = [r async for r in await c.search(vector=[1.0, 0.0], top=1, skip=1)]
    assert page[0]["score"] == pytest.approx(expected[1])
    bounded = [
        r
        async for r in await c.search(
            vector=[1.0, 0.0], score_threshold=expected[1] + 1e-6, skip=1, top=5, include_vectors=True
        )
    ]
    assert len(bounded) == 1
    assert "vector" in bounded[0]["record"]
    assert not [r async for r in await c.search(vector=[1.0, 0.0], score_threshold=expected[1] + 1e-6, skip=2, top=5)]
    filtered = [
        r
        async for r in await c.search(
            vector=[1.0, 0.0], filter=Filter("number", "gt", 0), score_threshold=expected[1] + 1e-6
        )
    ]
    assert len(filtered) == 1
    assert len([r async for r in await c.search(vector=[1.0, 0.0], score_threshold=0.0)]) >= 1
    other = [r async for r in await c.search(vector=[0.0, 1.0], vector_property_name="other_vector")]
    assert all(r["score"] == 0.0 for r in other)
    assert [r["id"] for r in await c.get(order_by={"number": False}, skip=1, top=1)] == ["two"]


@pytest.mark.integration
async def test_live_unicode_keys_and_text_roundtrip(live_store):
    c = live_store.get_collection(dict, definition=definition(), collection_name="unicode:\u00e9")
    await c.ensure_collection_exists()
    source = [record("abc", text="Plain text"), record("a\u00e9b\u00e9c", text="Caf\u00e9 \u6f22\u5b57")]
    assert await c.upsert(source, generate_vectors=False) == ["abc", "a\u00e9b\u00e9c"]
    assert await c.get(["abc", "a\u00e9b\u00e9c"], include_vectors=True) == source
    assert [r["id"] for r in await c.get(filter=Filter("text", "eq", "Caf\u00e9 \u6f22\u5b57"))] == ["a\u00e9b\u00e9c"]
    assert await live_store.list_collection_names() == ["unicode:\u00e9"]
    await c.delete(["abc"])
    assert await c.get(["a\u00e9b\u00e9c"], include_vectors=True) == [source[1]]
    await live_store.ensure_collection_deleted("unicode:\u00e9")
    assert not await live_store.collection_exists("unicode:\u00e9")


@pytest.mark.integration
async def test_live_store_ignores_noncanonical_indexes(live_store, noncanonical_index_suffixes):
    c = live_store.get_collection(dict, definition=definition(), collection_name="one")
    await c.ensure_collection_exists()
    await c.upsert([record()], generate_vectors=False)
    prefix = c.index_name.rsplit(":", 1)[0].encode() + b":"
    foreign_prefix = "af-test-foreign:" + uuid4().hex + ":"
    foreign_key = foreign_prefix + "one"
    index_names = [prefix + suffix for suffix in noncanonical_index_suffixes]
    index_names.append(foreign_prefix.encode() + b"\xff")
    created = []
    try:
        await c.redis_client.hset(foreign_key, mapping={"text": "Foreign"})
        for index_name in index_names:
            await c.redis_client.execute_command(
                "FT.CREATE", index_name, "ON", "HASH", "PREFIX", 1, foreign_prefix, "SCHEMA", "text", "TEXT"
            )
            created.append(index_name)
        assert await live_store.list_collection_names() == ["one"]
        assert await live_store.collection_exists("one")
        assert not await live_store.collection_exists("missing")
        await live_store.ensure_collection_deleted("one")
        assert await live_store.list_collection_names() == []
        assert not await live_store.collection_exists("one")
        assert not await c.redis_client.exists(c.key_prefix + "one")
        remaining = await c.redis_client.execute_command("FT._LIST")
        assert set(index_names) <= set(remaining)
        assert await c.redis_client.hgetall(foreign_key) == {b"text": b"Foreign"}
    finally:
        for index_name in created:
            await c.redis_client.execute_command("FT.DROPINDEX", index_name)
        await c.redis_client.delete(foreign_key)


@pytest.mark.integration
@pytest.mark.parametrize("change", ["deleted", "replaced"])
@pytest.mark.parametrize("operation", ["upsert", "get", "filtered_get", "delete", "search"])
async def test_live_warm_handle_rechecks_index(live_store, change, operation):
    c = live_store.get_collection(dict, definition=definition(), collection_name="lifecycle")
    await c.ensure_collection_exists()
    await c.upsert([record()], generate_vectors=False)
    key = c.key_prefix + "one"
    snapshot = await c.redis_client.dump(key)
    assert snapshot is not None
    try:
        await c.redis_client.ft(c.index_name).dropindex(delete_documents=False)
        if change == "replaced":
            replacement = live_store.get_collection(
                dict, definition=definition(dimensions=3), collection_name="lifecycle"
            )
            await replacement.ensure_collection_exists()
        error = ValueError if change == "replaced" and operation != "delete" else IntegrationException
        message = "incompatible" if change == "replaced" else "does not exist"
        with pytest.raises(error, match=message) as exc_info:
            if operation == "upsert":
                await c.upsert([record(text="Changed")], generate_vectors=False)
            elif operation == "get":
                await c.get(["one"])
            elif operation == "filtered_get":
                await c.get(filter=Filter("text", "eq", record()["text"]))
            elif operation == "delete":
                await c.delete(["one"])
            else:
                await c.search(vector=[1.0, 0.0])
        if change == "replaced" and operation == "delete":
            assert isinstance(exc_info.value.__cause__, ValueError)
        assert await c.redis_client.dump(key) == snapshot
    finally:
        await c.redis_client.delete(key)


@pytest.mark.integration
async def test_live_schema_mismatch_is_nondestructive(live_store):
    c = live_store.get_collection(dict, definition=definition(), collection_name="schema")
    await c.ensure_collection_exists()
    await c.upsert([record()], generate_vectors=False)
    incompatible = live_store.get_collection(dict, definition=definition(dimensions=3), collection_name="schema")
    with pytest.raises(ValueError, match="incompatible"):
        await incompatible.ensure_collection_exists()
    with pytest.raises(ValueError, match="incompatible"):
        await incompatible.ensure_collection_deleted()
    with pytest.raises(ValueError, match="incompatible"):
        await incompatible.upsert([record(vector=[1, 0, 0], other_vector=[0, 1, 0])], generate_vectors=False)
    assert (await c.get(["one"]))[0]["id"] == "one"


@pytest.mark.integration
async def test_live_hnsw_and_native_tag_boundary(live_store):
    c = live_store.get_collection(dict, definition=definition(index_kind="hnsw"), collection_name="hnsw")
    await c.ensure_collection_exists()
    text = "x" * 4096
    await c.upsert([record(text=text)], generate_vectors=False)
    assert [r["id"] for r in await c.get(filter=Filter("text", "eq", text))] == ["one"]
    assert len([r async for r in await c.search(vector=[1.0, 0.0])]) == 1
    assert len([r async for r in await c.search(vector=[1.0, 0.0], score_threshold=0.0)]) == 1


@pytest.mark.integration
async def test_live_native_json_null_vectors_and_empty_arrays(live_store, storage_type):
    c = live_store.get_collection(dict, definition=definition(), collection_name="null-vectors")
    await c.ensure_collection_exists()
    if storage_type == "hash":
        with pytest.raises(NotImplementedError, match="no native null"):
            await c.upsert([record(vector=None)], generate_vectors=False)
        assert not await c.get()
        return
    await c.upsert([record(vector=None, tags=[])], generate_vectors=False)
    assert (await c.get(["one"], include_vectors=True))[0]["vector"] is None
    assert len(await c.get(filter=Filter("tags", "exists"))) == 1
    assert not await c.get(filter=Filter("tags", "contains", "red"))
    assert not [r async for r in await c.search(vector=[1.0, 0.0])]
    await c.upsert([record(tags=[""])], generate_vectors=False)
    assert len(await c.get(filter=Filter("tags", "contains", ""))) == 1


@pytest.mark.integration
async def test_live_json_partial_batch_failure_is_explicit(live_store, storage_type):
    if storage_type != "json":
        pytest.skip("JSON.SET can fail on a preexisting non-JSON key; HASH replacement uses DEL/HSET.")
    c = live_store.get_collection(dict, definition=definition(), collection_name="partial")
    await c.ensure_collection_exists()
    await c.redis_client.set(c.key_prefix + "bad", "wrong type")
    try:
        with pytest.raises(IntegrationException):
            await c.upsert([record("good"), record("bad")], generate_vectors=False)
        assert await c.get(["good"])
        assert await c.redis_client.get(c.key_prefix + "bad") == b"wrong type"
    finally:
        await c.redis_client.delete(c.key_prefix + "bad")


@pytest.mark.integration
async def test_live_1000_records_multiple_1536_vectors(live_store):
    c = live_store.get_collection(dict, definition=definition(dimensions=1536), collection_name="large")
    await c.ensure_collection_exists()
    vector = [0.01] * 1536
    keys = await c.upsert(
        [record(str(i), number=i, vector=vector, other_vector=vector) for i in range(1000)], generate_vectors=False
    )
    assert len(keys) == 1000
    assert len(await c.get(top=1000)) == 1000
    assert len((await c.get(["999"], include_vectors=True))[0]["other_vector"]) == 1536
    assert len([r async for r in await c.search(vector=vector, top=5, skip=10)]) == 5
    assert len(await c.get(filter=Filter("number", "gte", 990), top=20)) == 10
    await c.delete(keys)
    assert not await c.get(top=1)
