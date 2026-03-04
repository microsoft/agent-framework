# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from contextlib import suppress
from typing import Any, ClassVar, Generic, TypedDict

from agent_framework import (
    BaseEmbeddingClient,
    Content,
    Embedding,
    EmbeddingGenerationOptions,
    GeneratedEmbeddings,
    UsageDetails,
    load_settings,
)
from agent_framework.observability import EmbeddingTelemetryLayer
from azure.ai.inference.aio import EmbeddingsClient, ImageEmbeddingsClient
from azure.ai.inference.models import ImageEmbeddingInput
from azure.core.credentials import AzureKeyCredential

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover


logger = logging.getLogger("agent_framework.azure_ai")

_IMAGE_MEDIA_PREFIXES = ("image/",)


class AzureAIInferenceEmbeddingOptions(EmbeddingGenerationOptions, total=False):
    """Azure AI Inference-specific embedding options.

    Extends EmbeddingGenerationOptions with Azure AI Inference-specific fields.

    Examples:
        .. code-block:: python

            from agent_framework_azure_ai import AzureAIInferenceEmbeddingOptions

            options: AzureAIInferenceEmbeddingOptions = {
                "model_id": "text-embedding-3-small",
                "dimensions": 1536,
                "input_type": "document",
                "encoding_format": "float",
            }
    """

    input_type: str
    """Input type hint for the model. Common values: ``"text"``, ``"query"``, ``"document"``."""

    image_model_id: str
    """Override model for image embeddings. Falls back to the client's ``image_model_id``."""

    encoding_format: str
    """Output encoding format.

    Common values: ``"float"``, ``"base64"``, ``"int8"``, ``"uint8"``,
    ``"binary"``, ``"ubinary"``.
    """

    extra_parameters: dict[str, Any]
    """Additional model-specific parameters passed directly to the API."""


AzureAIInferenceEmbeddingOptionsT = TypeVar(
    "AzureAIInferenceEmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="AzureAIInferenceEmbeddingOptions",
    covariant=True,
)


class AzureAIInferenceEmbeddingSettings(TypedDict, total=False):
    """Azure AI Inference embedding settings."""

    endpoint: str | None
    api_key: str | None
    embedding_model_id: str | None
    image_embedding_model_id: str | None


class RawAzureAIInferenceEmbeddingClient(
    BaseEmbeddingClient[Content | str, list[float], AzureAIInferenceEmbeddingOptionsT],
    Generic[AzureAIInferenceEmbeddingOptionsT],
):
    """Raw Azure AI Inference embedding client without telemetry.

    Accepts both text (``str``) and image (``Content``) inputs. Text and image
    inputs within a single batch are separated and dispatched to
    ``EmbeddingsClient`` and ``ImageEmbeddingsClient`` respectively. Results
    are reassembled in the original input order.

    Keyword Args:
        model_id: The text embedding model deployment name (e.g. "text-embedding-3-small").
            Can also be set via environment variable AZURE_AI_INFERENCE_EMBEDDING_MODEL_ID.
        image_model_id: The image embedding model deployment name (e.g. "Cohere-embed-v3-english").
            Can also be set via environment variable AZURE_AI_INFERENCE_IMAGE_EMBEDDING_MODEL_ID.
            Falls back to ``model_id`` if not provided.
        endpoint: The Azure AI Inference endpoint URL.
            Can also be set via environment variable AZURE_AI_INFERENCE_ENDPOINT.
        api_key: API key for authentication.
            Can also be set via environment variable AZURE_AI_INFERENCE_API_KEY.
        text_client: Optional pre-configured ``EmbeddingsClient``.
        image_client: Optional pre-configured ``ImageEmbeddingsClient``.
        credential: Optional ``AzureKeyCredential`` or token credential. If not provided,
            one is created from ``api_key``.
        env_file_path: Path to .env file for settings.
        env_file_encoding: Encoding for .env file.
    """

    def __init__(
        self,
        *,
        model_id: str | None = None,
        image_model_id: str | None = None,
        endpoint: str | None = None,
        api_key: str | None = None,
        text_client: EmbeddingsClient | None = None,
        image_client: ImageEmbeddingsClient | None = None,
        credential: AzureKeyCredential | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a raw Azure AI Inference embedding client."""
        settings = load_settings(
            AzureAIInferenceEmbeddingSettings,
            env_prefix="AZURE_AI_INFERENCE_",
            required_fields=["endpoint", "embedding_model_id"],
            endpoint=endpoint,
            api_key=api_key,
            embedding_model_id=model_id,
            image_embedding_model_id=image_model_id,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self.model_id = settings["embedding_model_id"]  # type: ignore[reportTypedDictNotRequiredAccess]
        self.image_model_id: str = settings.get("image_embedding_model_id") or self.model_id  # type: ignore[assignment]
        resolved_endpoint = settings["endpoint"]  # type: ignore[reportTypedDictNotRequiredAccess]

        if credential is None and settings.get("api_key"):
            credential = AzureKeyCredential(settings["api_key"])  # type: ignore[arg-type]

        if credential is None and text_client is None and image_client is None:
            raise ValueError("Either 'api_key', 'credential', or pre-configured client(s) must be provided.")

        self._text_client = text_client or EmbeddingsClient(
            endpoint=resolved_endpoint,  # type: ignore[arg-type]
            credential=credential,  # type: ignore[arg-type]
        )
        self._image_client = image_client or ImageEmbeddingsClient(
            endpoint=resolved_endpoint,  # type: ignore[arg-type]
            credential=credential,  # type: ignore[arg-type]
        )
        self._endpoint = resolved_endpoint
        super().__init__(**kwargs)

    async def close(self) -> None:
        """Close the underlying SDK clients and release resources."""
        with suppress(Exception):
            await self._text_client.close()
        with suppress(Exception):
            await self._image_client.close()

    async def __aenter__(self) -> RawAzureAIInferenceEmbeddingClient[AzureAIInferenceEmbeddingOptionsT]:
        """Enter the async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit the async context manager and close clients."""
        await self.close()

    def service_url(self) -> str:
        """Get the URL of the service."""
        return self._endpoint or ""

    async def get_embeddings(
        self,
        values: Sequence[Content | str],
        *,
        options: AzureAIInferenceEmbeddingOptionsT | None = None,
    ) -> GeneratedEmbeddings[list[float]]:
        """Generate embeddings for text and/or image inputs.

        Text inputs (``str`` or ``Content`` with ``type="text"``) are sent to the
        text embeddings endpoint. Image inputs (``Content`` with an image
        ``media_type``) are sent to the image embeddings endpoint. Results are
        returned in the same order as the input.

        Args:
            values: A sequence of text strings or ``Content`` instances.
            options: Optional embedding generation options.

        Returns:
            Generated embeddings with usage metadata.

        Raises:
            ValueError: If model_id is not provided or an unsupported content type is encountered.
        """
        if not values:
            return GeneratedEmbeddings([], options=options)  # type: ignore[reportReturnType]

        opts: dict[str, Any] = dict(options) if options else {}

        # Separate text and image inputs, tracking original indices.
        text_items: list[tuple[int, str]] = []
        image_items: list[tuple[int, ImageEmbeddingInput]] = []

        for idx, value in enumerate(values):
            if isinstance(value, str):
                text_items.append((idx, value))
            elif isinstance(value, Content):
                if value.type == "text" and value.text is not None:
                    text_items.append((idx, value.text))
                elif (
                    value.type in ("data", "uri")
                    and value.media_type
                    and value.media_type.startswith(_IMAGE_MEDIA_PREFIXES[0])
                ):
                    if not value.uri:
                        raise ValueError(f"Image Content at index {idx} has no URI.")
                    image_input = ImageEmbeddingInput(image=value.uri, text=value.text)
                    image_items.append((idx, image_input))
                else:
                    raise ValueError(
                        f"Unsupported Content type '{value.type}' with media_type "
                        f"'{value.media_type}' at index {idx}. Expected text content or "
                        f"image content (media_type starting with 'image/')."
                    )
            else:
                raise ValueError(f"Unsupported input type {type(value).__name__} at index {idx}.")

        # Build shared API kwargs (without model, which differs per client).
        common_kwargs: dict[str, Any] = {}
        if dimensions := opts.get("dimensions"):
            common_kwargs["dimensions"] = dimensions
        if encoding_format := opts.get("encoding_format"):
            common_kwargs["encoding_format"] = encoding_format
        if input_type := opts.get("input_type"):
            common_kwargs["input_type"] = input_type
        if extra_parameters := opts.get("extra_parameters"):
            common_kwargs["model_extras"] = extra_parameters

        # Allocate results array.
        embeddings: list[Embedding[list[float]] | None] = [None] * len(values)
        usage_details: UsageDetails = {}

        # Embed text inputs.
        if text_items:
            if not (text_model := opts.get("model_id") or self.model_id):
                raise ValueError("An model_id is required, either in the client or options, for text inputs.")
            text_inputs = [t for _, t in text_items]
            response = await self._text_client.embed(
                input=text_inputs,
                model=text_model,
                **common_kwargs,
            )
            for i, item in enumerate(response.data):
                original_idx = text_items[i][0]
                vector: list[float] = [float(v) for v in item.embedding]
                embeddings[original_idx] = Embedding(
                    vector=vector,
                    dimensions=len(vector),
                    model_id=response.model or text_model,
                )
            if response.usage:
                usage_details["input_token_count"] = (usage_details.get("input_token_count") or 0) + (
                    response.usage.prompt_tokens or 0
                )
                usage_details["output_token_count"] = (usage_details.get("output_token_count") or 0) + (
                    getattr(response.usage, "completion_tokens", 0) or 0
                )

        # Embed image inputs.
        if image_items:
            if not (image_model := opts.get("image_model_id") or self.image_model_id):
                raise ValueError("An image_model_id is required, either in the client or options, for image inputs.")
            image_inputs = [img for _, img in image_items]
            response = await self._image_client.embed(
                input=image_inputs,
                model=image_model,
                **common_kwargs,
            )
            for i, item in enumerate(response.data):
                original_idx = image_items[i][0]
                image_vector: list[float] = [float(v) for v in item.embedding]
                embeddings[original_idx] = Embedding(
                    vector=image_vector,
                    dimensions=len(image_vector),
                    model_id=response.model or image_model,
                )
            if response.usage:
                usage_details["input_token_count"] = (usage_details.get("input_token_count") or 0) + (
                    response.usage.prompt_tokens or 0
                )
                usage_details["output_token_count"] = (usage_details.get("output_token_count") or 0) + (
                    getattr(response.usage, "completion_tokens", 0) or 0
                )
        return GeneratedEmbeddings(
            [embedding for embedding in embeddings if embedding is not None],
            options=options,
            usage=usage_details,
        )  # type: ignore[reportReturnType]


class AzureAIInferenceEmbeddingClient(
    EmbeddingTelemetryLayer[Content | str, list[float], AzureAIInferenceEmbeddingOptionsT],
    RawAzureAIInferenceEmbeddingClient[AzureAIInferenceEmbeddingOptionsT],
    Generic[AzureAIInferenceEmbeddingOptionsT],
):
    """Azure AI Inference embedding client with telemetry support.

    Supports both text and image inputs in a single client. Pass plain strings
    or ``Content`` instances created with ``Content.from_text()`` or
    ``Content.from_data()``.

    Keyword Args:
        model_id: The text embedding model deployment name (e.g. "text-embedding-3-small").
            Can also be set via environment variable AZURE_AI_INFERENCE_EMBEDDING_MODEL_ID.
        image_model_id: The image embedding model deployment name
            (e.g. "Cohere-embed-v3-english"). Can also be set via environment variable
            AZURE_AI_INFERENCE_IMAGE_EMBEDDING_MODEL_ID. Falls back to ``model_id``.
        endpoint: The Azure AI Inference endpoint URL.
            Can also be set via environment variable AZURE_AI_INFERENCE_ENDPOINT.
        api_key: API key for authentication.
            Can also be set via environment variable AZURE_AI_INFERENCE_API_KEY.
        text_client: Optional pre-configured ``EmbeddingsClient``.
        image_client: Optional pre-configured ``ImageEmbeddingsClient``.
        credential: Optional ``AzureKeyCredential`` or token credential.
        otel_provider_name: Override for the OpenTelemetry provider name.
        env_file_path: Path to .env file for settings.
        env_file_encoding: Encoding for .env file.

    Examples:
        .. code-block:: python

            from agent_framework_azure_ai import AzureAIInferenceEmbeddingClient

            # Using environment variables
            # Set AZURE_AI_INFERENCE_ENDPOINT=https://your-endpoint.inference.ai.azure.com
            # Set AZURE_AI_INFERENCE_API_KEY=your-key
            # Set AZURE_AI_INFERENCE_EMBEDDING_MODEL_ID=text-embedding-3-small
            # Set AZURE_AI_INFERENCE_IMAGE_EMBEDDING_MODEL_ID=Cohere-embed-v3-english
            client = AzureAIInferenceEmbeddingClient()

            # Text embeddings
            result = await client.get_embeddings(["Hello, world!"])

            # Image embeddings
            from agent_framework import Content

            image = Content.from_data(data=image_bytes, media_type="image/png")
            result = await client.get_embeddings([image])

            # Mixed text and image
            result = await client.get_embeddings(["hello", image])
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.inference"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        model_id: str | None = None,
        image_model_id: str | None = None,
        endpoint: str | None = None,
        api_key: str | None = None,
        text_client: EmbeddingsClient | None = None,
        image_client: ImageEmbeddingsClient | None = None,
        credential: AzureKeyCredential | None = None,
        otel_provider_name: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Azure AI Inference embedding client."""
        super().__init__(
            model_id=model_id,
            image_model_id=image_model_id,
            endpoint=endpoint,
            api_key=api_key,
            text_client=text_client,
            image_client=image_client,
            credential=credential,
            otel_provider_name=otel_provider_name,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            **kwargs,
        )
