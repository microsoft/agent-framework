# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types import CreateEmbeddingResponse
from openai.types import Embedding as OpenAIEmbedding
from openai.types.create_embedding_response import Usage

from agent_framework.azure import AzureOpenAIEmbeddingClient
from agent_framework.openai import (
    OpenAIEmbeddingClient,
    OpenAIEmbeddingOptions,
)


def _make_openai_response(
    embeddings: list[list[float]],
    model: str = "text-embedding-3-small",
    prompt_tokens: int = 5,
    total_tokens: int = 5,
) -> CreateEmbeddingResponse:
    """Helper to create a mock OpenAI embeddings response."""
    data = [OpenAIEmbedding(embedding=emb, index=i, object="embedding") for i, emb in enumerate(embeddings)]
    return CreateEmbeddingResponse(
        data=data,
        model=model,
        object="list",
        usage=Usage(prompt_tokens=prompt_tokens, total_tokens=total_tokens),
    )


@pytest.fixture
def openai_unit_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up environment variables for OpenAI embedding client."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL_ID", "text-embedding-3-small")


# --- OpenAI unit tests ---


def test_openai_construction_with_explicit_params() -> None:
    client = OpenAIEmbeddingClient(
        model_id="text-embedding-3-small",
        api_key="test-key",
    )
    assert client.model_id == "text-embedding-3-small"


def test_openai_construction_from_env(openai_unit_test_env: None) -> None:
    client = OpenAIEmbeddingClient()
    assert client.model_id == "text-embedding-3-small"


def test_openai_construction_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="API key is required"):
        OpenAIEmbeddingClient(model_id="text-embedding-3-small")


def test_openai_construction_missing_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL_ID", raising=False)
    with pytest.raises(ValueError, match="model ID is required"):
        OpenAIEmbeddingClient(api_key="test-key")


async def test_openai_get_embeddings(openai_unit_test_env: None) -> None:
    mock_response = _make_openai_response(
        embeddings=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
    )
    client = OpenAIEmbeddingClient()
    client.client = MagicMock()
    client.client.embeddings = MagicMock()
    client.client.embeddings.create = AsyncMock(return_value=mock_response)

    result = await client.get_embeddings(["hello", "world"])

    assert len(result) == 2
    assert result[0].vector == [0.1, 0.2, 0.3]
    assert result[1].vector == [0.4, 0.5, 0.6]
    assert result[0].model_id == "text-embedding-3-small"
    assert result[0].dimensions == 3


async def test_openai_get_embeddings_usage(openai_unit_test_env: None) -> None:
    mock_response = _make_openai_response(
        embeddings=[[0.1]],
        prompt_tokens=10,
        total_tokens=10,
    )
    client = OpenAIEmbeddingClient()
    client.client = MagicMock()
    client.client.embeddings = MagicMock()
    client.client.embeddings.create = AsyncMock(return_value=mock_response)

    result = await client.get_embeddings(["test"])

    assert result.usage is not None
    assert result.usage["input_token_count"] == 10
    assert result.usage["total_token_count"] == 10


async def test_openai_options_passthrough_dimensions(openai_unit_test_env: None) -> None:
    mock_response = _make_openai_response(embeddings=[[0.1]])
    client = OpenAIEmbeddingClient()
    client.client = MagicMock()
    client.client.embeddings = MagicMock()
    client.client.embeddings.create = AsyncMock(return_value=mock_response)

    options: OpenAIEmbeddingOptions = {"dimensions": 256}
    result = await client.get_embeddings(["test"], options=options)

    call_kwargs = client.client.embeddings.create.call_args[1]
    assert call_kwargs["dimensions"] == 256
    assert result.options is options


async def test_openai_options_passthrough_encoding_format(openai_unit_test_env: None) -> None:
    mock_response = _make_openai_response(embeddings=[[0.1]])
    client = OpenAIEmbeddingClient()
    client.client = MagicMock()
    client.client.embeddings = MagicMock()
    client.client.embeddings.create = AsyncMock(return_value=mock_response)

    options: OpenAIEmbeddingOptions = {"encoding_format": "base64"}
    await client.get_embeddings(["test"], options=options)

    call_kwargs = client.client.embeddings.create.call_args[1]
    assert call_kwargs["encoding_format"] == "base64"


async def test_openai_base64_decoding(openai_unit_test_env: None) -> None:
    import base64
    import struct

    # Encode [0.1, 0.2, 0.3] as base64 little-endian floats
    raw_floats = [0.1, 0.2, 0.3]
    b64_str = base64.b64encode(struct.pack(f"<{len(raw_floats)}f", *raw_floats)).decode()

    # Mock the embedding item to return a base64 string (as the API does with encoding_format=base64)
    mock_item = MagicMock()
    mock_item.embedding = b64_str
    mock_item.index = 0

    mock_response = MagicMock()
    mock_response.data = [mock_item]
    mock_response.model = "text-embedding-3-small"
    mock_response.usage = MagicMock(prompt_tokens=3, total_tokens=3)

    client = OpenAIEmbeddingClient()
    client.client = MagicMock()
    client.client.embeddings = MagicMock()
    client.client.embeddings.create = AsyncMock(return_value=mock_response)

    options: OpenAIEmbeddingOptions = {"encoding_format": "base64"}
    result = await client.get_embeddings(["test"], options=options)

    assert len(result) == 1
    assert len(result[0].vector) == 3
    assert result[0].dimensions == 3
    for expected, actual in zip(raw_floats, result[0].vector):
        assert abs(expected - actual) < 1e-6


async def test_openai_error_when_no_model_id() -> None:
    client = OpenAIEmbeddingClient.__new__(OpenAIEmbeddingClient)
    client.model_id = None
    client.client = MagicMock()
    client.additional_properties = {}
    client.otel_provider_name = "openai"

    with pytest.raises(ValueError, match="model_id is required"):
        await client.get_embeddings(["test"])


async def test_openai_empty_values_returns_empty(openai_unit_test_env: None) -> None:
    client = OpenAIEmbeddingClient()
    client.client = MagicMock()
    client.client.embeddings = MagicMock()
    client.client.embeddings.create = AsyncMock()

    result = await client.get_embeddings([])

    assert len(result) == 0
    assert result.usage is None
    client.client.embeddings.create.assert_not_called()


# --- Azure OpenAI unit tests ---


def test_azure_construction_with_deployment_name() -> None:
    client = AzureOpenAIEmbeddingClient(
        deployment_name="text-embedding-3-small",
        api_key="test-key",
        endpoint="https://test.openai.azure.com/",
    )
    assert client.model_id == "text-embedding-3-small"


def test_azure_construction_with_existing_client() -> None:
    mock_client = MagicMock()
    client = AzureOpenAIEmbeddingClient(
        deployment_name="my-deployment",
        async_client=mock_client,
    )
    assert client.model_id == "my-deployment"
    assert client.client is mock_client


def test_azure_construction_missing_deployment_name_raises() -> None:
    with pytest.raises(ValueError, match="deployment name is required"):
        AzureOpenAIEmbeddingClient(
            api_key="test-key",
            endpoint="https://test.openai.azure.com/",
        )


def test_azure_construction_missing_credentials_raises() -> None:
    with pytest.raises(ValueError, match="api_key, credential, or a client"):
        AzureOpenAIEmbeddingClient(
            deployment_name="test",
            endpoint="https://test.openai.azure.com/",
        )


async def test_azure_get_embeddings() -> None:
    mock_response = _make_openai_response(
        embeddings=[[0.1, 0.2]],
    )
    mock_async_client = MagicMock()
    mock_async_client.embeddings = MagicMock()
    mock_async_client.embeddings.create = AsyncMock(return_value=mock_response)

    client = AzureOpenAIEmbeddingClient(
        deployment_name="text-embedding-3-small",
        async_client=mock_async_client,
    )

    result = await client.get_embeddings(["hello"])

    assert len(result) == 1
    assert result[0].vector == [0.1, 0.2]


def test_azure_otel_provider_name() -> None:
    mock_client = MagicMock()
    client = AzureOpenAIEmbeddingClient(
        deployment_name="test",
        async_client=mock_client,
    )
    assert client.OTEL_PROVIDER_NAME == "azure.ai.openai"


# --- Integration tests ---

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests.",
)

skip_if_azure_openai_integration_tests_disabled = pytest.mark.skipif(
    not os.getenv("AZURE_OPENAI_ENDPOINT")
    or (not os.getenv("AZURE_OPENAI_API_KEY") and not os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")),
    reason="No Azure OpenAI credentials provided; skipping integration tests.",
)


@skip_if_openai_integration_tests_disabled
@pytest.mark.flaky
async def test_integration_openai_get_embeddings() -> None:
    """End-to-end test of OpenAI embedding generation."""
    client = OpenAIEmbeddingClient(model_id="text-embedding-3-small")

    result = await client.get_embeddings(["hello world"])

    assert len(result) == 1
    assert isinstance(result[0].vector, list)
    assert len(result[0].vector) > 0
    assert all(isinstance(v, float) for v in result[0].vector)
    assert result[0].model_id is not None
    assert result.usage is not None
    assert result.usage["input_token_count"] > 0


@skip_if_openai_integration_tests_disabled
@pytest.mark.flaky
async def test_integration_openai_get_embeddings_multiple() -> None:
    """Test embedding generation for multiple inputs."""
    client = OpenAIEmbeddingClient(model_id="text-embedding-3-small")

    result = await client.get_embeddings(["hello", "world", "test"])

    assert len(result) == 3
    dims = [len(e.vector) for e in result]
    assert all(d == dims[0] for d in dims)


@skip_if_openai_integration_tests_disabled
@pytest.mark.flaky
async def test_integration_openai_get_embeddings_with_dimensions() -> None:
    """Test embedding generation with custom dimensions."""
    client = OpenAIEmbeddingClient(model_id="text-embedding-3-small")

    options: OpenAIEmbeddingOptions = {"dimensions": 256}
    result = await client.get_embeddings(["hello world"], options=options)

    assert len(result) == 1
    assert len(result[0].vector) == 256


@skip_if_azure_openai_integration_tests_disabled
@pytest.mark.flaky
async def test_integration_azure_openai_get_embeddings() -> None:
    """End-to-end test of Azure OpenAI embedding generation."""
    client = AzureOpenAIEmbeddingClient()

    result = await client.get_embeddings(["hello world"])

    assert len(result) == 1
    assert isinstance(result[0].vector, list)
    assert len(result[0].vector) > 0
    assert all(isinstance(v, float) for v in result[0].vector)
    assert result[0].model_id is not None
    assert result.usage is not None
    assert result.usage["input_token_count"] > 0


@skip_if_azure_openai_integration_tests_disabled
@pytest.mark.flaky
async def test_integration_azure_openai_get_embeddings_multiple() -> None:
    """Test Azure OpenAI embedding generation for multiple inputs."""
    client = AzureOpenAIEmbeddingClient()

    result = await client.get_embeddings(["hello", "world", "test"])

    assert len(result) == 3
    dims = [len(e.vector) for e in result]
    assert all(d == dims[0] for d in dims)


@skip_if_azure_openai_integration_tests_disabled
@pytest.mark.flaky
async def test_integration_azure_openai_get_embeddings_with_dimensions() -> None:
    """Test Azure OpenAI embedding generation with custom dimensions."""
    client = AzureOpenAIEmbeddingClient()

    options: OpenAIEmbeddingOptions = {"dimensions": 256}
    result = await client.get_embeddings(["hello world"], options=options)

    assert len(result) == 1
    assert len(result[0].vector) == 256
