# Copyright (c) Microsoft. All rights reserved.

import json
import sys
from collections.abc import AsyncIterable, Awaitable, Callable, Mapping, MutableMapping, MutableSequence, Sequence
from datetime import datetime, timezone
from itertools import chain
from typing import Any, Generic, Literal

from openai import AsyncOpenAI, BadRequestError
from openai.lib._parsing._completions import type_to_response_format_param
from openai.types import CompletionUsage
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_message_custom_tool_call import ChatCompletionMessageCustomToolCall
from pydantic import BaseModel, ValidationError

from .._clients import BaseChatClient
from .._logging import get_logger
from .._middleware import use_chat_middleware
from .._tools import FunctionTool, HostedWebSearchTool, ToolProtocol, use_function_invocation
from .._types import (
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FinishReason,
    Role,
    UsageDetails,
    prepare_function_call_results,
)
from ..exceptions import (
    ServiceInitializationError,
    ServiceInvalidRequestError,
    ServiceResponseException,
)
from ..observability import use_instrumentation
from ._exceptions import OpenAIContentFilterException
from ._shared import OpenAIBase, OpenAIConfigMixin, OpenAISettings

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

__all__ = ["OpenAIChatClient", "OpenAIChatOptions"]

logger = get_logger("agent_framework.openai")

TResponseModel = TypeVar("TResponseModel", bound=BaseModel | None, default=None)


# region OpenAI Chat Options TypedDict


class PredictionTextContent(TypedDict, total=False):
    """Prediction text content options for OpenAI Chat completions."""

    type: Literal["text"]
    text: str


class Prediction(TypedDict, total=False):
    """Prediction options for OpenAI Chat completions."""

    type: Literal["content"]
    content: str | list[PredictionTextContent]


class OpenAIChatOptions(ChatOptions[TResponseModel], Generic[TResponseModel], total=False):
    """OpenAI-specific chat options dict.

    Extends ChatOptions with options specific to OpenAI's Chat Completions API.

    Keys:
        model_id: The model to use for the request,
            translates to ``model`` in OpenAI API.
        temperature: Sampling temperature between 0 and 2.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum number of tokens to generate,
            translates to ``max_completion_tokens`` in OpenAI API.
        stop: Stop sequences.
        seed: Random seed for reproducibility.
        frequency_penalty: Frequency penalty between -2.0 and 2.0.
        presence_penalty: Presence penalty between -2.0 and 2.0.
        tools: List of tools (functions) available to the model.
        tool_choice: How the model should use tools.
        allow_multiple_tool_calls: Whether to allow parallel tool calls,
            translates to ``parallel_tool_calls`` in OpenAI API.
        response_format: Structured output schema.
        metadata: Request metadata for tracking.
        user: End-user identifier for abuse monitoring.
        store: Whether to store the conversation.
        instructions: System instructions for the model (prepended as system message).
        # OpenAI-specific options (supported by all models):
        logit_bias: Token bias values (-100 to 100).
        logprobs: Whether to return log probabilities.
        top_logprobs: Number of top log probabilities to return (0-20).
        prediction: Whether to use predicted return tokens.
    """

    # OpenAI-specific generation parameters (supported by all models)
    logit_bias: dict[str | int, float]  # type: ignore[misc]
    logprobs: bool
    top_logprobs: int
    prediction: Prediction


TOpenAIChatOptions = TypeVar("TOpenAIChatOptions", bound=TypedDict, default="OpenAIChatOptions", covariant=True)  # type: ignore[valid-type]

OPTION_TRANSLATIONS: dict[str, str] = {
    "model_id": "model",
    "allow_multiple_tool_calls": "parallel_tool_calls",
    "max_tokens": "max_completion_tokens",
}


# region Base Client
class OpenAIBaseChatClient(OpenAIBase, BaseChatClient[TOpenAIChatOptions], Generic[TOpenAIChatOptions]):
    """OpenAI Chat completion class."""

    @override
    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        client = await self._ensure_client()
        # prepare
        options_dict = self._prepare_options(messages, options)
        try:
            # execute and process
            return self._parse_response_from_openai(
                await client.chat.completions.create(stream=False, **options_dict), options
            )
        except BadRequestError as ex:
            if ex.code == "content_filter":
                raise OpenAIContentFilterException(
                    f"{type(self)} service encountered a content error: {ex}",
                    inner_exception=ex,
                ) from ex
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex
        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex

    @override
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        client = await self._ensure_client()
        # prepare
        options_dict = self._prepare_options(messages, options)
        options_dict["stream_options"] = {"include_usage": True}
        try:
            # execute and process
            async for chunk in await client.chat.completions.create(stream=True, **options_dict):
                if len(chunk.choices) == 0 and chunk.usage is None:
                    continue
                yield self._parse_response_update_from_openai(chunk)
        except BadRequestError as ex:
            if ex.code == "content_filter":
                raise OpenAIContentFilterException(
                    f"{type(self)} service encountered a content error: {ex}",
                    inner_exception=ex,
                ) from ex
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex
        except Exception as ex:
            raise ServiceResponseException(
                f"{type(self)} service failed to complete the prompt: {ex}",
                inner_exception=ex,
            ) from ex

    # region content creation

    def _prepare_tools_for_openai(self, tools: Sequence[ToolProtocol | MutableMapping[str, Any]]) -> dict[str, Any]:
        chat_tools: list[dict[str, Any]] = []
        web_search_options: dict[str, Any] | None = None
        for tool in tools:
            if isinstance(tool, ToolProtocol):
                match tool:
                    case FunctionTool():
                        chat_tools.append(tool.to_json_schema_spec())
                    case HostedWebSearchTool():
                        web_search_options = (
                            {
                                "user_location": {
                                    "approximate": tool.additional_properties.get("user_location", None),
                                    "type": "approximate",
                                }
                            }
                            if tool.additional_properties and "user_location" in tool.additional_properties
                            else {}
                        )
                    case _:
                        logger.debug("Unsupported tool passed (type: %s), ignoring", type(tool))
            else:
                chat_tools.append(tool if isinstance(tool, dict) else dict(tool))
        ret_dict: dict[str, Any] = {}
        if chat_tools:
            ret_dict["tools"] = chat_tools
        if web_search_options is not None:
            ret_dict["web_search_options"] = web_search_options
        return ret_dict

    def _prepare_options(self, messages: MutableSequence[ChatMessage], options: dict[str, Any]) -> dict[str, Any]:
        # Prepend instructions from options if they exist
        from .._types import prepend_instructions_to_messages, validate_tool_mode

        if instructions := options.get("instructions"):
            messages = prepend_instructions_to_messages(list(messages), instructions, role="system")

        # Start with a copy of options
        run_options = {k: v for k, v in options.items() if v is not None and k not in {"instructions", "tools"}}

        # messages
        if messages and "messages" not in run_options:
            run_options["messages"] = self._prepare_messages_for_openai(messages)
        if "messages" not in run_options:
            raise ServiceInvalidRequestError("Messages are required for chat completions")

        # Translation between options keys and Chat Completion API
        for old_key, new_key in OPTION_TRANSLATIONS.items():
            if old_key in run_options and old_key != new_key:
                run_options[new_key] = run_options.pop(old_key)

        # model id
        if not run_options.get("model"):
            if not self.model_id:
                raise ValueError("model_id must be a non-empty string")
            run_options["model"] = self.model_id

        # tools
        tools = options.get("tools")
        if tools is not None:
            run_options.update(self._prepare_tools_for_openai(tools))
        if not run_options.get("tools"):
            run_options.pop("parallel_tool_calls", None)
            run_options.pop("tool_choice", None)
        if tool_choice := run_options.pop("tool_choice", None):
            tool_mode = validate_tool_mode(tool_choice)
            if (mode := tool_mode.get("mode")) == "required" and (
                func_name := tool_mode.get("required_function_name")
            ) is not None:
                run_options["tool_choice"] = {
                    "type": "function",
                    "function": {"name": func_name},
                }
            else:
                run_options["tool_choice"] = mode

        # response format
        if response_format := options.get("response_format"):
            if isinstance(response_format, dict):
                run_options["response_format"] = response_format
            else:
                run_options["response_format"] = type_to_response_format_param(response_format)
        return run_options

    def _parse_response_from_openai(self, response: ChatCompletion, options: dict[str, Any]) -> "ChatResponse":
        """Parse a response from OpenAI into a ChatResponse."""
        response_metadata = self._get_metadata_from_chat_response(response)
        messages: list[ChatMessage] = []
        finish_reason: FinishReason | None = None
        for choice in response.choices:
            response_metadata.update(self._get_metadata_from_chat_choice(choice))
            if choice.finish_reason:
                finish_reason = FinishReason(value=choice.finish_reason)
            contents: list[Content] = []
            if text_content := self._parse_text_from_openai(choice):
                contents.append(text_content)
            if parsed_tool_calls := [tool for tool in self._parse_tool_calls_from_openai(choice)]:
                contents.extend(parsed_tool_calls)
            if reasoning_details := getattr(choice.message, "reasoning_details", None):
                contents.append(Content.from_text_reasoning(protected_data=json.dumps(reasoning_details)))
            messages.append(ChatMessage(role="assistant", contents=contents))
        return ChatResponse(
            response_id=response.id,
            created_at=datetime.fromtimestamp(response.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            usage_details=self._parse_usage_from_openai(response.usage) if response.usage else None,
            messages=messages,
            model_id=response.model,
            additional_properties=response_metadata,
            finish_reason=finish_reason,
            response_format=options.get("response_format"),
        )

    def _parse_response_update_from_openai(
        self,
        chunk: ChatCompletionChunk,
    ) -> ChatResponseUpdate:
        """Parse a streaming response update from OpenAI."""
        chunk_metadata = self._get_metadata_from_streaming_chat_response(chunk)
        if chunk.usage:
            return ChatResponseUpdate(
                role=Role.ASSISTANT,
                contents=[
                    Content.from_usage(
                        usage_details=self._parse_usage_from_openai(chunk.usage), raw_representation=chunk
                    )
                ],
                model_id=chunk.model,
                additional_properties=chunk_metadata,
                response_id=chunk.id,
                message_id=chunk.id,
            )
        contents: list[Content] = []
        finish_reason: FinishReason | None = None
        for choice in chunk.choices:
            chunk_metadata.update(self._get_metadata_from_chat_choice(choice))
            contents.extend(self._parse_tool_calls_from_openai(choice))
            if choice.finish_reason:
                finish_reason = FinishReason(value=choice.finish_reason)

            if text_content := self._parse_text_from_openai(choice):
                contents.append(text_content)
            if reasoning_details := getattr(choice.delta, "reasoning_details", None):
                contents.append(Content.from_text_reasoning(protected_data=json.dumps(reasoning_details)))
        return ChatResponseUpdate(
            created_at=datetime.fromtimestamp(chunk.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            contents=contents,
            role=Role.ASSISTANT,
            model_id=chunk.model,
            additional_properties=chunk_metadata,
            finish_reason=finish_reason,
            raw_representation=chunk,
            response_id=chunk.id,
            message_id=chunk.id,
        )

    def _parse_usage_from_openai(self, usage: CompletionUsage) -> UsageDetails:
        details = UsageDetails(
            input_token_count=usage.prompt_tokens,
            output_token_count=usage.completion_tokens,
            total_token_count=usage.total_tokens,
        )
        if usage.completion_tokens_details:
            if tokens := usage.completion_tokens_details.accepted_prediction_tokens:
                details["completion/accepted_prediction_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
            if tokens := usage.completion_tokens_details.audio_tokens:
                details["completion/audio_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
            if tokens := usage.completion_tokens_details.reasoning_tokens:
                details["completion/reasoning_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
            if tokens := usage.completion_tokens_details.rejected_prediction_tokens:
                details["completion/rejected_prediction_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
        if usage.prompt_tokens_details:
            if tokens := usage.prompt_tokens_details.audio_tokens:
                details["prompt/audio_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
            if tokens := usage.prompt_tokens_details.cached_tokens:
                details["prompt/cached_tokens"] = tokens  # type: ignore[typeddict-unknown-key]
        return details

    def _parse_text_from_openai(self, choice: Choice | ChunkChoice) -> Content | None:
        """Parse the choice into a Content object with type='text'."""
        message = choice.message if isinstance(choice, Choice) else choice.delta
        if message.content:
            return Content.from_text(text=message.content, raw_representation=choice)
        if hasattr(message, "refusal") and message.refusal:
            return Content.from_text(text=message.refusal, raw_representation=choice)
        return None

    def _get_metadata_from_chat_response(self, response: ChatCompletion) -> dict[str, Any]:
        """Get metadata from a chat response."""
        return {
            "system_fingerprint": response.system_fingerprint,
        }

    def _get_metadata_from_streaming_chat_response(self, response: ChatCompletionChunk) -> dict[str, Any]:
        """Get metadata from a streaming chat response."""
        return {
            "system_fingerprint": response.system_fingerprint,
        }

    def _get_metadata_from_chat_choice(self, choice: Choice | ChunkChoice) -> dict[str, Any]:
        """Get metadata from a chat choice."""
        return {
            "logprobs": getattr(choice, "logprobs", None),
        }

    def _parse_tool_calls_from_openai(self, choice: Choice | ChunkChoice) -> list[Content]:
        """Parse tool calls from an OpenAI response choice."""
        resp: list[Content] = []
        content = choice.message if isinstance(choice, Choice) else choice.delta
        if content and content.tool_calls:
            for tool in content.tool_calls:
                if not isinstance(tool, ChatCompletionMessageCustomToolCall) and tool.function:
                    # ignoring tool.custom
                    fcc = Content.from_function_call(
                        call_id=tool.id if tool.id else "",
                        name=tool.function.name if tool.function.name else "",
                        arguments=tool.function.arguments if tool.function.arguments else "",
                        raw_representation=tool.function,
                    )
                    resp.append(fcc)

        # When you enable asynchronous content filtering in Azure OpenAI, you may receive empty deltas
        return resp

    def _prepare_messages_for_openai(
        self,
        chat_messages: Sequence[ChatMessage],
        role_key: str = "role",
        content_key: str = "content",
    ) -> list[dict[str, Any]]:
        """Prepare the chat history for an OpenAI request.

        Allowing customization of the key names for role/author, and optionally overriding the role.

        Role.TOOL messages need to be formatted different than system/user/assistant messages:
            They require a "tool_call_id" and (function) "name" key, and the "metadata" key should
            be removed. The "encoding" key should also be removed.

        Override this method to customize the formatting of the chat history for a request.

        Args:
            chat_messages: The chat history to prepare.
            role_key: The key name for the role/author.
            content_key: The key name for the content/message.

        Returns:
            prepared_chat_history (Any): The prepared chat history for a request.
        """
        list_of_list = [self._prepare_message_for_openai(message) for message in chat_messages]
        # Flatten the list of lists into a single list
        return list(chain.from_iterable(list_of_list))

    # region Parsers

    def _prepare_message_for_openai(self, message: ChatMessage) -> list[dict[str, Any]]:
        """Prepare a chat message for OpenAI."""
        all_messages: list[dict[str, Any]] = []
        for content in message.contents:
            # Skip approval content - it's internal framework state, not for the LLM
            if content.type in ("function_approval_request", "function_approval_response"):
                continue

            args: dict[str, Any] = {
                "role": message.role.value if isinstance(message.role, Role) else message.role,
            }
            if message.author_name and message.role != Role.TOOL:
                args["name"] = message.author_name
            if "reasoning_details" in message.additional_properties and (
                details := message.additional_properties["reasoning_details"]
            ):
                args["reasoning_details"] = details
            match content.type:
                case "function_call":
                    if all_messages and "tool_calls" in all_messages[-1]:
                        # If the last message already has tool calls, append to it
                        all_messages[-1]["tool_calls"].append(self._prepare_content_for_openai(content))
                    else:
                        args["tool_calls"] = [self._prepare_content_for_openai(content)]  # type: ignore
                case "function_result":
                    args["tool_call_id"] = content.call_id
                    # Always include content for tool results - API requires it even if empty
                    # Functions returning None should still have a tool result message
                    args["content"] = (
                        prepare_function_call_results(content.result) if content.result is not None else ""
                    )
                case "text_reasoning" if (protected_data := content.protected_data) is not None:
                    all_messages[-1]["reasoning_details"] = json.loads(protected_data)
                case _:
                    if "content" not in args:
                        args["content"] = []
                    # this is a list to allow multi-modal content
                    args["content"].append(self._prepare_content_for_openai(content))  # type: ignore
            if "content" in args or "tool_calls" in args:
                all_messages.append(args)
        return all_messages

    def _prepare_content_for_openai(self, content: Content) -> dict[str, Any]:
        """Prepare content for OpenAI."""
        match content.type:
            case "function_call":
                args = json.dumps(content.arguments) if isinstance(content.arguments, Mapping) else content.arguments
                return {
                    "id": content.call_id,
                    "type": "function",
                    "function": {"name": content.name, "arguments": args},
                }
            case "function_result":
                return {
                    "tool_call_id": content.call_id,
                    "content": content.result,
                }
            case "data" | "uri" if content.has_top_level_media_type("image"):
                return {
                    "type": "image_url",
                    "image_url": {"url": content.uri},
                }
            case "data" | "uri" if content.has_top_level_media_type("audio"):
                if content.media_type and "wav" in content.media_type:
                    audio_format = "wav"
                elif content.media_type and "mp3" in content.media_type:
                    audio_format = "mp3"
                else:
                    # Fallback to default to_dict for unsupported audio formats
                    return content.to_dict(exclude_none=True)

                # Extract base64 data from data URI
                audio_data = content.uri
                if audio_data.startswith("data:"):  # type: ignore[union-attr]
                    # Extract just the base64 part after "data:audio/format;base64,"
                    audio_data = audio_data.split(",", 1)[-1]  # type: ignore[union-attr]

                return {
                    "type": "input_audio",
                    "input_audio": {
                        "data": audio_data,
                        "format": audio_format,
                    },
                }
            case "data" | "uri" if content.has_top_level_media_type("application") and content.uri.startswith("data:"):  # type: ignore[union-attr]
                # All application/* media types should be treated as files for OpenAI
                filename = getattr(content, "filename", None) or (
                    content.additional_properties.get("filename")
                    if hasattr(content, "additional_properties") and content.additional_properties
                    else None
                )
                file_obj = {"file_data": content.uri}
                if filename:
                    file_obj["filename"] = filename
                return {
                    "type": "file",
                    "file": file_obj,
                }
            case _:
                # Default fallback for all other content types
                return content.to_dict(exclude_none=True)

    @override
    def service_url(self) -> str:
        """Get the URL of the service.

        Override this in the subclass to return the proper URL.
        If the service does not have a URL, return None.
        """
        return str(self.client.base_url) if self.client else "Unknown"


# region Public client


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class OpenAIChatClient(OpenAIConfigMixin, OpenAIBaseChatClient[TOpenAIChatOptions], Generic[TOpenAIChatOptions]):
    """OpenAI Chat completion class."""

    def __init__(
        self,
        *,
        model_id: str | None = None,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        base_url: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an OpenAI Chat completion client.

        Keyword Args:
            model_id: OpenAI model name, see https://platform.openai.com/docs/models.
                Can also be set via environment variable OPENAI_CHAT_MODEL_ID.
            api_key: The API key to use. If provided will override the env vars or .env file value.
                Can also be set via environment variable OPENAI_API_KEY.
            org_id: The org ID to use. If provided will override the env vars or .env file value.
                Can also be set via environment variable OPENAI_ORG_ID.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests.
            async_client: An existing client to use.
            instruction_role: The role to use for 'instruction' messages, for example,
                "system" or "developer". If not provided, the default is "system".
            base_url: The base URL to use. If provided will override
                the standard value for an OpenAI connector, the env vars or .env file value.
                Can also be set via environment variable OPENAI_BASE_URL.
            env_file_path: Use the environment settings file as a fallback
                to environment variables.
            env_file_encoding: The encoding of the environment settings file.

        Examples:
            .. code-block:: python

                from agent_framework.openai import OpenAIChatClient

                # Using environment variables
                # Set OPENAI_API_KEY=sk-...
                # Set OPENAI_CHAT_MODEL_ID=<model name>
                client = OpenAIChatClient()

                # Or passing parameters directly
                client = OpenAIChatClient(model_id="<model name>", api_key="sk-...")

                # Or loading from a .env file
                client = OpenAIChatClient(env_file_path="path/to/.env")

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework.openai import OpenAIChatOptions


                class MyOptions(OpenAIChatOptions, total=False):
                    my_custom_option: str


                client: OpenAIChatClient[MyOptions] = OpenAIChatClient(model_id="<model name>")
                response = await client.get_response("Hello", options={"my_custom_option": "value"})
        """
        try:
            openai_settings = OpenAISettings(
                api_key=api_key,  # type: ignore[reportArgumentType]
                base_url=base_url,
                org_id=org_id,
                chat_model_id=model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create OpenAI settings.", ex) from ex

        if not async_client and not openai_settings.api_key:
            raise ServiceInitializationError(
                "OpenAI API key is required. Set via 'api_key' parameter or 'OPENAI_API_KEY' environment variable."
            )
        if not openai_settings.chat_model_id:
            raise ServiceInitializationError(
                "OpenAI model ID is required. "
                "Set via 'model_id' parameter or 'OPENAI_CHAT_MODEL_ID' environment variable."
            )

        super().__init__(
            model_id=openai_settings.chat_model_id,
            api_key=self._get_api_key(openai_settings.api_key),
            base_url=openai_settings.base_url if openai_settings.base_url else None,
            org_id=openai_settings.org_id,
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
        )
