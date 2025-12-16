# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import (
    AsyncIterable,
    Callable,
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
)
from itertools import chain
from typing import Any, ClassVar

from agent_framework import (
    AIFunction,
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Contents,
    DataContent,
    FunctionCallContent,
    FunctionResultContent,
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
from agent_framework.exceptions import (
    ServiceInitializationError,
    ServiceInvalidRequestError,
    ServiceResponseException,
)
from agent_framework.observability import use_instrumentation
from ollama import AsyncClient

# Rename imported types to avoid naming conflicts with Agent Framework types
from ollama._types import ChatResponse as OllamaChatResponse
from ollama._types import Message as OllamaMessage
from pydantic import ValidationError


class OllamaSettings(AFBaseSettings):
    """Ollama settings."""

    env_prefix: ClassVar[str] = "OLLAMA_"

    host: str | None = None
    model_id: str | None = None


logger = get_logger("agent_framework.ollama")


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class OllamaChatClient(BaseChatClient):
    """Ollama Chat completion class."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "ollama"

    def __init__(
        self,
        *,
        host: str | None = None,
        client: AsyncClient | None = None,
        model_id: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Ollama Chat client.

        Keyword Args:
            host: Ollama server URL, if none `http://localhost:11434` is used.
                Can be set via the OLLAMA_HOST env variable.
            client: An optional Ollama Client instance. If not provided, a new instance will be created.
            model_id: The Ollama chat model ID to use. Can be set via the OLLAMA_MODEL_ID env variable.
            env_file_path: An optional path to a dotenv (.env) file to load environment variables from.
            env_file_encoding: The encoding to use when reading the dotenv (.env) file. Defaults to 'utf-8'.
            **kwargs: Additional keyword arguments passed to BaseChatClient.
        """
        try:
            ollama_settings = OllamaSettings(
                host=host,
                model_id=model_id,
                env_file_encoding=env_file_encoding,
                env_file_path=env_file_path,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create Ollama settings.", ex) from ex

        if ollama_settings.model_id is None:
            raise ServiceInitializationError(
                "Ollama chat model ID must be provided via model_id or OLLAMA_MODEL_ID environment variable."
            )

        self.model_id = ollama_settings.model_id
        self.client = client or AsyncClient(host=ollama_settings.host)
        # Save Host URL for serialization with to_dict()
        self.host = str(self.client._client.base_url)

        super().__init__(**kwargs)

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        options_dict = self._prepare_options(messages, chat_options)

        try:
            response: OllamaChatResponse = await self.client.chat(  # type: ignore[misc]
                stream=False,
                **options_dict,
                **kwargs,
            )
        except Exception as ex:
            raise ServiceResponseException(f"Ollama chat request failed : {ex}", ex) from ex

        return self._ollama_response_to_agent_framework_response(response)

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        options_dict = self._prepare_options(messages, chat_options)

        try:
            response_object: AsyncIterable[OllamaChatResponse] = await self.client.chat(  # type: ignore[misc]
                stream=True,
                **options_dict,
                **kwargs,
            )
        except Exception as ex:
            raise ServiceResponseException(f"Ollama streaming chat request failed : {ex}", ex) from ex

        async for part in response_object:
            yield self._ollama_streaming_response_to_agent_framework_response(part)

    def _prepare_options(self, messages: MutableSequence[ChatMessage], chat_options: ChatOptions) -> dict[str, Any]:
        # Preprocess web search tool if it exists
        options_dict = chat_options.to_dict(exclude={"instructions", "type"})

        # Promote additional_properties to the top level of options_dict
        additional_props = options_dict.pop("additional_properties", {})
        options_dict.update(additional_props)

        # Prepare Messages from Agent Framework format to Ollama format
        if messages and "messages" not in options_dict:
            options_dict["messages"] = self._prepare_chat_history_for_request(messages)
        if "messages" not in options_dict:
            raise ServiceInvalidRequestError("Messages are required for chat completions")

        # Prepare Tools from Agent Framework format to Json Schema format
        if chat_options.tools:
            options_dict["tools"] = self._chat_to_tool_spec(chat_options.tools)

        # Currently Ollama only supports auto tool choice
        if chat_options.tool_choice == "required":
            raise ServiceInvalidRequestError("Ollama does not support required tool choice.")
        # Always auto: remove tool_choice since Ollama does not expose configuration to force or disable tools.
        if "tool_choice" in options_dict:
            del options_dict["tool_choice"]

        # Rename model_id to model for Ollama API, if no model is provided use the one from client initialization
        if "model_id" in options_dict:
            options_dict["model"] = options_dict.pop("model_id")

        if "model_id" not in options_dict:
            options_dict["model"] = self.model_id

        return options_dict

    def _prepare_chat_history_for_request(self, messages: MutableSequence[ChatMessage]) -> list[OllamaMessage]:
        ollama_messages = [self._agent_framework_message_to_ollama_message(msg) for msg in messages]
        # Flatten the list of lists into a single list
        return list(chain.from_iterable(ollama_messages))

    def _agent_framework_message_to_ollama_message(self, message: ChatMessage) -> list[OllamaMessage]:
        message_converters: dict[str, Callable[[ChatMessage], list[OllamaMessage]]] = {
            Role.SYSTEM.value: self._format_system_message,
            Role.USER.value: self._format_user_message,
            Role.ASSISTANT.value: self._format_assistant_message,
            Role.TOOL.value: self._format_tool_message,
        }
        return message_converters[message.role.value](message)

    def _format_system_message(self, message: ChatMessage) -> list[OllamaMessage]:
        return [OllamaMessage(role="system", content=message.text)]

    def _format_user_message(self, message: ChatMessage) -> list[OllamaMessage]:
        if not any(isinstance(c, (DataContent, TextContent)) for c in message.contents) and not message.text:
            raise ServiceInvalidRequestError(
                "Ollama connector currently only supports user messages with TextContent or DataContent."
            )

        if not any(isinstance(c, DataContent) for c in message.contents):
            return [OllamaMessage(role="user", content=message.text)]

        user_message = OllamaMessage(role="user", content=message.text)
        data_contents = [c for c in message.contents if isinstance(c, DataContent)]
        if data_contents:
            if not any(c.has_top_level_media_type("image") for c in data_contents):
                raise ServiceInvalidRequestError("Only image data content is supported for user messages in Ollama.")
            # Ollama expects base64 strings without prefix
            user_message["images"] = [c.uri.split(",")[1] for c in data_contents]
        return [user_message]

    def _format_assistant_message(self, message: ChatMessage) -> list[OllamaMessage]:
        text_content = message.text
        reasoning_contents = "".join(c.text for c in message.contents if isinstance(c, TextReasoningContent))

        assistant_message = OllamaMessage(role="assistant", content=text_content, thinking=reasoning_contents)

        tool_calls = [item for item in message.contents if isinstance(item, FunctionCallContent)]
        if tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "function": {
                        "call_id": tool_call.call_id,
                        "name": tool_call.name,
                        "arguments": tool_call.arguments
                        if isinstance(tool_call.arguments, Mapping)
                        else json.loads(tool_call.arguments or "{}"),
                    }
                }
                for tool_call in tool_calls
            ]
        return [assistant_message]

    def _format_tool_message(self, message: ChatMessage) -> list[OllamaMessage]:
        # Ollama does not support multiple tool results in a single message, so we create a separate
        return [
            OllamaMessage(role="tool", content=str(item.result), tool_name=item.call_id)
            for item in message.contents
            if isinstance(item, FunctionResultContent)
        ]

    def _ollama_response_to_agent_framework_content(self, response: OllamaChatResponse) -> list[Contents]:
        contents: list[Contents] = []
        if response.message.thinking:
            contents.append(TextReasoningContent(text=response.message.thinking))
        if response.message.content:
            contents.append(TextContent(text=response.message.content))
        if response.message.tool_calls:
            tool_calls = self._parse_ollama_tool_calls(response.message.tool_calls)
            contents.extend(tool_calls)
        return contents

    def _ollama_streaming_response_to_agent_framework_response(
        self, response: OllamaChatResponse
    ) -> ChatResponseUpdate:
        contents = self._ollama_response_to_agent_framework_content(response)
        return ChatResponseUpdate(
            contents=contents,
            role=Role.ASSISTANT,
            ai_model_id=response.model,
            created_at=response.created_at,
        )

    def _ollama_response_to_agent_framework_response(self, response: OllamaChatResponse) -> ChatResponse:
        contents = self._ollama_response_to_agent_framework_content(response)

        return ChatResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, contents=contents)],
            model_id=response.model,
            created_at=response.created_at,
            usage_details=UsageDetails(
                input_token_count=response.prompt_eval_count,
                output_token_count=response.eval_count,
            ),
        )

    def _parse_ollama_tool_calls(self, tool_calls: Sequence[OllamaMessage.ToolCall]) -> list[Contents]:
        resp: list[Contents] = []
        for tool in tool_calls:
            fcc = FunctionCallContent(
                call_id=tool.function.name,  # Use name of function as call ID since Ollama doesn't provide a call ID
                name=tool.function.name,
                arguments=tool.function.arguments if isinstance(tool.function.arguments, dict) else "",
                raw_representation=tool.function,
            )
            resp.append(fcc)
        return resp

    def _chat_to_tool_spec(self, tools: list[ToolProtocol | MutableMapping[str, Any]]) -> list[dict[str, Any]]:
        chat_tools: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, ToolProtocol):
                match tool:
                    case AIFunction():
                        chat_tools.append(tool.to_json_schema_spec())
                    case _:
                        raise ServiceInvalidRequestError(
                            "Unsupported tool type '"
                            f"{type(tool).__name__}"
                            "' for Ollama client. Supported tool types: AIFunction."
                        )
            else:
                chat_tools.append(tool if isinstance(tool, dict) else dict(tool))
        return chat_tools
