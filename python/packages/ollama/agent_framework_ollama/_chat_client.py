# Copyright (c) Microsoft. All rights reserved.

from collections.abc import MutableSequence
from itertools import chain
from typing import Any, AsyncIterable, ClassVar

from agent_framework import (
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Role,
    TextContent,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError, ServiceInvalidRequestError
from ollama import AsyncClient

# Rename imported types to avoid naming conflicts with Agent Framework types
from ollama._types import ChatResponse as OllamaChatResponse
from ollama._types import Message as OllamaMessage
from pydantic import ValidationError


class OllamaSettings(AFBaseSettings):
    """Ollama settings."""

    env_prefix: ClassVar[str] = "OLLAMA_"

    host: str | None = None
    chat_model_id: str | None = None


class OllamaChatClient(BaseChatClient):
    client: AsyncClient
    chat_model_id: str

    def __init__(
        self,
        host: str | None = None,
        client: AsyncClient | None = None,
        chat_model_id: str | None = None,
    ) -> None:
        """Initialize an Ollama Chat client.

        Args:
            host: The Ollama server host URL. If not provided, the default host will be used.
            client: An optional Ollama Client instance. If not provided, a new instance will be created.
            chat_model_id: The Ollama chat model ID to use.If not provided, the default model will be used.
        """
        try:
            ollama_settings = OllamaSettings(host=host, chat_model_id=chat_model_id)
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create Ollama settings.", ex) from ex

        client = client or AsyncClient(host=ollama_settings.host)

        super().__init__(
            client=client,  # type: ignore[reportCallIssue]
            chat_model_id=ollama_settings.chat_model_id,  # type: ignore[reportCallIssue]
        )

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        return await ChatResponse.from_chat_response_generator(
            updates=self._inner_get_streaming_response(messages=messages, chat_options=chat_options, **kwargs)
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        options_dict = self._prepare_options(messages, chat_options)
        response_object: AsyncIterable[OllamaChatResponse] = await self.client.chat(  # type: ignore[misc]
            model=self.chat_model_id,
            stream=True,
            **options_dict,
        )

        async for part in response_object:
            yield self._create_chat_response_update(part)

    def _prepare_options(self, messages: MutableSequence[ChatMessage], chat_options: ChatOptions) -> dict[str, Any]:
        # Preprocess web search tool if it exists
        options_dict = chat_options.to_provider_settings()
        if messages and "messages" not in options_dict:
            options_dict["messages"] = self._prepare_chat_history_for_request(messages)
        if "messages" not in options_dict:
            raise ServiceInvalidRequestError("Messages are required for chat completions")
        return options_dict

    def _prepare_chat_history_for_request(self, messages: MutableSequence[ChatMessage]) -> list[OllamaMessage]:
        list_of_list = [self._ollama_chat_message_parser(msg) for msg in messages]
        # Flatten the list of lists into a single list
        return list(chain.from_iterable(list_of_list))

    def _ollama_chat_message_parser(self, message: ChatMessage) -> list[OllamaMessage]:
        messages: list[OllamaMessage] = []
        for content in message.contents:
            if isinstance(content, TextContent):
                messages.append(OllamaMessage(role=message.role.value, content=content.text))
        return messages

    def _create_chat_response_update(self, response: OllamaChatResponse) -> ChatResponseUpdate:
        if response.message.content:
            return ChatResponseUpdate(text=response.message.content, role=Role.ASSISTANT)
        return ChatResponseUpdate(text="", role=Role.ASSISTANT)
