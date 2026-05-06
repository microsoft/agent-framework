# Copyright (c) Microsoft. All rights reserved.

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import Embedding, GeneratedEmbeddings

from agent_framework_mistral import MistralEmbeddingClient, MistralEmbeddingOptions

# region: Unit Tests


def test_mistral_embedding_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test construction with environment variables."""
    monkeypatch.setenv("MISTRAL_EMBEDDING_MODEL", "mistral-embed")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_cls.return_value = MagicMock()
        client = MistralEmbeddingClient()
        assert client.model == "mistral-embed"


def test_mistral_embedding_construction_with_params() -> None:
    """Test construction with explicit parameters."""
    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_cls.return_value = MagicMock()
        client = MistralEmbeddingClient(
            model="mistral-embed",
            api_key="test-key",
        )
        assert client.model == "mistral-embed"
        mock_cls.assert_called_once_with(api_key="test-key")


def test_mistral_embedding_construction_with_server_url() -> None:
    """Test construction with custom server URL."""
    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_cls.return_value = MagicMock()
        client = MistralEmbeddingClient(
            model="mistral-embed",
            api_key="test-key",
            server_url="https://custom.mistral.ai",
        )
        assert client.model == "mistral-embed"
        assert client.server_url == "https://custom.mistral.ai"
        mock_cls.assert_called_once_with(
            api_key="test-key",
            server_url="https://custom.mistral.ai",
        )


def test_mistral_embedding_construction_with_client() -> None:
    """Test construction with a pre-configured client."""
    mock_client = MagicMock()
    with patch("agent_framework_mistral._embedding_client.Mistral"):
        client = MistralEmbeddingClient(
            model="mistral-embed",
            api_key="test-key",
            client=mock_client,
        )
        assert client.client is mock_client


def test_mistral_embedding_construction_missing_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing model raises an error."""
    monkeypatch.delenv("MISTRAL_EMBEDDING_MODEL", raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    from agent_framework.exceptions import SettingNotFoundError

    with pytest.raises(SettingNotFoundError):
        MistralEmbeddingClient()


def test_mistral_embedding_construction_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing API key raises an error."""
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setenv("MISTRAL_EMBEDDING_MODEL", "mistral-embed")
    from agent_framework.exceptions import SettingNotFoundError

    with pytest.raises(SettingNotFoundError):
        MistralEmbeddingClient()


def test_mistral_embedding_service_url() -> None:
    """Test service_url returns the correct URL."""
    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_cls.return_value = MagicMock()
        client = MistralEmbeddingClient(
            model="mistral-embed",
            api_key="test-key",
        )
        assert client.service_url() == "https://api.mistral.ai"


def test_mistral_embedding_service_url_custom() -> None:
    """Test service_url returns custom URL when set."""
    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_cls.return_value = MagicMock()
        client = MistralEmbeddingClient(
            model="mistral-embed",
            api_key="test-key",
            server_url="https://custom.mistral.ai",
        )
        assert client.service_url() == "https://custom.mistral.ai"


async def test_mistral_embedding_get_embeddings() -> None:
    """Test generating embeddings via the Mistral API."""
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1, 0.2, 0.3], index=0, object="embedding"),
        MagicMock(embedding=[0.4, 0.5, 0.6], index=1, object="embedding"),
    ]
    mock_response.model = "mistral-embed"
    mock_response.usage = MagicMock(prompt_tokens=10, total_tokens=10)

    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_client = MagicMock()
        mock_client.embeddings = MagicMock()
        mock_client.embeddings.create_async = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        client = MistralEmbeddingClient(model="mistral-embed", api_key="test-key")
        result = await client.get_embeddings(["hello", "world"])

        assert isinstance(result, GeneratedEmbeddings)
        assert len(result) == 2
        assert result[0].vector == [0.1, 0.2, 0.3]
        assert result[1].vector == [0.4, 0.5, 0.6]
        assert result[0].model == "mistral-embed"
        assert result.usage == {"input_token_count": 10, "total_token_count": 10}

        mock_client.embeddings.create_async.assert_called_once_with(
            model="mistral-embed",
            inputs=["hello", "world"],
        )


async def test_mistral_embedding_get_embeddings_empty_input() -> None:
    """Test generating embeddings with empty input."""
    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        client = MistralEmbeddingClient(model="mistral-embed", api_key="test-key")
        result = await client.get_embeddings([])

        assert isinstance(result, GeneratedEmbeddings)
        assert len(result) == 0


async def test_mistral_embedding_get_embeddings_with_dimensions() -> None:
    """Test generating embeddings with custom dimensions option."""
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1, 0.2], index=0, object="embedding"),
    ]
    mock_response.model = "mistral-embed"
    mock_response.usage = MagicMock(prompt_tokens=5, total_tokens=5)

    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_client = MagicMock()
        mock_client.embeddings = MagicMock()
        mock_client.embeddings.create_async = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        client = MistralEmbeddingClient(model="mistral-embed", api_key="test-key")
        options: MistralEmbeddingOptions = {"dimensions": 512}
        result = await client.get_embeddings(["hello"], options=options)

        assert len(result) == 1
        mock_client.embeddings.create_async.assert_called_once_with(
            model="mistral-embed",
            inputs=["hello"],
            output_dimension=512,
        )


async def test_mistral_embedding_get_embeddings_no_model_raises() -> None:
    """Test that missing model at call time raises ValueError."""
    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        client = MistralEmbeddingClient(model="mistral-embed", api_key="test-key")
        client.model = None  # type: ignore[assignment]

        with pytest.raises(ValueError, match="model is required"):
            await client.get_embeddings(["hello"])


async def test_mistral_embedding_get_embeddings_model_override() -> None:
    """Test that model can be overridden via options."""
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1, 0.2, 0.3], index=0, object="embedding"),
    ]
    mock_response.model = "custom-embed"
    mock_response.usage = MagicMock(prompt_tokens=5, total_tokens=5)

    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_client = MagicMock()
        mock_client.embeddings = MagicMock()
        mock_client.embeddings.create_async = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        client = MistralEmbeddingClient(model="mistral-embed", api_key="test-key")
        options: MistralEmbeddingOptions = {"model": "custom-embed"}
        result = await client.get_embeddings(["hello"], options=options)

        assert len(result) == 1
        assert result[0].model == "custom-embed"
        mock_client.embeddings.create_async.assert_called_once_with(
            model="custom-embed",
            inputs=["hello"],
        )


async def test_mistral_embedding_get_embeddings_no_usage() -> None:
    """Test handling response without usage information."""
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1, 0.2, 0.3], index=0, object="embedding"),
    ]
    mock_response.model = "mistral-embed"
    mock_response.usage = None

    with patch("agent_framework_mistral._embedding_client.Mistral") as mock_cls:
        mock_client = MagicMock()
        mock_client.embeddings = MagicMock()
        mock_client.embeddings.create_async = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        client = MistralEmbeddingClient(model="mistral-embed", api_key="test-key")
        result = await client.get_embeddings(["hello"])

        assert len(result) == 1
        assert result.usage is None


# region: Integration Tests

skip_if_mistral_embedding_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("MISTRAL_EMBEDDING_MODEL", "") in ("", "test-model") or os.getenv("MISTRAL_API_KEY", "") == "",
    reason="No real Mistral embedding model or API key provided; skipping integration tests.",
)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_mistral_embedding_integration_tests_disabled
async def test_mistral_embedding_integration() -> None:
    """Integration test for Mistral AI embedding client."""
    client = MistralEmbeddingClient()
    result = await client.get_embeddings(["Hello, world!", "How are you?"])

    assert isinstance(result, GeneratedEmbeddings)
    assert len(result) == 2
    for embedding in result:
        assert isinstance(embedding, Embedding)
        assert isinstance(embedding.vector, list)
        assert len(embedding.vector) > 0
        assert all(isinstance(v, float) for v in embedding.vector)
    assert result.usage is not None
    assert result.usage["input_token_count"] is not None
    assert result.usage["input_token_count"] > 0
