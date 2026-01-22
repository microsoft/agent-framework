# Copyright (c) Microsoft. All rights reserved.

import json
import sys
from collections.abc import (
    AsyncIterable,
    Awaitable,
    Callable,
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
)
from copy import copy
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypedDict, cast, overload

if TYPE_CHECKING:
    from openai.lib.azure import AsyncAzureADTokenProvider

    from .._agents import ChatAgent

from azure.core.credentials import TokenCredential
from openai import AsyncOpenAI
from openai.lib.azure import AsyncAzureOpenAI
from openai.types.beta.threads import (
    ImageURLContentBlockParam,
    ImageURLParam,
    MessageContentPartParam,
    MessageDeltaEvent,
    Run,
    TextContentBlockParam,
    TextDeltaBlock,
)
from openai.types.beta.threads.run_create_params import AdditionalMessage
from openai.types.beta.threads.run_submit_tool_outputs_params import ToolOutput
from openai.types.beta.threads.runs import RunStep

from .._clients import BaseChatClient
from .._memory import ContextProvider
from .._middleware import Middleware, use_chat_middleware
from .._telemetry import APP_INFO, USER_AGENT_KEY, prepend_agent_framework_to_user_agent
from .._threads import ChatMessageStoreProtocol
from .._tools import (
    FunctionTool,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    ToolProtocol,
    use_function_invocation,
)
from .._types import (
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Role,
    UsageDetails,
    prepare_function_call_results,
)
from ..exceptions import ServiceInitializationError
from ..observability import use_instrumentation
from ._shared import OpenAIBackend, OpenAIBase, OpenAISettings, _check_openai_version_for_callable_api_key

if sys.version_info >= (3, 13):
    from typing import TypeVar
else:
    from typing_extensions import TypeVar

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


__all__ = [
    "AssistantToolResources",
    "OpenAIAssistantsClient",
    "OpenAIAssistantsOptions",
    "OpenAIBackend",
]


# region OpenAI Assistants Options TypedDict


class VectorStoreToolResource(TypedDict, total=False):
    """Vector store configuration for file search tool resources."""

    vector_store_ids: list[str]
    """IDs of vector stores attached to this assistant."""


class CodeInterpreterToolResource(TypedDict, total=False):
    """Code interpreter tool resource configuration."""

    file_ids: list[str]
    """File IDs accessible by the code interpreter tool. Max 20 files per assistant."""


class AssistantToolResources(TypedDict, total=False):
    """Tool resources attached to the assistant.

    See: https://platform.openai.com/docs/api-reference/assistants/createAssistant#assistants-createassistant-tool_resources
    """

    code_interpreter: CodeInterpreterToolResource
    """Resources for code interpreter tool, including file IDs."""

    file_search: VectorStoreToolResource
    """Resources for file search tool, including vector store IDs."""


class OpenAIAssistantsOptions(ChatOptions, total=False):
    """OpenAI Assistants API-specific options dict.

    Extends base ChatOptions with Assistants API-specific parameters
    for creating and running assistants.

    See: https://platform.openai.com/docs/api-reference/assistants

    Keys:
        # Inherited from ChatOptions:
        model_id: The model to use for the assistant,
            translates to ``model`` in OpenAI API.
        temperature: Sampling temperature between 0 and 2.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum number of tokens to generate,
            translates to ``max_completion_tokens`` in OpenAI API.
        tools: List of tools (functions, code_interpreter, file_search).
        tool_choice: How the model should use tools.
        allow_multiple_tool_calls: Whether to allow parallel tool calls,
            translates to ``parallel_tool_calls`` in OpenAI API.
        response_format: Structured output schema.
        metadata: Request metadata for tracking.

        # Options not supported in Assistants API (inherited but unused):
        stop: Not supported.
        seed: Not supported (use assistant-level configuration instead).
        frequency_penalty: Not supported.
        presence_penalty: Not supported.
        user: Not supported.
        store: Not supported.

        # Assistants-specific options:
        name: Name of the assistant.
        description: Description of the assistant.
        instructions: System instructions for the assistant.
        tool_resources: Resources for tools (file IDs, vector stores).
        reasoning_effort: Effort level for o-series reasoning models.
        conversation_id: Thread ID to continue conversation in.
    """

    # Assistants-specific options
    name: str
    """Name of the assistant (max 256 characters)."""

    description: str
    """Description of the assistant (max 512 characters)."""

    tool_resources: AssistantToolResources
    """Tool-specific resources like file IDs and vector stores."""

    reasoning_effort: Literal["low", "medium", "high"]
    """Effort level for o-series reasoning models (o1, o3-mini).
    Higher effort = more reasoning time and potentially better results."""

    conversation_id: str  # type: ignore[misc]
    """Thread ID to continue a conversation in an existing thread."""

    # OpenAI/ChatOptions fields not supported in Assistants API
    stop: None  # type: ignore[misc]
    """Not supported in Assistants API."""

    seed: None  # type: ignore[misc]
    """Not supported in Assistants API (use assistant-level configuration)."""

    frequency_penalty: None  # type: ignore[misc]
    """Not supported in Assistants API."""

    presence_penalty: None  # type: ignore[misc]
    """Not supported in Assistants API."""

    user: None  # type: ignore[misc]
    """Not supported in Assistants API."""

    store: None  # type: ignore[misc]
    """Not supported in Assistants API."""


ASSISTANTS_OPTION_TRANSLATIONS: dict[str, str] = {
    "model_id": "model",
    "max_tokens": "max_completion_tokens",
    "allow_multiple_tool_calls": "parallel_tool_calls",
}
"""Maps ChatOptions keys to OpenAI Assistants API parameter names."""

TOpenAIAssistantsOptions = TypeVar(
    "TOpenAIAssistantsOptions",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIAssistantsOptions",
    covariant=True,
)

# Default Azure API version for Assistants API
DEFAULT_AZURE_ASSISTANTS_API_VERSION = "2024-05-01-preview"


# endregion


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class OpenAIAssistantsClient(
    OpenAIBase,
    BaseChatClient[TOpenAIAssistantsOptions],
    Generic[TOpenAIAssistantsOptions],
):
    """OpenAI Assistants client with multi-backend support.

    This client supports two backends:
    - **openai**: Direct OpenAI API (default)
    - **azure**: Azure OpenAI Service

    The backend is determined automatically based on which credentials are available,
    or can be explicitly specified via the `backend` parameter.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "openai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    @overload
    def __init__(
        self,
        *,
        backend: Literal["openai"],
        model_id: str | None = None,
        assistant_id: str | None = None,
        assistant_name: str | None = None,
        assistant_description: str | None = None,
        thread_id: str | None = None,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with direct OpenAI API backend.

        Args:
            backend: Must be "openai" for direct OpenAI API.
            model_id: The model to use (e.g., "gpt-4o").
                Env var: OPENAI_CHAT_MODEL_ID
            assistant_id: ID of existing assistant to use.
            assistant_name: Name for new assistants.
            assistant_description: Description for new assistants.
            thread_id: Default thread ID for conversations.
            api_key: OpenAI API key.
                Env var: OPENAI_API_KEY
            org_id: OpenAI organization ID.
                Env var: OPENAI_ORG_ID
            base_url: Custom base URL.
                Env var: OPENAI_BASE_URL
            default_headers: Default headers for HTTP requests.
            client: Pre-configured AsyncOpenAI client.
            env_file_path: Path to .env file.
            env_file_encoding: Encoding of the .env file.
            **kwargs: Additional arguments.
        """
        ...

    @overload
    def __init__(
        self,
        *,
        backend: Literal["azure"],
        model_id: str | None = None,
        assistant_id: str | None = None,
        assistant_name: str | None = None,
        assistant_description: str | None = None,
        thread_id: str | None = None,
        azure_api_key: str | None = None,
        endpoint: str | None = None,
        azure_base_url: str | None = None,
        api_version: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: "AsyncAzureADTokenProvider | None" = None,
        token_endpoint: str | None = None,
        credential: TokenCredential | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncAzureOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with Azure OpenAI backend.

        Args:
            backend: Must be "azure" for Azure OpenAI Service.
            model_id: The deployment name to use.
                Env var: AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
            assistant_id: ID of existing assistant to use.
            assistant_name: Name for new assistants.
            assistant_description: Description for new assistants.
            thread_id: Default thread ID for conversations.
            azure_api_key: Azure OpenAI API key.
                Env var: AZURE_OPENAI_API_KEY
            endpoint: Azure OpenAI endpoint URL.
                Env var: AZURE_OPENAI_ENDPOINT
            azure_base_url: Custom base URL.
                Env var: AZURE_OPENAI_BASE_URL
            api_version: Azure API version.
                Env var: AZURE_OPENAI_API_VERSION
            ad_token: Azure AD token for authentication.
            ad_token_provider: Callable that provides Azure AD tokens.
            token_endpoint: Token endpoint for Azure AD.
                Env var: AZURE_OPENAI_TOKEN_ENDPOINT
            credential: Azure TokenCredential for authentication.
            default_headers: Default headers for HTTP requests.
            client: Pre-configured AsyncAzureOpenAI client.
            env_file_path: Path to .env file.
            env_file_encoding: Encoding of the .env file.
            **kwargs: Additional arguments.
        """
        ...

    @overload
    def __init__(
        self,
        *,
        backend: None = None,
        model_id: str | None = None,
        assistant_id: str | None = None,
        assistant_name: str | None = None,
        assistant_description: str | None = None,
        thread_id: str | None = None,
        # OpenAI backend parameters
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        # Azure backend parameters
        azure_api_key: str | None = None,
        endpoint: str | None = None,
        azure_base_url: str | None = None,
        api_version: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: "AsyncAzureADTokenProvider | None" = None,
        token_endpoint: str | None = None,
        credential: TokenCredential | None = None,
        # Common parameters
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | AsyncAzureOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with auto-detected backend based on available credentials.

        Backend detection order (first match wins):
        1. openai - if OPENAI_API_KEY is set
        2. azure - if AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY is set

        Args:
            backend: None for auto-detection.
            model_id: Model name (OpenAI) or deployment name (Azure).
            assistant_id: ID of existing assistant to use.
            assistant_name: Name for new assistants.
            assistant_description: Description for new assistants.
            thread_id: Default thread ID for conversations.
            api_key: OpenAI API key (for openai backend).
            org_id: OpenAI organization ID (for openai backend).
            base_url: Custom base URL (for openai backend).
            azure_api_key: Azure OpenAI API key (for azure backend).
            endpoint: Azure OpenAI endpoint URL (for azure backend).
            azure_base_url: Custom base URL (for azure backend).
            api_version: Azure API version (for azure backend).
            ad_token: Azure AD token (for azure backend).
            ad_token_provider: Azure AD token provider (for azure backend).
            token_endpoint: Token endpoint for Azure AD (for azure backend).
            credential: Azure TokenCredential (for azure backend).
            default_headers: Default headers for HTTP requests.
            client: Pre-configured client instance.
            env_file_path: Path to .env file.
            env_file_encoding: Encoding of the .env file.
            **kwargs: Additional arguments.
        """
        ...

    def __init__(
        self,
        *,
        backend: OpenAIBackend | None = None,
        model_id: str | None = None,
        assistant_id: str | None = None,
        assistant_name: str | None = None,
        assistant_description: str | None = None,
        thread_id: str | None = None,
        # OpenAI backend parameters
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        # Azure backend parameters
        azure_api_key: str | None = None,
        endpoint: str | None = None,
        azure_base_url: str | None = None,
        api_version: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: "AsyncAzureADTokenProvider | None" = None,
        token_endpoint: str | None = None,
        credential: TokenCredential | None = None,
        # Common parameters
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | AsyncAzureOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        # Backward compatibility
        async_client: AsyncOpenAI | AsyncAzureOpenAI | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an OpenAI Assistants client."""
        # Handle backward compatibility
        if async_client is not None and client is None:
            client = async_client

        # Create settings to resolve env vars and detect backend
        settings = OpenAISettings(
            backend=backend,
            chat_model_id=model_id,
            api_key=api_key if isinstance(api_key, str) or api_key is None else None,
            org_id=org_id,
            base_url=base_url,
            azure_api_key=azure_api_key,
            endpoint=endpoint,
            azure_base_url=azure_base_url,
            api_version=api_version,
            ad_token=ad_token,
            ad_token_provider=ad_token_provider,
            token_endpoint=token_endpoint,
            credential=credential,
            default_headers=default_headers,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        # Store callable API key if provided
        callable_api_key: Callable[[], str | Awaitable[str]] | None = None
        if callable(api_key):
            callable_api_key = api_key
            _check_openai_version_for_callable_api_key()

        # Determine the backend
        self._backend: OpenAIBackend = settings._backend or "openai"  # type: ignore[assignment]

        # For Azure Assistants API, apply default API version
        if self._backend == "azure" and settings.api_version is None:
            settings.api_version = DEFAULT_AZURE_ASSISTANTS_API_VERSION

        # Validate required fields based on backend
        if self._backend == "openai":
            if not client and not settings.api_key and not callable_api_key:
                raise ServiceInitializationError(
                    "OpenAI API key is required. Set via 'api_key' parameter or 'OPENAI_API_KEY' environment variable."
                )
            if not settings.chat_model_id:
                raise ServiceInitializationError(
                    "OpenAI model ID is required. "
                    "Set via 'model_id' parameter or 'OPENAI_CHAT_MODEL_ID' environment variable."
                )
        else:  # azure
            if not client:
                has_auth = (
                    settings.azure_api_key or settings.ad_token or settings.ad_token_provider or settings.credential
                )
                if not has_auth:
                    raise ServiceInitializationError(
                        "Azure OpenAI authentication is required. Provide azure_api_key, ad_token, "
                        "ad_token_provider, or credential."
                    )
                if not settings.endpoint and not settings.azure_base_url:
                    raise ServiceInitializationError(
                        "Azure OpenAI endpoint is required. Set via 'endpoint' parameter "
                        "or 'AZURE_OPENAI_ENDPOINT' environment variable."
                    )
            if not settings.chat_model_id:
                raise ServiceInitializationError(
                    "Azure OpenAI deployment name is required. Set via 'model_id' parameter "
                    "or 'AZURE_OPENAI_CHAT_DEPLOYMENT_NAME' environment variable."
                )

        # Create the appropriate client
        if client is None:
            client = self._create_client(settings, callable_api_key, default_headers)

        # Set the OTEL provider name based on backend
        if self._backend == "azure":
            self.OTEL_PROVIDER_NAME = "azure.ai.openai"  # type: ignore[misc]

        # Store configuration for serialization
        self.org_id = settings.org_id
        self.base_url = str(settings.base_url) if settings.base_url else None
        self.endpoint = str(settings.endpoint) if settings.endpoint else None
        self.api_version = settings.api_version
        # Store default_headers but filter out USER_AGENT_KEY for serialization
        if default_headers:
            self.default_headers: dict[str, Any] | None = {
                k: v for k, v in default_headers.items() if k != USER_AGENT_KEY
            }
        else:
            self.default_headers = None

        # Store assistant-specific attributes
        self.assistant_id: str | None = assistant_id
        self.assistant_name: str | None = assistant_name
        self.assistant_description: str | None = assistant_description
        self.thread_id: str | None = thread_id
        self._should_delete_assistant: bool = False

        # Call parent __init__
        super().__init__(
            model_id=settings.chat_model_id,
            client=client,
            **kwargs,
        )

    def _create_client(
        self,
        settings: OpenAISettings,
        callable_api_key: Callable[[], str | Awaitable[str]] | None,
        default_headers: Mapping[str, str] | None,
    ) -> AsyncOpenAI | AsyncAzureOpenAI:
        """Create the appropriate client based on backend."""
        # Merge APP_INFO into headers
        merged_headers = dict(copy(default_headers)) if default_headers else {}
        if APP_INFO:
            merged_headers.update(APP_INFO)
            merged_headers = prepend_agent_framework_to_user_agent(merged_headers)

        if self._backend == "openai":
            return self._create_openai_client(settings, callable_api_key, merged_headers)
        return self._create_azure_client(settings, merged_headers)

    def _create_openai_client(
        self,
        settings: OpenAISettings,
        callable_api_key: Callable[[], str | Awaitable[str]] | None,
        headers: dict[str, str],
    ) -> AsyncOpenAI:
        """Create an OpenAI client."""
        api_key_value: str | Callable[[], str | Awaitable[str]] | None = callable_api_key
        if api_key_value is None:
            api_key_value = settings.get_api_key_value()

        args: dict[str, Any] = {
            "api_key": api_key_value,
            "default_headers": headers,
        }
        if settings.org_id:
            args["organization"] = settings.org_id
        if settings.base_url:
            args["base_url"] = str(settings.base_url)

        return AsyncOpenAI(**args)

    def _create_azure_client(
        self,
        settings: OpenAISettings,
        headers: dict[str, str],
    ) -> AsyncAzureOpenAI:
        """Create an Azure OpenAI client."""
        # Get Azure AD token if credential is provided
        ad_token = settings.ad_token
        if not ad_token and not settings.ad_token_provider and settings.credential:
            ad_token = settings.get_azure_auth_token()

        api_key = settings.get_api_key_value()
        if not api_key and not ad_token and not settings.ad_token_provider:
            raise ServiceInitializationError(
                "Please provide either azure_api_key, ad_token, ad_token_provider, or credential."
            )

        args: dict[str, Any] = {"default_headers": headers}

        if settings.api_version:
            args["api_version"] = settings.api_version
        if ad_token:
            args["azure_ad_token"] = ad_token
        if settings.ad_token_provider:
            args["azure_ad_token_provider"] = settings.ad_token_provider
        if api_key:
            args["api_key"] = api_key
        if settings.azure_base_url:
            args["base_url"] = str(settings.azure_base_url)
        if settings.endpoint and not settings.azure_base_url:
            args["azure_endpoint"] = str(settings.endpoint)

        return AsyncAzureOpenAI(**args)

    @property
    def backend(self) -> OpenAIBackend:
        """Get the backend being used."""
        return self._backend

    async def __aenter__(self) -> "Self":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit - clean up any assistants we created."""
        await self.close()

    async def close(self) -> None:
        """Clean up any assistants we created."""
        if self._should_delete_assistant and self.assistant_id is not None:
            client = await self._ensure_client()
            await client.beta.assistants.delete(self.assistant_id)
            object.__setattr__(self, "assistant_id", None)
            object.__setattr__(self, "_should_delete_assistant", False)

    @override
    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        return await ChatResponse.from_chat_response_generator(
            updates=self._inner_get_streaming_response(messages=messages, options=options, **kwargs),
            output_format_type=options.get("response_format"),
        )

    @override
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        # prepare
        run_options, tool_results = self._prepare_options(messages, options, **kwargs)

        # Get the thread ID
        thread_id: str | None = options.get("conversation_id", run_options.get("conversation_id", self.thread_id))

        if thread_id is None and tool_results is not None:
            raise ValueError("No thread ID was provided, but chat messages includes tool results.")

        # Determine which assistant to use and create if needed
        assistant_id = await self._get_assistant_id_or_create()

        # execute
        stream, thread_id = await self._create_assistant_stream(thread_id, assistant_id, run_options, tool_results)

        # process
        async for update in self._process_stream_events(stream, thread_id):
            yield update

    async def _get_assistant_id_or_create(self) -> str:
        """Determine which assistant to use and create if needed.

        Returns:
            str: The assistant_id to use.
        """
        # If no assistant is provided, create a temporary assistant
        if self.assistant_id is None:
            if not self.model_id:
                raise ServiceInitializationError("Parameter 'model_id' is required for assistant creation.")

            client = await self._ensure_client()
            created_assistant = await client.beta.assistants.create(
                model=self.model_id,
                description=self.assistant_description,
                name=self.assistant_name,
            )
            self.assistant_id = created_assistant.id
            self._should_delete_assistant = True

        return self.assistant_id

    async def _create_assistant_stream(
        self,
        thread_id: str | None,
        assistant_id: str,
        run_options: dict[str, Any],
        tool_results: list[Content] | None,
    ) -> tuple[Any, str]:
        """Create the assistant stream for processing.

        Returns:
            tuple: (stream, final_thread_id)
        """
        client = await self._ensure_client()
        # Get any active run for this thread
        thread_run = await self._get_active_thread_run(thread_id)

        tool_run_id, tool_outputs = self._prepare_tool_outputs_for_assistants(tool_results)

        if thread_run is not None and tool_run_id is not None and tool_run_id == thread_run.id and tool_outputs:
            # There's an active run and we have tool results to submit, so submit the results.
            stream = client.beta.threads.runs.submit_tool_outputs_stream(  # type: ignore[reportDeprecated]
                run_id=tool_run_id,
                thread_id=thread_run.thread_id,
                tool_outputs=tool_outputs,
            )
            final_thread_id = thread_run.thread_id
        else:
            # Handle thread creation or cancellation
            final_thread_id = await self._prepare_thread(thread_id, thread_run, run_options)

            # Now create a new run and stream the results.
            stream = client.beta.threads.runs.stream(  # type: ignore[reportDeprecated]
                assistant_id=assistant_id, thread_id=final_thread_id, **run_options
            )

        return stream, final_thread_id

    async def _get_active_thread_run(self, thread_id: str | None) -> Run | None:
        """Get any active run for the given thread."""
        client = await self._ensure_client()
        if thread_id is None:
            return None

        async for run in client.beta.threads.runs.list(thread_id=thread_id, limit=1, order="desc"):  # type: ignore[reportDeprecated]
            if run.status not in ["completed", "cancelled", "failed", "expired"]:
                return run
        return None

    async def _prepare_thread(self, thread_id: str | None, thread_run: Run | None, run_options: dict[str, Any]) -> str:
        """Prepare the thread for a new run, creating or cleaning up as needed."""
        client = await self._ensure_client()
        if thread_id is None:
            # No thread ID was provided, so create a new thread.
            thread = await client.beta.threads.create(  # type: ignore[reportDeprecated]
                messages=run_options["additional_messages"],
                tool_resources=run_options.get("tool_resources"),
                metadata=run_options.get("metadata"),
            )
            run_options["additional_messages"] = []
            run_options.pop("tool_resources", None)
            return thread.id

        if thread_run is not None:
            # There was an active run; we need to cancel it before starting a new run.
            await client.beta.threads.runs.cancel(run_id=thread_run.id, thread_id=thread_id)  # type: ignore[reportDeprecated]

        return thread_id

    async def _process_stream_events(self, stream: Any, thread_id: str) -> AsyncIterable[ChatResponseUpdate]:
        response_id: str | None = None

        async with stream as response_stream:
            async for response in response_stream:
                if response.event == "thread.run.created":
                    yield ChatResponseUpdate(
                        contents=[],
                        conversation_id=thread_id,
                        message_id=response_id,
                        raw_representation=response.data,
                        response_id=response_id,
                        role=Role.ASSISTANT,
                    )
                elif response.event == "thread.run.step.created" and isinstance(response.data, RunStep):
                    response_id = response.data.run_id
                elif response.event == "thread.message.delta" and isinstance(response.data, MessageDeltaEvent):
                    delta = response.data.delta
                    role = Role.USER if delta.role == "user" else Role.ASSISTANT

                    for delta_block in delta.content or []:
                        if isinstance(delta_block, TextDeltaBlock) and delta_block.text and delta_block.text.value:
                            yield ChatResponseUpdate(
                                role=role,
                                text=delta_block.text.value,
                                conversation_id=thread_id,
                                message_id=response_id,
                                raw_representation=response.data,
                                response_id=response_id,
                            )
                elif response.event == "thread.run.requires_action" and isinstance(response.data, Run):
                    contents = self._parse_function_calls_from_assistants(response.data, response_id)
                    if contents:
                        yield ChatResponseUpdate(
                            role=Role.ASSISTANT,
                            contents=contents,
                            conversation_id=thread_id,
                            message_id=response_id,
                            raw_representation=response.data,
                            response_id=response_id,
                        )
                elif (
                    response.event == "thread.run.completed"
                    and isinstance(response.data, Run)
                    and response.data.usage is not None
                ):
                    usage = response.data.usage
                    usage_content = Content.from_usage(
                        UsageDetails(
                            input_token_count=usage.prompt_tokens,
                            output_token_count=usage.completion_tokens,
                            total_token_count=usage.total_tokens,
                        )
                    )
                    yield ChatResponseUpdate(
                        role=Role.ASSISTANT,
                        contents=[usage_content],
                        conversation_id=thread_id,
                        message_id=response_id,
                        raw_representation=response.data,
                        response_id=response_id,
                    )
                else:
                    yield ChatResponseUpdate(
                        contents=[],
                        conversation_id=thread_id,
                        message_id=response_id,
                        raw_representation=response.data,
                        response_id=response_id,
                        role=Role.ASSISTANT,
                    )

    def _parse_function_calls_from_assistants(self, event_data: Run, response_id: str | None) -> list[Content]:
        """Parse function call contents from an assistants tool action event."""
        contents: list[Content] = []

        if event_data.required_action is not None:
            for tool_call in event_data.required_action.submit_tool_outputs.tool_calls:
                tool_call_any = cast(Any, tool_call)
                call_id = json.dumps([response_id, tool_call.id])
                tool_type = getattr(tool_call, "type", None)
                if tool_type == "code_interpreter" and getattr(tool_call_any, "code_interpreter", None):
                    code_input = getattr(tool_call_any.code_interpreter, "input", None)
                    inputs = (
                        [Content.from_text(text=code_input, raw_representation=tool_call)]
                        if code_input is not None
                        else None
                    )
                    contents.append(
                        Content.from_code_interpreter_tool_call(
                            call_id=call_id,
                            inputs=inputs,
                            raw_representation=tool_call,
                        )
                    )
                elif tool_type == "mcp":
                    contents.append(
                        Content.from_mcp_server_tool_call(
                            call_id=call_id,
                            tool_name=getattr(tool_call, "name", "") or "",
                            server_name=getattr(tool_call, "server_label", None),
                            arguments=getattr(tool_call, "args", None),
                            raw_representation=tool_call,
                        )
                    )
                else:
                    function_name = tool_call.function.name
                    function_arguments = json.loads(tool_call.function.arguments)
                    contents.append(
                        Content.from_function_call(
                            call_id=call_id,
                            name=function_name,
                            arguments=function_arguments,
                        )
                    )

        return contents

    def _prepare_options(
        self,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> tuple[dict[str, Any], list[Content] | None]:
        from .._types import validate_tool_mode

        run_options: dict[str, Any] = {**kwargs}

        # Extract options from the dict
        max_tokens = options.get("max_tokens")
        model_id = options.get("model_id")
        top_p = options.get("top_p")
        temperature = options.get("temperature")
        allow_multiple_tool_calls = options.get("allow_multiple_tool_calls")
        tool_choice = options.get("tool_choice")
        tools = options.get("tools")
        response_format = options.get("response_format")

        if max_tokens is not None:
            run_options["max_completion_tokens"] = max_tokens
        if model_id is not None:
            run_options["model"] = model_id
        if top_p is not None:
            run_options["top_p"] = top_p
        if temperature is not None:
            run_options["temperature"] = temperature

        if allow_multiple_tool_calls is not None:
            run_options["parallel_tool_calls"] = allow_multiple_tool_calls

        tool_mode = validate_tool_mode(tool_choice)
        tool_definitions: list[MutableMapping[str, Any]] = []
        if tool_mode["mode"] != "none" and tools is not None:
            for tool in tools:
                if isinstance(tool, FunctionTool):
                    tool_definitions.append(tool.to_json_schema_spec())  # type: ignore[reportUnknownArgumentType]
                elif isinstance(tool, HostedCodeInterpreterTool):
                    tool_definitions.append({"type": "code_interpreter"})
                elif isinstance(tool, HostedFileSearchTool):
                    params: dict[str, Any] = {
                        "type": "file_search",
                    }
                    if tool.max_results is not None:
                        params["max_num_results"] = tool.max_results
                    tool_definitions.append(params)
                elif isinstance(tool, MutableMapping):
                    tool_definitions.append(tool)

        if len(tool_definitions) > 0:
            run_options["tools"] = tool_definitions

        if (mode := tool_mode["mode"]) == "required" and (
            func_name := tool_mode.get("required_function_name")
        ) is not None:
            run_options["tool_choice"] = {
                "type": "function",
                "function": {"name": func_name},
            }
        else:
            run_options["tool_choice"] = mode

        if response_format is not None:
            if isinstance(response_format, dict):
                run_options["response_format"] = response_format
            else:
                run_options["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_format.__name__,
                        "schema": response_format.model_json_schema(),
                        "strict": True,
                    },
                }

        instructions: list[str] = []
        tool_results: list[Content] | None = None

        additional_messages: list[AdditionalMessage] | None = None

        # System/developer messages are turned into instructions,
        # since there is no such message roles in OpenAI Assistants.
        # All other messages are added 1:1.
        for chat_message in messages:
            if chat_message.role.value in ["system", "developer"]:
                for text_content in [content for content in chat_message.contents if content.type == "text"]:
                    text = getattr(text_content, "text", None)
                    if text:
                        instructions.append(text)

                continue

            message_contents: list[MessageContentPartParam] = []

            for content in chat_message.contents:
                if content.type == "text":
                    message_contents.append(TextContentBlockParam(type="text", text=content.text))  # type: ignore[attr-defined, typeddict-item]
                elif content.type == "uri" and content.has_top_level_media_type("image"):
                    message_contents.append(
                        ImageURLContentBlockParam(type="image_url", image_url=ImageURLParam(url=content.uri))  # type: ignore[attr-defined, typeddict-item]
                    )
                elif content.type == "function_result":
                    if tool_results is None:
                        tool_results = []
                    tool_results.append(content)

            if len(message_contents) > 0:
                if additional_messages is None:
                    additional_messages = []
                additional_messages.append(
                    AdditionalMessage(
                        role="assistant" if chat_message.role == Role.ASSISTANT else "user",
                        content=message_contents,
                    )
                )

        if additional_messages is not None:
            run_options["additional_messages"] = additional_messages

        if len(instructions) > 0:
            run_options["instructions"] = "".join(instructions)

        return run_options, tool_results

    def _prepare_tool_outputs_for_assistants(
        self,
        tool_results: list[Content] | None,
    ) -> tuple[str | None, list[ToolOutput] | None]:
        """Prepare function results for submission to the assistants API."""
        run_id: str | None = None
        tool_outputs: list[ToolOutput] | None = None

        if tool_results:
            for function_result_content in tool_results:
                # When creating the FunctionCallContent, we created it with a CallId == [runId, callId].
                # We need to extract the run ID and ensure that the ToolOutput we send back to Azure
                # is only the call ID.
                run_and_call_ids: list[str] = json.loads(function_result_content.call_id)  # type: ignore[arg-type]

                if (
                    not run_and_call_ids
                    or len(run_and_call_ids) != 2
                    or not run_and_call_ids[0]
                    or not run_and_call_ids[1]
                    or (run_id is not None and run_id != run_and_call_ids[0])
                ):
                    continue

                run_id = run_and_call_ids[0]
                call_id = run_and_call_ids[1]

                if tool_outputs is None:
                    tool_outputs = []
                if function_result_content.result:
                    output = prepare_function_call_results(function_result_content.result)
                else:
                    output = "No output received."
                tool_outputs.append(ToolOutput(tool_call_id=call_id, output=output))

        return run_id, tool_outputs

    def _update_agent_name_and_description(self, agent_name: str | None, description: str | None = None) -> None:
        """Update the agent name in the chat client.

        Args:
            agent_name: The new name for the agent.
            description: The new description for the agent.
        """
        # This is a no-op in the base class, but can be overridden by subclasses
        # to update the agent name in the client.
        if agent_name and not self.assistant_name:
            self.assistant_name = agent_name
        if description and not self.assistant_description:
            self.assistant_description = description

    @override
    def as_agent(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        default_options: TOpenAIAssistantsOptions | None = None,
        chat_message_store_factory: Callable[[], ChatMessageStoreProtocol] | None = None,
        context_provider: ContextProvider | None = None,
        middleware: Sequence[Middleware] | None = None,
        **kwargs: Any,
    ) -> "ChatAgent[TOpenAIAssistantsOptions]":
        """Convert this chat client to a ChatAgent.

        This method creates a ChatAgent instance with this client pre-configured.
        It does NOT create an assistant on the OpenAI service - the actual assistant
        will be created on the server during the first invocation (run).

        For creating and managing persistent assistants on the server, use
        :class:`~agent_framework.openai.OpenAIAssistantProvider` instead.

        Keyword Args:
            id: The unique identifier for the agent. Will be created automatically if not provided.
            name: The name of the agent.
            description: A brief description of the agent's purpose.
            instructions: Optional instructions for the agent.
            tools: The tools to use for the request.
            default_options: A TypedDict containing chat options.
            chat_message_store_factory: Factory function to create an instance of ChatMessageStoreProtocol.
            context_provider: Context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
            kwargs: Any additional keyword arguments.

        Returns:
            A ChatAgent instance configured with this chat client.
        """
        return super().as_agent(
            id=id,
            name=name,
            description=description,
            instructions=instructions,
            tools=tools,
            default_options=default_options,
            chat_message_store_factory=chat_message_store_factory,
            context_provider=context_provider,
            middleware=middleware,
            **kwargs,
        )
