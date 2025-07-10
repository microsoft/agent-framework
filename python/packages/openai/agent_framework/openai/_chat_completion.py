# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import AsyncIterable, Mapping, MutableSequence, Sequence
from datetime import datetime
from typing import Any, ClassVar, cast

from agent_framework.exceptions import ServiceInitializationError, ServiceInvalidResponseError
from pydantic import SecretStr, ValidationError

from agent_framework import (
    ChatClientBase,
    ChatFinishReason,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    FunctionCallContent,
    TextContent,
    UsageDetails,
)
from openai import AsyncOpenAI, AsyncStream
from openai.types import CompletionUsage
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, ChoiceDeltaToolCall
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall

from ._openai_config_base import OpenAIConfigBase
from ._openai_handler import OpenAIHandler
from ._openai_model_types import OpenAIModelTypes
from ._openai_settings import OpenAISettings


# Implements agent_framework.ChatClient protocol
class OpenAIChatCompletionBase(OpenAIHandler, ChatClientBase):
    """OpenAI Chat completion class."""

    MODEL_PROVIDER_NAME: ClassVar[str] = "openai"
    SUPPORTS_FUNCTION_CALLING: ClassVar[bool] = True

    # region Overriding base class methods
    # most of the methods are overridden from the ChatCompletionClientBase class, otherwise it is mentioned

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        # TODO(peterychang): Is there a better way to handle this?
        chat_options.additional_properties = dict(chat_options.additional_properties)
        chat_options.additional_properties.update({"stream": False})
        chat_options.ai_model_id = chat_options.ai_model_id or self.ai_model_id

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
        # TODO(peterychang): Is there a better way to handle this?
        chat_options.additional_properties = dict(chat_options.additional_properties)
        chat_options.additional_properties.update({"stream": True, "stream_options": {"include_usage": True}})
        chat_options.ai_model_id = chat_options.ai_model_id or self.ai_model_id

        response = await self._send_request(chat_options, messages=self._prepare_chat_history_for_request(messages))
        if not isinstance(response, AsyncStream):
            raise ServiceInvalidResponseError("Expected an AsyncStream[ChatCompletionChunk] response.")
        async for chunk in response:
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

        items: list[ChatMessage] = [
            ChatMessage(role="assistant", contents=[tool]) for tool in self._get_tool_calls_from_chat_choice(choice)
        ]
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

    def _get_tool_calls_from_chat_choice(self, choice: Choice | ChunkChoice) -> list[FunctionCallContent]:
        """Get tool calls from a chat choice."""
        resp: list[FunctionCallContent] = []
        content = choice.message if isinstance(choice, Choice) else choice.delta
        if content and (tool_calls := getattr(content, "tool_calls", None)) is not None:
            for tool in cast(list[ChatCompletionMessageToolCall] | list[ChoiceDeltaToolCall], tool_calls):
                if tool.function:
                    fcc = FunctionCallContent(
                        call_id=tool.id if tool.id else "",
                        name=tool.function.name if tool.function and tool.function.name else "",
                        arguments=json.loads(tool.function.arguments)
                        if tool.function and tool.function.arguments
                        else {},
                    )
                    resp.append(fcc)

        # When you enable asynchronous content filtering in Azure OpenAI, you may receive empty deltas
        return resp

    def _prepare_chat_history_for_request(
        self,
        chat_history: ChatMessage | Sequence[ChatMessage],
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
            chat_history (list[ChatMessage]): The chat history to prepare.
            role_key (str): The key name for the role/author.
            content_key (str): The key name for the content/message.

        Returns:
            prepared_chat_history (Any): The prepared chat history for a request.
        """
        # TODO(peterychang): Chat history type is not finalized yet
        if not isinstance(chat_history, Sequence):
            chat_history = [chat_history]
        # TODO(peterychang): This is the bare minimum to get the chat history into a format that OpenAI expects.
        return [
            {
                "role": message.role.value if isinstance(message.role, ChatRole) else message.role,
                "content": [content.model_dump() for content in message.contents],
                "metadata": message.additional_properties or {},
            }
            for message in chat_history
        ]

    # endregion


class OpenAIChatCompletion(OpenAIConfigBase, OpenAIChatCompletionBase):
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
            if api_key:
                openai_settings = OpenAISettings(
                    api_key=SecretStr(api_key),
                    org_id=org_id,
                    chat_model_id=ai_model_id,
                    env_file_path=env_file_path,
                    env_file_encoding=env_file_encoding,
                )
            else:
                openai_settings = OpenAISettings(
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
    def from_dict(cls, settings: dict[str, Any]) -> "OpenAIChatCompletion":
        """Initialize an Open AI service from a dictionary of settings.

        Args:
            settings: A dictionary of settings for the service.
        """
        return OpenAIChatCompletion(
            ai_model_id=settings["ai_model_id"],
            default_headers=settings.get("default_headers"),
        )
