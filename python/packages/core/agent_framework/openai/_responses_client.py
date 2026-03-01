# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

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
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, NoReturn, TypedDict, cast

from openai import AsyncOpenAI, BadRequestError
from openai.types.responses.file_search_tool_param import FileSearchToolParam
from openai.types.responses.function_tool_param import FunctionToolParam
from openai.types.responses.parsed_response import (
    ParsedResponse,
)
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_stream_event import (
    ResponseStreamEvent as OpenAIResponseStreamEvent,
)
from openai.types.responses.response_usage import ResponseUsage
from openai.types.responses.tool_param import (
    CodeInterpreter,
    CodeInterpreterContainerCodeInterpreterToolAuto,
    ImageGeneration,
    Mcp,
)
from openai.types.responses.web_search_tool_param import WebSearchToolParam
from pydantic import BaseModel

from .._clients import BaseChatClient
from .._middleware import ChatMiddlewareLayer
from .._settings import load_settings
from .._tools import (
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    FunctionTool,
    ToolTypes,
    normalize_tools,
)
from .._types import (
    Annotation,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    ContinuationToken,
    Message,
    ResponseStream,
    Role,
    TextSpanRegion,
    UsageDetails,
    detect_media_type_from_base64,
    prepend_instructions_to_messages,
    validate_tool_mode,
)
from ..exceptions import (
    ChatClientException,
    ChatClientInvalidRequestException,
)
from ..observability import ChatTelemetryLayer
from ._exceptions import OpenAIContentFilterException
from ._shared import OpenAIBase, OpenAIConfigMixin, OpenAISettings

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from .._middleware import (
        ChatMiddleware,
        ChatMiddlewareCallable,
        FunctionMiddleware,
        FunctionMiddlewareCallable,
    )

logger = logging.getLogger("agent_framework.openai")


class OpenAIContinuationToken(ContinuationToken):
    """Continuation token for OpenAI Responses API background operations."""

    response_id: str
    """OpenAI Responses API response ID."""


# region OpenAI Responses Options TypedDict


class ReasoningOptions(TypedDict, total=False):
    """Configuration options for reasoning models (gpt-5, o-series).

    See: https://platform.openai.com/docs/guides/reasoning
    """

    effort: Literal["low", "medium", "high"]
    """The effort level for reasoning. Higher effort means more reasoning tokens."""

    summary: Literal["auto", "concise", "detailed"]
    """How to summarize reasoning in the response."""


class StreamOptions(TypedDict, total=False):
    """Options for streaming responses."""

    include_usage: bool
    """Whether to include usage statistics in stream events."""


ResponseFormatT = TypeVar("ResponseFormatT", bound=BaseModel | None, default=None)


class OpenAIResponsesOptions(ChatOptions[ResponseFormatT], Generic[ResponseFormatT], total=False):
    """OpenAI Responses API-specific chat options.

    Extends ChatOptions with options specific to OpenAI's Responses API.
    These options provide fine-grained control over response generation,
    reasoning, and API behavior.

    See: https://platform.openai.com/docs/api-reference/responses/create
    """

    # Responses API-specific parameters

    include: list[str]
    """Additional output data to include in the response.
    Supported values include:
    - 'web_search_call.action.sources'
    - 'code_interpreter_call.outputs'
    - 'file_search_call.results'
    - 'message.input_image.image_url'
    - 'message.output_text.logprobs'
    - 'reasoning.encrypted_content'
    """

    max_tool_calls: int
    """Maximum number of total calls to built-in tools in a response."""

    prompt: dict[str, Any]
    """Reference to a prompt template and its variables.
    Learn more: https://platform.openai.com/docs/guides/text#reusable-prompts"""

    prompt_cache_key: str
    """Used by OpenAI to cache responses for similar requests.
    Replaces the deprecated 'user' field for caching purposes."""

    prompt_cache_retention: Literal["24h"]
    """Retention policy for prompt cache. Set to '24h' for extended caching."""

    reasoning: ReasoningOptions
    """Configuration for reasoning models (gpt-5, o-series).
    See: https://platform.openai.com/docs/guides/reasoning"""

    safety_identifier: str
    """A stable identifier for detecting policy violations.
    Recommend hashing username/email to avoid sending identifying info."""

    service_tier: Literal["auto", "default", "flex", "priority"]
    """Processing type for serving the request.
    - 'auto': Use project settings
    - 'default': Standard pricing/performance
    - 'flex': Flexible processing
    - 'priority': Priority processing"""

    stream_options: StreamOptions
    """Options for streaming responses. Only set when stream=True."""

    top_logprobs: int
    """Number of most likely tokens (0-20) to return at each position."""

    truncation: Literal["auto", "disabled"]
    """Truncation strategy for model response.
    - 'auto': Truncate from beginning if exceeds context
    - 'disabled': Fail with 400 error if exceeds context"""

    background: bool
    """Whether to run the model response in the background.
    When True, the response returns immediately with a continuation token
    that can be used to poll for the result.
    See: https://platform.openai.com/docs/guides/background"""

    continuation_token: OpenAIContinuationToken
    """Token for resuming or polling a long-running background operation.
    Pass the ``continuation_token`` from a previous response to poll for
    completion or resume a streaming response."""


OpenAIResponsesOptionsT = TypeVar(
    "OpenAIResponsesOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIResponsesOptions",
    covariant=True,
)


# endregion


# region ResponsesClient


class RawOpenAIResponsesClient(  # type: ignore[misc]
    OpenAIBase,
    BaseChatClient[OpenAIResponsesOptionsT],
    Generic[OpenAIResponsesOptionsT],
):
    """Raw OpenAI Responses client without middleware, telemetry, or function invocation.

    Warning:
        **This class should not normally be used directly.** It does not include middleware,
        telemetry, or function invocation support that you most likely need. If you do use it,
        you should consider which additional layers to apply. There is a defined ordering that
        you should follow:

        1. **ChatMiddlewareLayer** - Should be applied first as it also prepares function middleware
        2. **FunctionInvocationLayer** - Handles tool/function calling loop
        3. **ChatTelemetryLayer** - Must be inside the function calling loop for correct per-call telemetry

        Use ``OpenAIResponsesClient`` instead for a fully-featured client with all layers applied.
    """

    STORES_BY_DEFAULT: ClassVar[bool] = True  # type: ignore[reportIncompatibleVariableOverride, misc]

    FILE_SEARCH_MAX_RESULTS: int = 50

    # region Inner Methods

    async def _prepare_request(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> tuple[AsyncOpenAI, dict[str, Any], dict[str, Any]]:
        """Validate options and prepare the request.

        Returns:
            Tuple of (client, run_options, validated_options).
        """
        client = await self._ensure_client()
        validated_options = await self._validate_options(options)
        run_options = await self._prepare_options(messages, validated_options, **kwargs)
        return client, run_options, validated_options

    def _handle_request_error(self, ex: Exception) -> NoReturn:
        """Convert exceptions to appropriate service exceptions. Always raises."""
        if isinstance(ex, BadRequestError) and ex.code == "content_filter":
            raise OpenAIContentFilterException(
                f"{type(self)} service encountered a content error: {ex}",
                inner_exception=ex,
            ) from ex
        raise ChatClientException(
            f"{type(self)} service failed to complete the prompt: {ex}",
            inner_exception=ex,
        ) from ex

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        continuation_token: OpenAIContinuationToken | None = options.get("continuation_token")  # type: ignore[assignment]

        if stream:
            function_call_ids: dict[int, tuple[str, str]] = {}
            validated_options: dict[str, Any] | None = None

            async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                nonlocal validated_options
                if continuation_token is not None:
                    # Resume a background streaming response by retrieving with stream=True
                    client = await self._ensure_client()
                    validated_options = await self._validate_options(options)
                    try:
                        stream_response = await client.responses.retrieve(
                            continuation_token["response_id"],
                            stream=True,
                        )
                        async for chunk in stream_response:
                            yield self._parse_chunk_from_openai(
                                chunk, options=validated_options, function_call_ids=function_call_ids
                            )
                    except Exception as ex:
                        self._handle_request_error(ex)
                else:
                    client, run_options, validated_options = await self._prepare_request(messages, options, **kwargs)
                    try:
                        if "text_format" in run_options:
                            async with client.responses.stream(**run_options) as response:
                                async for chunk in response:
                                    yield self._parse_chunk_from_openai(
                                        chunk, options=validated_options, function_call_ids=function_call_ids
                                    )
                        else:
                            async for chunk in await client.responses.create(stream=True, **run_options):
                                yield self._parse_chunk_from_openai(
                                    chunk, options=validated_options, function_call_ids=function_call_ids
                                )
                    except Exception as ex:
                        self._handle_request_error(ex)

            response_format = validated_options.get("response_format") if validated_options else None
            return self._build_response_stream(_stream(), response_format=response_format)

        # Non-streaming
        async def _get_response() -> ChatResponse:
            if continuation_token is not None:
                # Poll a background response by retrieving without stream
                client = await self._ensure_client()
                validated_options = await self._validate_options(options)
                try:
                    response = await client.responses.retrieve(continuation_token["response_id"])
                except Exception as ex:
                    self._handle_request_error(ex)
                return self._parse_response_from_openai(response, options=validated_options)
            client, run_options, validated_options = await self._prepare_request(messages, options, **kwargs)
            try:
                if "text_format" in run_options:
                    response = await client.responses.parse(stream=False, **run_options)
                else:
                    response = await client.responses.create(stream=False, **run_options)
            except Exception as ex:
                self._handle_request_error(ex)
            return self._parse_response_from_openai(response, options=validated_options)

        return _get_response()

    def _prepare_response_and_text_format(
        self,
        *,
        response_format: Any,
        text_config: MutableMapping[str, Any] | None,
    ) -> tuple[type[BaseModel] | None, dict[str, Any] | None]:
        """Normalize response_format into Responses text configuration and parse target."""
        if text_config is not None and not isinstance(text_config, MutableMapping):
            raise ChatClientInvalidRequestException("text must be a mapping when provided.")
        text_config = cast(dict[str, Any], text_config) if isinstance(text_config, MutableMapping) else None

        if response_format is None:
            return None, text_config

        if isinstance(response_format, type) and issubclass(response_format, BaseModel):
            if text_config and "format" in text_config:
                raise ChatClientInvalidRequestException("response_format cannot be combined with explicit text.format.")
            return response_format, text_config

        if isinstance(response_format, Mapping):
            format_config = self._convert_response_format(cast("Mapping[str, Any]", response_format))
            if text_config is None:
                text_config = {}
            elif "format" in text_config and text_config["format"] != format_config:
                raise ChatClientInvalidRequestException("Conflicting response_format definitions detected.")
            text_config["format"] = format_config
            return None, text_config

        raise ChatClientInvalidRequestException("response_format must be a Pydantic model or mapping.")

    def _convert_response_format(self, response_format: Mapping[str, Any]) -> dict[str, Any]:
        """Convert Chat style response_format into Responses text format config."""
        if "format" in response_format and isinstance(response_format["format"], Mapping):
            return dict(cast("Mapping[str, Any]", response_format["format"]))

        format_type = response_format.get("type")
        if format_type == "json_schema":
            schema_section = response_format.get("json_schema", response_format)
            if not isinstance(schema_section, Mapping):
                raise ChatClientInvalidRequestException("json_schema response_format must be a mapping.")
            schema_section_typed = cast("Mapping[str, Any]", schema_section)
            schema: Any = schema_section_typed.get("schema")
            if schema is None:
                raise ChatClientInvalidRequestException("json_schema response_format requires a schema.")
            name: str = str(
                schema_section_typed.get("name")
                or schema_section_typed.get("title")
                or (cast("Mapping[str, Any]", schema).get("title") if isinstance(schema, Mapping) else None)
                or "response"
            )
            format_config: dict[str, Any] = {
                "type": "json_schema",
                "name": name,
                "schema": schema,
            }
            if "strict" in schema_section:
                format_config["strict"] = schema_section["strict"]
            if "description" in schema_section and schema_section["description"] is not None:
                format_config["description"] = schema_section["description"]
            return format_config

        if format_type in {"json_object", "text"}:
            return {"type": format_type}

        raise ChatClientInvalidRequestException("Unsupported response_format provided for Responses client.")

    def _get_conversation_id(
        self, response: OpenAIResponse | ParsedResponse[BaseModel], store: bool | None
    ) -> str | None:
        """Get the conversation ID from the response if store is True."""
        if store is False:
            return None
        # If conversation ID exists, it means that we operate with conversation
        # so we use conversation ID as input and output.
        if response.conversation and response.conversation.id:
            return response.conversation.id
        # If conversation ID doesn't exist, we operate with responses
        # so we use response ID as input and output.
        return response.id

    # region Prep methods

    def _prepare_tools_for_openai(
        self, tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None
    ) -> list[Any]:
        """Prepare tools for the OpenAI Responses API.

        Converts FunctionTool to Responses API format. All other tools pass through unchanged.

        Args:
            tools: A single tool or sequence of tools to prepare.

        Returns:
            List of tool parameters ready for the OpenAI API.
        """
        tools_list = normalize_tools(tools)
        if not tools_list:
            return []
        response_tools: list[Any] = []
        for tool in tools_list:
            if isinstance(tool, FunctionTool):
                params = tool.parameters()
                params["additionalProperties"] = False
                response_tools.append(
                    FunctionToolParam(
                        name=tool.name,
                        parameters=params,
                        strict=False,
                        type="function",
                        description=tool.description,
                    )
                )
            else:
                # Pass through all other tools (dicts, SDK types) unchanged
                response_tools.append(tool)
        return response_tools

    # region Hosted Tool Factory Methods

    @staticmethod
    def get_code_interpreter_tool(
        *,
        file_ids: list[str] | None = None,
        container: Literal["auto"] | CodeInterpreterContainerCodeInterpreterToolAuto = "auto",
    ) -> Any:
        """Create a code interpreter tool configuration for the Responses API.

        Keyword Args:
            file_ids: List of file IDs to make available to the code interpreter.
            container: Container configuration. Use "auto" for automatic container management,
                or provide a TypedDict with custom container settings.

        Returns:
            A CodeInterpreter tool parameter ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient

                # Basic code interpreter
                tool = OpenAIResponsesClient.get_code_interpreter_tool()

                # With file access
                tool = OpenAIResponsesClient.get_code_interpreter_tool(file_ids=["file-abc123"])

                # Use with agent
                agent = ChatAgent(client, tools=[tool])
        """
        container_config: CodeInterpreterContainerCodeInterpreterToolAuto = (
            container if isinstance(container, dict) else {"type": "auto"}
        )

        if file_ids:
            container_config["file_ids"] = file_ids

        return CodeInterpreter(type="code_interpreter", container=container_config)

    @staticmethod
    def get_web_search_tool(
        *,
        user_location: dict[str, str] | None = None,
        search_context_size: Literal["low", "medium", "high"] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> Any:
        """Create a web search tool configuration for the Responses API.

        Keyword Args:
            user_location: Location context for search results. Dict with keys like
                "city", "country", "region", "timezone".
            search_context_size: Amount of context to include from search results.
                One of "low", "medium", or "high".
            filters: Additional search filters.

        Returns:
            A WebSearchToolParam dict ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient

                # Basic web search
                tool = OpenAIResponsesClient.get_web_search_tool()

                # With location context
                tool = OpenAIResponsesClient.get_web_search_tool(
                    user_location={"city": "Seattle", "country": "US"},
                    search_context_size="medium",
                )

                agent = ChatAgent(client, tools=[tool])
        """
        web_search_tool = WebSearchToolParam(type="web_search")

        if user_location:
            web_search_tool["user_location"] = {
                "type": "approximate",
                "city": user_location.get("city"),
                "country": user_location.get("country"),
                "region": user_location.get("region"),
                "timezone": user_location.get("timezone"),
            }

        if search_context_size:
            web_search_tool["search_context_size"] = search_context_size

        if filters:
            web_search_tool["filters"] = filters  # type: ignore[typeddict-item]

        return web_search_tool

    @staticmethod
    def get_image_generation_tool(
        *,
        size: Literal["1024x1024", "1024x1536", "1536x1024", "auto"] | None = None,
        output_format: Literal["png", "jpeg", "webp"] | None = None,
        model: Literal["gpt-image-1", "gpt-image-1-mini"] | str | None = None,
        quality: Literal["low", "medium", "high", "auto"] | None = None,
        partial_images: int | None = None,
        background: Literal["transparent", "opaque", "auto"] | None = None,
        moderation: Literal["auto", "low"] | None = None,
        output_compression: int | None = None,
    ) -> Any:
        """Create an image generation tool configuration for the Responses API.

        Keyword Args:
            size: Image dimensions. One of "1024x1024", "1024x1536", "1536x1024", or "auto".
            output_format: Output image format. One of "png", "jpeg", or "webp".
            model: Model to use for image generation. One of "gpt-image-1" or "gpt-image-1-mini".
            quality: Image quality level. One of "low", "medium", "high", or "auto".
            partial_images: Number of partial images to stream during generation.
            background: Background type. One of "transparent", "opaque", or "auto".
            moderation: Moderation level. One of "auto" or "low".
            output_compression: Compression level for output (0-100).

        Returns:
            An ImageGeneration tool parameter dict ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient

                # Basic image generation
                tool = OpenAIResponsesClient.get_image_generation_tool()

                # High quality large image
                tool = OpenAIResponsesClient.get_image_generation_tool(
                    size="1536x1024",
                    quality="high",
                    output_format="png",
                )

                agent = ChatAgent(client, tools=[tool])
        """
        tool: ImageGeneration = {"type": "image_generation"}

        if size:
            tool["size"] = size
        if output_format:
            tool["output_format"] = output_format
        if model:
            tool["model"] = model
        if quality:
            tool["quality"] = quality
        if partial_images is not None:
            tool["partial_images"] = partial_images
        if background:
            tool["background"] = background
        if moderation:
            tool["moderation"] = moderation
        if output_compression is not None:
            tool["output_compression"] = output_compression

        return tool

    @staticmethod
    def get_mcp_tool(
        *,
        name: str,
        url: str,
        description: str | None = None,
        approval_mode: Literal["always_require", "never_require"] | dict[str, list[str]] | None = None,
        allowed_tools: list[str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Create a hosted MCP (Model Context Protocol) tool configuration for the Responses API.

        This configures an MCP server that will be called by OpenAI's service.
        The tools from this MCP server are executed remotely by OpenAI,
        not locally by your application.

        Note:
            For local MCP execution where your application calls the MCP server
            directly, use the MCP client tools instead of this method.

        Keyword Args:
            name: A label/name for the MCP server.
            url: The URL of the MCP server.
            description: A description of what the MCP server provides.
            approval_mode: Tool approval mode. Use "always_require" or "never_require" for all tools,
                or provide a dict with "always_require_approval" and/or "never_require_approval"
                keys mapping to lists of tool names.
            allowed_tools: List of tool names that are allowed to be used from this MCP server.
            headers: HTTP headers to include in requests to the MCP server.

        Returns:
            An Mcp tool parameter dict ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient

                # Basic MCP tool
                tool = OpenAIResponsesClient.get_mcp_tool(
                    name="my_mcp",
                    url="https://mcp.example.com",
                )

                # With approval settings
                tool = OpenAIResponsesClient.get_mcp_tool(
                    name="github_mcp",
                    url="https://mcp.github.com",
                    description="GitHub MCP server",
                    approval_mode="always_require",
                    headers={"Authorization": "Bearer token"},
                )

                # With specific tool approvals
                tool = OpenAIResponsesClient.get_mcp_tool(
                    name="tools_mcp",
                    url="https://tools.example.com",
                    approval_mode={
                        "always_require_approval": ["dangerous_tool"],
                        "never_require_approval": ["safe_tool"],
                    },
                )

                agent = ChatAgent(client, tools=[tool])
        """
        mcp: Mcp = {
            "type": "mcp",
            "server_label": name.replace(" ", "_"),
            "server_url": url,
        }

        if description:
            mcp["server_description"] = description

        if headers:
            mcp["headers"] = headers

        if allowed_tools:
            mcp["allowed_tools"] = allowed_tools

        if approval_mode:
            if isinstance(approval_mode, str):
                mcp["require_approval"] = "always" if approval_mode == "always_require" else "never"
            else:
                if always_require := approval_mode.get("always_require_approval"):
                    mcp["require_approval"] = {"always": {"tool_names": always_require}}
                if never_require := approval_mode.get("never_require_approval"):
                    mcp["require_approval"] = {"never": {"tool_names": never_require}}

        return mcp

    @staticmethod
    def get_file_search_tool(
        *,
        vector_store_ids: list[str],
        max_num_results: int | None = None,
    ) -> Any:
        """Create a file search tool configuration for the Responses API.

        Keyword Args:
            vector_store_ids: List of vector store IDs to search within.
            max_num_results: Maximum number of results to return. Defaults to 50 if not specified.

        Returns:
            A FileSearchToolParam dict ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient

                # Basic file search
                tool = OpenAIResponsesClient.get_file_search_tool(
                    vector_store_ids=["vs_abc123"],
                )

                # With result limit
                tool = OpenAIResponsesClient.get_file_search_tool(
                    vector_store_ids=["vs_abc123", "vs_def456"],
                    max_num_results=10,
                )

                agent = ChatAgent(client, tools=[tool])
        """
        tool = FileSearchToolParam(
            type="file_search",
            vector_store_ids=vector_store_ids,
        )

        if max_num_results is not None:
            tool["max_num_results"] = max_num_results

        return tool

    # endregion

    async def _prepare_options(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Take options dict and create the specific options for Responses API."""
        # Exclude keys that are not supported or handled separately
        exclude_keys = {
            "type",
            "presence_penalty",  # not supported
            "frequency_penalty",  # not supported
            "logit_bias",  # not supported
            "seed",  # not supported
            "stop",  # not supported
            "instructions",  # already added as system message
            "response_format",  # handled separately
            "conversation_id",  # handled separately
            "tool_choice",  # handled separately
            "continuation_token",  # handled separately in _inner_get_response
        }
        run_options: dict[str, Any] = {k: v for k, v in options.items() if k not in exclude_keys and v is not None}

        # messages
        # Handle instructions by prepending to messages as system message
        # Only prepend instructions for the first turn (when no conversation/response ID exists)
        conversation_id = self._get_current_conversation_id(options, **kwargs)
        if (instructions := options.get("instructions")) and not conversation_id:
            # First turn: prepend instructions as system message
            messages = prepend_instructions_to_messages(list(messages), instructions, role="system")
        # Continuation turn: instructions already exist in conversation context, skip prepending
        request_input = self._prepare_messages_for_openai(messages)
        if not request_input:
            raise ChatClientInvalidRequestException("Messages are required for chat completions")
        conversation_id = self._get_current_conversation_id(options, **kwargs)
        run_options["input"] = request_input

        # model id
        self._check_model_presence(run_options)

        # translations between options and Responses API
        translations = {
            "model_id": "model",
            "allow_multiple_tool_calls": "parallel_tool_calls",
            "conversation_id": "previous_response_id",
            "max_tokens": "max_output_tokens",
        }
        for old_key, new_key in translations.items():
            if old_key in run_options and old_key != new_key:
                run_options[new_key] = run_options.pop(old_key)

        # Handle different conversation ID formats
        if conversation_id := self._get_current_conversation_id(options, **kwargs):
            if conversation_id.startswith("resp_"):
                # For response IDs, set previous_response_id and remove conversation property
                run_options["previous_response_id"] = conversation_id
            elif conversation_id.startswith("conv_"):
                # For conversation IDs, set conversation and remove previous_response_id property
                run_options["conversation"] = conversation_id
            else:
                # If the format is unrecognized, default to previous_response_id
                run_options["previous_response_id"] = conversation_id

        # tools
        if tools := self._prepare_tools_for_openai(options.get("tools")):
            run_options["tools"] = tools
            # tool_choice: convert ToolMode to appropriate format
            if tool_choice := options.get("tool_choice"):
                tool_mode = validate_tool_mode(tool_choice)
                if tool_mode is not None:
                    if (mode := tool_mode.get("mode")) == "required" and (
                        func_name := tool_mode.get("required_function_name")
                    ) is not None:
                        run_options["tool_choice"] = {
                            "type": "function",
                            "name": func_name,
                        }
                    else:
                        run_options["tool_choice"] = mode
        else:
            run_options.pop("parallel_tool_calls", None)
            run_options.pop("tool_choice", None)

        # response format and text config
        response_format = options.get("response_format")
        text_config = run_options.pop("text", None)
        response_format, text_config = self._prepare_response_and_text_format(
            response_format=response_format, text_config=text_config
        )
        if text_config:
            run_options["text"] = text_config
        if response_format:
            run_options["text_format"] = response_format

        return run_options

    def _check_model_presence(self, options: dict[str, Any]) -> None:
        """Check if the 'model' param is present, and if not raise a Error.

        Since AzureAIClients use a different param for this, this method is overridden in those clients.
        """
        if not options.get("model"):
            if not self.model_id:
                raise ValueError("model_id must be a non-empty string")
            options["model"] = self.model_id

    def _get_current_conversation_id(self, options: Mapping[str, Any], **kwargs: Any) -> str | None:
        """Get the current conversation ID, preferring kwargs over options.

        This ensures runtime-updated conversation IDs (for example, from tool execution
        loops) take precedence over the initial configuration provided in options.
        """
        return kwargs.get("conversation_id") or options.get("conversation_id")

    def _prepare_messages_for_openai(self, chat_messages: Sequence[Message]) -> list[dict[str, Any]]:
        """Prepare the chat messages for a request.

        Allowing customization of the key names for role/author, and optionally overriding the role.

        "tool" messages need to be formatted different than system/user/assistant messages:
            They require a "tool_call_id" and (function) "name" key, and the "metadata" key should
            be removed. The "encoding" key should also be removed.

        Override this method to customize the formatting of the chat history for a request.

        Args:
            chat_messages: The chat history to prepare.

        Returns:
            The prepared chat messages for a request.
        """
        call_id_to_id: dict[str, str] = {}
        for message in chat_messages:
            for content in message.contents:
                if (
                    content.type == "function_call"
                    and content.additional_properties
                    and "fc_id" in content.additional_properties
                ):
                    call_id_to_id[content.call_id] = content.additional_properties["fc_id"]  # type: ignore[attr-defined, index]
        list_of_list = [self._prepare_message_for_openai(message, call_id_to_id) for message in chat_messages]
        # Flatten the list of lists into a single list
        return list(chain.from_iterable(list_of_list))

    def _prepare_message_for_openai(
        self,
        message: Message,
        call_id_to_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Prepare a chat message for the OpenAI Responses API format."""
        all_messages: list[dict[str, Any]] = []
        args: dict[str, Any] = {
            "type": "message",
            "role": message.role,
        }
        # Reasoning items are only valid in input when they directly preceded a function_call
        # in the same response.  Including a reasoning item that preceded a text response
        # (i.e. no function_call in the same message) causes an API error:
        # "reasoning was provided without its required following item."
        has_function_call = any(c.type == "function_call" for c in message.contents)
        for content in message.contents:
            match content.type:
                case "text_reasoning":
                    if not has_function_call:
                        continue  # reasoning not followed by a function_call is invalid in input
                    reasoning = self._prepare_content_for_openai(message.role, content, call_id_to_id)  # type: ignore[arg-type]
                    if reasoning:
                        all_messages.append(reasoning)
                case "function_result":
                    new_args: dict[str, Any] = {}
                    new_args.update(self._prepare_content_for_openai(message.role, content, call_id_to_id))  # type: ignore[arg-type]
                    if new_args:
                        all_messages.append(new_args)
                case "function_call":
                    function_call = self._prepare_content_for_openai(message.role, content, call_id_to_id)  # type: ignore[arg-type]
                    if function_call:
                        all_messages.append(function_call)  # type: ignore
                case "function_approval_response" | "function_approval_request":
                    prepared = self._prepare_content_for_openai(Role(message.role), content, call_id_to_id)
                    if prepared:
                        all_messages.append(prepared)  # type: ignore
                case _:
                    prepared_content = self._prepare_content_for_openai(message.role, content, call_id_to_id)  # type: ignore
                    if prepared_content:
                        if "content" not in args:
                            args["content"] = []
                        args["content"].append(prepared_content)  # type: ignore
        if "content" in args or "tool_calls" in args:
            all_messages.append(args)
        return all_messages

    def _prepare_content_for_openai(
        self,
        role: Role,
        content: Content,
        call_id_to_id: dict[str, str],
    ) -> dict[str, Any]:
        """Prepare content for the OpenAI Responses API format."""
        match content.type:
            case "text":
                if role == "assistant":
                    # Assistant history is represented as output text items; Azure validation
                    # requires `annotations` to be present for this type.
                    return {
                        "type": "output_text",
                        "text": content.text,
                        "annotations": [],
                    }
                return {
                    "type": "input_text",
                    "text": content.text,
                }
            case "text_reasoning":
                ret: dict[str, Any] = {"type": "reasoning", "summary": []}
                if content.id:
                    ret["id"] = content.id
                props: dict[str, Any] | None = getattr(content, "additional_properties", None)
                if props:
                    if status := props.get("status"):
                        ret["status"] = status
                    if reasoning_text := props.get("reasoning_text"):
                        ret["content"] = [{"type": "reasoning_text", "text": reasoning_text}]
                    if encrypted_content := props.get("encrypted_content"):
                        ret["encrypted_content"] = encrypted_content
                if content.text:
                    ret["summary"].append({"type": "summary_text", "text": content.text})
                return ret
            case "data" | "uri":
                if content.has_top_level_media_type("image"):
                    return {
                        "type": "input_image",
                        "image_url": content.uri,
                        "detail": content.additional_properties.get("detail", "auto")
                        if content.additional_properties
                        else "auto",
                        "file_id": content.additional_properties.get("file_id", None)
                        if content.additional_properties
                        else None,
                    }
                if content.has_top_level_media_type("audio"):
                    if content.media_type and "wav" in content.media_type:
                        format = "wav"
                    elif content.media_type and "mp3" in content.media_type:
                        format = "mp3"
                    else:
                        logger.warning("Unsupported audio media type: %s", content.media_type)
                        return {}
                    return {
                        "type": "input_audio",
                        "input_audio": {
                            "data": content.uri,
                            "format": format,
                        },
                    }
                if content.has_top_level_media_type("application"):
                    filename = getattr(content, "filename", None) or (
                        content.additional_properties.get("filename")
                        if hasattr(content, "additional_properties") and content.additional_properties
                        else None
                    )
                    file_obj = {
                        "type": "input_file",
                        "file_data": content.uri,
                    }
                    if filename:
                        file_obj["filename"] = filename
                    return file_obj
                return {}
            case "function_call":
                if not content.call_id:
                    logger.warning(f"FunctionCallContent missing call_id for function '{content.name}'")
                    return {}
                # Use fc_id from additional_properties if available, otherwise fallback to call_id
                fc_id = call_id_to_id.get(content.call_id, content.call_id)
                # OpenAI Responses API requires IDs to start with `fc_`
                if not fc_id.startswith("fc_"):
                    fc_id = f"fc_{fc_id}"
                return {
                    "call_id": content.call_id,
                    "id": fc_id,
                    "type": "function_call",
                    "name": content.name,
                    "arguments": content.arguments,
                    "status": None,
                }
            case "function_result":
                # call_id for the result needs to be the same as the call_id for the function call
                args: dict[str, Any] = {
                    "call_id": content.call_id,
                    "type": "function_call_output",
                    "output": content.result if content.result is not None else "",
                }
                return args
            case "function_approval_request":
                return {
                    "type": "mcp_approval_request",
                    "id": content.id,  # type: ignore[union-attr]
                    "arguments": content.function_call.arguments,  # type: ignore[union-attr]
                    "name": content.function_call.name,  # type: ignore[union-attr]
                    "server_label": content.function_call.additional_properties.get("server_label")  # type: ignore[union-attr]
                    if content.function_call.additional_properties  # type: ignore[union-attr]
                    else None,
                }
            case "function_approval_response":
                return {
                    "type": "mcp_approval_response",
                    "approval_request_id": content.id,
                    "approve": content.approved,
                }
            case "hosted_file":
                return {
                    "type": "input_file",
                    "file_id": content.file_id,
                }
            case _:  # should catch UsageDetails and ErrorContent and HostedVectorStoreContent
                logger.debug("Unsupported content type passed (type: %s)", content.type)
                return {}

    # region Parse methods
    def _parse_response_from_openai(
        self,
        response: OpenAIResponse | ParsedResponse[BaseModel],
        options: dict[str, Any],
    ) -> ChatResponse:
        """Parse an OpenAI Responses API response into a ChatResponse."""
        structured_response: BaseModel | None = response.output_parsed if isinstance(response, ParsedResponse) else None  # type: ignore[reportUnknownMemberType]

        metadata: dict[str, Any] = response.metadata or {}
        contents: list[Content] = []
        for item in response.output:  # type: ignore[reportUnknownMemberType]
            match item.type:
                # types:
                # ParsedResponseOutputMessage[Unknown] |
                # ParsedResponseFunctionToolCall |
                # ResponseFileSearchToolCall |
                # ResponseFunctionWebSearch |
                # ResponseComputerToolCall |
                # ResponseReasoningItem |
                # MCPCall |
                # MCPApprovalRequest |
                # ImageGenerationCall |
                # LocalShellCall |
                # LocalShellCallAction |
                # MCPListTools |
                # ResponseCodeInterpreterToolCall |
                # ResponseCustomToolCall |
                # ParsedResponseOutputMessage[BaseModel] |
                # ResponseOutputMessage |
                # ResponseFunctionToolCall
                case "message":  # ResponseOutputMessage
                    for message_content in item.content:  # type: ignore[reportMissingTypeArgument]
                        match message_content.type:
                            case "output_text":
                                text_content = Content.from_text(
                                    text=message_content.text,
                                    raw_representation=message_content,  # type: ignore[reportUnknownArgumentType]
                                )
                                metadata.update(self._get_metadata_from_response(message_content))
                                if message_content.annotations:
                                    text_content.annotations = []
                                    for annotation in message_content.annotations:
                                        match annotation.type:
                                            case "file_path":
                                                text_content.annotations.append(  # pyright: ignore[reportUnknownMemberType]
                                                    Annotation(
                                                        type="citation",
                                                        file_id=annotation.file_id,
                                                        additional_properties={
                                                            "index": annotation.index,
                                                        },
                                                        raw_representation=annotation,
                                                    )
                                                )
                                            case "file_citation":
                                                text_content.annotations.append(  # pyright: ignore[reportUnknownMemberType]
                                                    Annotation(
                                                        type="citation",
                                                        url=annotation.filename,
                                                        file_id=annotation.file_id,
                                                        raw_representation=annotation,
                                                        additional_properties={
                                                            "index": annotation.index,
                                                        },
                                                    )
                                                )
                                            case "url_citation":
                                                text_content.annotations.append(  # pyright: ignore[reportUnknownMemberType]
                                                    Annotation(
                                                        type="citation",
                                                        title=annotation.title,
                                                        url=annotation.url,
                                                        annotated_regions=[
                                                            TextSpanRegion(
                                                                type="text_span",
                                                                start_index=annotation.start_index,
                                                                end_index=annotation.end_index,
                                                            )
                                                        ],
                                                        raw_representation=annotation,
                                                    )
                                                )
                                            case "container_file_citation":
                                                text_content.annotations.append(  # pyright: ignore[reportUnknownMemberType]
                                                    Annotation(
                                                        type="citation",
                                                        file_id=annotation.file_id,
                                                        url=annotation.filename,
                                                        additional_properties={
                                                            "container_id": annotation.container_id,
                                                        },
                                                        annotated_regions=[
                                                            TextSpanRegion(
                                                                type="text_span",
                                                                start_index=annotation.start_index,
                                                                end_index=annotation.end_index,
                                                            )
                                                        ],
                                                        raw_representation=annotation,
                                                    )
                                                )
                                            case _:
                                                logger.debug(
                                                    "Unparsed annotation type: %s",
                                                    annotation.type,
                                                )
                                contents.append(text_content)
                            case "refusal":
                                contents.append(
                                    Content.from_text(
                                        text=message_content.refusal,
                                        raw_representation=message_content,
                                    )
                                )
                case "reasoning":  # ResponseOutputReasoning
                    added_reasoning = False
                    if item_content := getattr(item, "content", None):
                        for index, reasoning_content in enumerate(item_content):
                            additional_properties: dict[str, Any] = {}
                            if hasattr(item, "summary") and item.summary and index < len(item.summary):
                                additional_properties["summary"] = item.summary[index]
                            contents.append(
                                Content.from_text_reasoning(
                                    id=item.id,
                                    text=reasoning_content.text,
                                    raw_representation=reasoning_content,
                                    additional_properties=additional_properties or None,
                                )
                            )
                            added_reasoning = True
                    if item_summary := getattr(item, "summary", None):
                        for summary in item_summary:
                            contents.append(
                                Content.from_text_reasoning(
                                    id=item.id,
                                    text=summary.text,
                                    raw_representation=summary,  # type: ignore[arg-type]
                                )
                            )
                            added_reasoning = True
                    if not added_reasoning:
                        # Reasoning item with no visible text (e.g. encrypted reasoning).
                        # Always emit an empty marker so co-occurrence detection can be done
                        additional_properties_empty: dict[str, Any] = {}
                        if encrypted := getattr(item, "encrypted_content", None):
                            additional_properties_empty["encrypted_content"] = encrypted
                        contents.append(
                            Content.from_text_reasoning(
                                id=item.id,
                                text="",
                                raw_representation=item,
                                additional_properties=additional_properties_empty or None,
                            )
                        )
                case "code_interpreter_call":  # ResponseOutputCodeInterpreterCall
                    call_id = getattr(item, "call_id", None) or getattr(item, "id", None)
                    outputs: list[Content] = []
                    if item_outputs := getattr(item, "outputs", None):
                        for code_output in item_outputs:
                            if getattr(code_output, "type", None) == "logs":
                                outputs.append(
                                    Content.from_text(
                                        text=code_output.logs,
                                        raw_representation=code_output,
                                    )
                                )
                            elif getattr(code_output, "type", None) == "image":
                                outputs.append(
                                    Content.from_uri(
                                        uri=code_output.url,
                                        raw_representation=code_output,
                                        media_type="image",
                                    )
                                )
                    if code := getattr(item, "code", None):
                        contents.append(
                            Content.from_code_interpreter_tool_call(
                                call_id=call_id,
                                inputs=[Content.from_text(text=code, raw_representation=item)],
                                raw_representation=item,
                            )
                        )
                    contents.append(
                        Content.from_code_interpreter_tool_result(
                            call_id=call_id,
                            outputs=outputs,
                            raw_representation=item,
                        )
                    )
                case "function_call":  # ResponseOutputFunctionCall
                    contents.append(
                        Content.from_function_call(
                            call_id=item.call_id if hasattr(item, "call_id") and item.call_id else "",
                            name=item.name if hasattr(item, "name") else "",
                            arguments=item.arguments if hasattr(item, "arguments") else "",
                            additional_properties={"fc_id": item.id} if hasattr(item, "id") else {},
                            raw_representation=item,
                        )
                    )
                case "mcp_approval_request":  # ResponseOutputMcpApprovalRequest
                    contents.append(
                        Content.from_function_approval_request(
                            id=item.id,
                            function_call=Content.from_function_call(
                                call_id=item.id,
                                name=item.name,
                                arguments=item.arguments,
                                additional_properties={"server_label": item.server_label},
                                raw_representation=item,
                            ),
                        )
                    )
                case "mcp_call":
                    call_id = item.id
                    contents.append(
                        Content.from_mcp_server_tool_call(
                            call_id=call_id,
                            tool_name=item.name,
                            server_name=item.server_label,
                            arguments=item.arguments,
                            raw_representation=item,
                        )
                    )
                    if item.output is not None:
                        contents.append(
                            Content.from_mcp_server_tool_result(
                                call_id=call_id,
                                output=[Content.from_text(text=item.output)],
                                raw_representation=item,
                            )
                        )
                case "image_generation_call":  # ResponseOutputImageGenerationCall
                    image_output: Content | None = None
                    if item.result is not None:
                        # item.result contains raw base64 string
                        # so we call detect_media_type_from_base64 to get the media type and fallback to image/png
                        image_output = Content.from_uri(
                            uri=f"data:{detect_media_type_from_base64(data_str=item.result) or 'image/png'}"
                            f";base64,{item.result}",
                            raw_representation=item.result,
                        )
                    image_id = item.id
                    contents.append(
                        Content.from_image_generation_tool_call(
                            image_id=image_id,
                            raw_representation=item,
                        )
                    )
                    contents.append(
                        Content.from_image_generation_tool_result(
                            image_id=image_id,
                            outputs=image_output,
                            raw_representation=item,
                        )
                    )
                case _:
                    logger.debug("Unparsed output of type: %s: %s", item.type, item)
        response_message = Message(role="assistant", contents=contents)
        args: dict[str, Any] = {
            "response_id": response.id,
            "created_at": datetime.fromtimestamp(response.created_at, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "messages": response_message,
            "model_id": response.model,
            "additional_properties": metadata,
            "raw_representation": response,
        }

        if conversation_id := self._get_conversation_id(response, options.get("store")):  # pyright: ignore[reportUnknownArgumentType]
            args["conversation_id"] = conversation_id
        if response.usage and (usage_details := self._parse_usage_from_openai(response.usage)):
            args["usage_details"] = usage_details
        if structured_response:
            args["value"] = structured_response
        elif (response_format := options.get("response_format")) and isinstance(response_format, type):
            # Only pass response_format to ChatResponse if it's a Pydantic model type,
            # not a runtime JSON schema dict
            args["response_format"] = response_format
        # Set continuation_token when background operation is still in progress
        if response.status and response.status in ("in_progress", "queued"):
            args["continuation_token"] = OpenAIContinuationToken(response_id=response.id)
        return ChatResponse(**args)

    def _parse_chunk_from_openai(
        self,
        event: OpenAIResponseStreamEvent,
        options: dict[str, Any],
        function_call_ids: dict[int, tuple[str, str]],
    ) -> ChatResponseUpdate:
        """Parse an OpenAI Responses API streaming event into a ChatResponseUpdate."""
        metadata: dict[str, Any] = {}
        contents: list[Content] = []
        conversation_id: str | None = None
        response_id: str | None = None
        continuation_token: OpenAIContinuationToken | None = None
        model = self.model_id
        match event.type:
            # types:
            # ResponseAudioDeltaEvent,
            # ResponseAudioDoneEvent,
            # ResponseAudioTranscriptDeltaEvent,
            # ResponseAudioTranscriptDoneEvent,
            # ResponseCodeInterpreterCallCodeDeltaEvent,
            # ResponseCodeInterpreterCallCodeDoneEvent,
            # ResponseCodeInterpreterCallCompletedEvent,
            # ResponseCodeInterpreterCallInProgressEvent,
            # ResponseCodeInterpreterCallInterpretingEvent,
            # ResponseCompletedEvent,
            # ResponseContentPartAddedEvent,
            # ResponseContentPartDoneEvent,
            # ResponseCreatedEvent,
            # ResponseErrorEvent,
            # ResponseFileSearchCallCompletedEvent,
            # ResponseFileSearchCallInProgressEvent,
            # ResponseFileSearchCallSearchingEvent,
            # ResponseFunctionCallArgumentsDeltaEvent,
            # ResponseFunctionCallArgumentsDoneEvent,
            # ResponseInProgressEvent,
            # ResponseFailedEvent,
            # ResponseIncompleteEvent,
            # ResponseOutputItemAddedEvent,
            # ResponseOutputItemDoneEvent,
            # ResponseReasoningSummaryPartAddedEvent,
            # ResponseReasoningSummaryPartDoneEvent,
            # ResponseReasoningSummaryTextDeltaEvent,
            # ResponseReasoningSummaryTextDoneEvent,
            # ResponseReasoningTextDeltaEvent,
            # ResponseReasoningTextDoneEvent,
            # ResponseRefusalDeltaEvent,
            # ResponseRefusalDoneEvent,
            # ResponseTextDeltaEvent,
            # ResponseTextDoneEvent,
            # ResponseWebSearchCallCompletedEvent,
            # ResponseWebSearchCallInProgressEvent,
            # ResponseWebSearchCallSearchingEvent,
            # ResponseImageGenCallCompletedEvent,
            # ResponseImageGenCallGeneratingEvent,
            # ResponseImageGenCallInProgressEvent,
            # ResponseImageGenCallPartialImageEvent,
            # ResponseMcpCallArgumentsDeltaEvent,
            # ResponseMcpCallArgumentsDoneEvent,
            # ResponseMcpCallCompletedEvent,
            # ResponseMcpCallFailedEvent,
            # ResponseMcpCallInProgressEvent,
            # ResponseMcpListToolsCompletedEvent,
            # ResponseMcpListToolsFailedEvent,
            # ResponseMcpListToolsInProgressEvent,
            # ResponseOutputTextAnnotationAddedEvent,
            # ResponseQueuedEvent,
            # ResponseCustomToolCallInputDeltaEvent,
            # ResponseCustomToolCallInputDoneEvent,
            case "response.content_part.added":
                event_part = event.part
                match event_part.type:
                    case "output_text":
                        contents.append(Content.from_text(text=event_part.text, raw_representation=event))
                        metadata.update(self._get_metadata_from_response(event_part))
                    case "refusal":
                        contents.append(Content.from_text(text=event_part.refusal, raw_representation=event))
                    case _:
                        pass
            case "response.output_text.delta":
                contents.append(Content.from_text(text=event.delta, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_text.delta":
                contents.append(
                    Content.from_text_reasoning(
                        id=event.item_id,
                        text=event.delta,
                        raw_representation=event,
                    )
                )
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_text.done":
                contents.append(
                    Content.from_text_reasoning(
                        id=event.item_id,
                        text=event.text,
                        raw_representation=event,
                    )
                )
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_summary_text.delta":
                contents.append(
                    Content.from_text_reasoning(
                        id=event.item_id,
                        text=event.delta,
                        raw_representation=event,
                    )
                )
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_summary_text.done":
                contents.append(
                    Content.from_text_reasoning(
                        id=event.item_id,
                        text=event.text,
                        raw_representation=event,
                    )
                )
                metadata.update(self._get_metadata_from_response(event))
            case "response.code_interpreter_call_code.delta":
                call_id = getattr(event, "call_id", None) or getattr(event, "id", None) or event.item_id
                ci_additional_properties = {
                    "output_index": event.output_index,
                    "sequence_number": event.sequence_number,
                    "item_id": event.item_id,
                }
                contents.append(
                    Content.from_code_interpreter_tool_call(
                        call_id=call_id,
                        inputs=[
                            Content.from_text(
                                text=event.delta,
                                raw_representation=event,
                                additional_properties=ci_additional_properties,
                            )
                        ],
                        raw_representation=event,
                        additional_properties=ci_additional_properties,
                    )
                )
                metadata.update(self._get_metadata_from_response(event))
            case "response.code_interpreter_call_code.done":
                call_id = getattr(event, "call_id", None) or getattr(event, "id", None) or event.item_id
                ci_additional_properties = {
                    "output_index": event.output_index,
                    "sequence_number": event.sequence_number,
                    "item_id": event.item_id,
                }
                contents.append(
                    Content.from_code_interpreter_tool_call(
                        call_id=call_id,
                        inputs=[
                            Content.from_text(
                                text=event.code,
                                raw_representation=event,
                                additional_properties=ci_additional_properties,
                            )
                        ],
                        raw_representation=event,
                        additional_properties=ci_additional_properties,
                    )
                )
                metadata.update(self._get_metadata_from_response(event))
            case "response.created":
                response_id = event.response.id
                conversation_id = self._get_conversation_id(event.response, options.get("store"))
                if event.response.status and event.response.status in ("in_progress", "queued"):
                    continuation_token = OpenAIContinuationToken(response_id=event.response.id)
            case "response.in_progress":
                response_id = event.response.id
                conversation_id = self._get_conversation_id(event.response, options.get("store"))
                continuation_token = OpenAIContinuationToken(response_id=event.response.id)
            case "response.completed":
                response_id = event.response.id
                conversation_id = self._get_conversation_id(event.response, options.get("store"))
                model = event.response.model
                if event.response.usage:
                    usage = self._parse_usage_from_openai(event.response.usage)
                    if usage:
                        contents.append(Content.from_usage(usage_details=usage, raw_representation=event))
            case "response.output_item.added":
                event_item = event.item
                match event_item.type:
                    # types:
                    # ResponseOutputMessage,
                    # ResponseFileSearchToolCall,
                    # ResponseFunctionToolCall,
                    # ResponseFunctionWebSearch,
                    # ResponseComputerToolCall,
                    # ResponseReasoningItem,
                    # ImageGenerationCall,
                    # ResponseCodeInterpreterToolCall,
                    # LocalShellCall,
                    # McpCall,
                    # McpListTools,
                    # McpApprovalRequest,
                    # ResponseCustomToolCall,
                    case "function_call":
                        function_call_ids[event.output_index] = (
                            event_item.call_id,
                            event_item.name,
                        )
                    case "mcp_approval_request":
                        contents.append(
                            Content.from_function_approval_request(
                                id=event_item.id,
                                function_call=Content.from_function_call(
                                    call_id=event_item.id,
                                    name=event_item.name,
                                    arguments=event_item.arguments,
                                    additional_properties={"server_label": event_item.server_label},
                                    raw_representation=event_item,
                                ),
                            )
                        )
                    case "mcp_call":
                        call_id = getattr(event_item, "id", None) or getattr(event_item, "call_id", None) or ""
                        contents.append(
                            Content.from_mcp_server_tool_call(
                                call_id=call_id,
                                tool_name=getattr(event_item, "name", "") or "",
                                server_name=getattr(event_item, "server_label", None),
                                arguments=getattr(event_item, "arguments", None),
                                raw_representation=event_item,
                            )
                        )
                        result_output = (
                            getattr(event_item, "result", None)
                            or getattr(event_item, "output", None)
                            or getattr(event_item, "outputs", None)
                        )
                        parsed_output: list[Content] | None = None
                        if result_output:
                            normalized = (  # pyright: ignore[reportUnknownVariableType]
                                result_output
                                if isinstance(result_output, Sequence)
                                and not isinstance(result_output, (str, bytes, MutableMapping))
                                else [result_output]
                            )
                            parsed_output = [Content.from_dict(output_item) for output_item in normalized]  # pyright: ignore[reportArgumentType,reportUnknownVariableType]
                        contents.append(
                            Content.from_mcp_server_tool_result(
                                call_id=call_id,
                                output=parsed_output,
                                raw_representation=event_item,
                            )
                        )
                    case "code_interpreter_call":  # ResponseOutputCodeInterpreterCall
                        call_id = getattr(event_item, "call_id", None) or getattr(event_item, "id", None)
                        outputs: list[Content] = []
                        if hasattr(event_item, "outputs") and event_item.outputs:
                            for code_output in event_item.outputs:
                                if getattr(code_output, "type", None) == "logs":
                                    outputs.append(
                                        Content.from_text(
                                            text=cast(Any, code_output).logs,
                                            raw_representation=code_output,
                                        )
                                    )
                                elif getattr(code_output, "type", None) == "image":
                                    outputs.append(
                                        Content.from_uri(
                                            uri=cast(Any, code_output).url,
                                            raw_representation=code_output,
                                            media_type="image",
                                        )
                                    )
                        if hasattr(event_item, "code") and event_item.code:
                            contents.append(
                                Content.from_code_interpreter_tool_call(
                                    call_id=call_id,
                                    inputs=[
                                        Content.from_text(
                                            text=event_item.code,
                                            raw_representation=event_item,
                                        )
                                    ],
                                    raw_representation=event_item,
                                )
                            )
                        contents.append(
                            Content.from_code_interpreter_tool_result(
                                call_id=call_id,
                                outputs=outputs,
                                raw_representation=event_item,
                            )
                        )
                    case "reasoning":  # ResponseOutputReasoning
                        reasoning_id = getattr(event_item, "id", None)
                        added_reasoning = False
                        if hasattr(event_item, "content") and event_item.content:
                            for index, reasoning_content in enumerate(event_item.content):
                                additional_properties: dict[str, Any] = {}
                                if (
                                    hasattr(event_item, "summary")
                                    and event_item.summary
                                    and index < len(event_item.summary)
                                ):
                                    additional_properties["summary"] = event_item.summary[index]
                                contents.append(
                                    Content.from_text_reasoning(
                                        id=reasoning_id or None,
                                        text=reasoning_content.text,
                                        raw_representation=reasoning_content,
                                        additional_properties=additional_properties or None,
                                    )
                                )
                                added_reasoning = True
                        if not added_reasoning:
                            # Reasoning item with no visible text (e.g. encrypted reasoning).
                            # Always emit an empty marker so co-occurrence detection can occur.
                            additional_properties_empty: dict[str, Any] = {}
                            if encrypted := getattr(event_item, "encrypted_content", None):
                                additional_properties_empty["encrypted_content"] = encrypted
                            contents.append(
                                Content.from_text_reasoning(
                                    id=reasoning_id or None,
                                    text="",
                                    raw_representation=event_item,
                                    additional_properties=additional_properties_empty or None,
                                )
                            )
                    case _:
                        logger.debug("Unparsed event of type: %s: %s", event.type, event)
            case "response.function_call_arguments.delta":
                call_id, name = function_call_ids.get(event.output_index, (None, None))
                if call_id and name:
                    contents.append(
                        Content.from_function_call(
                            call_id=call_id,
                            name=name,
                            arguments=event.delta,
                            additional_properties={
                                "output_index": event.output_index,
                                "fc_id": event.item_id,
                            },
                            raw_representation=event,
                        )
                    )
            case "response.image_generation_call.partial_image":
                # Handle streaming partial image generation
                image_base64 = event.partial_image_b64
                partial_index = event.partial_image_index
                image_output = Content.from_uri(
                    uri=f"data:{detect_media_type_from_base64(data_str=image_base64) or 'image/png'}"
                    f";base64,{image_base64}",
                    additional_properties={
                        "partial_image_index": partial_index,
                        "is_partial_image": True,
                    },
                    raw_representation=event,
                )

                image_id = getattr(event, "item_id", None)
                contents.append(
                    Content.from_image_generation_tool_call(
                        image_id=image_id,
                        raw_representation=event,
                    )
                )
                contents.append(
                    Content.from_image_generation_tool_result(
                        image_id=image_id,
                        outputs=image_output,
                        raw_representation=event,
                    )
                )
            case "response.output_text.annotation.added":
                # Handle streaming text annotations (file citations, file paths, etc.)
                annotation: Any = event.annotation

                def _get_ann_value(key: str) -> Any:
                    """Extract value from annotation (dict or object)."""
                    if isinstance(annotation, dict):
                        return cast("dict[str, Any]", annotation).get(key)
                    return getattr(annotation, key, None)

                ann_type = _get_ann_value("type")
                ann_file_id = _get_ann_value("file_id")
                if ann_type == "file_path":
                    if ann_file_id:
                        contents.append(
                            Content.from_hosted_file(
                                file_id=str(ann_file_id),
                                additional_properties={
                                    "annotation_index": event.annotation_index,
                                    "index": _get_ann_value("index"),
                                },
                                raw_representation=event,
                            )
                        )
                elif ann_type == "file_citation":
                    if ann_file_id:
                        contents.append(
                            Content.from_hosted_file(
                                file_id=str(ann_file_id),
                                additional_properties={
                                    "annotation_index": event.annotation_index,
                                    "filename": _get_ann_value("filename"),
                                    "index": _get_ann_value("index"),
                                },
                                raw_representation=event,
                            )
                        )
                elif ann_type == "container_file_citation":
                    if ann_file_id:
                        contents.append(
                            Content.from_hosted_file(
                                file_id=str(ann_file_id),
                                additional_properties={
                                    "annotation_index": event.annotation_index,
                                    "container_id": _get_ann_value("container_id"),
                                    "filename": _get_ann_value("filename"),
                                    "start_index": _get_ann_value("start_index"),
                                    "end_index": _get_ann_value("end_index"),
                                },
                                raw_representation=event,
                            )
                        )
                else:
                    logger.debug("Unparsed annotation type in streaming: %s", ann_type)
            case _:
                logger.debug("Unparsed event of type: %s: %s", event.type, event)

        return ChatResponseUpdate(
            contents=contents,
            conversation_id=conversation_id,
            response_id=response_id,
            role="assistant",
            model_id=model,
            continuation_token=continuation_token,
            additional_properties=metadata,
            raw_representation=event,
        )

    def _parse_usage_from_openai(self, usage: ResponseUsage) -> UsageDetails | None:
        details = UsageDetails(
            input_token_count=usage.input_tokens,
            output_token_count=usage.output_tokens,
            total_token_count=usage.total_tokens,
        )
        if usage.input_tokens_details and usage.input_tokens_details.cached_tokens:
            details["openai.cached_input_tokens"] = usage.input_tokens_details.cached_tokens  # type: ignore[typeddict-unknown-key]
        if usage.output_tokens_details and usage.output_tokens_details.reasoning_tokens:
            details["openai.reasoning_tokens"] = usage.output_tokens_details.reasoning_tokens  # type: ignore[typeddict-unknown-key]
        return details

    def _get_metadata_from_response(self, output: Any) -> dict[str, Any]:
        """Get metadata from a chat choice."""
        if logprobs := getattr(output, "logprobs", None):
            return {
                "logprobs": logprobs,
            }
        return {}


class OpenAIResponsesClient(  # type: ignore[misc]
    OpenAIConfigMixin,
    ChatMiddlewareLayer[OpenAIResponsesOptionsT],
    FunctionInvocationLayer[OpenAIResponsesOptionsT],
    ChatTelemetryLayer[OpenAIResponsesOptionsT],
    RawOpenAIResponsesClient[OpenAIResponsesOptionsT],
    Generic[OpenAIResponsesOptionsT],
):
    """OpenAI Responses client class with middleware, telemetry, and function invocation support."""

    def __init__(
        self,
        *,
        model_id: str | None = None,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        middleware: (
            Sequence[ChatMiddleware | ChatMiddlewareCallable | FunctionMiddleware | FunctionMiddlewareCallable] | None
        ) = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an OpenAI Responses client.

        Keyword Args:
            model_id: OpenAI model name, see https://platform.openai.com/docs/models.
                Can also be set via environment variable OPENAI_RESPONSES_MODEL_ID.
            api_key: The API key to use. If provided will override the env vars or .env file value.
                Can also be set via environment variable OPENAI_API_KEY.
            org_id: The org ID to use. If provided will override the env vars or .env file value.
                Can also be set via environment variable OPENAI_ORG_ID.
            base_url: The base URL to use. If provided will override the standard value.
                Can also be set via environment variable OPENAI_BASE_URL.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests.
            async_client: An existing client to use.
            instruction_role: The role to use for 'instruction' messages, for example,
                "system" or "developer". If not provided, the default is "system".
            env_file_path: Use the environment settings file as a fallback
                to environment variables.
            env_file_encoding: The encoding of the environment settings file.
            middleware: Optional middleware to apply to the client.
            function_invocation_configuration: Optional function invocation configuration override.
            kwargs: Other keyword parameters.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient

                # Using environment variables
                # Set OPENAI_API_KEY=sk-...
                # Set OPENAI_RESPONSES_MODEL_ID=gpt-4o
                client = OpenAIResponsesClient()

                # Or passing parameters directly
                client = OpenAIResponsesClient(model_id="gpt-4o", api_key="sk-...")

                # Or loading from a .env file
                client = OpenAIResponsesClient(env_file_path="path/to/.env")

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework.openai import OpenAIResponsesOptions


                class MyOptions(OpenAIResponsesOptions, total=False):
                    my_custom_option: str


                client: OpenAIResponsesClient[MyOptions] = OpenAIResponsesClient(model_id="gpt-4o")
                response = await client.get_response("Hello", options={"my_custom_option": "value"})
        """
        openai_settings = load_settings(
            OpenAISettings,
            env_prefix="OPENAI_",
            api_key=api_key,
            org_id=org_id,
            base_url=base_url,
            responses_model_id=model_id,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        if not async_client and not openai_settings["api_key"]:
            raise ValueError(
                "OpenAI API key is required. Set via 'api_key' parameter or 'OPENAI_API_KEY' environment variable."
            )
        if not openai_settings["responses_model_id"]:
            raise ValueError(
                "OpenAI model ID is required. "
                "Set via 'model_id' parameter or 'OPENAI_RESPONSES_MODEL_ID' environment variable."
            )

        super().__init__(
            model_id=openai_settings["responses_model_id"],
            api_key=self._get_api_key(openai_settings["api_key"]),
            org_id=openai_settings["org_id"],
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
            base_url=openai_settings["base_url"],
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            **kwargs,
        )
