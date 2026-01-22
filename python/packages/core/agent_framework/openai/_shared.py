# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from copy import copy
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal, Union

import openai
from azure.core.credentials import TokenCredential
from openai import (
    AsyncOpenAI,
    AsyncStream,
    _legacy_response,  # type: ignore
)
from openai.types import Completion
from openai.types.audio import Transcription
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.images_response import ImagesResponse
from openai.types.responses.response import Response
from openai.types.responses.response_stream_event import ResponseStreamEvent
from packaging.version import parse
from pydantic import SecretStr

from .._logging import get_logger
from .._pydantic import HTTPsUrl
from .._serialization import SerializationMixin
from .._settings import AFSettings, BackendConfig
from .._telemetry import APP_INFO, USER_AGENT_KEY, prepend_agent_framework_to_user_agent
from .._tools import FunctionTool, HostedCodeInterpreterTool, HostedFileSearchTool, ToolProtocol
from ..exceptions import ServiceInitializationError

if TYPE_CHECKING:
    from openai.lib.azure import AsyncAzureADTokenProvider

logger: logging.Logger = get_logger("agent_framework.openai")

OpenAIBackend = Literal["openai", "azure"]

DEFAULT_AZURE_API_VERSION: Final[str] = "2024-10-21"
DEFAULT_AZURE_TOKEN_ENDPOINT: Final[str] = "https://cognitiveservices.azure.com/.default"  # noqa: S105


class OpenAISettings(AFSettings):
    """OpenAI settings with multi-backend support.

    This settings class supports two backends:
    - **openai**: Direct OpenAI API (default, highest precedence)
    - **azure**: Azure OpenAI Service

    The backend is determined by:
    1. Explicit `backend` parameter
    2. `OPENAI_CHAT_CLIENT_BACKEND` environment variable
    3. Auto-detection based on which backend's credentials are present (using precedence)

    Keyword Args:
        backend: Explicit backend selection. One of "openai" or "azure".

        # Common fields
        chat_model_id: Model/deployment name for chat completions.
            OpenAI: OPENAI_CHAT_MODEL_ID
            Azure: AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
        responses_model_id: Model/deployment name for Responses API.
            OpenAI: OPENAI_RESPONSES_MODEL_ID
            Azure: AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME

        # OpenAI backend
        api_key: OpenAI API key (env: OPENAI_API_KEY).
            Supports callable for dynamic key generation.
        base_url: Base URL for the API (env: OPENAI_BASE_URL).
        org_id: Organization ID (env: OPENAI_ORG_ID).

        # Azure backend
        azure_api_key: Azure OpenAI API key (env: AZURE_OPENAI_API_KEY).
        endpoint: Azure OpenAI endpoint URL (env: AZURE_OPENAI_ENDPOINT).
        azure_base_url: Azure OpenAI base URL (env: AZURE_OPENAI_BASE_URL).
        api_version: Azure API version (env: AZURE_OPENAI_API_VERSION).
        ad_token: Azure AD token for authentication.
        ad_token_provider: Callable that provides Azure AD tokens.
        token_endpoint: Token endpoint for Azure AD (env: AZURE_OPENAI_TOKEN_ENDPOINT).
        credential: Azure TokenCredential for authentication.

        env_file_path: Path to .env file for loading settings.
        env_file_encoding: Encoding of the .env file.

    Examples:
        Using OpenAI API directly:

        .. code-block:: python

            # Via environment variable OPENAI_API_KEY
            settings = OpenAISettings()

            # Or explicitly
            settings = OpenAISettings(api_key="sk-...")

        Using Azure OpenAI:

        .. code-block:: python

            settings = OpenAISettings(
                backend="azure",
                endpoint="https://my-resource.openai.azure.com",
                chat_model_id="gpt-4o",  # deployment name
                azure_api_key="...",
            )

        Using Azure OpenAI with Entra ID:

        .. code-block:: python

            from azure.identity import DefaultAzureCredential

            settings = OpenAISettings(
                backend="azure",
                endpoint="https://my-resource.openai.azure.com",
                chat_model_id="gpt-4o",
                credential=DefaultAzureCredential(),
            )
    """

    env_prefix: ClassVar[str] = "OPENAI_"
    backend_env_var: ClassVar[str | None] = "OPENAI_CHAT_CLIENT_BACKEND"

    # Common field mappings (used regardless of backend for fallback)
    field_env_vars: ClassVar[dict[str, str]] = {
        "chat_model_id": "CHAT_MODEL_ID",  # OPENAI_CHAT_MODEL_ID (fallback)
        "responses_model_id": "RESPONSES_MODEL_ID",  # OPENAI_RESPONSES_MODEL_ID (fallback)
    }

    # Backend-specific configurations
    backend_configs: ClassVar[dict[str, BackendConfig]] = {
        "openai": BackendConfig(
            env_prefix="OPENAI_",
            precedence=1,
            detection_fields={"api_key"},
            field_env_vars={
                "api_key": "API_KEY",
                "base_url": "BASE_URL",
                "org_id": "ORG_ID",
                "chat_model_id": "CHAT_MODEL_ID",
                "responses_model_id": "RESPONSES_MODEL_ID",
            },
        ),
        "azure": BackendConfig(
            env_prefix="AZURE_OPENAI_",
            precedence=2,
            detection_fields={"endpoint", "azure_api_key"},
            field_env_vars={
                "azure_api_key": "API_KEY",
                "endpoint": "ENDPOINT",
                "azure_base_url": "BASE_URL",
                "api_version": "API_VERSION",
                "token_endpoint": "TOKEN_ENDPOINT",
                "chat_model_id": "CHAT_DEPLOYMENT_NAME",
                "responses_model_id": "RESPONSES_DEPLOYMENT_NAME",
            },
        ),
    }

    # Common fields
    chat_model_id: str | None = None
    responses_model_id: str | None = None

    # OpenAI backend fields
    api_key: SecretStr | None = None
    base_url: str | None = None
    org_id: str | None = None

    # Azure backend fields
    azure_api_key: SecretStr | None = None
    endpoint: HTTPsUrl | None = None
    azure_base_url: HTTPsUrl | None = None
    api_version: str | None = None
    token_endpoint: str | None = None

    def __init__(
        self,
        *,
        backend: OpenAIBackend | None = None,
        # Common fields
        chat_model_id: str | None = None,
        responses_model_id: str | None = None,
        # OpenAI backend
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        base_url: str | None = None,
        org_id: str | None = None,
        # Azure backend
        azure_api_key: str | None = None,
        endpoint: str | None = None,
        azure_base_url: str | None = None,
        api_version: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: "AsyncAzureADTokenProvider | None" = None,
        token_endpoint: str | None = None,
        credential: TokenCredential | None = None,
        default_headers: Mapping[str, str] | None = None,
        # Common
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize OpenAI settings."""
        # Store non-serializable objects before calling super().__init__
        self._callable_api_key: Callable[[], str | Awaitable[str]] | None = None
        if callable(api_key):
            self._callable_api_key = api_key
            api_key = None  # Don't pass callable to parent

        self._ad_token = ad_token
        self._ad_token_provider = ad_token_provider
        self._credential = credential
        self._default_headers = dict(default_headers) if default_headers else None

        super().__init__(
            backend=backend,
            chat_model_id=chat_model_id,
            responses_model_id=responses_model_id,
            api_key=api_key,
            base_url=base_url,
            org_id=org_id,
            azure_api_key=azure_api_key,
            endpoint=endpoint,
            azure_base_url=azure_base_url,
            api_version=api_version,
            token_endpoint=token_endpoint,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        # Apply Azure defaults
        if self._backend == "azure":
            if self.api_version is None:
                self.api_version = DEFAULT_AZURE_API_VERSION
            if self.token_endpoint is None:
                self.token_endpoint = DEFAULT_AZURE_TOKEN_ENDPOINT

    @property
    def callable_api_key(self) -> Callable[[], str | Awaitable[str]] | None:
        """Get the callable API key if one was provided."""
        return self._callable_api_key

    @property
    def ad_token(self) -> str | None:
        """Get the Azure AD token."""
        return self._ad_token

    @property
    def ad_token_provider(self) -> "AsyncAzureADTokenProvider | None":
        """Get the Azure AD token provider."""
        return self._ad_token_provider

    @property
    def credential(self) -> TokenCredential | None:
        """Get the Azure TokenCredential."""
        return self._credential

    @property
    def default_headers(self) -> dict[str, str] | None:
        """Get the default headers."""
        return self._default_headers

    def get_api_key_value(self) -> str | Callable[[], str | Awaitable[str]] | None:
        """Get the API key value for client initialization.

        For callable API keys: returns the callable directly.
        For SecretStr API keys: returns the string value.
        For string/None API keys: returns as-is.
        """
        if self._callable_api_key is not None:
            return self._callable_api_key

        if self._backend == "azure":
            if isinstance(self.azure_api_key, SecretStr):
                return self.azure_api_key.get_secret_value()
            return self.azure_api_key
        if isinstance(self.api_key, SecretStr):
            return self.api_key.get_secret_value()
        return self.api_key

    def get_azure_auth_token(self, **kwargs: Any) -> str | None:
        """Retrieve a Microsoft Entra Auth Token for Azure OpenAI.

        The required role for the token is `Cognitive Services OpenAI Contributor`.

        Returns:
            The Azure token or None if the token could not be retrieved.
        """
        from agent_framework.azure._entra_id_authentication import get_entra_auth_token

        if self._credential is None:
            return None

        endpoint_to_use = self.token_endpoint or DEFAULT_AZURE_TOKEN_ENDPOINT
        return get_entra_auth_token(self._credential, endpoint_to_use, **kwargs)


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

OPTION_TYPE = dict[str, Any]


__all__ = ["OpenAIBackend", "OpenAISettings"]


def _check_openai_version_for_callable_api_key() -> None:
    """Check if OpenAI version supports callable API keys.

    Callable API keys require OpenAI >= 1.106.0.
    If the version is too old, raise a ServiceInitializationError with helpful message.
    """
    try:
        current_version = parse(openai.__version__)
        min_required_version = parse("1.106.0")

        if current_version < min_required_version:
            raise ServiceInitializationError(
                f"Callable API keys require OpenAI SDK >= 1.106.0, but you have {openai.__version__}. "
                f"Please upgrade with 'pip install openai>=1.106.0' or provide a string API key instead. "
                f"Note: If you're using mem0ai, you may need to upgrade to mem0ai>=1.0.0 "
                f"to allow newer OpenAI versions."
            )
    except ServiceInitializationError:
        raise  # Re-raise our own exception
    except Exception as e:
        logger.warning(f"Could not check OpenAI version for callable API key support: {e}")


class OpenAIBase(SerializationMixin):
    """Base class for OpenAI Clients."""

    INJECTABLE: ClassVar[set[str]] = {"client"}

    def __init__(self, *, model_id: str | None = None, client: AsyncOpenAI | None = None, **kwargs: Any) -> None:
        """Initialize OpenAIBase.

        Keyword Args:
            client: The AsyncOpenAI client instance.
            model_id: The AI model ID to use.
            **kwargs: Additional keyword arguments.
        """
        self.client = client
        self.model_id = None
        if model_id:
            if not isinstance(model_id, str):
                raise ServiceInitializationError(f"model_id must be a string, got {type(model_id).__name__}")
            self.model_id = model_id.strip()

        # Call super().__init__() to continue MRO chain (e.g., BaseChatClient)
        # Extract known kwargs that belong to other base classes
        additional_properties = kwargs.pop("additional_properties", None)
        middleware = kwargs.pop("middleware", None)
        instruction_role = kwargs.pop("instruction_role", None)

        # Build super().__init__() args
        super_kwargs = {}
        if additional_properties is not None:
            super_kwargs["additional_properties"] = additional_properties
        if middleware is not None:
            super_kwargs["middleware"] = middleware

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
            raise ServiceInitializationError("OpenAI client is not initialized")

        return self.client

    def _get_api_key(
        self, api_key: str | SecretStr | Callable[[], str | Awaitable[str]] | None
    ) -> str | Callable[[], str | Awaitable[str]] | None:
        """Get the appropriate API key value for client initialization.

        Args:
            api_key: The API key parameter which can be a string, SecretStr, callable, or None.

        Returns:
            For callable API keys: returns the callable directly.
            For SecretStr API keys: returns the string value.
            For string/None API keys: returns as-is.
        """
        if isinstance(api_key, SecretStr):
            return api_key.get_secret_value()

        # Check version compatibility for callable API keys
        if callable(api_key):
            _check_openai_version_for_callable_api_key()

        return api_key  # Pass callable, string, or None directly to OpenAI SDK


class OpenAIConfigMixin(OpenAIBase):
    """Internal class for configuring a connection to an OpenAI service."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "openai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        model_id: str,
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
            model_id: OpenAI model identifier. Must be non-empty.
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
                raise ServiceInitializationError("Please provide an api_key")
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
            "model_id": model_id,
            "client": client,
        }
        if instruction_role:
            args["instruction_role"] = instruction_role

        # Ensure additional_properties and middleware are passed through kwargs to BaseChatClient
        # These are consumed by BaseChatClient.__init__ via kwargs
        super().__init__(**args, **kwargs)


def to_assistant_tools(
    tools: Sequence[ToolProtocol | MutableMapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Convert Agent Framework tools to OpenAI Assistants API format.

    Args:
        tools: Normalized tools (from ChatOptions.tools).

    Returns:
        List of tool definitions for OpenAI Assistants API.
    """
    if not tools:
        return []

    tool_definitions: list[dict[str, Any]] = []

    for tool in tools:
        if isinstance(tool, FunctionTool):
            tool_definitions.append(tool.to_json_schema_spec())
        elif isinstance(tool, HostedCodeInterpreterTool):
            tool_definitions.append({"type": "code_interpreter"})
        elif isinstance(tool, HostedFileSearchTool):
            params: dict[str, Any] = {"type": "file_search"}
            if tool.max_results is not None:
                params["file_search"] = {"max_num_results": tool.max_results}
            tool_definitions.append(params)
        elif isinstance(tool, MutableMapping):
            # Pass through raw dict definitions
            tool_definitions.append(dict(tool))

    return tool_definitions


def from_assistant_tools(
    assistant_tools: list[Any] | None,
) -> list[ToolProtocol]:
    """Convert OpenAI Assistant tools to Agent Framework format.

    This converts hosted tools (code_interpreter, file_search) from an OpenAI
    Assistant definition back to Agent Framework tool instances.

    Note: Function tools are skipped - user must provide implementations separately.

    Args:
        assistant_tools: Tools from OpenAI Assistant object (assistant.tools).

    Returns:
        List of Agent Framework tool instances for hosted tools.
    """
    if not assistant_tools:
        return []

    tools: list[ToolProtocol] = []

    for tool in assistant_tools:
        if hasattr(tool, "type"):
            tool_type = tool.type
        elif isinstance(tool, dict):
            tool_type = tool.get("type")
        else:
            tool_type = None

        if tool_type == "code_interpreter":
            tools.append(HostedCodeInterpreterTool())
        elif tool_type == "file_search":
            tools.append(HostedFileSearchTool())
        # Skip function tools - user must provide implementations

    return tools
