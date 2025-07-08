# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Sequence
import json
from typing import Any, ClassVar, cast

from openai import AsyncStream
from openai.types import CompletionUsage
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, ChoiceDeltaToolCall
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall

from agent_framework import (
    ChatMessage,
    ChatResponse, 
    ChatResponseUpdate,
    ChatRole,
    ChatFinishReason,
    FunctionCallContent,
    TextContent,
    UsageDetails,
)

from ._openai_handler import OpenAIHandler
from agent_framework import ChatOptions
from agent_framework.exceptions import ServiceInvalidResponseError

# from agent_framework.contents.streaming_text_content import StreamingTextContent

# from agent_framework.utils.telemetry.model_diagnostics.decorators import (
#     trace_chat_completion,
#     trace_streaming_chat_completion,
# )


# Implements agent_framework.ChatClient protocol
class OpenAIChatCompletionBase(OpenAIHandler):
    """OpenAI Chat completion class."""

    MODEL_PROVIDER_NAME: ClassVar[str] = "openai"
    SUPPORTS_FUNCTION_CALLING: ClassVar[bool] = True

    # region Overriding base class methods
    # most of the methods are overridden from the ChatCompletionClientBase class, otherwise it is mentioned

    # @trace_chat_completion(MODEL_PROVIDER_NAME)
    async def get_response(
        self,
        messages: ChatMessage | Sequence[ChatMessage],
        **kwargs: Any,
    ) -> ChatResponse:
        chat_options: ChatOptions = kwargs.get("chat_options", ChatOptions())
        assert isinstance(chat_options, ChatOptions)
        chat_options.additional_properties.update({"stream": False})
        chat_options.ai_model_id = chat_options.ai_model_id or self.ai_model_id

        response = await self._send_request(chat_options, messages=self._prepare_chat_history_for_request(messages))
        assert isinstance(response, ChatCompletion)  # nosec
        response_metadata = self._get_metadata_from_chat_response(response)
        return next(
            self._create_chat_message_content(response, choice, response_metadata) for choice in response.choices
        )
        
    # @trace_streaming_chat_completion(MODEL_PROVIDER_NAME)
    async def get_streaming_response( # type: ignore
        self,
        messages: ChatMessage | Sequence[ChatMessage],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        chat_options: ChatOptions = kwargs.get("chat_options", ChatOptions())
        assert isinstance(chat_options, ChatOptions)
        chat_options.additional_properties.update({"stream": True, "stream_options": {"include_usage": True}})
        chat_options.ai_model_id = chat_options.ai_model_id or self.ai_model_id

        response = await self._send_request(chat_options, messages=self._prepare_chat_history_for_request(messages))
        if not isinstance(response, AsyncStream):
            raise ServiceInvalidResponseError("Expected an AsyncStream[ChatCompletionChunk] response.")
        async for chunk in response:
            if len(chunk.choices) == 0 and chunk.usage is None:
                continue

            assert isinstance(chunk, ChatCompletionChunk)  # nosec
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

    # TODO: Usage?
    def _create_chat_message_content(
        self, response: ChatCompletion, choice: Choice, response_metadata: dict[str, Any]
    ) -> "ChatResponse":
        """Create a chat message content object from a choice."""
        metadata = self._get_metadata_from_chat_choice(choice)
        metadata.update(response_metadata)

        items: list[ChatMessage] = [ChatMessage(role='assistant', contents=[tool]) for tool in self._get_tool_calls_from_chat_choice(choice)]
        if choice.message.content:
            items.append(ChatMessage(role="assistant", text=choice.message.content))
        elif hasattr(choice.message, "refusal") and choice.message.refusal:
            items.append(ChatMessage(role="assistant", text=choice.message.refusal))

        return ChatResponse(
            response_id=response.id,
            # created_at=response.created,
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
            # created_at=response.created,
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
                            name=tool.function.name
                                if tool.function and tool.function.name else "",
                            arguments=json.loads(tool.function.arguments)
                                if tool.function and tool.function.arguments else {},
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
        # TODO: Chat history type is not finalized yet
        if not isinstance(chat_history, Sequence):
            chat_history = [chat_history]
        return [
            {
                **message.model_dump()            }
            for message in chat_history
        ]
        # return [
        #     {
        #         **message.to_dict(role_key=role_key, content_key=content_key),
        #         role_key: "developer"
        #         if self.instruction_role == "developer" and message.to_dict(role_key=role_key)[role_key] == "system"
        #         else message.to_dict(role_key=role_key)[role_key],
        #     }
        #     for message in chat_history.messages
        #     if not isinstance(message, (AnnotationContent, FileReferenceContent))
        # ]

    # endregion
