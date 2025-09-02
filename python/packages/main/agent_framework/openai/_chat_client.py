# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import AsyncIterable, Mapping, MutableMapping, MutableSequence, Sequence
from datetime import datetime
from itertools import chain
from typing import Any, TypeVar

from openai import AsyncOpenAI, BadRequestError
from openai.lib._parsing._completions import type_to_response_format_param
from openai.types import CompletionUsage
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_message_custom_tool_call import ChatCompletionMessageCustomToolCall
from pydantic import BaseModel, SecretStr, ValidationError

from agent_framework import AIFunction, AITool, UsageContent

from .._clients import ChatClientBase, use_tool_calling
from .._logging import get_logger
from .._tools import HostedWebSearchTool
from .._types import (
    AIContents,
    ChatFinishReason,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
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

__all__ = ["OpenAIChatClient"]

logger = get_logger("agent_framework.openai")


# region Base Client
@use_telemetry
@use_tool_calling
class OpenAIChatClientBase(OpenAIHandler, ChatClientBase):
    """OpenAI Chat completion class."""

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        options_dict = self._prepare_options(messages, chat_options)
        try:
            return self._create_chat_response(
                await self.client.chat.completions.create(stream=False, **options_dict), chat_options
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

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        options_dict = self._prepare_options(messages, chat_options)
        options_dict["stream_options"] = {"include_usage": True}
        try:
            async for chunk in await self.client.chat.completions.create(stream=True, **options_dict):
                if len(chunk.choices) == 0 and chunk.usage is None:
                    continue
                yield self._create_chat_response_update(chunk)
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

    # region content creation

    def _chat_to_tool_spec(self, tools: list[AITool | MutableMapping[str, Any]]) -> list[dict[str, Any]]:
        chat_tools: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, AITool):
                match tool:
                    case AIFunction():
                        chat_tools.append(tool.to_json_schema_spec())
                    case _:
                        logger.debug("Unsupported tool passed (type: %s), ignoring", type(tool))
            else:
                chat_tools.append(tool if isinstance(tool, dict) else dict(tool))
        return chat_tools

    def _process_web_search_tool(self, tools: list[AITool | MutableMapping[str, Any]]) -> dict[str, Any] | None:
        for tool in tools:
            if isinstance(tool, HostedWebSearchTool):
                # Web search tool requires special handling
                return (
                    {
                        "user_location": {
                            "approximate": tool.additional_properties.get("user_location", None),
                            "type": "approximate",
                        }
                    }
                    if tool.additional_properties and "user_location" in tool.additional_properties
                    else {}
                )

        return None

    def _prepare_options(self, messages: MutableSequence[ChatMessage], chat_options: ChatOptions) -> dict[str, Any]:
        # Preprocess web search tool if it exists
        options_dict = chat_options.to_provider_settings()
        if messages and "messages" not in options_dict:
            options_dict["messages"] = self._prepare_chat_history_for_request(messages)
        if "messages" not in options_dict:
            raise ServiceInvalidRequestError("Messages are required for chat completions")
        if chat_options.tools is not None:
            web_search_options = self._process_web_search_tool(chat_options.tools)
            if web_search_options:
                options_dict["web_search_options"] = web_search_options
            options_dict["tools"] = self._chat_to_tool_spec(chat_options.tools)
        if not options_dict.get("tools", None):
            options_dict.pop("tools", None)
            options_dict.pop("parallel_tool_calls", None)
            options_dict.pop("tool_choice", None)

        if "model" not in options_dict:
            options_dict["model"] = self.ai_model_id
        if (
            chat_options.response_format
            and isinstance(chat_options.response_format, type)
            and issubclass(chat_options.response_format, BaseModel)
        ):
            options_dict["response_format"] = type_to_response_format_param(chat_options.response_format)
        return options_dict

    def _create_chat_response(self, response: ChatCompletion, chat_options: ChatOptions) -> "ChatResponse":
        """Create a chat message content object from a choice."""
        response_metadata = self._get_metadata_from_chat_response(response)
        messages: list[ChatMessage] = []
        finish_reason: ChatFinishReason | None = None
        for choice in response.choices:
            response_metadata.update(self._get_metadata_from_chat_choice(choice))
            if choice.finish_reason:
                finish_reason = ChatFinishReason(value=choice.finish_reason)
            contents: list[AIContents] = []
            if parsed_tool_calls := [tool for tool in self._get_tool_calls_from_chat_choice(choice)]:
                contents.extend(parsed_tool_calls)
            if text_content := self._parse_text_from_choice(choice):
                contents.append(text_content)
            messages.append(ChatMessage(role="assistant", contents=contents))
        return ChatResponse(
            response_id=response.id,
            created_at=datetime.fromtimestamp(response.created).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            usage_details=self._usage_details_from_openai(response.usage) if response.usage else None,
            messages=messages,
            model_id=response.model,
            additional_properties=response_metadata,
            finish_reason=finish_reason,
            response_format=chat_options.response_format,
        )

    def _create_chat_response_update(
        self,
        chunk: ChatCompletionChunk,
    ) -> ChatResponseUpdate:
        """Create a streaming chat message content object from a choice."""
        chunk_metadata = self._get_metadata_from_streaming_chat_response(chunk)
        if chunk.usage:
            return ChatResponseUpdate(
                role=ChatRole.ASSISTANT,
                contents=[UsageContent(details=self._usage_details_from_openai(chunk.usage), raw_representation=chunk)],
                ai_model_id=chunk.model,
                additional_properties=chunk_metadata,
                response_id=chunk.id,
                message_id=chunk.id,
            )
        contents: list[AIContents] = []
        finish_reason: ChatFinishReason | None = None
        for choice in chunk.choices:
            chunk_metadata.update(self._get_metadata_from_chat_choice(choice))
            contents.extend(self._get_tool_calls_from_chat_choice(choice))
            if choice.finish_reason:
                finish_reason = ChatFinishReason(value=choice.finish_reason)

            if text_content := self._parse_text_from_choice(choice):
                contents.append(text_content)
        return ChatResponseUpdate(
            created_at=datetime.fromtimestamp(chunk.created).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            contents=contents,
            role=ChatRole.ASSISTANT,
            ai_model_id=chunk.model,
            additional_properties=chunk_metadata,
            finish_reason=finish_reason,
            raw_representation=chunk,
            response_id=chunk.id,
            message_id=chunk.id,
        )

    def _usage_details_from_openai(self, usage: CompletionUsage) -> UsageDetails:
        return UsageDetails(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )

    def _parse_text_from_choice(self, choice: Choice | ChunkChoice) -> TextContent | None:
        """Parse the choice into a TextContent object."""
        message = choice.message if isinstance(choice, Choice) else choice.delta
        if message.content:
            return TextContent(text=message.content, raw_representation=choice)
        if hasattr(message, "refusal") and message.refusal:
            return TextContent(text=message.refusal, raw_representation=choice)
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

    def _get_tool_calls_from_chat_choice(self, choice: Choice | ChunkChoice) -> list[AIContents]:
        """Get tool calls from a chat choice."""
        resp: list[AIContents] = []
        content = choice.message if isinstance(choice, Choice) else choice.delta
        if content and content.tool_calls:
            for tool in content.tool_calls:
                if not isinstance(tool, ChatCompletionMessageCustomToolCall) and tool.function:
                    # ignoring tool.custom
                    fcc = FunctionCallContent(
                        call_id=tool.id if tool.id else "",
                        name=tool.function.name if tool.function.name else "",
                        arguments=tool.function.arguments if tool.function.arguments else "",
                        raw_representation=tool.function,
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

    # region Parsers

    def _openai_chat_message_parser(self, message: ChatMessage) -> list[dict[str, Any]]:
        """Parse a chat message into the openai format."""
        all_messages: list[dict[str, Any]] = []
        for content in message.contents:
            args: dict[str, Any] = {
                "role": message.role.value if isinstance(message.role, ChatRole) else message.role,
            }
            if message.additional_properties:
                args["metadata"] = message.additional_properties
            match content:
                case FunctionCallContent():
                    if all_messages and "tool_calls" in all_messages[-1]:
                        # If the last message already has tool calls, append to it
                        all_messages[-1]["tool_calls"].append(self._openai_content_parser(content))
                    else:
                        args["tool_calls"] = [self._openai_content_parser(content)]  # type: ignore
                case FunctionResultContent():
                    args["tool_call_id"] = content.call_id
                    if content.result:
                        args["content"] = prepare_function_call_results(content.result)
                case _:
                    if "content" not in args:
                        args["content"] = []
                    # this is a list to allow multi-modal content
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

    def service_url(self) -> str | None:
        """Get the URL of the service.

        Override this in the subclass to return the proper URL.
        If the service does not have a URL, return None.
        """
        return str(self.client.base_url) if self.client else None


# region Public client

TOpenAIChatClient = TypeVar("TOpenAIChatClient", bound="OpenAIChatClient")


class OpenAIChatClient(OpenAIConfigBase, OpenAIChatClientBase):
    """OpenAI Chat completion class."""

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
                chat_model_id=ai_model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create OpenAI settings.", ex) from ex

        if not async_client and not openai_settings.api_key:
            raise ServiceInitializationError(
                "OpenAI API key is required. Set via 'api_key' parameter or 'OPENAI_API_KEY' environment variable."
            )
        if not openai_settings.chat_model_id:
            raise ServiceInitializationError(
                "OpenAI model ID is required. "
                "Set via 'ai_model_id' parameter or 'OPENAI_CHAT_MODEL_ID' environment variable."
            )

        super().__init__(
            ai_model_id=openai_settings.chat_model_id,
            api_key=openai_settings.api_key.get_secret_value() if openai_settings.api_key else None,
            org_id=openai_settings.org_id,
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
        )

    @classmethod
    def from_dict(cls: type[TOpenAIChatClient], settings: dict[str, Any]) -> TOpenAIChatClient:
        """Initialize an Open AI Chat Client from a dictionary of settings.

        Args:
            settings: A dictionary of settings for the service.
        """
        return cls(**settings)


# endregion
