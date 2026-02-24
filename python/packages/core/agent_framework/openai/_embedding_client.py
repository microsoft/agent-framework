# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import base64
import struct
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Generic, Literal, TypedDict

from openai import AsyncOpenAI

from .._clients import BaseEmbeddingClient
from .._settings import load_settings
from .._types import Embedding, EmbeddingGenerationOptions, GeneratedEmbeddings
from ..observability import EmbeddingTelemetryLayer
from ._shared import OpenAIBase, OpenAIConfigMixin, OpenAISettings

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover


class OpenAIEmbeddingOptions(EmbeddingGenerationOptions, total=False):
    """OpenAI-specific embedding options.

    Extends EmbeddingGenerationOptions with OpenAI-specific fields.

    Examples:
        .. code-block:: python

            from agent_framework.openai import OpenAIEmbeddingOptions

            options: OpenAIEmbeddingOptions = {
                "model_id": "text-embedding-3-small",
                "dimensions": 1536,
                "encoding_format": "float",
            }
    """

    encoding_format: Literal["float", "base64"]
    user: str


OpenAIEmbeddingOptionsT = TypeVar(
    "OpenAIEmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIEmbeddingOptions",
    covariant=True,
)


class RawOpenAIEmbeddingClient(
    OpenAIBase,
    BaseEmbeddingClient[str, list[float], OpenAIEmbeddingOptionsT],
    Generic[OpenAIEmbeddingOptionsT],
):
    """Raw OpenAI embedding client without telemetry."""

    def service_url(self) -> str:
        """Get the URL of the service."""
        return str(self.client.base_url) if self.client else "Unknown"

    async def get_embeddings(
        self,
        values: Sequence[str],
        *,
        options: OpenAIEmbeddingOptionsT | None = None,
    ) -> GeneratedEmbeddings[list[float]]:
        """Call the OpenAI embeddings API.

        Args:
            values: The text values to generate embeddings for.
            options: Optional embedding generation options.

        Returns:
            Generated embeddings with usage metadata.

        Raises:
            ValueError: If model_id is not provided or values is empty.
        """
        if not values:
            return GeneratedEmbeddings([], options=options)

        opts: dict[str, Any] = dict(options) if options else {}
        model = opts.get("model_id") or self.model_id
        if not model:
            raise ValueError("model_id is required")

        kwargs: dict[str, Any] = {"input": list(values), "model": model}
        if dimensions := opts.get("dimensions"):
            kwargs["dimensions"] = dimensions
        if encoding_format := opts.get("encoding_format"):
            kwargs["encoding_format"] = encoding_format
        if user := opts.get("user"):
            kwargs["user"] = user

        response = await (await self._ensure_client()).embeddings.create(**kwargs)

        encoding = kwargs.get("encoding_format", "float")
        embeddings: list[Embedding[list[float]]] = []
        for item in response.data:
            vector: list[float]
            if encoding == "base64" and isinstance(item.embedding, str):
                # Decode base64-encoded floats (little-endian IEEE 754)
                raw = base64.b64decode(item.embedding)
                vector = list(struct.unpack(f"<{len(raw) // 4}f", raw))
            else:
                vector = item.embedding  # type: ignore[assignment]
            embeddings.append(
                Embedding(
                    vector=vector,
                    dimensions=len(vector),
                    model_id=response.model,
                )
            )

        usage_dict: dict[str, Any] | None = None
        if response.usage:
            usage_dict = {
                "prompt_tokens": response.usage.prompt_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return GeneratedEmbeddings(embeddings, options=options, usage=usage_dict)


class OpenAIEmbeddingClient(
    OpenAIConfigMixin,
    EmbeddingTelemetryLayer[str, list[float], OpenAIEmbeddingOptionsT],
    RawOpenAIEmbeddingClient[OpenAIEmbeddingOptionsT],
    Generic[OpenAIEmbeddingOptionsT],
):
    """OpenAI embedding client with telemetry support.

    Keyword Args:
        model_id: The embedding model ID (e.g. "text-embedding-3-small").
            Can also be set via environment variable OPENAI_EMBEDDING_MODEL_ID.
        api_key: OpenAI API key.
            Can also be set via environment variable OPENAI_API_KEY.
        org_id: OpenAI organization ID.
        default_headers: Additional HTTP headers.
        async_client: Pre-configured AsyncOpenAI client.
        base_url: Custom API base URL.
        env_file_path: Path to .env file for settings.
        env_file_encoding: Encoding for .env file.

    Examples:
        .. code-block:: python

            from agent_framework.openai import OpenAIEmbeddingClient

            # Using environment variables
            # Set OPENAI_API_KEY=sk-...
            # Set OPENAI_EMBEDDING_MODEL_ID=text-embedding-3-small
            client = OpenAIEmbeddingClient()

            # Or passing parameters directly
            client = OpenAIEmbeddingClient(
                model_id="text-embedding-3-small",
                api_key="sk-...",
            )

            # Generate embeddings
            result = await client.get_embeddings(["Hello, world!"])
            print(result[0].vector)
    """

    def __init__(
        self,
        *,
        model_id: str | None = None,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        base_url: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an OpenAI embedding client."""
        openai_settings = load_settings(
            OpenAISettings,
            env_prefix="OPENAI_",
            api_key=api_key,
            base_url=base_url,
            org_id=org_id,
            embedding_model_id=model_id,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        if not async_client and not openai_settings["api_key"]:
            raise ValueError(
                "OpenAI API key is required. Set via 'api_key' parameter or 'OPENAI_API_KEY' environment variable."
            )
        if not openai_settings["embedding_model_id"]:
            raise ValueError(
                "OpenAI embedding model ID is required. "
                "Set via 'model_id' parameter or 'OPENAI_EMBEDDING_MODEL_ID' environment variable."
            )

        super().__init__(
            model_id=openai_settings["embedding_model_id"],
            api_key=self._get_api_key(openai_settings["api_key"]),
            base_url=openai_settings["base_url"] if openai_settings["base_url"] else None,
            org_id=openai_settings["org_id"],
            default_headers=default_headers,
            client=async_client,
        )
