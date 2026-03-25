# Copyright (c) Microsoft. All rights reserved.

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import Embedding, GeneratedEmbeddings

from agent_framework_ollama import OllamaEmbeddingClient, OllamaEmbeddingOptions

# region: Unit Tests


def test_ollama_embedding_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test construction with explicit parameters."""
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL_ID", "nomic-embed-text")
    with patch("agent_framework_ollama._embedding_client.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = MagicMock()
        client = OllamaEmbeddingClient()
        assert client.model_id == "nomic-embed-text"


def test_ollama_embedding_construction_with_params() -> None:
    """Test construction with explicit parameters."""
    with patch("agent_framework_ollama._embedding_client.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = MagicMock()
        client = OllamaEmbeddingClient(
            model_id="nomic-embed-text",
            host="http://localhost:11434",
        )
        assert client.model_id == "nomic-embed-text"


def test_ollama_embedding_construction_missing_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing model_id raises an error."""
    monkeypatch.delenv("OLLAMA_EMBEDDING_MODEL_ID", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL_ID", raising=False)
    from agent_framework.exceptions import SettingNotFoundError

    with pytest.raises(SettingNotFoundError):
        OllamaEmbeddingClient()


async def test_ollama_embedding_get_embeddings() -> None:
    """Test generating embeddings via the Ollama API."""
    mock_response = {
        "model": "nomic-embed-text",
        "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
        "prompt_eval_count": 10,
    }

    with patch("agent_framework_ollama._embedding_client.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.embed = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        client = OllamaEmbeddingClient(model_id="nomic-embed-text")
        result = await client.get_embeddings(["hello", "world"])

        assert isinstance(result, GeneratedEmbeddings)
        assert len(result) == 2
        assert result[0].vector == [0.1, 0.2, 0.3]
        assert result[1].vector == [0.4, 0.5, 0.6]
        assert result[0].model_id == "nomic-embed-text"
        assert result.usage == {"input_token_count": 10}

        mock_client.embed.assert_called_once_with(
            model="nomic-embed-text",
            input=["hello", "world"],
        )


async def test_ollama_embedding_get_embeddings_empty_input() -> None:
    """Test generating embeddings with empty input."""
    with patch("agent_framework_ollama._embedding_client.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        client = OllamaEmbeddingClient(model_id="nomic-embed-text")
        result = await client.get_embeddings([])

        assert isinstance(result, GeneratedEmbeddings)
        assert len(result) == 0
        mock_client.embed.assert_not_called()


async def test_ollama_embedding_get_embeddings_with_options() -> None:
    """Test generating embeddings with custom options."""
    mock_response = {
        "model": "nomic-embed-text",
        "embeddings": [[0.1, 0.2, 0.3]],
    }

    with patch("agent_framework_ollama._embedding_client.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.embed = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        client = OllamaEmbeddingClient(model_id="nomic-embed-text")
        options: OllamaEmbeddingOptions = {
            "truncate": True,
            "dimensions": 512,
        }
        result = await client.get_embeddings(["hello"], options=options)

        assert len(result) == 1
        mock_client.embed.assert_called_once_with(
            model="nomic-embed-text",
            input=["hello"],
            truncate=True,
            dimensions=512,
        )


async def test_ollama_embedding_get_embeddings_no_model_raises() -> None:
    """Test that missing model_id at call time raises ValueError."""
    with patch("agent_framework_ollama._embedding_client.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        client = OllamaEmbeddingClient(model_id="nomic-embed-text")
        client.model_id = None  # type: ignore[assignment]

        with pytest.raises(ValueError, match="model_id is required"):
            await client.get_embeddings(["hello"])


# region: Integration Tests

skip_if_ollama_embedding_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("OLLAMA_EMBEDDING_MODEL_ID", "") in ("", "test-model"),
    reason="No real Ollama embedding model provided; skipping integration tests.",
)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_ollama_embedding_integration_tests_disabled
async def test_ollama_embedding_integration() -> None:
    """Integration test for Ollama embedding client."""
    client = OllamaEmbeddingClient()
    result = await client.get_embeddings(["Hello, world!", "How are you?"])

    assert isinstance(result, GeneratedEmbeddings)
    assert len(result) == 2
    for embedding in result:
        assert isinstance(embedding, Embedding)
        assert isinstance(embedding.vector, list)
        assert len(embedding.vector) > 0
        assert all(isinstance(v, float) for v in embedding.vector)
