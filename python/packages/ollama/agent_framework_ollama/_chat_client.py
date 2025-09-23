# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import AsyncIterable, MutableMapping, MutableSequence, Sequence
from itertools import chain
from typing import Any, ClassVar, TypeVar

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
    ToolProtocol,
    get_logger,
    use_function_invocation,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError, ServiceInvalidRequestError
from agent_framework.telemetry import use_telemetry
from ollama import AsyncClient

# Rename imported types to avoid naming conflicts with Agent Framework types
from ollama._types import ChatResponse as OllamaChatResponse
from ollama._types import Image as OllamaImage
from ollama._types import Message as OllamaMessage


class OllamaSettings(AFBaseSettings):
    """Ollama settings."""

    env_prefix: ClassVar[str] = "OLLAMA_"

    host: str | None = None
    chat_model_id: str


logger = get_logger("agent_framework.ollama")
TOllamaChatClient = TypeVar("TOllamaChatClient", bound="OllamaChatClient")


@use_function_invocation
@use_telemetry
class OllamaChatClient(BaseChatClient):
    """Ollama Chat completion class."""

    client: AsyncClient
    chat_model_id: str

    def __init__(
        self,
        host: str | None = None,
        client: AsyncClient | None = None,
        chat_model_id: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Ollama Chat client.

        Args:
            host: The Ollama server host URL. Can be set via the OLLAMA_HOST env variable.
            client: An optional Ollama Client instance. If not provided, a new instance will be created.
            chat_model_id: The Ollama chat model ID to use. Can be set via the OLLAMA_CHAT_MODEL_ID env variable.
            env_file_path: An optional path to a dotenv (.env) file to load environment variables from.
            env_file_encoding: The encoding to use when reading the dotenv (.env) file. Defaults to 'utf-8'.
        """
        ollama_settings = OllamaSettings(
            host=host, chat_model_id=chat_model_id, env_file_encoding=env_file_encoding, env_file_path=env_file_path
        )

        if ollama_settings.chat_model_id is None:
            raise ServiceInitializationError(
                "Ollama chat model ID must be provided via chat_model_id or OLLAMA_CHAT_MODEL_ID environment variable."
            )

        client = client or AsyncClient(host=ollama_settings.host)

        super().__init__(
            client=client,  # type: ignore[reportCallIssue]
            chat_model_id=ollama_settings.chat_model_id,  # type: ignore[reportCallIssue]
        )

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        return await ChatResponse.from_chat_response_generator(
            updates=self._inner_get_streaming_response(messages=messages, chat_options=chat_options, **kwargs)
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        options_dict = self._prepare_options(messages, chat_options)

        response_object: AsyncIterable[OllamaChatResponse] = await self.client.chat(  # type: ignore[misc]
            model=self.chat_model_id,
            stream=True,
            **options_dict,
            **kwargs,
        )

        async for part in response_object:
            yield self._ollama_to_agent_framework_message(part)

    def _prepare_options(self, messages: MutableSequence[ChatMessage], chat_options: ChatOptions) -> dict[str, Any]:
        # Preprocess web search tool if it exists
        options_dict = chat_options.to_provider_settings()
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

        return options_dict

    def _prepare_chat_history_for_request(self, messages: MutableSequence[ChatMessage]) -> list[OllamaMessage]:
        list_of_list = [self._agent_framework_to_ollama_messages(msg) for msg in messages]
        # Flatten the list of lists into a single list
        return list(chain.from_iterable(list_of_list))

    def _agent_framework_to_ollama_messages(self, message: ChatMessage) -> list[OllamaMessage]:
        return [self._agent_framework_content_to_ollama_message(content, message.role) for content in message.contents]

    def _agent_framework_content_to_ollama_message(self, content: Contents, role: Role) -> OllamaMessage:
        match content:
            case TextContent():
                return OllamaMessage(role=role.value, content=content.text)
            case FunctionCallContent():
                return OllamaMessage(
                    role=role.value,
                    tool_calls=[
                        OllamaMessage.ToolCall(
                            function=OllamaMessage.ToolCall.Function(
                                name=content.name,
                                arguments=content.arguments
                                if isinstance(content.arguments, dict)
                                else json.loads(content.arguments or "{}"),
                            )
                        )
                    ],
                )
            case FunctionResultContent():
                return OllamaMessage(
                    role=str(Role.TOOL),
                    content=content.result,
                )
            case DataContent():
                if not content.has_top_level_media_type("image"):
                    raise ServiceInvalidRequestError("Only DataContent with image media type is supported.")
                return OllamaMessage(
                    role=role.value,
                    images=[OllamaImage(value=content.uri)],
                )
            case _:
                raise ServiceInvalidRequestError(f"Unsupported content type: {type(content)} for Ollama client.")

    def _ollama_to_agent_framework_message(self, response: OllamaChatResponse) -> ChatResponseUpdate:
        contents: list[Contents] = []
        if response.message.content:
            contents.append(TextContent(text=response.message.content))
        if response.message.tool_calls:
            tool_calls = self._parse_ollama_tool_calls(response.message.tool_calls)
            contents.extend(tool_calls)
        return ChatResponseUpdate(
            contents=contents,
            role=Role.ASSISTANT,
            ai_model_id=self.chat_model_id,
        )

    def _parse_ollama_tool_calls(self, tool_calls: Sequence[OllamaMessage.ToolCall]) -> list[Contents]:
        resp: list[Contents] = []
        for tool in tool_calls:
            fcc = FunctionCallContent(
                call_id="",  # Ollama does not provide a call ID
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

    @classmethod
    def from_dict(cls: type[TOllamaChatClient], settings: dict[str, Any]) -> TOllamaChatClient:
        """Initialize an Ollama service from a dictionary of settings.

        Args:
            settings: A dictionary that may contain:
                - ``host``
                - ``chat_model_id``
            Unknown keys are ignored.
        """
        return cls(
            chat_model_id=settings.get("chat_model_id"),
            host=settings.get("host"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the configuration to a dictionary."""
        return {
            "host": str(self.client._client.base_url),
            "chat_model_id": self.chat_model_id,
        }
