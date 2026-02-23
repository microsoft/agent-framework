# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections import deque
from collections.abc import AsyncIterable, Awaitable, Mapping, MutableMapping, Sequence
from typing import Any, ClassVar, Generic, Literal, TypedDict
from uuid import uuid4

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
    validate_tool_mode,
)
from agent_framework._settings import SecretString, load_settings
from agent_framework.exceptions import ChatClientInvalidResponseException
from agent_framework.observability import ChatTelemetryLayer
from boto3.session import Session as Boto3Session
from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from pydantic import BaseModel

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

logger = logging.getLogger("agent_framework.bedrock")


__all__ = [
    "BedrockChatClient",
    "BedrockChatOptions",
    "BedrockGuardrailConfig",
    "BedrockSettings",
]

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel | None, default=None)


# region Bedrock Chat Options TypedDict


DEFAULT_REGION = "us-east-1"
DEFAULT_MAX_TOKENS = 1024


class BedrockGuardrailConfig(TypedDict, total=False):
    """Amazon Bedrock Guardrails configuration.

    See: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html
    """

    guardrailIdentifier: str
    """The identifier of the guardrail to apply."""

    guardrailVersion: str
    """The version of the guardrail to use."""

    trace: Literal["enabled", "disabled"]
    """Whether to include guardrail trace information in the response."""

    streamProcessingMode: Literal["sync", "async"]
    """How to process guardrails during streaming (sync blocks, async does not)."""


class BedrockChatOptions(ChatOptions[ResponseModelT], Generic[ResponseModelT], total=False):
    """Amazon Bedrock Converse API-specific chat options dict.

    Extends base ChatOptions with Bedrock-specific parameters.
    Bedrock uses a unified Converse API that works across multiple
    foundation models (Claude, Titan, Llama, etc.).

    See: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html

    Keys:
        # Inherited from ChatOptions (mapped to Bedrock):
        model_id: The Bedrock model identifier,
            translates to ``modelId`` in Bedrock API.
        temperature: Sampling temperature,
            translates to ``inferenceConfig.temperature``.
        top_p: Nucleus sampling parameter,
            translates to ``inferenceConfig.topP``.
        max_tokens: Maximum number of tokens to generate,
            translates to ``inferenceConfig.maxTokens``.
        stop: Stop sequences,
            translates to ``inferenceConfig.stopSequences``.
        tools: List of tools available to the model,
            translates to ``toolConfig.tools``.
        tool_choice: How the model should use tools,
            translates to ``toolConfig.toolChoice``.

        # Options not supported in Bedrock Converse API:
        seed: Not supported.
        frequency_penalty: Not supported.
        presence_penalty: Not supported.
        allow_multiple_tool_calls: Not supported (models handle parallel calls automatically).
        response_format: Not directly supported (use model-specific prompting).
        user: Not supported.
        store: Not supported.
        logit_bias: Not supported.
        metadata: Not supported (use additional_properties for additionalModelRequestFields).

        # Bedrock-specific options:
        guardrailConfig: Guardrails configuration for content filtering.
        performanceConfig: Performance optimization settings.
        requestMetadata: Key-value metadata for the request.
        promptVariables: Variables for prompt management (if using managed prompts).
    """

    # Bedrock-specific options
    guardrailConfig: BedrockGuardrailConfig
    """Guardrails configuration for content filtering and safety."""

    performanceConfig: dict[str, Any]
    """Performance optimization settings (e.g., latency optimization).
    See: https://docs.aws.amazon.com/bedrock/latest/userguide/inference-performance.html"""

    requestMetadata: dict[str, str]
    """Key-value metadata for the request (max 2048 characters total)."""

    promptVariables: dict[str, dict[str, str]]
    """Variables for prompt management when using managed prompts."""

    # ChatOptions fields not supported in Bedrock
    seed: None  # type: ignore[misc]
    """Not supported in Bedrock Converse API."""

    frequency_penalty: None  # type: ignore[misc]
    """Not supported in Bedrock Converse API."""

    presence_penalty: None  # type: ignore[misc]
    """Not supported in Bedrock Converse API."""

    allow_multiple_tool_calls: None  # type: ignore[misc]
    """Not supported. Bedrock models handle parallel tool calls automatically."""

    response_format: None  # type: ignore[misc]
    """Not directly supported. Use model-specific prompting for JSON output."""

    user: None  # type: ignore[misc]
    """Not supported in Bedrock Converse API."""

    store: None  # type: ignore[misc]
    """Not supported in Bedrock Converse API."""

    logit_bias: None  # type: ignore[misc]
    """Not supported in Bedrock Converse API."""


BEDROCK_OPTION_TRANSLATIONS: dict[str, str] = {
    "model_id": "modelId",
    "max_tokens": "maxTokens",
    "top_p": "topP",
    "stop": "stopSequences",
}
"""Maps ChatOptions keys to Bedrock Converse API parameter names."""

BedrockChatOptionsT = TypeVar("BedrockChatOptionsT", bound=TypedDict, default="BedrockChatOptions", covariant=True)  # type: ignore[valid-type]


# endregion


ROLE_MAP: dict[str, str] = {
    "user": "user",
    "assistant": "assistant",
    "system": "user",
    "tool": "user",
}

FINISH_REASON_MAP: dict[str, FinishReasonLiteral] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "length": "length",
    "content_filtered": "content_filter",
    "tool_use": "tool_calls",
}


class BedrockSettings(TypedDict, total=False):
    """Bedrock configuration settings pulled from environment variables or .env files."""

    region: str | None
    chat_model_id: str | None
    access_key: SecretString | None
    secret_key: SecretString | None
    session_token: SecretString | None


class BedrockChatClient(
    ChatMiddlewareLayer[BedrockChatOptionsT],
    FunctionInvocationLayer[BedrockChatOptionsT],
    ChatTelemetryLayer[BedrockChatOptionsT],
    BaseChatClient[BedrockChatOptionsT],
    Generic[BedrockChatOptionsT],
):
    """Async chat client for Amazon Bedrock's Converse API with middleware, telemetry, and function invocation."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "aws.bedrock"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        region: str | None = None,
        model_id: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        session_token: str | None = None,
        client: BaseClient | None = None,
        boto3_session: Boto3Session | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Create a Bedrock chat client and load AWS credentials.

        Args:
            region: Region to send Bedrock requests to; falls back to BEDROCK_REGION.
            model_id: Default model identifier; falls back to BEDROCK_CHAT_MODEL_ID.
            access_key: Optional AWS access key for manual credential injection.
            secret_key: Optional AWS secret key paired with ``access_key``.
            session_token: Optional AWS session token for temporary credentials.
            client: Preconfigured Bedrock runtime client; when omitted a boto3 session is created.
            boto3_session: Custom boto3 session used to build the runtime client if provided.
            middleware: Optional sequence of middlewares to include.
            function_invocation_configuration: Optional function invocation configuration
            env_file_path: Optional .env file path used by ``BedrockSettings`` to load defaults.
            env_file_encoding: Encoding for the optional .env file.
            kwargs: Additional arguments forwarded to ``BaseChatClient``.

        Examples:
            .. code-block:: python

                from agent_framework.amazon import BedrockChatClient

                # Basic usage with default credentials
                client = BedrockChatClient(model_id="<model name>")

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework_bedrock import BedrockChatOptions


                class MyOptions(BedrockChatOptions, total=False):
                    my_custom_option: str


                client = BedrockChatClient[MyOptions](model_id="<model name>")
                response = await client.get_response("Hello", options={"my_custom_option": "value"})
        """
        settings = load_settings(
            BedrockSettings,
            env_prefix="BEDROCK_",
            region=region,
            chat_model_id=model_id,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        if not settings.get("region"):
            settings["region"] = DEFAULT_REGION

        if client is None:
            session = boto3_session or self._create_session(settings)
            client = session.client(
                "bedrock-runtime",
                region_name=settings["region"],
                config=BotoConfig(user_agent_extra=AGENT_FRAMEWORK_USER_AGENT),
            )

        super().__init__(
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            **kwargs,
        )
        self._bedrock_client = client
        self.model_id = settings["chat_model_id"]
        self.region = settings["region"]

    @staticmethod
    def _create_session(settings: BedrockSettings) -> Boto3Session:
        session_kwargs: dict[str, Any] = {"region_name": settings.get("region") or DEFAULT_REGION}
        if settings.get("access_key") and settings.get("secret_key"):
            session_kwargs["aws_access_key_id"] = settings["access_key"].get_secret_value()  # type: ignore[union-attr]
            session_kwargs["aws_secret_access_key"] = settings["secret_key"].get_secret_value()  # type: ignore[union-attr]
        if settings.get("session_token"):
            session_kwargs["aws_session_token"] = settings["session_token"].get_secret_value()  # type: ignore[union-attr]
        return Boto3Session(**session_kwargs)

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        request = self._prepare_options(messages, options, **kwargs)

        if stream:
            # Streaming mode - simulate streaming by yielding a single update
            async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                response = await asyncio.to_thread(self._bedrock_client.converse, **request)
                parsed_response = self._process_converse_response(response)
                contents = list(parsed_response.messages[0].contents if parsed_response.messages else [])
                if parsed_response.usage_details:
                    contents.append(Content.from_usage(usage_details=parsed_response.usage_details))  # type: ignore[arg-type]
                yield ChatResponseUpdate(
                    response_id=parsed_response.response_id,
                    contents=contents,
                    model_id=parsed_response.model_id,
                    finish_reason=parsed_response.finish_reason,
                    raw_representation=parsed_response.raw_representation,
                )

            return self._build_response_stream(_stream())

        # Non-streaming mode
        async def _get_response() -> ChatResponse:
            raw_response = await asyncio.to_thread(self._bedrock_client.converse, **request)
            return self._process_converse_response(raw_response)

        return _get_response()

    def _prepare_options(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        model_id = options.get("model_id") or self.model_id
        if not model_id:
            raise ValueError(
                "Bedrock model_id is required. Set via chat options or BEDROCK_CHAT_MODEL_ID environment variable."
            )

        system_prompts, conversation = self._prepare_bedrock_messages(messages)
        if not conversation:
            raise ValueError("At least one non-system message is required for Bedrock requests.")
        # Prepend instructions from options if they exist
        if instructions := options.get("instructions"):
            system_prompts = [{"text": instructions}, *system_prompts]

        run_options: dict[str, Any] = {
            "modelId": model_id,
            "messages": conversation,
            "inferenceConfig": {"maxTokens": options.get("max_tokens", DEFAULT_MAX_TOKENS)},
        }
        if system_prompts:
            run_options["system"] = system_prompts

        if (temperature := options.get("temperature")) is not None:
            run_options["inferenceConfig"]["temperature"] = temperature
        if (top_p := options.get("top_p")) is not None:
            run_options["inferenceConfig"]["topP"] = top_p
        if (stop := options.get("stop")) is not None:
            run_options["inferenceConfig"]["stopSequences"] = stop

        tool_config = self._prepare_tools(options.get("tools"))
        if tool_mode := validate_tool_mode(options.get("tool_choice")):
            tool_config = tool_config or {}
            match tool_mode.get("mode"):
                case "auto" | "none":
                    tool_config["toolChoice"] = {tool_mode.get("mode"): {}}
                case "required":
                    if required_name := tool_mode.get("required_function_name"):
                        tool_config["toolChoice"] = {"tool": {"name": required_name}}
                    else:
                        tool_config["toolChoice"] = {"any": {}}
                case _:
                    raise ValueError(f"Unsupported tool mode for Bedrock: {tool_mode.get('mode')}")
        if tool_config:
            run_options["toolConfig"] = tool_config

        return run_options

    def _prepare_bedrock_messages(
        self, messages: Sequence[Message]
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        prompts: list[dict[str, str]] = []
        conversation: list[dict[str, Any]] = []
        pending_tool_use_ids: deque[str] = deque()
        for message in messages:
            if message.role == "system":
                text_value = message.text
                if text_value:
                    prompts.append({"text": text_value})
                continue

            content_blocks = self._convert_message_to_content_blocks(message)
            if not content_blocks:
                continue

            role = ROLE_MAP.get(message.role, "user")
            if role == "assistant":
                pending_tool_use_ids = deque(
                    block["toolUse"]["toolUseId"]
                    for block in content_blocks
                    if isinstance(block, MutableMapping) and "toolUse" in block
                )
            elif message.role == "tool":
                content_blocks = self._align_tool_results_with_pending(content_blocks, pending_tool_use_ids)
                pending_tool_use_ids.clear()
                if not content_blocks:
                    continue
            else:
                pending_tool_use_ids.clear()

            conversation.append({"role": role, "content": content_blocks})

        return prompts, conversation

    def _align_tool_results_with_pending(
        self, content_blocks: list[dict[str, Any]], pending_tool_use_ids: deque[str]
    ) -> list[dict[str, Any]]:
        if not content_blocks:
            return content_blocks
        if not pending_tool_use_ids:
            # No pending tool calls; drop toolResult blocks to avoid Bedrock validation errors
            return [
                block for block in content_blocks if not (isinstance(block, MutableMapping) and "toolResult" in block)
            ]

        aligned_blocks: list[dict[str, Any]] = []
        pending = deque(pending_tool_use_ids)
        for block in content_blocks:
            if not isinstance(block, MutableMapping):
                aligned_blocks.append(block)
                continue
            tool_result = block.get("toolResult")
            if not tool_result:
                aligned_blocks.append(block)
                continue
            if not pending:
                logger.debug("Dropping extra tool result block due to missing pending tool uses: %s", block)
                continue
            tool_use_id = tool_result.get("toolUseId")
            if tool_use_id:
                try:
                    pending.remove(tool_use_id)
                except ValueError:
                    logger.debug("Tool result references unknown toolUseId '%s'. Dropping block.", tool_use_id)
                    continue
            else:
                tool_result["toolUseId"] = pending.popleft()
            aligned_blocks.append(block)

        return aligned_blocks

    def _convert_message_to_content_blocks(self, message: Message) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for content in message.contents:
            block = self._convert_content_to_bedrock_block(content)
            if block is None:
                logger.debug("Skipping unsupported content type for Bedrock: %s", type(content))
                continue
            blocks.append(block)
        return blocks

    def _convert_content_to_bedrock_block(self, content: Content) -> dict[str, Any] | None:
        match content.type:
            case "text":
                return {"text": content.text}
            case "function_call":
                arguments = content.parse_arguments() or {}
                return {
                    "toolUse": {
                        "toolUseId": content.call_id or self._generate_tool_call_id(),
                        "name": content.name,
                        "input": arguments,
                    }
                }
            case "function_result":
                tool_result_block = {
                    "toolResult": {
                        "toolUseId": content.call_id,
                        "content": self._convert_tool_result_to_blocks(content.result),
                        "status": "error" if content.exception else "success",
                    }
                }
                if content.exception:
                    tool_result = tool_result_block["toolResult"]
                    existing_content = tool_result.get("content")
                    content_list: list[dict[str, Any]]
                    if isinstance(existing_content, list):
                        content_list = existing_content
                    else:
                        content_list = []
                        tool_result["content"] = content_list
                    content_list.append({"text": str(content.exception)})
                return tool_result_block
            case _:
                # Bedrock does not support other content types at this time
                pass
        return None

    def _convert_tool_result_to_blocks(self, result: Any) -> list[dict[str, Any]]:
        prepared_result = result if isinstance(result, str) else FunctionTool.parse_result(result)
        try:
            parsed_result = json.loads(prepared_result)
        except json.JSONDecodeError:
            return [{"text": prepared_result}]

        return self._convert_prepared_tool_result_to_blocks(parsed_result)

    def _convert_prepared_tool_result_to_blocks(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            blocks: list[dict[str, Any]] = []
            for item in value:
                blocks.extend(self._convert_prepared_tool_result_to_blocks(item))
            return blocks or [{"text": ""}]
        return [self._normalize_tool_result_value(value)]

    def _normalize_tool_result_value(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {"json": value}
        if isinstance(value, (list, tuple)):
            return {"json": list(value)}
        if isinstance(value, str):
            return {"text": value}
        if isinstance(value, (int, float, bool)) or value is None:
            return {"json": value}
        if isinstance(value, Content) and value.type == "text":
            return {"text": value.text}
        if hasattr(value, "to_dict"):
            try:
                return {"json": value.to_dict()}  # type: ignore[call-arg]
            except Exception:  # pragma: no cover - defensive
                return {"text": str(value)}
        return {"text": str(value)}

    def _prepare_tools(self, tools: list[FunctionTool | MutableMapping[str, Any]] | None) -> dict[str, Any] | None:
        converted: list[dict[str, Any]] = []
        if not tools:
            return None
        for tool in tools:
            if isinstance(tool, MutableMapping):
                converted.append(dict(tool))
                continue
            if isinstance(tool, FunctionTool):
                converted.append({
                    "toolSpec": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": {"json": tool.parameters()},
                    }
                })
                continue
            logger.debug("Ignoring unsupported tool type for Bedrock: %s", type(tool))
        return {"tools": converted} if converted else None

    @staticmethod
    def _generate_tool_call_id() -> str:
        return f"tool-call-{uuid4().hex}"

    def _process_converse_response(self, response: dict[str, Any]) -> ChatResponse:
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", []) or []
        contents = self._parse_message_contents(content_blocks)
        chat_message = Message(role="assistant", contents=contents, raw_representation=message)
        usage_details = self._parse_usage(response.get("usage") or output.get("usage"))
        finish_reason = self._map_finish_reason(output.get("completionReason") or response.get("stopReason"))
        response_id = response.get("responseId") or message.get("id")
        model_id = response.get("modelId") or output.get("modelId") or self.model_id
        return ChatResponse(
            response_id=response_id,
            messages=[chat_message],
            usage_details=usage_details,
            model_id=model_id,
            finish_reason=finish_reason,
            raw_representation=response,
        )

    def _parse_usage(self, usage: dict[str, Any] | None) -> UsageDetails | None:
        if not usage:
            return None
        details: UsageDetails = {}
        if (input_tokens := usage.get("inputTokens")) is not None:
            details["input_token_count"] = input_tokens
        if (output_tokens := usage.get("outputTokens")) is not None:
            details["output_token_count"] = output_tokens
        if (total_tokens := usage.get("totalTokens")) is not None:
            details["total_token_count"] = total_tokens
        return details

    def _parse_message_contents(self, content_blocks: Sequence[MutableMapping[str, Any]]) -> list[Any]:
        contents: list[Any] = []
        for block in content_blocks:
            if text_value := block.get("text"):
                contents.append(Content.from_text(text=text_value, raw_representation=block))
                continue
            if (json_value := block.get("json")) is not None:
                contents.append(Content.from_text(text=json.dumps(json_value), raw_representation=block))
                continue
            tool_use = block.get("toolUse")
            if isinstance(tool_use, MutableMapping):
                tool_name = tool_use.get("name")
                if not tool_name:
                    raise ChatClientInvalidResponseException(
                        "Bedrock response missing required tool name in toolUse block."
                    )
                contents.append(
                    Content.from_function_call(
                        call_id=tool_use.get("toolUseId") or self._generate_tool_call_id(),
                        name=tool_name,
                        arguments=tool_use.get("input"),
                        raw_representation=block,
                    )
                )
                continue
            tool_result = block.get("toolResult")
            if isinstance(tool_result, MutableMapping):
                status = (tool_result.get("status") or "success").lower()
                exception = None
                if status not in {"success", "ok"}:
                    exception = RuntimeError(f"Bedrock tool result status: {status}")
                result_value = self._convert_bedrock_tool_result_to_value(tool_result.get("content"))
                contents.append(
                    Content.from_function_result(
                        call_id=tool_result.get("toolUseId") or self._generate_tool_call_id(),
                        result=result_value,
                        exception=str(exception) if exception else None,  # type: ignore[arg-type]
                        raw_representation=block,
                    )
                )
                continue
            logger.debug("Ignoring unsupported Bedrock content block: %s", block)
        return contents

    def _map_finish_reason(self, reason: str | None) -> FinishReasonLiteral | None:
        if not reason:
            return None
        return FINISH_REASON_MAP.get(reason.lower())

    def service_url(self) -> str:
        """Returns the service URL for the Bedrock runtime in the configured AWS region.

        Returns:
            str: The Bedrock runtime service URL.
        """
        return f"https://bedrock-runtime.{self.region}.amazonaws.com"

    def _convert_bedrock_tool_result_to_value(self, content: Any) -> Any:
        if not content:
            return None
        if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
            values: list[Any] = []
            for item in content:
                if isinstance(item, MutableMapping):
                    if (text_value := item.get("text")) is not None:
                        values.append(text_value)
                        continue
                    if "json" in item:
                        values.append(item["json"])
                        continue
                values.append(item)
            return values[0] if len(values) == 1 else values
        if isinstance(content, MutableMapping):
            if (text_value := content.get("text")) is not None:
                return text_value
            if "json" in content:
                return content["json"]
        return content
