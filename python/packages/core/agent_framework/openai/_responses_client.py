# Copyright (c) Microsoft. All rights reserved.

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
from datetime import datetime, timezone
from itertools import chain
from typing import Any, Generic, Literal, cast

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
    Mcp,
    ToolParam,
)
from openai.types.responses.web_search_tool_param import WebSearchToolParam
from pydantic import BaseModel, ValidationError

from .._clients import BaseChatClient
from .._logging import get_logger
from .._middleware import use_chat_middleware
from .._tools import (
    FunctionTool,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedImageGenerationTool,
    HostedMCPTool,
    HostedWebSearchTool,
    ToolProtocol,
    use_function_invocation,
)
from .._types import (
    Annotation,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Role,
    TextSpanRegion,
    UsageDetails,
    detect_media_type_from_base64,
    prepare_function_call_results,
    prepend_instructions_to_messages,
    validate_tool_mode,
)
from ..exceptions import (
    ServiceInitializationError,
    ServiceInvalidRequestError,
    ServiceResponseException,
)
from ..observability import use_instrumentation
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

logger = get_logger("agent_framework.openai")


__all__ = ["OpenAIResponsesClient", "OpenAIResponsesOptions"]


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


TResponseFormat = TypeVar("TResponseFormat", bound=BaseModel | None, default=None)


class OpenAIResponsesOptions(ChatOptions[TResponseFormat], Generic[TResponseFormat], total=False):
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


TOpenAIResponsesOptions = TypeVar(
    "TOpenAIResponsesOptions",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIResponsesOptions",
    covariant=True,
)


# endregion


# region ResponsesClient


class OpenAIBaseResponsesClient(
    OpenAIBase,
    BaseChatClient[TOpenAIResponsesOptions],
    Generic[TOpenAIResponsesOptions],
):
    """Base class for all OpenAI Responses based API's."""

    FILE_SEARCH_MAX_RESULTS: int = 50

    # region Inner Methods

    @override
    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        client = await self._ensure_client()
        # prepare
        run_options = await self._prepare_options(messages, options, **kwargs)
        try:
            # execute and process
            if "text_format" in run_options:
                response = await client.responses.parse(stream=False, **run_options)
            else:
                response = await client.responses.create(stream=False, **run_options)
        except BadRequestError as ex:
            if ex.code == "content_filter":
                raise OpenAIContentFilterException(
                    f"{type(self)} service encountered a content error: {ex}",
                    inner_exception=ex,
                ) from ex
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex
        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex
        return self._parse_response_from_openai(response, options=options)

    @override
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        client = await self._ensure_client()
        # prepare
        run_options = await self._prepare_options(messages, options, **kwargs)
        function_call_ids: dict[int, tuple[str, str]] = {}  # output_index: (call_id, name)
        try:
            # execute and process
            if "text_format" not in run_options:
                async for chunk in await client.responses.create(stream=True, **run_options):
                    yield self._parse_chunk_from_openai(
                        chunk,
                        options=options,
                        function_call_ids=function_call_ids,
                    )
                return
            async with client.responses.stream(**run_options) as response:
                async for chunk in response:
                    yield self._parse_chunk_from_openai(
                        chunk,
                        options=options,
                        function_call_ids=function_call_ids,
                    )
        except BadRequestError as ex:
            if ex.code == "content_filter":
                raise OpenAIContentFilterException(
                    f"{type(self)} service encountered a content error: {ex}",
                    inner_exception=ex,
                ) from ex
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex
        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex

    def _prepare_response_and_text_format(
        self,
        *,
        response_format: Any,
        text_config: MutableMapping[str, Any] | None,
    ) -> tuple[type[BaseModel] | None, dict[str, Any] | None]:
        """Normalize response_format into Responses text configuration and parse target."""
        if text_config is not None and not isinstance(text_config, MutableMapping):
            raise ServiceInvalidRequestError("text must be a mapping when provided.")
        text_config = cast(dict[str, Any], text_config) if isinstance(text_config, MutableMapping) else None

        if response_format is None:
            return None, text_config

        if isinstance(response_format, type) and issubclass(response_format, BaseModel):
            if text_config and "format" in text_config:
                raise ServiceInvalidRequestError("response_format cannot be combined with explicit text.format.")
            return response_format, text_config

        if isinstance(response_format, Mapping):
            format_config = self._convert_response_format(cast("Mapping[str, Any]", response_format))
            if text_config is None:
                text_config = {}
            elif "format" in text_config and text_config["format"] != format_config:
                raise ServiceInvalidRequestError("Conflicting response_format definitions detected.")
            text_config["format"] = format_config
            return None, text_config

        raise ServiceInvalidRequestError("response_format must be a Pydantic model or mapping.")

    def _convert_response_format(self, response_format: Mapping[str, Any]) -> dict[str, Any]:
        """Convert Chat style response_format into Responses text format config."""
        if "format" in response_format and isinstance(response_format["format"], Mapping):
            return dict(cast("Mapping[str, Any]", response_format["format"]))

        format_type = response_format.get("type")
        if format_type == "json_schema":
            schema_section = response_format.get("json_schema", response_format)
            if not isinstance(schema_section, Mapping):
                raise ServiceInvalidRequestError("json_schema response_format must be a mapping.")
            schema_section_typed = cast("Mapping[str, Any]", schema_section)
            schema: Any = schema_section_typed.get("schema")
            if schema is None:
                raise ServiceInvalidRequestError("json_schema response_format requires a schema.")
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

        raise ServiceInvalidRequestError("Unsupported response_format provided for Responses client.")

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
        self, tools: Sequence[ToolProtocol | MutableMapping[str, Any]] | None
    ) -> list[ToolParam | dict[str, Any]]:
        response_tools: list[ToolParam | dict[str, Any]] = []
        if not tools:
            return response_tools
        for tool in tools:
            if isinstance(tool, ToolProtocol):
                match tool:
                    case HostedMCPTool():
                        response_tools.append(self._prepare_mcp_tool(tool))
                    case HostedCodeInterpreterTool():
                        tool_args: CodeInterpreterContainerCodeInterpreterToolAuto = {"type": "auto"}
                        if tool.inputs:
                            tool_args["file_ids"] = []
                            for tool_input in tool.inputs:
                                if tool_input.type == "hosted_file":
                                    tool_args["file_ids"].append(tool_input.file_id)  # type: ignore[attr-defined]
                            if not tool_args["file_ids"]:
                                tool_args.pop("file_ids")
                        response_tools.append(
                            CodeInterpreter(
                                type="code_interpreter",
                                container=tool_args,
                            )
                        )
                    case FunctionTool():
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
                    case HostedFileSearchTool():
                        if not tool.inputs:
                            raise ValueError("HostedFileSearchTool requires inputs to be specified.")
                        inputs: list[str] = [
                            inp.vector_store_id  # type: ignore[misc]
                            for inp in tool.inputs
                            if inp.type == "hosted_vector_store"  # type: ignore[attr-defined]
                        ]
                        if not inputs:
                            raise ValueError(
                                "HostedFileSearchTool requires inputs to be of type `HostedVectorStoreContent`."
                            )

                        response_tools.append(
                            FileSearchToolParam(
                                type="file_search",
                                vector_store_ids=inputs,
                                max_num_results=tool.max_results
                                or self.FILE_SEARCH_MAX_RESULTS,  # default to max results  if not specified
                            )
                        )
                    case HostedWebSearchTool():
                        web_search_tool = WebSearchToolParam(type="web_search")
                        if location := (
                            tool.additional_properties.get("user_location", None)
                            if tool.additional_properties
                            else None
                        ):
                            web_search_tool["user_location"] = {
                                "type": "approximate",
                                "city": location.get("city", None),
                                "country": location.get("country", None),
                                "region": location.get("region", None),
                                "timezone": location.get("timezone", None),
                            }
                        if filters := (
                            tool.additional_properties.get("filters", None) if tool.additional_properties else None
                        ):
                            web_search_tool["filters"] = filters
                        if search_context_size := (
                            tool.additional_properties.get("search_context_size", None)
                            if tool.additional_properties
                            else None
                        ):
                            web_search_tool["search_context_size"] = search_context_size
                        response_tools.append(web_search_tool)
                    case HostedImageGenerationTool():
                        mapped_tool: dict[str, Any] = {"type": "image_generation"}
                        if tool.options:
                            option_mapping = {
                                "image_size": "size",
                                "media_type": "output_format",
                                "model_id": "model",
                                "streaming_count": "partial_images",
                            }
                            # count and response_format are not supported by Responses API
                            for key, value in tool.options.items():
                                mapped_key = option_mapping.get(key, key)
                                mapped_tool[mapped_key] = value
                        if tool.additional_properties:
                            mapped_tool.update(tool.additional_properties)
                        response_tools.append(mapped_tool)
                    case _:
                        logger.debug("Unsupported tool passed (type: %s)", type(tool))
            else:
                # Handle raw dictionary tools
                tool_dict = tool if isinstance(tool, dict) else dict(tool)
                response_tools.append(tool_dict)
        return response_tools

    @staticmethod
    def _prepare_mcp_tool(tool: HostedMCPTool) -> Mcp:
        """Get MCP tool from HostedMCPTool."""
        mcp: Mcp = {
            "type": "mcp",
            "server_label": tool.name.replace(" ", "_"),
            "server_url": str(tool.url),
            "server_description": tool.description,
            "headers": tool.headers,
        }
        if tool.allowed_tools:
            mcp["allowed_tools"] = list(tool.allowed_tools)
        if tool.approval_mode:
            match tool.approval_mode:
                case str():
                    mcp["require_approval"] = "always" if tool.approval_mode == "always_require" else "never"
                case _:
                    if always_require_approvals := tool.approval_mode.get("always_require_approval"):
                        mcp["require_approval"] = {"always": {"tool_names": list(always_require_approvals)}}
                    if never_require_approvals := tool.approval_mode.get("never_require_approval"):
                        mcp["require_approval"] = {"never": {"tool_names": list(never_require_approvals)}}

        return mcp

    async def _prepare_options(
        self,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
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
        }
        run_options: dict[str, Any] = {k: v for k, v in options.items() if k not in exclude_keys and v is not None}

        # messages
        # Handle instructions by prepending to messages as system message
        if instructions := options.get("instructions"):
            messages = prepend_instructions_to_messages(list(messages), instructions, role="system")
        request_input = self._prepare_messages_for_openai(messages)
        if not request_input:
            raise ServiceInvalidRequestError("Messages are required for chat completions")
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

    def _get_current_conversation_id(self, options: dict[str, Any], **kwargs: Any) -> str | None:
        """Get the current conversation ID, preferring kwargs over options.

        This ensures runtime-updated conversation IDs (for example, from tool execution
        loops) take precedence over the initial configuration provided in options.
        """
        return kwargs.get("conversation_id") or options.get("conversation_id")

    def _prepare_messages_for_openai(self, chat_messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
        """Prepare the chat messages for a request.

        Allowing customization of the key names for role/author, and optionally overriding the role.

        Role.TOOL messages need to be formatted different than system/user/assistant messages:
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
        message: ChatMessage,
        call_id_to_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Prepare a chat message for the OpenAI Responses API format."""
        all_messages: list[dict[str, Any]] = []
        args: dict[str, Any] = {
            "role": message.role.value if isinstance(message.role, Role) else message.role,
        }
        for content in message.contents:
            match content.type:
                case "text_reasoning":
                    # Don't send reasoning content back to model
                    continue
                case "function_result":
                    new_args: dict[str, Any] = {}
                    new_args.update(self._prepare_content_for_openai(message.role, content, call_id_to_id))
                    all_messages.append(new_args)
                case "function_call":
                    function_call = self._prepare_content_for_openai(message.role, content, call_id_to_id)
                    all_messages.append(function_call)  # type: ignore
                case "function_approval_response" | "function_approval_request":
                    all_messages.append(self._prepare_content_for_openai(message.role, content, call_id_to_id))  # type: ignore
                case _:
                    if "content" not in args:
                        args["content"] = []
                    args["content"].append(self._prepare_content_for_openai(message.role, content, call_id_to_id))  # type: ignore
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
                return {
                    "type": "output_text" if role == Role.ASSISTANT else "input_text",
                    "text": content.text,
                }
            case "text_reasoning":
                ret: dict[str, Any] = {
                    "type": "reasoning",
                    "summary": {
                        "type": "summary_text",
                        "text": content.text,
                    },
                }
                props: dict[str, Any] | None = getattr(content, "additional_properties", None)
                if props:
                    if status := props.get("status"):
                        ret["status"] = status
                    if reasoning_text := props.get("reasoning_text"):
                        ret["content"] = {
                            "type": "reasoning_text",
                            "text": reasoning_text,
                        }
                    if encrypted_content := props.get("encrypted_content"):
                        ret["encrypted_content"] = encrypted_content
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
                    "output": prepare_function_call_results(content.result),
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
    ) -> "ChatResponse":
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
                                                text_content.annotations.append(
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
                                                text_content.annotations.append(
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
                                                text_content.annotations.append(
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
                                                text_content.annotations.append(
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
                    if hasattr(item, "content") and item.content:
                        for index, reasoning_content in enumerate(item.content):
                            additional_properties = None
                            if hasattr(item, "summary") and item.summary and index < len(item.summary):
                                additional_properties = {"summary": item.summary[index]}
                            contents.append(
                                Content.from_text_reasoning(
                                    text=reasoning_content.text,
                                    raw_representation=reasoning_content,
                                    additional_properties=additional_properties,
                                )
                            )
                    if hasattr(item, "summary") and item.summary:
                        for summary in item.summary:
                            contents.append(
                                Content.from_text_reasoning(text=summary.text, raw_representation=summary)  # type: ignore[arg-type]
                            )
                case "code_interpreter_call":  # ResponseOutputCodeInterpreterCall
                    call_id = getattr(item, "call_id", None) or getattr(item, "id", None)
                    outputs: list["Content"] = []
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
        response_message = ChatMessage(role="assistant", contents=contents)
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

        if conversation_id := self._get_conversation_id(response, options.get("store")):
            args["conversation_id"] = conversation_id
        if response.usage and (usage_details := self._parse_usage_from_openai(response.usage)):
            args["usage_details"] = usage_details
        if structured_response:
            args["value"] = structured_response
        elif (response_format := options.get("response_format")) and isinstance(response_format, type):
            # Only pass response_format to ChatResponse if it's a Pydantic model type,
            # not a runtime JSON schema dict
            args["response_format"] = response_format
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
                contents.append(Content.from_text_reasoning(text=event.delta, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_text.done":
                contents.append(Content.from_text_reasoning(text=event.text, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_summary_text.delta":
                contents.append(Content.from_text_reasoning(text=event.delta, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_summary_text.done":
                contents.append(Content.from_text_reasoning(text=event.text, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case "response.created":
                response_id = event.response.id
                conversation_id = self._get_conversation_id(event.response, options.get("store"))
            case "response.in_progress":
                response_id = event.response.id
                conversation_id = self._get_conversation_id(event.response, options.get("store"))
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
                            normalized = (
                                result_output
                                if isinstance(result_output, Sequence)
                                and not isinstance(result_output, (str, bytes, MutableMapping))
                                else [result_output]
                            )
                            parsed_output = [Content.from_dict(output_item) for output_item in normalized]
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
                        if hasattr(event_item, "content") and event_item.content:
                            for index, reasoning_content in enumerate(event_item.content):
                                additional_properties = None
                                if (
                                    hasattr(event_item, "summary")
                                    and event_item.summary
                                    and index < len(event_item.summary)
                                ):
                                    additional_properties = {"summary": event_item.summary[index]}
                                contents.append(
                                    Content.from_text_reasoning(
                                        text=reasoning_content.text,
                                        raw_representation=reasoning_content,
                                        additional_properties=additional_properties,
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
            role=Role.ASSISTANT,
            model_id=model,
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


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class OpenAIResponsesClient(
    OpenAIConfigMixin,
    OpenAIBaseResponsesClient[TOpenAIResponsesOptions],
    Generic[TOpenAIResponsesOptions],
):
    """OpenAI Responses client class."""

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
        try:
            openai_settings = OpenAISettings(
                api_key=api_key,  # type: ignore[reportArgumentType]
                org_id=org_id,
                base_url=base_url,
                responses_model_id=model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create OpenAI settings.", ex) from ex

        if not async_client and not openai_settings.api_key:
            raise ServiceInitializationError(
                "OpenAI API key is required. Set via 'api_key' parameter or 'OPENAI_API_KEY' environment variable."
            )
        if not openai_settings.responses_model_id:
            raise ServiceInitializationError(
                "OpenAI model ID is required. "
                "Set via 'model_id' parameter or 'OPENAI_RESPONSES_MODEL_ID' environment variable."
            )

        super().__init__(
            model_id=openai_settings.responses_model_id,
            api_key=self._get_api_key(openai_settings.api_key),
            org_id=openai_settings.org_id,
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
            base_url=openai_settings.base_url,
        )
