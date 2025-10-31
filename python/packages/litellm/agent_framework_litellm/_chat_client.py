# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, MutableSequence
from typing import Any, ClassVar, cast

from agent_framework import (
    get_logger,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework._types import ChatMessage, ChatOptions, ChatResponse, ChatResponseUpdate
from agent_framework.exceptions import ServiceInitializationError, ServiceResponseException
from agent_framework.observability import use_observability
from agent_framework.openai._chat_client import OpenAIBaseChatClient
from litellm import CustomStreamWrapper, ModelResponse, ModelResponseStream, completion  # type: ignore
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from pydantic import ValidationError


class LiteLlmCompletionAISettings(AFBaseSettings):
    """LiteLLM AI Completion settings.

    The settings are first loaded from environment variables with the prefix 'LITE_LLM_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        model_id: The model to use, including both the provider and model (e.g., "azure_openai/gpt-4").
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework_litellm import LiteLlmAISettings

            # Using environment variables
            # Set LITE_LLM_MODEL_ID=azure_openai/gpt-4
            settings = LiteLlmAISettings()

            # Or passing parameters directly
            settings = LiteLlmAISettings(model_id="azure_openai/gpt-4")

            # Or loading from a .env file
            settings = LiteLlmAISettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "LITE_LLM_"

    model_id: str | None = None


logger = get_logger("agent_framework.litellm")


@use_function_invocation
@use_observability
@use_chat_middleware
class LiteLlmChatClient(OpenAIBaseChatClient):
    """LiteLLM Chat client.

    This client is used to interact with LiteLLM models via the Agent Framework. Note that LiteLLM is not fully OpenAI
    API compatible, so some features may not be supported. However, LiteLLM follows the OpenAI API structure closely
    enough to allow for basic interactions.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "litellm"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = "utf-8",
        model_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base

        try:
            lite_llm_settings = LiteLlmCompletionAISettings(
                model_id=model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create LiteLLM settings.", ex) from ex

        if lite_llm_settings.model_id is None:
            raise ServiceInitializationError(
                "model_id parameter, or LITE_LLM_MODEL_ID env variable must be provided for LiteLlmChatClient"
            )

        self.model_id = str(lite_llm_settings.model_id)

        super().__init__(api_base=api_base, api_key=api_key, model_id=self.model_id, client=None, **kwargs)  # type: ignore

    def make_completion_streaming_request(self, **options_dict: Any) -> CustomStreamWrapper:
        options_dict["model"] = options_dict.pop("model_id")
        lite_llm_response = completion(stream=True, **options_dict)
        # Completion conditionally returns this depending on streaming vs non-streaming
        return cast(CustomStreamWrapper, lite_llm_response)

    def make_completion_nonstreaming_request(self, **options_dict: Any) -> ModelResponse:
        options_dict["model"] = options_dict.pop("model_id")
        lite_llm_response = completion(stream=False, **options_dict)
        # Completion conditionally returns this depending on streaming vs non-streaming
        return cast(ModelResponse, lite_llm_response)

    def lite_llm_to_openai_completion(self, response: ModelResponse) -> ChatCompletion:
        # Convert a LiteLLM ResponsesAPIResponse to an OpenAI Response. LiteLLM aims to match the OpenAI A  I,
        # however in the future there may be differences that need to be accounted for here.
        return cast(ChatCompletion, response)

    def lite_llm_event_to_openai_event(self, event: ModelResponseStream) -> ChatCompletionChunk:
        # Convert a LiteLLM ResponsesAPIResponse to an OpenAI Response. LiteLLM aims to match the OpenAI API,
        # however in the future there may be differences that need to be accounted for here.
        openai_event = cast(ChatCompletionChunk, event)

        # LiteLLM does not providet this as a first-class field, so we map it here.
        openai_event.usage = event.get("usage", None)
        return openai_event

    def lite_llm_to_openai_response(self, response: ModelResponse) -> ChatCompletion:
        """Convert a LiteLLM ModelResponse to an OpenAI ChatCompletion."""
        # OpenAI parsing code currently directly checks for OpenAI classes. However,
        # LiteLLM implements the OpenAI API via its own classes, compatable via
        # duck typing. Therefore, we need to convert the LiteLLM ModelResponse
        # to an OpenAI ChatCompletion for compatibility.

        # You may need to adapt this mapping based on the actual structure of ModelResponse
        # and the expected fields of ChatCompletion.
        # Here is a basic example assuming similar structure:
        return ChatCompletion(**response.dict())

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        options_dict = self._prepare_options(messages, chat_options)
        options_dict["model_id"] = self.model_id

        response = self.make_completion_nonstreaming_request(**options_dict)

        open_ai_response = self.lite_llm_to_openai_response(response)

        return self._create_chat_response(open_ai_response, chat_options)

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        options_dict = self._prepare_options(messages, chat_options)
        options_dict["model_id"] = self.model_id
        options_dict["stream_options"] = {"include_usage": True}
        try:
            for event in self.make_completion_streaming_request(**options_dict):
                chunk = self.lite_llm_event_to_openai_event(event)

                if len(chunk.choices) == 0:
                    continue
                yield self._create_chat_response_update(chunk)
        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex
