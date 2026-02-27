# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types import CreateEmbeddingResponse
from openai.types import Embedding as OpenAIEmbedding
from openai.types.create_embedding_response import Usage

from agent_framework.azure import AzureOpenAIEmbeddingClient
from agent_framework.openai import OpenAIEmbeddingOptions


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
def azure_embedding_unit_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear ambient Azure OpenAI embedding env vars for deterministic unit tests."""
    for key in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME",
        "AZURE_OPENAI_BASE_URL",
        "AZURE_OPENAI_TOKEN_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_azure_construction_with_deployment_name(azure_embedding_unit_test_env: None) -> None:
    client = AzureOpenAIEmbeddingClient(
        deployment_name="text-embedding-3-small",
        api_key="test-key",
        endpoint="https://test.openai.azure.com/",
    )
    assert client.model_id == "text-embedding-3-small"


def test_azure_construction_with_existing_client(azure_embedding_unit_test_env: None) -> None:
    mock_client = MagicMock()
    client = AzureOpenAIEmbeddingClient(
        deployment_name="my-deployment",
        async_client=mock_client,
    )
    assert client.model_id == "my-deployment"
    assert client.client is mock_client


def test_azure_construction_missing_deployment_name_raises(azure_embedding_unit_test_env: None) -> None:
    with pytest.raises(ValueError, match="deployment name is required"):
        AzureOpenAIEmbeddingClient(
            api_key="test-key",
            endpoint="https://test.openai.azure.com/",
        )


def test_azure_construction_missing_credentials_raises(azure_embedding_unit_test_env: None) -> None:
    with pytest.raises(ValueError, match="api_key, credential, or a client"):
        AzureOpenAIEmbeddingClient(
            deployment_name="test",
            endpoint="https://test.openai.azure.com/",
        )


async def test_azure_get_embeddings(azure_embedding_unit_test_env: None) -> None:
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


def test_azure_otel_provider_name(azure_embedding_unit_test_env: None) -> None:
    mock_client = MagicMock()
    client = AzureOpenAIEmbeddingClient(
        deployment_name="test",
        async_client=mock_client,
    )
    assert client.OTEL_PROVIDER_NAME == "azure.ai.openai"


skip_if_azure_openai_integration_tests_disabled = pytest.mark.skipif(
    not os.getenv("AZURE_OPENAI_ENDPOINT")
    or (not os.getenv("AZURE_OPENAI_API_KEY") and not os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")),
    reason="No Azure OpenAI credentials provided; skipping integration tests.",
)


@skip_if_azure_openai_integration_tests_disabled
@pytest.mark.integration
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
@pytest.mark.integration
@pytest.mark.flaky
async def test_integration_azure_openai_get_embeddings_multiple() -> None:
    """Test Azure OpenAI embedding generation for multiple inputs."""
    client = AzureOpenAIEmbeddingClient()

    result = await client.get_embeddings(["hello", "world", "test"])

    assert len(result) == 3
    dims = [len(e.vector) for e in result]
    assert all(d == dims[0] for d in dims)


@skip_if_azure_openai_integration_tests_disabled
@pytest.mark.integration
@pytest.mark.flaky
async def test_integration_azure_openai_get_embeddings_with_dimensions() -> None:
    """Test Azure OpenAI embedding generation with custom dimensions."""
    client = AzureOpenAIEmbeddingClient()

    options: OpenAIEmbeddingOptions = {"dimensions": 256}
    result = await client.get_embeddings(["hello world"], options=options)

    assert len(result) == 1
    assert len(result[0].vector) == 256
