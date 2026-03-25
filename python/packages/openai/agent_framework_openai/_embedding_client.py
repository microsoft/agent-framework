# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import base64
import struct
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import copy
from typing import Any, ClassVar, Generic, Literal, TypedDict

from agent_framework._clients import BaseEmbeddingClient
from agent_framework._settings import SecretString, load_settings
from agent_framework._telemetry import APP_INFO, USER_AGENT_KEY, prepend_agent_framework_to_user_agent
from agent_framework._types import Embedding, EmbeddingGenerationOptions, GeneratedEmbeddings, UsageDetails
from agent_framework.observability import EmbeddingTelemetryLayer
from openai import AsyncOpenAI

from ._shared import OpenAISettings, get_api_key

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
                "model": "text-embedding-3-small",
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
    BaseEmbeddingClient[str, list[float], OpenAIEmbeddingOptionsT],
    Generic[OpenAIEmbeddingOptionsT],
):
    """Raw OpenAI embedding client without telemetry."""

    INJECTABLE: ClassVar[set[str]] = {"client"}

    def __init__(
        self,
        *,
        model: str | None = None,
        model_id: str | None = None,
        api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a raw OpenAI embedding client.

        Keyword Args:
            model: OpenAI embedding model name.
            model_id: Deprecated alias for ``model``.
            api_key: OpenAI API key, SecretString, or callable returning a key.
            org_id: OpenAI organization ID.
            base_url: Custom API base URL.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured AsyncOpenAI client (skips client creation).
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            kwargs: Additional keyword arguments forwarded to ``BaseEmbeddingClient``.
        """
        if model_id is not None and model is None:
            import warnings

            warnings.warn("model_id is deprecated, use model instead", DeprecationWarning, stacklevel=2)
            model = model_id

        if not async_client:
            openai_settings = load_settings(
                OpenAISettings,
                env_prefix="OPENAI_",
                api_key=api_key,
                org_id=org_id,
                base_url=base_url,
                embedding_model=model,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )

            api_key_value = openai_settings.get("api_key")
            resolved_model = openai_settings.get("embedding_model") or model

            # Only create a client when we have enough configuration.
            # Subclasses that manage their own client pass no args here
            if api_key_value:
                if not resolved_model:
                    raise ValueError(
                        "OpenAI embedding model is required. "
                        "Set via 'model' parameter or 'OPENAI_EMBEDDING_MODEL' environment variable."
                    )
                model = resolved_model

                resolved_api_key = get_api_key(api_key_value)

                # Merge APP_INFO into the headers
                merged_headers = dict(copy(default_headers)) if default_headers else {}
                if APP_INFO:
                    merged_headers.update(APP_INFO)
                    merged_headers = prepend_agent_framework_to_user_agent(merged_headers)

                client_args: dict[str, Any] = {"api_key": resolved_api_key, "default_headers": merged_headers}
                if resolved_org_id := openai_settings.get("org_id"):
                    client_args["organization"] = resolved_org_id
                if resolved_base_url := openai_settings.get("base_url"):
                    client_args["base_url"] = resolved_base_url

                async_client = AsyncOpenAI(**client_args)

        self.client = async_client
        self.model: str | None = model.strip() if model else None

        # Store configuration for serialization
        self.org_id = org_id
        self.base_url = str(base_url) if base_url else None
        if default_headers:
            self.default_headers: dict[str, Any] | None = {
                k: v for k, v in default_headers.items() if k != USER_AGENT_KEY
            }
        else:
            self.default_headers = None

        super().__init__(**kwargs)

    def service_url(self) -> str:
        """Get the URL of the service."""
        return str(self.client.base_url) if self.client else "Unknown"

    async def get_embeddings(
        self,
        values: Sequence[str],
        *,
        options: OpenAIEmbeddingOptionsT | None = None,
    ) -> GeneratedEmbeddings[list[float], OpenAIEmbeddingOptionsT]:
        """Call the OpenAI embeddings API.

        Args:
            values: The text values to generate embeddings for.
            options: Optional embedding generation options.

        Returns:
            Generated embeddings with usage metadata.

        Raises:
            ValueError: If model is not provided or values is empty.
        """
        if not values:
            return GeneratedEmbeddings([], options=options)  # type: ignore

        opts: dict[str, Any] = options or {}  # type: ignore
        # backward compat: accept model_id in options
        model = opts.get("model") or opts.get("model_id") or self.model
        if not model:
            raise ValueError("model is required")

        kwargs: dict[str, Any] = {"input": list(values), "model": model}
        if dimensions := opts.get("dimensions"):
            kwargs["dimensions"] = dimensions
        if encoding_format := opts.get("encoding_format"):
            kwargs["encoding_format"] = encoding_format
        if user := opts.get("user"):
            kwargs["user"] = user

        response = await self.client.embeddings.create(**kwargs)  # type: ignore[union-attr]

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
                    model=response.model,
                )
            )

        usage_dict: UsageDetails | None = None
        if response.usage:
            usage_dict = {
                "input_token_count": response.usage.prompt_tokens,
                "total_token_count": response.usage.total_tokens,
            }

        return GeneratedEmbeddings(embeddings, options=options, usage=usage_dict)


class OpenAIEmbeddingClient(
    EmbeddingTelemetryLayer[str, list[float], OpenAIEmbeddingOptionsT],
    RawOpenAIEmbeddingClient[OpenAIEmbeddingOptionsT],
    Generic[OpenAIEmbeddingOptionsT],
):
    """OpenAI embedding client with telemetry support.

    Keyword Args:
        model: The embedding model (e.g. "text-embedding-3-small").
            Can also be set via environment variable OPENAI_EMBEDDING_MODEL.
        model_id: Deprecated alias for ``model``.
        api_key: OpenAI API key.
            Can also be set via environment variable OPENAI_API_KEY.
        org_id: OpenAI organization ID.
        default_headers: Additional HTTP headers.
        async_client: Pre-configured AsyncOpenAI client.
        base_url: Custom API base URL.
        otel_provider_name: Override the OpenTelemetry provider name for telemetry.
        env_file_path: Path to .env file for settings.
        env_file_encoding: Encoding for .env file.

    Examples:
        .. code-block:: python

            from agent_framework.openai import OpenAIEmbeddingClient

            # Using environment variables
            # Set OPENAI_API_KEY=sk-...
            # Set OPENAI_EMBEDDING_MODEL=text-embedding-3-small
            client = OpenAIEmbeddingClient()

            # Or passing parameters directly
            client = OpenAIEmbeddingClient(
                model="text-embedding-3-small",
                api_key="sk-...",
            )

            # Generate embeddings
            result = await client.get_embeddings(["Hello, world!"])
            print(result[0].vector)
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "openai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        base_url: str | None = None,
        otel_provider_name: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an OpenAI embedding client."""
        super().__init__(
            model=model,
            api_key=api_key,
            org_id=org_id,
            base_url=base_url,
            default_headers=default_headers,
            async_client=async_client,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        if otel_provider_name is not None:
            self.OTEL_PROVIDER_NAME = otel_provider_name  # type: ignore[misc]

        # Validate that the client was created successfully (from explicit args or env vars)
        if self.client is None:
            raise ValueError(
                "OpenAI API key is required. Set via 'api_key' parameter or 'OPENAI_API_KEY' environment variable."
            )
        if not self.model:
            raise ValueError(
                "OpenAI embedding model is required. "
                "Set via 'model' parameter or 'OPENAI_EMBEDDING_MODEL' environment variable."
            )
