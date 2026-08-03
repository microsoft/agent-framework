# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
import warnings
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Generic, TypedDict, cast

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

from ._feature_usage import FeatureIndex

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover


logger = logging.getLogger("agent_framework.mistral")

_MISTRAL_API_BASE_URL = "https://api.mistral.ai"
_EMBEDDINGS_PATH = "/v1/embeddings"
_DEFAULT_TIMEOUT_SECONDS = 60.0


def _resolve_injected_clients(
    http_client: httpx.AsyncClient | None,
    client: Any | None,
) -> tuple[httpx.AsyncClient | None, Any | None]:
    """Split the deprecated ``client`` parameter into REST and legacy-SDK forms.

    Returns ``(http_client, sdk_client)``; at most one is set. The SDK form is
    duck-typed on ``.embeddings`` so the ``mistralai`` dependency stays optional.
    """
    if client is None:
        return http_client, None
    warnings.warn(
        "The 'client' parameter is deprecated; pass an httpx.AsyncClient as 'http_client' instead. "
        "Support for injected mistralai.Mistral clients will be removed in the next major release.",
        DeprecationWarning,
        stacklevel=3,
    )
    if http_client is not None:
        raise ValueError("Provide either 'http_client' or the deprecated 'client' parameter, not both.")
    if isinstance(client, httpx.AsyncClient):
        return client, None
    if hasattr(client, "embeddings"):
        return None, client
    raise TypeError(
        "The 'client' parameter accepts an httpx.AsyncClient or a mistralai.Mistral instance; "
        f"got {type(client).__name__}."
    )


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

    Talks to the Mistral REST API directly over HTTP; the ``mistralai`` SDK is not required.

    Keyword Args:
        model: The Mistral embedding model (e.g. "mistral-embed").
            Can also be set via environment variable ``MISTRAL_EMBEDDING_MODEL``.
        api_key: Mistral API key. Defaults to ``MISTRAL_API_KEY`` environment variable.
        server_url: Optional server URL override. Defaults to ``MISTRAL_SERVER_URL``
            environment variable, or the Mistral default.
        http_client: Optional pre-configured ``httpx.AsyncClient``. When provided, api_key is
            not required and the client is expected to carry its own auth headers and base URL.
        client: Deprecated. Accepts an ``httpx.AsyncClient`` (treated as ``http_client``) or a
            ``mistralai.Mistral`` instance, which keeps working through the legacy SDK path
            until the next major release.
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
        client: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw Mistral AI embedding client."""
        http_client, sdk_client = _resolve_injected_clients(http_client, client)
        injected = http_client is not None or sdk_client is not None
        required_fields = ["embedding_model"] if injected else ["embedding_model", "api_key"]
        mistral_settings = load_settings(
            MistralEmbeddingSettings,
            env_prefix="MISTRAL_",
            required_fields=required_fields,
            api_key=str(api_key) if isinstance(api_key, SecretString) else api_key,
            embedding_model=model,
            server_url=server_url,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self.model: str = mistral_settings["embedding_model"]  # type: ignore[assignment]
        self.server_url = mistral_settings.get("server_url")
        self._owns_client = not injected
        self._sdk_client = sdk_client
        self.client: Any

        if sdk_client is not None:
            self.client = sdk_client
        elif http_client is not None:
            self.client = http_client
            if self.server_url is None:
                client_base_url = str(http_client.base_url).rstrip("/")
                self.server_url = client_base_url or None
        else:
            resolved_api_key: str = mistral_settings["api_key"]  # type: ignore[assignment]
            self.client = httpx.AsyncClient(
                base_url=self.server_url or _MISTRAL_API_BASE_URL,
                headers={
                    "Authorization": f"Bearer {resolved_api_key}",
                    "User-Agent": get_user_agent(),
                    "Accept": "application/json",
                },
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )

        super().__init__(additional_properties=additional_properties)

    async def close(self) -> None:
        """Close the internally created HTTP client."""
        if self._owns_client:
            await self.client.aclose()

    def service_url(self) -> str:
        """Get the URL of the service."""
        return self.server_url or _MISTRAL_API_BASE_URL

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
        if self._sdk_client is not None:
            return await self._get_embeddings_sdk(self._sdk_client, model, values, opts, options)

        request: dict[str, Any] = {"model": model, "input": list(values)}
        if "dimensions" in opts:
            request["output_dimension"] = opts["dimensions"]

        try:
            response = await self.client.post(_EMBEDDINGS_PATH, json=request)
            if response.status_code >= 400:
                message = (
                    f"Mistral embeddings request failed with status {response.status_code}: {response.text[:2000]}"
                )
                if response.status_code in (401, 403):
                    raise IntegrationInvalidAuthException(message)
                if response.status_code < 500:
                    raise IntegrationInvalidRequestException(message)
                raise IntegrationException(message)
        except IntegrationException:
            raise
        except Exception as ex:
            raise IntegrationException(f"Mistral embeddings request failed: {ex}", inner_exception=ex) from ex

        try:
            raw_payload = response.json()
            if not isinstance(raw_payload, Mapping):
                raise IntegrationInvalidResponseException("Mistral embeddings response must be a JSON object.")
            payload = cast("Mapping[str, Any]", raw_payload)
            embeddings: list[Embedding[list[float]]] = []
            data = cast("Sequence[Mapping[str, Any]]", payload.get("data") or ())
            items = sorted(data, key=lambda item: item.get("index") or 0)
            for item in items:
                vector = [float(v) for v in cast("Sequence[float]", item.get("embedding") or ())]
                embeddings.append(
                    Embedding(
                        vector=vector,
                        dimensions=len(vector),
                        model=payload.get("model") or model,
                    )
                )

            usage_dict: UsageDetails | None = None
            if usage := payload.get("usage"):
                usage_dict = {}
                if (value := usage.get("prompt_tokens")) is not None:
                    usage_dict["input_token_count"] = value
                if (value := usage.get("total_tokens")) is not None:
                    usage_dict["total_token_count"] = value

            return GeneratedEmbeddings(embeddings, options=options, usage=usage_dict or None)
        except IntegrationException:
            raise
        except Exception as ex:
            raise IntegrationInvalidResponseException(
                f"Mistral embeddings response was invalid: {ex}",
                inner_exception=ex,
            ) from ex

    async def _get_embeddings_sdk(
        self,
        sdk_client: Any,
        model: str,
        values: Sequence[str],
        opts: Mapping[str, Any],
        options: MistralEmbeddingOptionsT | None,
    ) -> GeneratedEmbeddings[list[float], MistralEmbeddingOptionsT]:
        """Legacy path for injected mistralai.Mistral clients; removed in the next major release."""
        kwargs: dict[str, Any] = {"model": model, "inputs": list(values)}
        if "dimensions" in opts:
            kwargs["output_dimension"] = opts["dimensions"]

        response = await sdk_client.embeddings.create_async(**kwargs)

        embeddings: list[Embedding[list[float]]] = []
        if response and response.data:
            items = sorted(response.data, key=lambda d: d.index if d.index is not None else 0)
            for item in items:
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
        http_client: Optional pre-configured ``httpx.AsyncClient``.
        client: Deprecated. Accepts an ``httpx.AsyncClient`` or a ``mistralai.Mistral`` instance.
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
        client: Any | None = None,
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
