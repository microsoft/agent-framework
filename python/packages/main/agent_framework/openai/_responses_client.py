# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import AsyncIterable, Callable, Mapping, MutableMapping, MutableSequence, Sequence
from datetime import datetime
from itertools import chain
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from openai import AsyncOpenAI, BadRequestError
from openai.types.responses.file_search_tool_param import FileSearchToolParam
from openai.types.responses.function_tool_param import FunctionToolParam
from openai.types.responses.parsed_response import (
    ParsedResponse,
)
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_completed_event import ResponseCompletedEvent
from openai.types.responses.response_content_part_added_event import ResponseContentPartAddedEvent
from openai.types.responses.response_function_call_arguments_delta_event import ResponseFunctionCallArgumentsDeltaEvent
from openai.types.responses.response_output_item_added_event import ResponseOutputItemAddedEvent
from openai.types.responses.response_output_refusal import ResponseOutputRefusal
from openai.types.responses.response_output_text import ResponseOutputText
from openai.types.responses.response_stream_event import ResponseStreamEvent as OpenAIResponseStreamEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from openai.types.responses.response_usage import ResponseUsage
from openai.types.responses.tool_param import (
    CodeInterpreter,
    CodeInterpreterContainerCodeInterpreterToolAuto,
    ToolParam,
)
from openai.types.responses.web_search_tool_param import UserLocation as WebSearchUserLocation
from openai.types.responses.web_search_tool_param import WebSearchToolParam
from pydantic import BaseModel, SecretStr, ValidationError

from agent_framework import DataContent, TextReasoningContent, UriContent, UsageContent

from .._clients import ChatClientBase, use_tool_calling
from .._logging import get_logger
from .._tools import AIFunction, AITool, HostedCodeInterpreterTool, HostedFileSearchTool, HostedWebSearchTool
from .._types import (
    AIContents,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    CitationAnnotation,
    FunctionCallContent,
    FunctionResultContent,
    HostedFileContent,
    HostedVectorStoreContent,
    TextContent,
    TextSpanRegion,
    UsageDetails,
)
from ..exceptions import (
    ServiceInitializationError,
    ServiceInvalidRequestError,
    ServiceResponseException,
)
from ..telemetry import use_telemetry
from ._exceptions import OpenAIContentFilterException
from ._shared import OpenAIConfigBase, OpenAIHandler, OpenAISettings, prepare_function_call_results

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover

if TYPE_CHECKING:
    from openai.types.responses.response_includable import ResponseIncludable

    from .._types import ChatToolMode


logger = get_logger("agent_framework.openai")

__all__ = ["OpenAIResponsesClient"]

# region ResponsesClient


class OpenAIResponsesClientBase(OpenAIHandler, ChatClientBase):
    """Base class for all OpenAI Responses based API's."""

    FILE_SEARCH_MAX_RESULTS: int = 50

    def _filter_options(self, **kwargs: Any) -> dict[str, Any]:
        """Filter options for the responses call."""
        # The responses call does not support all the options that the chat completion call does.
        # We filter out the unsupported options.
        return {key: value for key, value in kwargs.items() if value is not None}

    @override
    async def get_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        *,
        include: list["ResponseIncludable"] | None = None,
        instructions: str | None = None,
        max_tokens: int | None = None,
        parallel_tool_calls: bool | None = None,
        model: str | None = None,
        previous_response_id: str | None = None,
        reasoning: dict[str, str] | None = None,
        service_tier: str | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: "ChatToolMode" | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: AITool
        | list[AITool]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        truncation: str | None = None,
        timeout: float | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Get a response from the OpenAI API.

        Args:
            messages: the message or messages to send to the model
            include: additional output data to include in the model response.
            instructions: a system (or developer) message inserted into the model's context.
            max_tokens: The maximum number of tokens to generate.
            parallel_tool_calls: Whether to enable parallel tool calls.
            model: The model to use for the agent.
            previous_response_id: The ID of the previous response.
            reasoning: The reasoning to use for the response.
            service_tier: The service tier to use for the response.
            response_format: The format of the response.
            seed: The random seed to use for the response.
            store: whether to store the response.
            temperature: the sampling temperature to use.
            tool_choice: the tool choice for the request.
            tools: the tools to use for the request.
            top_p: the nucleus sampling probability to use.
            user: the user to associate with the request.
            truncation: the truncation strategy to use.
            timeout: the timeout for the request.
            additional_properties: additional properties to include in the request.
            kwargs: any additional keyword arguments,
                will only be passed to functions that are called.

        Returns:
            A chat response from the model.
        """
        additional_properties = additional_properties or {}
        additional_properties.update(
            self._filter_options(
                include=include,
                instructions=instructions,
                parallel_tool_calls=parallel_tool_calls,
                model=model,
                previous_response_id=previous_response_id,
                reasoning=reasoning,
                service_tier=service_tier,
                truncation=truncation,
                timeout=timeout,
            )
        )

        return await super().get_response(
            messages=messages,
            max_tokens=max_tokens,
            response_format=response_format,
            seed=seed,
            store=store,
            temperature=temperature,
            tool_choice=tool_choice,
            tools=tools,  # type: ignore
            top_p=top_p,
            user=user,
            additional_properties=additional_properties,
            **kwargs,
        )

    @override
    async def get_streaming_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        *,
        # TODO(peterychang): enable this option. background: bool | None = None,
        include: list["ResponseIncludable"] | None = None,
        instructions: str | None = None,
        max_tokens: int | None = None,
        parallel_tool_calls: bool | None = None,
        model: str | None = None,
        previous_response_id: str | None = None,
        reasoning: dict[str, str] | None = None,
        service_tier: str | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: "ChatToolMode" | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: AITool
        | list[AITool]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        truncation: str | None = None,
        timeout: float | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Get a streaming response from the OpenAI API.

        Args:
            messages: the message or messages to send to the model
            include: additional output data to include in the model response.
            instructions: a system (or developer) message inserted into the model's context.
            max_tokens: The maximum number of tokens to generate.
            parallel_tool_calls: Whether to enable parallel tool calls.
            model: The model to use for the agent.
            previous_response_id: The ID of the previous response.
            reasoning: The reasoning to use for the response.
            service_tier: The service tier to use for the response.
            response_format: The format of the response.
            seed: The random seed to use for the response.
            store: whether to store the response.
            temperature: the sampling temperature to use.
            tool_choice: the tool choice for the request.
            tools: the tools to use for the request.
            top_p: the nucleus sampling probability to use.
            user: the user to associate with the request.
            truncation: the truncation strategy to use.
            timeout: the timeout for the request.
            additional_properties: additional properties to include in the request.
            kwargs: any additional keyword arguments,
                will only be passed to functions that are called.

        Returns:
            A stream representing the response(s) from the LLM.
        """
        additional_properties = additional_properties or {}
        additional_properties.update(
            self._filter_options(
                include=include,
                instructions=instructions,
                parallel_tool_calls=parallel_tool_calls,
                model=model,
                previous_response_id=previous_response_id,
                reasoning=reasoning,
                service_tier=service_tier,
                truncation=truncation,
                timeout=timeout,
            )
        )

        async for update in super().get_streaming_response(
            messages=messages,
            max_tokens=max_tokens,
            response_format=response_format,
            seed=seed,
            store=store,
            temperature=temperature,
            tool_choice=tool_choice,
            tools=tools,  # type: ignore
            top_p=top_p,
            user=user,
            additional_properties=additional_properties,
            **kwargs,
        ):
            yield update

    # region Inner Methods

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        options_dict = self._prepare_options(messages, chat_options)
        try:
            if not chat_options.response_format:
                response = await self.client.responses.create(
                    stream=False,
                    **options_dict,
                )
                chat_options.conversation_id = response.id if chat_options.store is True else None
                return self._create_response_content(response, chat_options=chat_options)
            # create call does not support response_format, so we need to handle it via parse call
            resp_format = chat_options.response_format
            parsed_response: ParsedResponse[BaseModel] = await self.client.responses.parse(
                text_format=resp_format,
                stream=False,
                **options_dict,
            )
            chat_options.conversation_id = parsed_response.id if chat_options.store is True else None
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
        options_dict = self._prepare_options(messages, chat_options)
        function_call_ids: dict[int, tuple[str, str]] = {}  # output_index: (call_id, name)
        try:
            if not chat_options.response_format:
                response = await self.client.responses.create(
                    stream=True,
                    **options_dict,
                )
                async for chunk in response:
                    update = self._create_streaming_response_content(
                        chunk, chat_options=chat_options, function_call_ids=function_call_ids
                    )
                    yield update
                return
            # create call does not support response_format, so we need to handle it via stream call
            async with self.client.responses.stream(
                text_format=chat_options.response_format,
                **options_dict,
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

    # region Prep methods

    def _chat_to_response_tool_spec(
        self, tools: list[AITool | MutableMapping[str, Any]]
    ) -> list[ToolParam | dict[str, Any]]:
        response_tools: list[ToolParam | dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, AITool):
                match tool:
                    case HostedCodeInterpreterTool():
                        tool_args: dict[str, Any] = {"type": "auto"}
                        if tool.inputs:
                            tool_args["file_ids"] = []
                            for tool_input in tool.inputs:
                                if isinstance(tool_input, HostedFileContent):
                                    tool_args["file_ids"].append(tool_input.file_id)
                            if not tool_args["file_ids"]:
                                tool_args.pop("file_ids")
                        response_tools.append(
                            CodeInterpreter(
                                type="code_interpreter",
                                container=CodeInterpreterContainerCodeInterpreterToolAuto(**tool_args),  # type: ignore[typeddict-item]
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
                                type="web_search_preview",
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
                response_tools.append(tool if isinstance(tool, dict) else dict(tool))
        return response_tools

    def _prepare_options(self, messages: MutableSequence[ChatMessage], chat_options: ChatOptions) -> dict[str, Any]:
        """Take ChatOptions and create the specific options for Responses."""
        options_dict = chat_options.to_provider_settings(exclude={"response_format"})
        # messages
        request_input = self._prepare_chat_messages_for_request(messages)
        if not request_input:
            raise ServiceInvalidRequestError("Messages are required for chat completions")
        options_dict["input"] = request_input
        # tools
        if chat_options.tools is None:
            options_dict.pop("parallel_tool_calls", None)
        else:
            options_dict["tools"] = self._chat_to_response_tool_spec(chat_options.tools)
        # other settings
        if "store" not in options_dict:
            options_dict["store"] = False
        if "conversation_id" in options_dict:
            options_dict["previous_response_id"] = options_dict["conversation_id"]
            options_dict.pop("conversation_id")
        if "model" not in options_dict:
            options_dict["model"] = self.ai_model_id
        return options_dict

    def _prepare_chat_messages_for_request(self, chat_messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
        """Prepare the chat messages for a request.

        Allowing customization of the key names for role/author, and optionally overriding the role.

        ChatRole.TOOL messages need to be formatted different than system/user/assistant messages:
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

    # region Response creation methods

    def _create_response_content(
        self,
        response: OpenAIResponse | ParsedResponse[BaseModel],
        chat_options: ChatOptions,
    ) -> "ChatResponse":
        """Create a chat message content object from a choice."""
        structured_response: BaseModel | None = response.output_parsed if isinstance(response, ParsedResponse) else None  # type: ignore[reportUnknownMemberType]

        metadata: dict[str, Any] = response.metadata or {}
        contents: list[AIContents] = []
        for item in response.output:  # type: ignore[reportUnknownMemberType]
            match item.type:
                # types:
                # ParsedResponseOutputMessage[Unknown] |
                # ParsedResponseFunctionToolCall |
                # ResponseFileSearchToolCall |
                # ResponseFunctionWebSearch |
                # ResponseComputerToolCall |
                # ResponseReasoningItem |
                # McpCall |
                # McpApprovalRequest |
                # ImageGenerationCall |
                # LocalShellCall |
                # LocalShellCallAction |
                # McpListTools |
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
                                    text=message_content.text, raw_representation=message_content
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
                    if item.content:
                        for index, reasoning_content in enumerate(item.content):
                            additional_properties = None
                            if item.summary and index < len(item.summary):
                                additional_properties = {"summary": item.summary[index]}
                            contents.append(
                                TextReasoningContent(
                                    text=reasoning_content.text,
                                    raw_representation=reasoning_content,
                                    additional_properties=additional_properties,
                                )
                            )
                case "code_interpreter_call":  # ResponseOutputCodeInterpreterCall
                    if item.outputs:
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
                    elif item.code:
                        # fallback if no output was returned is the code:
                        contents.append(TextContent(text=item.code, raw_representation=item))
                case "function_call":  # ResponseOutputFunctionCall
                    contents.append(
                        FunctionCallContent(
                            call_id=item.call_id if item.call_id else "",
                            name=item.name,
                            arguments=item.arguments,
                            additional_properties={"fc_id": item.id},
                            raw_representation=item,
                        )
                    )
                case "image_generation_call":  # ResponseOutputImageGenerationCall
                    if item.result:
                        contents.append(
                            DataContent(
                                uri=item.result,
                                raw_representation=item,
                            )
                        )
                # TODO(peterychang): Add support for other content types
                case _:
                    logger.debug("Unparsed content of type: %s: %s", item.type, item)
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
            args["conversation_id"] = response.id
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
        items: list[AIContents] = []
        conversation_id: str | None = None
        model = self.ai_model_id
        # TODO(peterychang): Add support for other content types
        match event:
            case ResponseContentPartAddedEvent():
                match event.part:
                    case ResponseOutputText():
                        items.append(TextContent(text=event.part.text, raw_representation=event))
                        metadata.update(self._get_metadata_from_response(event.part))
                    case ResponseOutputRefusal():
                        items.append(TextContent(text=event.part.refusal, raw_representation=event))
            case ResponseTextDeltaEvent():
                items.append(TextContent(text=event.delta, raw_representation=event))
                metadata.update(self._get_metadata_from_response(event))
            case ResponseCompletedEvent():
                conversation_id = event.response.id if chat_options.store is True else None
                model = event.response.model
                if event.response.usage:
                    usage = self._usage_details_from_openai(event.response.usage)
                    if usage:
                        items.append(UsageContent(details=usage, raw_representation=event))
            case ResponseOutputItemAddedEvent():
                if event.item.type == "function_call":
                    function_call_ids[event.output_index] = (event.item.call_id, event.item.name)
            case ResponseFunctionCallArgumentsDeltaEvent():
                call_id, name = function_call_ids.get(event.output_index, (None, None))
                if call_id and name:
                    items.append(
                        FunctionCallContent(
                            call_id=call_id,
                            name=name,
                            arguments=event.delta,
                            additional_properties={"output_index": event.output_index, "fc_id": event.item_id},
                            raw_representation=event,
                        )
                    )
            case _:
                logger.debug("Unparsed event: %s", event)

        return ChatResponseUpdate(
            contents=items,
            conversation_id=conversation_id,
            role=ChatRole.ASSISTANT,
            ai_model_id=model,
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

    def _openai_chat_message_parser(
        self,
        message: ChatMessage,
        call_id_to_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Parse a chat message into the openai format."""
        all_messages: list[dict[str, Any]] = []
        args: dict[str, Any] = {
            "role": message.role.value if isinstance(message.role, ChatRole) else message.role,
        }
        if message.additional_properties:
            args["metadata"] = message.additional_properties
        for content in message.contents:
            match content:
                case FunctionResultContent():
                    new_args: dict[str, Any] = {}
                    new_args.update(self._openai_content_parser(message.role, content, call_id_to_id))
                    all_messages.append(new_args)
                case FunctionCallContent():
                    function_call = self._openai_content_parser(message.role, content, call_id_to_id)
                    all_messages.append(function_call)  # type: ignore
                case _:
                    if "content" not in args:
                        args["content"] = []
                    args["content"].append(self._openai_content_parser(message.role, content, call_id_to_id))  # type: ignore
        if "content" in args or "tool_calls" in args:
            all_messages.append(args)
        return all_messages

    def _openai_content_parser(
        self,
        role: ChatRole,
        content: AIContents,
        call_id_to_id: dict[str, str],
    ) -> dict[str, Any]:
        """Parse contents into the openai format."""
        match content:
            case FunctionCallContent():
                return {
                    "call_id": content.call_id,
                    "id": call_id_to_id[content.call_id],
                    "type": "function_call",
                    "name": content.name,
                    "arguments": content.arguments,
                }
            case FunctionResultContent():
                # call_id for the result needs to be the same as the call_id for the function call
                args: dict[str, Any] = {
                    "call_id": content.call_id,
                    "id": call_id_to_id.get(content.call_id),
                    "type": "function_call_output",
                }
                if content.result:
                    args["output"] = prepare_function_call_results(content.result)
                return args
            case TextContent():
                return {
                    "type": "output_text" if role == ChatRole.ASSISTANT else "input_text",
                    "text": content.text,
                }
            # TODO(peterychang): We'll probably need to specialize the other content types as well
            case _:
                return content.model_dump(exclude_none=True)

    def _get_metadata_from_response(self, output: Any) -> dict[str, Any]:
        """Get metadata from a chat choice."""
        if logprobs := getattr(output, "logprobs", None):
            return {
                "logprobs": logprobs,
            }
        return {}


TOpenAIResponsesClient = TypeVar("TOpenAIResponsesClient", bound="OpenAIResponsesClient")


@use_telemetry
@use_tool_calling
class OpenAIResponsesClient(OpenAIConfigBase, OpenAIResponsesClientBase):
    """OpenAI Responses client class."""

    def __init__(
        self,
        ai_model_id: str | None = None,
        api_key: str | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an OpenAIChatCompletion service.

        Args:
            ai_model_id: OpenAI model name, see
                https://platform.openai.com/docs/models
            api_key: The optional API key to use. If provided will override,
                the env vars or .env file value.
            org_id: The optional org ID to use. If provided will override,
                the env vars or .env file value.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests. (Optional)
            async_client: An existing client to use. (Optional)
            instruction_role: The role to use for 'instruction' messages, for example,
                "system" or "developer". If not provided, the default is "system".
            env_file_path: Use the environment settings file as a fallback
                to environment variables. (Optional)
            env_file_encoding: The encoding of the environment settings file. (Optional)
        """
        try:
            openai_settings = OpenAISettings(
                api_key=SecretStr(api_key) if api_key else None,
                org_id=org_id,
                responses_model_id=ai_model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create OpenAI settings.", ex) from ex

        if not async_client and not openai_settings.api_key:
            raise ServiceInitializationError("The OpenAI API key is required.")
        if not openai_settings.responses_model_id:
            raise ServiceInitializationError("The OpenAI model ID is required.")

        super().__init__(
            ai_model_id=openai_settings.responses_model_id,
            api_key=openai_settings.api_key.get_secret_value() if openai_settings.api_key else None,
            org_id=openai_settings.org_id,
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
        )

    @classmethod
    def from_dict(cls: type[TOpenAIResponsesClient], settings: dict[str, Any]) -> TOpenAIResponsesClient:
        """Initialize an Open AI service from a dictionary of settings.

        Args:
            settings: A dictionary of settings for the service.
        """
        return cls(**settings)


# endregion
