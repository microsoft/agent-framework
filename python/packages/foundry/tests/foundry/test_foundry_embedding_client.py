# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from agent_framework import Content, SecretString
from agent_framework._telemetry import USER_AGENT_KEY, get_user_agent
from azure.core.credentials import AzureKeyCredential
from azure.identity.aio import AzureCliCredential

from agent_framework_foundry import (
    FoundryEmbeddingClient,
    FoundryEmbeddingOptions,
    RawFoundryEmbeddingClient,
)


def _make_embed_response(
    embeddings: Sequence[list[float]],
    model: str = "test-model",
    prompt_tokens: int = 10,
    indices: Sequence[int] | None = None,
) -> MagicMock:
    """Create a mock EmbeddingsResult."""
    data = []
    for position, emb in enumerate(embeddings):
        item = MagicMock()
        item.embedding = emb
        item.index = indices[position] if indices is not None else position
        data.append(item)

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = 0
    usage.total_tokens = prompt_tokens

    result = MagicMock()
    result.data = data
    result.model = model
    result.usage = usage
    return result


def _make_openai_client(
    embeddings: Sequence[list[float]] = ([0.1, 0.2, 0.3],),
    *,
    indices: Sequence[int] | None = None,
) -> MagicMock:
    """Create a mock OpenAI client exposed by AIProjectClient."""
    client = MagicMock()
    client.base_url = "https://test.services.ai.azure.com/api/projects/test/openai/v1/"
    client.embeddings.create = AsyncMock(return_value=_make_embed_response(embeddings, indices=indices))
    client.close = AsyncMock()
    return client


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
def raw_client(mock_text_client: AsyncMock, mock_image_client: AsyncMock) -> RawFoundryEmbeddingClient[Any]:
    """Create a RawFoundryEmbeddingClient with mocked SDK clients."""
    return RawFoundryEmbeddingClient(
        model="test-model",
        endpoint="https://test.inference.ai.azure.com",
        api_key="test-key",
        text_client=mock_text_client,
        image_client=mock_image_client,
    )


@pytest.fixture
def client(mock_text_client: AsyncMock, mock_image_client: AsyncMock) -> FoundryEmbeddingClient[Any]:
    """Create a FoundryEmbeddingClient with mocked SDK clients."""
    return FoundryEmbeddingClient(
        model="test-model",
        endpoint="https://test.inference.ai.azure.com",
        api_key="test-key",
        text_client=mock_text_client,
        image_client=mock_image_client,
    )


class TestRawFoundryEmbeddingClient:
    """Tests for the raw Foundry embedding client."""

    async def test_text_embeddings(
        self, raw_client: RawFoundryEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """Text inputs are dispatched to the text client."""
        result = await raw_client.get_embeddings(["hello", "world"])
        assert result is not None
        call_kwargs = mock_text_client.embed.call_args
        assert call_kwargs.kwargs["input"] == ["hello", "world"]
        assert call_kwargs.kwargs["model"] == "test-model"

    async def test_text_content_embeddings(
        self, raw_client: RawFoundryEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """Content.from_text() inputs are dispatched to the text client."""
        text_content = Content.from_text("hello")
        await raw_client.get_embeddings([text_content])

        mock_text_client.embed.assert_called_once()
        call_kwargs = mock_text_client.embed.call_args
        assert call_kwargs.kwargs["input"] == ["hello"]

    async def test_image_content_embeddings(
        self, raw_client: RawFoundryEmbeddingClient[Any], mock_image_client: AsyncMock
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
        raw_client: RawFoundryEmbeddingClient[Any],
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

    async def test_empty_input(self, raw_client: RawFoundryEmbeddingClient[Any]) -> None:
        """Empty input returns empty result."""
        result = await raw_client.get_embeddings([])
        assert len(result) == 0

    async def test_options_passed_through(
        self, raw_client: RawFoundryEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """Options are passed through to the SDK."""
        options: FoundryEmbeddingOptions = {
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
        self, raw_client: RawFoundryEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """model in options overrides the default."""
        options: FoundryEmbeddingOptions = {"model": "custom-model"}
        await raw_client.get_embeddings(["hello"], options=options)

        call_kwargs = mock_text_client.embed.call_args
        assert call_kwargs.kwargs["model"] == "custom-model"

    async def test_unsupported_content_type_raises(self, raw_client: RawFoundryEmbeddingClient[Any]) -> None:
        """Non-text, non-image Content raises ValueError."""
        error_content = Content("error", message="fail")
        with pytest.raises(ValueError, match="Unsupported Content type"):
            await raw_client.get_embeddings([error_content])

    async def test_usage_metadata(
        self, raw_client: RawFoundryEmbeddingClient[Any], mock_text_client: AsyncMock
    ) -> None:
        """Usage metadata is populated from the response."""
        mock_text_client.embed.return_value = _make_embed_response([[0.1, 0.2]], prompt_tokens=42)
        result = await raw_client.get_embeddings(["hello"])
        assert result.usage is not None
        assert result.usage["input_token_count"] == 42

    def test_service_url(self, raw_client: RawFoundryEmbeddingClient[Any]) -> None:
        """service_url returns the configured endpoint."""
        assert raw_client.service_url() == "https://test.inference.ai.azure.com"

    async def test_project_client_text_embeddings(self) -> None:
        """OpenAI deployments are called through an existing project client."""
        openai_client = _make_openai_client()
        project_client = MagicMock()
        project_client.get_openai_client.return_value = openai_client
        project_client.close = AsyncMock()
        client = RawFoundryEmbeddingClient(
            model="text-embedding-3-small",
            project_client=project_client,
        )

        result = await client.get_embeddings(["hello"])

        project_client.get_openai_client.assert_called_once_with()
        openai_client.embeddings.create.assert_awaited_once_with(
            input=["hello"],
            model="text-embedding-3-small",
        )
        assert result[0].vector == [0.1, 0.2, 0.3]
        assert result[0].dimensions == 3
        assert result[0].model == "test-model"
        assert result.usage == {"input_token_count": 10, "total_token_count": 10}
        assert client.service_url() == "https://test.openai.azure.com/openai/v1/"
        assert str(openai_client.base_url) == "https://test.openai.azure.com/openai/v1/"

        await client.close()
        openai_client.close.assert_awaited_once()
        project_client.close.assert_not_called()

    async def test_project_client_options_and_response_order(self) -> None:
        """Project requests pass options through and restore response ordering."""
        openai_client = _make_openai_client([[0.3], [0.1]], indices=[1, 0])
        project_client = MagicMock()
        project_client.get_openai_client.return_value = openai_client
        client = RawFoundryEmbeddingClient(
            model="text-embedding-3-small",
            project_client=project_client,
        )

        result = await client.get_embeddings(
            ["first", "second"],
            options={
                "model": "text-embedding-3-large",
                "dimensions": 256,
                "encoding_format": "float",
                "input_type": "document",
                "extra_parameters": {"custom": "value"},
            },
        )

        openai_client.embeddings.create.assert_awaited_once_with(
            input=["first", "second"],
            model="text-embedding-3-large",
            dimensions=256,
            encoding_format="float",
            extra_body={"custom": "value", "input_type": "document"},
        )
        assert [embedding.vector for embedding in result] == [[0.1], [0.3]]

    async def test_project_mode_rejects_images_before_sending_text(self) -> None:
        """Project OpenAI embedding deployments reject image inputs without partial requests."""
        openai_client = _make_openai_client()
        project_client = MagicMock()
        project_client.get_openai_client.return_value = openai_client
        client = RawFoundryEmbeddingClient(
            model="text-embedding-3-small",
            project_client=project_client,
        )
        image = Content.from_data(data=b"\x89PNG", media_type="image/png")

        with pytest.raises(ValueError, match="Image embeddings require a Foundry Models inference endpoint"):
            await client.get_embeddings(["hello", image])

        openai_client.embeddings.create.assert_not_awaited()

    async def test_owned_project_client_is_closed(self) -> None:
        """A project client created by the embedding client is closed with it."""
        openai_client = _make_openai_client()
        project_client = MagicMock()
        project_client.get_openai_client.return_value = openai_client
        project_client.close = AsyncMock()

        with patch("azure.ai.projects.aio.AIProjectClient", return_value=project_client):
            client = RawFoundryEmbeddingClient(
                model="text-embedding-3-small",
                project_endpoint="https://test.services.ai.azure.com/api/projects/test",
                credential=MagicMock(),
            )

        await client.close()

        openai_client.close.assert_awaited_once()
        project_client.close.assert_awaited_once()

    def test_project_endpoint_from_env_ignores_empty_models_endpoint(self) -> None:
        """Empty Models settings do not override a configured project endpoint."""
        openai_client = _make_openai_client()
        project_client = MagicMock()
        project_client.get_openai_client.return_value = openai_client
        credential = MagicMock()
        default_headers = {"X-Test": "value"}

        with (
            patch.dict(
                os.environ,
                {
                    "FOUNDRY_PROJECT_ENDPOINT": "https://test.services.ai.azure.com/api/projects/test",
                    "FOUNDRY_MODELS_ENDPOINT": "",
                    "FOUNDRY_MODELS_API_KEY": "",
                    "FOUNDRY_EMBEDDING_MODEL": "text-embedding-3-small",
                },
                clear=True,
            ),
            patch(
                "azure.ai.projects.aio.AIProjectClient",
                return_value=project_client,
            ) as project_client_type,
        ):
            client = RawFoundryEmbeddingClient(
                credential=credential,
                allow_preview=True,
                default_headers=default_headers,
            )

        assert client.project_client is project_client
        assert project_client_type.call_args.kwargs["endpoint"] == (
            "https://test.services.ai.azure.com/api/projects/test"
        )
        assert project_client_type.call_args.kwargs["credential"] is credential
        assert project_client_type.call_args.kwargs["allow_preview"] is True
        assert project_client_type.call_args.kwargs["user_agent"] == get_user_agent()
        project_client.get_openai_client.assert_called_once_with(
            default_headers=default_headers,
            http_client=ANY,
        )

    def test_project_endpoint_requires_credential(self) -> None:
        """Creating a project client requires a token credential."""
        with patch.dict(
            os.environ,
            {
                "FOUNDRY_PROJECT_ENDPOINT": "https://test.services.ai.azure.com/api/projects/test",
                "FOUNDRY_EMBEDDING_MODEL": "text-embedding-3-small",
            },
            clear=True,
        ):
            with pytest.raises(ValueError, match="Azure credential is required"):
                RawFoundryEmbeddingClient()

            with pytest.raises(ValueError, match="A token credential is required"):
                RawFoundryEmbeddingClient(credential=AzureKeyCredential("test-key"))

    def test_explicit_project_and_inference_sources_raise(self) -> None:
        """Explicit project and Models endpoint configuration cannot be combined."""
        with pytest.raises(ValueError, match="cannot be combined with Foundry Models"):
            RawFoundryEmbeddingClient(
                model="text-embedding-3-small",
                project_client=MagicMock(),
                endpoint="https://test.inference.ai.azure.com",
            )

    @pytest.mark.parametrize(("endpoint", "api_key"), [("", ""), ("   ", "   ")])
    def test_blank_explicit_models_values_do_not_conflict_with_project_client(
        self,
        endpoint: str,
        api_key: str,
    ) -> None:
        """Blank explicit Models settings are absent when selecting project mode."""
        openai_client = _make_openai_client()
        project_client = MagicMock()
        project_client.get_openai_client.return_value = openai_client

        client = RawFoundryEmbeddingClient(
            model="text-embedding-3-small",
            project_client=project_client,
            endpoint=endpoint,
            api_key=api_key,
        )

        assert client.project_client is project_client
        project_client.get_openai_client.assert_called_once_with()

    def test_legacy_models_endpoint_wins_when_both_env_endpoints_are_set(self) -> None:
        """Existing inference configuration remains preferred when both endpoints come from env."""
        with (
            patch.dict(
                os.environ,
                {
                    "FOUNDRY_PROJECT_ENDPOINT": "https://test.services.ai.azure.com/api/projects/test",
                    "FOUNDRY_MODELS_ENDPOINT": "https://test.inference.ai.azure.com",
                    "FOUNDRY_MODELS_API_KEY": "test-key",
                    "FOUNDRY_EMBEDDING_MODEL": "text-embedding-3-small",
                },
                clear=True,
            ),
            patch("azure.ai.projects.aio.AIProjectClient") as project_client_type,
            patch("agent_framework_foundry._embedding_client.EmbeddingsClient") as text_client_type,
            patch("agent_framework_foundry._embedding_client.ImageEmbeddingsClient"),
        ):
            RawFoundryEmbeddingClient()

        project_client_type.assert_not_called()
        text_client_type.assert_called_once()

    def test_settings_from_env(self) -> None:
        """Settings are loaded from environment variables."""
        with (
            patch.dict(
                os.environ,
                {
                    "FOUNDRY_MODELS_ENDPOINT": "https://env.inference.ai.azure.com",
                    "FOUNDRY_MODELS_API_KEY": "env-key",
                    "FOUNDRY_EMBEDDING_MODEL": "env-model",
                },
                clear=True,
            ),
            patch("agent_framework_foundry._embedding_client.EmbeddingsClient") as text_client_type,
            patch("agent_framework_foundry._embedding_client.ImageEmbeddingsClient") as image_client_type,
        ):
            client = RawFoundryEmbeddingClient()
            assert client.model == "env-model"
            assert client.image_model == "env-model"  # falls back to model
            text_client_type.assert_called_once_with(
                endpoint="https://env.inference.ai.azure.com",
                credential=ANY,
                user_agent=get_user_agent(),
                per_retry_policies=[ANY],
            )
            image_client_type.assert_called_once_with(
                endpoint="https://env.inference.ai.azure.com",
                credential=ANY,
                user_agent=get_user_agent(),
                per_retry_policies=[ANY],
            )

    def test_image_model_from_env(self) -> None:
        """image_model is loaded from its own environment variable."""
        with (
            patch.dict(
                os.environ,
                {
                    "FOUNDRY_MODELS_ENDPOINT": "https://env.inference.ai.azure.com",
                    "FOUNDRY_MODELS_API_KEY": "env-key",
                    "FOUNDRY_EMBEDDING_MODEL": "text-model",
                    "FOUNDRY_IMAGE_EMBEDDING_MODEL": "image-model",
                },
            ),
            patch("agent_framework_foundry._embedding_client.EmbeddingsClient"),
            patch("agent_framework_foundry._embedding_client.ImageEmbeddingsClient"),
        ):
            client = RawFoundryEmbeddingClient()
            assert client.model == "text-model"
            assert client.image_model == "image-model"

    def test_image_model_explicit(self, mock_text_client: AsyncMock, mock_image_client: AsyncMock) -> None:
        """image_model can be set explicitly."""
        client = RawFoundryEmbeddingClient(
            model="text-model",
            image_model="image-model",
            endpoint="https://test.inference.ai.azure.com",
            api_key="test-key",
            text_client=mock_text_client,
            image_client=mock_image_client,
        )
        assert client.model == "text-model"
        assert client.image_model == "image-model"

    async def test_image_model_sent_to_image_client(
        self, mock_text_client: AsyncMock, mock_image_client: AsyncMock
    ) -> None:
        """image_model is passed to the image client embed call."""
        client = RawFoundryEmbeddingClient(
            model="text-model",
            image_model="image-model",
            endpoint="https://test.inference.ai.azure.com",
            api_key="test-key",
            text_client=mock_text_client,
            image_client=mock_image_client,
        )
        image_content = Content.from_data(data=b"\x89PNG", media_type="image/png")
        await client.get_embeddings([image_content])
        call_kwargs = mock_image_client.embed.call_args
        assert call_kwargs.kwargs["model"] == "image-model"


class TestFoundryEmbeddingClient:
    """Tests for the telemetry-enabled Foundry embedding client."""

    async def test_text_embeddings(self, client: FoundryEmbeddingClient[Any], mock_text_client: AsyncMock) -> None:
        """Text embeddings work through the telemetry layer."""
        result = await client.get_embeddings(["hello"])
        assert len(result) == 1
        assert result[0].vector == [0.1, 0.2, 0.3]

    def test_accepts_secret_string_api_key(self) -> None:
        with (
            patch("agent_framework_foundry._embedding_client.EmbeddingsClient") as text_client_type,
            patch("agent_framework_foundry._embedding_client.ImageEmbeddingsClient") as image_client_type,
        ):
            FoundryEmbeddingClient(
                model="test-model",
                endpoint="https://test.inference.ai.azure.com",
                api_key=SecretString("test-key"),
            )

        text_credential = text_client_type.call_args.kwargs["credential"]
        image_credential = image_client_type.call_args.kwargs["credential"]
        assert isinstance(text_credential, AzureKeyCredential)
        assert text_credential is image_credential
        assert type(text_credential.key) is str
        assert text_credential.key == "test-key"

    async def test_otel_provider_name_default(self) -> None:
        """Default OTEL provider name is azure.ai.inference."""
        assert FoundryEmbeddingClient.OTEL_PROVIDER_NAME == "azure.ai.inference"

    async def test_otel_provider_name_override(self, mock_text_client: AsyncMock, mock_image_client: AsyncMock) -> None:
        """OTEL provider name can be overridden."""
        client = FoundryEmbeddingClient(
            model="test-model",
            endpoint="https://test.inference.ai.azure.com",
            api_key="test-key",
            text_client=mock_text_client,
            image_client=mock_image_client,
            otel_provider_name="custom-provider",
        )
        assert client.otel_provider_name == "custom-provider"

    def test_project_otel_provider_name(self) -> None:
        """Project-backed embeddings use the Foundry telemetry provider name."""
        openai_client = _make_openai_client()
        project_client = MagicMock()
        project_client.get_openai_client.return_value = openai_client

        client = FoundryEmbeddingClient(
            model="text-embedding-3-small",
            project_client=project_client,
        )

        assert client.otel_provider_name == "azure.ai.foundry"

    def test_project_client_serialization_round_trip(self) -> None:
        """Project-backed clients serialize without leaking an unsupported telemetry field."""
        openai_client = _make_openai_client()
        project_client = MagicMock()
        project_client.get_openai_client.return_value = openai_client
        default_headers = {
            "X-Test": "value",
            USER_AGENT_KEY: "custom-user-agent",
        }
        client = FoundryEmbeddingClient(
            model="text-embedding-3-small",
            project_client=project_client,
            default_headers=default_headers,
        )

        serialized = client.to_dict()

        assert "OTEL_PROVIDER_NAME" not in serialized
        assert "project_client" not in serialized
        assert serialized["default_headers"] == {"X-Test": "value"}
        assert serialized["otel_provider_name"] == "azure.ai.foundry"

        restored_openai_client = _make_openai_client()
        restored_project_client = MagicMock()
        restored_project_client.get_openai_client.return_value = restored_openai_client
        restored = FoundryEmbeddingClient.from_dict(
            serialized,
            dependencies={
                "foundry_embedding_client": {
                    "project_client": restored_project_client,
                }
            },
        )

        assert restored.project_client is restored_project_client
        assert restored.otel_provider_name == "azure.ai.foundry"
        restored_project_client.get_openai_client.assert_called_once_with(default_headers={"X-Test": "value"})


_SKIP_REASON = "Foundry inference integration tests disabled"


def _foundry_integration_tests_enabled() -> bool:
    return bool(
        os.environ.get("FOUNDRY_MODELS_ENDPOINT")
        and os.environ.get("FOUNDRY_MODELS_API_KEY")
        and os.environ.get("FOUNDRY_EMBEDDING_MODEL")
    )


skip_if_foundry_inference_integration_tests_disabled = pytest.mark.skipif(
    not _foundry_integration_tests_enabled(),
    reason=_SKIP_REASON,
)


class TestFoundryEmbeddingIntegration:
    """Integration tests requiring a live Foundry inference endpoint."""

    @pytest.mark.skip(reason="Flaky in merge queue, blocking unrelated PRs. Tracked in #5553.")
    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_inference_integration_tests_disabled
    async def test_text_embedding_live(self) -> None:
        """Generate text embeddings against a live endpoint."""
        client = FoundryEmbeddingClient()
        result = await client.get_embeddings(["Hello, world!"])
        assert len(result) == 1
        assert len(result[0].vector) > 0
        assert result[0].model is not None


skip_if_foundry_project_embedding_integration_tests_disabled = pytest.mark.skipif(
    not os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or not os.environ.get("FOUNDRY_EMBEDDING_MODEL"),
    reason="No FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_EMBEDDING_MODEL provided; skipping integration test.",
)


class TestFoundryProjectEmbeddingIntegration:
    """Integration tests for OpenAI embedding deployments in a Foundry project."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_project_embedding_integration_tests_disabled
    async def test_text_embedding_live(self) -> None:
        """Generate text embeddings through a Foundry project endpoint."""
        async with (
            AzureCliCredential() as credential,
            FoundryEmbeddingClient(
                project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=cast(Any, credential),
            ) as client,
        ):
            result = await client.get_embeddings(["Hello, world!"])

        assert len(result) == 1
        assert len(result[0].vector) > 0
        assert result[0].model is not None
