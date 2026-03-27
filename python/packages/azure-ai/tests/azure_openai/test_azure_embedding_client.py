# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from functools import wraps
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework.azure import AzureOpenAIEmbeddingClient
from agent_framework.openai import OpenAIEmbeddingOptions
from azure.identity.aio import AzureCliCredential
from openai.types import CreateEmbeddingResponse
from openai.types import Embedding as OpenAIEmbedding
from openai.types.create_embedding_response import Usage

pytestmark = pytest.mark.filterwarnings("ignore:AzureOpenAIEmbeddingClient is deprecated\\..*:DeprecationWarning")


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
    assert client.model == "text-embedding-3-small"


def test_azure_construction_with_existing_client(azure_embedding_unit_test_env: None) -> None:
    mock_client = MagicMock()
    client = AzureOpenAIEmbeddingClient(
        deployment_name="my-deployment",
        async_client=mock_client,
    )
    assert client.model == "my-deployment"
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
    os.getenv("AZURE_OPENAI_ENDPOINT", "") in ("", "https://test-endpoint.com")
    or (
        os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "") == ""
        and os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "") == ""
    ),
    reason="No Azure OpenAI endpoint or embedding deployment provided; skipping integration tests.",
)


def _with_azure_openai_debug() -> Any:
    def decorator(func: Any) -> Any:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                model = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") or os.getenv(
                    "AZURE_OPENAI_DEPLOYMENT_NAME", "<unset>"
                )
                api_version = os.getenv("AZURE_OPENAI_API_VERSION", "<unset>")
                endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "<unset>")
                debug_message = f"Azure OpenAI debug: endpoint={endpoint}, model={model}, api_version={api_version}"
                if hasattr(exc, "add_note"):
                    exc.add_note(debug_message)
                elif exc.args:
                    exc.args = (f"{exc.args[0]}\n{debug_message}", *exc.args[1:])
                else:
                    exc.args = (debug_message,)
                raise

        return wrapper

    return decorator


def _get_azure_embedding_deployment_name() -> str:
    return os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") or os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]


def _create_azure_openai_embedding_client(
    *,
    api_key: str | None = None,
    credential: AzureCliCredential | None = None,
) -> AzureOpenAIEmbeddingClient:
    resolved_api_key = (
        api_key if api_key is not None else None if credential is not None else os.getenv("AZURE_OPENAI_API_KEY")
    )
    return AzureOpenAIEmbeddingClient(
        deployment_name=_get_azure_embedding_deployment_name(),
        api_key=resolved_api_key,
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        credential=credential,
    )


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_integration_azure_openai_get_embeddings() -> None:
    """End-to-end test of Azure OpenAI embedding generation."""
    async with AzureCliCredential() as credential:
        client = _create_azure_openai_embedding_client(credential=credential)

        result = await client.get_embeddings(["hello world"])

    assert len(result) == 1
    assert isinstance(result[0].vector, list)
    assert len(result[0].vector) > 0
    assert all(isinstance(v, float) for v in result[0].vector)
    assert result[0].model_id is not None
    assert result.usage is not None
    assert result.usage["input_token_count"] > 0


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_integration_azure_openai_get_embeddings_multiple() -> None:
    """Test Azure OpenAI embedding generation for multiple inputs."""
    async with AzureCliCredential() as credential:
        client = _create_azure_openai_embedding_client(credential=credential)

        result = await client.get_embeddings(["hello", "world", "test"])

    assert len(result) == 3
    dims = [len(e.vector) for e in result]
    assert all(d == dims[0] for d in dims)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_integration_azure_openai_get_embeddings_with_dimensions() -> None:
    """Test Azure OpenAI embedding generation with custom dimensions."""
    async with AzureCliCredential() as credential:
        client = _create_azure_openai_embedding_client(credential=credential)

        options: OpenAIEmbeddingOptions = {"dimensions": 256}
        result = await client.get_embeddings(["hello world"], options=options)

    assert len(result) == 1
    assert len(result[0].vector) == 256
