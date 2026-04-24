# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from typing import Any, ClassVar, Generic, TypedDict

from agent_framework import (
    BaseEmbeddingClient,
    Embedding,
    EmbeddingGenerationOptions,
    GeneratedEmbeddings,
    UsageDetails,
    load_settings,
)
from agent_framework._settings import SecretString
from agent_framework.observability import EmbeddingTelemetryLayer
from mistralai.client import Mistral

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover


logger = logging.getLogger("agent_framework.mistral")


class MistralEmbeddingOptions(EmbeddingGenerationOptions, total=False):
    """Mistral AI-specific embedding options.

    Extends EmbeddingGenerationOptions with Mistral-specific fields.

    Examples:
        .. code-block:: python

            from agent_framework_mistral import MistralEmbeddingOptions

            options: MistralEmbeddingOptions = {
                "model": "mistral-embed",
                "dimensions": 1024,
            }
    """


MistralEmbeddingOptionsT = TypeVar(
    "MistralEmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="MistralEmbeddingOptions",
    covariant=True,
)


class MistralEmbeddingSettings(TypedDict, total=False):
    """Mistral AI embedding settings.

    Fields:
        api_key: Mistral API key. Resolved from ``MISTRAL_API_KEY``.
        embedding_model: Embedding model name. Resolved from ``MISTRAL_EMBEDDING_MODEL``.
        server_url: Optional server URL override. Resolved from ``MISTRAL_SERVER_URL``.
    """

    api_key: str | None
    embedding_model: str | None
    server_url: str | None


class RawMistralEmbeddingClient(
    BaseEmbeddingClient[str, list[float], MistralEmbeddingOptionsT],
    Generic[MistralEmbeddingOptionsT],
):
    """Raw Mistral AI embedding client without telemetry.

    Keyword Args:
        model: The Mistral embedding model (e.g. "mistral-embed").
            Can also be set via environment variable ``MISTRAL_EMBEDDING_MODEL``.
        api_key: Mistral API key. Defaults to ``MISTRAL_API_KEY`` environment variable.
        server_url: Optional server URL override. Defaults to ``MISTRAL_SERVER_URL``
            environment variable, or the Mistral default.
        client: Optional pre-configured ``Mistral`` client instance.
        additional_properties: Additional properties stored on the client instance.
        env_file_path: Path to ``.env`` file for settings.
        env_file_encoding: Encoding for ``.env`` file.
    """

    INJECTABLE: ClassVar[set[str]] = {"client"}

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | None = None,
        server_url: str | None = None,
        client: Mistral | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw Mistral AI embedding client."""
        mistral_settings = load_settings(
            MistralEmbeddingSettings,
            env_prefix="MISTRAL_",
            required_fields=["embedding_model", "api_key"],
            api_key=str(api_key) if isinstance(api_key, SecretString) else api_key,
            embedding_model=model,
            server_url=server_url,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self.model: str = mistral_settings["embedding_model"]  # type: ignore[assignment]
        resolved_api_key: str = mistral_settings["api_key"]  # type: ignore[assignment]
        resolved_server_url = mistral_settings.get("server_url")

        if client is not None:
            self.client = client
        else:
            client_kwargs: dict[str, Any] = {"api_key": resolved_api_key}
            if resolved_server_url:
                client_kwargs["server_url"] = resolved_server_url
            self.client = Mistral(**client_kwargs)

        self.server_url = resolved_server_url
        super().__init__(additional_properties=additional_properties)

    def service_url(self) -> str:
        """Get the URL of the service."""
        return self.server_url or "https://api.mistral.ai"

    async def get_embeddings(
        self,
        values: Sequence[str],
        *,
        options: MistralEmbeddingOptionsT | None = None,
    ) -> GeneratedEmbeddings[list[float], MistralEmbeddingOptionsT]:
        """Call the Mistral AI embeddings API.

        Args:
            values: The text values to generate embeddings for.
            options: Optional embedding generation options.

        Returns:
            Generated embeddings with usage metadata.

        Raises:
            ValueError: If model is not provided or values is empty.
        """
        if not values:
            return GeneratedEmbeddings([], options=options)

        opts: dict[str, Any] = options or {}  # type: ignore
        model = opts.get("model") or self.model
        if not model:
            raise ValueError("model is required")

        kwargs: dict[str, Any] = {"model": model, "inputs": list(values)}
        if dimensions := opts.get("dimensions"):
            kwargs["output_dimension"] = dimensions

        response = await self.client.embeddings.create_async(**kwargs)

        embeddings: list[Embedding[list[float]]] = []
        if response and response.data:
            for item in response.data:
                vector = list(item.embedding) if item.embedding else []
                embeddings.append(
                    Embedding(
                        vector=vector,
                        dimensions=len(vector),
                        model=response.model or model,
                    )
                )

        usage_dict: UsageDetails | None = None
        if response and response.usage:
            usage_dict = {
                "input_token_count": response.usage.prompt_tokens,
                "total_token_count": response.usage.total_tokens,
            }

        return GeneratedEmbeddings(embeddings, options=options, usage=usage_dict)


class MistralEmbeddingClient(
    EmbeddingTelemetryLayer[str, list[float], MistralEmbeddingOptionsT],
    RawMistralEmbeddingClient[MistralEmbeddingOptionsT],
    Generic[MistralEmbeddingOptionsT],
):
    """Mistral AI embedding client with telemetry support.

    Keyword Args:
        model: The Mistral embedding model (e.g. "mistral-embed").
            Can also be set via environment variable ``MISTRAL_EMBEDDING_MODEL``.
        api_key: Mistral API key. Defaults to ``MISTRAL_API_KEY`` environment variable.
        server_url: Optional server URL override. Defaults to ``MISTRAL_SERVER_URL``
            environment variable, or the Mistral default.
        client: Optional pre-configured ``Mistral`` client instance.
        otel_provider_name: Optional telemetry provider name override.
        env_file_path: Path to ``.env`` file for settings.
        env_file_encoding: Encoding for ``.env`` file.

    Examples:
        .. code-block:: python

            from agent_framework_mistral import MistralEmbeddingClient

            # Using environment variables
            # Set MISTRAL_API_KEY=your-key
            # Set MISTRAL_EMBEDDING_MODEL=mistral-embed
            client = MistralEmbeddingClient()

            # Or passing parameters directly
            client = MistralEmbeddingClient(
                model="mistral-embed",
                api_key="your-api-key",
            )

            # Generate embeddings
            result = await client.get_embeddings(["Hello, world!"])
            print(result[0].vector)
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "mistralai"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | None = None,
        server_url: str | None = None,
        client: Mistral | None = None,
        otel_provider_name: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a Mistral AI embedding client."""
        super().__init__(
            model=model,
            api_key=api_key,
            server_url=server_url,
            client=client,
            additional_properties=additional_properties,
            otel_provider_name=otel_provider_name,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
