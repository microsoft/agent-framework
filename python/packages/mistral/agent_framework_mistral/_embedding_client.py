# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
import warnings
from collections.abc import Sequence
from typing import Any, ClassVar, Generic, NoReturn, TypedDict

import httpx
from agent_framework import (
    BaseEmbeddingClient,
    Embedding,
    EmbeddingGenerationOptions,
    GeneratedEmbeddings,
    UsageDetails,
    load_settings,
)
from agent_framework._settings import SecretString
from agent_framework._telemetry import get_user_agent, mark_feature_used
from agent_framework.exceptions import (
    IntegrationException,
    IntegrationInvalidAuthException,
    IntegrationInvalidRequestException,
    IntegrationInvalidResponseException,
)
from agent_framework.observability import EmbeddingTelemetryLayer
from mistralai.client import Mistral
from mistralai.client.errors import MistralError

from ._feature_usage import FeatureIndex
from ._http_client import AsyncClientUsingConfiguredTimeout

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover


logger = logging.getLogger("agent_framework.mistral")

_MISTRAL_API_BASE_URL = "https://api.mistral.ai"
_DEFAULT_TIMEOUT_MS = 60_000


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

    api_key: SecretString | None
    embedding_model: str | None
    server_url: str | None


class RawMistralEmbeddingClient(
    BaseEmbeddingClient[str, list[float], MistralEmbeddingOptionsT],
    Generic[MistralEmbeddingOptionsT],
):
    """Raw Mistral AI embedding client without telemetry.

    Uses the official ``mistralai`` SDK without the framework's telemetry layer.

    Keyword Args:
        model: The Mistral embedding model (e.g. "mistral-embed").
            Can also be set via environment variable ``MISTRAL_EMBEDDING_MODEL``.
        api_key: Mistral API key. Defaults to ``MISTRAL_API_KEY`` environment variable.
        server_url: Optional server URL override. Defaults to ``MISTRAL_SERVER_URL``
            environment variable, or the Mistral default.
        http_client: Optional pre-configured ``httpx.AsyncClient``. When provided, api_key is
            not required and the client is expected to carry its own auth headers and base URL.
        client: Optional pre-configured ``mistralai.client.Mistral``. Passing an HTTP client via
            this parameter remains supported but is deprecated; use ``http_client`` instead.
        additional_properties: Additional properties stored on the client instance.
        env_file_path: Path to ``.env`` file for settings.
        env_file_encoding: Encoding for ``.env`` file.
    """

    INJECTABLE: ClassVar[set[str]] = {"http_client", "client"}

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | None = None,
        server_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        client: Mistral | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw Mistral AI embedding client."""
        if isinstance(client, httpx.AsyncClient):
            warnings.warn(
                "Passing an httpx.AsyncClient via 'client' is deprecated; pass it via 'http_client' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            if http_client is not None:
                raise ValueError("Provide either 'client' or 'http_client', not both.")
            http_client = client
            client = None
        if client is not None and not isinstance(client, Mistral):
            raise TypeError(
                f"The 'client' parameter accepts a mistralai.client.Mistral instance; got {type(client).__name__}."
            )
        if client is not None and http_client is not None:
            raise ValueError("Provide either 'client' or 'http_client', not both.")

        injected = client is not None or http_client is not None
        required_fields = ["embedding_model"] if injected else ["embedding_model", "api_key"]
        mistral_settings = load_settings(
            MistralEmbeddingSettings,
            env_prefix="MISTRAL_",
            required_fields=required_fields,
            api_key=api_key,
            embedding_model=model,
            server_url=server_url,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self.model: str = mistral_settings["embedding_model"]  # type: ignore[assignment]
        self.server_url = mistral_settings.get("server_url")
        self._owns_client = not isinstance(client, Mistral)

        if isinstance(client, Mistral):
            self.client = client
            if self.server_url is None:
                self.server_url = client.sdk_configuration.get_server_details()[0]
        else:
            client_kwargs: dict[str, Any] = {"timeout_ms": _DEFAULT_TIMEOUT_MS}
            if resolved_api_key := mistral_settings.get("api_key"):
                client_kwargs["api_key"] = resolved_api_key.get_secret_value()
            if http_client is not None:
                client_kwargs["async_client"] = AsyncClientUsingConfiguredTimeout(http_client)
                if self.server_url is None:
                    client_base_url = str(http_client.base_url).rstrip("/")
                    self.server_url = client_base_url or None
            if self.server_url:
                client_kwargs["server_url"] = self.server_url
            self.client = Mistral(**client_kwargs)

        super().__init__(additional_properties=additional_properties)

    async def close(self) -> None:
        """Close the internally created Mistral SDK client."""
        if self._owns_client:
            await self.client.__aexit__(None, None, None)  # type: ignore[no-untyped-call]
            self.client.__exit__(None, None, None)  # type: ignore[no-untyped-call]

    def service_url(self) -> str:
        """Get the URL of the service."""
        return self.server_url or _MISTRAL_API_BASE_URL

    @staticmethod
    def _raise_sdk_error(ex: MistralError) -> NoReturn:
        status_code = ex.raw_response.status_code
        if status_code < 400:
            raise IntegrationInvalidResponseException(
                f"Mistral embeddings response was invalid: {ex}",
                inner_exception=ex,
            ) from ex

        body = ex.body or str(ex)
        message = f"Mistral embeddings request failed with status {status_code}: {body[:2000]}"
        if status_code in (401, 403):
            raise IntegrationInvalidAuthException(message)
        if status_code < 500:
            raise IntegrationInvalidRequestException(message)
        raise IntegrationException(message, inner_exception=ex)

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
            IntegrationInvalidAuthException: If Mistral rejects the configured credentials.
            IntegrationInvalidRequestException: If Mistral rejects the request.
            IntegrationInvalidResponseException: If Mistral returns an invalid response.
            IntegrationException: If the request fails for another reason.
        """
        if not values:
            return GeneratedEmbeddings([], options=options)

        opts: dict[str, Any] = options or {}  # type: ignore
        model = opts.get("model") or self.model
        if not model:
            raise ValueError("model is required")

        mark_feature_used(FeatureIndex.MISTRAL)
        request: dict[str, Any] = {
            "model": model,
            "inputs": list(values),
            "http_headers": {"User-Agent": get_user_agent()},
        }
        if "dimensions" in opts:
            request["output_dimension"] = opts["dimensions"]

        try:
            response = await self.client.embeddings.create_async(**request)
        except MistralError as ex:
            self._raise_sdk_error(ex)
        except IntegrationException:
            raise
        except Exception as ex:
            raise IntegrationException(f"Mistral embeddings request failed: {ex}", inner_exception=ex) from ex

        try:
            embeddings: list[Embedding[list[float]]] = []
            items = sorted(response.data or (), key=lambda item: item.index or 0)
            for item in items:
                vector = [float(value) for value in item.embedding or ()]
                embeddings.append(
                    Embedding(
                        vector=vector,
                        dimensions=len(vector),
                        model=response.model or model,
                    )
                )

            usage_dict: UsageDetails | None = None
            if usage := response.usage:
                usage_dict = {}
                fields_set = getattr(usage, "model_fields_set", None)
                if (fields_set is None or "prompt_tokens" in fields_set) and (value := usage.prompt_tokens) is not None:
                    usage_dict["input_token_count"] = value
                if (fields_set is None or "total_tokens" in fields_set) and (value := usage.total_tokens) is not None:
                    usage_dict["total_token_count"] = value

            return GeneratedEmbeddings(embeddings, options=options, usage=usage_dict or None)
        except IntegrationException:
            raise
        except Exception as ex:
            raise IntegrationInvalidResponseException(
                f"Mistral embeddings response was invalid: {ex}",
                inner_exception=ex,
            ) from ex


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
        http_client: Optional pre-configured ``httpx.AsyncClient``.
        client: Optional pre-configured ``mistralai.client.Mistral``. Passing an HTTP client via
            this parameter remains supported but is deprecated; use ``http_client`` instead.
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
            await client.close()
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "mistralai"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | None = None,
        server_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
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
            http_client=http_client,
            client=client,
            additional_properties=additional_properties,
            otel_provider_name=otel_provider_name,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
