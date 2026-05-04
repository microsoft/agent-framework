# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import copy
from typing import TYPE_CHECKING, Any, Literal, Union

from agent_framework._settings import SecretString, load_settings
from agent_framework._telemetry import APP_INFO, prepend_agent_framework_to_user_agent
from agent_framework.exceptions import SettingNotFoundError
from openai import AsyncAzureOpenAI, AsyncOpenAI, AsyncStream, _legacy_response  # type: ignore
from openai.types import Completion
from openai.types.audio import Transcription
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.images_response import ImagesResponse
from openai.types.responses.response import Response
from openai.types.responses.response_stream_event import ResponseStreamEvent

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from azure.core.credentials import TokenCredential
    from azure.core.credentials_async import AsyncTokenCredential

    AzureCredentialTypes = TokenCredential | AsyncTokenCredential


AZURE_OPENAI_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"  # noqa: S105 # nosec B105


RESPONSE_TYPE = Union[
    ChatCompletion,
    Completion,
    AsyncStream[ChatCompletionChunk],
    AsyncStream[Completion],
    list[Any],
    ImagesResponse,
    Response,
    AsyncStream[ResponseStreamEvent],
    Transcription,
    _legacy_response.HttpxBinaryResponseContent,
]

AzureTokenProvider = Callable[[], str | Awaitable[str]]


class OpenAISettings(TypedDict, total=False):
    """OpenAI environment settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'OPENAI_'. If settings are missing after resolution, validation will fail.

    Keyword Args:
        api_key: OpenAI API key, see https://platform.openai.com/account/api-keys.
            Can be set via environment variable OPENAI_API_KEY.
        base_url: The base URL for the OpenAI API.
            Can be set via environment variable OPENAI_BASE_URL.
        org_id: This is usually optional unless your account belongs to multiple organizations.
            Can be set via environment variable OPENAI_ORG_ID.
        model: The OpenAI model to use, for example, gpt-4o or o1.
            Can be set via environment variable OPENAI_MODEL.
        embedding_model: The OpenAI embedding model to use, for example, text-embedding-3-small.
            Can be set via environment variable OPENAI_EMBEDDING_MODEL.
        chat_model: The OpenAIChatClient model to prefer before OPENAI_MODEL.
            Can be set via environment variable OPENAI_CHAT_MODEL.
        chat_completion_model: The OpenAIChatCompletionClient model to prefer before OPENAI_MODEL.
            Can be set via environment variable OPENAI_CHAT_COMPLETION_MODEL.

    Examples:
        .. code-block:: python

            from agent_framework.openai import OpenAISettings

            # Using environment variables
            # Set OPENAI_API_KEY=sk-...
            # Set OPENAI_MODEL=gpt-4o
            settings = load_settings(OpenAISettings, env_prefix="OPENAI_")

            # Or passing parameters directly
            settings = load_settings(OpenAISettings, env_prefix="OPENAI_", api_key="sk-...", model="gpt-4o")

            # Or loading from a .env file
            settings = load_settings(OpenAISettings, env_prefix="OPENAI_", env_file_path="path/to/.env")
    """

    api_key: SecretString | None
    base_url: str | None
    org_id: str | None
    model: str | None
    embedding_model: str | None
    chat_model: str | None
    chat_completion_model: str | None


class AzureOpenAISettings(TypedDict, total=False):
    """Azure OpenAI environment settings."""

    endpoint: str | None
    base_url: str | None
    api_key: SecretString | None
    model: str | None
    embedding_model: str | None
    chat_model: str | None
    chat_completion_model: str | None
    api_version: str | None


OpenAIModelSettingName = Literal["model", "embedding_model", "chat_model", "chat_completion_model"]

OPENAI_MODEL_ENV_VARS: dict[OpenAIModelSettingName, str] = {
    "model": "OPENAI_MODEL",
    "embedding_model": "OPENAI_EMBEDDING_MODEL",
    "chat_model": "OPENAI_CHAT_MODEL",
    "chat_completion_model": "OPENAI_CHAT_COMPLETION_MODEL",
}

AZURE_MODEL_ENV_VARS: dict[OpenAIModelSettingName, str] = {
    "model": "AZURE_OPENAI_MODEL",
    "embedding_model": "AZURE_OPENAI_EMBEDDING_MODEL",
    "chat_model": "AZURE_OPENAI_CHAT_MODEL",
    "chat_completion_model": "AZURE_OPENAI_CHAT_COMPLETION_MODEL",
}


def _resolve_named_setting(
    settings: Mapping[str, Any],
    fields: Sequence[OpenAIModelSettingName],
) -> str | None:
    """Return the first populated value from ``fields``."""
    for field in fields:
        value = settings.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _join_env_names(env_names: Sequence[str]) -> str:
    """Format env var names for user-facing error messages."""
    return ", ".join(f"'{env_name}'" for env_name in env_names)


def load_openai_service_settings(
    *,
    model: str | None,
    api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None,
    credential: AzureCredentialTypes | AzureTokenProvider | None,
    org_id: str | None,
    base_url: str | None,
    endpoint: str | None,
    api_version: str | None,
    default_azure_api_version: str,
    default_headers: Mapping[str, str] | None = None,
    client: AsyncOpenAI | None = None,
    env_file_path: str | None,
    env_file_encoding: str | None,
    openai_model_fields: Sequence[OpenAIModelSettingName] = ("model",),
    azure_model_fields: Sequence[OpenAIModelSettingName] = ("model",),
    responses_mode: bool = False,
) -> tuple[dict[str, Any], AsyncOpenAI, bool]:
    """Load OpenAI settings, including Azure OpenAI model aliases.

    The generic OpenAI clients primarily read from ``OPENAI_*`` variables. Azure-specific
    environment variables are used only when an explicit Azure signal is present
    (``endpoint`` or ``credential``) or when no explicit
    OpenAI API key is available.
    """
    # Merge APP_INFO into the headers
    merged_headers = dict(copy(default_headers)) if default_headers else {}
    if APP_INFO:
        merged_headers.update(APP_INFO)
        merged_headers = prepend_agent_framework_to_user_agent(merged_headers)

    api_key_callable = api_key if callable(api_key) else None
    api_key_str = api_key if not callable(api_key) else None
    azure_client = isinstance(client, AsyncAzureOpenAI)
    use_azure = azure_client or endpoint is not None or credential is not None
    checked_openai = False
    if not use_azure:
        openai_settings_kwargs: dict[str, Any] = {
            "api_key": api_key_str,
            "org_id": org_id,
            "base_url": base_url,
            "env_file_path": env_file_path,
            "env_file_encoding": env_file_encoding,
        }
        if model is not None:
            openai_settings_kwargs[openai_model_fields[0]] = model
        openai_settings = load_settings(
            OpenAISettings,
            env_prefix="OPENAI_",
            **openai_settings_kwargs,
        )
        if resolved_model := _resolve_named_setting(openai_settings, openai_model_fields):
            openai_settings["model"] = resolved_model
        if client:
            return openai_settings, client, False  # type: ignore[return-value]
        if openai_settings.get("api_key") is not None or api_key_callable is not None:
            resolved_model = _resolve_named_setting(openai_settings, openai_model_fields)
            if not resolved_model:
                raise SettingNotFoundError(
                    "Model must be specified via the 'model' parameter or the "
                    f"{_join_env_names([OPENAI_MODEL_ENV_VARS[field] for field in openai_model_fields])} "
                    "environment variable."
                )

            client_args: dict[str, Any] = {
                "api_key": api_key_callable
                if api_key_callable is not None
                else openai_settings["api_key"].get_secret_value(),  # type: ignore[reportOptionalMemberAccess, union-attr]
                "organization": openai_settings.get("org_id"),
                "default_headers": merged_headers,
            }
            if base_url := openai_settings.get("base_url"):
                client_args["base_url"] = base_url
            return openai_settings, AsyncOpenAI(**client_args), False  # type: ignore[return-value]
        checked_openai = True
    azure_settings = load_settings(
        AzureOpenAISettings,
        env_prefix="AZURE_OPENAI_",
        required_fields=None if client else [("base_url", "endpoint")],
        api_key=api_key_str,
        endpoint=endpoint,
        base_url=base_url,
        api_version=api_version or default_azure_api_version,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    if model is not None:
        azure_settings[azure_model_fields[0]] = model
    client_args = {}
    resolved_azure_model = _resolve_named_setting(azure_settings, azure_model_fields)
    if resolved_azure_model is None and client:
        azure_deployment = getattr(client, "_azure_deployment", None)
        if isinstance(azure_deployment, str) and azure_deployment:
            resolved_azure_model = azure_deployment
    if resolved_azure_model:
        azure_settings["model"] = resolved_azure_model
        client_args["azure_deployment"] = resolved_azure_model
    else:
        deployment_env_guidance = _join_env_names([AZURE_MODEL_ENV_VARS[field] for field in azure_model_fields])
        has_azure_configuration = (
            client is not None
            or azure_settings.get("endpoint") is not None
            or azure_settings.get("base_url") is not None
        )
        if checked_openai and not has_azure_configuration:
            raise SettingNotFoundError(
                "OpenAI credentials are required. Provide the 'api_key' parameter or set 'OPENAI_API_KEY'. "
                "To use Azure OpenAI instead, pass 'azure_endpoint' or set 'AZURE_OPENAI_ENDPOINT' or "
                "'AZURE_OPENAI_BASE_URL'."
            )
        raise SettingNotFoundError(
            "Azure OpenAI client requires a model, which can be provided via the 'model' parameter, "
            f"or the {deployment_env_guidance} environment variable."
        )
    if client:
        return azure_settings, client, True  # type: ignore[return-value]
    client_args["default_headers"] = merged_headers
    if endpoint := azure_settings.get("endpoint"):
        if responses_mode:
            client_args["base_url"] = f"{endpoint.rstrip('/')}/openai/v1/"
        else:
            client_args["azure_endpoint"] = endpoint
    if base_url := azure_settings.get("base_url"):
        client_args["base_url"] = base_url
    if api_key := azure_settings.get("api_key"):
        client_args["api_key"] = api_key.get_secret_value()
    if api_key_callable:
        client_args["api_key"] = api_key_callable
    if api_version := azure_settings.get("api_version"):
        client_args["api_version"] = api_version
    if credential:
        client_args["azure_ad_token_provider"] = _resolve_azure_credential_to_token_provider(credential)
    if "api_key" not in client_args and "azure_ad_token_provider" not in client_args:
        raise SettingNotFoundError(
            "Azure OpenAI client requires either an API key or an Azure AD token provider."
            " This can be provided either as a callable api_key or via the credential parameter."
        )

    # The /openai/v1 endpoint exposes an OpenAI-compatible API surface.
    # AsyncAzureOpenAI rewrites certain request paths (e.g. /embeddings,
    # /chat/completions) by inserting /deployments/{model}/, which produces
    # 404s on this endpoint.  Use AsyncOpenAI instead so request URLs are
    # sent as-is.  responses_mode is excluded because the Responses API path
    # (/responses) is not rewritten by the Azure SDK.
    resolved_base_url = client_args.get("base_url", "")
    if not responses_mode and resolved_base_url and resolved_base_url.rstrip("/").endswith("/openai/v1"):
        openai_args: dict[str, Any] = {
            "base_url": resolved_base_url,
            "default_headers": client_args.get("default_headers"),
        }
        if "azure_ad_token_provider" in client_args:
            openai_args["api_key"] = _ensure_async_token_provider(client_args["azure_ad_token_provider"])
        elif "api_key" in client_args:
            openai_args["api_key"] = client_args["api_key"]
        return azure_settings, AsyncOpenAI(**openai_args), True  # type: ignore[return-value]

    return azure_settings, AsyncAzureOpenAI(**client_args), True  # type: ignore[return-value]


def _ensure_async_token_provider(
    provider: AzureTokenProvider,
) -> Callable[[], Awaitable[str]]:
    """Wrap a (possibly synchronous) token provider so it always returns an awaitable.

    ``AsyncOpenAI`` requires callable ``api_key`` values to return ``Awaitable[str]``.
    Azure token providers may return a plain ``str``, so this normalises them.
    """

    async def _wrapper() -> str:
        result = provider()
        if isinstance(result, str):
            return result
        return await result

    return _wrapper


def _resolve_azure_credential_to_token_provider(
    credential: AzureCredentialTypes | AzureTokenProvider,
) -> AzureTokenProvider:
    """Resolve an Azure credential or token provider for Azure OpenAI auth."""
    if callable(credential):
        return credential

    try:
        from azure.core.credentials import TokenCredential
        from azure.core.credentials_async import AsyncTokenCredential
        from azure.identity import get_bearer_token_provider
        from azure.identity.aio import get_bearer_token_provider as get_async_bearer_token_provider
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Azure credential auth requires the 'azure-identity' package. Install it with: pip install azure-identity"
        ) from exc

    if isinstance(credential, AsyncTokenCredential):
        return get_async_bearer_token_provider(credential, AZURE_OPENAI_TOKEN_SCOPE)
    if isinstance(credential, TokenCredential):
        return get_bearer_token_provider(credential, AZURE_OPENAI_TOKEN_SCOPE)  # type: ignore[arg-type]
    raise ValueError(
        "The 'credential' parameter must be an Azure TokenCredential, AsyncTokenCredential, or a "
        "callable token provider."
    )


def maybe_append_azure_endpoint_guidance(message: str, *, azure_endpoint: str | None) -> str:
    """Append Azure endpoint guidance only when the configured endpoint shape looks suspicious."""
    if not azure_endpoint or not azure_endpoint.rstrip("/").endswith("/openai/v1"):
        return message

    return (
        f"{message} If you are using Azure OpenAI key auth, pass the resource endpoint without "
        "'/openai/v1' to 'azure_endpoint', or pass the full '/openai/v1' URL via 'base_url' instead."
    )


def get_api_key(
    api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None,
) -> str | Callable[[], str | Awaitable[str]] | None:
    """Get the appropriate API key value for client initialization.

    Args:
        api_key: The API key parameter which can be a string, SecretString, callable, or None.

    Returns:
        For callable API keys: returns the callable directly.
        For SecretString: returns the unwrapped secret value.
        For string/None API keys: returns as-is.
    """
    if isinstance(api_key, SecretString):
        return api_key.get_secret_value()

    return api_key  # Pass callable, string, or None directly to OpenAI SDK
