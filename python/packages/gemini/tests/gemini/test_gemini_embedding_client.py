# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Annotated, Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from agent_framework import (
    GeneratedEmbeddings,
    InMemoryCollection,
    SupportsGetEmbeddings,
    VectorStoreField,
    create_vector_search_tool,
    vectorstoremodel,
)
from agent_framework._settings import SecretString
from agent_framework.exceptions import (
    IntegrationException,
    IntegrationInvalidAuthException,
    IntegrationInvalidRequestException,
    IntegrationInvalidResponseException,
)
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from agent_framework_gemini import (
    GeminiEmbeddingClient,
    GeminiEmbeddingOptions,
    RawGeminiEmbeddingClient,
)
from agent_framework_gemini._feature_usage import FeatureIndex


@pytest.fixture
def clear_google_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_EMBEDDING_MODEL",
        "GOOGLE_EMBEDDING_MODEL",
        "GOOGLE_GENAI_USE_ENTERPRISE",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
    ):
        monkeypatch.delenv(key, raising=False)


def _make_sdk_client(*, vertexai: bool = False) -> MagicMock:
    sdk = MagicMock()
    sdk._api_client.vertexai = vertexai
    sdk._api_client._http_options.base_url = (
        "https://aiplatform.googleapis.com/" if vertexai else "https://generativelanguage.googleapis.com/"
    )
    sdk.aio.models.embed_content = AsyncMock()
    sdk.aio.aclose = AsyncMock()
    return sdk


def _make_client(
    *,
    model: str | None = "gemini-embedding-2",
    vertexai: bool = False,
    **kwargs: Any,
) -> tuple[GeminiEmbeddingClient, MagicMock]:
    sdk = _make_sdk_client(vertexai=vertexai)
    return GeminiEmbeddingClient(client=sdk, model=model, **kwargs), sdk


def _response(
    vectors: list[list[float]],
    *,
    counts: list[float] | None = None,
    truncated: list[bool] | None = None,
) -> types.EmbedContentResponse:
    return types.EmbedContentResponse(
        embeddings=[
            types.ContentEmbedding(
                values=vector,
                statistics=types.ContentEmbeddingStatistics(
                    token_count=counts[index] if counts is not None else None,
                    truncated=truncated[index] if truncated is not None else None,
                )
                if counts is not None or truncated is not None
                else None,
            )
            for index, vector in enumerate(vectors)
        ],
    )


def _texts(contents: list[types.Content]) -> list[str]:
    result: list[str] = []
    for content in contents:
        assert content.parts is not None and len(content.parts) == 1
        assert content.parts[0].text is not None
        result.append(content.parts[0].text)
    return result


def test_embedding_clients_are_exported_from_provider_namespace() -> None:
    from agent_framework.gemini import GeminiEmbeddingClient as NamespacedClient
    from agent_framework.gemini import RawGeminiEmbeddingClient as NamespacedRawClient

    assert NamespacedClient is GeminiEmbeddingClient
    assert NamespacedRawClient is RawGeminiEmbeddingClient
    client, _ = _make_client()
    assert isinstance(client, SupportsGetEmbeddings)


@pytest.mark.parametrize("api_key", ["explicit-key", SecretString("explicit-key")], ids=["str", "secret"])
def test_explicit_api_key_unwrapped(api_key: str | SecretString, clear_google_env: None) -> None:
    sdk = _make_sdk_client()
    with patch("agent_framework_gemini._sdk_client.genai.Client", return_value=sdk) as factory:
        client = GeminiEmbeddingClient(api_key=api_key)

    assert factory.call_args.kwargs["api_key"] == "explicit-key"
    assert type(factory.call_args.kwargs["api_key"]) is str
    assert "x-goog-api-client" in factory.call_args.kwargs["http_options"]["headers"]
    assert client.service_url() == "https://generativelanguage.googleapis.com"


def test_embedding_uses_google_settings_only(monkeypatch: pytest.MonkeyPatch, clear_google_env: None) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    monkeypatch.setenv("GOOGLE_EMBEDDING_MODEL", "gemini-embedding-2")
    monkeypatch.setenv("GOOGLE_MODEL", "gemini-2.5-flash")
    sdk = _make_sdk_client()
    with patch("agent_framework_gemini._sdk_client.genai.Client", return_value=sdk) as factory:
        client = GeminiEmbeddingClient()

    assert factory.call_args.kwargs["api_key"] == "google-key"
    assert client.model == "gemini-embedding-2"
    assert GeminiEmbeddingClient(model="gemini-embedding-2-preview", client=sdk).model == "gemini-embedding-2-preview"


def test_gemini_only_environment_is_not_supported(monkeypatch: pytest.MonkeyPatch, clear_google_env: None) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-key")
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        GeminiEmbeddingClient()

    injected = GeminiEmbeddingClient(client=_make_sdk_client())
    assert injected.model == "gemini-embedding-2"


def test_gemini_embedding_2_is_default(clear_google_env: None) -> None:
    client, _ = _make_client(model=None)
    assert client.model == "gemini-embedding-2"


def test_blank_model_setting_rejected(monkeypatch: pytest.MonkeyPatch, clear_google_env: None) -> None:
    monkeypatch.setenv("GOOGLE_EMBEDDING_MODEL", " ")
    with pytest.raises(ValueError, match="model must be a non-empty string"):
        GeminiEmbeddingClient(client=_make_sdk_client())


def test_vertex_ai_settings_reuse_chat_auth(monkeypatch: pytest.MonkeyPatch, clear_google_env: None) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    sdk = _make_sdk_client(vertexai=True)
    with patch("agent_framework_gemini._sdk_client.genai.Client", return_value=sdk) as factory:
        client = GeminiEmbeddingClient()

    assert factory.call_args.kwargs["vertexai"] is True
    assert factory.call_args.kwargs["project"] == "project"
    assert factory.call_args.kwargs["location"] == "global"
    assert "api_key" not in factory.call_args.kwargs
    assert client.service_url() == "https://aiplatform.googleapis.com"


def test_enterprise_settings_use_current_sdk_mode(monkeypatch: pytest.MonkeyPatch, clear_google_env: None) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    sdk = _make_sdk_client(vertexai=True)
    with patch("agent_framework_gemini._sdk_client.genai.Client", return_value=sdk) as factory:
        client = GeminiEmbeddingClient()

    assert factory.call_args.kwargs["enterprise"] is True
    assert "vertexai" not in factory.call_args.kwargs
    assert factory.call_args.kwargs["project"] == "project"
    assert factory.call_args.kwargs["location"] == "global"
    assert "api_key" not in factory.call_args.kwargs
    assert client.service_url() == "https://aiplatform.googleapis.com"


def test_conflicting_enterprise_flags_raise(monkeypatch: pytest.MonkeyPatch, clear_google_env: None) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")
    with pytest.raises(ValueError, match="cannot disagree"):
        GeminiEmbeddingClient()


def test_missing_auth_and_incomplete_vertex_config_raise(
    monkeypatch: pytest.MonkeyPatch, clear_google_env: None
) -> None:
    with pytest.raises(ValueError, match="requires an API key"):
        GeminiEmbeddingClient()

    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project")
    with pytest.raises(ValueError, match="requires both GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION"):
        GeminiEmbeddingClient()


def test_injected_vertex_client_controls_service_url() -> None:
    client = GeminiEmbeddingClient(client=_make_sdk_client(vertexai=True), vertexai=False)
    assert client.service_url() == "https://aiplatform.googleapis.com"


async def test_close_only_closes_owned_sdk_client(clear_google_env: None) -> None:
    owned_sdk = _make_sdk_client()
    with patch("agent_framework_gemini._sdk_client.genai.Client", return_value=owned_sdk):
        owned = GeminiEmbeddingClient(api_key="test-key")
    await owned.close()
    owned_sdk.aio.aclose.assert_awaited_once()
    owned_sdk.close.assert_called_once()

    injected, sdk = _make_client()
    await injected.close()
    sdk.aio.aclose.assert_not_awaited()
    sdk.close.assert_not_called()


async def test_batch_result_options_usage_and_metadata() -> None:
    client, sdk = _make_client()
    response = _response([[0.1, 0.2], [0.3, 0.4]], counts=[3.0, 4.0], truncated=[False, True])
    response.metadata = types.EmbedContentMetadata(billable_character_count=16)
    sdk.aio.models.embed_content.return_value = response
    options: GeminiEmbeddingOptions = {
        "model": "gemini-embedding-2-preview",
        "dimensions": 2,
        "task_type": "RETRIEVAL_DOCUMENT",
        "title": "Document title",
    }

    with patch("agent_framework_gemini._embedding_client.mark_feature_used") as mark:
        result = await client.get_embeddings(["first", "second"], options=options)

    mark.assert_called_once_with(FeatureIndex.GEMINI)
    assert isinstance(result, GeneratedEmbeddings)
    assert result.options is options
    assert [embedding.vector for embedding in result] == [[0.1, 0.2], [0.3, 0.4]]
    assert [embedding.dimensions for embedding in result] == [2, 2]
    assert [embedding.model for embedding in result] == ["gemini-embedding-2-preview"] * 2
    assert [embedding.additional_properties["truncated"] for embedding in result] == [False, True]
    assert result.usage == {"input_token_count": 7, "total_token_count": 7}
    assert result.additional_properties == {"billable_character_count": 16}
    request = sdk.aio.models.embed_content.call_args.kwargs
    assert request["model"] == "gemini-embedding-2-preview"
    assert _texts(request["contents"]) == [
        "title: Document title | text: first",
        "title: Document title | text: second",
    ]
    assert request["config"].task_type is None
    assert request["config"].title is None
    assert request["config"].output_dimensionality == 2


async def test_text_requires_task_type_on_every_call() -> None:
    client, sdk = _make_client()
    with pytest.raises(ValueError, match="task_type is required for text embeddings"):
        await client.get_embeddings(["document"])
    with pytest.raises(ValueError, match="task_type is required for text embeddings"):
        await client.get_embeddings(["query"], options={"dimensions": 768})
    sdk.aio.models.embed_content.assert_not_awaited()


@pytest.mark.parametrize("mime_type", ["image/png", "audio/mpeg", "video/mp4", "application/pdf"])
async def test_media_parts_need_no_task_and_are_not_prefixed(mime_type: str) -> None:
    client, sdk = _make_client()
    sdk.aio.models.embed_content.return_value = _response([[0.1]])
    part = types.Part.from_bytes(data=b"media", mime_type=mime_type)

    result = await client.get_embeddings([part], options={"dimensions": 1})

    assert result[0].vector == [0.1]
    request = sdk.aio.models.embed_content.call_args.kwargs
    assert request["contents"][0].parts == [part]
    assert request["config"].task_type is None


async def test_mixed_batch_preserves_multimodal_content_and_input_order() -> None:
    client, sdk = _make_client()
    sdk.aio.models.embed_content.return_value = _response([[0.1], [0.2], [0.3]])
    image = types.Part.from_bytes(data=b"image", mime_type="image/png")
    aggregate = types.Content(parts=[types.Part.from_text(text="An image of a dog"), image])
    pdf = types.Part.from_uri(file_uri="gs://example/document.pdf", mime_type="application/pdf")

    result = await client.get_embeddings(
        ["Find a dog", aggregate, pdf], options={"task_type": "RETRIEVAL_QUERY", "dimensions": 1}
    )

    assert [item.vector for item in result] == [[0.1], [0.2], [0.3]]
    contents = sdk.aio.models.embed_content.call_args.kwargs["contents"]
    assert _texts(contents[:1]) == ["task: search result | query: Find a dog"]
    assert contents[1] is aggregate
    assert aggregate.parts is not None and aggregate.parts[0].text == "An image of a dog"
    assert contents[2].parts == [pdf]


async def test_multimodal_only_rejects_task_type() -> None:
    client, sdk = _make_client()
    image = types.Part.from_bytes(data=b"image", mime_type="image/png")
    with pytest.raises(ValueError, match="omit it when embedding only multimodal content"):
        await client.get_embeddings([image], options={"task_type": "RETRIEVAL_QUERY"})
    sdk.aio.models.embed_content.assert_not_awaited()


@pytest.mark.parametrize(
    "value",
    [
        types.Part.from_text(text="text"),
        types.Content(parts=[types.Part.from_text(text="text")]),
        types.Content(parts=[]),
    ],
)
async def test_text_only_sdk_content_must_use_string_with_task(value: types.Content | types.Part) -> None:
    client, sdk = _make_client()
    with pytest.raises(ValueError, match="requires a media part; pass text as str with task_type"):
        await client.get_embeddings([value])
    sdk.aio.models.embed_content.assert_not_awaited()


async def test_unsupported_embedding_input_is_rejected() -> None:
    client, sdk = _make_client()
    with pytest.raises(ValueError, match="Unsupported embedding input at index 0"):
        await client.get_embeddings([cast(Any, 123)])
    sdk.aio.models.embed_content.assert_not_awaited()


@pytest.mark.parametrize(
    ("task_type", "expected"),
    [
        ("RETRIEVAL_DOCUMENT", "title: none | text: value"),
        ("RETRIEVAL_QUERY", "task: search result | query: value"),
        ("QUESTION_ANSWERING", "task: question answering | query: value"),
        ("FACT_VERIFICATION", "task: fact checking | query: value"),
        ("CODE_RETRIEVAL_QUERY", "task: code retrieval | query: value"),
        ("CLASSIFICATION", "task: classification | query: value"),
        ("CLUSTERING", "task: clustering | query: value"),
        ("SEMANTIC_SIMILARITY", "task: sentence similarity | query: value"),
    ],
)
async def test_text_task_instructions(task_type: str, expected: str) -> None:
    client, sdk = _make_client()
    sdk.aio.models.embed_content.return_value = _response([[0.1]])

    result = await client.get_embeddings(["value"], options=cast(GeminiEmbeddingOptions, {"task_type": task_type}))

    assert result[0].vector == [0.1]
    request = sdk.aio.models.embed_content.call_args.kwargs
    assert request["config"].task_type is None
    assert _texts(request["contents"]) == [expected]


async def test_embedding_2_rejects_unsupported_task_type() -> None:
    client, sdk = _make_client()
    with pytest.raises(ValueError, match="Unsupported Gemini embedding task_type"):
        await client.get_embeddings(["text"], options=cast(GeminiEmbeddingOptions, {"task_type": "UNKNOWN"}))
    with pytest.raises(ValueError, match="Unsupported Gemini embedding task_type"):
        await client.get_embeddings(["text"], options=cast(GeminiEmbeddingOptions, {"task_type": ""}))
    sdk.aio.models.embed_content.assert_not_awaited()


@pytest.mark.parametrize("dimensions", [0, -1, True, 1.5, "768"])
async def test_invalid_dimensions_rejected_before_sdk_call(dimensions: Any) -> None:
    client, sdk = _make_client()
    with pytest.raises(ValueError, match="dimensions must be a positive integer"):
        await client.get_embeddings(
            ["text"], options=cast(GeminiEmbeddingOptions, {"task_type": "RETRIEVAL_QUERY", "dimensions": dimensions})
        )
    sdk.aio.models.embed_content.assert_not_awaited()


async def test_title_requires_retrieval_document() -> None:
    client, sdk = _make_client()
    with pytest.raises(ValueError, match="title requires"):
        await client.get_embeddings(["text"], options={"title": "name"})

    document_client, document_sdk = _make_client()
    document_sdk.aio.models.embed_content.return_value = _response([[0.1]])
    await document_client.get_embeddings(["text"], options={"task_type": "RETRIEVAL_DOCUMENT", "title": "name"})
    request = document_sdk.aio.models.embed_content.call_args.kwargs
    assert request["config"].title is None
    assert _texts(request["contents"]) == ["title: name | text: text"]
    with pytest.raises(ValueError, match="title must be a non-empty string"):
        await document_client.get_embeddings(["text"], options={"task_type": "RETRIEVAL_DOCUMENT", "title": " "})

    with pytest.raises(ValueError, match="title requires"):
        await document_client.get_embeddings(["text"], options={"task_type": "RETRIEVAL_QUERY", "title": "name"})
    sdk.aio.models.embed_content.assert_not_awaited()


@pytest.mark.parametrize("model", [123, 0, None, "", " "])
async def test_model_override_must_be_nonempty_string(model: Any) -> None:
    client, sdk = _make_client()
    with pytest.raises(ValueError, match="model must be a non-empty string"):
        await client.get_embeddings(
            ["text"], options=cast(GeminiEmbeddingOptions, {"model": model, "task_type": "RETRIEVAL_QUERY"})
        )
    sdk.aio.models.embed_content.assert_not_awaited()


@pytest.mark.parametrize("model", ["gemini-embedding-001", "gemini-embedding-2-other", "models/gemini-embedding-2"])
async def test_other_embedding_models_are_rejected(model: str) -> None:
    with pytest.raises(ValueError, match="use gemini-embedding-2 or gemini-embedding-2-preview"):
        GeminiEmbeddingClient(model=model, client=_make_sdk_client())

    client, sdk = _make_client()
    with pytest.raises(ValueError, match="use gemini-embedding-2 or gemini-embedding-2-preview"):
        await client.get_embeddings(["text"], options={"model": model, "task_type": "RETRIEVAL_QUERY"})
    sdk.aio.models.embed_content.assert_not_awaited()


async def test_empty_input_avoids_sdk_and_feature_mark() -> None:
    client, sdk = _make_client(model=None)
    with patch("agent_framework_gemini._embedding_client.mark_feature_used") as mark:
        result = await client.get_embeddings([])
    assert result == []
    assert result.usage is None
    sdk.aio.models.embed_content.assert_not_awaited()
    mark.assert_not_called()


@pytest.mark.parametrize("vectors", [None, [], [[0.1]], [[0.1], [0.2], [0.3]]])
async def test_missing_or_wrong_number_of_embeddings_rejected(vectors: list[list[float]] | None) -> None:
    client, sdk = _make_client()
    sdk.aio.models.embed_content.return_value = (
        types.EmbedContentResponse(embeddings=None) if vectors is None else _response(vectors)
    )
    with pytest.raises(IntegrationInvalidResponseException, match="vectors for 2 inputs"):
        await client.get_embeddings(["one", "two"], options={"task_type": "RETRIEVAL_QUERY"})


async def test_malformed_response_or_partial_enterprise_batch_rejected() -> None:
    client, sdk = _make_client()
    sdk.aio.models.embed_content.return_value = None
    with pytest.raises(IntegrationInvalidResponseException, match="invalid response"):
        await client.get_embeddings(["one"], options={"task_type": "RETRIEVAL_QUERY"})

    enterprise_client, enterprise_sdk = _make_client(vertexai=True)
    enterprise_sdk.aio.models.embed_content.side_effect = [_response([[0.1]]), _response([])]
    with pytest.raises(IntegrationInvalidResponseException, match="vectors for 1 inputs"):
        await enterprise_client.get_embeddings(["one", "two"], options={"task_type": "RETRIEVAL_QUERY"})
    assert enterprise_sdk.aio.models.embed_content.await_count == 2


@pytest.mark.parametrize("vector", [[], [float("nan")], [float("inf")], ["not a number"], [True]])
async def test_invalid_vector_rejected(vector: list[Any]) -> None:
    client, sdk = _make_client()
    sdk.aio.models.embed_content.return_value = types.EmbedContentResponse.model_construct(
        embeddings=[types.ContentEmbedding.model_construct(values=vector, statistics=None)]
    )
    with pytest.raises(IntegrationInvalidResponseException, match="invalid vector"):
        await client.get_embeddings(["text"], options={"task_type": "RETRIEVAL_QUERY"})


async def test_invalid_token_count_rejected() -> None:
    client, sdk = _make_client()
    sdk.aio.models.embed_content.return_value = types.EmbedContentResponse.model_construct(
        embeddings=[
            types.ContentEmbedding.model_construct(
                values=[0.1],
                statistics=types.ContentEmbeddingStatistics.model_construct(token_count=float("inf")),
            )
        ]
    )
    with pytest.raises(IntegrationInvalidResponseException, match="invalid token count"):
        await client.get_embeddings(["text"], options={"task_type": "RETRIEVAL_QUERY"})


async def test_dimension_mismatch_rejected() -> None:
    client, sdk = _make_client()
    sdk.aio.models.embed_content.return_value = _response([[0.1]])
    with pytest.raises(IntegrationInvalidResponseException, match="requested 2"):
        await client.get_embeddings(["text"], options={"task_type": "RETRIEVAL_QUERY", "dimensions": 2})


async def test_partial_or_fractional_statistics_do_not_report_incorrect_usage() -> None:
    client, sdk = _make_client()
    sdk.aio.models.embed_content.return_value = _response([[0.1], [0.2]], counts=[3.0, 1.5])
    assert (await client.get_embeddings(["one", "two"], options={"task_type": "RETRIEVAL_QUERY"})).usage is None

    sdk.aio.models.embed_content.return_value = _response([[0.1], [0.2]])
    assert (await client.get_embeddings(["one", "two"], options={"task_type": "RETRIEVAL_QUERY"})).usage is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (genai_errors.ClientError(401, {"error": {"message": "unauthorized"}}), IntegrationInvalidAuthException),
        (genai_errors.ClientError(403, {"error": {"message": "forbidden"}}), IntegrationInvalidAuthException),
        (genai_errors.ClientError(400, {"error": {"message": "bad request"}}), IntegrationInvalidRequestException),
        (genai_errors.ClientError(429, {"error": {"message": "rate limit"}}), IntegrationInvalidRequestException),
        (genai_errors.ServerError(500, {"error": {"message": "server error"}}), IntegrationException),
        (ValueError("invalid SDK config"), IntegrationInvalidRequestException),
        (RuntimeError("network failure"), IntegrationException),
    ],
)
async def test_sdk_errors_are_translated(error: Exception, expected: type[Exception]) -> None:
    client, sdk = _make_client()
    sdk.aio.models.embed_content.side_effect = error
    with pytest.raises(expected, match="Gemini embeddings") as caught:
        await client.get_embeddings(["text"], options={"task_type": "RETRIEVAL_QUERY"})
    assert caught.value.__cause__ is error


async def test_google_genai_serializes_embedding_request() -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(":batchEmbedContents")
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            json={"embeddings": [{"values": [0.1, 0.2], "statistics": {"tokenCount": 2}} for _ in body["requests"]]},
        )

    sdk = genai.Client(
        api_key="test-key",
        http_options=types.HttpOptions(
            base_url="https://fake.local/",
            async_client_args={"transport": httpx.MockTransport(handler)},
        ),
    )
    client = GeminiEmbeddingClient(client=sdk)
    try:
        result = await client.get_embeddings(["one", "two"], options={"task_type": "RETRIEVAL_QUERY", "dimensions": 2})
        assert [embedding.vector for embedding in result] == [[0.1, 0.2], [0.1, 0.2]]
        assert result.usage == {"input_token_count": 4, "total_token_count": 4}
        assert len(requests[0]["requests"]) == 2
        assert [item["content"]["parts"][0]["text"] for item in requests[0]["requests"]] == [
            "task: search result | query: one",
            "task: search result | query: two",
        ]
        assert all("taskType" not in item and "title" not in item for item in requests[0]["requests"])
        assert all(item["outputDimensionality"] == 2 for item in requests[0]["requests"])
    finally:
        await sdk.aio.aclose()
        sdk.close()


@pytest.mark.filterwarnings("ignore::agent_framework._feature_stage.ExperimentalWarning")
async def test_vector_search_tool_routes_document_and_query_tasks_to_gemini() -> None:
    @vectorstoremodel(collection_name="gemini-embedding-task-test")
    @dataclass
    class Note:
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[
            str | list[float] | None,
            VectorStoreField("vector", dimensions=2, distance_function="cosine_similarity"),
        ] = None

    client, sdk = _make_client()
    sdk.aio.models.embed_content.side_effect = [_response([[0.5, 0.5]]), _response([[0.5, 0.5]])]
    collection: InMemoryCollection[str, Note] = InMemoryCollection(Note, embedding_generator=client)
    await collection.ensure_collection_exists()

    await collection.upsert([Note("one", "A note")], embeddings_options={"task_type": "RETRIEVAL_DOCUMENT"})
    search_tool = create_vector_search_tool(collection, embeddings_options={"task_type": "RETRIEVAL_QUERY"}, top=1)
    results = await search_tool(query="Find the note")

    assert len(results) == 1
    requests = [call.kwargs for call in sdk.aio.models.embed_content.await_args_list]
    assert _texts(requests[0]["contents"]) == ["title: none | text: A note"]
    assert _texts(requests[1]["contents"]) == ["task: search result | query: Find the note"]
    assert all(request["config"].output_dimensionality == 2 for request in requests)


async def test_google_genai_serializes_multimodal_aggregate_without_task_prefix() -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(":batchEmbedContents")
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={"embeddings": [{"values": [0.1]} for _ in body["requests"]]})

    sdk = genai.Client(
        api_key="test-key",
        http_options=types.HttpOptions(
            base_url="https://fake.local/",
            async_client_args={"transport": httpx.MockTransport(handler)},
        ),
    )
    client = GeminiEmbeddingClient(client=sdk)
    image = types.Part.from_bytes(data=b"image", mime_type="image/png")
    aggregate = types.Content(parts=[types.Part.from_text(text="An image of a dog"), image])
    try:
        result = await client.get_embeddings([aggregate], options={"dimensions": 1})
        assert result[0].vector == [0.1]
        request = requests[0]["requests"][0]
        assert request["content"]["parts"][0]["text"] == "An image of a dog"
        assert request["content"]["parts"][1]["inline_data"] == {"data": "aW1hZ2U=", "mime_type": "image/png"}
        assert "taskType" not in request

        mixed_batch = await client.get_embeddings(
            ["Find the dog", aggregate], options={"task_type": "RETRIEVAL_QUERY", "dimensions": 1}
        )
        assert [item.vector for item in mixed_batch] == [[0.1], [0.1]]
        assert requests[1]["requests"][0]["content"]["parts"][0]["text"] == "task: search result | query: Find the dog"
        assert requests[1]["requests"][1]["content"]["parts"][0]["text"] == "An image of a dog"
    finally:
        await sdk.aio.aclose()
        sdk.close()


async def test_google_genai_enterprise_embeds_texts_separately() -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(":embedContent")
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"embedding": {"values": [float(len(requests))]}, "metadata": {"billableCharacterCount": 5}},
        )

    sdk = genai.Client(
        enterprise=True,
        api_key="test-key",
        http_options=types.HttpOptions(
            base_url="https://fake.local/",
            async_client_args={"transport": httpx.MockTransport(handler)},
        ),
    )
    client = GeminiEmbeddingClient(client=sdk)
    try:
        result = await client.get_embeddings(
            ["first", "second"], options={"task_type": "RETRIEVAL_DOCUMENT", "title": "Heading", "dimensions": 1}
        )
        assert [embedding.vector for embedding in result] == [[1.0], [2.0]]
        assert result.additional_properties == {"billable_character_count": 10}
        assert len(requests) == 2
        assert [item["content"]["parts"][0]["text"] for item in requests] == [
            "title: Heading | text: first",
            "title: Heading | text: second",
        ]
        assert all(item["embedContentConfig"]["outputDimensionality"] == 1 for item in requests)
        assert all("taskType" not in item["embedContentConfig"] for item in requests)

        image = types.Part.from_bytes(data=b"image", mime_type="image/png")
        mixed = types.Content(parts=[types.Part.from_text(text="Unprefixed caption"), image])
        media_result = await client.get_embeddings([mixed], options={"dimensions": 1})
        assert media_result[0].vector == [3.0]
        assert requests[2]["content"]["parts"][0]["text"] == "Unprefixed caption"
        assert requests[2]["content"]["parts"][1]["inlineData"] == {"data": "aW1hZ2U=", "mime_type": "image/png"}

        mixed_batch = await client.get_embeddings(
            ["Find the image", mixed], options={"task_type": "RETRIEVAL_QUERY", "dimensions": 1}
        )
        assert [item.vector for item in mixed_batch] == [[4.0], [5.0]]
        assert requests[3]["content"]["parts"][0]["text"] == "task: search result | query: Find the image"
        assert requests[4]["content"]["parts"][0]["text"] == "Unprefixed caption"
    finally:
        await sdk.aio.aclose()
        sdk.close()


def _integration_configured() -> bool:
    if os.getenv("GOOGLE_API_KEY"):
        return True
    return bool(
        (os.getenv("GOOGLE_GENAI_USE_ENTERPRISE") or os.getenv("GOOGLE_GENAI_USE_VERTEXAI") or "").lower()
        in {"true", "1", "yes", "on"}
        and os.getenv("GOOGLE_CLOUD_PROJECT")
        and os.getenv("GOOGLE_CLOUD_LOCATION")
    )


def test_integration_gate_uses_default_embedding_model(monkeypatch: pytest.MonkeyPatch, clear_google_env: None) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assert _integration_configured()


@pytest.mark.flaky
@pytest.mark.integration
@pytest.mark.skipif(not _integration_configured(), reason="Set GOOGLE_API_KEY or Enterprise credentials to run.")
async def test_gemini_embedding_integration() -> None:
    client = GeminiEmbeddingClient()
    try:
        result = await client.get_embeddings(["What is Agent Framework?"], options={"task_type": "RETRIEVAL_QUERY"})
        assert len(result) == 1
        assert result[0].dimensions is not None and result[0].dimensions > 0
    finally:
        await client.close()
