# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable, Callable, Mapping, MutableMapping, MutableSequence, Sequence
from datetime import datetime
from itertools import chain
from typing import Any, TypeVar

from openai import AsyncOpenAI, BadRequestError
from openai.types.responses.file_search_tool_param import FileSearchToolParam
from openai.types.responses.function_tool_param import FunctionToolParam
from openai.types.responses.parsed_response import (
    ParsedResponse,
)
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_stream_event import ResponseStreamEvent as OpenAIResponseStreamEvent
from openai.types.responses.response_usage import ResponseUsage
from openai.types.responses.tool_param import (
    CodeInterpreter,
    CodeInterpreterContainerCodeInterpreterToolAuto,
    Mcp,
    ToolParam,
)
from openai.types.responses.web_search_tool_param import UserLocation as WebSearchUserLocation
from openai.types.responses.web_search_tool_param import WebSearchToolParam
from pydantic import BaseModel, ValidationError

from .._clients import BaseChatClient
from .._logging import get_logger
from .._middleware import use_chat_middleware
from .._tools import (
    AIFunction,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedMCPTool,
    HostedWebSearchTool,
    ToolProtocol,
    use_function_invocation,
)
from .._types import (
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    CitationAnnotation,
    Contents,
    DataContent,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
    FunctionCallContent,
    FunctionResultContent,
    HostedFileContent,
    HostedVectorStoreContent,
    Role,
    TextContent,
    TextReasoningContent,
    TextSpanRegion,
    UriContent,
    UsageContent,
    UsageDetails,
    prepare_function_call_results,
)
from ..exceptions import (
    ServiceInitializationError,
    ServiceInvalidRequestError,
    ServiceResponseException,
)
from ..observability import use_observability
from ._exceptions import OpenAIContentFilterException
from ._shared import OpenAIBase, OpenAIConfigMixin, OpenAISettings

logger = get_logger("agent_framework.openai")

__all__ = ["OpenAIResponsesClient"]

# region ResponsesClient


class OpenAIBaseResponsesClient(OpenAIBase, BaseChatClient):
    """Base class for all OpenAI Responses based API's."""

    FILE_SEARCH_MAX_RESULTS: int = 50

    # region Inner Methods

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        client = await self.ensure_client()
        run_options = await self.prepare_options(messages, chat_options)
        try:
            response_format = run_options.pop("response_format", None)
            if not response_format:
                response = await client.responses.create(
                    stream=False,
                    **run_options,
                )
                chat_options.conversation_id = self.get_conversation_id(response, chat_options.store)
                return self._create_response_content(response, chat_options=chat_options)
            # create call does not support response_format, so we need to handle it via parse call
            parsed_response: ParsedResponse[BaseModel] = await client.responses.parse(
                text_format=response_format,
                stream=False,
                **run_options,
            )
            chat_options.conversation_id = self.get_conversation_id(parsed_response, chat_options.store)
            return self._create_response_content(parsed_response, chat_options=chat_options)
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

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        client = await self.ensure_client()
        run_options = await self.prepare_options(messages, chat_options)
        function_call_ids: dict[int, tuple[str, str]] = {}  # output_index: (call_id, name)
        try:
            response_format = run_options.pop("response_format", None)
            if not response_format:
                response = await client.responses.create(
                    stream=True,
                    **run_options,
                )
                async for chunk in response:
                    update = self._create_streaming_response_content(
                        chunk, chat_options=chat_options, function_call_ids=function_call_ids
                    )
                    yield update
                return
            # create call does not support response_format, so we need to handle it via stream call
            async with client.responses.stream(
                text_format=response_format,
                **run_options,
            ) as response:
                async for chunk in response:
                    update = self._create_streaming_response_content(
                        chunk, chat_options=chat_options, function_call_ids=function_call_ids
                    )
                    yield update
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

    def get_conversation_id(
        self, response: OpenAIResponse | ParsedResponse[BaseModel], store: bool | None
    ) -> str | None:
        """Get the conversation ID from the response if store is True."""
        return response.id if store else None

    # region Prep methods

    def _tools_to_response_tools(
        self, tools: Sequence[ToolProtocol | MutableMapping[str, Any]]
    ) -> list[ToolParam | dict[str, Any]]:
        response_tools: list[ToolParam | dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, ToolProtocol):
                match tool:
                    case HostedMCPTool():
                        response_tools.append(self.get_mcp_tool(tool))
                    case HostedCodeInterpreterTool():
                        tool_args: CodeInterpreterContainerCodeInterpreterToolAuto = {"type": "auto"}
                        if tool.inputs:
                            tool_args["file_ids"] = []
                            for tool_input in tool.inputs:
                                if isinstance(tool_input, HostedFileContent):
                                    tool_args["file_ids"].append(tool_input.file_id)  # type: ignore[attr-defined]
                            if not tool_args["file_ids"]:
                                tool_args.pop("file_ids")
                        response_tools.append(
                            CodeInterpreter(
                                type="code_interpreter",
                                container=tool_args,
                            )
                        )
                    case AIFunction():
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
                            inp.vector_store_id for inp in tool.inputs if isinstance(inp, HostedVectorStoreContent)
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
                        location: dict[str, str] | None = (
                            tool.additional_properties.get("user_location", None)
                            if tool.additional_properties
                            else None
                        )
                        response_tools.append(
                            WebSearchToolParam(
                                type="web_search",
                                user_location=WebSearchUserLocation(
                                    type="approximate",
                                    city=location.get("city", None),
                                    country=location.get("country", None),
                                    region=location.get("region", None),
                                    timezone=location.get("timezone", None),
                                )
                                if location
                                else None,
                            )
                        )
                    case _:
                        logger.debug("Unsupported tool passed (type: %s)", type(tool))
            else:
                # Handle raw dictionary tools
                tool_dict = tool if isinstance(tool, dict) else dict(tool)

                # Special handling for image_generation tools
                if tool_dict.get("type") == "image_generation":
                    # Create a copy to avoid modifying the original
                    mapped_tool = tool_dict.copy()

                    # Map user-friendly parameter names to OpenAI API parameter names
                    parameter_mapping = {
                        "format": "output_format",
                        "compression": "output_compression",
                    }

                    for user_param, api_param in parameter_mapping.items():
                        if user_param in mapped_tool:
                            # Map the parameter name and remove the old one
                            mapped_tool[api_param] = mapped_tool.pop(user_param)

                    # Validate partial_images parameter for streaming image generation
                    # OpenAI API requires partial_images to be between 0-3 (inclusive) for image_generation tool
                    # Reference: https://platform.openai.com/docs/api-reference/responses/create#responses_create-tools-image_generation_tool-partial_images
                    if "partial_images" in mapped_tool:
                        partial_images = mapped_tool["partial_images"]
                        if not isinstance(partial_images, int) or partial_images < 0 or partial_images > 3:
                            raise ValueError("partial_images must be an integer between 0 and 3 (inclusive).")

                    response_tools.append(mapped_tool)
                else:
                    response_tools.append(tool_dict)
        return response_tools

    def get_mcp_tool(self, tool: HostedMCPTool) -> Any:
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

    async def prepare_options(
        self, messages: MutableSequence[ChatMessage], chat_options: ChatOptions
    ) -> dict[str, Any]:
        """Take ChatOptions and create the specific options for Responses API."""
        run_options: dict[str, Any] = chat_options.to_dict(
            exclude={
                "type",
                "presence_penalty",  # not supported
                "frequency_penalty",  # not supported
                "logit_bias",  # not supported
                "seed",  # not supported
                "stop",  # not supported
                "instructions",  # already added as system message
            }
        )

        if chat_options.response_format:
            run_options["response_format"] = chat_options.response_format

        translations = {
            "model_id": "model",
            "allow_multiple_tool_calls": "parallel_tool_calls",
            "conversation_id": "previous_response_id",
            "max_tokens": "max_output_tokens",
        }
        for old_key, new_key in translations.items():
            if old_key in run_options and old_key != new_key:
                run_options[new_key] = run_options.pop(old_key)

        # tools
        if chat_options.tools is None:
            run_options.pop("parallel_tool_calls", None)
        else:
            run_options["tools"] = self._tools_to_response_tools(chat_options.tools)

        # model id
        if not run_options.get("model"):
            if not self.model_id:
                raise ValueError("model_id must be a non-empty string")
            run_options["model"] = self.model_id

        # messages
        request_input = self._prepare_chat_messages_for_request(messages)
        if not request_input:
            raise ServiceInvalidRequestError("Messages are required for chat completions")
        run_options["input"] = request_input

        # additional provider specific settings
        if additional_properties := run_options.pop("additional_properties", None):
            for key, value in additional_properties.items():
                if value is not None:
                    run_options[key] = value
        if "store" not in run_options:
            run_options["store"] = False
        if (tool_choice := run_options.get("tool_choice")) and len(tool_choice.keys()) == 1:
            run_options["tool_choice"] = tool_choice["mode"]
        return run_options

    def _prepare_chat_messages_for_request(self, chat_messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
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
                    isinstance(content, FunctionCallContent)
                    and content.additional_properties
                    and "fc_id" in content.additional_properties
                ):
                    call_id_to_id[content.call_id] = content.additional_properties["fc_id"]
        list_of_list = [self._openai_chat_message_parser(message, call_id_to_id) for message in chat_messages]
        # Flatten the list of lists into a single list
        return list(chain.from_iterable(list_of_list))

    def _openai_chat_message_parser(
        self,
        message: ChatMessage,
        call_id_to_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Parse a chat message into the openai format."""
        all_messages: list[dict[str, Any]] = []
        args: dict[str, Any] = {
            "role": message.role.value if isinstance(message.role, Role) else message.role,
        }
        if message.additional_properties:
            args["metadata"] = message.additional_properties
        for content in message.contents:
            match content:
                case TextReasoningContent():
                    # Don't send reasoning content back to model
                    continue
                case FunctionResultContent():
                    new_args: dict[str, Any] = {}
                    new_args.update(self._openai_content_parser(message.role, content, call_id_to_id))
                    all_messages.append(new_args)
                case FunctionCallContent():
                    function_call = self._openai_content_parser(message.role, content, call_id_to_id)
                    all_messages.append(function_call)  # type: ignore
                case FunctionApprovalResponseContent() | FunctionApprovalRequestContent():
                    all_messages.append(self._openai_content_parser(message.role, content, call_id_to_id))  # type: ignore
                case _:
                    if "content" not in args:
                        args["content"] = []
                    args["content"].append(self._openai_content_parser(message.role, content, call_id_to_id))  # type: ignore
        if "content" in args or "tool_calls" in args:
            all_messages.append(args)
        return all_messages

    def _openai_content_parser(
        self,
        role: Role,
        content: Contents,
        call_id_to_id: dict[str, str],
    ) -> dict[str, Any]:
        """Parse contents into the openai format."""
        match content:
            case TextContent():
                return {
                    "type": "output_text" if role == Role.ASSISTANT else "input_text",
                    "text": content.text,
                }
            case TextReasoningContent():
                ret: dict[str, Any] = {
                    "type": "reasoning",
                    "summary": {
                        "type": "summary_text",
                        "text": content.text,
                    },
                }
                if content.additional_properties is not None:
                    if status := content.additional_properties.get("status"):
                        ret["status"] = status
                    if reasoning_text := content.additional_properties.get("reasoning_text"):
                        ret["content"] = {"type": "reasoning_text", "text": reasoning_text}
                    if encrypted_content := content.additional_properties.get("encrypted_content"):
                        ret["encrypted_content"] = encrypted_content
                return ret
            case DataContent() | UriContent():
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
            case FunctionCallContent():
                return {
                    "call_id": content.call_id,
                    "id": call_id_to_id[content.call_id],
                    "type": "function_call",
                    "name": content.name,
                    "arguments": content.arguments,
                    "status": None,
                }
            case FunctionResultContent():
                # call_id for the result needs to be the same as the call_id for the function call
                args: dict[str, Any] = {
                    "call_id": content.call_id,
                    "type": "function_call_output",
                }
                if content.result:
                    args["output"] = prepare_function_call_results(content.result)
                return args
            case FunctionApprovalRequestContent():
                return {
                    "type": "mcp_approval_request",
                    "id": content.id,
                    "arguments": content.function_call.arguments,
                    "name": content.function_call.name,
                    "server_label": content.function_call.additional_properties.get("server_label")
                    if content.function_call.additional_properties
                    else None,
                }
            case FunctionApprovalResponseContent():
                return {
                    "type": "mcp_approval_response",
                    "approval_request_id": content.id,
                    "approve": content.approved,
                }
            case HostedFileContent():
                return {
                    "type": "input_file",
                    "file_id": content.file_id,
                }
            case _:  # should catch UsageDetails and ErrorContent and HostedVectorStoreContent
                logger.debug("Unsupported content type passed (type: %s)", type(content))
                return {}

    # region Response creation methods

    def _create_response_content(
        self,
        response: OpenAIResponse | ParsedResponse[BaseModel],
        chat_options: ChatOptions,
    ) -> "ChatResponse":
        """Create a chat message content object from a choice."""
        structured_response: BaseModel | None = response.output_parsed if isinstance(response, ParsedResponse) else None  # type: ignore[reportUnknownMemberType]

        metadata: dict[str, Any] = response.metadata or {}
        contents: list[Contents] = []
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
                                text_content = TextContent(
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
                                                    CitationAnnotation(
                                                        file_id=annotation.file_id,
                                                        additional_properties={
                                                            "index": annotation.index,
                                                        },
                                                        raw_representation=annotation,
                                                    )
                                                )
                                            case "file_citation":
                                                text_content.annotations.append(
                                                    CitationAnnotation(
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
                                                    CitationAnnotation(
                                                        title=annotation.title,
                                                        url=annotation.url,
                                                        annotated_regions=[
                                                            TextSpanRegion(
                                                                start_index=annotation.start_index,
                                                                end_index=annotation.end_index,
                                                            )
                                                        ],
                                                        raw_representation=annotation,
                                                    )
                                                )
                                            case "container_file_citation":
                                                text_content.annotations.append(
                                                    CitationAnnotation(
                                                        file_id=annotation.file_id,
                                                        url=annotation.filename,
                                                        additional_properties={
                                                            "container_id": annotation.container_id,
                                                        },
                                                        annotated_regions=[
                                                            TextSpanRegion(
                                                                start_index=annotation.start_index,
                                                                end_index=annotation.end_index,
                                                            )
                                                        ],
                                                        raw_representation=annotation,
                                                    )
                                                )
                                            case _:
                                                logger.debug("Unparsed annotation type: %s", annotation.type)
                                contents.append(text_content)
                            case "refusal":
                                contents.append(
                                    TextContent(text=message_content.refusal, raw_representation=message_content)
                                )
                case "reasoning":  # ResponseOutputReasoning
                    if hasattr(item, "content") and item.content:
                        for index, reasoning_content in enumerate(item.content):
                            additional_properties = None
                            if hasattr(item, "summary") and item.summary and index < len(item.summary):
                                additional_properties = {"summary": item.summary[index]}
                            contents.append(
                                TextReasoningContent(
                                    text=reasoning_content.text,
                                    raw_representation=reasoning_content,
                                    additional_properties=additional_properties,
                                )
                            )
                    if hasattr(item, "summary") and item.summary:
                        for summary in item.summary:
                            contents.append(
                                TextReasoningContent(text=summary.text, raw_representation=summary)  # type: ignore[arg-type]
                            )
                case "code_interpreter_call":  # ResponseOutputCodeInterpreterCall
                    if hasattr(item, "outputs") and item.outputs:
                        for code_output in item.outputs:
                            if code_output.type == "logs":
                                contents.append(TextContent(text=code_output.logs, raw_representation=item))
                            if code_output.type == "image":
                                contents.append(
                                    UriContent(
                                        uri=code_output.url,
                                        raw_representation=item,
                                        # no more specific media type then this can be inferred
                                        media_type="image",
                                    )
                                )
                    elif hasattr(item, "code") and item.code:
                        # fallback if no output was returned is the code:
                        contents.append(TextContent(text=item.code, raw_representation=item))
                case "function_call":  # ResponseOutputFunctionCall
                    contents.append(
                        FunctionCallContent(
                            call_id=item.call_id if hasattr(item, "call_id") and item.call_id else "",
                            name=item.name if hasattr(item, "name") else "",
                            arguments=item.arguments if hasattr(item, "arguments") else "",
                            additional_properties={"fc_id": item.id} if hasattr(item, "id") else {},
                            raw_representation=item,
                        )
                    )
                case "mcp_approval_request":  # ResponseOutputMcpApprovalRequest
                    contents.append(
                        FunctionApprovalRequestContent(
                            id=item.id,
                            function_call=FunctionCallContent(
                                call_id=item.id,
                                name=item.name,
                                arguments=item.arguments,
                                additional_properties={"server_label": item.server_label},
                                raw_representation=item,
                            ),
                        )
                    )
                case "image_generation_call":  # ResponseOutputImageGenerationCall
                    if item.result:
                        # Handle the result as either a proper data URI or raw base64 string
                        uri = item.result
                        media_type = None
                        if not uri.startswith("data:"):
                            # Raw base64 string - convert to proper data URI format using helper
                            uri, media_type = DataContent.create_data_uri_from_base64(uri)
                        else:
                            # Parse media type from existing data URI
                            try:
                                # Extract media type from data URI (e.g., "data:image/png;base64,...")
                                if ";" in uri and uri.startswith("data:"):
                                    media_type = uri.split(";")[0].split(":", 1)[1]
                            except Exception:
                                # Fallback if parsing fails
                                media_type = "image"
                        contents.append(
                            DataContent(
                                uri=uri,
                                media_type=media_type,
                                raw_representation=item,
                            )
                        )
                # TODO(peterychang): Add support for other content types
                case _:
                    logger.debug("Unparsed output of type: %s: %s", item.type, item)
        response_message = ChatMessage(role="assistant", contents=contents)
        args: dict[str, Any] = {
            "response_id": response.id,
            "created_at": datetime.fromtimestamp(response.created_at).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "messages": response_message,
            "model_id": response.model,
            "additional_properties": metadata,
            "raw_representation": response,
        }
        if chat_options.store:
            args["conversation_id"] = self.get_conversation_id(response, chat_options.store)
        if response.usage and (usage_details := self._usage_details_from_openai(response.usage)):
            args["usage_details"] = usage_details
        if structured_response:
            args["value"] = structured_response
        elif chat_options.response_format:
            args["response_format"] = chat_options.response_format
        return ChatResponse(**args)

    def _create_streaming_response_content(
        self,
        event: OpenAIResponseStreamEvent,
        chat_options: ChatOptions,
        function_call_ids: dict[int, tuple[str, str]],
    ) -> ChatResponseUpdate:
        """Create a streaming chat message content object from a choice."""
        metadata: dict[str, Any] = {}
        contents: list[Contents] = []
        conversation_id: str | None = None
        model = self.model_id
        # TODO(peterychang): Add support for other content types
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
                        contents.append(TextContent(text=event_part.text, raw_representation=event))
                        metadata.update(self._get_metadata_from_response(event_part))
                    case "refusal":
                        contents.append(TextContent(text=event_part.refusal, raw_representation=event))
            case "response.output_text.delta":
                contents.append(TextContent(text=event.delta, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_text.delta":
                contents.append(TextReasoningContent(text=event.delta, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_text.done":
                contents.append(TextReasoningContent(text=event.text, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_summary_text.delta":
                contents.append(TextReasoningContent(text=event.delta, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case "response.reasoning_summary_text.done":
                contents.append(TextReasoningContent(text=event.text, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case "response.completed":
                conversation_id = self.get_conversation_id(event.response, chat_options.store)
                model = event.response.model
                if event.response.usage:
                    usage = self._usage_details_from_openai(event.response.usage)
                    if usage:
                        contents.append(UsageContent(details=usage, raw_representation=event))
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
                        function_call_ids[event.output_index] = (event_item.call_id, event_item.name)
                    case "mcp_approval_request":
                        contents.append(
                            FunctionApprovalRequestContent(
                                id=event_item.id,
                                function_call=FunctionCallContent(
                                    call_id=event_item.id,
                                    name=event_item.name,
                                    arguments=event_item.arguments,
                                    additional_properties={"server_label": event_item.server_label},
                                    raw_representation=event_item,
                                ),
                            )
                        )
                    case "code_interpreter_call":  # ResponseOutputCodeInterpreterCall
                        if hasattr(event_item, "outputs") and event_item.outputs:
                            for code_output in event_item.outputs:
                                if code_output.type == "logs":
                                    contents.append(TextContent(text=code_output.logs, raw_representation=event_item))
                                if code_output.type == "image":
                                    contents.append(
                                        UriContent(
                                            uri=code_output.url,
                                            raw_representation=event_item,
                                            # no more specific media type then this can be inferred
                                            media_type="image",
                                        )
                                    )
                        elif hasattr(event_item, "code") and event_item.code:
                            # fallback if no output was returned is the code:
                            contents.append(TextContent(text=event_item.code, raw_representation=event_item))
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
                                    TextReasoningContent(
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
                        FunctionCallContent(
                            call_id=call_id,
                            name=name,
                            arguments=event.delta,
                            additional_properties={"output_index": event.output_index, "fc_id": event.item_id},
                            raw_representation=event,
                        )
                    )
            case "response.image_generation_call.partial_image":
                # Handle streaming partial image generation
                image_base64 = event.partial_image_b64
                partial_index = event.partial_image_index

                # Use helper function to create data URI from base64
                uri, media_type = DataContent.create_data_uri_from_base64(image_base64)

                contents.append(
                    DataContent(
                        uri=uri,
                        media_type=media_type,
                        additional_properties={
                            "partial_image_index": partial_index,
                            "is_partial_image": True,
                        },
                        raw_representation=event,
                    )
                )
            case _:
                logger.debug("Unparsed event of type: %s: %s", event.type, event)

        return ChatResponseUpdate(
            contents=contents,
            conversation_id=conversation_id,
            role=Role.ASSISTANT,
            model_id=model,
            additional_properties=metadata,
            raw_representation=event,
        )

    def _usage_details_from_openai(self, usage: ResponseUsage) -> UsageDetails | None:
        details = UsageDetails(
            input_token_count=usage.input_tokens,
            output_token_count=usage.output_tokens,
            total_token_count=usage.total_tokens,
        )
        if usage.input_tokens_details and usage.input_tokens_details.cached_tokens:
            details["openai.cached_input_tokens"] = usage.input_tokens_details.cached_tokens
        if usage.output_tokens_details and usage.output_tokens_details.reasoning_tokens:
            details["openai.reasoning_tokens"] = usage.output_tokens_details.reasoning_tokens
        return details

    def _get_metadata_from_response(self, output: Any) -> dict[str, Any]:
        """Get metadata from a chat choice."""
        if logprobs := getattr(output, "logprobs", None):
            return {
                "logprobs": logprobs,
            }
        return {}


TOpenAIResponsesClient = TypeVar("TOpenAIResponsesClient", bound="OpenAIResponsesClient")


@use_function_invocation
@use_observability
@use_chat_middleware
class OpenAIResponsesClient(OpenAIConfigMixin, OpenAIBaseResponsesClient):
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
