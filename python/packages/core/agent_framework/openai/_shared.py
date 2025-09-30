# Copyright (c) Microsoft. All rights reserved.

import json
import logging
from collections.abc import Mapping
from copy import copy
from typing import Any, ClassVar, Union

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
from pydantic import SecretStr

from .._logging import get_logger
from .._pydantic import AFBaseSettings
from .._serialization import SerializationMixin
from .._telemetry import APP_INFO, USER_AGENT_KEY, prepend_agent_framework_to_user_agent
from .._types import ChatOptions, Contents
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

OPTION_TYPE = Union[ChatOptions, dict[str, Any]]


__all__ = [
    "OpenAISettings",
]


def _prepare_function_call_results_as_dumpable(content: Contents | Any | list[Contents | Any]) -> Any:
    if isinstance(content, list):
        # Particularly deal with lists of Content
        return [_prepare_function_call_results_as_dumpable(item) for item in content]
    if isinstance(content, dict):
        return {k: _prepare_function_call_results_as_dumpable(v) for k, v in content.items()}
    if hasattr(content, "to_dict"):
        return content.to_dict(exclude={"raw_representation", "additional_properties"})
    return content


def prepare_function_call_results(content: Contents | Any | list[Contents | Any]) -> str | list[str]:
    """Prepare the values of the function call results."""
    if isinstance(content, Contents):
        # For BaseContent objects, use to_dict and serialize to JSON
        return json.dumps(content.to_dict(exclude={"raw_representation", "additional_properties"}))

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

    Args:
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
        env_file_path: The path to the .env file to load settings from.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.
    """

    env_prefix: ClassVar[str] = "OPENAI_"

    api_key: SecretStr | None = None
    base_url: str | None = None
    org_id: str | None = None
    chat_model_id: str | None = None
    responses_model_id: str | None = None


class OpenAIBase(SerializationMixin):
    """Base class for OpenAI Clients."""

    INJECTABLE: ClassVar[set[str]] = {"client"}

    def __init__(self, *, client: AsyncOpenAI, model_id: str, **kwargs: Any) -> None:
        """Initialize OpenAIBase.

        Args:
            client: The AsyncOpenAI client instance.
            model_id: The AI model ID to use (non-empty, whitespace stripped).
            **kwargs: Additional keyword arguments.
        """
        if not model_id or not model_id.strip():
            raise ValueError("model_id must be a non-empty string")
        self.client = client
        self.model_id = model_id.strip()

        # Call super().__init__() to continue MRO chain (e.g., BaseChatClient)
        # Extract known kwargs that belong to other base classes
        additional_properties = kwargs.pop("additional_properties", None)
        middleware = kwargs.pop("middleware", None)
        instruction_role = kwargs.pop("instruction_role", None)

        # Build super().__init__() args
        super_kwargs = {}
        if additional_properties is not None:
            super_kwargs["additional_properties"] = additional_properties
        if middleware is not None:
            super_kwargs["middleware"] = middleware

        # Call super().__init__() with filtered kwargs
        super().__init__(**super_kwargs)

        # Store instruction_role and any remaining kwargs as instance attributes
        if instruction_role is not None:
            self.instruction_role = instruction_role
        for key, value in kwargs.items():
            setattr(self, key, value)


class OpenAIConfigMixin(OpenAIBase):
    """Internal class for configuring a connection to an OpenAI service."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "openai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        model_id: str,
        api_key: str | None = None,
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
            model_id: OpenAI model identifier. Must be non-empty.
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

        # Store configuration as instance attributes for serialization
        self.org_id = org_id
        self.base_url = str(base_url)
        # Store default_headers but filter out USER_AGENT_KEY for serialization
        if default_headers:
            self.default_headers: dict[str, Any] | None = {
                k: v for k, v in default_headers.items() if k != USER_AGENT_KEY
            }
        else:
            self.default_headers = None

        args = {
            "model_id": model_id,
            "client": client,
        }
        if instruction_role:
            args["instruction_role"] = instruction_role

        # Ensure additional_properties and middleware are passed through kwargs to BaseChatClient
        # These are consumed by BaseChatClient.__init__ via kwargs
        super().__init__(**args, **kwargs)
