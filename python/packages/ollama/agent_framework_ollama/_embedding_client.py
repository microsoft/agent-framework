# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from typing import Any, ClassVar, Generic, TypedDict, cast

from agent_framework import (
    BaseEmbeddingClient,
    Embedding,
    EmbeddingGenerationOptions,
    GeneratedEmbeddings,
    UsageDetails,
    load_settings,
)
from agent_framework.observability import EmbeddingTelemetryLayer
from ollama import AsyncClient

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover


logger = logging.getLogger("agent_framework.ollama")


class OllamaEmbeddingOptions(EmbeddingGenerationOptions, total=False):
    """Ollama-specific embedding options.

    Extends EmbeddingGenerationOptions with Ollama-specific fields.

    Examples:
        .. code-block:: python

            from agent_framework_ollama import OllamaEmbeddingOptions

            options: OllamaEmbeddingOptions = {
                "model": "nomic-embed-text",
                "dimensions": 768,
                "truncate": True,
            }
    """

    truncate: bool
    """Whether to truncate input text that exceeds the model's context length.

    When True, input that is too long will be silently truncated.
    When False (default), the request will fail if input exceeds the context length.
    """

    keep_alive: float | str
    """How long to keep the model loaded in memory (e.g. ``"5m"``, ``300``)."""


OllamaEmbeddingOptionsT = TypeVar(
    "OllamaEmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OllamaEmbeddingOptions",
    covariant=True,
)


class OllamaEmbeddingSettings(TypedDict, total=False):
    """Ollama embedding settings."""

    host: str | None
    embedding_model: str | None


class RawOllamaEmbeddingClient(
    BaseEmbeddingClient[str, list[float], OllamaEmbeddingOptionsT],
    Generic[OllamaEmbeddingOptionsT],
):
    """Raw Ollama embedding client without telemetry.

    Keyword Args:
        model: The Ollama embedding model (e.g. "nomic-embed-text").
            Can also be set via environment variable OLLAMA_EMBEDDING_MODEL.
        host: Ollama server URL. Defaults to http://localhost:11434.
            Can also be set via environment variable OLLAMA_HOST.
        client: Optional pre-configured Ollama AsyncClient.
        env_file_path: Path to .env file for settings.
        env_file_encoding: Encoding for .env file.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        host: str | None = None,
        client: AsyncClient | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw Ollama embedding client."""
        ollama_settings = load_settings(
            OllamaEmbeddingSettings,
            env_prefix="OLLAMA_",
            required_fields=["embedding_model"],
            host=host,
            embedding_model=model,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self.model = ollama_settings["embedding_model"]  # type: ignore[assignment,reportTypedDictNotRequiredAccess]
        self.client = client or AsyncClient(host=ollama_settings.get("host"))
        self.host = str(self.client._client.base_url)  # type: ignore[reportUnknownMemberType,reportPrivateUsage,reportUnknownArgumentType]
        super().__init__(additional_properties=additional_properties)

    def service_url(self) -> str:
        """Get the URL of the service."""
        return self.host

    async def get_embeddings(
        self,
        values: Sequence[str],
        *,
        options: OllamaEmbeddingOptionsT | None = None,  # type: ignore
    ) -> GeneratedEmbeddings[list[float], OllamaEmbeddingOptionsT]:
        """Call the Ollama embed API.

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

        kwargs: dict[str, Any] = {"model": model, "input": list(values)}
        if (truncate := opts.get("truncate")) is not None:
            kwargs["truncate"] = truncate
        if keep_alive := opts.get("keep_alive"):
            kwargs["keep_alive"] = keep_alive
        if dimensions := opts.get("dimensions"):
            kwargs["dimensions"] = dimensions

        response = await self.client.embed(**kwargs)

        embeddings = [
            Embedding(
                vector=list(emb),
                dimensions=len(emb),
                model=response.get("model") or model,  # type: ignore[assignment]
            )
            for emb in response.get("embeddings", [])
        ]

        usage_dict: UsageDetails | None = None
        prompt_eval_count = response.get("prompt_eval_count")
        if prompt_eval_count is not None:
            usage_dict = {"input_token_count": prompt_eval_count}

        return GeneratedEmbeddings(embeddings, options=cast(OllamaEmbeddingOptionsT, opts), usage=usage_dict)


class OllamaEmbeddingClient(
    EmbeddingTelemetryLayer[str, list[float], OllamaEmbeddingOptionsT],
    RawOllamaEmbeddingClient[OllamaEmbeddingOptionsT],
    Generic[OllamaEmbeddingOptionsT],
):
    """Ollama embedding client with telemetry support.

    Keyword Args:
        model: The Ollama embedding model (e.g. "nomic-embed-text").
            Can also be set via environment variable OLLAMA_EMBEDDING_MODEL.
        host: Ollama server URL. Defaults to http://localhost:11434.
            Can also be set via environment variable OLLAMA_HOST.
        client: Optional pre-configured Ollama AsyncClient.
        env_file_path: Path to .env file for settings.
        env_file_encoding: Encoding for .env file.

    Examples:
        .. code-block:: python

            from agent_framework_ollama import OllamaEmbeddingClient

            # Using environment variables
            # Set OLLAMA_EMBEDDING_MODEL=nomic-embed-text
            client = OllamaEmbeddingClient()

            # Or passing parameters directly
            client = OllamaEmbeddingClient(
                model="nomic-embed-text",
                host="http://localhost:11434",
            )

            # Generate embeddings
            result = await client.get_embeddings(["Hello, world!"])
            print(result[0].vector)
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "ollama"

    def __init__(
        self,
        *,
        model: str | None = None,
        host: str | None = None,
        client: AsyncClient | None = None,
        otel_provider_name: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Ollama embedding client."""
        super().__init__(
            model=model,
            host=host,
            client=client,
            additional_properties=additional_properties,
            otel_provider_name=otel_provider_name,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
