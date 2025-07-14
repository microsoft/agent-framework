# Copyright (c) Microsoft. All rights reserved.

import logging
from abc import ABC
from collections.abc import Mapping
from copy import copy
from enum import Enum
from typing import Annotated, Any, ClassVar, Union

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
from pydantic import BaseModel, ConfigDict, Field, SecretStr, validate_call
from pydantic.types import StringConstraints

from .._logging import get_logger
from .._pydantic import AFBaseModel, AFBaseSettings
from .._types import ChatOptions, SpeechToTextOptions, TextToSpeechOptions
from ..exceptions import ServiceInitializationError, ServiceInvalidRequestError, ServiceResponseException
from ..telemetry import APP_INFO, USER_AGENT_KEY, prepend_agent_framework_to_user_agent
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


class OpenAISettings(AFBaseSettings):
    """OpenAI model settings.

    The settings are first loaded from environment variables with the prefix 'OPENAI_'.
    If the environment variables are not found, the settings can be loaded from a .env file with the
    encoding 'utf-8'. If the settings are not found in the .env file, the settings are ignored;
    however, validation will fail alerting that the settings are missing.

    Optional settings for prefix 'OPENAI_' are:
    - api_key: SecretStr - OpenAI API key, see https://platform.openai.com/account/api-keys
        (Env var OPENAI_API_KEY)
    - org_id: str | None - This is usually optional unless your account belongs to multiple organizations.
        (Env var OPENAI_ORG_ID)
    - chat_model_id: str | None - The OpenAI chat model ID to use, for example, gpt-3.5-turbo or gpt-4.
        (Env var OPENAI_CHAT_MODEL_ID)
    - responses_model_id: str | None - The OpenAI responses model ID to use, for example, gpt-4o or o1.
        (Env var OPENAI_RESPONSES_MODEL_ID)
    - text_model_id: str | None - The OpenAI text model ID to use, for example, gpt-3.5-turbo-instruct.
        (Env var OPENAI_TEXT_MODEL_ID)
    - embedding_model_id: str | None - The OpenAI embedding model ID to use, for example, text-embedding-ada-002.
        (Env var OPENAI_EMBEDDING_MODEL_ID)
    - text_to_image_model_id: str | None - The OpenAI text to image model ID to use, for example, dall-e-3.
        (Env var OPENAI_TEXT_TO_IMAGE_MODEL_ID)
    - audio_to_text_model_id: str | None - The OpenAI audio to text model ID to use, for example, whisper-1.
        (Env var OPENAI_AUDIO_TO_TEXT_MODEL_ID)
    - text_to_audio_model_id: str | None - The OpenAI text to audio model ID to use, for example, jukebox-1.
        (Env var OPENAI_TEXT_TO_AUDIO_MODEL_ID)
    - realtime_model_id: str | None - The OpenAI realtime model ID to use,
    for example, gpt-4o-realtime-preview-2024-12-17.
        (Env var OPENAI_REALTIME_MODEL_ID)
    - env_file_path: str | None - if provided, the .env settings are read from this file path location
    """

    env_prefix: ClassVar[str] = "OPENAI_"

    api_key: SecretStr | None = None
    org_id: str | None = None
    chat_model_id: str | None = None
    responses_model_id: str | None = None
    text_model_id: str | None = None
    embedding_model_id: str | None = None
    text_to_image_model_id: str | None = None
    audio_to_text_model_id: str | None = None
    text_to_audio_model_id: str | None = None
    realtime_model_id: str | None = None


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


class OpenAIConfigBase(OpenAIHandler):
    """Internal class for configuring a connection to an OpenAI service."""

    @validate_call(config=ConfigDict(arbitrary_types_allowed=True))
    def __init__(
        self,
        ai_model_id: str = Field(min_length=1),
        api_key: str | None = Field(min_length=1),
        ai_model_type: OpenAIModelTypes | None = OpenAIModelTypes.CHAT,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a client for OpenAI services.

        This constructor sets up a client to interact with OpenAI's API, allowing for
        different types of AI model interactions, like chat or text completion.

        Args:
            ai_model_id (str): OpenAI model identifier. Must be non-empty.
                Default to a preset value.
            api_key (str): OpenAI API key for authentication.
                Must be non-empty. (Optional)
            ai_model_type (OpenAIModelTypes): The type of OpenAI
                model to interact with. Defaults to CHAT.
            org_id (str): OpenAI organization ID. This is optional
                unless the account belongs to multiple organizations.
            default_headers (Mapping[str, str]): Default headers
                for HTTP requests. (Optional)
            client (AsyncOpenAI): An existing OpenAI client, optional.
            instruction_role (str): The role to use for 'instruction'
                messages, for example, summarization prompts could use `developer` or `system`. (Optional)
            kwargs: Additional keyword arguments.

        """
        # Merge APP_INFO into the headers if it exists
        merged_headers = dict(copy(default_headers)) if default_headers else {}
        if APP_INFO:
            merged_headers.update(APP_INFO)
            merged_headers = prepend_agent_framework_to_user_agent(merged_headers)

        if not client:
            if not api_key:
                raise ServiceInitializationError("Please provide an api_key")
            client = AsyncOpenAI(
                api_key=api_key,
                organization=org_id,
                default_headers=merged_headers,
            )
        args = {
            "ai_model_id": ai_model_id,
            "client": client,
            "ai_model_type": ai_model_type,
        }
        if instruction_role:
            args["instruction_role"] = instruction_role
        super().__init__(**args, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Create a dict of the service settings."""
        client_settings = {
            "api_key": self.client.api_key,
            "default_headers": {k: v for k, v in self.client.default_headers.items() if k != USER_AGENT_KEY},
        }
        if self.client.organization:
            client_settings["org_id"] = self.client.organization
        base = self.model_dump(
            exclude={
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "api_type",
                "ai_model_type",
                "client",
            },
            by_alias=True,
            exclude_none=True,
        )
        base.update(client_settings)
        return base
