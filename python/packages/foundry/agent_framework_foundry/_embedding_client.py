# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import base64
import logging
import struct
import sys
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypedDict, cast
from urllib.parse import urlsplit, urlunsplit

from agent_framework import (
    BaseEmbeddingClient,
    Content,
    Embedding,
    EmbeddingGenerationOptions,
    GeneratedEmbeddings,
    SecretString,
    UsageDetails,
    load_settings,
)
from agent_framework._telemetry import IS_TELEMETRY_ENABLED, USER_AGENT_KEY, get_user_agent, mark_feature_used
from agent_framework.observability import EmbeddingTelemetryLayer
from azure.ai.inference.aio import EmbeddingsClient, ImageEmbeddingsClient
from azure.ai.inference.models import ImageEmbeddingInput
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential

from ._feature_usage import (
    FeatureIndex,
    create_feature_usage_policy,
    create_foundry_feature_usage_http_client,
)

if TYPE_CHECKING:
    from azure.ai.projects.aio import AIProjectClient
    from openai import AsyncOpenAI

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover


logger = logging.getLogger("agent_framework.foundry")

_IMAGE_MEDIA_PREFIXES = ("image/",)


def _get_openai_model_base_url(endpoint: str) -> str:
    """Get the documented resource-scoped OpenAI model URL from a Foundry endpoint."""
    parts = urlsplit(endpoint)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Invalid Foundry endpoint: {endpoint!r}")
    openai_netloc = parts.netloc.replace(".services.ai.", ".openai.", 1)
    return urlunsplit((parts.scheme, openai_netloc, "/openai/v1/", "", ""))


class FoundryEmbeddingOptions(EmbeddingGenerationOptions, total=False):
    """Foundry-specific embedding options.

    Extends ``EmbeddingGenerationOptions`` with Foundry-specific fields.

    Examples:
        .. code-block:: python

            from agent_framework_foundry import FoundryEmbeddingOptions

            options: FoundryEmbeddingOptions = {
                "model": "text-embedding-3-small",
                "dimensions": 1536,
                "input_type": "document",
                "encoding_format": "float",
            }
    """

    input_type: str
    """Input type hint for the model. Common values: ``"text"``, ``"query"``, ``"document"``."""

    image_model: str
    """Override model for image embeddings. Falls back to the client's ``image_model``."""

    encoding_format: str
    """Output encoding format.

    Common values: ``"float"``, ``"base64"``, ``"int8"``, ``"uint8"``,
    ``"binary"``, ``"ubinary"``.
    """

    extra_parameters: dict[str, Any]
    """Additional model-specific parameters passed directly to the API."""


FoundryEmbeddingOptionsT = TypeVar(
    "FoundryEmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="FoundryEmbeddingOptions",
    covariant=True,
)


class FoundryEmbeddingSettings(TypedDict, total=False):
    """Foundry embedding settings."""

    project_endpoint: str | None
    models_endpoint: str | None
    models_api_key: SecretString | None
    embedding_model: str | None
    image_embedding_model: str | None


class RawFoundryEmbeddingClient(
    BaseEmbeddingClient[Content | str, list[float], FoundryEmbeddingOptionsT],
    Generic[FoundryEmbeddingOptionsT],
):
    """Raw Foundry embedding client without telemetry.

    Text embeddings can be generated through OpenAI model deployments in a
    Foundry project or through a Foundry Models inference endpoint. Image
    embeddings use the Foundry Models inference endpoint. Results are
    reassembled in the original input order.

    Keyword Args:
        model: The text embedding model (e.g. "text-embedding-3-small").
            Can also be set via environment variable FOUNDRY_EMBEDDING_MODEL.
        image_model: The image embedding model (e.g. "Cohere-embed-v3-english").
            Can also be set via environment variable FOUNDRY_IMAGE_EMBEDDING_MODEL.
            Falls back to ``model`` if not provided.
        project_endpoint: The Foundry project endpoint URL used for OpenAI
            embedding deployments. Can also be set via environment variable
            FOUNDRY_PROJECT_ENDPOINT.
        project_client: An existing ``AIProjectClient``. If provided, its
            OpenAI-compatible client is used for text embeddings.
        endpoint: The Foundry inference endpoint URL.
            Can also be set via environment variable FOUNDRY_MODELS_ENDPOINT.
        api_key: API key for authentication.
            Can also be set via environment variable FOUNDRY_MODELS_API_KEY.
        text_client: Optional pre-configured ``EmbeddingsClient``.
        image_client: Optional pre-configured ``ImageEmbeddingsClient``.
        credential: Async Azure credential. Required when using
            ``project_endpoint`` without a ``project_client``. For a Foundry
            Models endpoint, an ``AzureKeyCredential`` is created from
            ``api_key`` when needed.
        allow_preview: Enables preview opt-in on an internally created
            ``AIProjectClient``.
        default_headers: Additional HTTP headers for project OpenAI requests.
        env_file_path: Path to .env file for settings.
        env_file_encoding: Encoding for .env file.
    """

    INJECTABLE: ClassVar[set[str]] = {"image_client", "project_client", "text_client"}

    def __init__(
        self,
        *,
        model: str | None = None,
        image_model: str | None = None,
        endpoint: str | None = None,
        project_endpoint: str | None = None,
        project_client: AIProjectClient | None = None,
        api_key: str | SecretString | None = None,
        text_client: EmbeddingsClient | None = None,
        image_client: ImageEmbeddingsClient | None = None,
        credential: AzureKeyCredential | AsyncTokenCredential | None = None,
        allow_preview: bool | None = None,
        default_headers: Mapping[str, str] | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw Foundry embedding client."""
        if project_endpoint is not None:
            project_endpoint = project_endpoint.strip() or None
        if endpoint is not None:
            endpoint = endpoint.strip() or None
        if (isinstance(api_key, str) and not api_key.strip()) or (
            isinstance(api_key, SecretString) and not api_key.get_secret_value().strip()
        ):
            api_key = None

        explicit_project_source = project_client is not None or project_endpoint is not None
        explicit_inference_source = any(value is not None for value in (endpoint, api_key, text_client, image_client))
        if explicit_project_source and explicit_inference_source:
            raise ValueError(
                "Foundry project embedding configuration cannot be combined with Foundry Models "
                "'endpoint', 'api_key', 'text_client', or 'image_client' configuration."
            )

        settings = load_settings(
            FoundryEmbeddingSettings,
            env_prefix="FOUNDRY_",
            required_fields=["embedding_model"],
            project_endpoint=project_endpoint,
            models_endpoint=endpoint,
            models_api_key=api_key,
            embedding_model=model,
            image_embedding_model=image_model,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self.model = settings["embedding_model"]  # type: ignore[reportTypedDictNotRequiredAccess]
        self.image_model: str = settings.get("image_embedding_model") or self.model  # type: ignore[assignment]
        resolved_models_endpoint = settings.get("models_endpoint") or None
        resolved_project_endpoint = settings.get("project_endpoint") or None
        use_project_client = explicit_project_source or (
            not explicit_inference_source and resolved_models_endpoint is None and resolved_project_endpoint is not None
        )

        self.project_client: AIProjectClient | None = None
        self._owns_project_client = False
        self._openai_client: AsyncOpenAI | None = None
        self._text_client: EmbeddingsClient | None = None
        self._image_client: ImageEmbeddingsClient | None = None
        self.default_headers = (
            {key: value for key, value in default_headers.items() if key != USER_AGENT_KEY} if default_headers else None
        )

        if use_project_client:
            if text_client is not None or image_client is not None:
                raise ValueError(
                    "'text_client' and 'image_client' cannot be used with 'project_endpoint' or 'project_client'."
                )
            if project_client is None:
                if not resolved_project_endpoint:
                    raise ValueError(
                        "Foundry project endpoint is required. Set via 'project_endpoint' parameter "
                        "or 'FOUNDRY_PROJECT_ENDPOINT' environment variable."
                    )
                if credential is None:
                    raise ValueError(
                        "Azure credential is required when using project_endpoint without a project_client."
                    )
                if isinstance(credential, AzureKeyCredential):
                    raise ValueError("A token credential is required when using a Foundry project endpoint.")

                from azure.ai.projects.aio import AIProjectClient

                project_client_kwargs: dict[str, Any] = {
                    "endpoint": resolved_project_endpoint,
                    "credential": credential,
                    "per_retry_policies": [create_feature_usage_policy()],
                }
                if IS_TELEMETRY_ENABLED:
                    project_client_kwargs["user_agent"] = get_user_agent()
                if allow_preview is not None:
                    project_client_kwargs["allow_preview"] = allow_preview
                project_client = AIProjectClient(**project_client_kwargs)
                self._owns_project_client = True

            openai_kwargs: dict[str, Any] = {}
            if default_headers:
                openai_kwargs["default_headers"] = default_headers
            if self._owns_project_client:
                openai_kwargs["http_client"] = create_foundry_feature_usage_http_client()

            self.project_client = project_client
            self._openai_client = project_client.get_openai_client(**openai_kwargs)
            self._endpoint = _get_openai_model_base_url(str(self._openai_client.base_url))
            self._openai_client.base_url = self._endpoint
        else:
            if not resolved_models_endpoint:
                raise ValueError(
                    "Either 'project_endpoint', 'project_client', or 'endpoint' is required. "
                    "Set a Foundry project endpoint via 'FOUNDRY_PROJECT_ENDPOINT' or a Foundry Models "
                    "endpoint via 'FOUNDRY_MODELS_ENDPOINT'."
                )

            if credential is None and (models_api_key := settings.get("models_api_key")):
                credential = AzureKeyCredential(models_api_key.get_secret_value())

            if credential is None and text_client is None and image_client is None:
                raise ValueError("Either 'api_key', 'credential', or pre-configured client(s) must be provided.")

            client_kwargs: dict[str, Any] = {
                "endpoint": resolved_models_endpoint,
                "credential": credential,
            }
            if IS_TELEMETRY_ENABLED:
                client_kwargs["user_agent"] = get_user_agent()
            self._text_client = text_client
            self._image_client = image_client
            if credential is not None:
                self._text_client = text_client or EmbeddingsClient(
                    **client_kwargs,
                    per_retry_policies=[create_feature_usage_policy()],
                )
                self._image_client = image_client or ImageEmbeddingsClient(
                    **client_kwargs,
                    per_retry_policies=[create_feature_usage_policy()],
                )
            self._endpoint = resolved_models_endpoint

        super().__init__(additional_properties=additional_properties)

    async def close(self) -> None:
        """Close the underlying SDK clients and release resources."""
        if self._openai_client is not None:
            with suppress(Exception):
                await self._openai_client.close()
        if self._owns_project_client and self.project_client is not None:
            with suppress(Exception):
                await self.project_client.close()
        if self._text_client is not None:
            with suppress(Exception):
                await self._text_client.close()
        if self._image_client is not None:
            with suppress(Exception):
                await self._image_client.close()

    async def __aenter__(self) -> RawFoundryEmbeddingClient[FoundryEmbeddingOptionsT]:
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
        options: FoundryEmbeddingOptionsT | None = None,
    ) -> GeneratedEmbeddings[list[float], FoundryEmbeddingOptionsT]:
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
            ValueError: If model is not provided or an unsupported content type is encountered.
        """
        if not values:
            return GeneratedEmbeddings([], options=options)
        mark_feature_used(FeatureIndex.FOUNDRY_EMBEDDING)

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

        image_client = self._image_client
        if image_items and image_client is None:
            raise ValueError(
                "Image embeddings require a Foundry Models inference endpoint. "
                "Configure 'endpoint' or 'FOUNDRY_MODELS_ENDPOINT' instead of a project endpoint."
            )
        image_client = cast(ImageEmbeddingsClient, image_client)

        # Embed text inputs.
        if text_items:
            if not (text_model := opts.get("model") or self.model):
                raise ValueError("A model is required, either in the client or options, for text inputs.")
            text_inputs = [t for _, t in text_items]
            if self._openai_client is not None:
                openai_kwargs: dict[str, Any] = {
                    "input": text_inputs,
                    "model": text_model,
                }
                if dimensions := opts.get("dimensions"):
                    openai_kwargs["dimensions"] = dimensions
                if encoding_format := opts.get("encoding_format"):
                    openai_kwargs["encoding_format"] = encoding_format

                extra_body = dict(opts.get("extra_parameters") or {})
                if input_type := opts.get("input_type"):
                    extra_body["input_type"] = input_type
                if extra_body:
                    openai_kwargs["extra_body"] = extra_body

                openai_response = await self._openai_client.embeddings.create(**openai_kwargs)
                encoding = openai_kwargs.get("encoding_format", "float")
                for item in sorted(openai_response.data, key=lambda value: value.index):
                    original_idx = text_items[item.index][0]
                    if encoding == "base64" and isinstance(item.embedding, str):
                        raw = base64.b64decode(item.embedding)
                        vector = list(struct.unpack(f"<{len(raw) // 4}f", raw))
                    else:
                        vector = [float(value) for value in item.embedding]
                    embeddings[original_idx] = Embedding(
                        vector=vector,
                        dimensions=len(vector),
                        model=openai_response.model or text_model,
                    )
                if openai_response.usage:
                    usage_details["input_token_count"] = openai_response.usage.prompt_tokens
                    usage_details["total_token_count"] = openai_response.usage.total_tokens
            elif self._text_client is not None:
                inference_response = await self._text_client.embed(
                    input=text_inputs,
                    model=text_model,
                    **common_kwargs,
                )
                for i, item in enumerate(inference_response.data):
                    original_idx = text_items[i][0]
                    vector = [float(value) for value in item.embedding]
                    embeddings[original_idx] = Embedding(
                        vector=vector,
                        dimensions=len(vector),
                        model=inference_response.model or text_model,
                    )
                if inference_response.usage:
                    usage_details["input_token_count"] = (usage_details.get("input_token_count") or 0) + (
                        inference_response.usage.prompt_tokens or 0
                    )
                    usage_details["output_token_count"] = (usage_details.get("output_token_count") or 0) + (
                        getattr(inference_response.usage, "completion_tokens", 0) or 0
                    )
            else:
                raise RuntimeError("No text embedding client is configured.")

        # Embed image inputs.
        if image_items:
            if not (image_model := opts.get("image_model") or self.image_model):
                raise ValueError("An image_model is required, either in the client or options, for image inputs.")
            image_inputs = [img for _, img in image_items]
            image_response = await image_client.embed(
                input=image_inputs,
                model=image_model,
                **common_kwargs,
            )
            for i, item in enumerate(image_response.data):
                original_idx = image_items[i][0]
                image_vector: list[float] = [float(v) for v in item.embedding]
                embeddings[original_idx] = Embedding(
                    vector=image_vector,
                    dimensions=len(image_vector),
                    model=image_response.model or image_model,
                )
            if image_response.usage:
                usage_details["input_token_count"] = (usage_details.get("input_token_count") or 0) + (
                    image_response.usage.prompt_tokens or 0
                )
                usage_details["output_token_count"] = (usage_details.get("output_token_count") or 0) + (
                    getattr(image_response.usage, "completion_tokens", 0) or 0
                )
        return GeneratedEmbeddings(
            [embedding for embedding in embeddings if embedding is not None],
            options=options,
            usage=usage_details,
        )


class FoundryEmbeddingClient(
    EmbeddingTelemetryLayer[Content | str, list[float], FoundryEmbeddingOptionsT],
    RawFoundryEmbeddingClient[FoundryEmbeddingOptionsT],
    Generic[FoundryEmbeddingOptionsT],
):
    """Foundry embedding client with telemetry support.

    Supports OpenAI text embedding deployments through a Foundry project and
    text or image models through a Foundry Models inference endpoint.

    Keyword Args:
        model: The text embedding model (e.g. "text-embedding-3-small").
            Can also be set via environment variable FOUNDRY_EMBEDDING_MODEL.
        image_model: The image embedding model
            (e.g. "Cohere-embed-v3-english"). Can also be set via environment variable
            FOUNDRY_IMAGE_EMBEDDING_MODEL. Falls back to ``model``.
        project_endpoint: The Foundry project endpoint URL used for OpenAI
            embedding deployments. Can also be set via environment variable
            FOUNDRY_PROJECT_ENDPOINT.
        project_client: An existing ``AIProjectClient``.
        endpoint: The Foundry inference endpoint URL.
            Can also be set via environment variable FOUNDRY_MODELS_ENDPOINT.
        api_key: API key for authentication.
            Can also be set via environment variable FOUNDRY_MODELS_API_KEY.
        text_client: Optional pre-configured ``EmbeddingsClient``.
        image_client: Optional pre-configured ``ImageEmbeddingsClient``.
        credential: Async Azure credential.
        allow_preview: Enables preview opt-in on an internally created
            ``AIProjectClient``.
        default_headers: Additional HTTP headers for project OpenAI requests.
        otel_provider_name: Override for the OpenTelemetry provider name.
        env_file_path: Path to .env file for settings.
        env_file_encoding: Encoding for .env file.

    Examples:
        .. code-block:: python

            from agent_framework_foundry import FoundryEmbeddingClient

            # OpenAI embedding deployment in a Foundry project
            # Set FOUNDRY_PROJECT_ENDPOINT=https://your-resource.services.ai.azure.com/api/projects/your-project
            # Set FOUNDRY_EMBEDDING_MODEL=text-embedding-3-small
            client = FoundryEmbeddingClient(credential=azure_credential)

            # Foundry Models inference endpoint (required for image embeddings)
            # Set FOUNDRY_MODELS_ENDPOINT=https://your-endpoint.inference.ai.azure.com
            # Set FOUNDRY_MODELS_API_KEY=your-key
            # Set FOUNDRY_IMAGE_EMBEDDING_MODEL=Cohere-embed-v3-english
            image_client = FoundryEmbeddingClient()

            # Text embeddings
            result = await client.get_embeddings(["Hello, world!"])

            # Image embeddings
            from agent_framework import Content

            image = Content.from_data(data=image_bytes, media_type="image/png")
            result = await image_client.get_embeddings([image])

            # Mixed text and image
            result = await image_client.get_embeddings(["hello", image])
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.inference"

    def __init__(
        self,
        *,
        model: str | None = None,
        image_model: str | None = None,
        endpoint: str | None = None,
        project_endpoint: str | None = None,
        project_client: AIProjectClient | None = None,
        api_key: str | SecretString | None = None,
        text_client: EmbeddingsClient | None = None,
        image_client: ImageEmbeddingsClient | None = None,
        credential: AzureKeyCredential | AsyncTokenCredential | None = None,
        allow_preview: bool | None = None,
        default_headers: Mapping[str, str] | None = None,
        otel_provider_name: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a Foundry embedding client."""
        super().__init__(
            model=model,
            image_model=image_model,
            endpoint=endpoint,
            project_endpoint=project_endpoint,
            project_client=project_client,
            api_key=api_key,
            text_client=text_client,
            image_client=image_client,
            credential=credential,
            allow_preview=allow_preview,
            default_headers=default_headers,
            additional_properties=additional_properties,
            otel_provider_name=otel_provider_name,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        if otel_provider_name is None and self.project_client is not None:
            self.otel_provider_name = "azure.ai.foundry"
