# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import base64
import json
import logging
import sys
import uuid
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, ClassVar, Generic

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    BaseChatClient,
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FinishReasonLiteral,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    FunctionTool,
    Message,
    ResponseStream,
    UsageDetails,
)
from agent_framework._settings import SecretString, load_settings
from agent_framework._types import _get_data_bytes_as_str  # type: ignore
from agent_framework.observability import ChatTelemetryLayer
from google import genai
from google.genai import types

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover
if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover


__all__ = [
    "GoogleAIChatClient",
    "GoogleAIChatOptions",
    "GoogleAISettings",
]

logger = logging.getLogger("agent_framework.google")


# region Role and Finish Reason Maps


# Role mapping from Agent Framework to Google AI
# Note: SYSTEM messages are extracted to config.system_instruction and skipped in message conversion
ROLE_MAP: dict[str, str] = {
    "user": "user",
    "assistant": "model",
    "system": "user",  # Fallback only - system messages are normally extracted to system_instruction
    "tool": "function",
}

# Finish reason mapping from Google AI to Agent Framework
FINISH_REASON_MAP: dict[str, FinishReasonLiteral] = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "LANGUAGE": "stop",
    "OTHER": "stop",
    "BLOCKLIST": "content_filter",
    "PROHIBITED_CONTENT": "content_filter",
    "SPII": "content_filter",
    "MALFORMED_FUNCTION_CALL": "stop",
    "IMAGE_SAFETY": "content_filter",
    "IMAGE_PROHIBITED_CONTENT": "content_filter",
    "IMAGE_OTHER": "stop",
    "NO_IMAGE": "stop",
    "IMAGE_RECITATION": "content_filter",
    "UNEXPECTED_TOOL_CALL": "stop",
    "TOO_MANY_TOOL_CALLS": "stop",
}


# region Settings and Options


class GoogleAISettings(TypedDict, total=False):
    """Google AI settings for Gemini API access.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'GOOGLE_AI_'.

    Keys:
        api_key: The Google AI API key.
        chat_model_id: The Google AI chat model ID (e.g., gemini-2.5-flash).
    """

    api_key: SecretString | None
    chat_model_id: str | None


class GoogleAIChatOptions(ChatOptions, total=False):
    """Google AI-specific chat options.

    Extends ChatOptions with options specific to Google's Gemini API.
    Options that Google doesn't support are typed as None to indicate they're unavailable.

    Keys:
        model_id: The model to use for the request.
        temperature: Sampling temperature between 0 and 2.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum number of output tokens,
            translates to ``max_output_tokens`` in Google AI API.
        stop: Stop sequences,
            translates to ``stop_sequences`` in Google AI API.
        tools: List of tools (functions) available to the model.
        tool_choice: How the model should use tools.
        top_k: Number of top tokens to consider for sampling.
        candidate_count: Number of response candidates to generate.
        presence_penalty: Presence penalty for the model.
        frequency_penalty: Frequency penalty for the model.
        instructions: System instructions for the model,
            translates to ``system_instruction`` in Google AI API.
    """

    # Google-specific generation parameters
    top_k: int
    candidate_count: int

    # Unsupported base options (override with None to indicate not supported)
    logit_bias: None  # type: ignore[misc]
    seed: None  # type: ignore[misc]
    store: None  # type: ignore[misc]
    conversation_id: None  # type: ignore[misc]


GoogleOptionsT = TypeVar(
    "GoogleOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="GoogleAIChatOptions",
    covariant=True,
)


# region GoogleAIChatClient


class GoogleAIChatClient(
    ChatMiddlewareLayer[GoogleOptionsT],
    FunctionInvocationLayer[GoogleOptionsT],
    ChatTelemetryLayer[GoogleOptionsT],
    BaseChatClient[GoogleOptionsT],
    Generic[GoogleOptionsT],
):
    """Google AI chat client for Gemini models with middleware, telemetry, and function invocation support.

    This client implements the BaseChatClient interface to provide access to
    Google's Gemini models through the Google AI API (Gemini API).

    Examples:
        .. code-block:: python

            from agent_framework_google import GoogleAIChatClient

            # Using environment variables
            # Set GOOGLE_AI_API_KEY=your_api_key
            # Set GOOGLE_AI_CHAT_MODEL_ID=gemini-2.5-flash

            client = GoogleAIChatClient()

            # Or pass parameters directly
            client = GoogleAIChatClient(api_key="your_api_key", model_id="gemini-2.5-flash")

            # Using custom ChatOptions with type safety:
            from typing import TypedDict
            from agent_framework_google import GoogleAIChatOptions


            class MyOptions(GoogleAIChatOptions, total=False):
                my_custom_option: str


            client: GoogleAIChatClient[MyOptions] = GoogleAIChatClient(model_id="gemini-2.5-flash")
            response = await client.get_response("Hello", options={"my_custom_option": "value"})
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "gcp.gemini"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        google_client: genai.Client | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a Google AI chat client.

        Keyword Args:
            api_key: The Google AI API key to use for authentication.
            model_id: The model ID to use for chat completions (e.g., "gemini-2.5-flash").
            google_client: An existing Google GenAI client to use. If not provided, one will be created.
            middleware: Optional middleware to apply to the client.
            function_invocation_configuration: Optional function invocation configuration override.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
            kwargs: Additional keyword arguments passed to the parent class.

        Examples:
            .. code-block:: python

                from agent_framework_google import GoogleAIChatClient

                # Using environment variables
                # Set GOOGLE_AI_API_KEY=your_api_key
                # Set GOOGLE_AI_CHAT_MODEL_ID=gemini-2.5-flash

                client = GoogleAIChatClient()

                # Or passing parameters directly
                client = GoogleAIChatClient(
                    model_id="gemini-2.5-flash",
                    api_key="your_api_key",
                )

                # Or loading from a .env file
                client = GoogleAIChatClient(env_file_path="path/to/.env")

                # Or passing in an existing client
                from google import genai

                google_client = genai.Client(api_key="your_api_key")
                client = GoogleAIChatClient(
                    model_id="gemini-2.5-flash",
                    google_client=google_client,
                )
        """
        google_settings = load_settings(
            GoogleAISettings,
            env_prefix="GOOGLE_AI_",
            api_key=api_key,
            chat_model_id=model_id,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        if google_client is None:
            if not google_settings["api_key"]:
                raise ValueError(
                    "Google AI API key is required. Set via 'api_key' parameter "
                    "or 'GOOGLE_AI_API_KEY' environment variable."
                )

            google_client = genai.Client(
                api_key=google_settings["api_key"].get_secret_value(),
                http_options={"headers": {"User-Agent": AGENT_FRAMEWORK_USER_AGENT}},
            )

        # Initialize parent
        super().__init__(
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            **kwargs,
        )

        # Initialize instance variables
        self.google_client = google_client
        self.model_id = google_settings["chat_model_id"]
        self._function_name_map: dict[str, str] = {}

    # region Static factory methods for hosted tools

    @staticmethod
    def get_google_search_tool() -> dict[str, Any]:
        """Create a Google Search tool configuration for Gemini.

        Returns:
            A dict-based tool configuration ready to pass to ChatAgent tools.

        Examples:
            .. code-block:: python

                from agent_framework_google import GoogleAIChatClient

                tool = GoogleAIChatClient.get_google_search_tool()
                agent = GoogleAIChatClient().as_agent(tools=[tool])
        """
        return {"google_search": {}}

    @staticmethod
    def get_code_execution_tool() -> dict[str, Any]:
        """Create a Code Execution tool configuration for Gemini.

        Returns:
            A dict-based tool configuration ready to pass to ChatAgent tools.

        Examples:
            .. code-block:: python

                from agent_framework_google import GoogleAIChatClient

                tool = GoogleAIChatClient.get_code_execution_tool()
                agent = GoogleAIChatClient().as_agent(tools=[tool])
        """
        return {"code_execution": {}}

    # endregion

    # region Get response methods

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        # prepare
        run_options = self._prepare_options(messages, options, **kwargs)
        model = run_options["model"]
        contents = run_options["contents"]
        config = run_options["config"]

        if stream:
            # Streaming mode
            async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                async for chunk in await self.google_client.aio.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=config,
                ):
                    parsed_chunk = self._process_stream_chunk(chunk)
                    if parsed_chunk:
                        yield parsed_chunk

            return self._build_response_stream(_stream(), response_format=options.get("response_format"))

        # Non-streaming mode
        async def _get_response() -> ChatResponse:
            response = await self.google_client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return self._process_response(response, options)

        return _get_response()

    # endregion

    # region Prep methods

    def _prepare_options(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create run options for the Google AI client based on messages and options.

        Args:
            messages: The list of chat messages.
            options: The options dict.
            kwargs: Additional keyword arguments.

        Returns:
            A dictionary with model, contents, and config keys for the Google AI client.
        """
        # Prepend instructions from options if they exist
        instructions = options.get("instructions")
        if instructions:
            from agent_framework._types import prepend_instructions_to_messages

            messages = prepend_instructions_to_messages(list(messages), instructions, role="system")

        # Build configuration
        config = self._create_config(options, messages, **kwargs)

        # Convert messages to Google AI format (skip system messages)
        contents = self._prepare_messages_for_google(messages)

        # Determine model ID
        model = options.get("model_id") or self.model_id
        if not model:
            raise ValueError("model_id must be a non-empty string")

        return {
            "model": model,
            "contents": contents,
            "config": config,
        }

    def _create_config(
        self,
        options: Mapping[str, Any],
        messages: Sequence[Message] | None = None,
        **kwargs: Any,
    ) -> types.GenerateContentConfig:
        """Create the Google AI generation config from chat options.

        Args:
            options: The chat options dict to convert.
            messages: The conversation messages (used to extract system instruction).
            kwargs: Additional keyword arguments.

        Returns:
            The Google AI generation config.
        """
        config_params: dict[str, Any] = {}

        # Extract system instruction from all system messages
        if messages:
            system_instructions = [msg.text for msg in messages if msg.role == "system" and msg.text]
            if system_instructions:
                config_params["system_instruction"] = "\n".join(system_instructions)

        # Map Agent Framework options to Google AI config
        if options.get("temperature") is not None:
            config_params["temperature"] = options["temperature"]
        if options.get("top_p") is not None:
            config_params["top_p"] = options["top_p"]
        if options.get("max_tokens") is not None:
            config_params["max_output_tokens"] = options["max_tokens"]
        if options.get("stop") is not None:
            stop_val = options["stop"]
            config_params["stop_sequences"] = [stop_val] if isinstance(stop_val, str) else list(stop_val)
        if options.get("top_k") is not None:
            config_params["top_k"] = options["top_k"]
        if options.get("candidate_count") is not None:
            config_params["candidate_count"] = options["candidate_count"]
        if options.get("presence_penalty") is not None:
            config_params["presence_penalty"] = options["presence_penalty"]
        if options.get("frequency_penalty") is not None:
            config_params["frequency_penalty"] = options["frequency_penalty"]

        # Add tools if provided
        if options.get("tools"):
            tools_list = self._prepare_tools_for_google(options)
            if tools_list:
                config_params["tools"] = tools_list

        # Add tool choice if provided
        if options.get("tool_choice") is not None:
            tool_config = self._prepare_tool_config(options)
            if tool_config:
                config_params["tool_config"] = tool_config

        extra_params = {k: v for k, v in kwargs.items() if not k.startswith("_") and k not in {"thread", "middleware"}}
        config_params.update(extra_params)

        return types.GenerateContentConfig(**config_params)

    def _prepare_tools_for_google(self, options: Mapping[str, Any]) -> list[Any] | None:
        """Convert tools to Google AI format.

        Converts FunctionTool to Google AI format. Hosted tools (google_search,
        code_execution) are passed through as Tool objects.

        Args:
            options: The options dict containing tools.

        Returns:
            List of Google AI Tool objects, or None if no tools.
        """
        tools = options.get("tools")
        if not tools:
            return None

        function_declarations: list[types.FunctionDeclaration] = []
        hosted_tools: list[Any] = []

        for tool_item in tools:
            if isinstance(tool_item, FunctionTool):
                # FunctionTool has name, description, and parameters() method
                function_declarations.append(
                    types.FunctionDeclaration(
                        name=tool_item.name,
                        description=tool_item.description or "",
                        parameters=tool_item.parameters(),
                    )
                )
            elif isinstance(tool_item, dict):
                # Hosted tools (google_search, code_execution) pass through as dicts
                if "google_search" in tool_item:
                    hosted_tools.append(types.Tool(google_search=types.GoogleSearch()))
                elif "code_execution" in tool_item:
                    hosted_tools.append(types.Tool(code_execution=types.ToolCodeExecution()))
                else:
                    # Other dict-based tools pass through unchanged
                    hosted_tools.append(tool_item)
            else:
                logger.debug(f"Ignoring unsupported tool type: {type(tool_item)}")

        result: list[Any] = []
        if function_declarations:
            result.append(types.Tool(function_declarations=function_declarations))
        result.extend(hosted_tools)

        return result or None

    def _prepare_tool_config(self, options: Mapping[str, Any]) -> types.ToolConfig | None:
        """Prepare tool_config for the Google AI request based on tool_choice.

        Args:
            options: The options dict containing tool_choice.

        Returns:
            A ToolConfig object, or None.
        """
        from agent_framework._types import validate_tool_mode

        tool_choice = options.get("tool_choice")
        tool_mode = validate_tool_mode(tool_choice)
        if tool_mode is None:
            return None

        match tool_mode.get("mode"):
            case "auto":
                return types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="AUTO")
                )
            case "required":
                if "required_function_name" in tool_mode:
                    return types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(
                            mode="ANY",
                            allowed_function_names=[tool_mode["required_function_name"]],
                        )
                    )
                return types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="ANY")
                )
            case "none":
                return types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="NONE")
                )
            case _:
                logger.debug(f"Ignoring unsupported tool choice mode: {tool_mode} for now")
                return None

    # endregion

    # region Message Conversion

    def _prepare_messages_for_google(self, messages: Sequence[Message]) -> list[dict[str, Any]]:
        """Convert Agent Framework messages to Google AI format.

        Args:
            messages: The messages to convert.

        Returns:
            The messages in Google AI format.

        Raises:
            ValueError: If no messages remain after filtering system messages.
        """
        google_messages: list[dict[str, Any]] = []

        for message in messages:
            # Skip system messages - they're passed as system_instruction in config
            if message.role == "system":
                continue
            google_messages.append(self._prepare_message_for_google(message))

        # Google AI requires at least one message
        if not google_messages:
            raise ValueError(
                "No messages to send to Google AI after filtering. "
                "Ensure at least one non-system message is provided."
            )

        return google_messages

    def _prepare_message_for_google(self, message: Message) -> dict[str, Any]:
        """Convert a single Agent Framework message to Google AI format.

        Args:
            message: The message to convert.

        Returns:
            The message in Google AI format.
        """
        google_parts: list[dict[str, Any]] = []

        for content in message.contents:
            match content.type:
                case "text":
                    if content.text:
                        google_parts.append({"text": content.text})
                case "function_call":
                    args = content.arguments
                    if isinstance(args, str):
                        from contextlib import suppress

                        with suppress(json.JSONDecodeError):
                            args = json.loads(args)
                    if isinstance(args, Mapping):
                        args = dict(args)
                    google_parts.append({
                        "function_call": {"name": content.name, "args": args or {}}
                    })
                case "function_result":
                    # function_result content uses call_id; Google API requires a name,
                    # so we look up the original function name from _function_name_map.
                    fn_name = self._function_name_map.get(content.call_id, content.call_id)
                    result = content.result
                    if result is None:
                        result = ""
                    google_parts.append({
                        "function_response": {
                            "name": fn_name,
                            "response": {"result": str(result)},
                        }
                    })
                case "data":
                    if content.media_type and content.media_type.startswith("image/"):
                        data_str = _get_data_bytes_as_str(content)
                        if data_str:
                            try:
                                data_bytes = base64.b64decode(data_str)
                                google_parts.append({
                                    "inline_data": {
                                        "mime_type": content.media_type,
                                        "data": data_bytes,
                                    }
                                })
                            except Exception as e:
                                logger.error(f"Failed to process image data: {e}")
                    else:
                        logger.debug(
                            f"Ignoring unsupported data media type: {content.media_type}"
                        )
                case "uri":
                    if content.media_type and content.media_type.startswith("image/"):
                        google_parts.append({
                            "file_data": {
                                "mime_type": content.media_type,
                                "file_uri": content.uri,
                            }
                        })
                    else:
                        logger.debug(
                            f"Ignoring unsupported URI content media type: {content.media_type}"
                        )
                case _:
                    logger.debug(
                        f"Ignoring unsupported content type: {content.type} for now"
                    )

        return {
            "role": ROLE_MAP.get(message.role, "user"),
            "parts": google_parts,
        }

    # endregion

    # region Response Processing Methods

    def _parse_parts_from_google(self, parts: list[Any]) -> list[Content]:
        """Parse Google AI response parts into Agent Framework Content objects.

        Handles text and function_call parts. Populates _function_name_map
        for function calls so that function_result conversion can look up
        the original function name.

        Args:
            parts: The list of parts from a Google AI response candidate.

        Returns:
            A list of Content objects parsed from the parts.
        """
        contents: list[Content] = []
        for part in parts:
            # Check for text content
            if hasattr(part, "text") and part.text:
                contents.append(
                    Content.from_text(
                        text=part.text,
                        raw_representation=part,
                    )
                )
            # Check for function call content
            elif hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                # Google doesn't provide a call ID, so we generate one
                call_id = str(uuid.uuid4())
                self._function_name_map[call_id] = fc.name
                # Handle args that might already be a dict or need parsing
                args_value = fc.args if fc.args else {}
                arguments = args_value if isinstance(args_value, dict) else str(args_value) if args_value else {}
                contents.append(
                    Content.from_function_call(
                        call_id=call_id,
                        name=fc.name,
                        arguments=arguments,
                        raw_representation=part,
                    )
                )
        return contents

    def _process_response(
        self,
        response: types.GenerateContentResponse,
        options: Mapping[str, Any],
    ) -> ChatResponse:
        """Process a Google AI response into Agent Framework format.

        Args:
            response: The Google AI response.
            options: The options dict used for the request.

        Returns:
            The Agent Framework chat response.
        """
        contents: list[Content] = []
        finish_reason: FinishReasonLiteral | None = "stop"

        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if (
                hasattr(candidate, "content")
                and candidate.content is not None
                and hasattr(candidate.content, "parts")
                and candidate.content.parts is not None
            ):
                contents = self._parse_parts_from_google(candidate.content.parts)

            # Determine finish reason from candidate
            if hasattr(candidate, "finish_reason") and candidate.finish_reason:
                reason_str = (
                    candidate.finish_reason.name
                    if hasattr(candidate.finish_reason, "name")
                    else str(candidate.finish_reason)
                )
                finish_reason = FINISH_REASON_MAP.get(reason_str, "stop")

        # If the response contains function calls, set finish_reason to "tool_calls"
        has_function_calls = any(c.type == "function_call" for c in contents)
        if has_function_calls and finish_reason == "stop":
            finish_reason = "tool_calls"

        # Parse usage
        usage_details = self._parse_usage_from_google(response)

        # Create the response message
        message = Message(
            "assistant",
            contents=contents,
            raw_representation=response,
        )

        return ChatResponse(
            messages=[message],
            finish_reason=finish_reason,
            usage_details=usage_details,
            model_id=options.get("model_id") or self.model_id,
            raw_representation=response,
            response_format=options.get("response_format"),
        )

    def _process_stream_chunk(
        self,
        chunk: types.GenerateContentResponse,
    ) -> ChatResponseUpdate | None:
        """Process a streaming chunk from Google AI.

        Args:
            chunk: The streaming chunk.

        Returns:
            A chat response update, or None if the chunk should be skipped.
        """
        contents: list[Content] = []
        finish_reason: FinishReasonLiteral | None = None

        if hasattr(chunk, "candidates") and chunk.candidates:
            candidate = chunk.candidates[0]
            if (
                hasattr(candidate, "content")
                and candidate.content is not None
                and hasattr(candidate.content, "parts")
                and candidate.content.parts is not None
            ):
                contents = self._parse_parts_from_google(candidate.content.parts)

            # Check finish reason
            if hasattr(candidate, "finish_reason") and candidate.finish_reason:
                reason_str = (
                    candidate.finish_reason.name
                    if hasattr(candidate.finish_reason, "name")
                    else str(candidate.finish_reason)
                )
                finish_reason = FINISH_REASON_MAP.get(reason_str, "stop")

        # Parse usage from chunk
        usage_details = self._parse_usage_from_google(chunk)
        if usage_details:
            contents.append(
                Content.from_usage(
                    usage_details=usage_details,
                    raw_representation=chunk,
                )
            )

        if not contents:
            return None

        return ChatResponseUpdate(
            role="assistant",
            contents=contents,
            finish_reason=finish_reason,
            raw_representation=chunk,
        )

    def _parse_usage_from_google(
        self,
        response: types.GenerateContentResponse,
    ) -> UsageDetails | None:
        """Parse usage details from a Google AI response.

        Args:
            response: The Google AI response or chunk.

        Returns:
            UsageDetails dict, or None if no usage metadata is present.
        """
        if not hasattr(response, "usage_metadata") or not response.usage_metadata:
            return None

        usage = response.usage_metadata
        result = UsageDetails(
            output_token_count=getattr(usage, "candidates_token_count", None),
        )
        input_count = getattr(usage, "prompt_token_count", None)
        if input_count is not None:
            result["input_token_count"] = input_count
        total_count = getattr(usage, "total_token_count", None)
        if total_count is not None:
            result["total_token_count"] = total_count
        cached_count = getattr(usage, "cached_content_token_count", None)
        if cached_count is not None:
            result["google.cached_content_token_count"] = cached_count  # type: ignore[typeddict-unknown-key]
        thoughts_count = getattr(usage, "thoughts_token_count", None)
        if thoughts_count is not None:
            result["google.thoughts_token_count"] = thoughts_count  # type: ignore[typeddict-unknown-key]
        return result

    def service_url(self) -> str:
        """Get the service URL for the chat client."""
        return "https://generativelanguage.googleapis.com"

    # endregion
