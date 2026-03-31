# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from copy import copy
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Union, cast

import openai
from agent_framework._serialization import SerializationMixin
from agent_framework._settings import SecretString, load_settings
from agent_framework._telemetry import APP_INFO, USER_AGENT_KEY, prepend_agent_framework_to_user_agent
from agent_framework._tools import FunctionTool
from agent_framework.exceptions import SettingNotFoundError
from openai import AsyncAzureOpenAI, AsyncOpenAI, AsyncStream, _legacy_response  # type: ignore
from openai.types import Completion
from openai.types.audio import Transcription
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.images_response import ImagesResponse
from openai.types.responses.response import Response
from openai.types.responses.response_stream_event import ResponseStreamEvent
from packaging.version import parse

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from azure.core.credentials import TokenCredential
    from azure.core.credentials_async import AsyncTokenCredential

    AzureCredentialTypes = TokenCredential | AsyncTokenCredential


logger: logging.Logger = logging.getLogger("agent_framework.openai")

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


def _check_openai_version_for_callable_api_key() -> None:
    """Check if OpenAI version supports callable API keys.

    Callable API keys require OpenAI >= 1.106.0.
    If the version is too old, raise a ValueError with helpful message.
    """
    try:
        current_version = parse(openai.__version__)
        min_required_version = parse("1.106.0")

        if current_version < min_required_version:
            raise ValueError(
                f"Callable API keys require OpenAI SDK >= 1.106.0, but you have {openai.__version__}. "
                f"Please upgrade with 'pip install openai>=1.106.0' or provide a string API key instead. "
                f"Note: If you're using mem0ai, you may need to upgrade to mem0ai>=1.0.0 "
                f"to allow newer OpenAI versions."
            )
    except ValueError:
        raise  # Re-raise our own exception
    except Exception as e:
        logger.warning(f"Could not check OpenAI version for callable API key support: {e}")


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
        chat_model: The OpenAI chat-completions model to prefer before OPENAI_MODEL.
            Can be set via environment variable OPENAI_CHAT_MODEL.
        responses_model: The OpenAI responses model to prefer before OPENAI_MODEL.
            Can be set via environment variable OPENAI_RESPONSES_MODEL.

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
    responses_model: str | None


class AzureOpenAISettings(TypedDict, total=False):
    """Azure OpenAI environment settings."""

    endpoint: str | None
    base_url: str | None
    api_key: SecretString | None
    deployment_name: str | None
    embedding_deployment_name: str | None
    chat_deployment_name: str | None
    responses_deployment_name: str | None
    api_version: str | None


OpenAIModelSettingName = Literal["model", "embedding_model", "chat_model", "responses_model"]
AzureDeploymentSettingName = Literal[
    "deployment_name", "embedding_deployment_name", "chat_deployment_name", "responses_deployment_name"
]

OPENAI_MODEL_ENV_VARS: dict[OpenAIModelSettingName, str] = {
    "model": "OPENAI_MODEL",
    "embedding_model": "OPENAI_EMBEDDING_MODEL",
    "chat_model": "OPENAI_CHAT_MODEL",
    "responses_model": "OPENAI_RESPONSES_MODEL",
}

AZURE_DEPLOYMENT_ENV_VARS: dict[AzureDeploymentSettingName, str] = {
    "deployment_name": "AZURE_OPENAI_DEPLOYMENT_NAME",
    "embedding_deployment_name": "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME",
    "chat_deployment_name": "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME",
    "responses_deployment_name": "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME",
}


def _resolve_named_setting(
    settings: Mapping[str, Any],
    fields: Sequence[OpenAIModelSettingName | AzureDeploymentSettingName],
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
    azure_deployment_fields: Sequence[AzureDeploymentSettingName] = ("deployment_name",),
    responses_mode: bool = False,
) -> tuple[dict[str, Any], AsyncOpenAI, bool]:
    """Load OpenAI settings, including Azure OpenAI aliases.

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
        azure_settings[azure_deployment_fields[0]] = model
    client_args = {}
    resolved_azure_deployment = _resolve_named_setting(azure_settings, azure_deployment_fields)
    if resolved_azure_deployment is None and client:
        azure_deployment = getattr(client, "_azure_deployment", None)
        if isinstance(azure_deployment, str) and azure_deployment:
            resolved_azure_deployment = azure_deployment
    if resolved_azure_deployment:
        azure_settings["deployment_name"] = resolved_azure_deployment
        client_args["azure_deployment"] = resolved_azure_deployment
    else:
        deployment_env_guidance = _join_env_names([
            AZURE_DEPLOYMENT_ENV_VARS[field] for field in azure_deployment_fields
        ])
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
            "Azure OpenAI client requires a deployment name, which can be provided via the 'model' parameter, "
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
    return azure_settings, AsyncAzureOpenAI(**client_args), True  # type: ignore[return-value]


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

    # Check version compatibility for callable API keys
    if callable(api_key):
        _check_openai_version_for_callable_api_key()

    return api_key  # Pass callable, string, or None directly to OpenAI SDK


class OpenAIBase(SerializationMixin):
    """Base class for OpenAI Clients.

    .. deprecated::
        ``OpenAIBase`` is deprecated and only used by ``OpenAIAssistantsClient``
        and ``AzureOpenAIAssistantsClient``.  New clients should manage ``client``
        and ``model`` directly in their own ``__init__``.
    """

    INJECTABLE: ClassVar[set[str]] = {"client"}

    def __init__(
        self, *, model: str | None = None, model_id: str | None = None, client: AsyncOpenAI | None = None, **kwargs: Any
    ) -> None:
        """Initialize OpenAIBase.

        Keyword Args:
            client: The AsyncOpenAI client instance.
            model: The AI model to use.
            model_id: Deprecated alias for ``model``.
            **kwargs: Additional keyword arguments.
        """
        if model_id is not None and model is None:
            import warnings

            warnings.warn("model_id is deprecated, use model instead", DeprecationWarning, stacklevel=2)
            model = model_id
        self.client = client
        self.model: str | None = None
        if model:
            self.model = model.strip()

        # Call super().__init__() to continue MRO chain (e.g., RawChatClient)
        # Extract known kwargs that belong to other base classes
        additional_properties = kwargs.pop("additional_properties", None)
        middleware = kwargs.pop("middleware", None)
        instruction_role = kwargs.pop("instruction_role", None)
        function_invocation_configuration = kwargs.pop("function_invocation_configuration", None)

        # Build super().__init__() args
        super_kwargs = {}
        if additional_properties is not None:
            super_kwargs["additional_properties"] = additional_properties
        if middleware is not None:
            super_kwargs["middleware"] = middleware
        if function_invocation_configuration is not None:
            super_kwargs["function_invocation_configuration"] = function_invocation_configuration

        # Call super().__init__() with filtered kwargs
        super().__init__(**super_kwargs)

        # Store instruction_role and any remaining kwargs as instance attributes
        if instruction_role is not None:
            self.instruction_role = instruction_role
        for key, value in kwargs.items():
            setattr(self, key, value)

    async def _initialize_client(self) -> None:
        """Initialize OpenAI client asynchronously.

        Override in subclasses to initialize the OpenAI client asynchronously.
        """
        pass

    async def _ensure_client(self) -> AsyncOpenAI:
        """Ensure OpenAI client is initialized."""
        await self._initialize_client()
        if self.client is None:
            raise RuntimeError("OpenAI client is not initialized")

        return self.client

    def _get_api_key(
        self, api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None
    ) -> str | Callable[[], str | Awaitable[str]] | None:
        """Get the appropriate API key value for client initialization.

        Args:
            api_key: The API key parameter which can be a string, SecretString, callable, or None.

        Returns:
            For callable API keys: returns the callable directly.
            For SecretString/string/None API keys: returns as-is (SecretString is a str subclass).
        """
        if isinstance(api_key, SecretString):
            return api_key.get_secret_value()

        # Check version compatibility for callable API keys
        if callable(api_key):
            _check_openai_version_for_callable_api_key()

        return api_key  # Pass callable, string, or None directly to OpenAI SDK


class OpenAIConfigMixin(OpenAIBase):
    """Internal class for configuring a connection to an OpenAI service.

    .. deprecated::
        ``OpenAIConfigMixin`` is deprecated and only used by ``OpenAIAssistantsClient``
        and ``AzureOpenAIAssistantsClient``.  New clients handle configuration
        directly in their own ``__init__``.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "openai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        model: str,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a client for OpenAI services.

        This constructor sets up a client to interact with OpenAI's API, allowing for
        different types of AI model interactions, like chat or text completion.

        Args:
            model: OpenAI model identifier. Must be non-empty.
                Default to a preset value.
            api_key: OpenAI API key for authentication, or a callable that returns an API key.
                Must be non-empty. (Optional)
            org_id: OpenAI organization ID. This is optional
                unless the account belongs to multiple organizations.
            default_headers: Default headers
                for HTTP requests. (Optional)
            client: An existing OpenAI client, optional.
            instruction_role: The role to use for 'instruction'
                messages, for example, summarization prompts could use `developer` or `system`. (Optional)
            base_url: The optional base URL to use. If provided will override the standard value for a OpenAI connector.
                Will not be used when supplying a custom client.
            kwargs: Additional keyword arguments.

        """
        # Merge APP_INFO into the headers if it exists
        merged_headers = dict(copy(default_headers)) if default_headers else {}
        if APP_INFO:
            merged_headers.update(APP_INFO)
            merged_headers = prepend_agent_framework_to_user_agent(merged_headers)

        # Handle callable API key using base class method
        api_key_value = self._get_api_key(api_key)

        if not client:
            if not api_key:
                raise ValueError("Please provide an api_key")
            args: dict[str, Any] = {"api_key": api_key_value, "default_headers": merged_headers}
            if org_id:
                args["organization"] = org_id
            if base_url:
                args["base_url"] = base_url
            client = AsyncOpenAI(**args)

        # Store configuration as instance attributes for serialization
        self.org_id = org_id
        self.base_url = str(base_url)
        # Store default_headers but filter out USER_AGENT_KEY for serialization
        if default_headers:
            self.default_headers: dict[str, Any] | None = {
                k: v for k, v in default_headers.items() if k != USER_AGENT_KEY
            }
        else:
            self.default_headers = None

        args = {
            "model": model,
            "client": client,
        }
        if instruction_role:
            args["instruction_role"] = instruction_role

        # Ensure additional_properties and middleware are passed through kwargs to RawChatClient
        # These are consumed by RawChatClient.__init__ via kwargs
        super().__init__(**args, **kwargs)


def to_assistant_tools(
    tools: Sequence[FunctionTool | MutableMapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Convert Agent Framework tools to OpenAI Assistants API format.

    Handles FunctionTool instances and dict-based tools from static factory methods.

    Args:
        tools: Sequence of Agent Framework tools.

    Returns:
        List of tool definitions for OpenAI Assistants API.
    """
    if not tools:
        return []

    tool_definitions: list[dict[str, Any]] = []

    for tool in tools:
        if isinstance(tool, FunctionTool):
            tool_definitions.append(tool.to_json_schema_spec())
        elif isinstance(tool, MutableMapping):
            # Pass through dict-based tools directly (from static factory methods)
            tool_definitions.append(dict(tool))

    return tool_definitions


def from_assistant_tools(
    assistant_tools: list[Any] | None,
) -> list[dict[str, Any]]:
    """Convert OpenAI Assistant tools to dict-based format.

    This converts hosted tools (code_interpreter, file_search) from an OpenAI
    Assistant definition back to dict-based tool definitions.

    Note: Function tools are skipped - user must provide implementations separately.

    Args:
        assistant_tools: Tools from OpenAI Assistant object (assistant.tools).

    Returns:
        List of dict-based tool definitions for hosted tools.
    """
    if not assistant_tools:
        return []

    tools: list[dict[str, Any]] = []

    for tool in assistant_tools:
        if hasattr(tool, "type"):
            tool_type = tool.type
        elif isinstance(tool, Mapping):
            typed_tool = cast(Mapping[str, Any], tool)
            tool_type_value: Any = typed_tool.get("type")
            tool_type = tool_type_value if isinstance(tool_type_value, str) else None
        else:
            tool_type = None

        if tool_type == "code_interpreter":
            tools.append({"type": "code_interpreter"})
        elif tool_type == "file_search":
            tools.append({"type": "file_search"})
        # Skip function tools - user must provide implementations

    return tools
