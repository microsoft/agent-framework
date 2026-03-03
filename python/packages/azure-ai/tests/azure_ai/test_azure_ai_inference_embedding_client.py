# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import Content

from agent_framework_azure_ai import (
    AzureAIInferenceEmbeddingClient,
    AzureAIInferenceEmbeddingOptions,
    RawAzureAIInferenceEmbeddingClient,
)


def _make_embed_response(
    embeddings: Sequence[list[float]],
    model: str = "test-model",
    prompt_tokens: int = 10,
) -> MagicMock:
    """Create a mock EmbeddingsResult."""
    data = []
    for emb in embeddings:
        item = MagicMock()
        item.embedding = emb
        data.append(item)

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = 0

    result = MagicMock()
    result.data = data
    result.model = model
    result.usage = usage
    return result


@pytest.fixture
def mock_text_client() -> AsyncMock:
    """Create a mock text EmbeddingsClient."""
    client = AsyncMock()
    client.embed = AsyncMock(return_value=_make_embed_response([[0.1, 0.2, 0.3]]))
    return client


@pytest.fixture
def mock_image_client() -> AsyncMock:
    """Create a mock image ImageEmbeddingsClient."""
    client = AsyncMock()
    client.embed = AsyncMock(return_value=_make_embed_response([[0.4, 0.5, 0.6]]))
    return client


@pytest.fixture
def raw_client(mock_text_client: AsyncMock, mock_image_client: AsyncMock) -> RawAzureAIInferenceEmbeddingClient[Any]:
    """Create a RawAzureAIInferenceEmbeddingClient with mocked SDK clients."""
    return RawAzureAIInferenceEmbeddingClient(
        model_id="test-model",
        endpoint="https://test.inference.ai.azure.com",
        api_key="test-key",
        text_client=mock_text_client,
        image_client=mock_image_client,
    )


@pytest.fixture
def client(mock_text_client: AsyncMock, mock_image_client: AsyncMock) -> AzureAIInferenceEmbeddingClient[Any]:
    """Create an AzureAIInferenceEmbeddingClient with mocked SDK clients."""
    return AzureAIInferenceEmbeddingClient(
        model_id="test-model",
        endpoint="https://test.inference.ai.azure.com",
        api_key="test-key",
        text_client=mock_text_client,
        image_client=mock_image_client,
    )


class TestRawAzureAIInferenceEmbeddingClient:
    """Tests for the raw Azure AI Inference embedding client."""

    async def test_text_embeddings(
        self, raw_client: RawAzureAIInferenceEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """Text inputs are dispatched to the text client."""
        result = await raw_client.get_embeddings(["hello", "world"])
        assert result is not None
        call_kwargs = mock_text_client.embed.call_args
        assert call_kwargs.kwargs["input"] == ["hello", "world"]
        assert call_kwargs.kwargs["model"] == "test-model"

    async def test_text_content_embeddings(
        self, raw_client: RawAzureAIInferenceEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """Content.from_text() inputs are dispatched to the text client."""
        text_content = Content.from_text("hello")
        await raw_client.get_embeddings([text_content])

        mock_text_client.embed.assert_called_once()
        call_kwargs = mock_text_client.embed.call_args
        assert call_kwargs.kwargs["input"] == ["hello"]

    async def test_image_content_embeddings(
        self, raw_client: RawAzureAIInferenceEmbeddingClient[Any], mock_image_client: AsyncMock
    ) -> None:
        """Image Content inputs are dispatched to the image client."""
        image_content = Content.from_data(data=b"\x89PNG", media_type="image/png")
        await raw_client.get_embeddings([image_content])

        mock_image_client.embed.assert_called_once()
        call_kwargs = mock_image_client.embed.call_args
        image_inputs = call_kwargs.kwargs["input"]
        assert len(image_inputs) == 1
        assert image_inputs[0].image == image_content.uri

    async def test_mixed_text_and_image(
        self,
        raw_client: RawAzureAIInferenceEmbeddingClient[Any],
        mock_text_client: AsyncMock,
        mock_image_client: AsyncMock,
    ) -> None:
        """Mixed text and image inputs are dispatched to the correct clients."""
        mock_text_client.embed.return_value = _make_embed_response([[0.1, 0.2]])
        mock_image_client.embed.return_value = _make_embed_response([[0.3, 0.4]])

        image = Content.from_data(data=b"\x89PNG", media_type="image/png")
        await raw_client.get_embeddings(["hello", image, "world"])

        # Text client gets "hello" and "world"
        text_call = mock_text_client.embed.call_args
        assert text_call.kwargs["input"] == ["hello", "world"]

        # Image client gets the image
        image_call = mock_image_client.embed.call_args
        assert len(image_call.kwargs["input"]) == 1

    async def test_empty_input(self, raw_client: RawAzureAIInferenceEmbeddingClient[Any]) -> None:
        """Empty input returns empty result."""
        result = await raw_client.get_embeddings([])
        assert len(result) == 0

    async def test_options_passed_through(
        self, raw_client: RawAzureAIInferenceEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """Options are passed through to the SDK."""
        options: AzureAIInferenceEmbeddingOptions = {
            "dimensions": 512,
            "input_type": "document",
            "encoding_format": "float",
        }
        await raw_client.get_embeddings(["hello"], options=options)

        call_kwargs = mock_text_client.embed.call_args
        assert call_kwargs.kwargs["dimensions"] == 512
        assert call_kwargs.kwargs["input_type"] == "document"
        assert call_kwargs.kwargs["encoding_format"] == "float"

    async def test_model_override_in_options(
        self, raw_client: RawAzureAIInferenceEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """model_id in options overrides the default."""
        options: AzureAIInferenceEmbeddingOptions = {"model_id": "custom-model"}
        await raw_client.get_embeddings(["hello"], options=options)

        call_kwargs = mock_text_client.embed.call_args
        assert call_kwargs.kwargs["model"] == "custom-model"

    async def test_unsupported_content_type_raises(self, raw_client: RawAzureAIInferenceEmbeddingClient[Any]) -> None:
        """Non-text, non-image Content raises ValueError."""
        error_content = Content("error", message="fail")
        with pytest.raises(ValueError, match="Unsupported Content type"):
            await raw_client.get_embeddings([error_content])

    async def test_usage_metadata(
        self, raw_client: RawAzureAIInferenceEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """Usage metadata is populated from the response."""
        mock_text_client.embed.return_value = _make_embed_response([[0.1, 0.2]], prompt_tokens=42)
        result = await raw_client.get_embeddings(["hello"])
        assert result.usage is not None
        assert result.usage["input_token_count"] == 42

    def test_service_url(self, raw_client: RawAzureAIInferenceEmbeddingClient[Any]) -> None:
        """service_url returns the configured endpoint."""
        assert raw_client.service_url() == "https://test.inference.ai.azure.com"

    def test_settings_from_env(self) -> None:
        """Settings are loaded from environment variables."""
        with (
            patch.dict(
                os.environ,
                {
                    "AZURE_AI_INFERENCE_ENDPOINT": "https://env.inference.ai.azure.com",
                    "AZURE_AI_INFERENCE_API_KEY": "env-key",
                    "AZURE_AI_INFERENCE_EMBEDDING_MODEL_ID": "env-model",
                },
            ),
            patch("agent_framework_azure_ai._embedding_client.EmbeddingsClient"),
            patch("agent_framework_azure_ai._embedding_client.ImageEmbeddingsClient"),
        ):
            client = RawAzureAIInferenceEmbeddingClient()
            assert client.model_id == "env-model"
            assert client.image_model_id == "env-model"  # falls back to model_id

    def test_image_model_id_from_env(self) -> None:
        """image_model_id is loaded from its own environment variable."""
        with (
            patch.dict(
                os.environ,
                {
                    "AZURE_AI_INFERENCE_ENDPOINT": "https://env.inference.ai.azure.com",
                    "AZURE_AI_INFERENCE_API_KEY": "env-key",
                    "AZURE_AI_INFERENCE_EMBEDDING_MODEL_ID": "text-model",
                    "AZURE_AI_INFERENCE_IMAGE_EMBEDDING_MODEL_ID": "image-model",
                },
            ),
            patch("agent_framework_azure_ai._embedding_client.EmbeddingsClient"),
            patch("agent_framework_azure_ai._embedding_client.ImageEmbeddingsClient"),
        ):
            client = RawAzureAIInferenceEmbeddingClient()
            assert client.model_id == "text-model"
            assert client.image_model_id == "image-model"

    def test_image_model_id_explicit(self, mock_text_client: AsyncMock, mock_image_client: AsyncMock) -> None:
        """image_model_id can be set explicitly."""
        client = RawAzureAIInferenceEmbeddingClient(
            model_id="text-model",
            image_model_id="image-model",
            endpoint="https://test.inference.ai.azure.com",
            api_key="test-key",
            text_client=mock_text_client,
            image_client=mock_image_client,
        )
        assert client.model_id == "text-model"
        assert client.image_model_id == "image-model"

    async def test_image_model_id_sent_to_image_client(
        self, mock_text_client: AsyncMock, mock_image_client: AsyncMock
    ) -> None:
        """image_model_id is passed to the image client embed call."""
        client = RawAzureAIInferenceEmbeddingClient(
            model_id="text-model",
            image_model_id="image-model",
            endpoint="https://test.inference.ai.azure.com",
            api_key="test-key",
            text_client=mock_text_client,
            image_client=mock_image_client,
        )
        image_content = Content.from_data(data=b"\x89PNG", media_type="image/png")
        await client.get_embeddings([image_content])
        call_kwargs = mock_image_client.embed.call_args
        assert call_kwargs.kwargs["model"] == "image-model"


class TestAzureAIInferenceEmbeddingClient:
    """Tests for the telemetry-enabled Azure AI Inference embedding client."""

    async def test_text_embeddings(
        self, client: AzureAIInferenceEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """Text embeddings work through the telemetry layer."""
        result = await client.get_embeddings(["hello"])
        assert len(result) == 1
        assert result[0].vector == [0.1, 0.2, 0.3]

    async def test_otel_provider_name_default(self) -> None:
        """Default OTEL provider name is azure.ai.inference."""
        assert AzureAIInferenceEmbeddingClient.OTEL_PROVIDER_NAME == "azure.ai.inference"

    async def test_otel_provider_name_override(self, mock_text_client: AsyncMock, mock_image_client: AsyncMock) -> None:
        """OTEL provider name can be overridden."""
        client = AzureAIInferenceEmbeddingClient(
            model_id="test-model",
            endpoint="https://test.inference.ai.azure.com",
            api_key="test-key",
            text_client=mock_text_client,
            image_client=mock_image_client,
            otel_provider_name="custom-provider",
        )
        assert client.otel_provider_name == "custom-provider"


_SKIP_REASON = "Azure AI Inference integration tests disabled"


def _integration_tests_enabled() -> bool:
    return bool(
        os.environ.get("AZURE_AI_INFERENCE_ENDPOINT")
        and os.environ.get("AZURE_AI_INFERENCE_API_KEY")
        and os.environ.get("AZURE_AI_INFERENCE_EMBEDDING_MODEL_ID")
    )


skip_if_azure_ai_inference_integration_tests_disabled = pytest.mark.skipif(
    not _integration_tests_enabled(),
    reason=_SKIP_REASON,
)


class TestAzureAIInferenceEmbeddingIntegration:
    """Integration tests requiring a live Azure AI Inference endpoint."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_azure_ai_inference_integration_tests_disabled
    async def test_text_embedding_live(self) -> None:
        """Generate text embeddings against a live endpoint."""
        client = AzureAIInferenceEmbeddingClient()
        result = await client.get_embeddings(["Hello, world!"])
        assert len(result) == 1
        assert len(result[0].vector) > 0
        assert result[0].model_id is not None
