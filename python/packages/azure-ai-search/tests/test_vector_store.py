# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import gc
import inspect
import json
from collections.abc import AsyncIterator
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any
from unittest.mock import AsyncMock, Mock, patch
from weakref import ref

import pytest
from agent_framework import (
    Embedding,
    Filter,
    FilterGroup,
    GeneratedEmbeddings,
    Param,
    SecretString,
    VectorStoreCollectionDefinition,
    VectorStoreField,
    create_vector_search_tool,
    load_settings,
    vectorstoremodel,
)
from agent_framework._in_memory import _evaluate_filter
from agent_framework.exceptions import IntegrationException, IntegrationInvalidResponseException, SettingNotFoundError
from azure.core.credentials import AccessToken, AzureKeyCredential
from azure.core.exceptions import HttpResponseError, ResourceExistsError, ResourceNotFoundError
from azure.core.pipeline.transport import AioHttpTransport
from azure.search.documents import models as query_models
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    ScalarQuantizationCompression,
    SearchIndex,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import IndexAction, IndexDocumentsBatch, IndexingResult, VectorizableTextQuery

from agent_framework_azure_ai_search import (
    AzureAISearchCollection,
    AzureAISearchContextProvider,
    AzureAISearchSettings,
    AzureAISearchStore,
)
from agent_framework_azure_ai_search._vector_store import _MAX_BATCH_BYTES, _require_preview_request


@pytest.fixture(autouse=True)
def clear_azure_search_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ENDPOINT", "API_KEY", "INDEX_NAME", "KNOWLEDGE_BASE_NAME"):
        monkeypatch.delenv(f"AZURE_SEARCH_{name}", raising=False)


async def rows(records: list[Any]) -> AsyncIterator[Any]:
    for record in records:
        yield record


def definition(dimensions: int = 3, **vector_options: Any) -> VectorStoreCollectionDefinition:
    return VectorStoreCollectionDefinition(
        [
            VectorStoreField("key", name="key", storage_name="doc_id", type_="str"),
            VectorStoreField(
                "data",
                name="body",
                storage_name="content",
                type_="str",
                is_indexed=True,
                is_full_text_indexed=True,
            ),
            VectorStoreField(
                "data",
                name="price",
                type_="int",
                is_indexed=True,
                provider_annotations={"azure_ai_search": {"sortable": True}},
            ),
            VectorStoreField("data", name="active", type_="bool", is_indexed=True),
            VectorStoreField("data", name="tags", type_="list[str]", is_indexed=True),
            VectorStoreField(
                "vector",
                name="vector",
                storage_name="embedding",
                type_="float",
                dimensions=dimensions,
                **vector_options,
            ),
            VectorStoreField("vector", name="other", dimensions=dimensions, type_="float", index_kind="flat"),
        ],
        collection_name="test-index",
    )


def record(key: str = "one") -> dict[str, Any]:
    return {
        "key": key,
        "body": "quoted 'text'",
        "price": 3,
        "active": True,
        "tags": ["x"],
        "vector": [1.0, 0.0, 0.0],
        "other": None,
    }


def stored(key: str = "one", score: float = 0.9) -> dict[str, Any]:
    return {
        "doc_id": key,
        "content": "quoted 'text'",
        "price": 3,
        "active": True,
        "tags": ["x"],
        "embedding": [1.0, 0.0, 0.0],
        "other": None,
        "@search.score": score,
    }


@pytest.fixture
def client() -> Mock:
    result = Mock(spec=SearchClient)
    result.search = AsyncMock(side_effect=lambda **kwargs: rows([stored()]))
    result.upload_documents = AsyncMock(
        side_effect=lambda documents: [
            IndexingResult(key=d["doc_id"], succeeded=True, status_code=201) for d in documents
        ]
    )
    result.delete_documents = AsyncMock(
        side_effect=lambda documents: [
            IndexingResult(key=d["doc_id"], succeeded=True, status_code=200) for d in documents
        ]
    )
    return result


@pytest.fixture
def collection(client: Mock) -> AzureAISearchCollection[dict[str, Any]]:
    return AzureAISearchCollection(dict, definition=definition(), search_client=client)


def test_public_exports() -> None:
    from agent_framework.azure import AzureAISearchCollection as LazyCollection
    from agent_framework.azure import AzureAISearchStore as LazyStore

    assert LazyCollection is AzureAISearchCollection
    assert LazyStore is AzureAISearchStore
    assert AzureAISearchContextProvider is not None


@pytest.mark.parametrize("required", [False, True])
async def test_search_tool_param_without_default_preserves_unset(
    collection: AzureAISearchCollection,
    client: Mock,
    required: bool,
) -> None:
    param = Param("body", str, required=required)
    assert not param.has_default
    assert param.default is Param("other", str).default
    assert deepcopy(param) is param
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup("and", [Filter("active", "eq", True), Filter("body", "eq", param)]),
        top=Param("limit", int, default=2, minimum=1, maximum=10),
        skip=Param("offset", int, default=0, minimum=0, maximum=10),
        result_mapper=lambda result: result["record"]["body"],
    )
    assert tool.parameters()["required"] == (["query", "body"] if required else ["query"])
    results = await tool(query="hotel", body="O'Brien", limit=3, offset=1)
    assert results[0].text == "quoted 'text'"
    request = client.search.call_args.kwargs
    assert request["filter"] == "(active eq true and content eq 'O''Brien')"
    assert request["top"] == 3 and request["skip"] == 1
    assert request["vector_queries"][0].text == "hotel"
    assert request["vector_queries"][0].k_nearest_neighbors == 4
    if required:
        with pytest.raises(TypeError, match="Missing required.*body"):
            await tool(query="hotel")
        assert client.search.await_count == 1
    else:
        await tool(query="hotel")
        request = client.search.call_args.kwargs
        assert request["filter"] == "(active eq true)"
        assert request["top"] == 2 and request["skip"] == 0


@pytest.mark.parametrize("arguments", [{}, {"body": None}, {"body": "hotel"}])
async def test_search_tool_nullable_param_omits_only_optional_leaf(
    collection: AzureAISearchCollection,
    client: Mock,
    arguments: dict[str, Any],
) -> None:
    tool = create_vector_search_tool(
        collection,
        filter=FilterGroup(
            "and",
            [
                Filter("active", "eq", True),
                Filter("body", "eq", Param("body", str | None, default=None, omit_if_none=True)),
            ],
        ),
    )
    await tool(query="hotel", **arguments)
    assert client.search.call_args.kwargs["filter"] == (
        "(active eq true and content eq 'hotel')" if arguments.get("body") else "(active eq true)"
    )


def test_schema_aliases_metrics_and_two_vectors(collection: AzureAISearchCollection) -> None:
    index = collection.build_index()
    assert isinstance(index, SearchIndex)
    fields = {f.name: f for f in index.fields}
    assert fields["doc_id"].key is True
    assert fields["content"].searchable is True
    assert fields["price"].sortable is True
    assert fields["embedding"].vector_search_dimensions == 3
    assert fields["embedding"].type == "Collection(Edm.Single)"
    assert fields["tags"].type == "Collection(Edm.String)"
    assert index.vector_search is not None and index.vector_search.algorithms
    algorithm = index.vector_search.algorithms[0]
    assert isinstance(algorithm, HnswAlgorithmConfiguration) and algorithm.parameters is not None
    assert algorithm.parameters.metric == "cosine"
    assert index.vector_search.algorithms[1].kind == "exhaustiveKnn"


def test_native_vectorizer_compression_config(client: Mock) -> None:
    config = VectorSearch(
        profiles=[
            VectorSearchProfile(
                name="embedding_profile",
                algorithm_configuration_name="h",
                vectorizer_name="openai",
                compression_name="compressed",
            ),
            VectorSearchProfile(name="other_profile", algorithm_configuration_name="h"),
        ],
        algorithms=[HnswAlgorithmConfiguration(name="h")],
        compressions=[ScalarQuantizationCompression(compression_name="compressed")],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="openai",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url="https://example.openai.azure.com",
                    deployment_name="embedding",
                    model_name="text-embedding-3-small",
                ),
            )
        ],
    )
    collection = AzureAISearchCollection(dict, definition=definition(), search_client=client, vector_search=config)
    index = collection.build_index()
    assert index.vector_search is config
    assert config.profiles and config.profiles[0].compression_name == "compressed"


@pytest.mark.parametrize("kwargs", [{"index_kind": "unknown"}, {"distance_function": "manhattan"}])
def test_unsupported_schema(client: Mock, kwargs: dict) -> None:
    with pytest.raises(NotImplementedError):
        AzureAISearchCollection(dict, definition=definition(**kwargs), search_client=client)


def test_invalid_storage_identifier(client: Mock) -> None:
    invalid = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="key", storage_name="id) or true", type_="str")
    ])
    with pytest.raises(ValueError, match="identifiers"):
        AzureAISearchCollection(dict, definition=invalid, collection_name="test", search_client=client)


@pytest.mark.parametrize(
    "options",
    [
        {"sortable": True},
        {"facetable": True},
        {"analyzer_name": "standard.lucene"},
        {"analyzer_name": ""},
        {"search_analyzer_name": "standard.lucene"},
        {"index_analyzer_name": "standard.lucene"},
        {"synonym_map_names": ["synonyms"]},
    ],
)
def test_invalid_vector_field_attributes_rejected(client: Mock, options: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="cannot be filterable"):
        AzureAISearchCollection(
            dict,
            definition=definition(provider_annotations={"azure_ai_search": options}),
            search_client=client,
        )
    assert client.mock_calls == []


def test_filterable_vector_field_rejected(client: Mock) -> None:
    with pytest.raises(ValueError, match="cannot be filterable"):
        AzureAISearchCollection(dict, definition=definition(is_indexed=True), search_client=client)


@pytest.mark.parametrize(
    ("options", "retrievable"),
    [
        ({}, True),
        ({"retrievable": None}, True),
        ({"retrievable": True}, True),
        ({"retrievable": False}, False),
        ({"stored": False}, False),
        ({"stored": False, "retrievable": False}, False),
        ({"stored": True, "retrievable": False}, False),
        ({"sortable": False, "facetable": False, "analyzer_name": None, "synonym_map_names": []}, True),
    ],
)
async def test_vector_retrieval_schema_defaults(client: Mock, options: dict[str, Any], retrievable: bool) -> None:
    collection = AzureAISearchCollection(
        dict, definition=definition(provider_annotations={"azure_ai_search": options}), search_client=client
    )
    vector_field = next(field for field in collection.build_index().as_dict()["fields"] if field["name"] == "embedding")
    assert vector_field["retrievable"] is retrievable
    if "stored" in options:
        assert vector_field["stored"] is options["stored"]
    if retrievable:
        assert (await collection.get(["one"], include_vectors=True))[0]["vector"] == [1, 0, 0]
    else:
        with pytest.raises(ValueError, match="retrievable"):
            await collection.get(["one"], include_vectors=True)
        client.search.assert_not_called()


def test_unstored_retrievable_vector_conflict(client: Mock) -> None:
    with pytest.raises(ValueError, match="stored=False require retrievable=False"):
        AzureAISearchCollection(
            dict,
            definition=definition(provider_annotations={"azure_ai_search": {"stored": False, "retrievable": True}}),
            search_client=client,
        )


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (Filter("body", "eq", "O'Brien"), "content eq 'O''Brien'"),
        (Filter("price", "gte", 3), "price ge 3"),
        (Filter("active", "eq", True), "active eq true"),
        (Filter("price", "eq", True), "false"),
        (Filter("active", "eq", 1), "false"),
        (Filter("price", "between", [2, 4]), "(price ge 2 and price le 4)"),
        (Filter("body", "in", ["a", "b'b"]), "(content eq 'a' or content eq 'b''b')"),
        (Filter("price", "not_in", [1]), "(price ne null and not ((price eq 1)))"),
        (Filter("price", "in", []), "false"),
        (Filter("tags", "contains", "O'Brien"), "(tags/any(v: v eq 'O''Brien'))"),
        (Filter("tags", "contains_all", ["x", "y"]), "(tags/any(v: v eq 'x') and tags/any(v: v eq 'y'))"),
        (Filter("tags", "contains_any", []), "false"),
        (Filter("tags", "contains", 1), "(false)"),
        (
            Filter("body", "azure_ai_search.match", "cat' or dog"),
            "search.ismatch('cat'' or dog', 'content', 'simple', 'any')",
        ),
        (
            FilterGroup("not", [FilterGroup("or", [Filter("price", "lt", 1), Filter("price", "gt", 4)])]),
            "not ((price lt 1 or price gt 4))",
        ),
    ],
)
def test_prepare_filter(collection: AzureAISearchCollection, expression: Any, expected: str) -> None:
    assert collection._prepare_filter(expression) == expected


@pytest.mark.parametrize(
    ("document", "excluded", "expected"),
    [
        ({}, [1], False),
        ({"price": None}, [1], False),
        ({"price": 1}, [1], False),
        ({"price": 2}, [1], True),
        ({}, [], False),
        ({"price": None}, [], False),
        ({"price": 1}, [], True),
    ],
)
def test_not_in_null_and_missing_match_in_memory(
    collection: AzureAISearchCollection,
    document: dict[str, Any],
    excluded: list[int],
    expected: bool,
) -> None:
    expression = Filter("price", "not_in", excluded)
    assert _evaluate_filter(expression, document, collection.definition) is expected
    assert collection._prepare_filter(expression) == (
        "(price ne null and not ((price eq 1)))" if excluded else "(price ne null and not (false))"
    )


async def test_get_and_search_share_prepare_filter(collection: AzureAISearchCollection, client: Mock) -> None:
    expression = Filter("body", "eq", "O'Brien")
    with patch.object(collection, "_prepare_filter", wraps=collection._prepare_filter) as prepare_filter:
        await collection.get(filter=expression)
        await collection.search(vector=[1, 0, 0], filter=expression)
    assert prepare_filter.call_count == 2
    assert all(call.kwargs["filter"] == "content eq 'O''Brien'" for call in client.search.call_args_list)


@pytest.mark.parametrize("operation", ["get", "search"])
async def test_read_validation_precedes_query_identity(
    collection: AzureAISearchCollection,
    client: Mock,
    operation: str,
) -> None:
    identity = Mock()
    identity.get_token = Mock(side_effect=AssertionError("Invalid filters must not obtain credentials"))
    collection.query_source_credential = identity
    expression = Filter("body", "contains_text", "hotel")
    with pytest.raises(NotImplementedError, match="literal 'contains_text'"):
        if operation == "get":
            await collection.get(filter=expression)
        else:
            await collection.search(vector=[1, 0, 0], filter=expression)
    identity.get_token.assert_not_called()
    client.search.assert_not_called()


@pytest.mark.parametrize(
    "expression",
    [
        Filter("body", "ne", "x"),
        Filter("body", "exists"),
        Filter("body", "is_null"),
        Filter("body", "is_not_null"),
        Filter("body", "contains_text", "cat"),
        Filter("body", "starts_with", "cat"),
        Filter("body", "ends_with", "cat"),
        Filter("body", "in", [None]),
        Filter("tags", "contains_all", []),
        Filter("tags", "eq", ["a"]),
        Filter("body", "azure_ai_search.unsupported", "x"),
    ],
)
async def test_unsupported_filters_fail_before_io(
    collection: AzureAISearchCollection,
    client: Mock,
    expression: Any,
) -> None:
    with pytest.raises(NotImplementedError):
        await collection.get(filter=expression)
    client.search.assert_not_called()


async def test_batch_crud_and_storage_roundtrip(collection: AzureAISearchCollection, client: Mock) -> None:
    original = record()
    assert await collection.upsert([original], generate_vectors=False) == ["one"]
    sent = client.upload_documents.call_args.args[0][0]
    assert sent["embedding"] == [1, 0, 0]
    assert sent["other"] is None
    assert sent["content"] == original["body"]
    assert "vector" not in sent
    assert original == record()
    found = await collection.get(["one", "absent", "one"], include_vectors=True)
    assert found == [original, original]
    assert await collection.get([]) == []
    await collection.delete(["one", "absent"])
    assert client.delete_documents.call_args.args[0] == [{"doc_id": "one"}, {"doc_id": "absent"}]


async def test_filtered_get_order_and_projection(collection: AzureAISearchCollection, client: Mock) -> None:
    values = await collection.get(filter=Filter("price", "gte", 1), top=4, skip=2, order_by={"price": False})
    assert "vector" not in values[0]
    options = client.search.call_args.kwargs
    assert options["filter"] == "price ge 1"
    assert options["order_by"] == ["price desc"]
    assert options["top"] == 4 and options["skip"] == 2
    assert "embedding" not in options["select"]


@pytest.mark.parametrize("direction", ["descending", 0, 1, None])
async def test_order_direction_requires_bool_before_identity(
    collection: AzureAISearchCollection, client: Mock, direction: Any
) -> None:
    identity = Mock()
    collection.query_source_credential = identity
    with pytest.raises(TypeError, match="must be a boolean"):
        await collection.get(order_by={"price": direction})
    client.search.assert_not_called()
    identity.get_token.assert_not_called()


@pytest.mark.parametrize(("direction", "expected"), [(True, "price asc"), (False, "price desc")])
async def test_boolean_order_directions(
    collection: AzureAISearchCollection, client: Mock, direction: bool, expected: str
) -> None:
    await collection.get(order_by={"price": direction})
    assert client.search.call_args.kwargs["order_by"] == [expected]


async def test_empty_batches_do_not_call_sdk(collection: AzureAISearchCollection, client: Mock) -> None:
    assert await collection.upsert([], generate_vectors=False) == []
    await collection.delete([])
    with pytest.raises(ValueError, match="greater than zero"):
        await collection.get(top=0)
    with pytest.raises(ValueError, match="greater than zero"):
        await collection.search(vector=[1, 0, 0], top=0)
    client.upload_documents.assert_not_called()
    client.delete_documents.assert_not_called()
    client.search.assert_not_called()


@pytest.mark.parametrize("key", ["", "a') or true or ('b", "a/b", "a b", "\u00e9", "_first", "x" * 1025])
@pytest.mark.parametrize("operation", ["upsert", "get", "delete"])
async def test_invalid_late_key_rejected_before_batch_io(
    collection: AzureAISearchCollection, client: Mock, key: str, operation: str
) -> None:
    keys = [str(i) for i in range(1001)] + [key]
    error_type = IntegrationException if operation == "delete" else ValueError
    with pytest.raises(error_type, match="1-1024 ASCII"):
        if operation == "upsert":
            await collection.upsert([record(item) for item in keys], generate_vectors=False)
        elif operation == "get":
            await collection.get(keys)
        else:
            await collection.delete(keys)
    client.search.assert_not_called()
    client.upload_documents.assert_not_called()
    client.delete_documents.assert_not_called()


@pytest.mark.parametrize("key", ["A0-z_=", "-", "=", "x" * 1024])
async def test_valid_key_boundaries_roundtrip(collection: AzureAISearchCollection, client: Mock, key: str) -> None:
    client.search.side_effect = lambda **kwargs: rows([stored(key)])
    assert await collection.upsert([record(key)], generate_vectors=False) == [key]
    assert await collection.get([key], include_vectors=True) == [record(key)]
    await collection.delete([key])
    assert client.delete_documents.call_args.args[0] == [{"doc_id": key}]


@pytest.mark.parametrize("operation", ["upsert", "delete"])
async def test_partial_batch_failure_is_not_success(
    collection: AzureAISearchCollection,
    client: Mock,
    operation: str,
) -> None:
    response = [IndexingResult(key="one", succeeded=False, status_code=503, error_message="sensitive body")]
    if operation == "upsert":
        client.upload_documents.side_effect = None
        client.upload_documents.return_value = response
    else:
        client.delete_documents.side_effect = None
        client.delete_documents.return_value = response
    with pytest.raises(IntegrationException, match="not atomic") as error:
        if operation == "upsert":
            await collection.upsert([record()], generate_vectors=False)
        else:
            await collection.delete(["one"])
    assert "sensitive body" not in str(error.value)


async def test_missing_indexing_result_rejected(collection: AzureAISearchCollection, client: Mock) -> None:
    client.upload_documents.side_effect = None
    client.upload_documents.return_value = []
    with pytest.raises(IntegrationInvalidResponseException):
        await collection.upsert([record()], generate_vectors=False)


async def test_indexing_results_matched_by_key_not_response_order(
    collection: AzureAISearchCollection,
    client: Mock,
) -> None:
    client.upload_documents.side_effect = None
    client.upload_documents.return_value = [
        IndexingResult(key="two", succeeded=True, status_code=201),
        IndexingResult(key="one", succeeded=True, status_code=201),
    ]
    assert await collection.upsert([record("one"), record("two")], generate_vectors=False) == ["one", "two"]


async def test_large_batch_multiple_1536_vectors(client: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    collection = AzureAISearchCollection(dict, definition=definition(1536), search_client=client)
    first = [float(i % 7) / 7 for i in range(1536)]
    second = [float(i % 11) / 11 for i in range(1536)]
    records = [{**record(str(i)), "vector": first, "other": second} for i in range(1000)]
    assert len(await collection.upsert(records, generate_vectors=False)) == 1000
    batches = [call.args[0] for call in client.upload_documents.call_args_list]
    assert len(batches) > 1
    assert all(len(batch) <= 1000 for batch in batches)
    assert all(size <= _MAX_BATCH_BYTES for size in await capture_upload_sizes(monkeypatch, batches))
    documents = [document for batch in batches for document in batch]
    assert len(documents) == 1000
    assert all(len(d["embedding"]) == len(d["other"]) == 1536 for d in documents)
    assert documents[999]["embedding"] == first and documents[999]["other"] == second


async def test_service_batch_action_limit(collection: AzureAISearchCollection, client: Mock) -> None:
    assert len(await collection.upsert([record(str(i)) for i in range(1001)], generate_vectors=False)) == 1001
    assert [len(call.args[0]) for call in client.upload_documents.call_args_list] == [1000, 1]
    await collection.delete([str(i) for i in range(1001)])
    assert [len(call.args[0]) for call in client.delete_documents.call_args_list] == [1000, 1]
    await collection.get([str(i) for i in range(201)])
    assert client.search.call_count == 3


@pytest.mark.parametrize("bad_vector", [[1, 2], "source text", b"\x01\x02", {"indices": [1], "values": [0.5]}])
async def test_unsupported_write_representation_no_side_effects(
    collection: AzureAISearchCollection,
    client: Mock,
    bad_vector: Any,
) -> None:
    with pytest.raises((ValueError, TypeError)):
        await collection.upsert([record("valid"), {**record("invalid"), "vector": bad_vector}], generate_vectors=False)
    client.upload_documents.assert_not_called()


@pytest.mark.parametrize(
    ("edm_type", "bad_value"),
    [
        ("Collection(Edm.Single)", True),
        ("Collection(Edm.Single)", "bad"),
        ("Collection(Edm.Single)", None),
        ("Collection(Edm.Single)", float("nan")),
        ("Collection(Edm.Single)", float("inf")),
        ("Collection(Edm.Single)", -float("inf")),
        ("Collection(Edm.Single)", 3.402823466385289e38),
        ("Collection(Edm.Single)", -(10**100)),
        ("Collection(Edm.Half)", 65505.0),
        ("Collection(Edm.Half)", -65505.0),
        ("Collection(Edm.Int16)", 32768),
        ("Collection(Edm.Int16)", -32769),
        ("Collection(Edm.Int16)", 1.0),
        ("Collection(Edm.SByte)", 128),
        ("Collection(Edm.SByte)", -129),
        ("Collection(Edm.SByte)", True),
    ],
)
async def test_invalid_late_vector_element_preflight(client: Mock, edm_type: str, bad_value: Any) -> None:
    collection = AzureAISearchCollection(
        dict,
        definition=definition(provider_annotations={"azure_ai_search": {"type": edm_type}}),
        search_client=client,
    )
    records = [{**record(str(i)), "vector": [1, 0, 0]} for i in range(1001)]
    records.append({**record("bad"), "vector": [bad_value, 0, 0]})
    with pytest.raises((TypeError, ValueError), match="vector"):
        await collection.upsert(records, generate_vectors=False)
    client.upload_documents.assert_not_called()


async def test_secondary_vector_elements_validated(collection: AzureAISearchCollection, client: Mock) -> None:
    with pytest.raises(ValueError, match="finite"):
        await collection.upsert([record(), {**record("bad"), "other": [float("nan"), 0, 0]}], generate_vectors=False)
    client.upload_documents.assert_not_called()


@pytest.mark.parametrize(
    ("edm_type", "vector"),
    [
        ("Collection(Edm.Single)", [-3.4028234663852886e38, 0.0, 3.4028234663852886e38]),
        ("Collection(Edm.Half)", [-65504.0, 0, 65504.0]),
        ("Collection(Edm.Int16)", [-32768, 0, 32767]),
        ("Collection(Edm.SByte)", [-128, 0, 127]),
    ],
)
async def test_valid_vector_edm_boundaries(client: Mock, edm_type: str, vector: list[int | float]) -> None:
    collection = AzureAISearchCollection(
        dict,
        definition=definition(provider_annotations={"azure_ai_search": {"type": edm_type}}),
        search_client=client,
    )
    assert await collection.upsert([{**record(), "vector": vector}], generate_vectors=False) == ["one"]
    assert client.upload_documents.call_args.args[0][0]["embedding"] == vector


@pytest.mark.parametrize("bad_value", [True, "bad", None, float("nan"), float("inf"), 3.5e38, -(10**100)])
async def test_invalid_query_vector_before_identity(
    collection: AzureAISearchCollection, client: Mock, bad_value: Any
) -> None:
    identity = Mock()
    collection.query_source_credential = identity
    with pytest.raises((TypeError, ValueError), match="vector"):
        await collection.search(vector=[bad_value, 0, 0])
    client.search.assert_not_called()
    identity.get_token.assert_not_called()


@pytest.mark.parametrize("edm_type", ["Collection(Edm.SByte)", "Collection(Edm.Int16)", "Collection(Edm.Half)"])
async def test_query_float_contract_independent_of_stored_edm(client: Mock, edm_type: str) -> None:
    collection = AzureAISearchCollection(
        dict,
        definition=definition(provider_annotations={"azure_ai_search": {"type": edm_type}}),
        search_client=client,
    )
    vector = [100000.5, -100000.5, 0.0]
    await collection.search(vector=vector)
    assert client.search.call_args.kwargs["vector_queries"][0].vector == vector
    await collection.search("provider-vectorized text")
    assert isinstance(client.search.call_args.kwargs["vector_queries"][0], VectorizableTextQuery)


@pytest.mark.parametrize("operation", ["upsert", "search"])
async def test_generated_vector_elements_validated(
    collection: AzureAISearchCollection, client: Mock, operation: str
) -> None:
    generator = Mock()
    generator.get_embeddings = AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[float("inf"), 0, 0])]))
    collection.embedding_generator = generator
    with pytest.raises(ValueError, match="finite"):
        if operation == "upsert":
            await collection.upsert([{**record(), "vector": "source"}], generate_vectors=["vector"])
        else:
            await collection.search("source")
    client.upload_documents.assert_not_called()
    client.search.assert_not_called()


async def test_selected_generation_preserves_other_vectors(collection: AzureAISearchCollection, client: Mock) -> None:
    generator = Mock()
    generator.get_embeddings = AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[0.0, 1.0, 0.0])]))
    collection.embedding_generator = generator
    source = {**record(), "vector": "source text"}
    await collection.upsert([source], generate_vectors=["vector"])
    generator.get_embeddings.assert_awaited_once_with(["source text"], options={"dimensions": 3})
    assert client.upload_documents.call_args.args[0][0]["embedding"] == [0, 1, 0]
    assert client.upload_documents.call_args.args[0][0]["other"] is None
    assert source["vector"] == "source text"


async def test_generate_all_vectors_and_validate_generated_dimensions(client: Mock) -> None:
    first = Mock()
    first.get_embeddings = AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[0.0, 1.0, 0.0])]))
    default = Mock()
    default.get_embeddings = AsyncMock(return_value=GeneratedEmbeddings([Embedding(vector=[0.0, 0.0, 1.0])]))
    collection = AzureAISearchCollection(
        dict,
        definition=definition(embedding_generator=first),
        search_client=client,
        embedding_generator=default,
    )
    original = {**record(), "vector": "first source", "other": "second source"}
    await collection.upsert([original], generate_vectors=True)
    first.get_embeddings.assert_awaited_once_with(["first source"], options={"dimensions": 3})
    default.get_embeddings.assert_awaited_once_with(["second source"], options={"dimensions": 3})
    uploaded = client.upload_documents.call_args.args[0][0]
    assert uploaded["embedding"] == [0, 1, 0] and uploaded["other"] == [0, 0, 1]
    first.get_embeddings.return_value = GeneratedEmbeddings([Embedding(vector=[1.0, 2.0])])
    with pytest.raises(ValueError, match="dimensions"):
        await collection.upsert([original], generate_vectors=True)
    assert client.upload_documents.call_count == 1


async def test_query_dimension_mismatch_before_dispatch(collection: AzureAISearchCollection, client: Mock) -> None:
    with pytest.raises(ValueError, match="dimensions"):
        await collection.search(vector=[1, 2], vector_property_name="vector")
    client.search.assert_not_called()


async def test_registered_model_decoding(client: Mock) -> None:
    @vectorstoremodel
    @dataclass
    class Document:
        key: Annotated[str, VectorStoreField("key", storage_name="doc_id")]
        body: Annotated[str, VectorStoreField("data", storage_name="content")]
        vector: Annotated[list[float] | None, VectorStoreField("vector", storage_name="embedding", dimensions=3)] = None

    collection = AzureAISearchCollection(Document, collection_name="test", search_client=client)
    assert await collection.get(["one"]) == [Document(key="one", body="quoted 'text'")]
    results = [r async for r in await collection.search(vector=[1, 0, 0], include_vectors=True)]
    assert results[0]["record"].vector == [1, 0, 0]


async def test_search_projection_score_and_native_paging(collection: AzureAISearchCollection, client: Mock) -> None:
    results = await collection.search(vector=[1, 0, 0], top=2, skip=3, filter=Filter("price", "eq", 3))
    responses = [r async for r in results]
    assert responses[0]["score"] == 0.9
    assert "vector" not in responses[0]["record"]
    options = client.search.call_args.kwargs
    assert options["vector_queries"][0].k_nearest_neighbors == 5
    assert options["vector_queries"][0].fields == "embedding"
    assert options["top"] == 2 and options["skip"] == 3
    assert options["vector_filter_mode"] == "preFilter"
    assert options["filter"] == "price eq 3"


async def test_hybrid_and_integrated_vectorization(collection: AzureAISearchCollection, client: Mock) -> None:
    await collection.search(
        "find cats",
        search_type="keyword_hybrid",
        additional_property_name="body",
        vector_property_name="other",
        operation_options={"weight": 2, "exhaustive": True},
    )
    options = client.search.call_args.kwargs
    query = options["vector_queries"][0]
    assert isinstance(query, VectorizableTextQuery)
    assert query.fields == "other"
    assert query.text == "find cats"
    assert query.weight == 2 and query.exhaustive is True
    assert options["search_text"] == "find cats" and options["search_fields"] == ["content"]


@pytest.mark.parametrize(
    "options",
    [
        {"filter": "true"},
        {"vector_queries": []},
        {"filter_override": "true"},
        {"enable_elevated_read": True},
        {"top": 100},
        {"weight": 0},
        {"oversampling": 0.5},
        {"k_nearest_neighbors": 1},
        {"vector_filter_mode": "unknown"},
    ],
)
async def test_invalid_search_options_fail_closed(
    collection: AzureAISearchCollection,
    client: Mock,
    options: dict,
) -> None:
    with pytest.raises(ValueError):
        await collection.search(vector=[1, 0, 0], top=3, operation_options=options)
    client.search.assert_not_called()


async def test_hybrid_score_threshold_always_rejected(collection: AzureAISearchCollection, client: Mock) -> None:
    with pytest.raises(NotImplementedError, match="pure-vector"):
        await collection.search("text", vector=[1, 0, 0], search_type="keyword_hybrid", score_threshold=0.3)
    client.search.assert_not_called()


async def test_preview_opt_in_required(collection: AzureAISearchCollection, client: Mock) -> None:
    with pytest.raises(NotImplementedError):
        await collection.search(vector=[1, 0, 0], score_threshold=0.7)
    with pytest.raises(NotImplementedError):
        await collection.search(vector=[1, 0, 0], operation_options={"vector_filter_mode": "strictPostFilter"})
    collection.query_source_credential = Mock()
    with pytest.raises(NotImplementedError):
        await collection.get(["one"])
    client.search.assert_not_called()


@pytest.mark.skipif(not hasattr(query_models, "SearchScoreThreshold"), reason="Preview SDK only")
async def test_native_threshold_models_and_identity(client: Mock) -> None:
    identity = Mock()
    identity.get_token = Mock(return_value=AccessToken("test-token", 9999999999))
    collection = AzureAISearchCollection(
        dict, definition=definition(), search_client=client, allow_preview=True, query_source_credential=identity
    )
    await collection.search(vector=[1, 0, 0], score_threshold=0.7, skip=2)
    options = client.search.call_args.kwargs
    assert options["vector_queries"][0].threshold.value == 0.7
    assert options["vector_queries"][0].threshold.kind == "searchScore"
    assert options["query_source_authorization"] == "test-token"
    assert options["raw_request_hook"].func is _require_preview_request
    assert options["raw_request_hook"].keywords["capabilities"] == ("vector_threshold", "query_identity")
    assert options["skip"] == 2
    identity.get_token.assert_called_once_with("https://search.azure.com/.default")
    with pytest.raises(ValueError, match="cannot be combined"):
        await collection.search(
            vector=[1, 0, 0],
            score_threshold=0.7,
            operation_options={"vector_threshold": options["vector_queries"][0].threshold},
        )


@pytest.mark.parametrize("version", ["2026-04-01", "", "2026-04-01&api-version=2026-08-01-preview"])
def test_preview_gate_checks_actual_sdk_request(version: str) -> None:
    request = SimpleNamespace(http_request=SimpleNamespace(url=f"https://example/docs/search?api-version={version}"))
    with pytest.raises(NotImplementedError, match="never overrides"):
        _require_preview_request(request, capabilities=("vector_threshold",))


async def test_owned_and_borrowed_clients(client: Mock) -> None:
    index_client = Mock(spec=SearchIndexClient)
    index_client.get_search_client.return_value = client
    async with AzureAISearchStore(index_client=index_client) as store:
        collection = store.get_collection(dict, definition=definition())
        await collection.close()
        client.close.assert_awaited_once()
    client.close.assert_awaited_once()
    index_client.close.assert_not_awaited()
    with pytest.raises(RuntimeError):
        store.get_collection(dict, definition=definition())
    async with AzureAISearchCollection(dict, definition=definition(), search_client=client):
        pass
    client.close.assert_awaited_once()
    async with AzureAISearchCollection(dict, definition=definition(), search_client=client, managed_client=True):
        pass
    assert client.close.await_count == 2


@pytest.mark.parametrize("managed", [False, True])
async def test_store_releases_closed_collections_but_retains_open_clients(managed: bool) -> None:
    index_client = Mock(spec=SearchIndexClient)
    index_client.get_search_client.side_effect = lambda *args, **kwargs: Mock(spec=SearchClient)
    store = AzureAISearchStore(index_client=index_client, managed_client=managed)
    active = store.get_collection(dict, definition=definition())
    active_client = active.search_client
    assert isinstance(active_client, Mock)
    active_ref = ref(active)
    del active
    gc.collect()
    assert active_ref() is not None

    for _ in range(3):
        generator = Mock()
        async with store.get_collection(dict, definition=definition(), embedding_generator=generator) as collection:
            collection_ref = ref(collection)
            generator_ref = ref(generator)
            client_ref = ref(collection.search_client)
            assert len(store._collections) == 2
        await collection.close()
        assert isinstance(collection.search_client, Mock)
        collection.search_client.close.assert_awaited_once()
        generator.close.assert_not_called()
        assert len(store._collections) == 1
        del collection, generator
        gc.collect()
        assert collection_ref() is None
        assert generator_ref() is None
        assert client_ref() is None
        active_client.close.assert_not_called()

    await store.close()
    await store.close()
    active_client.close.assert_awaited_once()
    assert index_client.close.await_count == int(managed)
    assert not store._collections
    gc.collect()
    assert active_ref() is None


@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_store_releases_collection_after_close_error(client: Mock, error: type[BaseException]) -> None:
    index_client = Mock(spec=SearchIndexClient)
    index_client.get_search_client.return_value = client
    client.close.side_effect = error("close failure")
    store = AzureAISearchStore(index_client=index_client, managed_client=True)
    collection = store.get_collection(dict, definition=definition())
    with pytest.raises(error, match="close failure"):
        await collection.close()
    assert not store._collections
    await collection.close()
    await store.close()
    client.close.assert_awaited_once()
    index_client.close.assert_awaited_once()


async def test_close_remaining_clients_if_one_close_fails(client: Mock) -> None:
    index_client = Mock(spec=SearchIndexClient)
    other_client = Mock(spec=SearchClient)
    index_client.get_search_client.side_effect = [other_client, client]
    client.close.side_effect = RuntimeError("close failure")
    store = AzureAISearchStore(index_client=index_client, managed_client=True)
    store.get_collection(dict, definition=definition())
    store.get_collection(dict, definition=definition())
    with pytest.raises(RuntimeError, match="close failure"):
        await store.close()
    client.close.assert_awaited_once()
    other_client.close.assert_awaited_once()
    index_client.close.assert_awaited_once()
    assert not store._collections


async def test_lifecycle_and_alias_safety(client: Mock) -> None:
    index_client = Mock(spec=SearchIndexClient)
    collection = AzureAISearchCollection(dict, definition=definition(), search_client=client, index_client=index_client)
    index_client.get_index.side_effect = ResourceNotFoundError()
    assert not await collection.collection_exists()
    await collection.ensure_collection_exists()
    index_client.create_index.assert_awaited_once()
    index_client.create_index.side_effect = ResourceExistsError()
    await collection.ensure_collection_exists()
    index_client.get_index.side_effect = None
    await collection.ensure_collection_exists()
    assert index_client.create_index.await_count == 2
    index_client.delete_index.side_effect = ResourceNotFoundError()
    await collection.ensure_collection_deleted()
    index_client.get_index.side_effect = HttpResponseError(message="forbidden", status_code=403)
    with pytest.raises(HttpResponseError):
        await collection.collection_exists()
    alias = AzureAISearchCollection(
        dict, definition=definition(), search_client=client, index_client=index_client, is_alias=True
    )
    with pytest.raises(NotImplementedError, match="alias"):
        await alias.ensure_collection_deleted()
    with pytest.raises(NotImplementedError, match="alias"):
        await alias.ensure_collection_exists()
    assert await alias.collection_exists()
    index_client.get_alias.assert_awaited_once_with("test-index")


async def test_store_alias_administration_and_listing() -> None:
    index_client = Mock(spec=SearchIndexClient)
    index_client.list_index_names.return_value = rows(["first", "second"])
    store = AzureAISearchStore(index_client=index_client)
    assert await store.list_collection_names() == ["first", "second"]
    index_client.list_index_names.assert_called_once_with()
    await store.create_or_update_alias("live", "next-index")
    alias = index_client.create_or_update_alias.call_args.args[0]
    assert alias.name == "live" and alias.indexes == ["next-index"]
    await store.delete_alias("live")
    index_client.delete_index.assert_not_called()


async def test_secret_settings_and_credential_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "environment-key")
    async with AzureAISearchStore(api_key=SecretString("explicit-key")) as store:
        assert store.managed_client
    credential = Mock()
    async with AzureAISearchStore(credential=credential):
        pass
    credential.close.assert_not_called()
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT")
    with pytest.raises(SettingNotFoundError):
        AzureAISearchStore()


@pytest.mark.parametrize("kind", ["store", "collection"])
@pytest.mark.parametrize("identity", [object(), SimpleNamespace(get_token=None), SimpleNamespace(get_token="token")])
def test_invalid_query_credential_before_settings_and_client_creation(kind: str, identity: Any) -> None:
    with (
        patch("agent_framework_azure_ai_search._vector_store.load_settings") as settings_loader,
        patch("agent_framework_azure_ai_search._vector_store.SearchIndexClient") as factory,
        pytest.raises(TypeError, match="query_source_credential must be"),
    ):
        if kind == "store":
            AzureAISearchStore(query_source_credential=identity)
        else:
            AzureAISearchCollection(dict, definition=definition(), query_source_credential=identity)
    settings_loader.assert_not_called()
    factory.assert_not_called()


@pytest.mark.parametrize("kind", ["store", "collection"])
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_valid_query_credential_not_called_or_closed_during_construction(
    client: Mock, kind: str, asynchronous: bool
) -> None:
    identity = Mock()
    identity.get_token = AsyncMock() if asynchronous else Mock()
    connector = (
        AzureAISearchStore(index_client=Mock(spec=SearchIndexClient), query_source_credential=identity)
        if kind == "store"
        else AzureAISearchCollection(
            dict, definition=definition(), search_client=client, query_source_credential=identity
        )
    )
    await connector.close()
    identity.get_token.assert_not_called()
    identity.close.assert_not_called()


@pytest.mark.parametrize("kind", ["store", "collection"])
@pytest.mark.parametrize("source", ["explicit", "file", "environment"])
async def test_constructor_settings_precedence_and_encoding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    client: Mock,
    kind: str,
    source: str,
) -> None:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://environment.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "environment-key")
    env_file = tmp_path / "search.env"
    env_file.write_text(
        "AZURE_SEARCH_ENDPOINT=https://file.search.windows.net\nAZURE_SEARCH_API_KEY=file-key\n",
        encoding="utf-16",
    )
    options: dict[str, Any] = {}
    if source != "environment":
        options.update(env_file_path=str(env_file), env_file_encoding="utf-16")
    if source == "explicit":
        options.update(endpoint="https://explicit.search.windows.net", api_key=SecretString("explicit-key"))
    index_client = Mock(spec=SearchIndexClient)
    index_client.get_search_client.return_value = client
    with (
        patch("agent_framework_azure_ai_search._vector_store.load_settings", wraps=load_settings) as settings_loader,
        patch("agent_framework_azure_ai_search._vector_store.SearchIndexClient", return_value=index_client) as factory,
    ):
        connector = (
            AzureAISearchStore(**options)
            if kind == "store"
            else AzureAISearchCollection(dict, definition=definition(), **options)
        )
        await connector.close()
    settings_loader.assert_called_once()
    assert settings_loader.call_args.args == (AzureAISearchSettings,)
    assert settings_loader.call_args.kwargs["env_prefix"] == "AZURE_SEARCH_"
    assert settings_loader.call_args.kwargs["env_file_encoding"] == ("utf-16" if source != "environment" else None)
    endpoint, credential = factory.call_args.args
    assert endpoint == f"https://{source}.search.windows.net"
    assert isinstance(credential, AzureKeyCredential)
    assert credential.key == f"{source}-key"
    index_client.close.assert_awaited_once()
    if kind == "collection":
        client.close.assert_awaited_once()
        index_client.get_search_client.assert_called_once()


@pytest.mark.parametrize("kind", ["store", "collection"])
@pytest.mark.parametrize("masked", [False, True])
async def test_constructor_api_key_settings_use_secret_string(kind: str, masked: bool, client: Mock) -> None:
    key = SecretString("explicit-key") if masked else "explicit-key"
    endpoint = "https://example.search.windows.net"
    index_client = Mock(spec=SearchIndexClient)
    index_client.get_search_client.return_value = client
    resolved_settings: list[AzureAISearchSettings] = []

    def capture_settings(*args: Any, **kwargs: Any) -> AzureAISearchSettings:
        settings = load_settings(*args, **kwargs)
        resolved_settings.append(settings)
        return settings

    with (
        patch("agent_framework_azure_ai_search._vector_store.load_settings", side_effect=capture_settings),
        patch("agent_framework_azure_ai_search._vector_store.SearchIndexClient", return_value=index_client) as factory,
    ):
        connector = (
            AzureAISearchStore(endpoint=endpoint, api_key=key)
            if kind == "store"
            else AzureAISearchCollection(dict, definition=definition(), endpoint=endpoint, api_key=key)
        )
        await connector.close()
    assert isinstance(resolved_settings[0]["api_key"], SecretString)
    assert "explicit-key" not in repr(resolved_settings)
    assert factory.call_args.args[1].key == "explicit-key"


@pytest.mark.parametrize("kind", ["store", "collection"])
async def test_constructor_explicit_credential_overrides_environment_key(
    monkeypatch: pytest.MonkeyPatch,
    client: Mock,
    kind: str,
) -> None:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "unused-environment-key")
    credential = Mock()
    index_client = Mock(spec=SearchIndexClient)
    index_client.get_search_client.return_value = client
    with patch("agent_framework_azure_ai_search._vector_store.SearchIndexClient", return_value=index_client) as factory:
        connector = (
            AzureAISearchStore(credential=credential)
            if kind == "store"
            else AzureAISearchCollection(dict, definition=definition(), credential=credential)
        )
        await connector.close()
    assert factory.call_args.args[1] is credential
    credential.close.assert_not_called()


@pytest.mark.parametrize("kind", ["store", "collection"])
@pytest.mark.parametrize(
    ("options", "error"),
    [
        ({}, SettingNotFoundError),
        ({"endpoint": "https://example.search.windows.net"}, SettingNotFoundError),
        ({"env_file_path": "missing-search-settings.env"}, FileNotFoundError),
    ],
)
def test_constructor_settings_failures_match(
    tmp_path: Path,
    kind: str,
    options: dict[str, Any],
    error: type[Exception],
) -> None:
    if "env_file_path" in options:
        options = {**options, "env_file_path": str(tmp_path / options["env_file_path"])}
    with patch("agent_framework_azure_ai_search._vector_store.SearchIndexClient") as factory, pytest.raises(error):
        if kind == "store":
            AzureAISearchStore(**options)
        else:
            AzureAISearchCollection(dict, definition=definition(), **options)
    factory.assert_not_called()


@pytest.mark.parametrize("kind", ["store", "collection"])
def test_constructor_rejects_credential_and_key_before_settings(kind: str) -> None:
    credential = AzureKeyCredential("credential-key")
    api_key = SecretString("explicit-key")
    with (
        patch("agent_framework_azure_ai_search._vector_store.load_settings") as settings_loader,
        pytest.raises(ValueError, match="credential or api_key"),
    ):
        if kind == "store":
            AzureAISearchStore(credential=credential, api_key=api_key)
        else:
            AzureAISearchCollection(dict, definition=definition(), credential=credential, api_key=api_key)
    settings_loader.assert_not_called()


@pytest.mark.parametrize("kind", ["store", "collection-index", "collection-search", "collection-both"])
@pytest.mark.parametrize("managed", [False, True])
async def test_injected_clients_bypass_settings_and_preserve_ownership(
    monkeypatch: pytest.MonkeyPatch,
    client: Mock,
    kind: str,
    managed: bool,
) -> None:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "invalid ambient endpoint")
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "ignored-ambient-key")
    index_client = Mock(spec=SearchIndexClient)
    index_client.get_search_client.return_value = client
    connector: AzureAISearchStore | AzureAISearchCollection[dict[str, Any]]
    with patch("agent_framework_azure_ai_search._vector_store.load_settings") as settings_loader:
        if kind == "store":
            connector = AzureAISearchStore(index_client=index_client, managed_client=managed)
        else:
            options: dict[str, Any] = {"managed_client": managed}
            if kind != "collection-search":
                options["index_client"] = index_client
            if kind != "collection-index":
                options["search_client"] = client
            connector = AzureAISearchCollection(dict, definition=definition(), **options)
        await connector.close()
        await connector.close()
    settings_loader.assert_not_called()
    assert index_client.close.await_count == int(managed and kind != "collection-search")
    assert client.close.await_count == int(kind == "collection-index" or (managed and kind != "store"))


@pytest.mark.parametrize("kind", ["store", "collection-index", "collection-search", "collection-both"])
@pytest.mark.parametrize("override", ["endpoint", "credential", "api_key", "env_file_path", "env_file_encoding"])
def test_injected_clients_reject_explicit_settings_before_resolution(
    client: Mock,
    kind: str,
    override: str,
) -> None:
    index_client = Mock(spec=SearchIndexClient)
    connection_options = {
        "endpoint": "https://explicit.search.windows.net",
        "credential": AzureKeyCredential("credential-key"),
        "api_key": SecretString("explicit-key"),
        "env_file_path": "missing-search-settings.env",
        "env_file_encoding": "utf-16",
    }
    options: dict[str, Any] = {override: connection_options[override]}
    if kind != "collection-search":
        options["index_client"] = index_client
    if kind in ("collection-search", "collection-both"):
        options["search_client"] = client
    with (
        patch("agent_framework_azure_ai_search._vector_store.load_settings") as settings_loader,
        pytest.raises(ValueError, match="Injected clients cannot be combined"),
    ):
        if kind == "store":
            AzureAISearchStore(**options)
        else:
            AzureAISearchCollection(dict, definition=definition(), **options)
    settings_loader.assert_not_called()
    index_client.get_search_client.assert_not_called()
    index_client.close.assert_not_called()
    client.close.assert_not_called()


async def test_store_collections_reuse_resolved_clients_without_settings(
    monkeypatch: pytest.MonkeyPatch,
    client: Mock,
) -> None:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://original.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "original-key")
    index_client = Mock(spec=SearchIndexClient)
    index_client.get_search_client.return_value = client
    identity = Mock()
    generator = Mock()
    with (
        patch("agent_framework_azure_ai_search._vector_store.SearchIndexClient", return_value=index_client) as factory,
        patch("agent_framework_azure_ai_search._vector_store.load_settings", wraps=load_settings) as settings_loader,
    ):
        store = AzureAISearchStore(
            allow_preview=True,
            query_source_credential=identity,
            embedding_generator=generator,
        )
        settings_loader.assert_called_once()
        settings_loader.side_effect = AssertionError("Store collections must not reload settings")
        monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://changed.search.windows.net")
        monkeypatch.setenv("AZURE_SEARCH_API_KEY", "changed-key")
        collection = store.get_collection(dict, definition=definition())
        assert collection.index_client is store.index_client
        assert collection.search_client is client
        assert collection.embedding_generator is generator
        assert collection.query_source_credential is identity
        assert collection.allow_preview
        await store.close()
    assert factory.call_args.args[0] == "https://original.search.windows.net"
    assert factory.call_args.args[1].key == "original-key"
    settings_loader.assert_called_once()
    index_client.close.assert_awaited_once()
    client.close.assert_awaited_once()
    identity.close.assert_not_called()
    generator.close.assert_not_called()


class RequestCaptured(Exception):
    pass


async def capture_upload_sizes(monkeypatch: pytest.MonkeyPatch, batches: list[list[dict[str, Any]]]) -> list[int]:
    sizes: list[int] = []
    transport = AioHttpTransport()

    async def capture(request: Any, **kwargs: Any) -> None:
        body = request.body
        assert isinstance(body, (str, bytes))
        sizes.append(len(body.encode("utf-8") if isinstance(body, str) else body))
        raise RequestCaptured

    monkeypatch.setattr(transport, "send", capture)
    async with SearchClient(
        endpoint="https://example.search.windows.net",
        index_name="test-index",
        credential=AzureKeyCredential("test-key"),
        transport=transport,
    ) as sdk:
        upload_documents = getattr(sdk, "upload_documents", None)
        assert callable(upload_documents)
        for batch in batches:
            with pytest.raises(RequestCaptured):
                result = upload_documents(batch)
                assert inspect.isawaitable(result)
                await result
    return sizes


@pytest.mark.parametrize("mode", ["exact", "split", "oversized"])
async def test_sdk_wire_payload_limit_and_late_oversize_preflight(
    collection: AzureAISearchCollection, client: Mock, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    candidate = {**record("tail"), "body": '\u00e9\U0001f600\\"\n'}
    serialized = await collection.serialize([candidate], generate_vectors=False)
    batch = IndexDocumentsBatch(actions=[IndexAction({"@search.action": "upload", **serialized[0]})])
    overhead = len(json.dumps(batch.as_dict()).encode("utf-8"))
    candidate["body"] += "x" * (_MAX_BATCH_BYTES - overhead + int(mode == "oversized"))
    records = [candidate] if mode == "exact" else [record(str(i)) for i in range(1001)] + [candidate]
    if mode == "oversized":
        with pytest.raises(ValueError, match="16 MiB indexing limit"):
            await collection.upsert(records, generate_vectors=False)
        client.upload_documents.assert_not_called()
        return
    assert len(await collection.upsert(records, generate_vectors=False)) == len(records)
    batches = [call.args[0] for call in client.upload_documents.call_args_list]
    assert [len(part) for part in batches] == ([1] if mode == "exact" else [1000, 1, 1])
    sizes = await capture_upload_sizes(monkeypatch, batches)
    assert sizes[-1] == _MAX_BATCH_BYTES
    assert all(size <= _MAX_BATCH_BYTES for size in sizes)


async def test_real_sdk_serializes_vector_query_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Any] = []
    transport = AioHttpTransport()

    async def capture(request: Any, **kwargs: Any) -> None:
        captured.append(request)
        raise RequestCaptured

    monkeypatch.setattr(transport, "send", capture)
    async with SearchClient(
        endpoint="https://example.search.windows.net",
        index_name="test-index",
        credential=AzureKeyCredential("test-key"),
        transport=transport,
    ) as client:
        collection = AzureAISearchCollection(dict, definition=definition(), search_client=client)
        with pytest.raises(IntegrationException):
            results = await collection.search(
                vector=[1, 0, 0], filter=Filter("body", "eq", "O'Brien"), top=2, skip=1, operation_options={"weight": 2}
            )
            _ = [r async for r in results]
    assert len(captured) == 1
    payload = json.loads(captured[0].body)
    assert payload["filter"] == "content eq 'O''Brien'"
    assert payload["vectorQueries"][0]["vector"] == [1, 0, 0]
    assert payload["vectorQueries"][0]["k"] == 3
    assert payload["vectorQueries"][0]["weight"] == 2
    assert payload["skip"] == 1 and payload["top"] == 2
    assert payload["vectorFilterMode"] == "preFilter"
    assert "api-version=" in captured[0].url


@pytest.mark.skipif(not hasattr(query_models, "SearchScoreThreshold"), reason="Preview SDK only")
@pytest.mark.parametrize("api_version", ["2026-04-01", "2024-05-01-preview"])
@pytest.mark.parametrize("capability", ["threshold", "identity", "strict_filter"])
async def test_injected_unsupported_api_fails_before_network(
    monkeypatch: pytest.MonkeyPatch,
    api_version: str,
    capability: str,
) -> None:
    transport = AioHttpTransport()
    send = AsyncMock(side_effect=AssertionError("Network must not be reached"))
    monkeypatch.setattr(transport, "send", send)
    identity = Mock()
    identity.get_token.return_value = AccessToken("caller-token", 9999999999)
    async with SearchClient(
        endpoint="https://example.search.windows.net",
        index_name="test-index",
        credential=AzureKeyCredential("test-key"),
        api_version=api_version,
        transport=transport,
    ) as client:
        collection = AzureAISearchCollection(
            dict,
            definition=definition(),
            search_client=client,
            allow_preview=True,
            query_source_credential=identity if capability == "identity" else None,
        )
        kwargs: dict[str, Any] = (
            {"score_threshold": 0.7}
            if capability == "threshold"
            else {"operation_options": {"vector_filter_mode": "strictPostFilter"}}
            if capability == "strict_filter"
            else {}
        )
        with pytest.raises(IntegrationException, match="not available in API version|never overrides"):
            results = await collection.search(vector=[1, 0, 0], **kwargs)
            _ = [r async for r in results]
    send.assert_not_awaited()


@pytest.mark.skipif(not hasattr(query_models, "HybridSearch"), reason="Preview SDK only")
async def test_native_hybrid_threshold_and_recall(client: Mock) -> None:
    collection = AzureAISearchCollection(dict, definition=definition(), search_client=client, allow_preview=True)
    threshold_type = getattr(query_models, "VectorSimilarityThreshold", None)
    hybrid_type = getattr(query_models, "HybridSearch", None)
    assert threshold_type is not None and hybrid_type is not None
    threshold = threshold_type(value=0.8)
    hybrid = hybrid_type(max_text_recall_size=200)
    await collection.search(
        "cat",
        vector=[1, 0, 0],
        search_type="keyword_hybrid",
        operation_options={"vector_threshold": threshold, "hybrid_search": hybrid},
    )
    options = client.search.call_args.kwargs
    assert options["vector_queries"][0].threshold is threshold
    assert options["hybrid_search"] is hybrid
    options["raw_request_hook"](
        SimpleNamespace(http_request=SimpleNamespace(url="https://example/search?api-version=2026-08-01-preview"))
    )
    with pytest.raises(NotImplementedError):
        options["raw_request_hook"](
            SimpleNamespace(http_request=SimpleNamespace(url="https://example/search?api-version=2025-08-01-preview"))
        )


@pytest.mark.skipif(not hasattr(query_models, "HybridSearch"), reason="Preview SDK only")
async def test_async_identity_empty_token_and_sdk_request(client: Mock) -> None:
    identity = Mock()
    identity.get_token = AsyncMock(return_value=AccessToken("first", 9999999999))
    collection = AzureAISearchCollection(
        dict,
        definition=definition(),
        search_client=client,
        allow_preview=True,
        query_source_credential=identity,
    )
    await collection.get(["one"])
    assert client.search.call_args.kwargs["query_source_authorization"] == "first"
    identity.get_token.return_value = AccessToken("", 9999999999)
    with pytest.raises(ValueError, match="empty authorization"):
        await collection.get(["one"])
    assert client.search.call_count == 1


@pytest.mark.skipif(not hasattr(query_models, "HybridSearch"), reason="Preview SDK only")
async def test_permission_schema_uses_current_preview_api(client: Mock) -> None:
    fields = VectorStoreCollectionDefinition([
        VectorStoreField("key", name="key", type_="str"),
        VectorStoreField(
            "data",
            name="users",
            type_="list[str]",
            is_indexed=True,
            provider_annotations={"azure_ai_search": {"permission_filter": "userIds"}},
        ),
    ])
    index_client = Mock(spec=SearchIndexClient)
    index_client.get_index.side_effect = ResourceNotFoundError()
    collection = AzureAISearchCollection(
        dict,
        definition=fields,
        collection_name="permissions",
        search_client=client,
        index_client=index_client,
        allow_preview=True,
        index_options={"permission_filter_option": "enabled"},
    )
    await collection.ensure_collection_exists()
    index = index_client.create_index.call_args.args[0]
    assert index.as_dict()["fields"][1]["permissionFilter"] == "userIds"
    hook = index_client.create_index.call_args.kwargs["raw_request_hook"]
    with pytest.raises(NotImplementedError, match="2026-08-01"):
        hook(
            SimpleNamespace(http_request=SimpleNamespace(url="https://example/indexes?api-version=2026-05-01-preview"))
        )


async def test_invalid_results_surface_during_iteration(collection: AzureAISearchCollection, client: Mock) -> None:
    client.search.side_effect = lambda **kwargs: rows([{**stored(), "@search.score": float("nan")}])
    with pytest.raises(IntegrationInvalidResponseException, match="invalid"):
        _ = [r async for r in await collection.search(vector=[1, 0, 0])]
    client.search.side_effect = lambda **kwargs: rows([{"doc_id": "one", "@search.score": 1}])
    with pytest.raises(IntegrationInvalidResponseException, match="missing required"):
        _ = [r async for r in await collection.search(vector=[1, 0, 0])]


async def test_filters_validate_even_with_no_documents(collection: AzureAISearchCollection, client: Mock) -> None:
    client.search.side_effect = lambda **kwargs: rows([])
    with pytest.raises(NotImplementedError):
        await collection.search(vector=[1, 0, 0], filter=Filter("body", "is_null"))
    client.search.assert_not_called()
    assert [r async for r in await collection.search(vector=[1, 0, 0], filter=Filter("body", "eq", "x"))] == []


@pytest.mark.parametrize("operator", ["eq", "in", "not_in"])
async def test_date_filter_rejected_instead_of_constant_false(client: Mock, operator: str) -> None:
    collection = AzureAISearchCollection(
        dict,
        definition=VectorStoreCollectionDefinition([
            VectorStoreField("key", name="key", type_="str"),
            VectorStoreField("data", name="created", type_="datetime", is_indexed=True),
        ]),
        collection_name="dated-documents",
        search_client=client,
    )
    value = "2026-09-08T00:00:00Z"
    with pytest.raises(NotImplementedError, match="date comparisons"):
        await collection.get(filter=Filter("created", operator, value if operator == "eq" else [value]))
    client.search.assert_not_called()


async def test_closed_collection_and_no_admin_client(collection: AzureAISearchCollection) -> None:
    with pytest.raises(NotImplementedError, match="index_client"):
        await collection.collection_exists()
    await collection.close()
    with pytest.raises(IntegrationException, match="closed"):
        await collection.get()


def test_missing_vector_profile_rejected(client: Mock) -> None:
    collection = AzureAISearchCollection(
        dict,
        definition=definition(),
        search_client=client,
        vector_search=VectorSearch(profiles=[]),
    )
    with pytest.raises(ValueError, match="Missing vector search profile"):
        collection.build_index()


async def test_nonretrievable_vectors(client: Mock) -> None:
    definition_ = definition(provider_annotations={"azure_ai_search": {"retrievable": False, "stored": False}})
    collection = AzureAISearchCollection(dict, definition=definition_, search_client=client)
    with pytest.raises(ValueError, match="retrievable"):
        await collection.search(vector=[1, 0, 0], include_vectors=True)
    client.search.assert_not_called()


async def test_store_absent_delete_and_closed_admin() -> None:
    index = Mock(spec=SearchIndexClient)
    store = AzureAISearchStore(index_client=index)
    index.get_index.side_effect = ResourceNotFoundError()
    await store.ensure_collection_deleted("absent")
    index.delete_index.assert_not_called()
    index.get_index.side_effect = None
    index.delete_index.side_effect = ResourceNotFoundError()
    await store.ensure_collection_deleted("racing-delete")
    index.delete_index.assert_awaited_once()
    index.delete_alias.side_effect = ResourceNotFoundError()
    await store.delete_alias("absent")
    await store.close()
    with pytest.raises(RuntimeError, match="closed"):
        await store.list_collection_names()


async def test_key_get_rejects_order_and_invalid_paging(collection: AzureAISearchCollection, client: Mock) -> None:
    with pytest.raises(ValueError, match="preserves input order"):
        await collection.get(["one"], skip=1)
    with pytest.raises(ValueError, match="skip cannot"):
        await collection.get(skip=100001)
    with pytest.raises(ValueError, match="sortable"):
        await collection.get(order_by={"body": True})
    with pytest.raises(ValueError, match="Unknown ordering"):
        await collection.get(order_by={"missing": True})
    with pytest.raises(ValueError, match="result window"):
        await collection.search(vector=[1, 0, 0], top=10001)
    client.search.assert_not_called()


@pytest.mark.skipif(not hasattr(query_models, "SearchScoreThreshold"), reason="Preview SDK only")
async def test_real_preview_sdk_threshold_identity_and_recall_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    threshold_type = getattr(query_models, "VectorSimilarityThreshold", None)
    hybrid_type = getattr(query_models, "HybridSearch", None)
    assert threshold_type is not None and hybrid_type is not None
    requests: list[Any] = []
    transport = AioHttpTransport()

    async def capture(request: Any, **kwargs: Any) -> None:
        requests.append(request)
        raise RequestCaptured

    monkeypatch.setattr(transport, "send", capture)
    identity = Mock()
    identity.get_token.return_value = AccessToken("caller-identity-token", 9999999999)
    async with SearchClient(
        endpoint="https://example.search.windows.net",
        index_name="test-index",
        credential=AzureKeyCredential("test-key"),
        transport=transport,
    ) as client:
        collection = AzureAISearchCollection(
            dict,
            definition=definition(),
            search_client=client,
            allow_preview=True,
            query_source_credential=identity,
        )
        with pytest.raises(IntegrationException):
            results = await collection.search(
                "hotel",
                vector=[1, 0, 0],
                search_type="keyword_hybrid",
                filter=Filter("active", "eq", True),
                operation_options={
                    "vector_threshold": threshold_type(value=0.8),
                    "hybrid_search": hybrid_type(max_text_recall_size=200),
                },
            )
            _ = [r async for r in results]
    assert len(requests) == 1
    payload = json.loads(requests[0].body)
    assert payload["vectorQueries"][0]["threshold"] == {"kind": "vectorSimilarity", "value": 0.8}
    assert payload["hybridSearch"]["maxTextRecallSize"] == 200
    assert payload["filter"] == "active eq true"
    assert requests[0].headers["x-ms-query-source-authorization"] == "caller-identity-token"
    assert "filterOverride" not in payload["vectorQueries"][0]


_list_index_names = getattr(SearchIndexClient, "list_index_names", None)


@pytest.mark.skipif(
    not callable(_list_index_names) or "page_size" not in inspect.signature(_list_index_names).parameters,
    reason="Requires cursor-listing SDK support",
)
async def test_preview_cursor_listing_options() -> None:
    index_client = Mock(spec=SearchIndexClient)
    index_client.list_index_names.return_value = rows(["af-first", "af-second"])
    store = AzureAISearchStore(index_client=index_client, allow_preview=True)
    assert await store.list_collection_names(
        operation_options={"search": "af-", "search_type": "prefix", "page_size": 1},
    ) == ["af-first", "af-second"]
    kwargs = index_client.list_index_names.call_args.kwargs
    assert kwargs["page_size"] == 1
    assert "top" not in kwargs and "skip" not in kwargs
    with pytest.raises(NotImplementedError, match="2026-08-01"):
        kwargs["raw_request_hook"](
            SimpleNamespace(http_request=SimpleNamespace(url="https://example/indexes?api-version=2026-05-01-preview"))
        )
