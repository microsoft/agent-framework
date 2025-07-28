# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Mapping, MutableSequence
from typing import Any, ClassVar

from openai import AsyncOpenAI
from pydantic import Field, PrivateAttr, SecretStr, ValidationError

from .._clients import ChatClientBase, use_tool_calling
from .._types import ChatMessage, ChatOptions, ChatResponse, ChatResponseUpdate, TextContent
from ..exceptions import ServiceInitializationError
from ._shared import OpenAIConfigBase, OpenAIHandler, OpenAIModelTypes, OpenAISettings


@use_tool_calling
class OpenAIAssistantsClient(OpenAIConfigBase, ChatClientBase, OpenAIHandler):
    """OpenAI Assistants client."""

    MODEL_PROVIDER_NAME: ClassVar[str] = "openai"  # type: ignore[reportIncompatibleVariableOverride]
    assistant_id: str | None = Field(default=None)
    assistant_name: str | None = Field(default=None)
    thread_id: str | None = Field(default=None)
    _should_delete_assistant: bool = PrivateAttr(default=False)  # Track whether we should delete the assistant

    def __init__(
        self,
        ai_model_id: str | None = None,
        assistant_id: str | None = None,
        assistant_name: str | None = None,
        thread_id: str | None = None,
        api_key: str | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an OpenAI Assistants client.

        Args:
            ai_model_id (str): OpenAI model name, see
                https://platform.openai.com/docs/models
            assistant_id (str | None): The ID of an OpenAI assistant to use.
                If not provided, a new assistant will be created (and deleted after the request).
            assistant_name (str | None): The name to use when creating new assistants.
            thread_id: Default thread ID to use for conversations. Can be overridden by
                conversation_id property from ChatOptions, when making a request.
                If not provided, a new thread will be created (and deleted after the request).
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
            assistant_id=assistant_id,  # type: ignore[reportCallIssue]
            assistant_name=assistant_name,  # type: ignore[reportCallIssue]
            thread_id=thread_id,  # type: ignore[reportCallIssue]
            api_key=openai_settings.api_key.get_secret_value() if openai_settings.api_key else None,
            org_id=openai_settings.org_id,
            ai_model_type=OpenAIModelTypes.ASSISTANT,
            default_headers=default_headers,
            client=async_client,
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
        yield ChatResponseUpdate(contents=[TextContent(text="test")])

    async def _get_assistant_id_or_create(self) -> str:
        """Determine which assistant to use and create if needed.

        Returns:
            str: The assistant_id to use.
        """
        # If no assistant is provided, create a temporary assistant
        if self.assistant_id is None:
            created_assistant = await self.client.beta.assistants.create(
                name=self.assistant_name, model=self.ai_model_id
            )

            self.assistant_id = created_assistant.id
            self._should_delete_assistant = True

        return self.assistant_id
