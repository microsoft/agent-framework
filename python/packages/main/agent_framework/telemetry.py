# Copyright (c) Microsoft. All rights reserved.

import functools
import json
import logging
import os
from collections.abc import AsyncIterable, Callable, MutableSequence
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, Final, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode, get_tracer, use_span

from . import __version__ as version_info
from ._pydantic import AFBaseSettings
from ._types import ChatMessage, ChatRole, UsageDetails

if TYPE_CHECKING:
    from ._clients import ChatClientBase
    from ._tools import AIFunction
    from ._types import ChatOptions, ChatResponse, ChatResponseUpdate

__all__ = [
    "AGENT_FRAMEWORK_USER_AGENT",
    "APP_INFO",
    "USER_AGENT_KEY",
    "prepend_agent_framework_to_user_agent",
    "use_telemetry",
]


# Constants for tracing activities with semantic conventions.
# Ideally, we should use the attributes from the semcov package.
# However, many of the attributes are not yet available in the package,
# so we define them here for now.


# Activity tags
class GenAIAttributes(str, Enum):
    OPERATION = "gen_ai.operation.name"
    SYSTEM = "gen_ai.system"
    ERROR_TYPE = "error.type"
    MODEL = "gen_ai.request.model"
    SEED = "gen_ai.request.seed"
    PORT = "server.port"
    ENCODING_FORMATS = "gen_ai.request.encoding_formats"
    FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
    MAX_TOKENS = "gen_ai.request.max_tokens"
    STOP_SEQUENCES = "gen_ai.request.stop_sequences"
    TEMPERATURE = "gen_ai.request.temperature"
    TOP_K = "gen_ai.request.top_k"
    TOP_P = "gen_ai.request.top_p"
    FINISH_REASON = "gen_ai.response.finish_reason"
    RESPONSE_ID = "gen_ai.response.id"
    INPUT_TOKENS = "gen_ai.usage.input_tokens"
    OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
    TOOL_CALL_ID = "gen_ai.tool.call.id"
    TOOL_DESCRIPTION = "gen_ai.tool.description"
    TOOL_NAME = "gen_ai.tool.name"
    ADDRESS = "server.address"

    # Activity events
    EVENT_NAME = "event.name"
    SYSTEM_MESSAGE = "gen_ai.system.message"
    USER_MESSAGE = "gen_ai.user.message"
    ASSISTANT_MESSAGE = "gen_ai.assistant.message"
    TOOL_MESSAGE = "gen_ai.tool.message"
    CHOICE = "gen_ai.choice"
    PROMPT = "gen_ai.prompt"

    # Operation names
    CHAT_COMPLETION_OPERATION = "chat.completions"
    CHAT_STREAMING_COMPLETION_OPERATION = "chat.streaming_completions"
    TOOL_EXECUTION_OPERATION = "execute_tool"


ROLE_EVENT_MAP = {
    ChatRole.SYSTEM.value: GenAIAttributes.SYSTEM_MESSAGE,
    ChatRole.USER.value: GenAIAttributes.USER_MESSAGE,
    ChatRole.ASSISTANT.value: GenAIAttributes.ASSISTANT_MESSAGE,
    ChatRole.TOOL.value: GenAIAttributes.TOOL_MESSAGE,
}


# Note that if this environment variable does not exist, telemetry is enabled.
TELEMETRY_DISABLED_ENV_VAR = "AZURE_TELEMETRY_DISABLED"
IS_TELEMETRY_ENABLED = os.environ.get(TELEMETRY_DISABLED_ENV_VAR, "false").lower() not in ["true", "1"]

APP_INFO = (
    {
        "agent-framework-version": f"python/{version_info}",
    }
    if IS_TELEMETRY_ENABLED
    else None
)
USER_AGENT_KEY: Final[str] = "User-Agent"
HTTP_USER_AGENT: Final[str] = "agent-framework-python"
AGENT_FRAMEWORK_USER_AGENT = f"{HTTP_USER_AGENT}/{version_info}"

__all__ = [
    "AGENT_FRAMEWORK_USER_AGENT",
    "APP_INFO",
    "USER_AGENT_KEY",
    "prepend_agent_framework_to_user_agent",
]


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


class ModelDiagnosticSettings(AFBaseSettings):
    """Settings for model diagnostics.

    The settings are first loaded from environment variables with
    the prefix 'AGENT_FRAMEWORK_GENAI_'.
    If the environment variables are not found, the settings can
    be loaded from a .env file with the encoding 'utf-8'.
    If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the
    settings are missing.

    Required settings for prefix 'AGENT_FRAMEWORK_GENAI_' are:
    - enable_otel_diagnostics: bool - Enable OpenTelemetry diagnostics. Default is False.
                (Env var AGENT_FRAMEWORK_GENAI_ENABLE_OTEL_DIAGNOSTICS)
    - enable_otel_diagnostics_sensitive: bool - Enable OpenTelemetry sensitive events. Default is False.
                (Env var AGENT_FRAMEWORK_GENAI_ENABLE_OTEL_DIAGNOSTICS_SENSITIVE)
    """

    env_prefix: ClassVar[str] = "AGENT_FRAMEWORK_GENAI_"

    enable_otel_diagnostics: bool = False
    enable_otel_diagnostics_sensitive: bool = False


def start_as_current_span(
    tracer: trace.Tracer,
    function: "AIFunction[Any, Any]",
    metadata: dict[str, Any] | None = None,
):
    """Starts a span for the given function using the provided tracer.

    Args:
        tracer: The OpenTelemetry tracer to use.
        function: The function for which to start the span.
        metadata: Optional metadata to include in the span attributes.

    Returns:
        trace.Span: The started span as a context manager.
    """
    attributes = {
        GenAIAttributes.OPERATION.value: GenAIAttributes.TOOL_EXECUTION_OPERATION,
        GenAIAttributes.TOOL_NAME.value: function.name,
    }

    tool_call_id = metadata.get("id", None) if metadata else None
    if tool_call_id:
        attributes[GenAIAttributes.TOOL_CALL_ID.value] = tool_call_id
    if function.description:
        attributes[GenAIAttributes.TOOL_DESCRIPTION.value] = function.description

    return tracer.start_as_current_span(
        f"{GenAIAttributes.TOOL_EXECUTION_OPERATION} {function.name}", attributes=attributes
    )


MODEL_DIAGNOSTICS_SETTINGS = ModelDiagnosticSettings()


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
class ChatHistoryMessageTimestampFilter(logging.Filter):
    """A filter to increment the timestamp of INFO logs by 1 microsecond."""

    INDEX_KEY: ClassVar[str] = "CHAT_MESSAGE_INDEX"

    def filter(self, record: logging.LogRecord) -> bool:
        """Increment the timestamp of INFO logs by 1 microsecond."""
        if hasattr(record, self.INDEX_KEY):
            idx = getattr(record, self.INDEX_KEY)
            record.created += idx * 1e-6
        return True


# Creates a tracer from the global tracer provider
tracer = get_tracer(__name__)

logger = logging.getLogger(__name__)
logger.addFilter(ChatHistoryMessageTimestampFilter())


def are_model_diagnostics_enabled() -> bool:
    """Check if model diagnostics are enabled.

    Model diagnostics are enabled if either diagnostic is enabled or diagnostic with sensitive events is enabled.
    """
    return (
        MODEL_DIAGNOSTICS_SETTINGS.enable_otel_diagnostics
        or MODEL_DIAGNOSTICS_SETTINGS.enable_otel_diagnostics_sensitive
    )


def are_sensitive_events_enabled() -> bool:
    """Check if sensitive events are enabled.

    Sensitive events are enabled if the diagnostic with sensitive events is enabled.
    """
    return MODEL_DIAGNOSTICS_SETTINGS.enable_otel_diagnostics_sensitive


def _trace_chat_get_response(completion_func: Callable[..., Any]) -> Callable[..., Any]:
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
        if not are_model_diagnostics_enabled():
            # If model diagnostics are not enabled, just return the completion
            return await completion_func(self, messages=messages, chat_options=chat_options, **kwargs)

        with use_span(
            _get_completion_span(
                GenAIAttributes.CHAT_COMPLETION_OPERATION,
                getattr(self, "ai_model_id", chat_options.ai_model_id or "unknown"),
                self.MODEL_PROVIDER_NAME,
                self.service_url(),
                chat_options,
            ),
            end_on_exit=True,
        ) as current_span:
            _set_completion_input(self.MODEL_PROVIDER_NAME, messages)
            try:
                response: "ChatResponse" = await completion_func(
                    self, messages=messages, chat_options=chat_options, **kwargs
                )
                _set_completion_response(current_span, response, self.MODEL_PROVIDER_NAME)
                return response
            except Exception as exception:
                _set_completion_error(current_span, exception)
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
        if not are_model_diagnostics_enabled():
            # If model diagnostics are not enabled, just return the completion
            async for streaming_chat_message_contents in completion_func(
                self, messages=messages, chat_options=chat_options, **kwargs
            ):
                yield streaming_chat_message_contents
            return

        all_updates: list["ChatResponseUpdate"] = []

        with use_span(
            _get_completion_span(
                GenAIAttributes.CHAT_STREAMING_COMPLETION_OPERATION,
                getattr(self, "ai_model_id", chat_options.ai_model_id or "unknown"),
                self.MODEL_PROVIDER_NAME,
                self.service_url(),
                chat_options,
            ),
            end_on_exit=True,
        ) as current_span:
            _set_completion_input(self.MODEL_PROVIDER_NAME, messages)
            try:
                async for response in completion_func(self, messages=messages, chat_options=chat_options, **kwargs):
                    all_updates.append(response)
                    yield response

                all_messages_flattened = ChatResponse.from_chat_response_updates(all_updates)
                _set_completion_response(current_span, all_messages_flattened, self.MODEL_PROVIDER_NAME)
            except Exception as exception:
                _set_completion_error(current_span, exception)
                raise

    # Mark the wrapper decorator as a streaming chat completion decorator
    wrap_inner_get_streaming_response.__model_diagnostics_streaming_chat_completion__ = True  # type: ignore
    return wrap_inner_get_streaming_response


TChatClientBase = TypeVar("TChatClientBase", bound="ChatClientBase")


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


def _get_completion_span(
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
        GenAIAttributes.OPERATION: operation_name,
        GenAIAttributes.SYSTEM: model_provider,
        GenAIAttributes.MODEL: model_name,
    })

    if service_url:
        span.set_attribute(GenAIAttributes.ADDRESS, service_url)

    if chat_options.seed is not None:
        span.set_attribute(GenAIAttributes.SEED, chat_options.seed)
    if chat_options.frequency_penalty is not None:
        span.set_attribute(GenAIAttributes.FREQUENCY_PENALTY, chat_options.frequency_penalty)
    if chat_options.max_tokens is not None:
        span.set_attribute(GenAIAttributes.MAX_TOKENS, chat_options.max_tokens)
    if chat_options.stop is not None:
        span.set_attribute(GenAIAttributes.STOP_SEQUENCES, chat_options.stop)
    if chat_options.temperature is not None:
        span.set_attribute(GenAIAttributes.TEMPERATURE, chat_options.temperature)
    if chat_options.top_p is not None:
        span.set_attribute(GenAIAttributes.TOP_P, chat_options.top_p)
    if "top_k" in chat_options.additional_properties:
        span.set_attribute(GenAIAttributes.TOP_K, chat_options.additional_properties["top_k"])
    if "encoding_formats" in chat_options.additional_properties:
        span.set_attribute(GenAIAttributes.ENCODING_FORMATS, chat_options.additional_properties["encoding_formats"])
    return span


def _set_completion_input(
    model_provider: str,
    messages: MutableSequence[ChatMessage],
) -> None:
    """Set the input for a chat response.

    The logs will be associated to the current span.
    """
    if are_sensitive_events_enabled():
        for idx, message in enumerate(messages):
            event_name = ROLE_EVENT_MAP.get(message.role.value)
            if event_name:
                logger.info(
                    message.model_dump_json(exclude_none=True),
                    extra={
                        GenAIAttributes.EVENT_NAME: event_name,
                        GenAIAttributes.SYSTEM: model_provider,
                        ChatHistoryMessageTimestampFilter.INDEX_KEY: idx,
                    },
                )


def _set_completion_response(
    current_span: Span,
    response: "ChatResponse",
    model_provider: str,
) -> None:
    """Set the a text or chat completion response for a given span."""
    first_completion = response.messages[0]

    # Set the response ID
    response_id = (
        first_completion.additional_properties.get("id") if first_completion.additional_properties is not None else None
    )
    if response_id:
        current_span.set_attribute(GenAIAttributes.RESPONSE_ID, response_id)

    # Set the finish reason
    finish_reason = response.finish_reason
    if finish_reason:
        current_span.set_attribute(GenAIAttributes.FINISH_REASON, finish_reason.value)

    # Set usage attributes
    usage = response.usage_details
    if isinstance(usage, UsageDetails):
        if usage.input_token_count:
            current_span.set_attribute(GenAIAttributes.INPUT_TOKENS, usage.input_token_count)
        if usage.output_token_count:
            current_span.set_attribute(GenAIAttributes.OUTPUT_TOKENS, usage.output_token_count)

    # Set the completion event
    if are_sensitive_events_enabled():
        for completion in response.messages:
            full_response: dict[str, Any] = {
                "message": completion.model_dump(exclude_none=True),
            }
            full_response["index"] = response.response_id
            logger.info(
                json.dumps(full_response),
                extra={
                    GenAIAttributes.EVENT_NAME: GenAIAttributes.CHOICE,
                    GenAIAttributes.SYSTEM: model_provider,
                },
            )


def _set_completion_error(span: Span, error: Exception) -> None:
    """Set an error for a text or chat completion ."""
    span.set_attribute(GenAIAttributes.ERROR_TYPE, str(type(error)))
    span.set_status(StatusCode.ERROR, repr(error))
