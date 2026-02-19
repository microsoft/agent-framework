# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterable, Awaitable, Mapping, MutableMapping, Sequence
from typing import Any, ClassVar, Final, Generic, Literal, TypedDict

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    Annotation,
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
    TextSpanRegion,
    UsageDetails,
)
from agent_framework._settings import SecretString, load_settings
from agent_framework._types import _get_data_bytes_as_str  # type: ignore
from agent_framework.observability import ChatTelemetryLayer
from anthropic import AsyncAnthropic
from anthropic.types.beta import (
    BetaContentBlock,
    BetaMessage,
    BetaMessageDeltaUsage,
    BetaRawContentBlockDelta,
    BetaRawMessageStreamEvent,
    BetaTextBlock,
    BetaUsage,
)
from anthropic.types.beta.beta_bash_code_execution_tool_result_error import (
    BetaBashCodeExecutionToolResultError,
)
from anthropic.types.beta.beta_code_execution_result_block import BetaCodeExecutionResultBlock
from anthropic.types.beta.beta_code_execution_tool_result_error import (
    BetaCodeExecutionToolResultError,
)
from anthropic.types.beta.beta_encrypted_code_execution_result_block import BetaEncryptedCodeExecutionResultBlock
from pydantic import BaseModel

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
    "AnthropicChatOptions",
    "AnthropicClient",
    "ThinkingConfig",
]

logger = logging.getLogger("agent_framework.anthropic")

ANTHROPIC_DEFAULT_MAX_TOKENS: Final[int] = 1024
BETA_FLAGS: Final[list[str]] = ["mcp-client-2025-04-04", "code-execution-2025-08-25"]
STRUCTURED_OUTPUTS_BETA_FLAG: Final[str] = "structured-outputs-2025-11-13"

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel | None, default=None)


# region Anthropic Chat Options TypedDict


class ThinkingConfig(TypedDict, total=False):
    """Configuration for enabling Claude's extended thinking.

    When enabled, responses include ``thinking`` content blocks showing Claude's
    thinking process before the final answer. Requires a minimum budget of 1,024
    tokens and counts towards your ``max_tokens`` limit.

    See https://docs.claude.com/en/docs/build-with-claude/extended-thinking for details.

    Keys:
        type: "enabled" to enable extended thinking, "disabled" to disable.
        budget_tokens: The token budget for thinking (minimum 1024, required when type="enabled").
    """

    type: Literal["enabled", "disabled"]
    budget_tokens: int


class AnthropicChatOptions(ChatOptions[ResponseModelT], Generic[ResponseModelT], total=False):
    """Anthropic-specific chat options.

    Extends ChatOptions with options specific to Anthropic's Messages API.
    Options that Anthropic doesn't support are typed as None to indicate they're unavailable.

    Note:
        Anthropic REQUIRES max_tokens to be specified. If not provided,
        a default of 1024 will be used.

    Keys:
        model_id: The model to use for the request,
            translates to ``model`` in Anthropic API.
        temperature: Sampling temperature between 0 and 1.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum number of tokens to generate (REQUIRED).
        stop: Stop sequences,
            translates to ``stop_sequences`` in Anthropic API.
        tools: List of tools (functions) available to the model.
        tool_choice: How the model should use tools.
        response_format: Structured output schema.
        metadata: Request metadata with user_id for tracking.
        user: User identifier, translates to ``metadata.user_id`` in Anthropic API.
        instructions: System instructions for the model,
            translates to ``system`` in Anthropic API.
        top_k: Number of top tokens to consider for sampling.
        service_tier: Service tier ("auto" or "standard_only").
        thinking: Extended thinking configuration for Claude models.
            When enabled, responses include ``thinking`` content blocks showing Claude's
            thinking process before the final answer. Requires a minimum budget of 1,024
            tokens and counts towards your ``max_tokens`` limit.
            See https://docs.claude.com/en/docs/build-with-claude/extended-thinking for details.
        container: Container configuration for skills.
        additional_beta_flags: Additional beta flags to enable on the request.
    """

    # Anthropic-specific generation parameters (supported by all models)
    top_k: int
    service_tier: Literal["auto", "standard_only"]

    # Extended thinking (Claude models)
    thinking: ThinkingConfig

    # Skills
    container: dict[str, Any]

    # Beta features
    additional_beta_flags: list[str]

    # Unsupported base options (override with None to indicate not supported)
    logit_bias: None  # type: ignore[misc]
    seed: None  # type: ignore[misc]
    frequency_penalty: None  # type: ignore[misc]
    presence_penalty: None  # type: ignore[misc]
    store: None  # type: ignore[misc]
    conversation_id: None  # type: ignore[misc]


AnthropicOptionsT = TypeVar(
    "AnthropicOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="AnthropicChatOptions",
    covariant=True,
)

# Translation between framework options keys and Anthropic Messages API
OPTION_TRANSLATIONS: dict[str, str] = {
    "model_id": "model",
    "stop": "stop_sequences",
    "instructions": "system",
}


# region Role and Finish Reason Maps


ROLE_MAP: dict[str, str] = {
    "user": "user",
    "assistant": "assistant",
    "system": "user",
    "tool": "user",
}

FINISH_REASON_MAP: dict[str, FinishReasonLiteral] = {
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "end_turn": "stop",
    "refusal": "content_filter",
    "pause_turn": "stop",
}


class AnthropicSettings(TypedDict, total=False):
    """Anthropic Project settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'ANTHROPIC_'.

    Keys:
        api_key: The Anthropic API key.
        chat_model_id: The Anthropic chat model ID.
    """

    api_key: SecretString | None
    chat_model_id: str | None


class AnthropicClient(
    ChatMiddlewareLayer[AnthropicOptionsT],
    FunctionInvocationLayer[AnthropicOptionsT],
    ChatTelemetryLayer[AnthropicOptionsT],
    BaseChatClient[AnthropicOptionsT],
    Generic[AnthropicOptionsT],
):
    """Anthropic Chat client with middleware, telemetry, and function invocation support."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "anthropic"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        anthropic_client: AsyncAnthropic | None = None,
        additional_beta_flags: list[str] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Anthropic Agent client.

        Keyword Args:
            api_key: The Anthropic API key to use for authentication.
            model_id: The ID of the model to use.
            anthropic_client: An existing Anthropic client to use. If not provided, one will be created.
                This can be used to further configure the client before passing it in.
                For instance if you need to set a different base_url for testing or private deployments.
            additional_beta_flags: Additional beta flags to enable on the client.
                Default flags are: "mcp-client-2025-04-04", "code-execution-2025-08-25".
            middleware: Optional middleware to apply to the client.
            function_invocation_configuration: Optional function invocation configuration override.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
            kwargs: Additional keyword arguments passed to the parent class.

        Examples:
            .. code-block:: python

                from agent_framework.anthropic import AnthropicClient
                from azure.identity.aio import DefaultAzureCredential

                # Using environment variables
                # Set ANTHROPIC_API_KEY=your_anthropic_api_key
                # ANTHROPIC_CHAT_MODEL_ID=claude-sonnet-4-5-20250929

                # Or passing parameters directly
                client = AnthropicClient(
                    model_id="claude-sonnet-4-5-20250929",
                    api_key="your_anthropic_api_key",
                )

                # Or loading from a .env file
                client = AnthropicClient(env_file_path="path/to/.env")

                # Or passing in an existing client
                from anthropic import AsyncAnthropic

                anthropic_client = AsyncAnthropic(
                    api_key="your_anthropic_api_key", base_url="https://custom-anthropic-endpoint.com"
                )
                client = AnthropicClient(
                    model_id="claude-sonnet-4-5-20250929",
                    anthropic_client=anthropic_client,
                )

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework.anthropic import AnthropicChatOptions


                class MyOptions(AnthropicChatOptions, total=False):
                    my_custom_option: str


                client: AnthropicClient[MyOptions] = AnthropicClient(model_id="claude-sonnet-4-5-20250929")
                response = await client.get_response("Hello", options={"my_custom_option": "value"})

        """
        anthropic_settings = load_settings(
            AnthropicSettings,
            env_prefix="ANTHROPIC_",
            api_key=api_key,
            chat_model_id=model_id,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        if anthropic_client is None:
            if not anthropic_settings["api_key"]:
                raise ValueError(
                    "Anthropic API key is required. Set via 'api_key' parameter "
                    "or 'ANTHROPIC_API_KEY' environment variable."
                )

            anthropic_client = AsyncAnthropic(
                api_key=anthropic_settings["api_key"].get_secret_value(),
                default_headers={"User-Agent": AGENT_FRAMEWORK_USER_AGENT},
            )

        # Initialize parent
        super().__init__(
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            **kwargs,
        )

        # Initialize instance variables
        self.anthropic_client = anthropic_client
        self.additional_beta_flags = additional_beta_flags or []
        self.model_id = anthropic_settings["chat_model_id"]
        # streaming requires tracking the last function call ID, name, and content type
        self._last_call_id_name: tuple[str, str] | None = None
        self._last_call_content_type: str | None = None

    # region Static factory methods for hosted tools

    @staticmethod
    def get_code_interpreter_tool(
        *,
        type_name: str | None = None,
        name: str = "code_execution",
    ) -> dict[str, Any]:
        """Create a code interpreter tool configuration for Anthropic.

        Keyword Args:
            type_name: Override the tool type name. Defaults to "code_execution_20250825".
            name: The name for this tool. Defaults to "code_execution".

        Returns:
            A dict-based tool configuration ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.anthropic import AnthropicClient

                tool = AnthropicClient.get_code_interpreter_tool()
                agent = AnthropicClient().as_agent(tools=[tool])
        """
        return {"type": type_name or "code_execution_20250825", "name": name}

    @staticmethod
    def get_web_search_tool(
        *,
        type_name: str | None = None,
        name: str = "web_search",
    ) -> dict[str, Any]:
        """Create a web search tool configuration for Anthropic.

        Keyword Args:
            type_name: Override the tool type name. Defaults to "web_search_20250305".
            name: The name for this tool. Defaults to "web_search".

        Returns:
            A dict-based tool configuration ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.anthropic import AnthropicClient

                tool = AnthropicClient.get_web_search_tool()
                agent = AnthropicClient().as_agent(tools=[tool])
        """
        return {"type": type_name or "web_search_20250305", "name": name}

    @staticmethod
    def get_mcp_tool(
        *,
        name: str,
        url: str,
        allowed_tools: list[str] | None = None,
        authorization_token: str | None = None,
    ) -> dict[str, Any]:
        """Create a hosted MCP tool configuration for Anthropic.

        This configures an MCP (Model Context Protocol) server that will be called
        by Anthropic's service. The tools from this MCP server are executed remotely
        by Anthropic, not locally by your application.

        Note:
            For local MCP execution where your application calls the MCP server
            directly, use the MCP client tools instead of this method.

        Keyword Args:
            name: A label/name for the MCP server.
            url: The URL of the MCP server.
            allowed_tools: List of tool names that are allowed to be used from this MCP server.
            authorization_token: Authorization token for the MCP server (e.g., Bearer token).

        Returns:
            A dict-based tool configuration ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.anthropic import AnthropicClient

                tool = AnthropicClient.get_mcp_tool(
                    name="GitHub",
                    url="https://api.githubcopilot.com/mcp/",
                    authorization_token="Bearer ghp_xxx",
                )
                agent = AnthropicClient().as_agent(tools=[tool])
        """
        result: dict[str, Any] = {
            "type": "mcp",
            "server_label": name.replace(" ", "_"),
            "server_url": url,
        }

        if allowed_tools:
            result["allowed_tools"] = allowed_tools

        if authorization_token:
            result["headers"] = {"authorization": authorization_token}

        return result

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

        if stream:
            # Streaming mode
            async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                async for chunk in await self.anthropic_client.beta.messages.create(**run_options, stream=True):
                    parsed_chunk = self._process_stream_event(chunk)
                    if parsed_chunk:
                        yield parsed_chunk

            return self._build_response_stream(_stream(), response_format=options.get("response_format"))

        # Non-streaming mode
        async def _get_response() -> ChatResponse:
            message = await self.anthropic_client.beta.messages.create(**run_options, stream=False)
            return self._process_message(message, options)

        return _get_response()

    # region Prep methods

    def _prepare_options(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create run options for the Anthropic client based on messages and options.

        Args:
            messages: The list of chat messages.
            options: The options dict.
            kwargs: Additional keyword arguments.

        Returns:
            A dictionary of run options for the Anthropic client.
        """
        # Prepend instructions from options if they exist
        instructions = options.get("instructions")
        if instructions:
            from agent_framework._types import prepend_instructions_to_messages

            messages = prepend_instructions_to_messages(list(messages), instructions, role="system")

        # Start with a copy of options, excluding keys we handle separately
        run_options: dict[str, Any] = {
            k: v for k, v in options.items() if v is not None and k not in {"instructions", "response_format"}
        }
        # Framework-level options handled elsewhere; do not forward as raw Anthropic request kwargs.
        run_options.pop("allow_multiple_tool_calls", None)
        # Stream mode is controlled explicitly at call sites.
        run_options.pop("stream", None)

        # Translation between options keys and Anthropic Messages API
        for old_key, new_key in OPTION_TRANSLATIONS.items():
            if old_key in run_options and old_key != new_key:
                run_options[new_key] = run_options.pop(old_key)

        # model id
        if not run_options.get("model"):
            if not self.model_id:
                raise ValueError("model_id must be a non-empty string")
            run_options["model"] = self.model_id

        # max_tokens - Anthropic requires this, default if not provided
        if not run_options.get("max_tokens"):
            run_options["max_tokens"] = ANTHROPIC_DEFAULT_MAX_TOKENS

        # messages
        run_options["messages"] = self._prepare_messages_for_anthropic(messages)

        # system message - first system message is passed as instructions
        if messages and isinstance(messages[0], Message) and messages[0].role == "system":
            run_options["system"] = messages[0].text

        # betas
        run_options["betas"] = self._prepare_betas(options)

        # extra headers
        run_options["extra_headers"] = {"User-Agent": AGENT_FRAMEWORK_USER_AGENT}

        # Handle user option -> metadata.user_id (Anthropic uses metadata.user_id instead of user)
        if user := run_options.pop("user", None):
            metadata = run_options.get("metadata", {})
            if "user_id" not in metadata:
                metadata["user_id"] = user
            run_options["metadata"] = metadata

        # tools, mcp servers and tool choice
        if tools_config := self._prepare_tools_for_anthropic(options):
            run_options.update(tools_config)

        # response_format - use native output_format for structured outputs
        response_format = options.get("response_format")
        if response_format is not None:
            run_options["output_format"] = self._prepare_response_format(response_format)
            # Add the structured outputs beta flag
            run_options["betas"].add(STRUCTURED_OUTPUTS_BETA_FLAG)

        # Filter out framework kwargs that should not be passed to the Anthropic API.
        # This includes underscore-prefixed internal objects (like _function_middleware_pipeline)
        # and framework kwargs like 'thread' and 'middleware'.
        filtered_kwargs = {
            k: v for k, v in kwargs.items() if not k.startswith("_") and k not in {"thread", "middleware"}
        }
        run_options.update(filtered_kwargs)
        return run_options

    def _prepare_betas(self, options: Mapping[str, Any]) -> set[str]:
        """Prepare the beta flags for the Anthropic API request.

        Args:
            options: The options dict that may contain additional beta flags.

        Returns:
            A set of beta flag strings to include in the request.
        """
        return {
            *BETA_FLAGS,
            *self.additional_beta_flags,
            *options.get("additional_beta_flags", []),
        }

    def _prepare_response_format(self, response_format: type[BaseModel] | dict[str, Any]) -> dict[str, Any]:
        """Prepare the output_format parameter for structured output.

        Args:
            response_format: Either a Pydantic model class or a dict with the schema specification.
                If a dict, it can be in OpenAI-style format with "json_schema" key,
                or direct format with "schema" key, or the raw schema dict itself.

        Returns:
            A dictionary representing the output_format for Anthropic's structured outputs.
        """
        if isinstance(response_format, dict):
            if "json_schema" in response_format:
                schema = response_format["json_schema"].get("schema", {})
            elif "schema" in response_format:
                schema = response_format["schema"]
            else:
                schema = response_format

            if isinstance(schema, dict):
                schema["additionalProperties"] = False

            return {
                "type": "json_schema",
                "schema": schema,
            }

        schema = response_format.model_json_schema()
        schema["additionalProperties"] = False

        return {
            "type": "json_schema",
            "schema": schema,
        }

    def _prepare_messages_for_anthropic(self, messages: Sequence[Message]) -> list[dict[str, Any]]:
        """Prepare a list of ChatMessages for the Anthropic client.

        This skips the first message if it is a system message,
        as Anthropic expects system instructions as a separate parameter.
        """
        # first system message is passed as instructions
        if messages and isinstance(messages[0], Message) and messages[0].role == "system":
            return [self._prepare_message_for_anthropic(msg) for msg in messages[1:]]
        return [self._prepare_message_for_anthropic(msg) for msg in messages]

    def _prepare_message_for_anthropic(self, message: Message) -> dict[str, Any]:
        """Prepare a Message for the Anthropic client.

        Args:
            message: The Message to convert.

        Returns:
            A dictionary representing the message in Anthropic format.
        """
        a_content: list[dict[str, Any]] = []
        for content in message.contents:
            match content.type:
                case "text":
                    # Skip empty text content blocks - Anthropic API rejects them
                    if content.text:
                        a_content.append({"type": "text", "text": content.text})
                case "data":
                    if content.has_top_level_media_type("image"):
                        a_content.append({
                            "type": "image",
                            "source": {
                                "data": _get_data_bytes_as_str(content),  # type: ignore[attr-defined]
                                "media_type": content.media_type,
                                "type": "base64",
                            },
                        })
                    else:
                        logger.debug(f"Ignoring unsupported data content media type: {content.media_type} for now")
                case "uri":
                    if content.has_top_level_media_type("image"):
                        a_content.append({
                            "type": "image",
                            "source": {"type": "url", "url": content.uri},
                        })
                    else:
                        logger.debug(f"Ignoring unsupported data content media type: {content.media_type} for now")
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
                        "content": content.result if content.result is not None else "",
                        "is_error": content.exception is not None,
                    })
                case "mcp_server_tool_call":
                    mcp_call: dict[str, Any] = {
                        "type": "mcp_tool_use",
                        "id": content.call_id,
                        "name": content.tool_name,
                        "server_name": content.server_name or "",
                        "input": content.parse_arguments() or {},
                    }
                    a_content.append(mcp_call)
                case "mcp_server_tool_result":
                    mcp_result: dict[str, Any] = {
                        "type": "mcp_tool_result",
                        "tool_use_id": content.call_id,
                        "content": content.output if content.output is not None else "",
                    }
                    a_content.append(mcp_result)
                case "text_reasoning":
                    thinking_block: dict[str, Any] = {"type": "thinking", "thinking": content.text}
                    if content.protected_data:
                        thinking_block["signature"] = content.protected_data
                    a_content.append(thinking_block)
                case _:
                    logger.debug(f"Ignoring unsupported content type: {content.type} for now")

        return {
            "role": ROLE_MAP.get(message.role, "user"),
            "content": a_content,
        }

    def _prepare_tools_for_anthropic(self, options: Mapping[str, Any]) -> dict[str, Any] | None:
        """Prepare tools and tool choice configuration for the Anthropic API request.

        Converts FunctionTool to Anthropic format. MCP tools are routed to separate
        mcp_servers parameter. All other tools pass through unchanged.

        Args:
            options: The options dict containing tools and tool choice settings.

        Returns:
            A dictionary with tools, mcp_servers, and tool_choice configuration, or None if empty.
        """
        from agent_framework._types import validate_tool_mode

        result: dict[str, Any] = {}
        tools = options.get("tools")

        # Process tools
        if tools:
            tool_list: list[Any] = []
            mcp_server_list: list[Any] = []
            for tool in tools:
                if isinstance(tool, FunctionTool):
                    tool_list.append({
                        "type": "custom",
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.parameters(),
                    })
                elif isinstance(tool, MutableMapping) and tool.get("type") == "mcp":
                    # MCP servers must be routed to separate mcp_servers parameter
                    server_def: dict[str, Any] = {
                        "type": "url",
                        "name": tool.get("server_label", ""),
                        "url": tool.get("server_url", ""),
                    }
                    if allowed_tools := tool.get("allowed_tools"):
                        server_def["tool_configuration"] = {"allowed_tools": list(allowed_tools)}
                    headers = tool.get("headers")
                    if isinstance(headers, dict) and (auth := headers.get("authorization")):
                        server_def["authorization_token"] = auth
                    mcp_server_list.append(server_def)
                else:
                    # Pass through all other tools (dicts, SDK types) unchanged
                    tool_list.append(tool)

            if tool_list:
                result["tools"] = tool_list
            if mcp_server_list:
                result["mcp_servers"] = mcp_server_list

        # Process tool choice
        if options.get("tool_choice") is None:
            return result or None
        tool_mode = validate_tool_mode(options.get("tool_choice"))
        if tool_mode is None:
            return result or None
        allow_multiple = options.get("allow_multiple_tool_calls")
        match tool_mode.get("mode"):
            case "auto":
                tool_choice: dict[str, Any] = {"type": "auto"}
                if allow_multiple is not None:
                    tool_choice["disable_parallel_tool_use"] = not allow_multiple
                result["tool_choice"] = tool_choice
            case "required":
                if "required_function_name" in tool_mode:
                    tool_choice = {
                        "type": "tool",
                        "name": tool_mode["required_function_name"],
                    }
                else:
                    tool_choice = {"type": "any"}
                if allow_multiple is not None:
                    tool_choice["disable_parallel_tool_use"] = not allow_multiple
                result["tool_choice"] = tool_choice
            case "none":
                result["tool_choice"] = {"type": "none"}
            case _:
                logger.debug(f"Ignoring unsupported tool choice mode: {tool_mode} for now")

        return result or None

    # region Response Processing Methods

    def _process_message(self, message: BetaMessage, options: Mapping[str, Any]) -> ChatResponse:
        """Process the response from the Anthropic client.

        Args:
            message: The message returned by the Anthropic client.
            options: The options dict used for the request.

        Returns:
            A ChatResponse object containing the processed response.
        """
        return ChatResponse(
            response_id=message.id,
            messages=[
                Message(
                    role="assistant",
                    contents=self._parse_contents_from_anthropic(message.content),
                    raw_representation=message,
                )
            ],
            usage_details=self._parse_usage_from_anthropic(message.usage),
            model_id=message.model,
            finish_reason=FINISH_REASON_MAP.get(message.stop_reason) if message.stop_reason else None,
            response_format=options.get("response_format"),
            raw_representation=message,
        )

    def _process_stream_event(self, event: BetaRawMessageStreamEvent) -> ChatResponseUpdate | None:
        """Process a streaming event from the Anthropic client.

        Args:
            event: The streaming event returned by the Anthropic client.

        Returns:
            A ChatResponseUpdate object containing the processed update.
        """
        match event.type:
            case "message_start":
                usage_details: list[Content] = []
                if event.message.usage and (details := self._parse_usage_from_anthropic(event.message.usage)):
                    usage_details.append(Content.from_usage(usage_details=details))

                return ChatResponseUpdate(
                    response_id=event.message.id,
                    contents=[
                        *self._parse_contents_from_anthropic(event.message.content),
                        *usage_details,
                    ],
                    model_id=event.message.model,
                    finish_reason=FINISH_REASON_MAP.get(event.message.stop_reason)
                    if event.message.stop_reason
                    else None,
                    raw_representation=event,
                )
            case "message_delta":
                usage = self._parse_usage_from_anthropic(event.usage)
                return ChatResponseUpdate(
                    contents=[Content.from_usage(usage_details=usage, raw_representation=event.usage)] if usage else [],
                    finish_reason=FINISH_REASON_MAP.get(event.delta.stop_reason) if event.delta.stop_reason else None,
                    raw_representation=event,
                )
            case "message_stop":
                logger.debug("Received message_stop event; no content to process.")
            case "content_block_start":
                contents = self._parse_contents_from_anthropic([event.content_block])
                return ChatResponseUpdate(
                    contents=contents,
                    raw_representation=event,
                )
            case "content_block_delta":
                contents = self._parse_contents_from_anthropic([event.delta])
                return ChatResponseUpdate(
                    contents=contents,
                    raw_representation=event,
                )
            case "content_block_stop":
                logger.debug("Received content_block_stop event; no content to process.")
            case _:
                logger.debug(f"Ignoring unsupported event type: {event.type}")
        return None

    def _parse_usage_from_anthropic(self, usage: BetaUsage | BetaMessageDeltaUsage | None) -> UsageDetails | None:
        """Parse usage details from the Anthropic message usage."""
        if not usage:
            return None
        usage_details = UsageDetails(output_token_count=usage.output_tokens)
        if usage.input_tokens is not None:
            usage_details["input_token_count"] = usage.input_tokens
        if usage.cache_creation_input_tokens is not None:
            usage_details["anthropic.cache_creation_input_tokens"] = usage.cache_creation_input_tokens  # type: ignore[typeddict-unknown-key]
        if usage.cache_read_input_tokens is not None:
            usage_details["anthropic.cache_read_input_tokens"] = usage.cache_read_input_tokens  # type: ignore[typeddict-unknown-key]
        return usage_details

    def _parse_contents_from_anthropic(
        self,
        content: Sequence[BetaContentBlock | BetaRawContentBlockDelta | BetaTextBlock],
    ) -> list[Content]:
        """Parse contents from the Anthropic message."""
        contents: list[Content] = []
        for content_block in content:
            match content_block.type:
                case "text" | "text_delta":
                    contents.append(
                        Content.from_text(
                            text=content_block.text,
                            raw_representation=content_block,
                            annotations=self._parse_citations_from_anthropic(content_block),
                        )
                    )
                case "tool_use" | "mcp_tool_use" | "server_tool_use":
                    self._last_call_id_name = (content_block.id, content_block.name)
                    self._last_call_content_type = content_block.type
                    if content_block.type == "mcp_tool_use":
                        contents.append(
                            Content.from_mcp_server_tool_call(
                                call_id=content_block.id,
                                tool_name=content_block.name,
                                server_name=getattr(content_block, "server_name", None),
                                arguments=content_block.input,
                                raw_representation=content_block,
                            )
                        )
                    elif "code_execution" in (content_block.name or ""):
                        contents.append(
                            Content.from_code_interpreter_tool_call(
                                call_id=content_block.id,
                                inputs=[
                                    Content.from_text(
                                        text=str(content_block.input),
                                        raw_representation=content_block,
                                    )
                                ],
                                raw_representation=content_block,
                            )
                        )
                    else:
                        contents.append(
                            Content.from_function_call(
                                call_id=content_block.id,
                                name=content_block.name,
                                arguments=content_block.input,
                                raw_representation=content_block,
                            )
                        )
                case "mcp_tool_result":
                    call_id, _ = self._last_call_id_name or (None, None)
                    parsed_output: list[Content] | None = None
                    if content_block.content:
                        if isinstance(content_block.content, list):
                            parsed_output = self._parse_contents_from_anthropic(content_block.content)
                        elif isinstance(content_block.content, (str, bytes)):
                            parsed_output = [
                                Content.from_text(
                                    text=str(content_block.content),
                                    raw_representation=content_block,
                                )
                            ]
                        else:
                            parsed_output = self._parse_contents_from_anthropic([content_block.content])
                    contents.append(
                        Content.from_mcp_server_tool_result(
                            call_id=content_block.tool_use_id,
                            output=parsed_output,
                            raw_representation=content_block,
                        )
                    )
                case "web_search_tool_result" | "web_fetch_tool_result":
                    call_id, _ = self._last_call_id_name or (None, None)
                    contents.append(
                        Content.from_function_result(
                            call_id=content_block.tool_use_id,
                            result=content_block.content,
                            raw_representation=content_block,
                        )
                    )
                case "code_execution_tool_result":
                    code_outputs: list[Content] = []
                    if content_block.content:
                        if isinstance(content_block.content, BetaCodeExecutionToolResultError):
                            code_outputs.append(
                                Content.from_error(
                                    message=content_block.content.error_code,
                                    raw_representation=content_block.content,
                                )
                            )
                        else:
                            if (
                                isinstance(content_block.content, BetaCodeExecutionResultBlock)
                                and content_block.content.stdout
                            ):
                                code_outputs.append(
                                    Content.from_text(
                                        text=content_block.content.stdout,
                                        raw_representation=content_block.content,
                                    )
                                )
                            if (
                                isinstance(content_block.content, BetaEncryptedCodeExecutionResultBlock)
                                and content_block.content.encrypted_stdout
                            ):
                                code_outputs.append(
                                    Content.from_text(
                                        text=content_block.content.encrypted_stdout,
                                        raw_representation=content_block.content,
                                    )
                                )
                            if content_block.content.stderr:
                                code_outputs.append(
                                    Content.from_error(
                                        message=content_block.content.stderr,
                                        raw_representation=content_block.content,
                                    )
                                )
                            for code_file_content in content_block.content.content:
                                code_outputs.append(
                                    Content.from_hosted_file(
                                        file_id=code_file_content.file_id,
                                        raw_representation=code_file_content,
                                    )
                                )
                    contents.append(
                        Content.from_code_interpreter_tool_result(
                            call_id=content_block.tool_use_id,
                            raw_representation=content_block,
                            outputs=code_outputs,
                        )
                    )
                case "bash_code_execution_tool_result":
                    bash_outputs: list[Content] = []
                    if content_block.content:
                        if isinstance(
                            content_block.content,
                            BetaBashCodeExecutionToolResultError,
                        ):
                            bash_outputs.append(
                                Content.from_error(
                                    message=content_block.content.error_code,
                                    raw_representation=content_block.content,
                                )
                            )
                        else:
                            if content_block.content.stdout:
                                bash_outputs.append(
                                    Content.from_text(
                                        text=content_block.content.stdout,
                                        raw_representation=content_block.content,
                                    )
                                )
                            if content_block.content.stderr:
                                bash_outputs.append(
                                    Content.from_error(
                                        message=content_block.content.stderr,
                                        raw_representation=content_block.content,
                                    )
                                )
                            for bash_file_content in content_block.content.content:
                                contents.append(
                                    Content.from_hosted_file(
                                        file_id=bash_file_content.file_id,
                                        raw_representation=bash_file_content,
                                    )
                                )
                    contents.append(
                        Content.from_function_result(
                            call_id=content_block.tool_use_id,
                            result=bash_outputs,
                            raw_representation=content_block,
                        )
                    )
                case "text_editor_code_execution_tool_result":
                    text_editor_outputs: list[Content] = []
                    match content_block.content.type:
                        case "text_editor_code_execution_tool_result_error":
                            text_editor_outputs.append(
                                Content.from_error(
                                    message=content_block.content.error_code
                                    and getattr(content_block.content, "error_message", ""),
                                    raw_representation=content_block.content,
                                )
                            )
                        case "text_editor_code_execution_view_result":
                            annotations = (
                                [
                                    Annotation(
                                        type="citation",
                                        raw_representation=content_block.content,
                                        annotated_regions=[
                                            TextSpanRegion(
                                                type="text_span",
                                                start_index=content_block.content.start_line,
                                                end_index=content_block.content.start_line
                                                + (content_block.content.num_lines or 0),
                                            )
                                        ],
                                    )
                                ]
                                if content_block.content.num_lines is not None
                                and content_block.content.start_line is not None
                                else None
                            )
                            text_editor_outputs.append(
                                Content.from_text(
                                    text=content_block.content.content,
                                    annotations=annotations,
                                    raw_representation=content_block.content,
                                )
                            )
                        case "text_editor_code_execution_str_replace_result":
                            old_annotation = (
                                Annotation(
                                    type="citation",
                                    raw_representation=content_block.content,
                                    annotated_regions=[
                                        TextSpanRegion(
                                            type="text_span",
                                            start_index=content_block.content.old_start or 0,
                                            end_index=(
                                                (content_block.content.old_start or 0)
                                                + (content_block.content.old_lines or 0)
                                            ),
                                        )
                                    ],
                                )
                                if content_block.content.old_lines is not None
                                and content_block.content.old_start is not None
                                else None
                            )
                            new_annotation = (
                                Annotation(
                                    type="citation",
                                    raw_representation=content_block.content,
                                    snippet="\n".join(content_block.content.lines)  # type: ignore[typeddict-item]
                                    if content_block.content.lines
                                    else None,
                                    annotated_regions=[
                                        TextSpanRegion(
                                            type="text_span",
                                            start_index=content_block.content.new_start or 0,
                                            end_index=(
                                                (content_block.content.new_start or 0)
                                                + (content_block.content.new_lines or 0)
                                            ),
                                        )
                                    ],
                                )
                                if content_block.content.new_lines is not None
                                and content_block.content.new_start is not None
                                else None
                            )
                            annotations = [ann for ann in [old_annotation, new_annotation] if ann is not None]

                            text_editor_outputs.append(
                                Content.from_text(
                                    text=(
                                        "\n".join(content_block.content.lines) if content_block.content.lines else ""
                                    ),
                                    annotations=annotations or None,
                                    raw_representation=content_block.content,
                                )
                            )
                        case "text_editor_code_execution_create_result":
                            text_editor_outputs.append(
                                Content.from_text(
                                    text=f"File update: {content_block.content.is_file_update}",
                                    raw_representation=content_block.content,
                                )
                            )
                    contents.append(
                        Content.from_function_result(
                            call_id=content_block.tool_use_id,
                            result=text_editor_outputs,
                            raw_representation=content_block,
                        )
                    )
                case "input_json_delta":
                    # Skip argument deltas for MCP tools — execution is handled server-side.
                    if self._last_call_content_type == "mcp_tool_use":
                        pass
                    else:
                        call_id = self._last_call_id_name[0] if self._last_call_id_name else ""
                        contents.append(
                            Content.from_function_call(
                                call_id=call_id,
                                name="",
                                arguments=content_block.partial_json,
                                raw_representation=content_block,
                            )
                        )
                case "thinking" | "thinking_delta":
                    contents.append(
                        Content.from_text_reasoning(
                            text=content_block.thinking,
                            protected_data=getattr(content_block, "signature", None),
                            raw_representation=content_block,
                        )
                    )
                case "signature_delta":
                    contents.append(
                        Content.from_text_reasoning(
                            text=None,
                            protected_data=content_block.signature,
                            raw_representation=content_block,
                        )
                    )
                case _:
                    logger.debug(f"Ignoring unsupported content type: {content_block.type} for now")
        return contents

    def _parse_citations_from_anthropic(
        self, content_block: BetaContentBlock | BetaRawContentBlockDelta | BetaTextBlock
    ) -> list[Annotation] | None:
        content_blocks = getattr(content_block, "citations", None)
        if not content_blocks:
            return None
        annotations: list[Annotation] = []
        for citation in content_blocks:
            cit = Annotation(type="citation", raw_representation=citation)
            match citation.type:
                case "char_location":
                    cit["title"] = citation.title
                    cit["snippet"] = citation.cited_text
                    if citation.file_id:
                        cit["file_id"] = citation.file_id
                    cit.setdefault("annotated_regions", [])
                    cit["annotated_regions"].append(  # type: ignore[attr-defined]
                        TextSpanRegion(
                            type="text_span",
                            start_index=citation.start_char_index,
                            end_index=citation.end_char_index,
                        )
                    )
                case "page_location":
                    cit["title"] = citation.document_title
                    cit["snippet"] = citation.cited_text
                    if citation.file_id:
                        cit["file_id"] = citation.file_id
                    cit.setdefault("annotated_regions", [])
                    cit["annotated_regions"].append(  # type: ignore[attr-defined]
                        TextSpanRegion(
                            type="text_span",
                            start_index=citation.start_page_number,
                            end_index=citation.end_page_number,
                        )
                    )
                case "content_block_location":
                    cit["title"] = citation.document_title
                    cit["snippet"] = citation.cited_text
                    if citation.file_id:
                        cit["file_id"] = citation.file_id
                    cit.setdefault("annotated_regions", [])
                    cit["annotated_regions"].append(  # type: ignore[attr-defined]
                        TextSpanRegion(
                            type="text_span",
                            start_index=citation.start_block_index,
                            end_index=citation.end_block_index,
                        )
                    )
                case "web_search_result_location":
                    cit["title"] = citation.title
                    cit["snippet"] = citation.cited_text
                    cit["url"] = citation.url
                case "search_result_location":
                    cit["title"] = citation.title
                    cit["snippet"] = citation.cited_text
                    cit["url"] = citation.source
                    cit.setdefault("annotated_regions", [])
                    cit["annotated_regions"].append(  # type: ignore[attr-defined]
                        TextSpanRegion(
                            type="text_span",
                            start_index=citation.start_block_index,
                            end_index=citation.end_block_index,
                        )
                    )
                case _:
                    logger.debug(f"Unknown citation type encountered: {citation.type}")
            annotations.append(cit)
        return annotations or None

    def service_url(self) -> str:
        """Get the service URL for the chat client.

        Returns:
            The service URL for the chat client, or None if not set.
        """
        return str(self.anthropic_client.base_url)
