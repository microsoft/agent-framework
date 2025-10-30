# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import AsyncIterable, MutableMapping, MutableSequence, Sequence
from typing import Any, ClassVar, TypeVar

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    AIFunction,
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Contents,
    FinishReason,
    FunctionCallContent,
    HostedWebSearchTool,
    Role,
    TextContent,
    TextReasoningContent,
    ToolProtocol,
    UsageDetails,
    get_logger,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.observability import use_observability
from anthropic import AsyncAnthropic
from anthropic.types import ContentBlock, Message, MessageDeltaUsage, RawContentBlockDelta, RawMessageStreamEvent, Usage
from pydantic import SecretStr, ValidationError

logger = get_logger("agent_framework.anthropic")


ROLE_MAP: dict[Role, str] = {
    Role.USER: "user",
    Role.ASSISTANT: "assistant",
    Role.SYSTEM: "user",
    Role.TOOL: "user",
}

FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop_sequence": FinishReason.STOP,
    "max_tokens": FinishReason.LENGTH,
    "tool_use": FinishReason.TOOL_CALLS,
    "end_turn": FinishReason.STOP,
    "refusal": FinishReason.CONTENT_FILTER,
    "pause_turn": FinishReason.STOP,
}


class AnthropicSettings(AFBaseSettings):
    """Anthropic Project settings.

    The settings are first loaded from environment variables with the prefix 'ANTHROPIC_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        api_key: The Anthropic API key.
        chat_model_id: The Anthropic chat model ID.
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework.anthropic import AnthropicSettings

            # Using environment variables
            # Set ANTHROPIC_API_KEY=your_anthropic_api_key
            # ANTHROPIC_CHAT_MODEL_ID=claude-sonnet-4-5-20250929

            # Or passing parameters directly
            settings = AnthropicSettings(chat_model_id="claude-sonnet-4-5-20250929")

            # Or loading from a .env file
            settings = AnthropicSettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "ANTHROPIC_"

    api_key: SecretStr | None = None
    chat_model_id: str | None = None


TAnthropicClient = TypeVar("TAnthropicClient", bound="AnthropicClient")


@use_function_invocation
@use_observability
@use_chat_middleware
class AnthropicClient(BaseChatClient):
    """Anthropic Chat client."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "anthropic"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        anthropic_client: AsyncAnthropic | None = None,
        api_key: str | None = None,
        model_id: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Anthropic Agent client.

        Keyword Args:
            anthropic_client: An existing Anthropic client to use. If not provided, one will be created.
            api_key: The Anthropic API key to use for authentication.
            model_id: The ID of the model to use.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
            kwargs: Additional keyword arguments passed to the parent class.

        Examples:
            .. code-block:: python

                from agent_framework.anthropic import AnthropicClient
                from azure.identity.aio import DefaultAzureCredential

                # Using environment variables
                # Set AZURE_AI_PROJECT_ENDPOINT=https://your-project.cognitiveservices.azure.com
                # Set AZURE_AI_MODEL_DEPLOYMENT_NAME=claude-sonnet-4-5-20250929
                credential = DefaultAzureCredential()
                client = AnthropicClient(async_credential=credential)

                # Or passing parameters directly
                client = AnthropicClient(
                    model_name="claude-sonnet-4-5-20250929",
                    async_credential=credential,
                )

                # Or loading from a .env file
                client = AnthropicClient(async_credential=credential, env_file_path="path/to/.env")
        """
        try:
            anthropic_settings = AnthropicSettings(
                api_key=api_key,  # type: ignore[arg-type]
                chat_model_id=model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create Anthropic settings.", ex) from ex

        if anthropic_client is None:
            if not anthropic_settings.api_key:
                raise ServiceInitializationError(
                    "Anthropic API key is required. Set via 'api_key' parameter "
                    "or 'AZURE_AI_API_KEY' environment variable."
                )

            anthropic_client = AsyncAnthropic(api_key=anthropic_settings.api_key.get_secret_value())

        # Initialize parent
        super().__init__(**kwargs)

        # Initialize instance variables
        self.anthropic_client = anthropic_client
        self.model_id = anthropic_settings.chat_model_id

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        # Extract necessary state from messages and options
        run_options = self._create_run_options(messages, chat_options, **kwargs)

        message = await self.anthropic_client.messages.create(**run_options, stream=False)
        return self._process_message(message)

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        # Extract necessary state from messages and options
        run_options = self._create_run_options(messages, chat_options, **kwargs)

        stream = await self.anthropic_client.messages.create(**run_options, stream=True)
        async for chunk in stream:
            parsed_chunk = self._process_stream_event(chunk)
            if parsed_chunk:
                yield parsed_chunk

    def _process_message(self, message: Message) -> ChatResponse:
        """Process the response from the Anthropic client.

        Args:
            message: The message returned by the Anthropic client.

        Returns:
            A ChatResponse object containing the processed response.
        """
        return ChatResponse(
            response_id=message.id,
            messages=[
                ChatMessage(
                    role=Role.ASSISTANT,
                    contents=self._parse_message_contents(message.content),
                    raw_representation=message,
                )
            ],
            usage_details=self._parse_message_usage(message.usage),
            model_id=message.model,
            finish_reason=FINISH_REASON_MAP.get(message.stop_reason) if message.stop_reason else None,
            raw_response=message,
        )

    def _parse_message_usage(self, usage: Usage | MessageDeltaUsage | None) -> UsageDetails | None:
        """Parse usage details from the Anthropic message usage."""
        if not usage:
            return None
        usage_details = UsageDetails(output_token_count=usage.output_tokens)
        if usage.input_tokens is not None:
            usage_details.input_token_count = usage.input_tokens
        if usage_details and usage:
            if usage.cache_creation_input_tokens:
                usage_details.additional_counts["anthropic.cache_creation_input_tokens"] = (
                    usage.cache_creation_input_tokens
                )
            if usage.cache_read_input_tokens:
                usage_details.additional_counts["anthropic.cache_read_input_tokens"] = usage.cache_read_input_tokens

        return usage_details

    def _parse_message_contents(self, content: Sequence[ContentBlock | RawContentBlockDelta]) -> list[Contents]:
        """Parse contents from the Anthropic message."""
        contents: list[Contents] = []
        for content_block in content:
            match content_block.type:
                case "text" | "text_delta":
                    contents.append(TextContent(text=content_block.text, raw_representation=content_block))
                case "tool_use":
                    self._last_call_id_name = (content_block.id, content_block.name)
                    contents.append(
                        FunctionCallContent(
                            call_id=content_block.id,
                            name=content_block.name,
                            arguments=content_block.input,
                            raw_representation=content_block,
                        )
                    )
                case "input_json_delta":
                    call_id, name = self._last_call_id_name if self._last_call_id_name else ("", "")
                    contents.append(
                        FunctionCallContent(
                            call_id=call_id,
                            name=name,
                            arguments=content_block.partial_json,
                            raw_representation=content_block,
                        )
                    )
                case "thinking" | "thinking_delta":
                    contents.append(TextReasoningContent(text=content_block.thinking, raw_representation=content_block))
                case _:
                    logger.debug(f"Ignoring unsupported content type: {content_block.type} for now")
        return contents

    def _process_stream_event(self, event: RawMessageStreamEvent) -> ChatResponseUpdate | None:
        """Process a streaming event from the Anthropic client.

        Args:
            event: The streaming event returned by the Anthropic client.

        Returns:
            A ChatResponseUpdate object containing the processed update.
        """
        contents: list[Contents] = []
        match event.type:
            case "message_start":
                return ChatResponseUpdate(
                    response_id=event.message.id,
                    contents=self._parse_message_contents(event.message.content),
                    usage_details=self._parse_message_usage(event.message.usage),
                    model_id=event.message.model,
                    finish_reason=FINISH_REASON_MAP.get(event.message.stop_reason)
                    if event.message.stop_reason
                    else None,
                    raw_response=event,
                )
            case "message_delta":
                return ChatResponseUpdate(
                    usage_details=self._parse_message_usage(event.usage),
                    raw_response=event,
                )
            case "message_stop":
                logger.debug("Received message_stop event; no content to process.")
                return None
            case "content_block_start":
                contents = self._parse_message_contents([event.content_block])
                return ChatResponseUpdate(
                    contents=contents,
                    raw_response=event,
                )
            case "content_block_delta":
                contents = self._parse_message_contents([event.delta])
                return ChatResponseUpdate(
                    contents=contents,
                    raw_response=event,
                )
            case "content_block_stop":
                logger.debug("Received content_block_stop event; no content to process.")
                return None
            case _:
                logger.debug(f"Ignoring unsupported event type: {event.type}")
                return None

    def _create_run_options(
        self, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
    ) -> dict[str, Any]:
        """Create run options for the Anthropic client based on messages and chat options.

        Args:
            messages: The list of chat messages.
            chat_options: The chat options.
            kwargs: Additional keyword arguments.

        Returns:
            A dictionary of run options for the Anthropic client.
        """
        run_options: dict[str, Any] = {
            "model": chat_options.model_id or self.model_id,
            "messages": self._convert_messages_to_anthropic_format(messages),
            "max_tokens": chat_options.max_tokens or 1024,
            "extra_headers": {"User-Agent": AGENT_FRAMEWORK_USER_AGENT},
        }

        # Add any additional options from chat_options or kwargs
        if chat_options.temperature is not None:
            run_options["temperature"] = chat_options.temperature
        if chat_options.top_p is not None:
            run_options["top_p"] = chat_options.top_p
        if chat_options.stop is not None:
            run_options["stop_sequences"] = chat_options.stop
        if messages[0].role == Role.SYSTEM:
            # first system message is passed as instructions
            run_options["system"] = messages[0].text
        if chat_options.tool_choice is not None:
            match (
                chat_options.tool_choice if isinstance(chat_options.tool_choice, str) else chat_options.tool_choice.mode
            ):
                case "auto":
                    run_options["tool_choice"] = {"type": "auto"}
                case "required":
                    run_options["tool_choice"] = {
                        "type": "tool",
                        "name": chat_options.tool_choice.required_function_name,
                    }
                case "none":
                    run_options["tool_choice"] = {"type": "none"}
                case _:
                    logger.debug(f"Ignoring unsupported tool choice mode: {chat_options.tool_choice.mode} for now")
        if tools := self._convert_tools_to_anthropic_format(chat_options.tools):
            run_options["tools"] = tools
        run_options.update(kwargs)
        return run_options

    def _convert_messages_to_anthropic_format(self, messages: MutableSequence[ChatMessage]) -> list[dict[str, Any]]:
        # first system message is passed as instructions
        if messages[0].role == Role.SYSTEM:
            return [self._convert_message_to_anthropic_format(msg) for msg in messages[1:]]
        return [self._convert_message_to_anthropic_format(msg) for msg in messages]

    def _convert_message_to_anthropic_format(self, message: ChatMessage) -> dict[str, Any]:
        """Convert a ChatMessage to the format expected by the Anthropic client.

        Args:
            message: The ChatMessage to convert.

        Returns:
            A dictionary representing the message in Anthropic format.
        """
        a_content: list[dict[str, Any]] = []
        for content in message.contents:
            match content.type:
                case "text":
                    a_content.append({"type": "text", "text": content.text})
                case "data":
                    if content.has_top_level_media_type("image"):
                        a_content.append({
                            "type": "image",
                            "source": {"data": content.uri, "media_type": content.media_type},
                        })
                case "uri":
                    if content.has_top_level_media_type("image"):
                        a_content.append({"type": "image", "source": {"type": "url", "url": content.uri}})
                case "function_call":
                    a_content.append({
                        "type": "tool_use",
                        "id": content.call_id,
                        "name": content.name,
                        "input": content.parse_arguments(),
                    })
                case "function_result":
                    a_content.append({
                        "type": "tool_result",
                        "tool_use_id": content.call_id,
                        "content": json.dumps(content.result),  # TODO (eavanvalkenburg): handle other content types
                        "is_error": content.exception is not None,
                    })
                case "text_reasoning":
                    a_content.append({"type": "thinking", "thinking": content.text})
                case _:
                    logger.debug(f"Ignoring unsupported content type: {content.type} for now")

        return {
            "role": ROLE_MAP.get(message.role, "user"),
            "content": a_content,
        }

    def _convert_tools_to_anthropic_format(
        self, tools: list[ToolProtocol | MutableMapping[str, Any]] | None
    ) -> list[MutableMapping[str, Any]] | None:
        if not tools:
            return None
        tool_list: list[MutableMapping[str, Any]] = []
        for tool in tools:
            if converted_tool := self._convert_tool_to_anthropic_format(tool):
                tool_list.append(converted_tool)
        return tool_list

    def _convert_tool_to_anthropic_format(
        self, tool: ToolProtocol | MutableMapping[str, Any]
    ) -> MutableMapping[str, Any] | None:
        """Convert an AIFunction tool to the format expected by the Anthropic client.

        Args:
            tool: The AIFunction tool to convert.

        Returns:
            A dictionary representing the tool in Anthropic format.
        """
        if isinstance(tool, MutableMapping):
            return tool  # Assume already in correct format
        match tool:
            case AIFunction():
                return {
                    "type": "custom",
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters(),
                }
            case HostedWebSearchTool():
                ret: dict[str, Any] = {
                    "type": "web_search_20250305",
                    "name": "web_search",
                }
                if tool.additional_properties:
                    ret.update(tool.additional_properties)
                return ret
            case _:
                logger.debug(f"Ignoring unsupported tool type: {type(tool)} for now")
                return None

    def service_url(self) -> str:
        """Get the service URL for the chat client.

        Returns:
            The service URL for the chat client, or None if not set.
        """
        return str(self.anthropic_client.base_url)
