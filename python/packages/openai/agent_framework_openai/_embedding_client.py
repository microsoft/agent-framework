# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import base64
import struct
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypedDict, overload

from agent_framework._clients import BaseEmbeddingClient
from agent_framework._settings import SecretString
from agent_framework._telemetry import USER_AGENT_KEY
from agent_framework._types import Embedding, EmbeddingGenerationOptions, GeneratedEmbeddings, UsageDetails
from agent_framework.observability import EmbeddingTelemetryLayer
from openai import AsyncAzureOpenAI, AsyncOpenAI

from ._shared import AzureTokenProvider, load_openai_service_settings

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from azure.core.credentials import TokenCredential
    from azure.core.credentials_async import AsyncTokenCredential

    AzureCredentialTypes = TokenCredential | AsyncTokenCredential


DEFAULT_AZURE_OPENAI_EMBEDDING_API_VERSION = "2024-10-21"


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

    @overload
    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw OpenAI embedding client.

        Keyword Args:
            model: Embedding model identifier. When not provided, the constructor reads
                ``OPENAI_EMBEDDING_MODEL`` and then ``OPENAI_MODEL``.
            api_key: API key. When not provided explicitly, the constructor reads
                ``OPENAI_API_KEY``. A callable API key is also supported.
            org_id: OpenAI organization ID. When not provided explicitly, the constructor reads
                ``OPENAI_ORG_ID``.
            base_url: Base URL override. When not provided explicitly, the constructor reads
                ``OPENAI_BASE_URL``.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured OpenAI client.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Optional ``.env`` file that is checked before the process environment
                for ``OPENAI_*`` values.
            env_file_encoding: Encoding for the ``.env`` file.
        """
        ...

    @overload
    def __init__(
        self,
        *,
        model: str | None = None,
        azure_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        api_version: str | None = None,
        api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None = None,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | AsyncOpenAI | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw OpenAI embedding client.

        Keyword Args:
            model: Embedding deployment name. When not provided, the constructor reads
                ``AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`` and then
                ``AZURE_OPENAI_DEPLOYMENT_NAME``.
            azure_endpoint: Azure resource endpoint. When not provided explicitly, the constructor
                reads ``AZURE_OPENAI_ENDPOINT``.
            credential: Azure credential or token provider for Entra auth.
            api_version: Azure API version. When not provided explicitly, the constructor reads
                ``AZURE_OPENAI_API_VERSION`` and then uses the embedding default.
            api_key: API key. For Azure this can be used instead of ``AZURE_OPENAI_API_KEY`` for key
                auth. A callable token provider is also accepted, but ``credential`` is the preferred
                Azure auth surface.
            base_url: Base URL override. When not provided explicitly, the constructor reads
                ``AZURE_OPENAI_BASE_URL``. Use this instead of ``azure_endpoint`` when you want
                to pass the full ``.../openai/v1`` base URL directly.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured client. Passing ``AsyncAzureOpenAI`` keeps the client on
                Azure; passing ``AsyncOpenAI`` keeps the client on OpenAI.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Optional ``.env`` file that is checked before process environment
                variables for ``AZURE_OPENAI_*`` values.
            env_file_encoding: Encoding for the ``.env`` file.
        """
        ...

    def __init__(
        self,
        *,
        model: str | None = None,
        model_id: str | None = None,
        api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        azure_endpoint: str | None = None,
        api_version: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | AsyncOpenAI | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw OpenAI embedding client.

        Keyword Args:
            model: Embedding model or Azure OpenAI deployment name. When not provided, the
                constructor reads ``OPENAI_EMBEDDING_MODEL`` and then ``OPENAI_MODEL``
                for OpenAI. For Azure it first checks ``AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME``
                and then ``AZURE_OPENAI_DEPLOYMENT_NAME``.
            model_id: Deprecated alias for ``model``.
            api_key: API key override. For OpenAI this maps to ``OPENAI_API_KEY``.
                For Azure this can be used instead of ``AZURE_OPENAI_API_KEY`` for key auth.
                A callable token provider is also accepted for backwards compatibility,
                but ``credential`` is the preferred Azure auth surface.
            credential: Azure credential or token provider for Azure OpenAI auth. Passing this
                is an explicit Azure signal, even when ``OPENAI_API_KEY`` is also configured.
                Credential objects require the optional ``azure-identity`` package.
            org_id: OpenAI organization ID. Used only for OpenAI and resolved from
                ``OPENAI_ORG_ID`` when not provided.
            base_url: Base URL override. For OpenAI this maps to ``OPENAI_BASE_URL``.
                For Azure this may be used instead of ``azure_endpoint`` when you want
                to pass the full ``.../openai/v1`` base URL directly.
            azure_endpoint: Azure resource endpoint. When not provided explicitly, Azure
                falls back to ``AZURE_OPENAI_ENDPOINT``.
            api_version: Azure API version to use for Azure requests. When not provided explicitly,
                Azure falls back to
                ``AZURE_OPENAI_API_VERSION`` and then the embedding default.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured client. Passing ``AsyncAzureOpenAI`` keeps the client on
                Azure; passing ``AsyncOpenAI`` keeps the client on OpenAI.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Optional ``.env`` file that is checked before process environment
                variables. The same file is used for both ``OPENAI_*`` and ``AZURE_OPENAI_*``
                lookups.
            env_file_encoding: Encoding for the ``.env`` file.

        Notes:
            Environment resolution precedence is:

            1. Explicit Azure inputs (``azure_endpoint`` or ``credential``)
            2. Explicit OpenAI API key or ``OPENAI_API_KEY``
            3. Azure environment fallback

            OpenAI reads ``OPENAI_API_KEY``, ``OPENAI_EMBEDDING_MODEL``,
            ``OPENAI_MODEL``, ``OPENAI_ORG_ID``, and ``OPENAI_BASE_URL``. Azure reads
            ``AZURE_OPENAI_ENDPOINT``, ``AZURE_OPENAI_BASE_URL``,
            ``AZURE_OPENAI_API_KEY``, ``AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME``,
            ``AZURE_OPENAI_DEPLOYMENT_NAME``, and ``AZURE_OPENAI_API_VERSION``.
        """
        if model_id is not None and model is None:
            import warnings

            warnings.warn("model_id is deprecated, use model instead", DeprecationWarning, stacklevel=2)
            model = model_id

        settings, client, use_azure_client = load_openai_service_settings(
            model=model,
            api_key=api_key,
            credential=credential,
            org_id=org_id,
            base_url=base_url,
            endpoint=azure_endpoint,
            api_version=api_version,
            default_azure_api_version=DEFAULT_AZURE_OPENAI_EMBEDDING_API_VERSION,
            default_headers=default_headers,
            client=async_client,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            openai_model_fields=("embedding_model", "model"),
            azure_deployment_fields=("embedding_deployment_name", "deployment_name"),
        )

        self.client = client
        resolved_model = settings.get("model") or settings.get("deployment_name")
        self.model: str | None = resolved_model.strip() if isinstance(resolved_model, str) and resolved_model else None

        # Store configuration for serialization
        self.org_id = settings.get("org_id")
        self.base_url = settings.get("base_url")
        self.azure_endpoint = settings.get("endpoint")
        self.api_version = settings.get("api_version")
        if default_headers:
            self.default_headers: dict[str, Any] | None = {
                k: v for k, v in default_headers.items() if k != USER_AGENT_KEY
            }
        else:
            self.default_headers = None
        if use_azure_client:
            self.OTEL_PROVIDER_NAME = "azure.ai.openai"  # type: ignore[misc]

        super().__init__(additional_properties=additional_properties)

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
    """OpenAI embedding client with telemetry support."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "openai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    @overload
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
        """Initialize an OpenAI embedding client.

        Keyword Args:
            model: Embedding model identifier. When not provided, the constructor reads
                ``OPENAI_EMBEDDING_MODEL`` and then ``OPENAI_MODEL``.
            api_key: API key. When not provided explicitly, the constructor reads
                ``OPENAI_API_KEY``. A callable API key is also supported.
            org_id: OpenAI organization ID. When not provided explicitly, the constructor reads
                ``OPENAI_ORG_ID``.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured OpenAI client.
            base_url: Base URL override. When not provided explicitly, the constructor reads
                ``OPENAI_BASE_URL``.
            otel_provider_name: Optional telemetry provider name override.
            env_file_path: Optional ``.env`` file that is checked before the process environment
                for ``OPENAI_*`` values.
            env_file_encoding: Encoding for the ``.env`` file.
        """
        ...

    @overload
    def __init__(
        self,
        *,
        model: str | None = None,
        azure_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        api_version: str | None = None,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | AsyncOpenAI | None = None,
        otel_provider_name: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an OpenAI embedding client.

        Keyword Args:
            model: Embedding deployment name. When not provided, the constructor reads
                ``AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`` and then
                ``AZURE_OPENAI_DEPLOYMENT_NAME``.
            azure_endpoint: Azure resource endpoint. When not provided explicitly, the constructor
                reads ``AZURE_OPENAI_ENDPOINT``.
            credential: Azure credential or token provider for Entra auth.
            api_version: Azure API version. When not provided explicitly, the constructor reads
                ``AZURE_OPENAI_API_VERSION`` and then uses the embedding default.
            api_key: API key. For Azure this can be used instead of ``AZURE_OPENAI_API_KEY`` for key
                auth. A callable token provider is also accepted, but ``credential`` is the preferred
                Azure auth surface.
            base_url: Base URL override. When not provided explicitly, the constructor reads
                ``AZURE_OPENAI_BASE_URL``. Use this instead of ``azure_endpoint`` when you want
                to pass the full ``.../openai/v1`` base URL directly.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured client. Passing ``AsyncAzureOpenAI`` keeps the client on
                Azure; passing ``AsyncOpenAI`` keeps the client on OpenAI.
            otel_provider_name: Optional telemetry provider name override.
            env_file_path: Optional ``.env`` file that is checked before process environment
                variables for ``AZURE_OPENAI_*`` values.
            env_file_encoding: Encoding for the ``.env`` file.
        """
        ...

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | AsyncOpenAI | None = None,
        base_url: str | None = None,
        azure_endpoint: str | None = None,
        api_version: str | None = None,
        otel_provider_name: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an OpenAI embedding client.

        Keyword Args:
            model: Embedding model or Azure OpenAI deployment name. When not provided, the
                constructor reads ``OPENAI_EMBEDDING_MODEL`` and then ``OPENAI_MODEL``
                for OpenAI. For Azure it first checks ``AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME``
                and then ``AZURE_OPENAI_DEPLOYMENT_NAME``.
            api_key: API key override. For OpenAI this maps to ``OPENAI_API_KEY``.
                For Azure this can be used instead of ``AZURE_OPENAI_API_KEY`` for key auth.
                A callable token provider is also accepted for backwards compatibility,
                but ``credential`` is the preferred Azure auth surface.
            credential: Azure credential or token provider for Azure OpenAI auth. Passing this
                is an explicit Azure signal, even when ``OPENAI_API_KEY`` is also configured.
                Credential objects require the optional ``azure-identity`` package.
            org_id: OpenAI organization ID. Used only for OpenAI and resolved from
                ``OPENAI_ORG_ID`` when not provided.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured client. Passing ``AsyncAzureOpenAI`` keeps the client on
                Azure; passing ``AsyncOpenAI`` keeps the client on OpenAI.
            base_url: Base URL override. For OpenAI this maps to ``OPENAI_BASE_URL``.
                For Azure this may be used instead of ``azure_endpoint`` when you want
                to pass the full ``.../openai/v1`` base URL directly.
            azure_endpoint: Azure resource endpoint. When not provided explicitly, Azure
                falls back to ``AZURE_OPENAI_ENDPOINT``.
            api_version: Azure API version to use for Azure requests. When not provided explicitly,
                Azure falls back to
                ``AZURE_OPENAI_API_VERSION`` and then the embedding default.
            otel_provider_name: Override the OpenTelemetry provider name.
            env_file_path: Optional ``.env`` file that is checked before process environment
                variables. The same file is used for both ``OPENAI_*`` and ``AZURE_OPENAI_*``
                lookups.
            env_file_encoding: Encoding for the ``.env`` file.

        Notes:
            Environment resolution precedence is:

            1. Explicit Azure inputs (``azure_endpoint`` or ``credential``)
            2. Explicit OpenAI API key or ``OPENAI_API_KEY``
            3. Azure environment fallback

            OpenAI reads ``OPENAI_API_KEY``, ``OPENAI_EMBEDDING_MODEL``,
            ``OPENAI_MODEL``, ``OPENAI_ORG_ID``, and ``OPENAI_BASE_URL``. Azure reads
            ``AZURE_OPENAI_ENDPOINT``, ``AZURE_OPENAI_BASE_URL``,
            ``AZURE_OPENAI_API_KEY``, ``AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME``,
            ``AZURE_OPENAI_DEPLOYMENT_NAME``, and ``AZURE_OPENAI_API_VERSION``.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIEmbeddingClient

                # Using environment variables
                # Set OPENAI_API_KEY=sk-...
                # Set OPENAI_EMBEDDING_MODEL=text-embedding-3-small
                client = OpenAIEmbeddingClient()

                # Or passing OpenAI parameters directly
                client = OpenAIEmbeddingClient(
                    model="text-embedding-3-small",
                    api_key="sk-...",
                )

                # Or using Azure OpenAI with an Azure credential
                client = OpenAIEmbeddingClient(
                    model="text-embedding-3-small",
                    azure_endpoint="https://example-resource.openai.azure.com/",
                    credential=my_azure_credential,
                )
        """
        super().__init__(
            model=model,
            api_key=api_key,
            credential=credential,
            org_id=org_id,
            base_url=base_url,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
            default_headers=default_headers,
            async_client=async_client,
            otel_provider_name=otel_provider_name,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
