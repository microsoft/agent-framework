# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import AsyncIterable, Mapping, MutableSequence, Sequence
from datetime import datetime
from itertools import chain
from typing import Any, ClassVar, cast

from openai import AsyncOpenAI, AsyncStream
from openai.types import CompletionUsage
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, ChoiceDeltaToolCall
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
from pydantic import SecretStr, ValidationError

from .._clients import ChatClientBase, use_tool_calling
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
from ..exceptions import ServiceInitializationError, ServiceInvalidResponseError
from ..telemetry import use_telemetry
from ._shared import OpenAIConfigBase, OpenAIHandler, OpenAIModelTypes, OpenAISettings

__all__ = ["OpenAIChatClient"]


# region Base Client
@use_telemetry
@use_tool_calling
class OpenAIChatClientBase(OpenAIHandler, ChatClientBase):
    """OpenAI Chat completion class."""

    MODEL_PROVIDER_NAME: ClassVar[str] = "openai"  # type: ignore[reportIncompatibleVariableOverride, misc]

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
                    args["content"] = content.result
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
