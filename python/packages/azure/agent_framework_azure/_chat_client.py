# Copyright (c) Microsoft. All rights reserved.

import json
import logging
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, TypeVar
from uuid import uuid4

from agent_framework import (
    ChatFinishReason,
    ChatResponse,
    ChatResponseUpdate,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
)
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.openai._chat_client import OpenAIChatClientBase
from agent_framework.openai._shared import OpenAIModelTypes
from openai.lib.azure import AsyncAzureADTokenProvider, AsyncAzureOpenAI
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from pydantic import SecretStr, ValidationError
from pydantic.networks import AnyUrl

from ._shared import (
    DEFAULT_AZURE_API_VERSION,
    DEFAULT_AZURE_TOKEN_ENDPOINT,
    AzureOpenAIConfigBase,
    AzureOpenAISettings,
)

logger: logging.Logger = logging.getLogger(__name__)

TChatResponse = TypeVar("TChatResponse", ChatResponse, ChatResponseUpdate)


class AzureChatClient(AzureOpenAIConfigBase, OpenAIChatClientBase):
    """Azure Chat completion class."""

    def __init__(
        self,
        api_key: str | None = None,
        deployment_name: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: AsyncAzureADTokenProvider | None = None,
        token_endpoint: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
    ) -> None:
        """Initialize an AzureChatCompletion service.

        Args:
            api_key: The optional api key. If provided, will override the value in the
                env vars or .env file.
            deployment_name: The optional deployment. If provided, will override the value
                (chat_deployment_name) in the env vars or .env file.
            endpoint: The optional deployment endpoint. If provided will override the value
                in the env vars or .env file.
            base_url: The optional deployment base_url. If provided will override the value
                in the env vars or .env file.
            api_version: The optional deployment api version. If provided will override the value
                in the env vars or .env file.
            ad_token: The Azure Active Directory token. (Optional)
            ad_token_provider: The Azure Active Directory token provider. (Optional)
            token_endpoint: The token endpoint to request an Azure token. (Optional)
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests. (Optional)
            async_client: An existing client to use. (Optional)
            env_file_path: Use the environment settings file as a fallback to using env vars.
            env_file_encoding: The encoding of the environment settings file, defaults to 'utf-8'.
            instruction_role: The role to use for 'instruction' messages, for example, summarization
                prompts could use `developer` or `system`. (Optional)
        """
        try:
            # Filter out any None values from the arguments
            azure_openai_settings = AzureOpenAISettings(
                api_key=SecretStr(api_key) if api_key else None,
                base_url=AnyUrl(base_url) if base_url else None,
                endpoint=AnyUrl(endpoint) if endpoint else None,
                chat_deployment_name=deployment_name,
                api_version=api_version or DEFAULT_AZURE_API_VERSION,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
                token_endpoint=token_endpoint or DEFAULT_AZURE_TOKEN_ENDPOINT,
            )
        except ValidationError as exc:
            raise ServiceInitializationError(f"Failed to validate settings: {exc}") from exc

        if not azure_openai_settings.chat_deployment_name:
            raise ServiceInitializationError("chat_deployment_name is required.")

        super().__init__(
            deployment_name=azure_openai_settings.chat_deployment_name,
            endpoint=azure_openai_settings.endpoint,
            base_url=azure_openai_settings.base_url,
            api_version=azure_openai_settings.api_version,
            api_key=azure_openai_settings.api_key.get_secret_value() if azure_openai_settings.api_key else None,
            ad_token=ad_token,
            ad_token_provider=ad_token_provider,
            token_endpoint=azure_openai_settings.token_endpoint,
            default_headers=default_headers,
            ai_model_type=OpenAIModelTypes.CHAT,
            client=async_client,
            instruction_role=instruction_role,
        )

    @classmethod
    def from_dict(cls, settings: dict[str, Any]) -> "AzureChatClient":
        """Initialize an Azure OpenAI service from a dictionary of settings.

        Args:
            settings: A dictionary of settings for the service.
                should contain keys: service_id, and optionally:
                ad_auth, ad_token_provider, default_headers
        """
        return AzureChatClient(
            api_key=settings.get("api_key"),
            deployment_name=settings.get("deployment_name"),
            endpoint=settings.get("endpoint"),
            base_url=settings.get("base_url"),
            api_version=settings.get("api_version"),
            ad_token=settings.get("ad_token"),
            ad_token_provider=settings.get("ad_token_provider"),
            default_headers=settings.get("default_headers"),
            env_file_path=settings.get("env_file_path"),
        )

    def _create_chat_message_content(
        self, response: ChatCompletion, choice: Choice, response_metadata: dict[str, Any]
    ) -> ChatResponse:
        """Create an Azure chat message content object from a choice."""
        content = super()._create_chat_message_content(response, choice, response_metadata)
        return self._add_tool_message_to_chat_message_content(content, choice)

    def _create_streaming_chat_message_content(
        self,
        chunk: ChatCompletionChunk,
        choice: ChunkChoice,
        chunk_metadata: dict[str, Any],
    ) -> ChatResponseUpdate:
        """Create an Azure streaming chat message content object from a choice."""
        content = super()._create_streaming_chat_message_content(chunk, choice, chunk_metadata)
        assert isinstance(content, ChatResponseUpdate) and isinstance(choice, ChunkChoice)  # nosec # noqa: S101
        return self._add_tool_message_to_chat_message_content(content, choice)

    def _add_tool_message_to_chat_message_content(
        self,
        content: TChatResponse,
        choice: Choice | ChunkChoice,
    ) -> TChatResponse:
        if tool_message := self._get_tool_message_from_chat_choice(choice=choice):
            if not isinstance(tool_message, dict):
                # try to json, to ensure it is a dictionary
                try:
                    tool_message = json.loads(tool_message)
                except json.JSONDecodeError:
                    logger.warning("Tool message is not a dictionary, ignore context.")
                    return content
            function_call = FunctionCallContent(
                call_id=str(uuid4()),
                name="Azure-OnYourData",
                arguments={"query": tool_message.get("intent", [])},
            )
            result = FunctionResultContent(
                call_id=function_call.call_id,
                result=tool_message["citations"],
                exception=function_call.exception,
                additional_properties=function_call.additional_properties,
            )

            inner_content = content.messages[0].contents if isinstance(content, ChatResponse) else content.contents

            inner_content.insert(0, function_call)
            inner_content.insert(1, result)
        return content

    def _get_tool_message_from_chat_choice(self, choice: Choice | ChunkChoice) -> dict[str, Any] | None:
        """Get the tool message from a choice."""
        content = choice.message if isinstance(choice, Choice) else choice.delta
        # When you enable asynchronous content filtering in Azure OpenAI, you may receive empty deltas
        if content and content.model_extra is not None:
            return content.model_extra.get("context", None)
        # openai allows extra content, so model_extra will be a dict, but we need to check anyway, but no way to test.
        return None  # pragma: no cover

    @staticmethod
    def _split_message(message: "ChatResponse") -> ChatResponse:
        """Split an Azure On Your Data response into separate ChatMessages within the ChatResponse.

        If the message does not have three contents, and those three are one each of:
        FunctionCallContent, FunctionResultContent, and TextContent,
        it will not return three messages, potentially only one or two.

        The order of the returned messages is as expected by OpenAI.
        """
        if len(message.messages) == 0:
            return message
        if len(message.messages[0].contents) != 3:
            return message
        messages = {
            "tool_call": deepcopy(message.messages[0]),
            "tool_result": deepcopy(message.messages[0]),
            "assistant": deepcopy(message.messages[0]),
        }
        for key, msg in messages.items():
            if key == "tool_call":
                msg.contents = [item for item in msg.contents if isinstance(item, FunctionCallContent)]
                message.finish_reason = ChatFinishReason.TOOL_CALLS
            if key == "tool_result":
                msg.contents = [item for item in msg.contents if isinstance(item, FunctionResultContent)]
            if key == "assistant":
                msg.contents = [item for item in msg.contents if isinstance(item, TextContent)]

        return ChatResponse(
            response_id=message.response_id,
            conversation_id=message.conversation_id,
            messages=[messages["tool_call"], messages["tool_result"], messages["assistant"]],
            created_at=message.created_at,
            model_id=message.ai_model_id,
            usage_details=message.usage_details,
            finish_reason=message.finish_reason,
            additional_properties=message.additional_properties,
        )
