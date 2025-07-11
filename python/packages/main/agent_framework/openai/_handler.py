# Copyright (c) Microsoft. All rights reserved.

import logging
from abc import ABC
from enum import Enum
from typing import Annotated, Any, Union

from openai import (
    AsyncOpenAI,
    AsyncStream,
    BadRequestError,
    _legacy_response,  # type: ignore
)
from openai.lib._parsing._completions import type_to_response_format_param
from openai.types import Completion
from openai.types.audio import Transcription
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.images_response import ImagesResponse
from pydantic import BaseModel
from pydantic.types import StringConstraints

from .._logging import get_logger
from .._pydantic import AFBaseModel
from .._types import ChatOptions, SpeechToTextOptions, TextToSpeechOptions
from ..exceptions import ServiceInvalidRequestError, ServiceResponseException
from .exceptions import OpenAIContentFilterException

logger: logging.Logger = get_logger("agent_framework.openai")


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

OPTION_TYPE = Union[
    ChatOptions,
    SpeechToTextOptions,
    TextToSpeechOptions,
]


class OpenAIModelTypes(Enum):
    """OpenAI model types, can be text, chat or embedding."""

    CHAT = "chat"
    EMBEDDING = "embedding"
    TEXT_TO_IMAGE = "text-to-image"
    SPEECH_TO_TEXT = "speech-to-text"
    TEXT_TO_SPEECH = "text-to-speech"
    REALTIME = "realtime"
    RESPONSE = "response"


class OpenAIHandler(AFBaseModel, ABC):
    """Internal class for calls to OpenAI API's."""

    client: AsyncOpenAI
    ai_model_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    ai_model_type: OpenAIModelTypes = OpenAIModelTypes.CHAT

    async def _send_request(self, options: OPTION_TYPE, messages: list[dict[str, Any]] | None = None) -> RESPONSE_TYPE:
        """Send a request to the OpenAI API."""
        if self.ai_model_type == OpenAIModelTypes.CHAT:
            assert isinstance(options, ChatOptions)  # nosec # noqa: S101
            return await self._send_completion_request(options, messages)
        # TODO(evmattso): move other PromptExecutionSettings to a common options class
        if self.ai_model_type == OpenAIModelTypes.EMBEDDING:
            raise NotImplementedError("Embedding generation is not yet implemented in OpenAIHandler")
        if self.ai_model_type == OpenAIModelTypes.TEXT_TO_IMAGE:
            raise NotImplementedError("Text to image generation is not yet implemented in OpenAIHandler")
        if self.ai_model_type == OpenAIModelTypes.SPEECH_TO_TEXT:
            assert isinstance(options, SpeechToTextOptions)  # nosec # noqa: S101
            return await self._send_audio_to_text_request(options)
        if self.ai_model_type == OpenAIModelTypes.TEXT_TO_SPEECH:
            assert isinstance(options, TextToSpeechOptions)  # nosec # noqa: S101
            return await self._send_text_to_audio_request(options)

        raise NotImplementedError(f"Model type {self.ai_model_type} is not supported")

    async def _send_completion_request(
        self,
        chat_options: "ChatOptions",
        messages: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion | AsyncStream[ChatCompletionChunk]:
        """Execute the appropriate call to OpenAI models."""
        try:
            options_dict = chat_options.to_provider_settings()
            if messages and "messages" not in options_dict:
                options_dict["messages"] = messages
            if "messages" not in options_dict:
                raise ServiceInvalidRequestError("Messages are required for chat completions")
            self._handle_structured_outputs(chat_options, options_dict)
            if chat_options.tools is None:
                options_dict.pop("parallel_tool_calls", None)
            return await self.client.chat.completions.create(**options_dict)  # type: ignore
        except BadRequestError as ex:
            if ex.code == "content_filter":
                raise OpenAIContentFilterException(
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

    async def _send_audio_to_text_request(self, options: SpeechToTextOptions) -> Transcription:
        """Send a request to the OpenAI audio to text endpoint."""
        if not options.additional_properties["filename"]:
            raise ServiceInvalidRequestError("Audio file is required for audio to text service")

        try:
            # TODO(peterychang): open isn't async safe
            with open(options.additional_properties["filename"], "rb") as audio_file:  # noqa: ASYNC230
                return await self.client.audio.transcriptions.create(  # type: ignore
                    file=audio_file,
                    **options.to_provider_settings(exclude={"filename"}),
                )
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
        if (
            chat_options.response_format
            and isinstance(chat_options.response_format, type)
            and issubclass(chat_options.response_format, BaseModel)
        ):
            options_dict["response_format"] = type_to_response_format_param(chat_options.response_format)
