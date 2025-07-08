# Copyright (c) Microsoft. All rights reserved.

import logging
from abc import ABC
from typing import Any, Union

from openai import AsyncOpenAI, AsyncStream, BadRequestError
from openai import _legacy_response # type: ignore
from openai.lib._parsing._completions import type_to_response_format_param
from openai.types import Completion, CreateEmbeddingResponse
from openai.types.audio import Transcription
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.images_response import ImagesResponse
from pydantic import BaseModel

from agent_framework import (
    AFBaseModel, ChatOptions, SpeechToTextOptions, TextToSpeechOptions
)
from agent_framework.exceptions import (
    ServiceInvalidRequestError, ServiceResponseException
)

from .exceptions import ContentFilterAIException
from .openai_model_types import OpenAIModelTypes
from ._openai_prompt_execution_settings import OpenAIEmbeddingPromptExecutionSettings
from ._openai_text_to_image_execution_settings import (
    OpenAITextToImageExecutionSettings,
)



logger: logging.Logger = logging.getLogger(__name__)

RESPONSE_TYPE = Union[
    ChatCompletion,
    Completion,
    AsyncStream[ChatCompletionChunk],
    AsyncStream[Completion],
    list[Any],
    ImagesResponse,
    Transcription,
    _legacy_response.HttpxBinaryResponseContent,
]

# TODO(evmattso): update with proper Options types to move away from ExecutionSettings
OPTION_TYPE = Union[
    ChatOptions,
    SpeechToTextOptions,
    TextToSpeechOptions,
    OpenAITextToImageExecutionSettings,
    OpenAIEmbeddingPromptExecutionSettings,
]


class OpenAIHandler(AFBaseModel, ABC):
    """Internal class for calls to OpenAI API's."""

    client: AsyncOpenAI
    ai_model_type: OpenAIModelTypes = OpenAIModelTypes.CHAT
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    async def _send_request(self, options: OPTION_TYPE, messages: list[dict[str, Any]] | None = None) -> RESPONSE_TYPE:
        """Send a request to the OpenAI API."""
        if self.ai_model_type == OpenAIModelTypes.CHAT:
            assert isinstance(options, ChatOptions)  # nosec
            return await self._send_completion_request(options, messages)
        # TODO(evmattso): move other PromptExecutionSettings to a common options class
        if self.ai_model_type == OpenAIModelTypes.EMBEDDING:
            assert isinstance(options, OpenAIEmbeddingPromptExecutionSettings)  # nosec
            return await self._send_embedding_request(options)
        if self.ai_model_type == OpenAIModelTypes.TEXT_TO_IMAGE:
            assert isinstance(options, OpenAITextToImageExecutionSettings)  # nosec
            return await self._send_text_to_image_request(options)
        if self.ai_model_type == OpenAIModelTypes.SPEECH_TO_TEXT:
            assert isinstance(options, SpeechToTextOptions)  # nosec
            return await self._send_audio_to_text_request(options)
        if self.ai_model_type == OpenAIModelTypes.TEXT_TO_SPEECH:
            assert isinstance(options, TextToSpeechOptions)  # nosec
            return await self._send_text_to_audio_request(options)

        raise NotImplementedError(f"Model type {self.ai_model_type} is not supported")

    async def _send_completion_request(
        self,
        chat_options: "ChatOptions",
        messages: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion | Completion | AsyncStream[ChatCompletionChunk] | AsyncStream[Completion]:
        """Execute the appropriate call to OpenAI models."""
        try:
            options_dict = chat_options.to_provider_settings()
            if messages is not None:
                options_dict["messages"] = messages
            if self.ai_model_type == OpenAIModelTypes.CHAT:
                self._handle_structured_outputs(chat_options, options_dict)
                if chat_options.tools is None:
                    options_dict.pop("parallel_tool_calls", None)
                response = await self.client.chat.completions.create(**options_dict) # type: ignore
            else:
                response = await self.client.completions.create(**options_dict) # type: ignore

            assert isinstance(response, (ChatCompletion, Completion, AsyncStream))
            self.store_usage(response) # type: ignore
            return response # type: ignore
        except BadRequestError as ex:
            if ex.code == "content_filter":
                raise ContentFilterAIException(
                    f"{type(self)} service encountered a content error",
                    ex,
                ) from ex
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt",
                ex,
            ) from ex
        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt",
                ex,
            ) from ex

    async def _send_embedding_request(self, settings: OpenAIEmbeddingPromptExecutionSettings) -> list[Any]:
        """Send a request to the OpenAI embeddings endpoint."""
        try:
            response = await self.client.embeddings.create(**settings.prepare_settings_dict())

            self.store_usage(response)
            return [x.embedding for x in response.data]
        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to generate embeddings",
                ex,
            ) from ex

    async def _send_text_to_image_request(self, settings: OpenAITextToImageExecutionSettings) -> ImagesResponse:
        """Send a request to the OpenAI text to image endpoint."""
        try:
            return await self.client.images.generate(
                **settings.prepare_settings_dict(),
            )
        except Exception as ex:
            raise ServiceResponseException(f"Failed to generate image: {ex}") from ex

    async def _send_audio_to_text_request(self, options: SpeechToTextOptions) -> Transcription:
        """Send a request to the OpenAI audio to text endpoint."""
        if not options.additional_properties["filename"]:
            raise ServiceInvalidRequestError("Audio file is required for audio to text service")

        try:
            with open(options.additional_properties["filename"], "rb") as audio_file:
                return await self.client.audio.transcriptions.create(
                    file=audio_file,
                    **options.to_provider_settings(exclude={"filename"}),
                ) # type: ignore
        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to transcribe audio",
                ex,
            ) from ex

    async def _send_text_to_audio_request(
        self, options: TextToSpeechOptions
    ) -> _legacy_response.HttpxBinaryResponseContent:
        """Send a request to the OpenAI text to audio endpoint.

        The OpenAI API returns the content of the generated audio file.
        """
        try:
            return await self.client.audio.speech.create(
                **options.to_provider_settings(),
            )
        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to generate audio",
                ex,
            ) from ex

    def _handle_structured_outputs(self, chat_options: "ChatOptions", options_dict: dict[str, Any]) -> None:
        response_format = getattr(chat_options, "response_format", None)
        if response_format and isinstance(response_format, type) and issubclass(response_format, BaseModel):
            options_dict["response_format"] = type_to_response_format_param(response_format)

    def store_usage(
        self,
        response: ChatCompletion
        | Completion
        | AsyncStream[ChatCompletionChunk]
        | AsyncStream[Completion]
        | CreateEmbeddingResponse,
    ):
        """Store the usage information from the response."""
        if isinstance(response, (ChatCompletion, Completion)) and response.usage:
            logger.info(f"OpenAI usage: {response.usage}")
            self.prompt_tokens += response.usage.prompt_tokens
            self.total_tokens += response.usage.total_tokens
            if hasattr(response.usage, "completion_tokens"):
                self.completion_tokens += response.usage.completion_tokens
        elif isinstance(response, CreateEmbeddingResponse) and response.usage:
            logger.info(f"OpenAI embedding usage: {response.usage}")
            self.prompt_tokens += response.usage.prompt_tokens
            self.total_tokens += response.usage.total_tokens
