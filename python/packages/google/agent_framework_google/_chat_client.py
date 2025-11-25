# Copyright (c) Microsoft. All rights reserved.

import base64
import json
import uuid
from collections.abc import AsyncIterable, MutableSequence
from typing import Any, ClassVar

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
    Role,
    TextContent,
    UsageContent,
    UsageDetails,
    get_logger,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.observability import use_observability
from google import genai
from google.genai import types
from pydantic import SecretStr, ValidationError

logger = get_logger("agent_framework.google")

# Role mapping from Agent Framework to Google AI
# Note: SYSTEM messages are extracted to config.system_instruction and skipped in message conversion
ROLE_MAP: dict[Role, str] = {
    Role.USER: "user",
    Role.ASSISTANT: "model",
    Role.SYSTEM: "user",  # Fallback only - system messages are normally extracted to system_instruction
    Role.TOOL: "function",
}

# Finish reason mapping from Google AI to Agent Framework
FINISH_REASON_MAP: dict[str, FinishReason] = {
    "STOP": FinishReason.STOP,
    "MAX_TOKENS": FinishReason.LENGTH,
    "SAFETY": FinishReason.CONTENT_FILTER,
    "RECITATION": FinishReason.CONTENT_FILTER,
    "LANGUAGE": FinishReason.STOP,
    "OTHER": FinishReason.STOP,
    "BLOCKLIST": FinishReason.CONTENT_FILTER,
    "PROHIBITED_CONTENT": FinishReason.CONTENT_FILTER,
    "SPII": FinishReason.CONTENT_FILTER,
    "MALFORMED_FUNCTION_CALL": FinishReason.STOP,
    "IMAGE_SAFETY": FinishReason.CONTENT_FILTER,
    "IMAGE_PROHIBITED_CONTENT": FinishReason.CONTENT_FILTER,
    "IMAGE_OTHER": FinishReason.STOP,
    "NO_IMAGE": FinishReason.STOP,
    "IMAGE_RECITATION": FinishReason.CONTENT_FILTER,
    "UNEXPECTED_TOOL_CALL": FinishReason.STOP,
    "TOO_MANY_TOOL_CALLS": FinishReason.STOP,
}


class GoogleAISettings(AFBaseSettings):
    """Google AI settings for Gemini API access.

    The settings are first loaded from environment variables with the prefix 'GOOGLE_AI_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        api_key: The Google AI API key.
        chat_model_id: The Google AI chat model ID (e.g., gemini-1.5-pro).
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework_google import GoogleAISettings
            from pydantic import SecretStr

            # Using environment variables
            # Set GOOGLE_AI_API_KEY=your_api_key
            # GOOGLE_AI_CHAT_MODEL_ID=gemini-1.5-pro

            settings = GoogleAISettings()

            # Or pass parameters directly (pass SecretStr for type safety)
            settings = GoogleAISettings(api_key=SecretStr("your_api_key"), chat_model_id="gemini-1.5-pro")

            # Or loading from a .env file
            settings = GoogleAISettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "GOOGLE_AI_"

    api_key: SecretStr | None = None
    chat_model_id: str | None = None


@use_function_invocation
@use_observability
@use_chat_middleware
class GoogleAIChatClient(BaseChatClient):
    """Google AI chat client for Gemini models.

    This client implements the BaseChatClient interface to provide access to
    Google's Gemini models through the Google AI API (Gemini API).

    Examples:
        .. code-block:: python

            from agent_framework.google import GoogleAIChatClient

            # Using environment variables
            # Set GOOGLE_AI_API_KEY=your_api_key
            # Set GOOGLE_AI_CHAT_MODEL_ID=gemini-2.5-flash

            client = GoogleAIChatClient()

            # Or pass parameters directly
            client = GoogleAIChatClient(api_key="your_api_key", model_id="gemini-2.5-flash")
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "google"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        google_client: genai.Client | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a Google AI chat client.

        Keyword Args:
            api_key: The Google AI API key to use for authentication.
            model_id: The model ID to use for chat completions (e.g., "gemini-1.5-pro").
            google_client: An existing Google AI client instance. If provided, api_key is ignored.
            google_client: An existing Google GenAI client to use. If not provided, one will be created.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
            kwargs: Additional keyword arguments passed to the parent class.

        Raises:
            ServiceInitializationError: If settings validation fails or required values are missing.
        """
        try:
            google_settings = GoogleAISettings(
                api_key=api_key,  # type: ignore[arg-type]
                chat_model_id=model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create Google AI settings.", ex) from ex

        if google_client is None:
            if not google_settings.api_key:
                raise ServiceInitializationError(
                    "Google AI API key is required. Set via 'api_key' parameter "
                    "or 'GOOGLE_AI_API_KEY' environment variable."
                )

            google_client = genai.Client(
                api_key=google_settings.api_key.get_secret_value(),
                http_options={"headers": {"User-Agent": AGENT_FRAMEWORK_USER_AGENT}},
            )

        # Initialize parent
        super().__init__(**kwargs)

        # Initialize instance variables
        self.google_client = google_client
        self.model_id = google_settings.chat_model_id

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        """Get a response from the Google AI model.

        Args:
            messages: The conversation messages.
            chat_options: Options for the chat completion.
            kwargs: Additional keyword arguments.

        Returns:
            The chat response from the model.
        """
        # Create the request configuration (extracts system instruction)
        config = self._create_config(chat_options, messages, **kwargs)
        contents = self._convert_messages_to_google_format(messages)

        # Call the Google AI API using async interface
        response = await self.google_client.aio.models.generate_content(
            model=chat_options.model_id or self.model_id,
            contents=contents,
            config=config,
        )

        # Convert the response to Agent Framework format
        return self._process_response(response)

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Get a streaming response from the Google AI model.

        Args:
            messages: The conversation messages.
            chat_options: Options for the chat completion.
            kwargs: Additional keyword arguments.

        Yields:
            Chat response updates as they arrive from the model.
        """
        # Create the request configuration (extracts system instruction)
        config = self._create_config(chat_options, messages, **kwargs)
        contents = self._convert_messages_to_google_format(messages)

        # Call the Google AI streaming API using async interface
        stream = await self.google_client.aio.models.generate_content_stream(
            model=chat_options.model_id or self.model_id,
            contents=contents,
            config=config,
        )

        # Process the streaming response
        async for chunk in stream:
            parsed_chunk = self._process_stream_chunk(chunk)
            if parsed_chunk:
                yield parsed_chunk

    def _create_config(
        self,
        chat_options: ChatOptions,
        messages: MutableSequence[ChatMessage] | None = None,
        **kwargs: Any,
    ) -> types.GenerateContentConfig:
        """Create the Google AI generation config from chat options.

        Args:
            chat_options: The chat options to convert.
            messages: The conversation messages (used to extract system instruction).
            kwargs: Additional keyword arguments.

        Returns:
            The Google AI generation config.
        """
        config_params: dict[str, Any] = {}

        # Extract system instruction from all system messages
        if messages:
            system_instructions = [msg.text for msg in messages if msg.role == Role.SYSTEM]
            if system_instructions:
                config_params["system_instruction"] = "\n".join(system_instructions)

        # Map Agent Framework options to Google AI config
        if chat_options.temperature is not None:
            config_params["temperature"] = chat_options.temperature
        if chat_options.top_p is not None:
            config_params["top_p"] = chat_options.top_p
        if chat_options.max_tokens is not None:
            config_params["max_output_tokens"] = chat_options.max_tokens
        if chat_options.stop is not None:
            config_params["stop_sequences"] = chat_options.stop

        # Add tools if provided
        if chat_options.tools:
            tools_list = self._convert_tools_to_google_format(chat_options.tools)
            if tools_list:
                config_params["tools"] = tools_list

        # Add any additional properties
        if chat_options.additional_properties:
            config_params.update(chat_options.additional_properties)
        config_params.update(kwargs)

        return types.GenerateContentConfig(**config_params)

    def _convert_tools_to_google_format(self, tools: list[Any] | None) -> list[types.Tool] | None:
        """Convert tools to Google AI format.

        Args:
            tools: List of tools (functions, AIFunction objects, etc.)

        Returns:
            List of Google AI Tool objects, or None if no tools.
        """
        if not tools:
            return None

        function_declarations: list[types.FunctionDeclaration] = []

        for tool in tools:
            if isinstance(tool, AIFunction):
                # AIFunction has name, description, and parameters() method
                function_declarations.append(
                    types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description or "",
                        parameters=tool.parameters(),  # Returns JSON schema
                    )
                )
            elif callable(tool):
                # Plain function - extract schema from docstring and annotations
                func_name = tool.__name__
                func_doc = tool.__doc__ or ""

                # Try to get parameters from function annotations
                import inspect

                sig = inspect.signature(tool)
                parameters_schema = {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
                for param_name, param in sig.parameters.items():
                    if param_name == "self":
                        continue

                    param_type = "string"  # Default
                    if param.annotation != inspect.Parameter.empty:
                        # Map Python types to JSON schema types
                        annotation_str = str(param.annotation)

                        if param.annotation is int:
                            param_type = "integer"
                        elif param.annotation is float:
                            param_type = "number"
                        elif param.annotation is bool:
                            param_type = "boolean"
                        elif param.annotation is str:
                            param_type = "string"
                        elif param.annotation in (list, dict) or "list" in annotation_str or "dict" in annotation_str:
                            # Handle complex types (list, dict) as generic types
                            # Google AI requires specific schema, so we use string representation
                            param_type = "string"

                    parameters_schema["properties"][param_name] = {"type": param_type}

                    # Add to required if no default value
                    if param.default == inspect.Parameter.empty:
                        parameters_schema["required"].append(param_name)

                function_declarations.append(
                    types.FunctionDeclaration(
                        name=func_name,
                        description=func_doc.split("\n\n")[0].strip(),  # First paragraph
                        parameters=parameters_schema,
                    )
                )
            else:
                logger.debug(f"Ignoring unsupported tool type: {type(tool)}")

        if not function_declarations:
            return None

        # Google AI expects a list of Tool objects
        return [types.Tool(function_declarations=function_declarations)]

    def _convert_messages_to_google_format(self, messages: MutableSequence[ChatMessage]) -> list[dict[str, Any]]:
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
            if message.role == Role.SYSTEM:
                continue
            google_messages.append(self._convert_message_to_google_format(message))

        # Google AI requires at least one message
        if not google_messages:
            raise ValueError(
                "No messages to send to Google AI after filtering. Ensure at least one non-system message is provided."
            )

        return google_messages

    def _convert_message_to_google_format(self, message: ChatMessage) -> dict[str, Any]:
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
                    google_parts.append({"text": content.text})
                case "function_call":
                    args = content.arguments
                    if isinstance(args, str):
                        from contextlib import suppress

                        with suppress(json.JSONDecodeError):
                            args = json.loads(args)
                    google_parts.append({"function_call": {"name": content.name, "args": args}})
                case "function_result":
                    # FunctionResultContent only has call_id and result, not function name
                    # Use call_id as the name since Google requires it
                    google_parts.append({
                        "function_response": {"name": content.call_id, "response": {"result": content.result}}
                    })
                case "data":
                    if content.media_type and content.media_type.startswith("image/"):
                        # Extract base64 data from URI (data:image/png;base64,...)
                        try:
                            base64_data = content.uri.split(",", 1)[1]
                            data_bytes = base64.b64decode(base64_data)

                            google_parts.append({"inline_data": {"mime_type": content.media_type, "data": data_bytes}})
                        except Exception as e:
                            logger.error(f"Failed to process image data: {e}")
                    else:
                        logger.debug(f"Ignoring unsupported data media type: {content.media_type}")
                case _:
                    logger.debug(f"Ignoring unsupported content type: {content.type} for now")

        return {
            "role": ROLE_MAP.get(message.role, "user"),
            "parts": google_parts,
        }

    def _extract_text_from_response(self, response: types.GenerateContentResponse) -> str:
        """Extract text content from a Google AI response.

        Args:
            response: The Google AI response or chunk.

        Returns:
            The extracted text content.
        """
        text = ""
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                for part in candidate.content.parts:
                    if hasattr(part, "text") and part.text:
                        text += part.text
        return text

    def _process_response(self, response: types.GenerateContentResponse) -> ChatResponse:
        """Process a Google AI response into Agent Framework format.

        Args:
            response: The Google AI response.

        Returns:
            The Agent Framework chat response.
        """
        contents: list[Contents] = []

        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if (
                hasattr(candidate, "content")
                and candidate.content is not None
                and hasattr(candidate.content, "parts")
                and candidate.content.parts is not None
            ):
                for part in candidate.content.parts:
                    # Check for text content
                    if hasattr(part, "text") and part.text:
                        contents.append(TextContent(text=part.text, raw_representation=part))
                    # Check for function call content (only if text is not present)
                    elif hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        # Google doesn't provide a call ID, so we generate one
                        call_id = str(uuid.uuid4())
                        # Handle args that might already be a dict or need parsing
                        args_value = fc.args if fc.args else {}
                        if isinstance(args_value, dict):
                            arguments_str = json.dumps(args_value)
                        else:
                            arguments_str = str(args_value) if args_value else "{}"
                        contents.append(FunctionCallContent(call_id=call_id, name=fc.name, arguments=arguments_str))

        # Add usage information if available
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage_details = UsageDetails(
                input_token_count=getattr(response.usage_metadata, "prompt_token_count", 0),
                output_token_count=getattr(response.usage_metadata, "candidates_token_count", 0),
            )
            contents.append(UsageContent(details=usage_details, raw_representation=response.usage_metadata))

        # Determine finish reason
        finish_reason = FinishReason.STOP
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "finish_reason"):
                finish_reason = FINISH_REASON_MAP.get(
                    candidate.finish_reason.name
                    if hasattr(candidate.finish_reason, "name")
                    else str(candidate.finish_reason),
                    FinishReason.STOP,
                )

        # Create the chat message
        message = ChatMessage(
            role=Role.ASSISTANT,
            contents=contents,
        )

        return ChatResponse(
            messages=[message],
            finish_reason=finish_reason,
        )

    def _process_stream_chunk(self, chunk: types.GenerateContentResponse) -> ChatResponseUpdate | None:
        """Process a streaming chunk from Google AI.

        Args:
            chunk: The streaming chunk.

        Returns:
            A chat response update, or None if the chunk should be skipped.
        """
        # Extract text from the chunk
        text = self._extract_text_from_response(chunk)

        if not text:
            return None

        # Create the update
        return ChatResponseUpdate(
            role=Role.ASSISTANT,
            contents=[TextContent(text=text, raw_representation=chunk)],
        )
