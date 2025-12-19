# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterable, MutableMapping, MutableSequence, Sequence
from typing import Any, ClassVar
from uuid import uuid4

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
    FunctionResultContent,
    Role,
    TextContent,
    ToolProtocol,
    UsageContent,
    UsageDetails,
    get_logger,
    prepare_function_call_results,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError, ServiceInvalidResponseError
from agent_framework.observability import use_instrumentation
from boto3.session import Session as Boto3Session
from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from pydantic import SecretStr, ValidationError

logger = get_logger("agent_framework.bedrock")

DEFAULT_REGION = "us-east-1"
DEFAULT_MAX_TOKENS = 1024

ROLE_MAP: dict[Role, str] = {
    Role.USER: "user",
    Role.ASSISTANT: "assistant",
    Role.SYSTEM: "user",
    Role.TOOL: "user",
}

FINISH_REASON_MAP: dict[str, FinishReason] = {
    "end_turn": FinishReason.STOP,
    "stop_sequence": FinishReason.STOP,
    "max_tokens": FinishReason.LENGTH,
    "length": FinishReason.LENGTH,
    "content_filtered": FinishReason.CONTENT_FILTER,
    "tool_use": FinishReason.TOOL_CALLS,
}


class BedrockSettings(AFBaseSettings):
    """Bedrock configuration settings pulled from environment variables or .env files."""

    env_prefix: ClassVar[str] = "BEDROCK_"

    region: str = DEFAULT_REGION
    chat_model_id: str | None = None
    access_key: SecretStr | None = None
    secret_key: SecretStr | None = None
    session_token: SecretStr | None = None


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class BedrockChatClient(BaseChatClient):
    """Async chat client for Amazon Bedrock's Converse API."""

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
            env_file_path: Optional .env file path used by ``BedrockSettings`` to load defaults.
            env_file_encoding: Encoding for the optional .env file.
            kwargs: Additional arguments forwarded to ``BaseChatClient``.
        """
        try:
            settings = BedrockSettings(
                region=region,
                chat_model_id=model_id,
                access_key=access_key,  # type: ignore[arg-type]
                secret_key=secret_key,  # type: ignore[arg-type]
                session_token=session_token,  # type: ignore[arg-type]
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to initialize Bedrock settings.", ex) from ex

        if client is None:
            session = boto3_session or self._create_session(settings)
            client = session.client(
                "bedrock-runtime",
                region_name=settings.region,
                config=BotoConfig(user_agent_extra=AGENT_FRAMEWORK_USER_AGENT),
            )

        super().__init__(**kwargs)
        self._bedrock_client = client
        self.model_id = settings.chat_model_id
        self.region = settings.region

    @staticmethod
    def _create_session(settings: BedrockSettings) -> Boto3Session:
        session_kwargs: dict[str, Any] = {"region_name": settings.region or DEFAULT_REGION}
        if settings.access_key and settings.secret_key:
            session_kwargs["aws_access_key_id"] = settings.access_key.get_secret_value()
            session_kwargs["aws_secret_access_key"] = settings.secret_key.get_secret_value()
        if settings.session_token:
            session_kwargs["aws_session_token"] = settings.session_token.get_secret_value()
        return Boto3Session(**session_kwargs)

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        request = self._build_converse_request(messages, chat_options, **kwargs)
        raw_response = await asyncio.to_thread(self._bedrock_client.converse, **request)
        return self._process_converse_response(raw_response)

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        response = await self._inner_get_response(messages=messages, chat_options=chat_options, **kwargs)
        contents = list(response.messages[0].contents if response.messages else [])
        if response.usage_details:
            contents.append(UsageContent(details=response.usage_details))
        yield ChatResponseUpdate(
            response_id=response.response_id,
            contents=contents,
            model_id=response.model_id,
            finish_reason=response.finish_reason,
            raw_representation=response.raw_representation,
        )

    def _build_converse_request(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> dict[str, Any]:
        model_id = chat_options.model_id or self.model_id
        if not model_id:
            raise ServiceInitializationError(
                "Bedrock model_id is required. Set via chat options or BEDROCK_CHAT_MODEL_ID environment variable."
            )

        system_prompts, conversation = self._prepare_bedrock_messages(messages)
        if not conversation:
            raise ServiceInitializationError("At least one non-system message is required for Bedrock requests.")

        payload: dict[str, Any] = {
            "modelId": model_id,
            "messages": conversation,
        }
        if system_prompts:
            payload["system"] = system_prompts

        inference_config: dict[str, Any] = {}
        inference_config["maxTokens"] = (
            chat_options.max_tokens if chat_options.max_tokens is not None else DEFAULT_MAX_TOKENS
        )
        if chat_options.temperature is not None:
            inference_config["temperature"] = chat_options.temperature
        if chat_options.top_p is not None:
            inference_config["topP"] = chat_options.top_p
        if chat_options.stop is not None:
            inference_config["stopSequences"] = chat_options.stop
        if inference_config:
            payload["inferenceConfig"] = inference_config

        tool_config = self._convert_tools_to_bedrock_config(chat_options.tools)
        if tool_choice := self._convert_tool_choice(chat_options.tool_choice):
            if tool_config is None:
                tool_config = {}
            tool_config["toolChoice"] = tool_choice
        if tool_config:
            payload["toolConfig"] = tool_config

        if chat_options.additional_properties:
            payload.update(chat_options.additional_properties)
        if kwargs:
            payload.update(kwargs)
        return payload

    def _prepare_bedrock_messages(
        self, messages: Sequence[ChatMessage]
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        prompts: list[dict[str, str]] = []
        conversation: list[dict[str, Any]] = []
        pending_tool_use_ids: deque[str] = deque()
        for message in messages:
            if message.role == Role.SYSTEM:
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
            elif message.role == Role.TOOL:
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

    def _convert_message_to_content_blocks(self, message: ChatMessage) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for content in message.contents:
            block = self._convert_content_to_bedrock_block(content)
            if block is None:
                logger.debug("Skipping unsupported content type for Bedrock: %s", type(content))
                continue
            blocks.append(block)
        return blocks

    def _convert_content_to_bedrock_block(self, content: Contents) -> dict[str, Any] | None:
        if isinstance(content, TextContent):
            return {"text": content.text}
        if isinstance(content, FunctionCallContent):
            arguments = content.parse_arguments() or {}
            return {
                "toolUse": {
                    "toolUseId": content.call_id or self._generate_tool_call_id(),
                    "name": content.name,
                    "input": arguments,
                }
            }
        if isinstance(content, FunctionResultContent):
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
        return None

    def _convert_tool_result_to_blocks(self, result: Any) -> list[dict[str, Any]]:
        prepared_result = prepare_function_call_results(result)
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
        if isinstance(value, TextContent) and getattr(value, "text", None):
            return {"text": value.text}
        if hasattr(value, "to_dict"):
            try:
                return {"json": value.to_dict()}  # type: ignore[call-arg]
            except Exception:  # pragma: no cover - defensive
                return {"text": str(value)}
        return {"text": str(value)}

    def _convert_tools_to_bedrock_config(
        self, tools: list[ToolProtocol | MutableMapping[str, Any]] | None
    ) -> dict[str, Any] | None:
        if not tools:
            return None
        converted: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, MutableMapping):
                converted.append(dict(tool))
                continue
            if isinstance(tool, AIFunction):
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

    def _convert_tool_choice(self, tool_choice: Any) -> dict[str, Any] | None:
        if not tool_choice:
            return None
        mode = tool_choice.mode if hasattr(tool_choice, "mode") else str(tool_choice)
        required_name = getattr(tool_choice, "required_function_name", None)
        match mode:
            case "auto":
                return {"auto": {}}
            case "none":
                return {"none": {}}
            case "required":
                if required_name:
                    return {"tool": {"name": required_name}}
                return {"any": {}}
            case _:
                logger.debug("Unsupported tool choice mode for Bedrock: %s", mode)
                return None

    @staticmethod
    def _generate_tool_call_id() -> str:
        return f"tool-call-{uuid4().hex}"

    def _process_converse_response(self, response: dict[str, Any]) -> ChatResponse:
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", []) or []
        contents = self._parse_message_contents(content_blocks)
        chat_message = ChatMessage(role=Role.ASSISTANT, contents=contents, raw_representation=message)
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
        details = UsageDetails()
        if (input_tokens := usage.get("inputTokens")) is not None:
            details.input_token_count = input_tokens
        if (output_tokens := usage.get("outputTokens")) is not None:
            details.output_token_count = output_tokens
        if (total_tokens := usage.get("totalTokens")) is not None:
            details.additional_counts["bedrock.total_tokens"] = total_tokens
        return details

    def _parse_message_contents(self, content_blocks: Sequence[MutableMapping[str, Any]]) -> list[Any]:
        contents: list[Any] = []
        for block in content_blocks:
            if text_value := block.get("text"):
                contents.append(TextContent(text=text_value, raw_representation=block))
                continue
            if (json_value := block.get("json")) is not None:
                contents.append(TextContent(text=json.dumps(json_value), raw_representation=block))
                continue
            tool_use = block.get("toolUse")
            if isinstance(tool_use, MutableMapping):
                tool_name = tool_use.get("name")
                if not tool_name:
                    raise ServiceInvalidResponseError("Bedrock response missing required tool name in toolUse block.")
                contents.append(
                    FunctionCallContent(
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
                    FunctionResultContent(
                        call_id=tool_result.get("toolUseId") or self._generate_tool_call_id(),
                        result=result_value,
                        exception=exception,
                        raw_representation=block,
                    )
                )
                continue
            logger.debug("Ignoring unsupported Bedrock content block: %s", block)
        return contents

    def _map_finish_reason(self, reason: str | None) -> FinishReason | None:
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
