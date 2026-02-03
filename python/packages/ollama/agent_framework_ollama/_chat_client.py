# Copyright (c) Microsoft. All rights reserved.

import json
import sys
from collections.abc import (
    AsyncIterable,
    Callable,
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
)
from itertools import chain
from typing import Any, ClassVar, Generic

from agent_framework import (
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionTool,
    Role,
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
from pydantic import BaseModel, ValidationError

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

__all__ = ["OllamaChatClient", "OllamaChatOptions"]

TResponseModel = TypeVar("TResponseModel", bound=BaseModel | None, default=None)


# region Ollama Chat Options TypedDict


class OllamaChatOptions(ChatOptions[TResponseModel], Generic[TResponseModel], total=False):
    """Ollama-specific chat options dict.

    Extends base ChatOptions with Ollama-specific parameters.
    Ollama passes model parameters through the `options` field.

    See: https://github.com/ollama/ollama/blob/main/docs/api.md

    Keys:
        # Inherited from ChatOptions (mapped to Ollama options):
        model_id: The model name, translates to ``model`` in Ollama API.
        temperature: Sampling temperature, translates to ``options.temperature``.
        top_p: Nucleus sampling, translates to ``options.top_p``.
        max_tokens: Maximum tokens to generate, translates to ``options.num_predict``.
        stop: Stop sequences, translates to ``options.stop``.
        seed: Random seed for reproducibility, translates to ``options.seed``.
        frequency_penalty: Frequency penalty, translates to ``options.frequency_penalty``.
        presence_penalty: Presence penalty, translates to ``options.presence_penalty``.
        tools: List of function tools.
        response_format: Output format, translates to ``format``.
            Use 'json' for JSON mode or a JSON schema dict for structured output.

        # Options not supported in Ollama:
        tool_choice: Ollama only supports auto tool choice.
        allow_multiple_tool_calls: Not configurable.
        user: Not supported.
        store: Not supported.
        logit_bias: Not supported.
        metadata: Not supported.

        # Ollama model-level options (placed in `options` dict):
        # See: https://github.com/ollama/ollama/blob/main/docs/modelfile.mdx#valid-parameters-and-values
        num_predict: Maximum number of tokens to predict (alternative to max_tokens).
        top_k: Top-k sampling: limits tokens to k most likely. Higher = more diverse.
        min_p: Minimum probability threshold for token selection.
        typical_p: Locally typical sampling parameter (0.0-1.0).
        repeat_penalty: Penalty for repeating tokens. Higher = less repetition.
        repeat_last_n: Number of tokens to consider for repeat penalty.
        penalize_newline: Whether to penalize newline characters.
        num_ctx: Context window size (number of tokens).
        num_batch: Batch size for prompt processing.
        num_keep: Number of tokens to keep from initial prompt.
        num_gpu: Number of layers to offload to GPU.
        main_gpu: Main GPU for computation.
        use_mmap: Whether to use memory-mapped files.
        num_thread: Number of threads for CPU computation.
        numa: Enable NUMA optimization.

        # Ollama-specific top-level options:
        keep_alive: How long to keep model loaded (default: '5m').
        think: Whether thinking models should think before responding.

    Examples:
        .. code-block:: python

            from agent_framework_ollama import OllamaChatOptions

            # Basic usage - standard options automatically mapped
            options: OllamaChatOptions = {
                "temperature": 0.7,
                "max_tokens": 1000,
                "seed": 42,
            }

            # With Ollama-specific model options
            options: OllamaChatOptions = {
                "top_k": 40,
                "num_ctx": 4096,
                "keep_alive": "10m",
            }

            # With JSON output format
            options: OllamaChatOptions = {
                "response_format": "json",
            }

            # With structured output (JSON schema)
            options: OllamaChatOptions = {
                "response_format": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                },
            }
    """

    # Ollama model-level options (will be placed in `options` dict)
    num_predict: int
    """Maximum number of tokens to predict (equivalent to max_tokens)."""

    top_k: int
    """Top-k sampling: limits tokens to k most likely. Higher = more diverse."""

    min_p: float
    """Minimum probability threshold for token selection."""

    typical_p: float
    """Locally typical sampling parameter (0.0-1.0)."""

    repeat_penalty: float
    """Penalty for repeating tokens. Higher = less repetition."""

    repeat_last_n: int
    """Number of tokens to consider for repeat penalty."""

    penalize_newline: bool
    """Whether to penalize newline characters."""

    num_ctx: int
    """Context window size (number of tokens)."""

    num_batch: int
    """Batch size for prompt processing."""

    num_keep: int
    """Number of tokens to keep from initial prompt."""

    num_gpu: int
    """Number of layers to offload to GPU."""

    main_gpu: int
    """Main GPU for computation."""

    use_mmap: bool
    """Whether to use memory-mapped files."""

    num_thread: int
    """Number of threads for CPU computation."""

    numa: bool
    """Enable NUMA optimization."""

    # Ollama-specific top-level options
    keep_alive: str | int
    """How long to keep the model loaded in memory after request.
    Can be duration string (e.g., '5m', '1h') or seconds as int.
    Set to 0 to unload immediately after request."""

    think: bool
    """For thinking models: whether the model should think before responding."""

    # ChatOptions fields not supported in Ollama
    tool_choice: None  # type: ignore[misc]
    """Not supported. Ollama only supports auto tool choice."""

    allow_multiple_tool_calls: None  # type: ignore[misc]
    """Not supported. Not configurable in Ollama."""

    user: None  # type: ignore[misc]
    """Not supported in Ollama."""

    store: None  # type: ignore[misc]
    """Not supported in Ollama."""

    logit_bias: None  # type: ignore[misc]
    """Not supported in Ollama."""

    metadata: None  # type: ignore[misc]
    """Not supported in Ollama."""


OLLAMA_OPTION_TRANSLATIONS: dict[str, str] = {
    "model_id": "model",
    "response_format": "format",
}
"""Maps ChatOptions keys to Ollama API parameter names."""

# Keys that should be placed in the nested `options` dict for the Ollama API
OLLAMA_MODEL_OPTIONS: set[str] = {
    # From ChatOptions (mapped to options.*)
    "temperature",
    "top_p",
    "max_tokens",  # -> num_predict
    "stop",
    "seed",
    "frequency_penalty",
    "presence_penalty",
    # Ollama-specific model options
    "num_predict",
    "top_k",
    "min_p",
    "typical_p",
    "repeat_penalty",
    "repeat_last_n",
    "penalize_newline",
    "num_ctx",
    "num_batch",
    "num_keep",
    "num_gpu",
    "main_gpu",
    "use_mmap",
    "num_thread",
    "numa",
}

# Translations for options that go into the nested `options` dict
OLLAMA_MODEL_OPTION_TRANSLATIONS: dict[str, str] = {
    "max_tokens": "num_predict",
}
"""Maps ChatOptions keys to Ollama model option parameter names."""

TOllamaChatOptions = TypeVar("TOllamaChatOptions", bound=TypedDict, default="OllamaChatOptions", covariant=True)  # type: ignore[valid-type]


# endregion


class OllamaSettings(AFBaseSettings):
    """Ollama settings."""

    env_prefix: ClassVar[str] = "OLLAMA_"

    host: str | None = None
    model_id: str | None = None


logger = get_logger("agent_framework.ollama")


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class OllamaChatClient(BaseChatClient[TOllamaChatOptions], Generic[TOllamaChatOptions]):
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

    @override
    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        # prepare
        options_dict = self._prepare_options(messages, options)

        try:
            # execute
            response: OllamaChatResponse = await self.client.chat(  # type: ignore[misc]
                stream=False,
                **options_dict,
                **kwargs,
            )
        except Exception as ex:
            raise ServiceResponseException(f"Ollama chat request failed : {ex}", ex) from ex

        # process
        return self._parse_response_from_ollama(response)

    @override
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        # prepare
        options_dict = self._prepare_options(messages, options)

        try:
            # execute
            response_object: AsyncIterable[OllamaChatResponse] = await self.client.chat(  # type: ignore[misc]
                stream=True,
                **options_dict,
                **kwargs,
            )
        except Exception as ex:
            raise ServiceResponseException(f"Ollama streaming chat request failed : {ex}", ex) from ex

        # process
        async for part in response_object:
            yield self._parse_streaming_response_from_ollama(part)

    def _prepare_options(self, messages: MutableSequence[ChatMessage], options: dict[str, Any]) -> dict[str, Any]:
        # Handle instructions by prepending to messages as system message
        instructions = options.get("instructions")
        if instructions:
            from agent_framework._types import prepend_instructions_to_messages

            messages = prepend_instructions_to_messages(list(messages), instructions, role="system")

        # Keys to exclude from processing
        exclude_keys = {"instructions", "tool_choice"}

        # Build run_options and model_options separately
        run_options: dict[str, Any] = {}
        model_options: dict[str, Any] = {}

        for key, value in options.items():
            if key in exclude_keys or value is None:
                continue

            if key in OLLAMA_MODEL_OPTIONS:
                # Apply model option translations (e.g., max_tokens -> num_predict)
                translated_key = OLLAMA_MODEL_OPTION_TRANSLATIONS.get(key, key)
                model_options[translated_key] = value
            else:
                # Apply top-level translations (e.g., model_id -> model)
                translated_key = OLLAMA_OPTION_TRANSLATIONS.get(key, key)
                run_options[translated_key] = value

        # Add model options to run_options if any
        if model_options:
            run_options["options"] = model_options

        # messages
        if messages and "messages" not in run_options:
            run_options["messages"] = self._prepare_messages_for_ollama(messages)
        if "messages" not in run_options:
            raise ServiceInvalidRequestError("Messages are required for chat completions")

        # model id
        if not run_options.get("model"):
            if not self.model_id:
                raise ValueError("model_id must be a non-empty string")
            run_options["model"] = self.model_id

        # tools
        tools = options.get("tools")
        if tools and (prepared_tools := self._prepare_tools_for_ollama(tools)):
            run_options["tools"] = prepared_tools

        return run_options

    def _prepare_messages_for_ollama(self, messages: MutableSequence[ChatMessage]) -> list[OllamaMessage]:
        ollama_messages = [self._prepare_message_for_ollama(msg) for msg in messages]
        # Flatten the list of lists into a single list
        return list(chain.from_iterable(ollama_messages))

    def _prepare_message_for_ollama(self, message: ChatMessage) -> list[OllamaMessage]:
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
        if not any(c.type in {"text", "data"} for c in message.contents) and not message.text:
            raise ServiceInvalidRequestError(
                "Ollama connector currently only supports user messages with TextContent or DataContent."
            )

        if not any(c.type == "data" for c in message.contents):
            return [OllamaMessage(role="user", content=message.text)]

        user_message = OllamaMessage(role="user", content=message.text)
        data_contents = [c for c in message.contents if c.type == "data"]
        if data_contents:
            if not any(c.has_top_level_media_type("image") for c in data_contents):
                raise ServiceInvalidRequestError("Only image data content is supported for user messages in Ollama.")
            # Ollama expects base64 strings without prefix
            user_message["images"] = [c.uri.split(",")[1] for c in data_contents if c.uri]
        return [user_message]

    def _format_assistant_message(self, message: ChatMessage) -> list[OllamaMessage]:
        text_content = message.text
        # Ollama shouldn't have encrypted reasoning, so we just process text.
        reasoning_contents = "".join((c.text or "") for c in message.contents if c.type == "text_reasoning")

        assistant_message = OllamaMessage(role="assistant", content=text_content, thinking=reasoning_contents)

        tool_calls = [item for item in message.contents if item.type == "function_call"]
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
            if item.type == "function_result"
        ]

    def _parse_contents_from_ollama(self, response: OllamaChatResponse) -> list[Content]:
        contents: list[Content] = []
        if response.message.thinking:
            contents.append(Content.from_text_reasoning(text=response.message.thinking))
        if response.message.content:
            contents.append(Content.from_text(text=response.message.content))
        if response.message.tool_calls:
            tool_calls = self._parse_tool_calls_from_ollama(response.message.tool_calls)
            contents.extend(tool_calls)
        return contents

    def _parse_streaming_response_from_ollama(self, response: OllamaChatResponse) -> ChatResponseUpdate:
        contents = self._parse_contents_from_ollama(response)
        return ChatResponseUpdate(
            contents=contents,
            role=Role.ASSISTANT,
            ai_model_id=response.model,
            created_at=response.created_at,
        )

    def _parse_response_from_ollama(self, response: OllamaChatResponse) -> ChatResponse:
        contents = self._parse_contents_from_ollama(response)

        return ChatResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, contents=contents)],
            model_id=response.model,
            created_at=response.created_at,
            usage_details=UsageDetails(
                input_token_count=response.prompt_eval_count,
                output_token_count=response.eval_count,
            ),
        )

    def _parse_tool_calls_from_ollama(self, tool_calls: Sequence[OllamaMessage.ToolCall]) -> list[Content]:
        resp: list[Content] = []
        for tool in tool_calls:
            fcc = Content.from_function_call(
                call_id=tool.function.name,  # Use name of function as call ID since Ollama doesn't provide a call ID
                name=tool.function.name,
                arguments=tool.function.arguments if isinstance(tool.function.arguments, dict) else "",
                raw_representation=tool.function,
            )
            resp.append(fcc)
        return resp

    def _prepare_tools_for_ollama(self, tools: list[ToolProtocol | MutableMapping[str, Any]]) -> list[dict[str, Any]]:
        chat_tools: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, ToolProtocol):
                match tool:
                    case FunctionTool():
                        chat_tools.append(tool.to_json_schema_spec())
                    case _:
                        raise ServiceInvalidRequestError(
                            "Unsupported tool type '"
                            f"{type(tool).__name__}"
                            "' for Ollama client. Supported tool types: FunctionTool."
                        )
            else:
                chat_tools.append(tool if isinstance(tool, dict) else dict(tool))
        return chat_tools
