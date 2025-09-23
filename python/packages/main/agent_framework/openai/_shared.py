# Copyright (c) Microsoft. All rights reserved.

import json
import logging
from collections.abc import Mapping
from copy import copy
from typing import Annotated, Any, ClassVar, Union

from openai import (
    AsyncOpenAI,
    AsyncStream,
    _legacy_response,  # type: ignore
)
from openai.types import Completion
from openai.types.audio import Transcription
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.images_response import ImagesResponse
from openai.types.responses.response import Response
from openai.types.responses.response_stream_event import ResponseStreamEvent
from pydantic import BaseModel, ConfigDict, Field, SecretStr, validate_call
from pydantic.types import StringConstraints

from .._logging import get_logger
from .._pydantic import AFBaseModel, AFBaseSettings
from .._telemetry import APP_INFO, USER_AGENT_KEY, prepend_agent_framework_to_user_agent
from .._types import ChatOptions, Contents, SpeechToTextOptions, TextToSpeechOptions
from ..exceptions import ServiceInitializationError

logger: logging.Logger = get_logger("agent_framework.openai")


RESPONSE_TYPE = Union[
    ChatCompletion,
    Completion,
    AsyncStream[ChatCompletionChunk],
    AsyncStream[Completion],
    list[Any],
    ImagesResponse,
    Response,
    AsyncStream[ResponseStreamEvent],
    Transcription,
    _legacy_response.HttpxBinaryResponseContent,
]

OPTION_TYPE = Union[ChatOptions, SpeechToTextOptions, TextToSpeechOptions, dict[str, Any]]


__all__ = [
    "OpenAISettings",
]


def _prepare_function_call_results_as_dumpable(content: Contents | Any | list[Contents | Any]) -> Any:
    if isinstance(content, list):
        # Particularly deal with lists of BaseModel
        return [_prepare_function_call_results_as_dumpable(item) for item in content]
    if isinstance(content, dict):
        return {k: _prepare_function_call_results_as_dumpable(v) for k, v in content.items()}
    if isinstance(content, BaseModel):
        return content.model_dump(exclude={"raw_representation", "additional_properties"})
    return content


def prepare_function_call_results(content: Contents | Any | list[Contents | Any]) -> str | list[str]:
    """Prepare the values of the function call results."""
    if isinstance(content, BaseModel):
        # BaseModel is already dumpable, shortcut for performance
        return content.model_dump_json(exclude={"raw_representation", "additional_properties"})

    dumpable = _prepare_function_call_results_as_dumpable(content)
    if isinstance(dumpable, str):
        return dumpable
    # fallback
    return json.dumps(dumpable)


class OpenAISettings(AFBaseSettings):
    """OpenAI environment settings.

    The settings are first loaded from environment variables with the prefix 'OPENAI_'.
    If the environment variables are not found, the settings can be loaded from a .env file with the
    encoding 'utf-8'. If the settings are not found in the .env file, the settings are ignored;
    however, validation will fail alerting that the settings are missing.

    Attributes:
        api_key: OpenAI API key, see https://platform.openai.com/account/api-keys
            (Env var OPENAI_API_KEY)
        base_url: The base URL for the OpenAI API.
            (Env var OPENAI_BASE_URL)
        org_id: This is usually optional unless your account belongs to multiple organizations.
            (Env var OPENAI_ORG_ID)
        chat_model_id: The OpenAI chat model ID to use, for example, gpt-3.5-turbo or gpt-4.
            (Env var OPENAI_CHAT_MODEL_ID)
        responses_model_id: The OpenAI responses model ID to use, for example, gpt-4o or o1.
            (Env var OPENAI_RESPONSES_MODEL_ID)
        text_model_id: The OpenAI text model ID to use, for example, gpt-3.5-turbo-instruct.
            (Env var OPENAI_TEXT_MODEL_ID)
        embedding_model_id: The OpenAI embedding model ID to use, for example, text-embedding-ada-002.
            (Env var OPENAI_EMBEDDING_MODEL_ID)
        text_to_image_model_id: The OpenAI text to image model ID to use, for example, dall-e-3.
            (Env var OPENAI_TEXT_TO_IMAGE_MODEL_ID)
        audio_to_text_model_id: The OpenAI audio to text model ID to use, for example, whisper-1.
            (Env var OPENAI_AUDIO_TO_TEXT_MODEL_ID)
        text_to_audio_model_id: The OpenAI text to audio model ID to use, for example, jukebox-1.
            (Env var OPENAI_TEXT_TO_AUDIO_MODEL_ID)
        realtime_model_id: The OpenAI realtime model ID to use,
            for example, gpt-4o-realtime-preview-2024-12-17.
            (Env var OPENAI_REALTIME_MODEL_ID)

    Parameters:
        env_file_path: The path to the .env file to load settings from.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.
    """

    env_prefix: ClassVar[str] = "OPENAI_"

    api_key: SecretStr | None = None
    base_url: str | None = None
    org_id: str | None = None
    chat_model_id: str | None = None
    responses_model_id: str | None = None
    text_model_id: str | None = None
    embedding_model_id: str | None = None
    text_to_image_model_id: str | None = None
    audio_to_text_model_id: str | None = None
    text_to_audio_model_id: str | None = None
    realtime_model_id: str | None = None


class OpenAIBase(AFBaseModel):
    """Base class for OpenAI Clients."""

    client: AsyncOpenAI
    ai_model_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class OpenAIConfigMixin(OpenAIBase):
    """Internal class for configuring a connection to an OpenAI service."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "openai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    @validate_call(config=ConfigDict(arbitrary_types_allowed=True))
    def __init__(
        self,
        ai_model_id: str = Field(min_length=1),
        api_key: str | None = Field(min_length=1),
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a client for OpenAI services.

        This constructor sets up a client to interact with OpenAI's API, allowing for
        different types of AI model interactions, like chat or text completion.

        Args:
            ai_model_id: OpenAI model identifier. Must be non-empty.
                Default to a preset value.
            api_key: OpenAI API key for authentication.
                Must be non-empty. (Optional)
            org_id: OpenAI organization ID. This is optional
                unless the account belongs to multiple organizations.
            default_headers: Default headers
                for HTTP requests. (Optional)
            client: An existing OpenAI client, optional.
            instruction_role: The role to use for 'instruction'
                messages, for example, summarization prompts could use `developer` or `system`. (Optional)
            base_url: The optional base URL to use. If provided will override the standard value for a OpenAI connector.
                Will not be used when supplying a custom client.
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
            args: dict[str, Any] = {"api_key": api_key, "default_headers": merged_headers}
            if org_id:
                args["organization"] = org_id
            if base_url:
                args["base_url"] = base_url
            client = AsyncOpenAI(**args)
        args = {
            "ai_model_id": ai_model_id,
            "client": client,
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
                "client",
            },
            by_alias=True,
            exclude_none=True,
        )
        base.update(client_settings)
        return base
