# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, ClassVar, Generic, Literal, TypedDict

from agent_framework import (
    Embedding,
    GeneratedEmbeddings,
    SecretString,
    UsageDetails,
    add_usage_details,
    load_settings,
)
from agent_framework.observability import EmbeddingTelemetryLayer
from agent_framework_openai import OpenAIEmbeddingOptions
from agent_framework_openai._embedding_client import RawOpenAIEmbeddingClient
from openai import AsyncOpenAI

from ._feature_usage import FeatureIndex

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover

__all__ = [
    "NvidiaEmbeddingClient",
    "NvidiaEmbeddingOptions",
    "NvidiaEmbeddingSettings",
    "RawNvidiaEmbeddingClient",
]

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
"""NVIDIA's hosted NIM endpoint, which exposes an OpenAI-compatible surface."""


MAX_BATCH_SIZE = 256
"""The most inputs NVIDIA's hosted endpoint accepts in one embeddings request."""

MAX_BATCH_BYTES = 2_000_000
"""Budget for the inputs of one request. The hosted endpoint rejects bodies over 2 MiB with ``413``,
so this leaves room for the other request fields."""


def _batches(values: Sequence[str]) -> Iterator[Sequence[str]]:
    """Split ``values`` into consecutive runs within both ``MAX_BATCH_SIZE`` and ``MAX_BATCH_BYTES``.

    Each input is costed at its ASCII-escaped JSON length, which is never less than the bytes it
    occupies in the request. An input over the byte budget on its own still gets its own request.
    """
    start, size = 0, 0
    for index, value in enumerate(values):
        cost = len(json.dumps(value)) + 1
        if index > start and (index - start == MAX_BATCH_SIZE or size + cost > MAX_BATCH_BYTES):
            yield values[start:index]
            start, size = index, 0
        size += cost
    if start < len(values):
        yield values[start:]


_INPUT_TYPES = ("query", "passage")
_TRUNCATE_MODES = ("NONE", "START", "END")


class NvidiaEmbeddingOptions(OpenAIEmbeddingOptions, total=False):
    """Request settings for NVIDIA embedding generation.

    NVIDIA accepts the OpenAI embedding options, including ``encoding_format`` and ``user``,
    plus the two keys below.

    Keys:
        input_type: ``"passage"`` for documents being stored and ``"query"`` for search
            text. Asymmetric retrieval models embed the two differently, so set it per
            call, for example through ``embeddings_options`` on vector upsert and search.
            Omitted, the service uses its default and the key is not sent.
        truncate: How the service handles long input. ``"START"`` or ``"END"`` drop tokens
            from that end, and ``"NONE"`` rejects input over the model's token limit
            (4,096 for ``nvidia/nemotron-3-embed-1b``). Omitted, the service shortens
            over-limit input itself but still rejects any input over 65,536 characters,
            and one such input fails the whole call, so set ``"START"`` or ``"END"`` when
            ingesting documents of unknown length.
    """

    input_type: Literal["query", "passage"]
    truncate: Literal["NONE", "START", "END"]


NvidiaEmbeddingOptionsT = TypeVar(
    "NvidiaEmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="NvidiaEmbeddingOptions",
    covariant=True,
)


class NvidiaEmbeddingSettings(TypedDict, total=False):
    """NVIDIA embedding settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'NVIDIA_'.

    Keys:
        api_key: The API key for NVIDIA's hosted endpoint.
            (Env var NVIDIA_API_KEY)
        embedding_model: The embedding model to use, for example
            ``nvidia/nemotron-3-embed-1b``. (Env var NVIDIA_EMBEDDING_MODEL)
        base_url: Override for the endpoint. Defaults to NVIDIA's hosted NIM surface,
            and is the hook for pointing at a self-hosted NIM container.
            (Env var NVIDIA_BASE_URL)
    """

    api_key: SecretString | None
    embedding_model: str | None
    base_url: str | None


class RawNvidiaEmbeddingClient(
    RawOpenAIEmbeddingClient[NvidiaEmbeddingOptionsT],
    Generic[NvidiaEmbeddingOptionsT],
):
    """NVIDIA NIM embedding client without telemetry.

    NVIDIA's NIM endpoint is OpenAI-compatible, so this builds on the OpenAI embedding
    client rather than reimplementing the wire format, in the same way
    ``agent_framework_foundry_local`` builds on the OpenAI Chat Completions client.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "nvidia"
    _FEATURE_USAGE_INDEX: ClassVar[int | None] = FeatureIndex.NVIDIA

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | None = None,
        base_url: str | None = None,
        async_client: AsyncOpenAI | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw NVIDIA embedding client.

        Keyword Args:
            model: The embedding model to use. Falls back to NVIDIA_EMBEDDING_MODEL.
            api_key: The API key. Falls back to NVIDIA_API_KEY.
            base_url: Endpoint override, for a self-hosted NIM container. Falls back to
                NVIDIA_BASE_URL, then to NVIDIA's hosted endpoint.
            async_client: A pre-configured client to use instead of one built from the
                settings above. It stays caller-owned: ``close()`` leaves it open.
            additional_properties: Extra properties carried on the client.
            env_file_path: Path to a .env file to read settings from.
            env_file_encoding: Encoding of that .env file.

        Raises:
            ValueError: If no model is supplied, or if no API key is available and no
                pre-configured client was passed.
        """
        settings = load_settings(
            NvidiaEmbeddingSettings,
            env_prefix="NVIDIA_",
            required_fields=["embedding_model"],
            embedding_model=model,
            api_key=api_key,
            base_url=base_url,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        model_setting: str = settings["embedding_model"]  # type: ignore[assignment]

        owns_client = async_client is None
        if async_client is None:
            key = settings.get("api_key")
            if key is None:
                raise ValueError(
                    "An NVIDIA API key is required. Set NVIDIA_API_KEY, pass api_key, "
                    "or supply a pre-configured async_client."
                )
            async_client = AsyncOpenAI(
                api_key=key.get_secret_value(),
                base_url=settings.get("base_url") or DEFAULT_BASE_URL,
            )

        super().__init__(
            model=model_setting,
            async_client=async_client,
            additional_properties=additional_properties,
        )
        self._owns_client = owns_client

    async def close(self) -> None:
        """Close the HTTP client this instance created. A supplied ``async_client`` stays open for its owner."""
        if self._owns_client:
            await self.client.close()

    async def get_embeddings(
        self,
        values: Sequence[str],
        *,
        options: NvidiaEmbeddingOptionsT | None = None,
    ) -> GeneratedEmbeddings[list[float], NvidiaEmbeddingOptionsT]:
        """Generate one embedding per value, splitting large inputs into several requests.

        The hosted endpoint rejects a request with more than ``MAX_BATCH_SIZE`` inputs or a body
        over 2 MiB, and a vector-store upsert embeds every record in one call, so larger inputs
        are sent as consecutive requests within both limits. Vectors keep the order of
        ``values``, usage is summed, and a failed request fails the whole call.

        Args:
            values: The texts to embed.
            options: Embedding options, applied to every request.

        Returns:
            One embedding per value, in order.
        """
        batches = list(_batches(values))
        if len(batches) <= 1:
            return await super().get_embeddings(values, options=options)
        embeddings: list[Embedding[list[float]]] = []
        usage: UsageDetails | None = None
        for values_batch in batches:
            batch = await super().get_embeddings(values_batch, options=options)
            embeddings.extend(batch)
            if batch.usage:
                usage = add_usage_details(usage, batch.usage)
        return GeneratedEmbeddings(embeddings, options=options, usage=usage)

    def _prepare_extra_request_options(self, options: Mapping[str, Any]) -> dict[str, Any]:
        """Send ``input_type`` and ``truncate``, which are outside the OpenAI schema, as ``extra_body``.

        Raises:
            ValueError: If ``input_type`` or ``truncate`` is not a value NVIDIA accepts.
        """
        extra_body: dict[str, Any] = {}
        input_type = options.get("input_type")
        if input_type is not None:
            if input_type not in _INPUT_TYPES:
                raise ValueError(f"Unsupported NVIDIA embedding input_type: {input_type!r}.")
            extra_body["input_type"] = input_type
        truncate = options.get("truncate")
        if truncate is not None:
            if truncate not in _TRUNCATE_MODES:
                raise ValueError(f"Unsupported NVIDIA embedding truncate mode: {truncate!r}.")
            extra_body["truncate"] = truncate
        return {"extra_body": extra_body} if extra_body else {}


class NvidiaEmbeddingClient(
    EmbeddingTelemetryLayer[str, list[float], NvidiaEmbeddingOptionsT],
    RawNvidiaEmbeddingClient[NvidiaEmbeddingOptionsT],
    Generic[NvidiaEmbeddingOptionsT],
):
    """NVIDIA NIM embedding client with telemetry support."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "nvidia"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | None = None,
        base_url: str | None = None,
        async_client: AsyncOpenAI | None = None,
        additional_properties: dict[str, Any] | None = None,
        otel_provider_name: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an NVIDIA embedding client with telemetry.

        Keyword Args:
            model: The embedding model to use. Falls back to NVIDIA_EMBEDDING_MODEL.
            api_key: The API key. Falls back to NVIDIA_API_KEY.
            base_url: Endpoint override, for a self-hosted NIM container. Falls back to
                NVIDIA_BASE_URL, then to NVIDIA's hosted endpoint.
            async_client: A pre-configured client to use instead of one built from the
                settings above. It stays caller-owned: ``close()`` leaves it open.
            additional_properties: Extra properties carried on the client.
            otel_provider_name: Override for the provider name reported in telemetry.
            env_file_path: Path to a .env file to read settings from.
            env_file_encoding: Encoding of that .env file.

        Raises:
            ValueError: If no model is supplied, or if no API key is available and no
                pre-configured client was passed.
        """
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            async_client=async_client,
            additional_properties=additional_properties,
            otel_provider_name=otel_provider_name,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
