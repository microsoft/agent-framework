# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import logging
import sys
from collections.abc import (
    AsyncIterable,
    Awaitable,
    Callable,
    Mapping,
    MutableMapping,
    Sequence,
)
from datetime import datetime, timezone
from itertools import chain
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, cast, overload

from agent_framework._clients import BaseChatClient
from agent_framework._compaction import CompactionStrategy, TokenizerProtocol
from agent_framework._docstrings import apply_layered_docstring
from agent_framework._middleware import ChatAndFunctionMiddlewareTypes, ChatMiddlewareLayer
from agent_framework._settings import SecretString
from agent_framework._telemetry import USER_AGENT_KEY
from agent_framework._tools import (
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    FunctionTool,
    ToolTypes,
    normalize_tools,
)
from agent_framework._types import (
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FinishReason,
    Message,
    ResponseStream,
    UsageDetails,
)
from agent_framework.exceptions import (
    ChatClientException,
    ChatClientInvalidRequestException,
)
from agent_framework.observability import ChatTelemetryLayer
from openai import AsyncAzureOpenAI, AsyncOpenAI, BadRequestError
from openai.lib._parsing._completions import type_to_response_format_param
from openai.types import CompletionUsage
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_message_custom_tool_call import (
    ChatCompletionMessageCustomToolCall,
)
from openai.types.chat.completion_create_params import WebSearchOptions
from pydantic import BaseModel

from ._exceptions import OpenAIContentFilterException
from ._shared import (
    AzureTokenProvider,
    load_openai_service_settings,
    maybe_append_azure_endpoint_guidance,
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from azure.core.credentials import TokenCredential
    from azure.core.credentials_async import AsyncTokenCredential

    AzureCredentialTypes = TokenCredential | AsyncTokenCredential

logger = logging.getLogger("agent_framework.openai")

DEFAULT_AZURE_OPENAI_CHAT_COMPLETION_API_VERSION = "2024-12-01-preview"

ResponseModelBoundT = TypeVar("ResponseModelBoundT", bound=BaseModel)
ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel | None, default=None)


# region OpenAI Chat Options TypedDict


class PredictionTextContent(TypedDict, total=False):
    """Prediction text content options for OpenAI Chat completions."""

    type: Literal["text"]
    text: str


class Prediction(TypedDict, total=False):
    """Prediction options for OpenAI Chat completions."""

    type: Literal["content"]
    content: str | list[PredictionTextContent]


class OpenAIChatCompletionOptions(ChatOptions[ResponseModelT], Generic[ResponseModelT], total=False):
    """OpenAI-specific chat options dict.

    Extends ChatOptions with options specific to OpenAI's Chat Completions API.

    Keys:
        model_id: The model to use for the request,
            translates to ``model`` in OpenAI API.
        temperature: Sampling temperature between 0 and 2.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum number of tokens to generate,
            translates to ``max_completion_tokens`` in OpenAI API.
        stop: Stop sequences.
        seed: Random seed for reproducibility.
        frequency_penalty: Frequency penalty between -2.0 and 2.0.
        presence_penalty: Presence penalty between -2.0 and 2.0.
        tools: List of tools (functions) available to the model.
        tool_choice: How the model should use tools.
        allow_multiple_tool_calls: Whether to allow parallel tool calls,
            translates to ``parallel_tool_calls`` in OpenAI API.
        response_format: Structured output schema.
        metadata: Request metadata for tracking.
        user: End-user identifier for abuse monitoring.
        store: Whether to store the conversation.
        instructions: System instructions for the model (prepended as system message).
        # OpenAI-specific options (supported by all models):
        logit_bias: Token bias values (-100 to 100).
        logprobs: Whether to return log probabilities.
        top_logprobs: Number of top log probabilities to return (0-20).
        prediction: Whether to use predicted return tokens.
    """

    # OpenAI-specific generation parameters (supported by all models)
    logit_bias: dict[str | int, float]  # type: ignore[misc]
    logprobs: bool
    top_logprobs: int
    prediction: Prediction


OpenAIChatCompletionOptionsT = TypeVar(
    "OpenAIChatCompletionOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIChatCompletionOptions",
    covariant=True,
)

OPTION_TRANSLATIONS: dict[str, str] = {
    "model_id": "model",  # backward compat: accept model_id in options
    "allow_multiple_tool_calls": "parallel_tool_calls",
    "max_tokens": "max_completion_tokens",
}


# region Base Client
class RawOpenAIChatCompletionClient(  # type: ignore[misc]
    BaseChatClient[OpenAIChatCompletionOptionsT],
    Generic[OpenAIChatCompletionOptionsT],
):
    """Raw OpenAI Chat completion class without middleware, telemetry, or function invocation.

    Warning:
        **This class should not normally be used directly.** It does not include middleware,
        telemetry, or function invocation support that you most likely need. If you do use it,
        you should consider which additional layers to apply. There is a defined ordering that
        you should follow:

        1. **FunctionInvocationLayer** - Owns the tool/function calling loop and routes function middleware
        2. **ChatMiddlewareLayer** - Applies chat middleware per model call and stays outside telemetry
        3. **ChatTelemetryLayer** - Must stay inside chat middleware for correct per-call telemetry

        Use ``OpenAIChatCompletionClient`` instead for a fully-featured client with all layers applied.
    """

    INJECTABLE: ClassVar[set[str]] = {"client"}

    @overload
    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw OpenAI Chat completion client.

        Keyword Args:
            model: Model identifier to use for the request. When not provided, the constructor
                reads ``OPENAI_CHAT_MODEL`` and then ``OPENAI_MODEL``.
            api_key: API key. When not provided explicitly, the constructor reads
                ``OPENAI_API_KEY``. A callable API key is also supported.
            org_id: OpenAI organization ID. When not provided explicitly, the constructor reads
                ``OPENAI_ORG_ID``.
            base_url: Base URL override. When not provided explicitly, the constructor reads
                ``OPENAI_BASE_URL``.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured OpenAI client.
            instruction_role: Role for instruction messages (for example ``"system"``).
            compaction_strategy: Optional per-client compaction override.
            tokenizer: Optional tokenizer for compaction strategies.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Optional ``.env`` file that is checked before the process environment
                for ``OPENAI_*`` values.
            env_file_encoding: Encoding for the ``.env`` file.
        """
        ...

    @overload
    def __init__(
        self,
        model: str | None = None,
        *,
        azure_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        api_version: str | None = None,
        api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None = None,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw OpenAI Chat completion client.

        Keyword Args:
            model: Model identifier to use for the request. When not provided, the constructor
                reads ``AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`` and then
                ``AZURE_OPENAI_DEPLOYMENT_NAME``.
            azure_endpoint: Azure resource endpoint. When not provided explicitly, the constructor
                reads ``AZURE_OPENAI_ENDPOINT``.
            credential: Azure credential or token provider for Entra auth.
            api_version: Azure API version. When not provided explicitly, the constructor reads
                ``AZURE_OPENAI_API_VERSION`` and then uses the Chat Completions default.
            api_key: API key. For Azure this can be used instead of ``AZURE_OPENAI_API_KEY`` for key
                auth. A callable token provider is also accepted, but ``credential`` is the preferred
                Azure auth surface.
            base_url: Base URL override. When not provided explicitly, the constructor reads
                ``AZURE_OPENAI_BASE_URL``. Use this instead of ``azure_endpoint`` when you want
                to pass the full ``.../openai/v1`` base URL directly.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured client. Passing ``AsyncAzureOpenAI`` keeps the client on
                Azure; passing ``AsyncOpenAI`` keeps the client on OpenAI and bypasses env lookup.
            instruction_role: Role for instruction messages (for example ``"system"``).
            compaction_strategy: Optional per-client compaction override.
            tokenizer: Optional tokenizer for compaction strategies.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Optional ``.env`` file that is checked before process environment
                variables for ``AZURE_OPENAI_*`` values.
            env_file_encoding: Encoding for the ``.env`` file.
        """
        ...

    def __init__(
        self,
        model: str | None = None,
        *,
        model_id: str | None = None,
        api_key: str | SecretString | Callable[[], str | Awaitable[str]] | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        azure_endpoint: str | None = None,
        api_version: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw OpenAI Chat completion client.

        Keyword Args:
            model: Model identifier to use for the request. When not provided, the constructor
                reads ``OPENAI_CHAT_MODEL`` and then ``OPENAI_MODEL`` for OpenAI routing,
                or ``AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`` and then
                ``AZURE_OPENAI_DEPLOYMENT_NAME`` for Azure routing.
            model_id: Deprecated alias for ``model``.
            api_key: API key override. For OpenAI routing this maps to ``OPENAI_API_KEY``.
                For Azure routing this can be used instead of ``AZURE_OPENAI_API_KEY`` for key
                auth. A callable token provider is also accepted for backwards compatibility,
                but ``credential`` is the preferred Azure auth surface.
            credential: Azure credential or token provider for Azure OpenAI auth. Passing this
                is an explicit Azure signal, even when ``OPENAI_API_KEY`` is also configured.
                Credential objects require the optional ``azure-identity`` package.
            org_id: OpenAI organization ID. Used only for OpenAI routing and resolved from
                ``OPENAI_ORG_ID`` when not provided.
            base_url: Base URL override. For OpenAI routing this maps to ``OPENAI_BASE_URL``.
                For Azure routing this may be used instead of ``azure_endpoint`` when you want
                to pass the full ``.../openai/v1`` base URL directly.
            azure_endpoint: Azure resource endpoint. When not provided explicitly, Azure routing
                falls back to ``AZURE_OPENAI_ENDPOINT``.
            api_version: Azure API version to use once Azure routing is selected. When
                not provided explicitly, Azure routing falls back to
                ``AZURE_OPENAI_API_VERSION`` and then the Chat Completions default.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured client. Passing ``AsyncAzureOpenAI`` keeps the client on
                Azure; passing ``AsyncOpenAI`` keeps the client on OpenAI and bypasses env lookup.
            instruction_role: Role for instruction messages (for example ``"system"``).
            compaction_strategy: Optional per-client compaction override.
            tokenizer: Optional tokenizer for compaction strategies.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Optional ``.env`` file that is checked before process environment
                variables. The same file is used for both ``OPENAI_*`` and ``AZURE_OPENAI_*``
                lookups.
            env_file_encoding: Encoding for the ``.env`` file.

        Notes:
            Environment resolution and routing precedence are:

            1. Explicit Azure inputs (``azure_endpoint`` or ``credential``)
            2. Explicit OpenAI API key or ``OPENAI_API_KEY``
            3. Azure environment fallback

            OpenAI routing reads ``OPENAI_API_KEY``, ``OPENAI_CHAT_MODEL``,
            ``OPENAI_MODEL``, ``OPENAI_ORG_ID``, and ``OPENAI_BASE_URL``. Azure routing
            reads ``AZURE_OPENAI_ENDPOINT``, ``AZURE_OPENAI_BASE_URL``,
            ``AZURE_OPENAI_API_KEY``, ``AZURE_OPENAI_CHAT_DEPLOYMENT_NAME``,
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
            default_azure_api_version=DEFAULT_AZURE_OPENAI_CHAT_COMPLETION_API_VERSION,
            default_headers=default_headers,
            client=async_client,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            openai_model_fields=("chat_model", "model"),
            azure_deployment_fields=("chat_deployment_name", "deployment_name"),
        )

        self.client = client
        self.model: str = settings.get("model") or settings.get("deployment_name") or ""

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
        self.instruction_role = instruction_role
        if use_azure_client:
            self.OTEL_PROVIDER_NAME = "azure.ai.openai"  # type: ignore[misc]

        super().__init__(
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
        )

    # region Hosted Tool Factory Methods

    @staticmethod
    def get_web_search_tool(
        *,
        web_search_options: WebSearchOptions | None = None,
    ) -> dict[str, Any]:
        """Create a web search tool configuration for the Chat Completions API.

        Note: For the Chat Completions API, web search is passed via the `web_search_options`
        parameter rather than in the `tools` array. This method returns a dict that can be
        passed as a tool to ChatAgent, which will handle it appropriately.

        Keyword Args:
            web_search_options: The full WebSearchOptions configuration. This TypedDict includes:
                - user_location: Location context with "type" and "approximate" containing
                  "city", "country", "region", "timezone".
                - search_context_size: One of "low", "medium", "high".

        Returns:
            A dict configuration that enables web search when passed to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIChatCompletionClient

                # Basic web search
                tool = OpenAIChatCompletionClient.get_web_search_tool()

                # With location context
                tool = OpenAIChatCompletionClient.get_web_search_tool(
                    web_search_options={
                        "user_location": {
                            "type": "approximate",
                            "approximate": {"city": "Seattle", "country": "US"},
                        },
                        "search_context_size": "medium",
                    }
                )

                agent = ChatAgent(client, tools=[tool])
        """
        tool: dict[str, Any] = {"type": "web_search"}

        if web_search_options:
            tool.update(web_search_options)

        return tool

    # endregion

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[ResponseModelBoundT],
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[ResponseModelBoundT]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: OpenAIChatCompletionOptionsT | ChatOptions[None] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: OpenAIChatCompletionOptionsT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    @override
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: OpenAIChatCompletionOptionsT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Get a response from the raw OpenAI chat client."""
        super_get_response = cast(
            "Callable[..., Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]]",
            super().get_response,  # type: ignore[misc]
        )
        return super_get_response(  # type: ignore[no-any-return]
            messages=messages,
            stream=stream,
            options=options,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=client_kwargs,
        )

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        # prepare
        options_dict = self._prepare_options(messages, options)

        if stream:
            # Streaming mode
            options_dict["stream_options"] = {"include_usage": True}

            async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                client = self.client
                try:
                    async for chunk in await client.chat.completions.create(stream=True, **options_dict):
                        if len(chunk.choices) == 0 and chunk.usage is None:
                            continue
                        yield self._parse_response_update_from_openai(chunk)
                except BadRequestError as ex:
                    if ex.code == "content_filter":
                        raise OpenAIContentFilterException(
                            f"{type(self)} service encountered a content error: {ex}",
                            inner_exception=ex,
                        ) from ex
                    raise ChatClientException(
                        maybe_append_azure_endpoint_guidance(
                            f"{type(self)} service failed to complete the prompt: {ex}",
                            azure_endpoint=self.azure_endpoint,
                        ),
                        inner_exception=ex,
                    ) from ex
                except Exception as ex:
                    raise ChatClientException(
                        maybe_append_azure_endpoint_guidance(
                            f"{type(self)} service failed to complete the prompt: {ex}",
                            azure_endpoint=self.azure_endpoint,
                        ),
                        inner_exception=ex,
                    ) from ex

            return self._build_response_stream(_stream(), response_format=options.get("response_format"))

        # Non-streaming mode
        async def _get_response() -> ChatResponse:
            client = self.client
            try:
                return self._parse_response_from_openai(
                    await client.chat.completions.create(stream=False, **options_dict), options
                )
            except BadRequestError as ex:
                if ex.code == "content_filter":
                    raise OpenAIContentFilterException(
                        f"{type(self)} service encountered a content error: {ex}",
                        inner_exception=ex,
                    ) from ex
                raise ChatClientException(
                    maybe_append_azure_endpoint_guidance(
                        f"{type(self)} service failed to complete the prompt: {ex}",
                        azure_endpoint=self.azure_endpoint,
                    ),
                    inner_exception=ex,
                ) from ex
            except Exception as ex:
                raise ChatClientException(
                    maybe_append_azure_endpoint_guidance(
                        f"{type(self)} service failed to complete the prompt: {ex}",
                        azure_endpoint=self.azure_endpoint,
                    ),
                    inner_exception=ex,
                ) from ex

        return _get_response()

    # region content creation

    def _prepare_tools_for_openai(
        self,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None,
    ) -> dict[str, Any]:
        """Prepare tools for the OpenAI Chat Completions API.

        Converts FunctionTool to JSON schema format. Web search tools are routed
        to web_search_options parameter. All other tools pass through unchanged.

        Args:
            tools: Tool(s) to prepare.

        Returns:
            Dict containing tools and optionally web_search_options.
        """
        chat_tools: list[Any] = []
        web_search_options: dict[str, Any] | None = None
        for tool in normalize_tools(tools):
            if isinstance(tool, FunctionTool):
                chat_tools.append(tool.to_json_schema_spec())
            elif isinstance(tool, MutableMapping):
                typed_tool = cast(MutableMapping[str, Any], tool)
                if typed_tool.get("type") == "web_search":
                    # Web search is handled via web_search_options, not tools array
                    web_search_options = {k: v for k, v in typed_tool.items() if k != "type"}
                else:
                    # Pass through all other dict-based tools unchanged
                    chat_tools.append(typed_tool)
            else:
                # Pass through all other tools (SDK types) unchanged
                chat_tools.append(tool)
        result: dict[str, Any] = {}
        if chat_tools:
            result["tools"] = chat_tools
        if web_search_options is not None:
            result["web_search_options"] = web_search_options
        return result

    def _prepare_options(self, messages: Sequence[Message], options: Mapping[str, Any]) -> dict[str, Any]:
        # Prepend instructions from options if they exist
        from agent_framework._types import prepend_instructions_to_messages, validate_tool_mode

        if instructions := options.get("instructions"):
            messages = prepend_instructions_to_messages(list(messages), instructions, role="system")

        # Start with a copy of options
        run_options = {
            k: v for k, v in options.items() if v is not None and k not in {"instructions", "tools", "conversation_id"}
        }

        # messages
        if messages and "messages" not in run_options:
            run_options["messages"] = self._prepare_messages_for_openai(messages)
        if "messages" not in run_options:
            raise ChatClientInvalidRequestException("Messages are required for chat completions")

        # Translation between options keys and Chat Completion API
        for old_key, new_key in OPTION_TRANSLATIONS.items():
            if old_key in run_options and old_key != new_key:
                run_options[new_key] = run_options.pop(old_key)

        # model id
        if not run_options.get("model"):
            if not self.model:
                raise ValueError("model must be a non-empty string")
            run_options["model"] = self.model

        # tools
        tools = options.get("tools")
        if tools is not None:
            run_options.update(self._prepare_tools_for_openai(tools))
        # Only include tool_choice and parallel_tool_calls if tools are present
        if not run_options.get("tools"):
            run_options.pop("parallel_tool_calls", None)
            run_options.pop("tool_choice", None)
        elif tool_choice := run_options.pop("tool_choice", None):
            tool_mode = validate_tool_mode(tool_choice)
            if tool_mode is not None:
                if (mode := tool_mode.get("mode")) == "required" and (
                    func_name := tool_mode.get("required_function_name")
                ) is not None:
                    run_options["tool_choice"] = {
                        "type": "function",
                        "function": {"name": func_name},
                    }
                else:
                    run_options["tool_choice"] = mode

        # response format
        if response_format := options.get("response_format"):
            if isinstance(response_format, dict):
                run_options["response_format"] = response_format
            else:
                run_options["response_format"] = type_to_response_format_param(response_format)
        return run_options

    def _parse_response_from_openai(self, response: ChatCompletion, options: Mapping[str, Any]) -> ChatResponse:
        """Parse a response from OpenAI into a ChatResponse."""
        response_metadata = self._get_metadata_from_chat_response(response)
        messages: list[Message] = []
        finish_reason: FinishReason | None = None
        for choice in response.choices:
            response_metadata.update(self._get_metadata_from_chat_choice(choice))
            if choice.finish_reason:
                finish_reason = choice.finish_reason  # type: ignore[assignment]
            contents: list[Content] = []
            if text_content := self._parse_text_from_openai(choice):
                contents.append(text_content)
            if parsed_tool_calls := [tool for tool in self._parse_tool_calls_from_openai(choice)]:
                contents.extend(parsed_tool_calls)
            if reasoning_details := getattr(choice.message, "reasoning_details", None):
                contents.append(Content.from_text_reasoning(protected_data=json.dumps(reasoning_details)))
            messages.append(Message(role="assistant", contents=contents))
        return ChatResponse(
            response_id=response.id,
            created_at=datetime.fromtimestamp(response.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            usage_details=self._parse_usage_from_openai(response.usage) if response.usage else None,
            messages=messages,
            model=response.model,
            additional_properties=response_metadata,
            finish_reason=finish_reason,
            response_format=options.get("response_format"),
        )

    def _parse_response_update_from_openai(
        self,
        chunk: ChatCompletionChunk,
    ) -> ChatResponseUpdate:
        """Parse a streaming response update from OpenAI."""
        chunk_metadata = self._get_metadata_from_streaming_chat_response(chunk)
        contents: list[Content] = []
        finish_reason: FinishReason | None = None

        # Process usage data (may coexist with text/tool content in providers like Gemini).
        # See https://github.com/microsoft/agent-framework/issues/3434
        if chunk.usage:
            contents.append(
                Content.from_usage(usage_details=self._parse_usage_from_openai(chunk.usage), raw_representation=chunk)
            )

        for choice in chunk.choices:
            chunk_metadata.update(self._get_metadata_from_chat_choice(choice))
            contents.extend(self._parse_tool_calls_from_openai(choice))
            if choice.finish_reason:
                finish_reason = choice.finish_reason  # type: ignore[assignment]

            if text_content := self._parse_text_from_openai(choice):
                contents.append(text_content)
            if reasoning_details := getattr(choice.delta, "reasoning_details", None):
                contents.append(Content.from_text_reasoning(protected_data=json.dumps(reasoning_details)))
        return ChatResponseUpdate(
            created_at=datetime.fromtimestamp(chunk.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            contents=contents,
            role="assistant",
            model=chunk.model,
            additional_properties=chunk_metadata,
            finish_reason=finish_reason,
            raw_representation=chunk,
            response_id=chunk.id,
            message_id=chunk.id,
        )

    def _parse_usage_from_openai(self, usage: CompletionUsage) -> UsageDetails:
        details = UsageDetails(
            input_token_count=usage.prompt_tokens,
            output_token_count=usage.completion_tokens,
            total_token_count=usage.total_tokens,
        )
        if usage.completion_tokens_details:
            if tokens := usage.completion_tokens_details.accepted_prediction_tokens:
                details["completion/accepted_prediction_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
            if tokens := usage.completion_tokens_details.audio_tokens:
                details["completion/audio_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
            if tokens := usage.completion_tokens_details.reasoning_tokens:
                details["completion/reasoning_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
            if tokens := usage.completion_tokens_details.rejected_prediction_tokens:
                details["completion/rejected_prediction_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
        if usage.prompt_tokens_details:
            if tokens := usage.prompt_tokens_details.audio_tokens:
                details["prompt/audio_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
            if tokens := usage.prompt_tokens_details.cached_tokens:
                details["prompt/cached_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
        return details

    def _parse_text_from_openai(self, choice: Choice | ChunkChoice) -> Content | None:
        """Parse the choice into a Content object with type='text'."""
        message = choice.message if isinstance(choice, Choice) else choice.delta
        if message.content:
            return Content.from_text(text=message.content, raw_representation=choice)
        if hasattr(message, "refusal") and message.refusal:
            return Content.from_text(text=message.refusal, raw_representation=choice)
        return None

    def _get_metadata_from_chat_response(self, response: ChatCompletion) -> dict[str, Any]:
        """Get metadata from a chat response."""
        return {
            "system_fingerprint": response.system_fingerprint,
        }

    def _get_metadata_from_streaming_chat_response(self, response: ChatCompletionChunk) -> dict[str, Any]:
        """Get metadata from a streaming chat response."""
        return {
            "system_fingerprint": response.system_fingerprint,
        }

    def _get_metadata_from_chat_choice(self, choice: Choice | ChunkChoice) -> dict[str, Any]:
        """Get metadata from a chat choice."""
        return {
            "logprobs": getattr(choice, "logprobs", None),
        }

    def _parse_tool_calls_from_openai(self, choice: Choice | ChunkChoice) -> list[Content]:
        """Parse tool calls from an OpenAI response choice."""
        resp: list[Content] = []
        content = choice.message if isinstance(choice, Choice) else choice.delta
        if content and content.tool_calls:
            for tool in content.tool_calls:
                if not isinstance(tool, ChatCompletionMessageCustomToolCall) and tool.function:
                    # ignoring tool.custom
                    fcc = Content.from_function_call(
                        call_id=tool.id if tool.id else "",
                        name=tool.function.name if tool.function.name else "",
                        arguments=tool.function.arguments if tool.function.arguments else "",
                        raw_representation=tool.function,
                    )
                    resp.append(fcc)

        # When you enable asynchronous content filtering in Azure OpenAI, you may receive empty deltas
        return resp

    def _prepare_messages_for_openai(
        self,
        chat_messages: Sequence[Message],
        role_key: str = "role",
        content_key: str = "content",
    ) -> list[dict[str, Any]]:
        """Prepare the chat history for an OpenAI request.

        Allowing customization of the key names for role/author, and optionally overriding the role.

        "tool" messages need to be formatted different than system/user/assistant messages:
            They require a "tool_call_id" and (function) "name" key, and the "metadata" key should
            be removed. The "encoding" key should also be removed.

        Override this method to customize the formatting of the chat history for a request.

        Args:
            chat_messages: The chat history to prepare.
            role_key: The key name for the role/author.
            content_key: The key name for the content/message.

        Returns:
            prepared_chat_history (Any): The prepared chat history for a request.
        """
        list_of_list = [self._prepare_message_for_openai(message) for message in chat_messages]
        # Flatten the list of lists into a single list
        return list(chain.from_iterable(list_of_list))

    # region Parsers

    def _prepare_message_for_openai(self, message: Message) -> list[dict[str, Any]]:
        """Prepare a chat message for OpenAI."""
        # System/developer messages must use plain string content because some
        # OpenAI-compatible endpoints reject list content for non-user roles.
        if message.role in ("system", "developer"):
            texts = [content.text for content in message.contents if content.type == "text" and content.text]
            if texts:
                sys_args: dict[str, Any] = {"role": message.role, "content": "\n".join(texts)}
                if message.author_name:
                    sys_args["name"] = message.author_name
                return [sys_args]
            return []

        all_messages: list[dict[str, Any]] = []
        pending_reasoning: Any = None
        for content in message.contents:
            # Skip approval content - it's internal framework state, not for the LLM
            if content.type in ("function_approval_request", "function_approval_response"):
                continue

            args: dict[str, Any] = {
                "role": message.role,
            }
            if message.author_name and message.role != "tool":
                args["name"] = message.author_name
            if "reasoning_details" in message.additional_properties and (
                details := message.additional_properties["reasoning_details"]
            ):
                args["reasoning_details"] = details
            match content.type:
                case "function_call":
                    if all_messages and "tool_calls" in all_messages[-1]:
                        # If the last message already has tool calls, append to it
                        all_messages[-1]["tool_calls"].append(self._prepare_content_for_openai(content))
                    else:
                        args["tool_calls"] = [self._prepare_content_for_openai(content)]  # type: ignore
                case "function_result":
                    args["tool_call_id"] = content.call_id
                    if content.items:
                        text_parts = [item.text or "" for item in content.items if item.type == "text"]
                        rich_items = [item for item in content.items if item.type in ("data", "uri")]
                        if rich_items:
                            logger.warning(
                                "OpenAI Chat Completions API does not support rich content (images, audio) "
                                "in tool results. Rich content items will be omitted. "
                                "Use the Responses API client for rich tool results."
                            )
                        args["content"] = "\n".join(text_parts) if text_parts else ""
                    else:
                        args["content"] = content.result if content.result is not None else ""
                    all_messages.append(args)
                    continue
                case "text_reasoning" if (protected_data := content.protected_data) is not None:
                    # Buffer reasoning to attach to the next message with content/tool_calls
                    pending_reasoning = json.loads(protected_data)
                case _:
                    if "content" not in args:
                        args["content"] = []
                    # this is a list to allow multi-modal content
                    args["content"].append(self._prepare_content_for_openai(content))  # type: ignore
            if "content" in args or "tool_calls" in args:
                if pending_reasoning is not None:
                    args["reasoning_details"] = pending_reasoning
                    pending_reasoning = None
                all_messages.append(args)

        # If reasoning was the only content, emit a valid message with empty content
        if pending_reasoning is not None:
            if all_messages:
                all_messages[-1]["reasoning_details"] = pending_reasoning
            else:
                pending_args: dict[str, Any] = {
                    "role": message.role,
                    "content": "",
                    "reasoning_details": pending_reasoning,
                }
                if message.author_name and message.role != "tool":
                    pending_args["name"] = message.author_name
                all_messages.append(pending_args)

        # Flatten text-only content lists to plain strings for broader
        # compatibility with OpenAI-like endpoints (e.g. Foundry Local).
        # See https://github.com/microsoft/agent-framework/issues/4084
        for msg in all_messages:
            msg_content: Any = msg.get("content")
            if isinstance(msg_content, list):
                typed_msg_content = cast(list[object], msg_content)
                text_items: list[Mapping[str, Any]] = []
                for item in typed_msg_content:
                    if not isinstance(item, Mapping):
                        break
                    text_item = cast(Mapping[str, Any], item)
                    if text_item.get("type") != "text":
                        break
                    text_items.append(text_item)
                else:
                    msg["content"] = "\n".join(
                        text_item.get("text", "") if isinstance(text_item.get("text", ""), str) else ""
                        for text_item in text_items
                    )

        return all_messages

    def _prepare_content_for_openai(self, content: Content) -> dict[str, Any]:
        """Prepare content for OpenAI."""
        match content.type:
            case "function_call":
                args = json.dumps(content.arguments) if isinstance(content.arguments, Mapping) else content.arguments
                return {
                    "id": content.call_id,
                    "type": "function",
                    "function": {"name": content.name, "arguments": args},
                }
            case "function_result":
                return {
                    "tool_call_id": content.call_id,
                    "content": content.result if content.result is not None else "",
                }
            case "data" | "uri" if content.has_top_level_media_type("image"):
                image_url_obj: dict[str, Any] = {"url": content.uri}
                detail = content.additional_properties.get("detail")
                if isinstance(detail, str):
                    image_url_obj["detail"] = detail
                return {
                    "type": "image_url",
                    "image_url": image_url_obj,
                }
            case "data" | "uri" if content.has_top_level_media_type("audio"):
                if content.media_type and "wav" in content.media_type:
                    audio_format = "wav"
                elif content.media_type and "mp3" in content.media_type:
                    audio_format = "mp3"
                else:
                    # Fallback to default to_dict for unsupported audio formats
                    return content.to_dict(exclude_none=True)

                # Extract base64 data from data URI
                audio_data = content.uri
                if audio_data.startswith("data:"):  # type: ignore[union-attr]
                    # Extract just the base64 part after "data:audio/format;base64,"
                    audio_data = audio_data.split(",", 1)[-1]  # type: ignore[union-attr]

                return {
                    "type": "input_audio",
                    "input_audio": {
                        "data": audio_data,
                        "format": audio_format,
                    },
                }
            case "data" | "uri" if content.has_top_level_media_type("application") and content.uri.startswith("data:"):  # type: ignore[union-attr]
                # All application/* media types should be treated as files for OpenAI
                filename = getattr(content, "filename", None) or (
                    content.additional_properties.get("filename")
                    if hasattr(content, "additional_properties") and content.additional_properties
                    else None
                )
                file_obj = {"file_data": content.uri}
                if filename:
                    file_obj["filename"] = filename
                return {
                    "type": "file",
                    "file": file_obj,
                }
            case _:
                # Default fallback for all other content types
                return content.to_dict(exclude_none=True)

    @override
    def service_url(self) -> str:
        """Get the URL of the service.

        Override this in the subclass to return the proper URL.
        If the service does not have a URL, return None.
        """
        return str(self.client.base_url) if self.client else "Unknown"


# region Public client


class OpenAIChatCompletionClient(  # type: ignore[misc]
    FunctionInvocationLayer[OpenAIChatCompletionOptionsT],
    ChatMiddlewareLayer[OpenAIChatCompletionOptionsT],
    ChatTelemetryLayer[OpenAIChatCompletionOptionsT],
    RawOpenAIChatCompletionClient[OpenAIChatCompletionOptionsT],
    Generic[OpenAIChatCompletionOptionsT],
):
    """OpenAI Chat completion class with middleware, telemetry, and function invocation support."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "openai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    @overload
    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
    ) -> None:
        """Initialize an OpenAI Chat completion client.

        Keyword Args:
            model: Model identifier to use for the request. When not provided, the constructor
                reads ``OPENAI_CHAT_MODEL`` and then ``OPENAI_MODEL``.
            api_key: API key. When not provided explicitly, the constructor reads
                ``OPENAI_API_KEY``. A callable API key is also supported.
            org_id: OpenAI organization ID. When not provided explicitly, the constructor reads
                ``OPENAI_ORG_ID``.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured OpenAI client.
            instruction_role: Role for instruction messages (for example ``"system"``).
            base_url: Base URL override. When not provided explicitly, the constructor reads
                ``OPENAI_BASE_URL``.
            env_file_path: Optional ``.env`` file that is checked before the process environment
                for ``OPENAI_*`` values.
            env_file_encoding: Encoding for the ``.env`` file.
            middleware: Optional sequence of ChatAndFunctionMiddlewareTypes to apply to requests.
            function_invocation_configuration: Optional configuration for function invocation support.
        """
        ...

    @overload
    def __init__(
        self,
        model: str | None = None,
        *,
        azure_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        api_version: str | None = None,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
    ) -> None:
        """Initialize an OpenAI Chat completion client.

        Keyword Args:
            model: Model identifier to use for the request. When not provided, the constructor
                reads ``AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`` and then
                ``AZURE_OPENAI_DEPLOYMENT_NAME``.
            azure_endpoint: Azure resource endpoint. When not provided explicitly, the constructor
                reads ``AZURE_OPENAI_ENDPOINT``.
            credential: Azure credential or token provider for Entra auth.
            api_version: Azure API version. When not provided explicitly, the constructor reads
                ``AZURE_OPENAI_API_VERSION`` and then uses the Chat Completions default.
            api_key: API key. For Azure this can be used instead of ``AZURE_OPENAI_API_KEY`` for key
                auth. A callable token provider is also accepted, but ``credential`` is the preferred
                Azure auth surface.
            base_url: Base URL override. When not provided explicitly, the constructor reads
                ``AZURE_OPENAI_BASE_URL``. Use this instead of ``azure_endpoint`` when you want
                to pass the full ``.../openai/v1`` base URL directly.
            default_headers: Additional HTTP headers.
            async_client: Pre-configured client. Passing ``AsyncAzureOpenAI`` keeps the client on
                Azure; passing ``AsyncOpenAI`` keeps the client on OpenAI and bypasses env lookup.
            instruction_role: Role for instruction messages (for example ``"system"``).
            env_file_path: Optional ``.env`` file that is checked before process environment
                variables for ``AZURE_OPENAI_*`` values.
            env_file_encoding: Encoding for the ``.env`` file.
            middleware: Optional sequence of ChatAndFunctionMiddlewareTypes to apply to requests.
            function_invocation_configuration: Optional configuration for function invocation support.
        """
        ...

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        base_url: str | None = None,
        azure_endpoint: str | None = None,
        api_version: str | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an OpenAI Chat completion client.

        Keyword Args:
            model: Model identifier to use for the request. When not provided, the constructor
                reads ``OPENAI_CHAT_MODEL`` and then ``OPENAI_MODEL`` for OpenAI routing,
                or ``AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`` and then
                ``AZURE_OPENAI_DEPLOYMENT_NAME`` for Azure routing.
            api_key: API key override. For OpenAI routing this maps to ``OPENAI_API_KEY``.
                For Azure routing this can be used instead of ``AZURE_OPENAI_API_KEY`` for key
                auth. A callable token provider is also accepted for backwards compatibility,
                but ``credential`` is the preferred Azure auth surface.
            credential: Azure credential or token provider for Azure OpenAI auth. Passing this
                is an explicit Azure signal, even when ``OPENAI_API_KEY`` is also configured.
                Credential objects require the optional ``azure-identity`` package.
            org_id: OpenAI organization ID. Used only for OpenAI routing and resolved from
                ``OPENAI_ORG_ID`` when not provided.
            default_headers: Default HTTP headers that are merged into each request.
            async_client: Pre-configured client. Passing ``AsyncAzureOpenAI`` keeps the client on
                Azure; passing ``AsyncOpenAI`` keeps the client on OpenAI and bypasses env lookup.
            instruction_role: Role to use for instruction messages (for example ``"system"``).
            base_url: Base URL override. For OpenAI routing this maps to ``OPENAI_BASE_URL``.
                For Azure routing this may be used instead of ``azure_endpoint`` when you want
                to pass the full ``.../openai/v1`` base URL directly.
            azure_endpoint: Azure resource endpoint. When not provided explicitly, Azure routing
                falls back to ``AZURE_OPENAI_ENDPOINT``.
            api_version: Azure API version to use once Azure routing is selected. When
                not provided explicitly, Azure routing falls back to
                ``AZURE_OPENAI_API_VERSION`` and then the Chat Completions default.
            middleware: Optional sequence of ChatAndFunctionMiddlewareTypes to apply to requests.
            function_invocation_configuration: Optional configuration for function invocation support.
            env_file_path: Optional ``.env`` file that is checked before process environment
                variables. The same file is used for both ``OPENAI_*`` and ``AZURE_OPENAI_*``
                lookups.
            env_file_encoding: Encoding for the ``.env`` file.

        Notes:
            Environment resolution and routing precedence are:

            1. Explicit Azure inputs (``azure_endpoint`` or ``credential``)
            2. Explicit OpenAI API key or ``OPENAI_API_KEY``
            3. Azure environment fallback

            OpenAI routing reads ``OPENAI_API_KEY``, ``OPENAI_CHAT_MODEL``,
            ``OPENAI_MODEL``, ``OPENAI_ORG_ID``, and ``OPENAI_BASE_URL``. Azure routing
            reads ``AZURE_OPENAI_ENDPOINT``, ``AZURE_OPENAI_BASE_URL``,
            ``AZURE_OPENAI_API_KEY``, ``AZURE_OPENAI_CHAT_DEPLOYMENT_NAME``,
            ``AZURE_OPENAI_DEPLOYMENT_NAME``, and ``AZURE_OPENAI_API_VERSION``.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIChatCompletionClient

                # Using environment variables
                # Set OPENAI_API_KEY=sk-...
                # Set OPENAI_MODEL=<model name>
                client = OpenAIChatCompletionClient()

                # Or passing parameters directly
                client = OpenAIChatCompletionClient(model="<model name>", api_key="sk-...")

                # Or loading from a .env file
                client = OpenAIChatCompletionClient(env_file_path="path/to/.env")

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework.openai import OpenAIChatCompletionOptions


                class MyOptions(OpenAIChatCompletionOptions, total=False):
                    my_custom_option: str


                client: OpenAIChatCompletionClient[MyOptions] = OpenAIChatCompletionClient(model="<model name>")
                response = await client.get_response("Hello", options={"my_custom_option": "value"})
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
            instruction_role=instruction_role,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
        )

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[ResponseModelBoundT],
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> Awaitable[ChatResponse[ResponseModelBoundT]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: OpenAIChatCompletionOptionsT | ChatOptions[None] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: OpenAIChatCompletionOptionsT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    @override
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: OpenAIChatCompletionOptionsT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Get a response from the OpenAI chat client with all standard layers enabled."""
        super_get_response = cast(
            "Callable[..., Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]]",
            super().get_response,  # type: ignore[misc]
        )
        effective_client_kwargs = dict(client_kwargs) if client_kwargs is not None else {}
        if middleware is not None:
            effective_client_kwargs["middleware"] = middleware
        return super_get_response(  # type: ignore[no-any-return]
            messages=messages,
            stream=stream,
            options=options,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=effective_client_kwargs,
        )


def _apply_openai_chat_completion_client_docstrings() -> None:
    """Align OpenAI chat completion client docstrings with the raw implementation."""
    apply_layered_docstring(RawOpenAIChatCompletionClient.get_response, BaseChatClient.get_response)
    apply_layered_docstring(
        OpenAIChatCompletionClient.get_response,
        RawOpenAIChatCompletionClient.get_response,
        extra_keyword_args={
            "middleware": """
                Optional per-call chat and function middleware.
                This is merged with any middleware configured on the client for the current request.
            """,
        },
    )


_apply_openai_chat_completion_client_docstrings()
