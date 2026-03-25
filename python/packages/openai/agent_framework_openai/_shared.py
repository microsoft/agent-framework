# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from copy import copy
from typing import Any, ClassVar, Union, cast

import openai
from agent_framework._serialization import SerializationMixin
from agent_framework._settings import SecretString, load_settings
from agent_framework._telemetry import APP_INFO, USER_AGENT_KEY, prepend_agent_framework_to_user_agent
from agent_framework._tools import FunctionTool
from dotenv import dotenv_values
from openai import AsyncOpenAI, AsyncStream, _legacy_response  # type: ignore
from openai.types import Completion
from openai.types.audio import Transcription
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.images_response import ImagesResponse
from openai.types.responses.response import Response
from openai.types.responses.response_stream_event import ResponseStreamEvent
from packaging.version import parse

logger: logging.Logger = logging.getLogger("agent_framework.openai")

DEFAULT_AZURE_OPENAI_CHAT_COMPLETION_API_VERSION = "2024-10-21"
DEFAULT_AZURE_OPENAI_RESPONSES_API_VERSION = "preview"


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

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover


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

    api_key: SecretString | Callable[[], str | Awaitable[str]] | None
    base_url: str | None
    org_id: str | None
    model: str | None
    embedding_model: str | None
    azure_endpoint: str | None
    api_version: str | None


def _load_dotenv_values(*, env_file_path: str | None, env_file_encoding: str | None) -> dict[str, str]:
    """Load dotenv values for non-standard environment variable aliases."""
    if env_file_path is None or not os.path.exists(env_file_path):
        return {}

    raw_dotenv_values = dotenv_values(dotenv_path=env_file_path, encoding=env_file_encoding or "utf-8")
    return {key: value for key, value in raw_dotenv_values.items() if value is not None}


def _get_setting_from_alias(
    name: str,
    *,
    dotenv_values_by_name: Mapping[str, str],
) -> str | None:
    """Resolve a setting from an explicit env-var alias."""
    if dotenv_value := dotenv_values_by_name.get(name):
        return dotenv_value
    return os.getenv(name)


def load_openai_service_settings(
    *,
    model: str | None,
    api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None,
    org_id: str | None,
    base_url: str | None,
    azure_endpoint: str | None,
    api_version: str | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
    azure_model_env_vars: Sequence[str],
    default_azure_api_version: str,
) -> tuple[OpenAISettings, bool]:
    """Load OpenAI settings, including Azure OpenAI aliases.

    The generic OpenAI clients primarily read from ``OPENAI_*`` variables. When an
    ``AZURE_OPENAI_ENDPOINT`` (or ``AZURE_OPENAI_BASE_URL``) is available and no
    explicit OpenAI base URL is configured, this helper switches to Azure-specific
    environment variables for endpoint, API key, model deployment, and API version.
    """
    openai_settings = load_settings(
        OpenAISettings,
        env_prefix="OPENAI_",
        api_key=api_key,
        org_id=org_id,
        base_url=base_url,
        model=model,
        azure_endpoint=azure_endpoint,
        api_version=api_version,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )

    dotenv_values_by_name = _load_dotenv_values(
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )

    resolved_azure_endpoint = azure_endpoint
    resolved_azure_base_url: str | None = None
    if not openai_settings.get("base_url"):
        if resolved_azure_endpoint is None:
            resolved_azure_endpoint = _get_setting_from_alias(
                "AZURE_OPENAI_ENDPOINT",
                dotenv_values_by_name=dotenv_values_by_name,
            )
        if resolved_azure_endpoint is None:
            resolved_azure_base_url = _get_setting_from_alias(
                "AZURE_OPENAI_BASE_URL",
                dotenv_values_by_name=dotenv_values_by_name,
            )
            if resolved_azure_base_url is not None:
                openai_settings["base_url"] = resolved_azure_base_url

    use_azure_client = resolved_azure_endpoint is not None or resolved_azure_base_url is not None
    if resolved_azure_endpoint is not None:
        openai_settings["azure_endpoint"] = resolved_azure_endpoint

    if use_azure_client:
        if api_key is None:
            resolved_azure_api_key = _get_setting_from_alias(
                "AZURE_OPENAI_API_KEY",
                dotenv_values_by_name=dotenv_values_by_name,
            )
            if resolved_azure_api_key is not None:
                openai_settings["api_key"] = SecretString(resolved_azure_api_key)

        if model is None:
            for env_var_name in azure_model_env_vars:
                resolved_model = _get_setting_from_alias(
                    env_var_name,
                    dotenv_values_by_name=dotenv_values_by_name,
                )
                if resolved_model is not None:
                    openai_settings["model"] = resolved_model
                    break

        if not openai_settings.get("api_version"):
            resolved_api_version = _get_setting_from_alias(
                "AZURE_OPENAI_API_VERSION",
                dotenv_values_by_name=dotenv_values_by_name,
            )
            openai_settings["api_version"] = resolved_api_version or default_azure_api_version

    return openai_settings, use_azure_client


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
