# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Generic

from openai.lib.azure import AsyncAzureOpenAI

from agent_framework.observability import EmbeddingTelemetryLayer
from agent_framework.openai import OpenAIEmbeddingOptions
from agent_framework.openai._embedding_client import RawOpenAIEmbeddingClient

from .._settings import load_settings
from ._entra_id_authentication import AzureCredentialTypes, AzureTokenProvider
from ._shared import (
    AzureOpenAIConfigMixin,
    AzureOpenAISettings,
    _apply_azure_defaults,
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover


AzureOpenAIEmbeddingOptionsT = TypeVar(
    "AzureOpenAIEmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIEmbeddingOptions",
    covariant=True,
)


class AzureOpenAIEmbeddingClient(
    AzureOpenAIConfigMixin,
    EmbeddingTelemetryLayer[str, list[float], AzureOpenAIEmbeddingOptionsT],
    RawOpenAIEmbeddingClient[AzureOpenAIEmbeddingOptionsT],
    Generic[AzureOpenAIEmbeddingOptionsT],
):
    """Azure OpenAI embedding client with telemetry support.

    Keyword Args:
        api_key: The API key. If provided, will override the value in the env vars or .env file.
            Can also be set via environment variable AZURE_OPENAI_API_KEY.
        deployment_name: The deployment name. If provided, will override the value
            (embedding_deployment_name) in the env vars or .env file.
            Can also be set via environment variable AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME.
        endpoint: The deployment endpoint.
            Can also be set via environment variable AZURE_OPENAI_ENDPOINT.
        base_url: The deployment base URL.
            Can also be set via environment variable AZURE_OPENAI_BASE_URL.
        api_version: The deployment API version.
            Can also be set via environment variable AZURE_OPENAI_API_VERSION.
        token_endpoint: The token endpoint to request an Azure token.
            Can also be set via environment variable AZURE_OPENAI_TOKEN_ENDPOINT.
        credential: Azure credential or token provider for authentication.
        default_headers: Default headers for HTTP requests.
        async_client: An existing client to use.
        env_file_path: Path to .env file for settings.
        env_file_encoding: Encoding for .env file.

    Examples:
        .. code-block:: python

            from agent_framework.azure import AzureOpenAIEmbeddingClient

            # Using environment variables
            # Set AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
            # Set AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-small
            # Set AZURE_OPENAI_API_KEY=your-key
            client = AzureOpenAIEmbeddingClient()

            # Or passing parameters directly
            client = AzureOpenAIEmbeddingClient(
                endpoint="https://your-endpoint.openai.azure.com",
                deployment_name="text-embedding-3-small",
                api_key="your-key",
            )

            result = await client.get_embeddings(["Hello, world!"])
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        deployment_name: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        token_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Azure OpenAI embedding client."""
        azure_openai_settings = load_settings(
            AzureOpenAISettings,
            env_prefix="AZURE_OPENAI_",
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            embedding_deployment_name=deployment_name,
            api_version=api_version,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            token_endpoint=token_endpoint,
        )
        _apply_azure_defaults(azure_openai_settings)

        if not azure_openai_settings.get("embedding_deployment_name"):
            raise ValueError(
                "Azure OpenAI embedding deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME' environment variable."
            )

        super().__init__(
            deployment_name=azure_openai_settings["embedding_deployment_name"],  # type: ignore[arg-type]
            endpoint=azure_openai_settings["endpoint"],
            base_url=azure_openai_settings["base_url"],
            api_version=azure_openai_settings["api_version"],  # type: ignore
            api_key=azure_openai_settings["api_key"].get_secret_value() if azure_openai_settings["api_key"] else None,
            token_endpoint=azure_openai_settings["token_endpoint"],
            credential=credential,
            default_headers=default_headers,
            client=async_client,
        )
