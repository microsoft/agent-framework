# Copyright (c) Microsoft. All rights reserved.

import json
import logging
import os
from collections.abc import AsyncIterable, Awaitable, Callable
from enum import Enum
from functools import wraps
from time import time_ns
from typing import TYPE_CHECKING, Any, ClassVar, Final, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode, get_tracer, use_span

from . import __version__ as version_info
from ._logging import get_logger
from ._pydantic import AFBaseSettings

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry.util._decorator import _AgnosticContextManager  # type: ignore[reportPrivateUsage]

    from ._agents import AIAgent, ChatClientAgent
    from ._clients import ChatClient
    from ._threads import AgentThread
    from ._tools import AIFunction
    from ._types import (
        AgentRunResponse,
        AgentRunResponseUpdate,
        ChatMessage,
        ChatResponse,
        ChatResponseUpdate,
    )

TChatClientAgent = TypeVar("TChatClientAgent", bound="ChatClientAgent")

tracer = get_tracer("agent_framework")
logger = get_logger()

__all__ = [
    "AGENT_FRAMEWORK_USER_AGENT",
    "APP_INFO",
    "USER_AGENT_KEY",
    "OpenTelemetryChatClient",
    "prepend_agent_framework_to_user_agent",
    "use_agent_telemetry",
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

    INDEX_KEY: ClassVar[str] = "chat_message_index"

    def filter(self, record: logging.LogRecord) -> bool:
        """Increment the timestamp of INFO logs by 1 microsecond."""
        if hasattr(record, self.INDEX_KEY):
            idx = getattr(record, self.INDEX_KEY)
            record.created += idx * 1e-6
        return True


# Creates a tracer from the global tracer provider
logger.addFilter(ChatMessageListTimestampFilter())


class OtelAttr(str, Enum):
    """Enum to capture the attributes used in OpenTelemetry for Generative AI.

    Based on: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/
    and https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/
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

    def __repr__(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


ROLE_EVENT_MAP = {
    "system": OtelAttr.SYSTEM_MESSAGE,
    "user": OtelAttr.USER_MESSAGE,
    "assistant": OtelAttr.ASSISTANT_MESSAGE,
    "tool": OtelAttr.TOOL_MESSAGE,
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
    tool_call_id: str | None = None,
) -> "_AgnosticContextManager[Span]":
    """Starts a span for the given function using the provided tracer.

    Args:
        tracer: The OpenTelemetry tracer to use.
        function: The function for which to start the span.
        tool_call_id: The id of the tool_call that was requested.

    Returns:
        trace.Span: The started span as a context manager.
    """
    attributes: dict[str, str] = {
        OtelAttr.OPERATION: OtelAttr.TOOL_EXECUTION_OPERATION,
        OtelAttr.TOOL_NAME: function.name,
        OtelAttr.TOOL_CALL_ID: tool_call_id or "unknown",
    }
    if function.description:
        attributes[OtelAttr.TOOL_DESCRIPTION] = function.description

    return tracer.start_as_current_span(
        name=f"{OtelAttr.TOOL_EXECUTION_OPERATION} {function.name}",
        attributes=attributes,
        set_status_on_exception=False,
        end_on_exit=True,
        record_exception=False,
    )


def set_exception(span: Span, exception: Exception, timestamp: int | None = None) -> None:
    """Set an error for spans."""
    span.set_attribute(OtelAttr.ERROR_TYPE, str(type(exception)))
    span.record_exception(exception=exception, timestamp=timestamp)
    span.set_status(status=StatusCode.ERROR, description=repr(exception))


# region ChatClient


def _trace_get_response(
    chat_client: "ChatClient",
    get_response_func: Callable[..., Awaitable["ChatResponse"]],
    model_diagnostics: ModelDiagnosticSettings,
    model_provider: str,
) -> Callable[..., Awaitable["ChatResponse"]]:
    """Decorator to trace chat completion activities.

    Args:
        chat_client: the chat client
        get_response_func: The function to trace.
        model_diagnostics: the settings for what to trace
        model_provider: The model provider name.
    """

    @wraps(get_response_func)
    async def wrap_get_response(
        messages: "str | ChatMessage | list[str] | list[ChatMessage]",
        **kwargs: Any,
    ) -> "ChatResponse":
        if not model_diagnostics.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            return await get_response_func(
                messages=messages,
                **kwargs,
            )

        with use_span(
            span=_get_response_span(
                operation_name=OtelAttr.CHAT_COMPLETION_OPERATION,
                model_provider=model_provider,
                chat_client=chat_client,
                **kwargs,
            ),
            end_on_exit=True,
            record_exception=False,
            set_status_on_exception=False,
        ) as current_span:
            if model_diagnostics.SENSITIVE_EVENTS_ENABLED:
                from ._clients import _prepare_messages

                _log_messages(
                    model_provider=model_provider,
                    messages=_prepare_messages(messages),
                )
            try:
                response = await get_response_func(messages=messages, **kwargs)
            except Exception as exception:
                set_exception(span=current_span, exception=exception, timestamp=time_ns())
                raise
            _set_response_output(span=current_span, response=response)
            if model_diagnostics.SENSITIVE_EVENTS_ENABLED:
                _log_messages(model_provider=model_provider, messages=response.messages)
            return response

    # Mark the wrapper decorator as a chat completion decorator
    wrap_get_response.__model_diagnostics_chat_client__ = True  # type: ignore
    return wrap_get_response


def _trace_get_streaming_response(
    chat_client: "ChatClient",
    get_streaming_response_func: Callable[..., AsyncIterable["ChatResponseUpdate"]],
    model_diagnostics: ModelDiagnosticSettings,
    model_provider: str,
) -> Callable[..., AsyncIterable["ChatResponseUpdate"]]:
    """Decorator to trace streaming chat completion activities.

    Args:
        chat_client: the Chat client.
        get_streaming_response_func: The function to trace.
        model_diagnostics: the settings for what to trace.
        model_provider: The model provider name.
    """

    @wraps(get_streaming_response_func)
    async def wrap_get_streaming_response(
        messages: "str | ChatMessage | list[str] | list[ChatMessage]", **kwargs: Any
    ) -> AsyncIterable["ChatResponseUpdate"]:
        if not model_diagnostics.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            async for streaming_chat_message_contents in get_streaming_response_func(messages=messages, **kwargs):
                yield streaming_chat_message_contents
            return

        # when this function is wrapped by the FunctionCalling decorator
        # the function results are handled there and passed.
        all_updates: list["ChatResponseUpdate"] = []

        with use_span(
            span=_get_response_span(
                operation_name=OtelAttr.CHAT_COMPLETION_OPERATION,
                model_provider=model_provider,
                chat_client=chat_client,
                **kwargs,
            ),
            end_on_exit=True,
            record_exception=False,
            set_status_on_exception=False,
        ) as current_span:
            if model_diagnostics.SENSITIVE_EVENTS_ENABLED:
                from ._clients import _prepare_messages

                _log_messages(
                    model_provider=model_provider,
                    messages=_prepare_messages(messages),
                )
            try:
                async for update in get_streaming_response_func(messages=messages, **kwargs):
                    all_updates.append(update)
                    yield update
            except Exception as exception:
                set_exception(span=current_span, exception=exception, timestamp=time_ns())
                raise
            from ._types import ChatResponse

            response = ChatResponse.from_chat_response_updates(all_updates)
            _set_response_output(span=current_span, response=response)

            if model_diagnostics.SENSITIVE_EVENTS_ENABLED:
                _log_messages(
                    model_provider=model_provider,
                    messages=response.messages,
                )

    # Mark the wrapper decorator as a streaming chat completion decorator
    wrap_get_streaming_response.__model_diagnostics_streaming_chat_completion__ = True  # type: ignore
    return wrap_get_streaming_response


def OpenTelemetryChatClient(
    chat_client: "ChatClient",
    *,
    enable_otel_diagnostics: bool | None = None,
    enable_otel_diagnostics_sensitive: bool | None = None,
    model_provider_name: str | None = None,
) -> "ChatClient":
    """Class decorator that enables telemetry for a chat client.

    Args:
        chat_client: The chat client to decorate.
        enable_otel_diagnostics: Enable OpenTelemetry diagnostics.
            If None, uses the value from the environment.
            If those are not present, the default is False.
        enable_otel_diagnostics_sensitive: Enable OpenTelemetry sensitive events.
            If None, uses the value from the environment.
            If those are not present, the default is False.
        model_provider_name: The model provider name.
            If None, uses the value from the chat client's MODEL_PROVIDER_NAME variable.
    """
    model_diagnostics = ModelDiagnosticSettings(
        enable_otel_diagnostics=enable_otel_diagnostics,  # type: ignore[reportArgumentType]
        enable_otel_diagnostics_sensitive=enable_otel_diagnostics_sensitive,  # type: ignore[reportArgumentType]
    )
    model_provider = model_provider_name or str(getattr(chat_client, "MODEL_PROVIDER_NAME", "unknown"))

    object.__setattr__(
        chat_client,
        "get_response",
        _trace_get_response(
            chat_client=chat_client,
            get_response_func=chat_client.get_response,
            model_diagnostics=model_diagnostics,
            model_provider=model_provider,
        ),
    )
    object.__setattr__(
        chat_client,
        "get_streaming_response",
        _trace_get_streaming_response(
            chat_client=chat_client,
            get_streaming_response_func=chat_client.get_streaming_response,
            model_diagnostics=model_diagnostics,
            model_provider=model_provider,
        ),
    )
    setattr(chat_client, "__open_telemetry_chat_client__", True)  # noqa: B010
    return chat_client


def _get_response_span(
    operation_name: str,
    model_provider: str,
    chat_client: "ChatClient",
    **kwargs: Any,
) -> Span:
    """Start a text or chat completion span for a given model.

    Note that `start_span` doesn't make the span the current span.
    Use `use_span` to make it the current span as a context manager.
    """
    model_name = getattr(chat_client, "ai_model_id", kwargs.get("ai_model_id", "unknown"))
    span = tracer.start_span(f"{operation_name} {model_name}")

    # Set attributes on the span
    span.set_attributes({
        OtelAttr.OPERATION: operation_name,
        OtelAttr.SYSTEM: model_provider,
        OtelAttr.MODEL: model_name,
        OtelAttr.CHOICE_COUNT: 1,
    })

    if (service_url_func := getattr(chat_client, "service_url")) and callable(service_url_func):  # noqa: B009
        span.set_attribute(OtelAttr.ADDRESS, service_url_func())  # type: ignore[reportArgumentType]

    if seed := kwargs.get("seed"):
        span.set_attribute(OtelAttr.SEED, seed)
    if frequency_penalty := kwargs.get("frequency_penalty"):
        span.set_attribute(OtelAttr.FREQUENCY_PENALTY, frequency_penalty)
    if max_tokens := kwargs.get("max_tokens"):
        span.set_attribute(OtelAttr.MAX_TOKENS, max_tokens)
    if stop := kwargs.get("stop"):
        span.set_attribute(OtelAttr.STOP_SEQUENCES, stop)
    if temperature := kwargs.get("temperature"):
        span.set_attribute(OtelAttr.TEMPERATURE, temperature)
    if top_p := kwargs.get("top_p"):
        span.set_attribute(OtelAttr.TOP_P, top_p)
    if presence_penalty := kwargs.get("presence_penalty"):
        span.set_attribute(OtelAttr.PRESENCE_PENALTY, presence_penalty)
    if top_k := kwargs.get("top_k"):
        span.set_attribute(OtelAttr.TOP_K, top_k)
    if encoding_formats := kwargs.get("encoding_formats"):
        span.set_attribute(
            OtelAttr.ENCODING_FORMATS,
            encoding_formats if isinstance(encoding_formats, list) else [encoding_formats],
        )
    return span


def _log_messages(
    model_provider: str,
    messages: "list[ChatMessage]",
) -> None:
    """Log messages with extra information."""
    for index, message in enumerate(messages):
        logger.info(
            json.dumps({"message": message.model_dump_json(exclude_none=True), "index": index}),
            extra={
                OtelAttr.EVENT_NAME: ROLE_EVENT_MAP.get(message.role.value),
                OtelAttr.SYSTEM: model_provider,
                ChatMessageListTimestampFilter.INDEX_KEY: index,
            },
        )


def _set_response_output(
    span: Span,
    response: "ChatResponse",
) -> None:
    """Set the response for a given span."""
    first_completion = response.messages[0]

    # Set the response ID
    if response_id := (
        first_completion.additional_properties.get("id") if first_completion.additional_properties is not None else None
    ):
        span.set_attribute(OtelAttr.RESPONSE_ID, response_id)

    # Set the finish reason
    if finish_reason := response.finish_reason:
        span.set_attribute(OtelAttr.FINISH_REASONS, [finish_reason.value])  # type: ignore[reportArgumentType]

    # Set usage attributes
    if usage := response.usage_details:
        if usage.input_token_count:
            span.set_attribute(OtelAttr.INPUT_TOKENS, usage.input_token_count)
        if usage.output_token_count:
            span.set_attribute(OtelAttr.OUTPUT_TOKENS, usage.output_token_count)


# region Agent


def _trace_agent_run(
    run_func: Callable[..., Awaitable["AgentRunResponse"]],
) -> Callable[..., Awaitable["AgentRunResponse"]]:
    """Decorator to trace chat completion activities.

    Args:
        run_func: The function to trace.
    """

    @wraps(run_func)
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
                operation_name=OtelAttr.AGENT_INVOKE_OPERATION,
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
                set_exception(span=current_span, exception=exception, timestamp=time_ns())
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

    @wraps(run_func)
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
                operation_name=OtelAttr.AGENT_INVOKE_OPERATION,
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
                set_exception(span=current_span, exception=exception, timestamp=time_ns())
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
        OtelAttr.OPERATION: operation_name,
        OtelAttr.SYSTEM: system,
        OtelAttr.CHOICE_COUNT: 1,
        OtelAttr.AGENT_ID: agent.id,
    })
    if agent.name:
        span.set_attribute(OtelAttr.AGENT_NAME, agent.name)
    if agent.description:
        span.set_attribute(OtelAttr.AGENT_DESCRIPTION, agent.description)
    if thread and thread.service_thread_id:
        span.set_attribute(OtelAttr.CONVERSATION_ID, thread.service_thread_id)
    if "model" in kwargs:
        span.set_attribute(OtelAttr.MODEL, kwargs["model"])
    if "seed" in kwargs:
        span.set_attribute(OtelAttr.SEED, kwargs["seed"])
    if "frequency_penalty" in kwargs:
        span.set_attribute(OtelAttr.FREQUENCY_PENALTY, kwargs["frequency_penalty"])
    if "presence_penalty" in kwargs:
        span.set_attribute(OtelAttr.PRESENCE_PENALTY, kwargs["presence_penalty"])
    if "max_tokens" in kwargs:
        span.set_attribute(OtelAttr.MAX_TOKENS, kwargs["max_tokens"])
    if "stop" in kwargs:
        span.set_attribute(OtelAttr.STOP_SEQUENCES, kwargs["stop"])
    if "temperature" in kwargs:
        span.set_attribute(OtelAttr.TEMPERATURE, kwargs["temperature"])
    if "top_p" in kwargs:
        span.set_attribute(OtelAttr.TOP_P, kwargs["top_p"])
    if "top_k" in kwargs:
        span.set_attribute(OtelAttr.TOP_K, kwargs["top_k"])
    if "encoding_formats" in kwargs:
        span.set_attribute(OtelAttr.ENCODING_FORMATS, kwargs["encoding_formats"])
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
                        OtelAttr.EVENT_NAME.value: OtelAttr.USER_MESSAGE,
                        OtelAttr.SYSTEM: system,
                        ChatMessageListTimestampFilter.INDEX_KEY: idx,
                    },
                )
            else:
                logger.info(
                    message.model_dump_json(exclude_none=True),
                    extra={
                        OtelAttr.EVENT_NAME.value: ROLE_EVENT_MAP.get(message.role.value),
                        OtelAttr.SYSTEM: system,
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
        current_span.set_attribute(OtelAttr.RESPONSE_ID, response_id)

    # Set the finish reason
    finish_reason = getattr(response.raw_representation, "finish_reason", None) if response.raw_representation else None
    if finish_reason:
        current_span.set_attribute(OtelAttr.FINISH_REASONS.value, [finish_reason])

    # Set usage attributes
    usage = response.usage_details
    if usage:
        if usage.input_token_count:
            current_span.set_attribute(OtelAttr.INPUT_TOKENS, usage.input_token_count)
        if usage.output_token_count:
            current_span.set_attribute(OtelAttr.OUTPUT_TOKENS, usage.output_token_count)

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
                    OtelAttr.EVENT_NAME.value: OtelAttr.CHOICE,
                    OtelAttr.SYSTEM: model_provider,
                },
            )
