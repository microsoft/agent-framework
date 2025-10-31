# Copyright (c) Microsoft. All rights reserved.


from collections.abc import AsyncIterable, MutableSequence
from typing import Any, ClassVar, cast

from agent_framework import (
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError, ServiceResponseException
from agent_framework.observability import use_observability
from agent_framework.openai._responses_client import OpenAIBaseResponsesClient
from litellm import ResponsesAPIResponse, responses  # type: ignore
from litellm.responses.streaming_iterator import SyncResponsesAPIStreamingIterator
from litellm.types.llms.openai import ResponsesAPIStreamingResponse
from openai.types.responses.response import Response as OpenAIResponse
from openai.types.responses.response_stream_event import ResponseStreamEvent as OpenAIResponseStreamEvent
from pydantic import ValidationError


class LiteLlmResponsesAISettings(AFBaseSettings):
    """LiteLLM AI Responses settings.

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


@use_function_invocation
@use_observability
@use_chat_middleware
class LiteLlmResponsesClient(OpenAIBaseResponsesClient):
    """LiteLLM Responses completion class.

    This client is used to interact with LiteLLM models via the Agent Framework. Note that LiteLLM is not fully OpenAI
    API compatible, so some features may not be supported. However, LiteLLM follows the OpenAI API structure closely
    enough to allow for basic interactions.
    """

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
            lite_llm_settings = LiteLlmResponsesAISettings(
                model_id=model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create LiteLLM settings.", ex) from ex

        if lite_llm_settings.model_id is None:
            raise ServiceInitializationError(
                "model_id parameter, or LITE_LLM_MODEL_ID env variable must be provided for LiteLlmResponsesClient"
            )

        self.model_id = str(lite_llm_settings.model_id)

        super().__init__(api_base=api_base, api_key=api_key, model_id=self.model_id, client=None, **kwargs)  # type: ignore

    def make_responses_streaming_request(self, **options_dict: Any) -> SyncResponsesAPIStreamingIterator:
        options_dict["model"] = options_dict.pop("model_id")
        lite_llm_response = responses(stream=True, **options_dict)
        # Responses conditionally returns this depending on streaming vs non-streaming
        return cast(SyncResponsesAPIStreamingIterator, lite_llm_response)

    def make_responses_nonstreaming_request(self, **options_dict: Any) -> ResponsesAPIResponse:
        options_dict["model"] = options_dict.pop("model_id")
        lite_llm_response = responses(stream=False, **options_dict)
        # Responses conditionally returns this depending on streaming vs non-streaming
        return cast(ResponsesAPIResponse, lite_llm_response)

    def lite_llm_to_openai_response(self, response: ResponsesAPIResponse) -> OpenAIResponse:
        # Convert a LiteLLM ResponsesAPIResponse to an OpenAI Response. LiteLLM aims to match the OpenAI API,
        # however in the future there may be differences that need to be accounted for here.
        return cast(OpenAIResponse, response)

    def lite_llm_event_to_openai_event(self, event: ResponsesAPIStreamingResponse) -> OpenAIResponseStreamEvent:
        # Convert a LiteLLM ResponsesAPIResponse to an OpenAI Response. LiteLLM aims to match the OpenAI API,
        # however in the future there may be differences that need to be accounted for here.
        return cast(OpenAIResponseStreamEvent, event)

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        options_dict = self._prepare_options(messages, chat_options)
        options_dict["model_id"] = self.model_id

        if chat_options.response_format is not None:
            raise NotImplementedError("Response format parsing is not implemented for LiteLLM.")

        try:
            lite_llm_response = self.make_responses_nonstreaming_request(**options_dict)

            response = self.lite_llm_to_openai_response(lite_llm_response)
            chat_options.conversation_id = response.id if chat_options.store is True else None
            return self._create_response_content(response, chat_options=chat_options)

        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        options_dict = self._prepare_options(messages, chat_options)
        options_dict["model_id"] = self.model_id
        function_call_ids: dict[int, tuple[str, str]] = {}  # output_index: (call_id, name)

        if chat_options.response_format is not None:
            raise NotImplementedError("Response format parsing is not implemented for LiteLLM.")

        try:
            lite_llm_response = self.make_responses_streaming_request(**options_dict)

            for event in lite_llm_response:
                update = self._create_streaming_response_content(
                    cast(OpenAIResponseStreamEvent, event),
                    chat_options=chat_options,
                    function_call_ids=function_call_ids,
                )
                yield update
            return

        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex
