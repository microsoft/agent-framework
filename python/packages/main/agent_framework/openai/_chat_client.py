# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import AsyncIterable, Callable, Mapping, MutableMapping, MutableSequence, Sequence
from datetime import datetime
from itertools import chain
from typing import Any, ClassVar, Literal, cast, override

from openai import AsyncOpenAI, AsyncStream
from openai.types import CompletionUsage
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, ChoiceDeltaToolCall
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_completed_event import ResponseCompletedEvent
from openai.types.responses.response_content_part_added_event import ResponseContentPartAddedEvent
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall
from openai.types.responses.response_includable import ResponseIncludable
from openai.types.responses.response_output_item import ResponseOutputItem
from openai.types.responses.response_output_message import ResponseOutputMessage
from openai.types.responses.response_output_refusal import ResponseOutputRefusal
from openai.types.responses.response_output_text import ResponseOutputText
from openai.types.responses.response_stream_event import ResponseStreamEvent as OpenAIResponseStreamEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from openai.types.responses.response_usage import ResponseUsage
from pydantic import BaseModel, SecretStr, ValidationError

from .._clients import ChatClientBase, use_tool_calling
from .._types import (
    AIContents,
    AITool,
    ChatFinishReason,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    ChatToolMode,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
    UsageDetails,
)
from ..exceptions import ServiceInitializationError, ServiceInvalidResponseError
from ._shared import OpenAIConfigBase, OpenAIHandler, OpenAIModelTypes, OpenAISettings

__all__ = ["OpenAIChatClient", "OpenAIResponsesClient"]


# region OpenAIChatClientBase


# Implements agent_framework.ChatClient protocol, through ChatClientBase
@use_tool_calling
class OpenAIChatClientBase(OpenAIHandler, ChatClientBase):
    """OpenAI Chat completion class."""

    MODEL_PROVIDER_NAME: ClassVar[str] = "openai"
    SUPPORTS_FUNCTION_CALLING: ClassVar[bool] = True

    # region Overriding base class methods
    # most of the methods are overridden from the ChatClientBase class, otherwise it is mentioned

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        chat_options.additional_properties["stream"] = False
        if not chat_options.ai_model_id:
            chat_options.ai_model_id = self.ai_model_id

        response = await self._send_request(chat_options, messages=self._prepare_chat_history_for_request(messages))
        assert isinstance(response, ChatCompletion)  # nosec  # noqa: S101
        response_metadata = self._get_metadata_from_chat_response(response)
        return next(
            self._create_chat_message_content(response, choice, response_metadata) for choice in response.choices
        )

    # @trace_streaming_chat_completion(MODEL_PROVIDER_NAME)
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        chat_options.additional_properties["stream"] = True
        chat_options.additional_properties["stream_options"] = {"include_usage": True}
        chat_options.ai_model_id = chat_options.ai_model_id or self.ai_model_id

        response = await self._send_request(chat_options, messages=self._prepare_chat_history_for_request(messages))
        if not isinstance(response, AsyncStream):
            raise ServiceInvalidResponseError("Expected an AsyncStream[ChatCompletionChunk] response.")
        async for chunk in response:
            assert isinstance(chunk, ChatCompletionChunk)  # nosec  # noqa: S101
            if len(chunk.choices) == 0 and chunk.usage is None:
                continue

            assert isinstance(chunk, ChatCompletionChunk)  # nosec  # noqa: S101
            chunk_metadata = self._get_metadata_from_streaming_chat_response(chunk)
            if chunk.usage is not None:
                # Usage is contained in the last chunk where the choices are empty
                # We are duplicating the usage metadata to all the choices in the response
                yield ChatResponseUpdate(
                    role=ChatRole.ASSISTANT,
                    contents=[],
                    ai_model_id=chat_options.ai_model_id,
                    additional_properties=chunk_metadata,
                )

            else:
                yield next(
                    self._create_streaming_chat_message_content(chunk, choice, chunk_metadata)
                    for choice in chunk.choices
                )

    # endregion

    # region content creation

    def _create_chat_message_content(
        self, response: ChatCompletion, choice: Choice, response_metadata: dict[str, Any]
    ) -> "ChatResponse":
        """Create a chat message content object from a choice."""
        metadata = self._get_metadata_from_chat_choice(choice)
        metadata.update(response_metadata)
        items: MutableSequence[ChatMessage] = []
        if parsed_tool_calls := [tool for tool in self._get_tool_calls_from_chat_choice(choice)]:
            items.append(ChatMessage(role="assistant", contents=parsed_tool_calls))
        if choice.message.content:
            items.append(ChatMessage(role="assistant", text=choice.message.content))
        elif hasattr(choice.message, "refusal") and choice.message.refusal:
            items.append(ChatMessage(role="assistant", text=choice.message.refusal))

        return ChatResponse(
            response_id=response.id,
            created_at=datetime.fromtimestamp(response.created).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            usage_details=self._usage_details_from_openai(response.usage) if response.usage else None,
            messages=items,
            model_id=self.ai_model_id,
            additional_properties=metadata,
            finish_reason=(ChatFinishReason(value=choice.finish_reason) if choice.finish_reason else None),
        )

    def _create_streaming_chat_message_content(
        self,
        chunk: ChatCompletionChunk,
        choice: ChunkChoice,
        chunk_metadata: dict[str, Any],
    ) -> ChatResponseUpdate:
        """Create a streaming chat message content object from a choice."""
        metadata = self._get_metadata_from_chat_choice(choice)
        metadata.update(chunk_metadata)

        items: list[Any] = self._get_tool_calls_from_chat_choice(choice)
        if choice.delta and choice.delta.content is not None:
            items.append(TextContent(text=choice.delta.content))
        return ChatResponseUpdate(
            created_at=datetime.fromtimestamp(chunk.created).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            contents=items,
            role=ChatRole.ASSISTANT,
            ai_model_id=self.ai_model_id,
            additional_properties=metadata,
            finish_reason=(ChatFinishReason(value=choice.finish_reason) if choice.finish_reason else None),
        )

    def _usage_details_from_openai(self, usage: CompletionUsage) -> UsageDetails | None:
        return UsageDetails(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )

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

    def _get_tool_calls_from_chat_choice(self, choice: Choice | ChunkChoice) -> list[AIContents]:
        """Get tool calls from a chat choice."""
        resp: list[AIContents] = []
        content = choice.message if isinstance(choice, Choice) else choice.delta
        if content and (tool_calls := getattr(content, "tool_calls", None)) is not None:
            for tool in cast(list[ChatCompletionMessageToolCall] | list[ChoiceDeltaToolCall], tool_calls):
                if tool.function:
                    fcc = FunctionCallContent(
                        call_id=tool.id if tool.id else "",
                        name=tool.function.name if tool.function.name else "",
                        arguments=tool.function.arguments if tool.function.arguments else "",
                    )
                    resp.append(fcc)

        # When you enable asynchronous content filtering in Azure OpenAI, you may receive empty deltas
        return resp

    def _prepare_chat_history_for_request(
        self,
        chat_messages: Sequence[ChatMessage],
        role_key: str = "role",
        content_key: str = "content",
    ) -> list[dict[str, Any]]:
        """Prepare the chat history for a request.

        Allowing customization of the key names for role/author, and optionally overriding the role.

        ChatRole.TOOL messages need to be formatted different than system/user/assistant messages:
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
        list_of_list = [self._openai_chat_message_parser(message) for message in chat_messages]
        # Flatten the list of lists into a single list
        return list(chain.from_iterable(list_of_list))

    # endregion

    def _openai_chat_message_parser(self, message: ChatMessage) -> list[dict[str, Any]]:
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
                    new_args = args.copy()
                    new_args["tool_call_id"] = content.call_id
                    new_args["content"] = content.result
                    all_messages.append(new_args)
                case FunctionCallContent():
                    function_call = self._openai_content_parser(content)
                    if "tool_calls" not in args:
                        args["tool_calls"] = []
                    args["tool_calls"].append(function_call)  # type: ignore
                case _:
                    if "content" not in args:
                        args["content"] = []
                    args["content"].append(self._openai_content_parser(content))  # type: ignore
        if "content" in args or "tool_calls" in args:
            all_messages.append(args)
        return all_messages

    def _openai_content_parser(self, content: AIContents) -> dict[str, Any]:
        """Parse contents into the openai format."""
        match content:
            case FunctionCallContent():
                args = json.dumps(content.arguments) if isinstance(content.arguments, Mapping) else content.arguments
                return {
                    "id": content.call_id,
                    "type": "function",
                    "function": {"name": content.name, "arguments": args},
                }
            case FunctionResultContent():
                return {
                    "tool_call_id": content.call_id,
                    "content": content.result,
                }
            case _:
                return content.model_dump(exclude_none=True)


# endregion

# region OpenAIChatClient


class OpenAIChatClient(OpenAIConfigBase, OpenAIChatClientBase):
    """OpenAI Chat completion class."""

    def __init__(
        self,
        ai_model_id: str | None = None,
        api_key: str | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
    ) -> None:
        """Initialize an OpenAIChatCompletion service.

        Args:
            ai_model_id (str): OpenAI model name, see
                https://platform.openai.com/docs/models
            api_key (str | None): The optional API key to use. If provided will override,
                the env vars or .env file value.
            org_id (str | None): The optional org ID to use. If provided will override,
                the env vars or .env file value.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests. (Optional)
            async_client (Optional[AsyncOpenAI]): An existing client to use. (Optional)
            env_file_path (str | None): Use the environment settings file as a fallback
                to environment variables. (Optional)
            env_file_encoding (str | None): The encoding of the environment settings file. (Optional)
            instruction_role (str | None): The role to use for 'instruction' messages, for example,
        """
        try:
            openai_settings = OpenAISettings(
                api_key=SecretStr(api_key) if api_key else None,
                org_id=org_id,
                chat_model_id=ai_model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create OpenAI settings.", ex) from ex

        if not async_client and not openai_settings.api_key:
            raise ServiceInitializationError("The OpenAI API key is required.")
        if not openai_settings.chat_model_id:
            raise ServiceInitializationError("The OpenAI model ID is required.")

        super().__init__(
            ai_model_id=openai_settings.chat_model_id,
            api_key=openai_settings.api_key.get_secret_value() if openai_settings.api_key else None,
            org_id=openai_settings.org_id,
            ai_model_type=OpenAIModelTypes.CHAT,
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
        )

    @classmethod
    def from_dict(cls, settings: dict[str, Any]) -> "OpenAIChatClient":
        """Initialize an Open AI service from a dictionary of settings.

        Args:
            settings: A dictionary of settings for the service.
        """
        return OpenAIChatClient(
            ai_model_id=settings["ai_model_id"],
            default_headers=settings.get("default_headers"),
        )


# endregion

# region ResponsesClient


@use_tool_calling
class OpenAIResponsesClient(OpenAIConfigBase, ChatClientBase, OpenAIHandler):
    """OpenAI Responses client class."""

    MODEL_PROVIDER_NAME: ClassVar[str] = "openai"
    SUPPORTS_FUNCTION_CALLING: ClassVar[bool] = True

    def __init__(
        self,
        ai_model_id: str | None = None,
        api_key: str | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
    ) -> None:
        """Initialize an OpenAIChatCompletion service.

        Args:
            ai_model_id (str): OpenAI model name, see
                https://platform.openai.com/docs/models
            api_key (str | None): The optional API key to use. If provided will override,
                the env vars or .env file value.
            org_id (str | None): The optional org ID to use. If provided will override,
                the env vars or .env file value.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests. (Optional)
            async_client (Optional[AsyncOpenAI]): An existing client to use. (Optional)
            env_file_path (str | None): Use the environment settings file as a fallback
                to environment variables. (Optional)
            env_file_encoding (str | None): The encoding of the environment settings file. (Optional)
            instruction_role (str | None): The role to use for 'instruction' messages, for example,
        """
        try:
            openai_settings = OpenAISettings(
                api_key=SecretStr(api_key) if api_key else None,
                org_id=org_id,
                chat_model_id=ai_model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create OpenAI settings.", ex) from ex

        if not async_client and not openai_settings.api_key:
            raise ServiceInitializationError("The OpenAI API key is required.")
        if not openai_settings.chat_model_id:
            raise ServiceInitializationError("The OpenAI model ID is required.")

        super().__init__(
            ai_model_id=openai_settings.chat_model_id,
            api_key=openai_settings.api_key.get_secret_value() if openai_settings.api_key else None,
            org_id=openai_settings.org_id,
            ai_model_type=OpenAIModelTypes.RESPONSE,
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
        )

    def _filter_options(self, **kwargs: Any) -> dict[str, Any]:
        """Filter options for the responses call."""
        # The responses call does not support all the options that the chat completion call does.
        # We filter out the unsupported options.
        return {key: value for key, value in kwargs.items() if value is not None}

    # The responses create call takes very different parameters than the chat completion call,
    # so we override the get_response method to handle the specific parameters for responses.
    @override
    async def get_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        *,
        # TODO(peterychang): enable this option. background: bool | None = None,
        include: list[ResponseIncludable] | None = None,
        instruction: str | None = None,
        max_tokens: int | None = None,
        parallel_tool_calls: bool | None = None,
        model: str | None = None,
        previous_response_id: str | None = None,
        reasoning: str | None = None,
        service_tier: str | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
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
        """Get a response from the OpenAI API."""
        filtered_options = self._filter_options(
            background=False,
            include=include,
            instruction=instruction,
            parallel_tool_calls=parallel_tool_calls,
            previous_response_id=previous_response_id,
            reasoning=reasoning,
            service_tier=service_tier,
            truncation=truncation,
            timeout=timeout,
        )
        filtered_options.update(additional_properties or {})
        chat_options = ChatOptions(
            ai_model_id=model,
            max_tokens=max_tokens,
            response_format=response_format,
            seed=seed,
            store=store,
            temperature=temperature,
            top_p=top_p,
            tool_choice=tool_choice,
            tools=tools,  # type: ignore
            user=user,
            additional_properties=filtered_options,
        )
        return await super().get_response(
            messages=messages,
            chat_options=chat_options,
            **kwargs,
        )

    def _chat_to_response_tool_spec(self, tools: list[AITool | MutableMapping[str, Any]]) -> list[dict[str, Any]]:
        response_tools: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, AITool):
                # TODO(peterychang): Support AITools
                continue
            if "function" not in tool:
                response_tools.append(tool if isinstance(tool, dict) else dict(tool))
            parameters = {"additionalProperties": False}
            parameters.update(tool.get("function", {}).get("parameters", {}))
            response_tools.append({
                "type": "function",
                "name": tool.get("function", {}).get("name", ""),
                "strict": True,
                "description": tool.get("function", {}).get("description", None),
                "parameters": parameters,
            })
        return response_tools

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        chat_options.additional_properties["stream"] = False
        if not chat_options.ai_model_id:
            chat_options.ai_model_id = self.ai_model_id
        if chat_options.tools:
            chat_options.additional_properties.update({
                "response_tools": self._chat_to_response_tool_spec(chat_options.tools)
            })
        response = await self._send_request(chat_options, messages=self._prepare_chat_history_for_request(messages))
        assert isinstance(response, OpenAIResponse)  # nosec  # noqa: S101
        return next(self._create_response_content(response, item) for item in response.output)

    # @trace_streaming_chat_completion(MODEL_PROVIDER_NAME)
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        chat_options.additional_properties["stream"] = True
        chat_options.ai_model_id = chat_options.ai_model_id or self.ai_model_id

        if chat_options.tools:
            chat_options.additional_properties.update({
                "response_tools": self._chat_to_response_tool_spec(chat_options.tools)
            })
        response = await self._send_request(chat_options, messages=self._prepare_chat_history_for_request(messages))
        if not isinstance(response, AsyncStream):
            raise ServiceInvalidResponseError("Expected an AsyncStream[ResponseStreamEvent] response.")
        async for chunk in response:
            update = self._create_streaming_response_content(chunk)  # type: ignore
            if not update:
                continue
            yield update

    def _create_response_content(self, response: OpenAIResponse, item: ResponseOutputItem) -> "ChatResponse":
        """Create a chat message content object from a choice."""
        items: MutableSequence[ChatMessage] = []
        metadata: dict[str, Any] = response.metadata or {}
        # TODO(peterychang): Add support for other content types
        if parsed_tool_calls := [tool for tool in self._get_tool_calls_from_response(response)]:
            items.append(ChatMessage(role="assistant", contents=parsed_tool_calls))
        if isinstance(item, ResponseOutputMessage):
            for content in item.content:
                # TODO(peterychang): Add annotations when available
                if isinstance(content, ResponseOutputText):
                    items.append(ChatMessage(role=item.role, text=content.text))
                    metadata.update(self._get_metadata_from_response(content))
                elif isinstance(content, ResponseOutputRefusal):
                    items.append(ChatMessage(role=item.role, text=content.refusal))
        return ChatResponse(
            response_id=response.id,
            created_at=datetime.fromtimestamp(response.created_at).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            usage_details=self._usage_details_from_openai(response.usage) if response.usage else None,
            messages=items,
            model_id=self.ai_model_id,
            additional_properties=metadata,
        )

    def _create_streaming_response_content(
        self,
        event: OpenAIResponseStreamEvent,
    ) -> ChatResponseUpdate | None:
        """Create a streaming chat message content object from a choice."""
        metadata: dict[str, Any] = {}
        items: list[AIContents] = []
        # TODO(peterychang): Add support for other content types
        if isinstance(event, ResponseContentPartAddedEvent):
            if isinstance(event.part, ResponseOutputText):
                items.append(TextContent(text=event.part.text))
                metadata.update(self._get_metadata_from_response(event.part))
            elif isinstance(event.part, ResponseOutputRefusal):
                items.append(TextContent(text=event.part.refusal))
        elif isinstance(event, ResponseTextDeltaEvent):
            items.append(TextContent(text=event.delta))
            metadata.update(self._get_metadata_from_response(event))
        elif isinstance(event, ResponseCompletedEvent):
            # Tool calls are available in the completed event
            if parsed_tool_calls := [tool for tool in self._get_tool_calls_from_response(event.response)]:
                items.extend(parsed_tool_calls)
        else:
            return None
        return ChatResponseUpdate(
            contents=items,
            role=ChatRole.ASSISTANT,
            ai_model_id=self.ai_model_id,
            additional_properties=metadata,
        )

    def _get_tool_calls_from_response(self, response: OpenAIResponse) -> list[AIContents]:
        resp: list[AIContents] = []
        # TODO(peterychang): Support the other tool calls
        for item in (i for i in response.output if isinstance(i, ResponseFunctionToolCall)):
            fcc = FunctionCallContent(
                call_id=item.id if item.id else "",
                name=item.name,
                arguments=item.arguments,
                additional_properties={"call_id": item.call_id},
            )
            resp.append(fcc)

        return resp

    def _usage_details_from_openai(self, usage: ResponseUsage) -> UsageDetails | None:
        return UsageDetails(
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )

    def _openai_chat_message_parser(
        self,
        message: ChatMessage,
        tool_id_to_call_id: dict[str, str],
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
                    new_args.update(self._openai_content_parser(content, tool_id_to_call_id))
                    all_messages.append(new_args)
                case FunctionCallContent():
                    function_call = self._openai_content_parser(content, tool_id_to_call_id)
                    all_messages.append(function_call)  # type: ignore
                case _:
                    if "content" not in args:
                        args["content"] = []
                    args["content"].append(self._openai_content_parser(content, tool_id_to_call_id))  # type: ignore
        if "content" in args or "tool_calls" in args:
            all_messages.append(args)
        return all_messages

    def _openai_content_parser(
        self,
        content: AIContents,
        tool_id_to_call_id: dict[str, str],
    ) -> dict[str, Any]:
        """Parse contents into the openai format."""
        match content:
            case FunctionCallContent():
                return {
                    "id": content.call_id,
                    "call_id": tool_id_to_call_id[content.call_id],
                    "type": "function_call",
                    "name": content.name,
                    "arguments": content.arguments,
                }
            case FunctionResultContent():
                # call_id for the result needs to be the same as the call_id for the function call
                return {
                    "call_id": tool_id_to_call_id[content.call_id],
                    "type": "function_call_output",
                    "output": content.result,
                }
            case TextContent():
                return {
                    "type": "input_text",
                    "text": content.text,
                }
            # TODO(peterychang): We'll probably need to specialize the other content types as well
            case _:
                return content.model_dump(exclude_none=True)

    def _prepare_chat_history_for_request(
        self,
        chat_messages: Sequence[ChatMessage],
        role_key: str = "role",
        content_key: str = "content",
    ) -> list[dict[str, Any]]:
        """Prepare the chat history for a request.

        Allowing customization of the key names for role/author, and optionally overriding the role.

        ChatRole.TOOL messages need to be formatted different than system/user/assistant messages:
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
        tool_id_to_call_id: dict[str, str] = {}
        for message in chat_messages:
            for content in message.contents:
                if isinstance(content, FunctionCallContent):
                    assert content.additional_properties and "call_id" in content.additional_properties  # nosec  # noqa: S101
                    call_id = content.additional_properties["call_id"]
                    tool_id_to_call_id[content.call_id] = call_id
        list_of_list = [self._openai_chat_message_parser(message, tool_id_to_call_id) for message in chat_messages]
        # Flatten the list of lists into a single list
        return list(chain.from_iterable(list_of_list))

    def _get_metadata_from_response(self, output: Any) -> dict[str, Any]:
        """Get metadata from a chat choice."""
        return {
            "logprobs": getattr(output, "logprobs", None),
        }

    @classmethod
    def from_dict(cls, settings: dict[str, Any]) -> "OpenAIResponsesClient":
        """Initialize an Open AI service from a dictionary of settings.

        Args:
            settings: A dictionary of settings for the service.
        """
        return OpenAIResponsesClient(
            ai_model_id=settings["ai_model_id"],
            default_headers=settings.get("default_headers"),
            api_key=settings.get("api_key"),
            org_id=settings.get("org_id"),
        )


# endregion
