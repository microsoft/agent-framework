# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import copy
import gc
import importlib
import math
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from weakref import ref

import pytest
from agent_framework import (
    Filter,
    FilterGroup,
    SecretString,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    load_settings,
)
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException, SettingNotFoundError
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceExistsError, CosmosResourceNotFoundError

import agent_framework_azure_cosmos as cosmos_package
import agent_framework_azure_cosmos._vector_store as vector_store_module
from agent_framework_azure_cosmos import AzureCosmosSettings, CosmosCollection, CosmosStore
from agent_framework_azure_cosmos._vector_store import (
    _CosmosConnection,
    _normalize_policy_path,
    _property_access,
    _query_metadata_hook,
    _required_indexed_paths,
    _validate_existing_policies,
    _validate_key,
)

pytestmark = pytest.mark.filterwarnings("ignore::agent_framework._feature_stage.ExperimentalWarning")


def test_package_vector_exports_are_lazy() -> None:
    with patch.object(importlib, "import_module", wraps=importlib.import_module) as importer:
        package = importlib.reload(cosmos_package)
    importer.assert_not_called()
    assert "CosmosCollection" not in vars(package)
    assert package.CosmosCollection is CosmosCollection
    assert {"AzureCosmosSettings", "CosmosCollection", "CosmosStore"} <= set(dir(package))
    export_name = "CosmosStore"
    with (
        patch.object(importlib, "import_module", side_effect=ImportError("missing vector core")),
        pytest.raises(ImportError, match="core with vector-store support"),
    ):
        getattr(package, export_name)
    missing_name = "not_an_export"
    with pytest.raises(AttributeError):
        getattr(package, missing_name)


def _async_items(items: list[Any]) -> AsyncIterator[Any]:
    async def iterator() -> AsyncIterator[Any]:
        for item in items:
            yield item

    return iterator()


def _not_found() -> CosmosResourceNotFoundError:
    return CosmosResourceNotFoundError(message="missing")


def _http_error() -> CosmosHttpResponseError:
    return CosmosHttpResponseError(message="failed")


def _definition(
    *,
    index_kind: str = "default",
    distance: str = "cosine_similarity",
    dimensions: int = 3,
    vector_type: str = "float32",
    annotations: Mapping[str, Any] | None = None,
    second_vector: bool = False,
) -> VectorStoreCollectionDefinition:
    fields = [
        VectorStoreField("key", name="key", storage_name="id", type_="str"),
        VectorStoreField("data", name="text", storage_name="content", type_="str", is_indexed=True),
        VectorStoreField("data", name="count", type_="int", is_indexed=True),
        VectorStoreField("data", name="active", type_="bool", is_indexed=True),
        VectorStoreField("data", name="tags", type_="list", is_indexed=True),
        VectorStoreField("data", name="optional", type_="str", is_indexed=True),
        VectorStoreField(
            "vector",
            name="vector",
            storage_name="embedding",
            type_=vector_type,
            dimensions=dimensions,
            index_kind=index_kind,
            distance_function=distance,
            provider_annotations=annotations,
        ),
    ]
    if second_vector:
        fields.append(
            VectorStoreField(
                "vector",
                name="other_vector",
                storage_name="otherEmbedding",
                type_="uint8",
                dimensions=dimensions,
                index_kind="disk_ann",
                distance_function="euclidean_distance",
            )
        )
    return VectorStoreCollectionDefinition(fields, collection_name="items")


def _record(key: str = "one", *, include_vectors: bool = True) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": key,
        "content": "hello",
        "count": 2,
        "active": True,
        "tags": ["a", "b"],
        "optional": None,
    }
    if include_vectors:
        record["embedding"] = [1.0, 0.0, 0.0]
    return record


def _container_properties(collection: CosmosCollection[Any]) -> dict[str, Any]:
    return {
        "partitionKey": {"paths": ["/id"], "kind": "Hash"},
        "vectorEmbeddingPolicy": copy.deepcopy(collection._vector_policy),
        "indexingPolicy": copy.deepcopy(collection._indexing_policy),
    }


def _collection(
    *,
    definition: VectorStoreCollectionDefinition | None = None,
    query_results: list[Any] | None = None,
) -> tuple[CosmosCollection[dict[str, Any]], MagicMock]:
    container = MagicMock()
    container.id = "items"
    container.read = AsyncMock()
    container.upsert_item = AsyncMock(return_value={})
    container.read_item = AsyncMock()
    container.delete_item = AsyncMock(return_value=None)
    container.query_items = MagicMock(return_value=_async_items(query_results or []))
    collection = CosmosCollection(
        dict,
        definition=definition or _definition(),
        container_client=container,
    )
    container.read.return_value = _container_properties(collection)
    return collection, container


def test_settings_precedence(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / "cosmos.env"
    env_file.write_text(
        "AZURE_COSMOS_ENDPOINT=https://file.documents.azure.com/\n"
        "AZURE_COSMOS_DATABASE_NAME=file-db\n"
        "AZURE_COSMOS_CONTAINER_NAME=file-container\n"
        "AZURE_COSMOS_KEY=file-key\n"
    )
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://process.documents.azure.com/")
    monkeypatch.setenv("AZURE_COSMOS_DATABASE_NAME", "process-db")
    settings = load_settings(
        AzureCosmosSettings,
        env_prefix="AZURE_COSMOS_",
        endpoint="https://explicit.documents.azure.com/",
        env_file_path=str(env_file),
    )
    assert settings["endpoint"] == "https://explicit.documents.azure.com/"
    assert settings["database_name"] == "file-db"
    assert settings["container_name"] == "file-container"
    key = settings["key"]
    assert isinstance(key, SecretString)
    assert key.get_secret_value() == "file-key"


def test_owned_store_uses_masked_key_and_closes_only_client() -> None:
    client = MagicMock()
    client.close = AsyncMock()
    with patch.object(vector_store_module, "CosmosClient", return_value=client) as factory:
        store = CosmosStore(
            endpoint="https://account.documents.azure.com/",
            database_name="db",
            credential=SecretString("secret"),
        )
    assert store.database_name == "db"
    factory.assert_called_once()
    assert factory.call_args.kwargs["credential"] == "secret"
    assert "secret" not in repr(SecretString("secret"))


async def test_owned_store_closes_client() -> None:
    client = MagicMock()
    client.close = AsyncMock()
    with patch.object(vector_store_module, "CosmosClient", return_value=client):
        store = CosmosStore(
            endpoint="https://account.documents.azure.com/",
            database_name="db",
            credential="key",
        )
    await store.close()
    client.close.assert_awaited_once()
    await store.close()
    client.close.assert_awaited_once()


async def test_injected_clients_bypass_settings_and_remain_open() -> None:
    client = MagicMock()
    client.close = AsyncMock()
    database = MagicMock()
    database.id = "db"
    database.read = AsyncMock(return_value={})
    with patch.object(vector_store_module, "load_settings", side_effect=AssertionError("must not load settings")):
        client_store = CosmosStore(cosmos_client=client, database_name="db")
        database_store = CosmosStore(database_client=database)
        collection, container = _collection()
        await collection.collection_exists()
    await client_store.close()
    await database_store.close()
    await collection.close()
    client.close.assert_not_awaited()
    container.close.assert_not_called()


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"cosmos_client": MagicMock()}, "database_name"),
        ({"cosmos_client": MagicMock(), "database_client": MagicMock()}, "at most one"),
        ({"database_client": MagicMock(), "database_name": "db"}, "cannot be combined"),
        ({"database_client": MagicMock(), "create_database": True}, "create_database"),
        ({"cosmos_client": MagicMock(), "database_name": "db", "endpoint": "https://x"}, "cannot be combined"),
    ],
)
def test_store_rejects_conflicting_injection(kwargs: dict[str, Any], match: str) -> None:
    if "database_client" in kwargs:
        kwargs["database_client"].id = "db"
    with pytest.raises(ValueError, match=match):
        CosmosStore(**kwargs)


def test_container_injection_rejects_settings_and_name_mismatch() -> None:
    container = MagicMock()
    container.id = "actual"
    with pytest.raises(ValueError, match="cannot be combined"):
        CosmosCollection(
            dict,
            definition=_definition(),
            container_client=container,
            endpoint="https://account.documents.azure.com/",
        )
    with pytest.raises(ValueError, match="must match"):
        CosmosCollection(
            dict,
            definition=_definition(),
            collection_name="other",
            container_client=container,
        )


def test_missing_settings_and_invalid_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AZURE_COSMOS_ENDPOINT",
        "AZURE_COSMOS_DATABASE_NAME",
        "AZURE_COSMOS_CONTAINER_NAME",
        "AZURE_COSMOS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SettingNotFoundError):
        CosmosStore()
    with pytest.raises(TypeError, match="credential"):
        CosmosStore(
            endpoint="https://account.documents.azure.com/",
            database_name="db",
            credential=cast(Any, object()),
        )


def test_default_and_multi_vector_schema() -> None:
    collection, _ = _collection(definition=_definition(second_vector=True))
    embeddings = collection._vector_policy["vectorEmbeddings"]
    indexes = collection._indexing_policy["vectorIndexes"]
    assert embeddings == [
        {
            "path": "/embedding",
            "dataType": "float32",
            "distanceFunction": "cosine",
            "dimensions": 3,
        },
        {
            "path": "/otherEmbedding",
            "dataType": "uint8",
            "distanceFunction": "euclidean",
            "dimensions": 3,
        },
    ]
    assert indexes == [
        {"path": "/embedding", "type": "quantizedFlat"},
        {"path": "/otherEmbedding", "type": "diskANN"},
    ]
    assert {"path": "/embedding/*"} in collection._indexing_policy["excludedPaths"]
    assert {"path": "/otherEmbedding/*"} in collection._indexing_policy["excludedPaths"]


def test_vector_schema_tuning_annotations() -> None:
    definition = _definition(
        index_kind="disk_ann",
        vector_type="float",
        dimensions=512,
        annotations={
            "azure_cosmos": {
                "data_type": "int8",
                "quantizer_type": "spherical",
                "quantization_byte_size": 256,
                "indexing_search_list_size": 200,
            }
        },
    )
    collection, _ = _collection(definition=definition)
    assert collection._vector_policy["vectorEmbeddings"][0]["dataType"] == "int8"
    assert collection._indexing_policy["vectorIndexes"] == [
        {
            "path": "/embedding",
            "type": "diskANN",
            "quantizerType": "spherical",
            "quantizationByteSize": 256,
            "indexingSearchListSize": 200,
        }
    ]


def test_declared_data_storage_names_are_escaped_and_unindexed_paths_are_excluded() -> None:
    storage_name = 'content"] WHERE true --'
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="key", storage_name="id", type_="str"),
            VectorStoreField("data", name="text", storage_name=storage_name, type_="str", is_indexed=False),
            VectorStoreField("vector", name="vector", storage_name="embedding", dimensions=3, type_="float"),
        ],
        collection_name="items",
    )
    collection, _ = _collection(definition=definition)
    assert _property_access(storage_name) == 'c["content\\"] WHERE true --"]'
    assert {"path": '/"content\\"] WHERE true --"/*'} in collection._indexing_policy["excludedPaths"]
    with pytest.raises(ValueError, match="excluded from indexing"):
        collection._prepare_filter(Filter("text", "eq", "value"))


@pytest.mark.parametrize(
    "definition_factory,match",
    [
        (
            lambda: VectorStoreCollectionDefinition(
                [
                    VectorStoreField("key", name="key", type_="str"),
                    VectorStoreField("vector", name="vector", dimensions=3, type_="float"),
                ],
                collection_name="items",
            ),
            "storage name 'id'",
        ),
        (
            lambda: VectorStoreCollectionDefinition(
                [
                    VectorStoreField("key", name="key", storage_name="id", type_="int"),
                    VectorStoreField("vector", name="vector", dimensions=3, type_="float"),
                ],
                collection_name="items",
            ),
            "Key field type",
        ),
        (
            lambda: VectorStoreCollectionDefinition(
                [VectorStoreField("key", name="key", storage_name="id", type_="str")],
                collection_name="items",
            ),
            "at least one vector",
        ),
        (
            lambda: VectorStoreCollectionDefinition(
                [
                    VectorStoreField("key", name="key", storage_name="id", type_="str"),
                    VectorStoreField("vector", name="nested", storage_name="a.b", dimensions=3, type_="float"),
                ],
                collection_name="items",
            ),
            "top-level ASCII",
        ),
    ],
)
def test_invalid_collection_schema(
    definition_factory: Callable[[], VectorStoreCollectionDefinition],
    match: str,
) -> None:
    container = MagicMock()
    container.id = "items"
    with pytest.raises(ValueError, match=match):
        CosmosCollection(dict, definition=definition_factory(), container_client=container)


@pytest.mark.parametrize(
    "field_kwargs,exception,match",
    [
        ({"index_kind": "flat", "dimensions": 506}, ValueError, "at most 505"),
        ({"index_kind": "disk_ann", "dimensions": 4097}, ValueError, "at most 4096"),
        ({"index_kind": "hnsw"}, NotImplementedError, "index kind"),
        ({"distance": "cosine_distance"}, NotImplementedError, "distance"),
        ({"vector_type": "float16"}, ValueError, "Vector field"),
        ({"vector_type": "float64"}, ValueError, "Vector field"),
        (
            {"vector_type": "float", "annotations": {"azure_cosmos": {"data_type": "float16"}}},
            NotImplementedError,
            "float32, int8, or uint8",
        ),
        (
            {"annotations": {"azure_cosmos": {"unknown": 1}}},
            ValueError,
            "annotation",
        ),
        (
            {"annotations": {"azure_cosmos": {"data_type": 1}}},
            TypeError,
            "data_type",
        ),
        (
            {"index_kind": "flat", "annotations": {"azure_cosmos": {"quantizer_type": "product"}}},
            ValueError,
            "quantizer_type",
        ),
        (
            {"index_kind": "quantized_flat", "annotations": {"azure_cosmos": {"indexing_search_list_size": 100}}},
            ValueError,
            "diskANN",
        ),
        (
            {
                "index_kind": "disk_ann",
                "dimensions": 1536,
                "annotations": {"azure_cosmos": {"quantization_byte_size": 513}},
            },
            ValueError,
            "between 4 and 512",
        ),
        (
            {
                "index_kind": "disk_ann",
                "dimensions": 1536,
                "annotations": {"azure_cosmos": {"quantization_byte_size": 3}},
            },
            ValueError,
            "between 4 and 512",
        ),
        (
            {
                "index_kind": "disk_ann",
                "dimensions": 8,
                "annotations": {"azure_cosmos": {"quantization_byte_size": 9}},
            },
            ValueError,
            "between 4 and 8",
        ),
        (
            {
                "index_kind": "disk_ann",
                "annotations": {"azure_cosmos": {"indexing_search_list_size": 24}},
            },
            ValueError,
            "between 25 and 500",
        ),
    ],
)
def test_invalid_vector_schema(field_kwargs: dict[str, Any], exception: type[Exception], match: str) -> None:
    with pytest.raises(exception, match=match):
        _collection(definition=_definition(**field_kwargs))


@pytest.mark.parametrize(
    "vector_type,annotations,match",
    [
        ("float16", None, "Vector field"),
        ("float", {"azure_cosmos": {"data_type": "float16"}}, "float32, int8, or uint8"),
        ("float16", {"azure_cosmos": {"data_type": "float32"}}, "Vector field"),
    ],
)
def test_float16_schema_rejected_before_container_io(
    vector_type: str,
    annotations: Mapping[str, Any] | None,
    match: str,
) -> None:
    container = MagicMock()
    container.id = "items"
    container.read = AsyncMock()
    with pytest.raises((ValueError, NotImplementedError), match=match):
        CosmosCollection(
            dict,
            definition=_definition(vector_type=vector_type, annotations=annotations),
            container_client=container,
        )
    container.read.assert_not_awaited()
    container.query_items.assert_not_called()


def test_vector_schema_tuning_boundaries() -> None:
    collection, _ = _collection(
        definition=_definition(
            index_kind="disk_ann",
            dimensions=4,
            annotations={
                "azure_cosmos": {
                    "quantization_byte_size": 4,
                    "indexing_search_list_size": 25,
                }
            },
        )
    )
    assert collection._indexing_policy["vectorIndexes"] == [
        {
            "path": "/embedding",
            "type": "diskANN",
            "quantizationByteSize": 4,
            "indexingSearchListSize": 25,
        }
    ]


def test_policy_path_normalization_and_semantic_defaults() -> None:
    collection, _ = _collection(
        definition=_definition(
            index_kind="disk_ann",
            annotations={"azure_cosmos": {"indexing_search_list_size": 100}},
            second_vector=True,
        )
    )
    properties = _container_properties(collection)
    properties["vectorEmbeddingPolicy"]["vectorEmbeddings"].reverse()
    properties["indexingPolicy"]["excludedPaths"] = [
        {"path": '/"_etag"/?'},
        {"path": '/"embedding"/*'},
        {"path": '/"otherEmbedding"/*'},
    ]
    properties["indexingPolicy"]["vectorIndexes"][0]["quantizerType"] = "product"
    properties["indexingPolicy"]["vectorIndexes"].reverse()
    assert _normalize_policy_path('/"embedding"/*') == "/embedding/*"
    assert _normalize_policy_path('/"a/b"/*') == '/"a/b"/*'
    assert _normalize_policy_path('/"a/b"/*') != "/a/b/*"
    _validate_existing_policies(
        properties,
        vector_policy=collection._vector_policy,
        indexing_policy=collection._indexing_policy,
        required_indexed_paths=_required_indexed_paths(collection.definition),
    )


def test_quoted_policy_path_does_not_match_nested_path() -> None:
    definition = VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="key", storage_name="id", type_="str"),
            VectorStoreField("data", name="value", storage_name="a/b", type_="str", is_indexed=False),
            VectorStoreField("vector", name="vector", storage_name="embedding", dimensions=3, type_="float"),
        ],
        collection_name="items",
    )
    collection, _ = _collection(definition=definition)
    properties = _container_properties(collection)
    excluded_paths = properties["indexingPolicy"]["excludedPaths"]
    excluded_paths[1] = {"path": "/a/b/*"}
    with pytest.raises(ValueError, match="exclude all required"):
        _validate_existing_policies(
            properties,
            vector_policy=collection._vector_policy,
            indexing_policy=collection._indexing_policy,
            required_indexed_paths=_required_indexed_paths(collection.definition),
        )


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda p: p.update({"partitionKey": {"paths": ["/tenant"], "kind": "Hash"}}), "partition"),
        (lambda p: p.pop("vectorEmbeddingPolicy"), "embedding policy"),
        (
            lambda p: p["vectorEmbeddingPolicy"]["vectorEmbeddings"][0].update({"dimensions": 99}),
            "embedding policy",
        ),
        (lambda p: p["indexingPolicy"].update({"automatic": False}), "automatic"),
        (lambda p: p["indexingPolicy"].update({"includedPaths": []}), "root path"),
        (lambda p: p["indexingPolicy"].update({"excludedPaths": [{"path": "/_etag/?"}]}), "exclude"),
        (
            lambda p: p["indexingPolicy"]["excludedPaths"].append({"path": "/content/*"}),
            "must remain indexed",
        ),
        (lambda p: p["indexingPolicy"]["vectorIndexes"][0].update({"type": "flat"}), "index type"),
        (
            lambda p: p["indexingPolicy"]["vectorIndexes"][0].update({"quantizerType": "spherical"}),
            "quantizer",
        ),
    ],
)
def test_incompatible_existing_policy(mutate: Any, match: str) -> None:
    collection, _ = _collection()
    properties = _container_properties(collection)
    mutate(properties)
    with pytest.raises(ValueError, match=match):
        _validate_existing_policies(
            properties,
            vector_policy=collection._vector_policy,
            indexing_policy=collection._indexing_policy,
            required_indexed_paths=_required_indexed_paths(collection.definition),
        )


@pytest.mark.parametrize(
    "key,exception",
    [
        ("", ValueError),
        ("a/b", ValueError),
        ("a\\b", ValueError),
        ("a?b", ValueError),
        ("a#b", ValueError),
        ("a" * 1024, ValueError),
        (1, TypeError),
    ],
)
def test_key_validation(key: Any, exception: type[Exception]) -> None:
    with pytest.raises(exception):
        _validate_key(key)
    assert _validate_key("cafe-\N{SNOWMAN}") == "cafe-\N{SNOWMAN}"


@pytest.mark.parametrize(
    "vector,vector_type,exception",
    [
        ([1.0, 2.0], "float32", ValueError),
        ([1.0, math.inf, 0.0], "float32", ValueError),
        ([1.0, True, 0.0], "float32", TypeError),
        ([1, 2.0, 3], "int8", TypeError),
        ([1, 2, 128], "int8", ValueError),
        (b"123", "float32", TypeError),
    ],
)
async def test_full_batch_vector_preflight(vector: Any, vector_type: str, exception: type[Exception]) -> None:
    collection, container = _collection(definition=_definition(vector_type=vector_type))
    records = [_record("valid"), {**_record("late"), "embedding": vector}]
    if vector_type in ("int8", "uint8"):
        records[0]["embedding"] = [1, 0, 0]
    with pytest.raises(exception):
        await collection.upsert(records, generate_vectors=False)
    container.read.assert_not_awaited()
    container.upsert_item.assert_not_awaited()


async def test_full_batch_item_size_and_json_preflight() -> None:
    collection, container = _collection()
    oversized = {**_record("large"), "content": "x" * (2 * 1024 * 1024)}
    with pytest.raises(ValueError, match="2 MiB"):
        await collection.upsert([_record(), oversized], generate_vectors=False)
    with pytest.raises(ValueError, match="IEEE 754"):
        await collection.upsert([{**_record(), "count": 2**53}], generate_vectors=False)
    with pytest.raises(TypeError, match="declared type"):
        await collection.upsert([{**_record(), "active": 1}], generate_vectors=False)
    container.upsert_item.assert_not_awaited()


@pytest.mark.parametrize(
    "expression,clause,values",
    [
        (Filter("optional", "exists"), 'IS_DEFINED(c["optional"])', []),
        (
            Filter("optional", "is_null"),
            '(IS_DEFINED(c["optional"]) AND IS_NULL(c["optional"]))',
            [],
        ),
        (
            Filter("optional", "is_not_null"),
            '(IS_DEFINED(c["optional"]) AND NOT IS_NULL(c["optional"]))',
            [],
        ),
        (
            Filter("text", "eq", "O'Reilly"),
            '(IS_DEFINED(c["content"]) AND c["content"] = @filter_0)',
            ["O'Reilly"],
        ),
        (
            Filter("text", "ne", "x"),
            '(IS_DEFINED(c["content"]) AND (IS_NULL(c["content"]) OR c["content"] != @filter_0))',
            ["x"],
        ),
        (Filter("count", "eq", True), "false", []),
        (Filter("count", "ne", True), 'IS_DEFINED(c["count"])', []),
        (
            Filter("count", "gt", 1),
            '(IS_DEFINED(c["count"]) AND NOT IS_NULL(c["count"]) AND c["count"] > @filter_0)',
            [1],
        ),
        (
            Filter("count", "between", [1, 3]),
            (
                '(IS_DEFINED(c["count"]) AND NOT IS_NULL(c["count"]) '
                'AND c["count"] >= @filter_0 AND c["count"] <= @filter_1)'
            ),
            [1, 3],
        ),
        (
            Filter("text", "in", ["a", "b"]),
            '(IS_DEFINED(c["content"]) AND NOT IS_NULL(c["content"]) AND ARRAY_CONTAINS(@filter_0, c["content"]))',
            [["a", "b"]],
        ),
        (Filter("text", "in", []), "false", []),
        (
            Filter("text", "not_in", []),
            '(IS_DEFINED(c["content"]) AND NOT IS_NULL(c["content"]))',
            [],
        ),
        (
            Filter("tags", "contains", "a"),
            '(IS_ARRAY(c["tags"]) AND (ARRAY_CONTAINS(c["tags"], @filter_0)))',
            ["a"],
        ),
        (Filter("tags", "contains_any", []), "false", []),
        (Filter("tags", "contains_all", []), 'IS_ARRAY(c["tags"])', []),
        (
            Filter("tags", "contains_all", ["a", "b"]),
            '(IS_ARRAY(c["tags"]) AND (ARRAY_CONTAINS(c["tags"], @filter_0) AND ARRAY_CONTAINS(c["tags"], @filter_1)))',
            ["a", "b"],
        ),
        (
            Filter("tags", "contains_any", [None]),
            '(IS_ARRAY(c["tags"]) AND (ARRAY_CONTAINS(c["tags"], @filter_0)))',
            [None],
        ),
        (
            Filter("text", "in", [None, "a"]),
            '(IS_DEFINED(c["content"]) AND NOT IS_NULL(c["content"]) AND ARRAY_CONTAINS(@filter_0, c["content"]))',
            [[None, "a"]],
        ),
        (
            Filter("text", "starts_with", "he"),
            '(IS_STRING(c["content"]) AND STARTSWITH(c["content"], @filter_0))',
            ["he"],
        ),
        (
            Filter("text", "ends_with", "lo"),
            '(IS_STRING(c["content"]) AND ENDSWITH(c["content"], @filter_0))',
            ["lo"],
        ),
        (
            Filter("text", "contains_text", "ell"),
            '(IS_STRING(c["content"]) AND CONTAINS(c["content"], @filter_0))',
            ["ell"],
        ),
    ],
)
def test_filter_translation_matches_portable_semantics(
    expression: Filter,
    clause: str,
    values: list[Any],
) -> None:
    collection, _ = _collection()
    actual, parameters = collection._prepare_filter(expression)
    assert actual == clause
    assert actual is not None
    assert [parameter["value"] for parameter in parameters] == values
    if values == ["O'Reilly"]:
        assert "O'Reilly" not in actual


def test_filter_groups_and_rejections() -> None:
    collection, _ = _collection()
    group = FilterGroup(
        "and",
        [
            Filter("count", "gte", 1),
            FilterGroup("not", [Filter("active", "eq", False)]),
        ],
    )
    clause, parameters = collection._prepare_filter(group)
    assert clause == (
        '((IS_DEFINED(c["count"]) AND NOT IS_NULL(c["count"]) AND c["count"] >= @filter_0) '
        'AND (NOT (IS_DEFINED(c["active"]) AND c["active"] = @filter_1)))'
    )
    assert [item["value"] for item in parameters] == [1, False]
    for expression, exception in (
        (Filter("tags", "eq", {"a": 1}), NotImplementedError),
        (Filter("text", "in", [["nested"]]), NotImplementedError),
        (Filter("vector", "eq", 1), NotImplementedError),
        (Filter("text.child", "eq", "x"), NotImplementedError),
        (Filter("text", "provider.unknown", "x"), NotImplementedError),
        (Filter("active", "gt", True), NotImplementedError),
    ):
        with pytest.raises(exception):
            collection._prepare_filter(expression)


async def test_get_rejects_unsupported_filter_before_io() -> None:
    collection, container = _collection()
    with pytest.raises(NotImplementedError, match="nested"):
        await collection.get(filter=Filter("text.child", "eq", "x"))
    container.read.assert_not_awaited()
    container.query_items.assert_not_called()


async def test_ensure_existing_and_create_absent() -> None:
    definition = _definition()
    database = MagicMock()
    database.id = "db"
    database.read = AsyncMock(return_value={})
    existing = MagicMock()
    existing.read = AsyncMock()
    database.get_container_client.return_value = existing
    database.create_container = AsyncMock()
    collection = CosmosCollection(
        dict,
        definition=definition,
        database_client=database,
    )
    existing.read.return_value = _container_properties(collection)
    await collection.ensure_collection_exists()
    database.create_container.assert_not_awaited()

    existing.read.side_effect = [_not_found(), _container_properties(collection)]
    created = MagicMock()
    created.read = AsyncMock(return_value=_container_properties(collection))
    database.create_container.return_value = created
    collection._container_client = None
    collection._container_validated = False
    await collection.ensure_collection_exists()
    await_args = database.create_container.await_args
    assert await_args is not None
    kwargs = await_args.kwargs
    assert kwargs["partition_key"].path == "/id"
    assert kwargs["vector_embedding_policy"] == collection._vector_policy
    assert kwargs["indexing_policy"] == collection._indexing_policy


async def test_ensure_handles_create_race_and_revalidates_winner() -> None:
    database = MagicMock()
    database.id = "db"
    database.read = AsyncMock(return_value={})
    winner = MagicMock()
    winner.read = AsyncMock()
    database.get_container_client.return_value = winner
    database.create_container = AsyncMock(side_effect=CosmosResourceExistsError(message="race"))
    collection = CosmosCollection(dict, definition=_definition(), database_client=database)
    winner.read.side_effect = [_not_found(), _container_properties(collection)]
    await collection.ensure_collection_exists()
    assert winner.read.await_count == 2


async def test_database_creation_is_explicit() -> None:
    client = MagicMock()
    database = MagicMock()
    database.id = "db"
    database.read = AsyncMock(return_value={})
    client.create_database = AsyncMock(return_value=database)
    client.get_database_client.return_value = database
    connection = _CosmosConnection(
        cosmos_client=client,
        database_client=None,
        database_name="db",
        owns_client=False,
        create_database=True,
    )
    assert await connection.get_database() is database
    client.create_database.assert_awaited_once_with(id="db")
    assert await connection.get_database() is database
    client.create_database.assert_awaited_once()


async def test_database_creation_race_uses_existing_database() -> None:
    client = MagicMock()
    database = MagicMock()
    database.read = AsyncMock(return_value={})
    client.create_database = AsyncMock(side_effect=CosmosResourceExistsError(message="race"))
    client.get_database_client.return_value = database
    connection = _CosmosConnection(
        cosmos_client=client,
        database_client=None,
        database_name="db",
        owns_client=False,
        create_database=True,
    )
    assert await connection.get_database() is database
    database.read.assert_awaited_once()


async def test_collection_exists_and_delete_lifecycle() -> None:
    database = MagicMock()
    database.id = "db"
    database.read = AsyncMock(return_value={})
    container = MagicMock()
    container.read = AsyncMock(return_value={})
    database.get_container_client.return_value = container
    database.delete_container = AsyncMock(side_effect=_not_found())
    collection = CosmosCollection(dict, definition=_definition(), database_client=database)
    assert await collection.collection_exists()
    container.read.side_effect = _not_found()
    assert not await collection.collection_exists()
    await collection.ensure_collection_deleted()
    database.delete_container.assert_awaited_once_with("items")


async def test_upsert_point_get_and_delete() -> None:
    collection, container = _collection()
    records = [_record("one"), _record("two")]
    assert await collection.upsert(records, generate_vectors=False) == ["one", "two"]
    assert [call.kwargs["body"]["id"] for call in container.upsert_item.await_args_list] == ["one", "two"]

    container.read_item.side_effect = [_record("one"), _not_found(), _record("two")]
    found = await collection.get(["one", "missing", "two"])
    assert [item["key"] for item in found] == ["one", "two"]
    assert all("vector" not in item for item in found)
    calls = container.read_item.await_args_list
    assert [(call.kwargs["item"], call.kwargs["partition_key"]) for call in calls] == [
        ("one", "one"),
        ("missing", "missing"),
        ("two", "two"),
    ]
    await collection.delete(["one", "missing"])
    assert [(call.kwargs["item"], call.kwargs["partition_key"]) for call in container.delete_item.await_args_list] == [
        ("one", "one"),
        ("missing", "missing"),
    ]


async def test_partial_write_and_delete_failures_are_aligned() -> None:
    collection, container = _collection()
    container.upsert_item.side_effect = [{}, _http_error()]
    with pytest.raises(IntegrationException, match="1/2.*input index 1"):
        await collection.upsert([_record("one"), _record("two")], generate_vectors=False)
    container.delete_item.side_effect = [None, _http_error()]
    with pytest.raises(IntegrationException, match="1/2.*input index 1"):
        await collection.delete(["one", "two"])


async def test_filtered_get_query_is_parameterized_and_bounded() -> None:
    collection, container = _collection(query_results=[_record("one", include_vectors=False)])
    found = await collection.get(
        filter=Filter("text", "eq", "hello"),
        top=4,
        skip=2,
        order_by={"count": False},
    )
    assert [item["key"] for item in found] == ["one"]
    kwargs = container.query_items.call_args.kwargs
    query = kwargs["query"]
    assert "hello" not in query
    assert 'WHERE (IS_DEFINED(c["content"]) AND c["content"] = @filter_0)' in query
    assert 'ORDER BY c["count"] DESC OFFSET @skip LIMIT @top' in query
    assert kwargs["parameters"] == [
        {"name": "@filter_0", "value": "hello"},
        {"name": "@skip", "value": 2},
        {"name": "@top", "value": 4},
    ]


def test_order_by_validation() -> None:
    collection, _ = _collection()
    with pytest.raises(NotImplementedError, match="one order_by"):
        collection._prepare_order_by({"text": True, "count": False})
    with pytest.raises(TypeError, match="boolean"):
        collection._prepare_order_by(cast(Mapping[str, bool], {"text": 1}))
    with pytest.raises(ValueError, match="Unknown"):
        collection._prepare_order_by({"missing": True})
    with pytest.raises(ValueError, match="indexed"):
        collection._prepare_order_by({"vector": True})


async def test_cosine_search_query_threshold_filter_order_and_metadata() -> None:
    collection, container = _collection(
        query_results=[{"record": _record("one", include_vectors=False), "score": 0.75}]
    )

    def query_items(**kwargs: Any) -> AsyncIterator[Any]:
        kwargs["response_hook"](
            {
                "x-ms-request-charge": "3.5",
                "x-ms-activity-id": "activity",
                "x-ms-continuation": "",
            },
            None,
        )
        return _async_items([{"record": _record("one", include_vectors=False), "score": 0.75}])

    container.query_items.side_effect = query_items
    results = await collection.search(
        vector=[1.0, 0.0, 0.0],
        filter=Filter("count", "gte", 1),
        score_threshold=0.7,
        top=2,
    )
    rows = [row async for row in results]
    assert rows == [
        {
            "record": {
                "key": "one",
                "text": "hello",
                "count": 2,
                "active": True,
                "tags": ["a", "b"],
                "optional": None,
            },
            "score": 0.75,
        }
    ]
    query_kwargs = container.query_items.call_args.kwargs
    query = query_kwargs["query"]
    assert query.startswith("SELECT TOP @top VALUE")
    assert (
        'WHERE ((IS_DEFINED(c["count"]) AND NOT IS_NULL(c["count"]) AND c["count"] >= @filter_0) AND VectorDistance'
    ) in query
    assert " >= @threshold_" in query
    assert query.index("WHERE") < query.index("ORDER BY")
    assert " OFFSET " not in query
    assert [item["value"] for item in query_kwargs["parameters"]] == [
        [1.0, 0.0, 0.0],
        1,
        0.7,
        2,
    ]
    assert results.metadata == {
        "score_kind": "cosine_similarity",
        "score_direction": "higher_is_better",
        "request_charge": 3.5,
        "activity_id": "activity",
        "has_more_results": False,
    }


async def test_euclidean_search_uses_bounded_top_and_lazily_skips() -> None:
    collection, container = _collection(
        definition=_definition(distance="euclidean_distance"),
        query_results=[
            {"record": _record("skipped", include_vectors=False), "score": 0.0},
            {"record": _record("kept", include_vectors=False), "score": 0.25},
        ],
    )
    results = await collection.search(
        vector=[1.0, 0.0, 0.0],
        top=2,
        skip=1,
    )
    rows = [row async for row in results]
    assert rows == [
        {
            "record": {
                "key": "kept",
                "text": "hello",
                "count": 2,
                "active": True,
                "tags": ["a", "b"],
                "optional": None,
            },
            "score": 0.25,
        }
    ]
    kwargs = container.query_items.call_args.kwargs
    query = kwargs["query"]
    assert query.startswith("SELECT TOP @top VALUE")
    assert "@threshold_" not in query
    assert "OFFSET" not in query
    assert {"name": "@top", "value": 3} in kwargs["parameters"]
    assert results.metadata is not None
    assert results.metadata["score_kind"] == "euclidean_distance"
    assert results.metadata["score_direction"] == "lower_is_better"


async def test_euclidean_threshold_rejected_before_io() -> None:
    collection, container = _collection(definition=_definition(distance="euclidean_distance"))
    with pytest.raises(NotImplementedError, match="Omit score_threshold"):
        await collection.search(
            vector=[1.0, 0.0, 0.0],
            score_threshold=0.5,
        )
    container.read.assert_not_awaited()
    container.query_items.assert_not_called()


@pytest.mark.parametrize("distance", ["cosine_similarity", "dot_prod"])
async def test_similarity_threshold_is_inclusive_and_parameterized(distance: str) -> None:
    collection, container = _collection(
        definition=_definition(distance=distance),
        query_results=[{"record": _record("one", include_vectors=False), "score": 0.5}],
    )
    results = await collection.search(
        vector=[1.0, 0.0, 0.0],
        score_threshold=0.5,
    )
    assert [row async for row in results][0]["score"] == 0.5
    kwargs = container.query_items.call_args.kwargs
    assert " >= @threshold_" in kwargs["query"]
    assert {"name": "@threshold_1", "value": 0.5} in kwargs["parameters"]


async def test_search_options_are_validated_and_parameterized() -> None:
    collection, container = _collection(definition=_definition(index_kind="disk_ann"))
    results = await collection.search(
        vector=[1.0, 0.0, 0.0],
        operation_options={
            "search_list_size_multiplier": 10,
            "quantized_vector_list_multiplier": 5,
            "filter_priority": 0.5,
            "brute_force": True,
        },
    )
    assert [row async for row in results] == []
    kwargs = container.query_items.call_args.kwargs
    query = kwargs["query"]
    assert "searchListSizeMultiplier" not in query
    assert "@brute_force_" in query
    options = next(item["value"] for item in kwargs["parameters"] if item["name"].startswith("@vector_options_"))
    assert options == {
        "searchListSizeMultiplier": 10,
        "quantizedVectorListMultiplier": 5,
        "filterPriority": 0.5,
    }


@pytest.mark.parametrize(
    "options,match",
    [
        ({"unknown": 1}, "Unsupported"),
        ({"brute_force": 1}, "boolean"),
        ({"search_list_size_multiplier": 0}, "positive"),
        ({"filter_priority": 2}, "between 0 and 1"),
    ],
)
async def test_invalid_search_options(options: dict[str, Any], match: str) -> None:
    collection, container = _collection(definition=_definition(index_kind="disk_ann"))
    with pytest.raises((TypeError, ValueError), match=match):
        await collection.search(vector=[1.0, 0.0, 0.0], operation_options=options)
    container.query_items.assert_not_called()


async def test_flat_index_rejects_approximate_search_options() -> None:
    collection, _ = _collection(definition=_definition(index_kind="flat"))
    with pytest.raises(ValueError, match="flat"):
        await collection.search(
            vector=[1.0, 0.0, 0.0],
            operation_options={"quantized_vector_list_multiplier": 2},
        )


async def test_search_rejects_server_vectorization_and_invalid_score() -> None:
    collection, _ = _collection()
    with pytest.raises(NotImplementedError, match="server-side embedding"):
        await collection.search("text")
    with pytest.raises(ValueError, match="finite"):
        await collection.search(vector=[1.0, 0.0, 0.0], score_threshold=math.inf)
    with pytest.raises(ValueError, match="keyword-hybrid"):
        await collection.search(
            vector=[1.0, 0.0, 0.0],
            additional_property_name="text",
        )
    with pytest.raises(IntegrationInvalidResponseException, match="invalid score"):
        collection._get_score_from_result({"record": {}, "score": True})
    with pytest.raises(IntegrationInvalidResponseException, match="record projection"):
        collection._get_record_from_result({"record": 1})


def test_metadata_hook_is_bounded_and_rejects_bad_charge() -> None:
    metadata: dict[str, Any] = {
        "request_charge": 0.0,
        "activity_id": None,
        "has_more_results": False,
    }
    hook = _query_metadata_hook(metadata)
    with pytest.raises(IntegrationInvalidResponseException, match="request-charge"):
        hook(
            {
                "x-ms-request-charge": "bad",
                "x-ms-activity-id": "activity",
                "x-ms-continuation": "opaque",
            },
            None,
        )
    assert "opaque" not in repr(metadata)


async def test_store_children_share_database_and_do_not_reload_settings() -> None:
    database = MagicMock()
    database.id = "db"
    database.read = AsyncMock(return_value={})
    database.list_containers = MagicMock(return_value=_async_items([{"id": "one"}, {"id": 2}, {"id": "two"}]))
    existing = MagicMock()
    existing.read = AsyncMock(return_value={})
    database.get_container_client.return_value = existing
    database.delete_container = AsyncMock(side_effect=_not_found())
    with patch.object(vector_store_module, "load_settings", side_effect=AssertionError("must not reload settings")):
        store = CosmosStore(database_client=database)
        collection = store.get_collection(dict, definition=_definition())
    assert await store.list_collection_names() == ["one", "two"]
    assert await store.collection_exists("one")
    existing.read.side_effect = _not_found()
    assert not await store.collection_exists("missing")
    await store.ensure_collection_deleted("missing")
    assert collection._connection is store._connection
    await store.close()
    assert collection._closed
    database.close.assert_not_called()


async def test_store_does_not_retain_abandoned_collection_handles() -> None:
    database = MagicMock()
    database.id = "db"
    database.read = AsyncMock(return_value={})
    store = CosmosStore(database_client=database)
    collection = store.get_collection(dict, definition=_definition())
    collection_ref = ref(collection)
    assert len(store._collections) == 1
    del collection
    gc.collect()
    assert collection_ref() is None
    assert len(store._collections) == 0
    await store.close()


async def test_store_delete_invalidates_same_name_children_only() -> None:
    database = MagicMock()
    database.id = "db"
    database.read = AsyncMock(return_value={})
    lifecycle_container = MagicMock()
    lifecycle_container.read = AsyncMock(return_value={})
    database.get_container_client.return_value = lifecycle_container
    database.delete_container = AsyncMock(return_value=None)
    store = CosmosStore(database_client=database)
    first = store.get_collection(dict, definition=_definition())
    sibling = store.get_collection(dict, definition=_definition())
    other = store.get_collection(dict, definition=_definition(), collection_name="other")
    for collection in (first, sibling, other):
        collection._container_client = MagicMock()
        collection._container_validated = True

    await store.ensure_collection_deleted("items")

    assert first._container_client is None
    assert not first._container_validated
    assert sibling._container_client is None
    assert not sibling._container_validated
    assert other._container_client is not None
    assert other._container_validated
    await store.close()


async def test_child_delete_invalidates_same_name_sibling() -> None:
    database = MagicMock()
    database.id = "db"
    database.read = AsyncMock(return_value={})
    database.delete_container = AsyncMock(return_value=None)
    store = CosmosStore(database_client=database)
    first = store.get_collection(dict, definition=_definition())
    sibling = store.get_collection(dict, definition=_definition())
    first._container_client = MagicMock()
    first._container_validated = True
    sibling._container_client = MagicMock()
    sibling._container_validated = True

    await first.ensure_collection_deleted()

    assert first._container_client is None
    assert not first._container_validated
    assert sibling._container_client is None
    assert not sibling._container_validated
    await store.close()
