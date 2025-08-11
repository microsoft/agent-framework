# Copyright (c) Microsoft. All rights reserved.

import functools
import json
import logging
import os
from collections.abc import AsyncIterable, Awaitable, Callable, MutableSequence
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, Final, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode, get_tracer, use_span

from . import __version__ as version_info
from ._logging import get_logger
from ._pydantic import AFBaseSettings

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry.util._decorator import _AgnosticContextManager  # type: ignore[reportPrivateUsage]

    from ._agents import AgentThread, AIAgent, ChatClientAgent
    from ._clients import ChatClientBase
    from ._tools import AIFunction
    from ._types import (
        AgentRunResponse,
        AgentRunResponseUpdate,
        ChatMessage,
        ChatOptions,
        ChatResponse,
        ChatResponseUpdate,
    )

TChatClientBase = TypeVar("TChatClientBase", bound="ChatClientBase")
TChatClientAgent = TypeVar("TChatClientAgent", bound="ChatClientAgent")

tracer = get_tracer("agent_framework")
logger = get_logger()

__all__ = [
    "AGENT_FRAMEWORK_USER_AGENT",
    "APP_INFO",
    "USER_AGENT_KEY",
    "prepend_agent_framework_to_user_agent",
    "use_agent_telemetry",
    "use_telemetry",
]


# We're recording multiple events for the chat history, some of them are emitted within (hundreds of)
# nanoseconds of each other. The default timestamp resolution is not high enough to guarantee unique
# timestamps for each message. Also Azure Monitor truncates resolution to microseconds and some other
# backends truncate to milliseconds.
#
# But we need to give users a way to restore chat message order, so we're incrementing the timestamp
# by 1 microsecond for each message.
#
# This is a workaround, we'll find a generic and better solution - see
# https://github.com/open-telemetry/semantic-conventions/issues/1701
class ChatMessageListTimestampFilter(logging.Filter):
    """A filter to increment the timestamp of INFO logs by 1 microsecond."""

    INDEX_KEY: ClassVar[str] = "CHAT_MESSAGE_INDEX"

    def filter(self, record: logging.LogRecord) -> bool:
        """Increment the timestamp of INFO logs by 1 microsecond."""
        if hasattr(record, self.INDEX_KEY):
            idx = getattr(record, self.INDEX_KEY)
            record.created += idx * 1e-6
        return True


# Creates a tracer from the global tracer provider
logger.addFilter(ChatMessageListTimestampFilter())


class GenAIAttributes(str, Enum):
    """Enum to capture the attributes used in OpenTelemetry for Generative AI.

    Based on: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/
    and https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/

    Should always be used, with `.value` to get the string representation.
    """

    OPERATION = "gen_ai.operation.name"
    SYSTEM = "gen_ai.system"
    ERROR_TYPE = "error.type"
    PORT = "server.port"
    ADDRESS = "server.address"
    SPAN_ID = "SpanId"
    TRACE_ID = "TraceId"
    # Request attributes
    MODEL = "gen_ai.request.model"
    SEED = "gen_ai.request.seed"
    ENCODING_FORMATS = "gen_ai.request.encoding_formats"
    FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
    MAX_TOKENS = "gen_ai.request.max_tokens"
    PRESENCE_PENALTY = "gen_ai.request.presence_penalty"
    STOP_SEQUENCES = "gen_ai.request.stop_sequences"
    TEMPERATURE = "gen_ai.request.temperature"
    TOP_K = "gen_ai.request.top_k"
    TOP_P = "gen_ai.request.top_p"
    CHOICE_COUNT = "gen_ai.request.choice.count"
    # Response attributes
    FINISH_REASONS = "gen_ai.response.finish_reasons"
    RESPONSE_ID = "gen_ai.response.id"
    RESPONSE_MODEL = "gen_ai.response.model"
    # Usage attributes
    INPUT_TOKENS = "gen_ai.usage.input_tokens"
    OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
    # Tool attributes
    TOOL_CALL_ID = "gen_ai.tool.call.id"
    TOOL_DESCRIPTION = "gen_ai.tool.description"
    TOOL_NAME = "gen_ai.tool.name"
    AGENT_ID = "gen_ai.agent.id"
    # Agent attributes
    AGENT_NAME = "gen_ai.agent.name"
    AGENT_DESCRIPTION = "gen_ai.agent.description"
    CONVERSATION_ID = "gen_ai.conversation.id"
    DATA_SOURCE_ID = "gen_ai.data_source.id"
    OUTPUT_TYPE = "gen_ai.output.type"

    # Activity events
    EVENT_NAME = "event.name"
    SYSTEM_MESSAGE = "gen_ai.system.message"
    USER_MESSAGE = "gen_ai.user.message"
    ASSISTANT_MESSAGE = "gen_ai.assistant.message"
    TOOL_MESSAGE = "gen_ai.tool.message"
    CHOICE = "gen_ai.choice"
    PROMPT = "gen_ai.prompt"

    # Operation names
    CHAT_COMPLETION_OPERATION = "chat"
    TOOL_EXECUTION_OPERATION = "execute_tool"
    #    Describes GenAI agent creation and is usually applicable when working with remote agent services.
    AGENT_CREATE_OPERATION = "create_agent"
    AGENT_INVOKE_OPERATION = "invoke_agent"

    # Agent Framework specific attributes
    MEASUREMENT_FUNCTION_TAG_NAME = "agent_framework.function.name"
    MEASUREMENT_FUNCTION_INVOCATION_DURATION = "agent_framework.function.invocation.duration"
    AGENT_FRAMEWORK_GEN_AI_SYSTEM = "microsoft.agent_framework"


ROLE_EVENT_MAP = {
    "system": GenAIAttributes.SYSTEM_MESSAGE.value,
    "user": GenAIAttributes.USER_MESSAGE.value,
    "assistant": GenAIAttributes.ASSISTANT_MESSAGE.value,
    "tool": GenAIAttributes.TOOL_MESSAGE.value,
}
# Note that if this environment variable does not exist, telemetry is enabled.
TELEMETRY_DISABLED_ENV_VAR = "AZURE_TELEMETRY_DISABLED"
IS_TELEMETRY_ENABLED = os.environ.get(TELEMETRY_DISABLED_ENV_VAR, "false").lower() not in ["true", "1"]

APP_INFO = (
    {
        "agent-framework-version": f"python/{version_info}",  # type: ignore[has-type]
    }
    if IS_TELEMETRY_ENABLED
    else None
)
USER_AGENT_KEY: Final[str] = "User-Agent"
HTTP_USER_AGENT: Final[str] = "agent-framework-python"
AGENT_FRAMEWORK_USER_AGENT = f"{HTTP_USER_AGENT}/{version_info}"  # type: ignore[has-type]


def prepend_agent_framework_to_user_agent(headers: dict[str, Any]) -> dict[str, Any]:
    """Prepend "agent-framework" to the User-Agent in the headers.

    Args:
        headers: The existing headers dictionary.

    Returns:
        The modified headers dictionary with "agent-framework-python/{version}" prepended to the User-Agent.
    """
    headers[USER_AGENT_KEY] = (
        f"{AGENT_FRAMEWORK_USER_AGENT} {headers[USER_AGENT_KEY]}"
        if USER_AGENT_KEY in headers
        else AGENT_FRAMEWORK_USER_AGENT
    )

    return headers


# region Telemetry utils


class ModelDiagnosticSettings(AFBaseSettings):
    """Settings for model diagnostics.

    The settings are first loaded from environment variables with
    the prefix 'AGENT_FRAMEWORK_GENAI_'.
    If the environment variables are not found, the settings can
    be loaded from a .env file with the encoding 'utf-8'.
    If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the
    settings are missing.

    Warning:
        Sensitive events should only be enabled on test and development environments.

    Required settings for prefix 'AGENT_FRAMEWORK_GENAI_' are:
    - enable_otel_diagnostics: bool - Enable OpenTelemetry diagnostics. Default is False.
                (Env var AGENT_FRAMEWORK_GENAI_ENABLE_OTEL_DIAGNOSTICS)
    - enable_otel_diagnostics_sensitive: bool - Enable OpenTelemetry sensitive events. Default is False.
                (Env var AGENT_FRAMEWORK_GENAI_ENABLE_OTEL_DIAGNOSTICS_SENSITIVE)
    """

    env_prefix: ClassVar[str] = "AGENT_FRAMEWORK_GENAI_"

    enable_otel_diagnostics: bool = False
    enable_otel_diagnostics_sensitive: bool = False

    @property
    def ENABLED(self) -> bool:
        """Check if model diagnostics are enabled.

        Model diagnostics are enabled if either diagnostic is enabled or diagnostic with sensitive events is enabled.
        """
        return self.enable_otel_diagnostics or self.enable_otel_diagnostics_sensitive

    @property
    def SENSITIVE_EVENTS_ENABLED(self) -> bool:
        """Check if sensitive events are enabled.

        Sensitive events are enabled if the diagnostic with sensitive events is enabled.
        """
        return self.enable_otel_diagnostics_sensitive


MODEL_DIAGNOSTICS_SETTINGS = ModelDiagnosticSettings()


def start_as_current_span(
    tracer: trace.Tracer,
    function: "AIFunction[Any, Any]",
    metadata: dict[str, Any] | None = None,
) -> "_AgnosticContextManager[Span]":
    """Starts a span for the given function using the provided tracer.

    Args:
        tracer: The OpenTelemetry tracer to use.
        function: The function for which to start the span.
        metadata: Optional metadata to include in the span attributes.

    Returns:
        trace.Span: The started span as a context manager.
    """
    attributes = {
        GenAIAttributes.OPERATION.value: GenAIAttributes.TOOL_EXECUTION_OPERATION.value,
        GenAIAttributes.TOOL_NAME.value: function.name,
    }

    tool_call_id = metadata.get("tool_call_id", None) if metadata else None
    if tool_call_id:
        attributes[GenAIAttributes.TOOL_CALL_ID.value] = tool_call_id
    if function.description:
        attributes[GenAIAttributes.TOOL_DESCRIPTION.value] = function.description

    return tracer.start_as_current_span(
        f"{GenAIAttributes.TOOL_EXECUTION_OPERATION.value} {function.name}", attributes=attributes
    )


def _set_error(span: Span, error: Exception) -> None:
    """Set an error for spans."""
    span.set_attribute(GenAIAttributes.ERROR_TYPE.value, str(type(error)))
    span.set_status(StatusCode.ERROR, repr(error))


# region ChatClient


def _trace_chat_get_response(
    completion_func: Callable[..., Awaitable["ChatResponse"]],
) -> Callable[..., Awaitable["ChatResponse"]]:
    """Decorator to trace chat completion activities.

    Args:
        completion_func: The function to trace.
    """

    @functools.wraps(completion_func)
    async def wrap_inner_get_response(
        self: "ChatClientBase",
        *,
        messages: MutableSequence["ChatMessage"],
        chat_options: "ChatOptions",
        **kwargs: Any,
    ) -> "ChatResponse":
        if not MODEL_DIAGNOSTICS_SETTINGS.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            return await completion_func(
                self,
                messages=messages,
                chat_options=chat_options,
                **kwargs,
            )

        with use_span(
            _get_chat_response_span(
                GenAIAttributes.CHAT_COMPLETION_OPERATION.value,
                getattr(self, "ai_model_id", chat_options.ai_model_id or "unknown"),
                self.MODEL_PROVIDER_NAME,
                self.service_url() if hasattr(self, "service_url") else None,
                chat_options,
            ),
            end_on_exit=True,
        ) as current_span:
            _set_chat_response_input(self.MODEL_PROVIDER_NAME, messages)
            try:
                response = await completion_func(self, messages=messages, chat_options=chat_options, **kwargs)
                _set_chat_response_output(current_span, response, self.MODEL_PROVIDER_NAME)
                return response
            except Exception as exception:
                _set_error(current_span, exception)
                raise

    # Mark the wrapper decorator as a chat completion decorator
    wrap_inner_get_response.__model_diagnostics_chat_client__ = True  # type: ignore

    return wrap_inner_get_response


def _trace_chat_get_streaming_response(
    completion_func: Callable[..., AsyncIterable["ChatResponseUpdate"]],
) -> Callable[..., AsyncIterable["ChatResponseUpdate"]]:
    """Decorator to trace streaming chat completion activities.

    Args:
        completion_func: The function to trace.
    """

    @functools.wraps(completion_func)
    async def wrap_inner_get_streaming_response(
        self: "ChatClientBase", *, messages: MutableSequence["ChatMessage"], chat_options: "ChatOptions", **kwargs: Any
    ) -> AsyncIterable["ChatResponseUpdate"]:
        if not MODEL_DIAGNOSTICS_SETTINGS.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            async for streaming_chat_message_contents in completion_func(
                self, messages=messages, chat_options=chat_options, **kwargs
            ):
                yield streaming_chat_message_contents
            return

        from ._types import ChatResponse

        all_updates: list["ChatResponseUpdate"] = []

        with use_span(
            _get_chat_response_span(
                GenAIAttributes.CHAT_COMPLETION_OPERATION.value,
                getattr(self, "ai_model_id", chat_options.ai_model_id or "unknown"),
                self.MODEL_PROVIDER_NAME,
                self.service_url() if hasattr(self, "service_url") else None,
                chat_options,
            ),
            end_on_exit=True,
        ) as current_span:
            _set_chat_response_input(self.MODEL_PROVIDER_NAME, messages)
            try:
                async for response in completion_func(self, messages=messages, chat_options=chat_options, **kwargs):
                    all_updates.append(response)
                    yield response

                all_messages_flattened = ChatResponse.from_chat_response_updates(all_updates)
                _set_chat_response_output(current_span, all_messages_flattened, self.MODEL_PROVIDER_NAME)
            except Exception as exception:
                _set_error(current_span, exception)
                raise

    # Mark the wrapper decorator as a streaming chat completion decorator
    wrap_inner_get_streaming_response.__model_diagnostics_streaming_chat_completion__ = True  # type: ignore
    return wrap_inner_get_streaming_response


def use_telemetry(cls: type[TChatClientBase]) -> type[TChatClientBase]:
    """Class decorator that enables telemetry for a chat client.

    Remarks:
        This only works on classes that derive from ChatClientBase
        and the _inner_get_response
        and _inner_get_streaming_response methods.
        It also relies on the presence of the MODEL_PROVIDER_NAME class variable.
        ```
    """
    if inner_response := getattr(cls, "_inner_get_response", None):
        cls._inner_get_response = _trace_chat_get_response(inner_response)  # type: ignore
    if inner_streaming_response := getattr(cls, "_inner_get_streaming_response", None):
        cls._inner_get_streaming_response = _trace_chat_get_streaming_response(inner_streaming_response)  # type: ignore
    return cls


def _get_chat_response_span(
    operation_name: str,
    model_name: str,
    model_provider: str,
    service_url: str | None,
    chat_options: "ChatOptions",
) -> Span:
    """Start a text or chat completion span for a given model.

    Note that `start_span` doesn't make the span the current span.
    Use `use_span` to make it the current span as a context manager.
    """
    span = tracer.start_span(f"{operation_name} {model_name}")

    # Set attributes on the span
    span.set_attributes({
        GenAIAttributes.OPERATION.value: operation_name,
        GenAIAttributes.SYSTEM.value: model_provider,
        GenAIAttributes.MODEL.value: model_name,
        GenAIAttributes.CHOICE_COUNT.value: 1,
    })

    if service_url:
        span.set_attribute(GenAIAttributes.ADDRESS.value, service_url)

    if chat_options.seed is not None:
        span.set_attribute(GenAIAttributes.SEED.value, chat_options.seed)
    if chat_options.frequency_penalty is not None:
        span.set_attribute(GenAIAttributes.FREQUENCY_PENALTY.value, chat_options.frequency_penalty)
    if chat_options.max_tokens is not None:
        span.set_attribute(GenAIAttributes.MAX_TOKENS.value, chat_options.max_tokens)
    if chat_options.stop is not None:
        span.set_attribute(GenAIAttributes.STOP_SEQUENCES.value, chat_options.stop)
    if chat_options.temperature is not None:
        span.set_attribute(GenAIAttributes.TEMPERATURE.value, chat_options.temperature)
    if chat_options.top_p is not None:
        span.set_attribute(GenAIAttributes.TOP_P.value, chat_options.top_p)
    if chat_options.presence_penalty is not None:
        span.set_attribute(GenAIAttributes.PRESENCE_PENALTY.value, chat_options.presence_penalty)
    if "top_k" in chat_options.additional_properties:
        span.set_attribute(GenAIAttributes.TOP_K.value, chat_options.additional_properties["top_k"])
    if "encoding_formats" in chat_options.additional_properties:
        span.set_attribute(
            GenAIAttributes.ENCODING_FORMATS.value, chat_options.additional_properties["encoding_formats"]
        )
    return span


def _set_chat_response_input(
    model_provider: str,
    messages: MutableSequence["ChatMessage"],
) -> None:
    """Set the input for a chat response.

    The logs will be associated to the current span.
    """
    if MODEL_DIAGNOSTICS_SETTINGS.SENSITIVE_EVENTS_ENABLED:
        for idx, message in enumerate(messages):
            event_name = ROLE_EVENT_MAP.get(message.role.value)
            logger.info(
                message.model_dump_json(exclude_none=True),
                extra={
                    GenAIAttributes.EVENT_NAME.value: event_name,
                    GenAIAttributes.SYSTEM.value: model_provider,
                    ChatMessageListTimestampFilter.INDEX_KEY: idx,
                },
            )


def _set_chat_response_output(
    current_span: Span,
    response: "ChatResponse",
    model_provider: str,
) -> None:
    """Set the response for a given span."""
    first_completion = response.messages[0]

    # Set the response ID
    response_id = (
        first_completion.additional_properties.get("id") if first_completion.additional_properties is not None else None
    )
    if response_id:
        current_span.set_attribute(GenAIAttributes.RESPONSE_ID.value, response_id)

    # Set the finish reason
    finish_reason = response.finish_reason
    if finish_reason:
        current_span.set_attribute(GenAIAttributes.FINISH_REASONS.value, [finish_reason.value])

    # Set usage attributes

    usage = response.usage_details
    if usage:
        if usage.input_token_count:
            current_span.set_attribute(GenAIAttributes.INPUT_TOKENS.value, usage.input_token_count)
        if usage.output_token_count:
            current_span.set_attribute(GenAIAttributes.OUTPUT_TOKENS.value, usage.output_token_count)

    # Set the completion event
    if MODEL_DIAGNOSTICS_SETTINGS.SENSITIVE_EVENTS_ENABLED:
        for completion in response.messages:
            full_response: dict[str, Any] = {
                "message": completion.model_dump(exclude_none=True),
            }
            full_response["index"] = response.response_id
            logger.info(
                json.dumps(full_response),
                extra={
                    GenAIAttributes.EVENT_NAME.value: GenAIAttributes.CHOICE.value,
                    GenAIAttributes.SYSTEM.value: model_provider,
                },
            )


# region Agent


def _trace_agent_run(
    run_func: Callable[..., Awaitable["AgentRunResponse"]],
) -> Callable[..., Awaitable["AgentRunResponse"]]:
    """Decorator to trace chat completion activities.

    Args:
        run_func: The function to trace.
    """

    @functools.wraps(run_func)
    async def wrap_run(
        self: "ChatClientAgent",
        messages: "str | ChatMessage | list[str] | list[ChatMessage] | None" = None,
        *,
        thread: "AgentThread | None" = None,
        **kwargs: Any,
    ) -> "AgentRunResponse":
        if not MODEL_DIAGNOSTICS_SETTINGS.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            return await run_func(
                self,
                messages=messages,
                thread=thread,
                **kwargs,
            )

        with use_span(
            _get_agent_run_span(
                operation_name=GenAIAttributes.AGENT_INVOKE_OPERATION.value,
                agent=self,
                system=self.AGENT_SYSTEM_NAME,
                thread=thread,
                **kwargs,
            ),
            end_on_exit=True,
        ) as current_span:
            _set_agent_run_input(self.AGENT_SYSTEM_NAME, messages)
            try:
                response = await run_func(self, messages=messages, thread=thread, **kwargs)
                _set_agent_run_output(current_span, response, self.AGENT_SYSTEM_NAME)
                return response
            except Exception as exception:
                _set_error(current_span, exception)
                raise

    # Mark the wrapper decorator as a agent run decorator
    wrap_run.__model_diagnostics_agent_run__ = True  # type: ignore

    return wrap_run


def _trace_agent_run_streaming(
    run_func: Callable[..., AsyncIterable["AgentRunResponseUpdate"]],
) -> Callable[..., AsyncIterable["AgentRunResponseUpdate"]]:
    """Decorator to trace streaming agent run activities.

    Args:
        run_func: The function to trace.
    """

    @functools.wraps(run_func)
    async def wrap_run_streaming(
        self: "ChatClientAgent",
        messages: "str | ChatMessage | list[str] | list[ChatMessage] | None" = None,
        *,
        thread: "AgentThread | None" = None,
        **kwargs: Any,
    ) -> AsyncIterable["AgentRunResponseUpdate"]:
        if not MODEL_DIAGNOSTICS_SETTINGS.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            async for streaming_agent_response in run_func(self, messages=messages, thread=thread, **kwargs):
                yield streaming_agent_response
            return

        from ._types import AgentRunResponse

        all_updates: list["AgentRunResponseUpdate"] = []

        with use_span(
            _get_agent_run_span(
                operation_name=GenAIAttributes.AGENT_INVOKE_OPERATION.value,
                agent=self,
                system=self.AGENT_SYSTEM_NAME,
                thread=thread,
                **kwargs,
            ),
            end_on_exit=True,
        ) as current_span:
            _set_agent_run_input(self.AGENT_SYSTEM_NAME, messages)
            try:
                async for response in run_func(self, messages=messages, thread=thread, **kwargs):
                    all_updates.append(response)
                    yield response

                all_messages_flattened = AgentRunResponse.from_agent_run_response_updates(all_updates)
                _set_agent_run_output(current_span, all_messages_flattened, self.AGENT_SYSTEM_NAME)
            except Exception as exception:
                _set_error(current_span, exception)
                raise

    # Mark the wrapper decorator as a streaming agent run decorator
    wrap_run_streaming.__model_diagnostics_streaming_agent_run__ = True  # type: ignore
    return wrap_run_streaming


def use_agent_telemetry(cls: type[TChatClientAgent]) -> type[TChatClientAgent]:
    """Class decorator that enables telemetry for an agent."""
    if run := getattr(cls, "run", None):
        cls.run = _trace_agent_run(run)  # type: ignore
    if run_streaming := getattr(cls, "run_streaming", None):
        cls.run_streaming = _trace_agent_run_streaming(run_streaming)  # type: ignore
    return cls


def _get_agent_run_span(
    *,
    operation_name: str,
    agent: "AIAgent",
    system: str,
    thread: "AgentThread | None",
    **kwargs: Any,
) -> Span:
    """Start a text or chat completion span for a given model.

    Note that `start_span` doesn't make the span the current span.
    Use `use_span` to make it the current span as a context manager.

    Should follow: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/#invoke-agent-span
    """
    span = tracer.start_span(f"{operation_name} {agent.display_name}")

    # Set attributes on the span
    span.set_attributes({
        GenAIAttributes.OPERATION.value: operation_name,
        GenAIAttributes.SYSTEM.value: system,
        GenAIAttributes.CHOICE_COUNT.value: 1,
        GenAIAttributes.AGENT_ID.value: agent.id,
    })
    if agent.name:
        span.set_attribute(GenAIAttributes.AGENT_NAME.value, agent.name)
    if agent.description:
        span.set_attribute(GenAIAttributes.AGENT_DESCRIPTION.value, agent.description)
    if thread and thread.id:
        span.set_attribute(GenAIAttributes.CONVERSATION_ID.value, thread.id)
    if "model" in kwargs:
        span.set_attribute(GenAIAttributes.MODEL.value, kwargs["model"])
    if "seed" in kwargs:
        span.set_attribute(GenAIAttributes.SEED.value, kwargs["seed"])
    if "frequency_penalty" in kwargs:
        span.set_attribute(GenAIAttributes.FREQUENCY_PENALTY.value, kwargs["frequency_penalty"])
    if "presence_penalty" in kwargs:
        span.set_attribute(GenAIAttributes.PRESENCE_PENALTY.value, kwargs["presence_penalty"])
    if "max_tokens" in kwargs:
        span.set_attribute(GenAIAttributes.MAX_TOKENS.value, kwargs["max_tokens"])
    if "stop" in kwargs:
        span.set_attribute(GenAIAttributes.STOP_SEQUENCES.value, kwargs["stop"])
    if "temperature" in kwargs:
        span.set_attribute(GenAIAttributes.TEMPERATURE.value, kwargs["temperature"])
    if "top_p" in kwargs:
        span.set_attribute(GenAIAttributes.TOP_P.value, kwargs["top_p"])
    if "top_k" in kwargs:
        span.set_attribute(GenAIAttributes.TOP_K.value, kwargs["top_k"])
    if "encoding_formats" in kwargs:
        span.set_attribute(GenAIAttributes.ENCODING_FORMATS.value, kwargs["encoding_formats"])
    return span


def _set_agent_run_input(
    system: str,
    messages: "str | ChatMessage | list[str] | list[ChatMessage] | list[str | ChatMessage] | None" = None,
) -> None:
    """Set the input for a chat response.

    The logs will be associated to the current span.
    """
    if messages and MODEL_DIAGNOSTICS_SETTINGS.SENSITIVE_EVENTS_ENABLED:
        if not isinstance(messages, list):
            messages = [messages]
        for idx, message in enumerate(messages):
            if isinstance(message, str):
                logger.info(
                    message,
                    extra={
                        # assume user message
                        GenAIAttributes.EVENT_NAME.value: GenAIAttributes.USER_MESSAGE.value,
                        GenAIAttributes.SYSTEM.value: system,
                        ChatMessageListTimestampFilter.INDEX_KEY: idx,
                    },
                )
            else:
                logger.info(
                    message.model_dump_json(exclude_none=True),
                    extra={
                        GenAIAttributes.EVENT_NAME.value: ROLE_EVENT_MAP.get(message.role.value),
                        GenAIAttributes.SYSTEM.value: system,
                        ChatMessageListTimestampFilter.INDEX_KEY: idx,
                    },
                )


def _set_agent_run_output(
    current_span: Span,
    response: "AgentRunResponse",
    model_provider: str,
) -> None:
    """Set the agent response for a given span."""
    first_completion = response.messages[0]

    # Set the response ID
    response_id = (
        first_completion.additional_properties.get("id") if first_completion.additional_properties is not None else None
    )
    if response_id:
        current_span.set_attribute(GenAIAttributes.RESPONSE_ID.value, response_id)

    # Set the finish reason
    finish_reason = getattr(response.raw_representation, "finish_reason", None) if response.raw_representation else None
    if finish_reason:
        current_span.set_attribute(GenAIAttributes.FINISH_REASONS.value, [finish_reason.value])

    # Set usage attributes
    usage = response.usage_details
    if usage:
        if usage.input_token_count:
            current_span.set_attribute(GenAIAttributes.INPUT_TOKENS.value, usage.input_token_count)
        if usage.output_token_count:
            current_span.set_attribute(GenAIAttributes.OUTPUT_TOKENS.value, usage.output_token_count)

    # Set the completion event
    if MODEL_DIAGNOSTICS_SETTINGS.SENSITIVE_EVENTS_ENABLED:
        for msg in response.messages:
            full_response: dict[str, Any] = {
                "message": msg.model_dump(exclude_none=True),
            }
            full_response["index"] = response.response_id
            logger.info(
                json.dumps(full_response),
                extra={
                    GenAIAttributes.EVENT_NAME.value: GenAIAttributes.CHOICE.value,
                    GenAIAttributes.SYSTEM.value: model_provider,
                },
            )
