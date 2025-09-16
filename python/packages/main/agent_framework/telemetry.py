# Copyright (c) Microsoft. All rights reserved.

import json
import logging
import os
from collections.abc import AsyncIterable, Awaitable, Callable, Generator
from contextlib import contextmanager
from enum import Enum
from functools import wraps
from time import perf_counter, time_ns
from typing import TYPE_CHECKING, Any, ClassVar, Final, TypeVar

from opentelemetry import metrics
from opentelemetry.semconv_ai import GenAISystem, Meters, SpanAttributes
from opentelemetry.trace import Span, StatusCode, get_tracer, use_span
from opentelemetry.version import __version__ as otel_version
from pydantic import PrivateAttr

from . import __version__ as version_info
from ._logging import get_logger
from ._pydantic import AFBaseSettings
from .exceptions import AgentInitializationError, ChatClientInitializationError

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry.metrics import Histogram
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.util._decorator import _AgnosticContextManager  # type: ignore[reportPrivateUsage]

    from ._agents import AgentProtocol
    from ._clients import ChatClientProtocol
    from ._threads import AgentThread
    from ._tools import AIFunction
    from ._types import (
        AgentRunResponse,
        AgentRunResponseUpdate,
        ChatMessage,
        ChatResponse,
        ChatResponseUpdate,
        Contents,
        FinishReason,
    )

TAgent = TypeVar("TAgent", bound="AgentProtocol")
TChatClient = TypeVar("TChatClient", bound="ChatClientProtocol")

logger = get_logger()

__all__ = [
    "AGENT_FRAMEWORK_USER_AGENT",
    "APP_INFO",
    "OPEN_TELEMETRY_AGENT_MARKER",
    "OPEN_TELEMETRY_CHAT_CLIENT_MARKER",
    "OTEL_SETTINGS",
    "USER_AGENT_KEY",
    "prepend_agent_framework_to_user_agent",
    "setup_telemetry",
    "use_agent_telemetry",
    "use_telemetry",
]

# region User Agents
# Note that if this environment variable does not exist, user agent telemetry is enabled.
USER_AGENT_TELEMETRY_DISABLED_ENV_VAR = "AGENT_FRAMEWORK_USER_AGENT_DISABLED"
IS_TELEMETRY_ENABLED = os.environ.get(USER_AGENT_TELEMETRY_DISABLED_ENV_VAR, "false").lower() not in ["true", "1"]

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


def prepend_agent_framework_to_user_agent(headers: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prepend "agent-framework" to the User-Agent in the headers.

    When user agent telemetry is disabled, through the AZURE_TELEMETRY_DISABLED environment variable,
    the User-Agent header will not include the agent-framework information, it will be sent back as is,
    or as a empty dict when None is passed.

    Args:
        headers: The existing headers dictionary.

    Returns:
        A new dict with "User-Agent" set to "agent-framework-python/{version}" if headers is None.
        The modified headers dictionary with "agent-framework-python/{version}" prepended to the User-Agent.
    """
    if not IS_TELEMETRY_ENABLED:
        return headers or {}
    if not headers:
        return {USER_AGENT_KEY: AGENT_FRAMEWORK_USER_AGENT}
    headers[USER_AGENT_KEY] = (
        f"{AGENT_FRAMEWORK_USER_AGENT} {headers[USER_AGENT_KEY]}"
        if USER_AGENT_KEY in headers
        else AGENT_FRAMEWORK_USER_AGENT
    )

    return headers


# region Otel

tracer = get_tracer("agent_framework", otel_version)
meter = metrics.get_meter_provider().get_meter("agent_framework", otel_version)

OTEL_METRICS: Final[str] = "__otel_metrics__"
OPEN_TELEMETRY_CHAT_CLIENT_MARKER: Final[str] = "__open_telemetry_chat_client__"
OPEN_TELEMETRY_AGENT_MARKER: Final[str] = "__open_telemetry_agent__"
TOKEN_USAGE_BUCKET_BOUNDARIES: Final[tuple[float, ...]] = (
    1,
    4,
    16,
    64,
    256,
    1024,
    4096,
    16384,
    65536,
    262144,
    1048576,
    4194304,
    16777216,
    67108864,
)
OPERATION_DURATION_BUCKET_BOUNDARIES: Final[tuple[float, ...]] = (
    0.01,
    0.02,
    0.04,
    0.08,
    0.16,
    0.32,
    0.64,
    1.28,
    2.56,
    5.12,
    10.24,
    20.48,
    40.96,
    81.92,
)


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


logger.addFilter(ChatMessageListTimestampFilter())


class OtelAttr(str, Enum):
    """Enum to capture the attributes used in OpenTelemetry for Generative AI.

    Based on: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/
    and https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/
    """

    OPERATION = "gen_ai.operation.name"
    PROVIDER_NAME = "gen_ai.provider.name"
    ERROR_TYPE = "error.type"
    PORT = "server.port"
    ADDRESS = "server.address"
    SPAN_ID = "SpanId"
    TRACE_ID = "TraceId"
    # Request attributes
    SEED = "gen_ai.request.seed"
    ENCODING_FORMATS = "gen_ai.request.encoding_formats"
    FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
    PRESENCE_PENALTY = "gen_ai.request.presence_penalty"
    STOP_SEQUENCES = "gen_ai.request.stop_sequences"
    TOP_K = "gen_ai.request.top_k"
    CHOICE_COUNT = "gen_ai.request.choice.count"
    # Response attributes
    FINISH_REASONS = "gen_ai.response.finish_reasons"
    RESPONSE_ID = "gen_ai.response.id"
    # Usage attributes
    INPUT_TOKENS = "gen_ai.usage.input_tokens"
    OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
    # Tool attributes
    TOOL_CALL_ID = "gen_ai.tool.call.id"
    TOOL_DESCRIPTION = "gen_ai.tool.description"
    TOOL_NAME = "gen_ai.tool.name"
    TOOL_TYPE = "gen_ai.tool.type"
    TOOL_ARGUMENTS = "gen_ai.tool.call.arguments"
    TOOL_RESULT = "gen_ai.tool.call.result"
    # Agent attributes
    AGENT_ID = "gen_ai.agent.id"
    # Client attributes
    # replaced TOKEN with T, because both ruff and bandit,
    # complain about TOKEN being a potential secret
    T_UNIT = "tokens"
    T_TYPE = "gen_ai.token.type"
    T_TYPE_INPUT = "input"
    T_TYPE_OUTPUT = "output"
    DURATION_UNIT = "s"
    # Agent attributes
    AGENT_NAME = "gen_ai.agent.name"
    AGENT_DESCRIPTION = "gen_ai.agent.description"
    CONVERSATION_ID = "gen_ai.conversation.id"
    DATA_SOURCE_ID = "gen_ai.data_source.id"
    OUTPUT_TYPE = "gen_ai.output.type"
    INPUT_MESSAGES = "gen_ai.input.messages"
    OUTPUT_MESSAGES = "gen_ai.output.messages"
    SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions"

    # Activity events
    EVENT_NAME = "event.name"
    SYSTEM_MESSAGE = "gen_ai.system.message"
    USER_MESSAGE = "gen_ai.user.message"
    ASSISTANT_MESSAGE = "gen_ai.assistant.message"
    TOOL_MESSAGE = "gen_ai.tool.message"
    CHOICE = "gen_ai.choice"

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
FINISH_REASON_MAP = {
    "stop": "stop",
    "content_filter": "content_filter",
    "tool_calls": "tool_call",
    "length": "length",
}


# region Telemetry utils


def _get_exporters(endpoint: str | None = None, connection_string: str | None = None) -> dict[str, list[Any]]:
    """Create the different exporters based on the connection string and endpoint."""
    from azure.monitor.opentelemetry.exporter import (  # pylint: disable=import-error,no-name-in-module
        AzureMonitorLogExporter,
        AzureMonitorMetricExporter,
        AzureMonitorTraceExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    exporters: dict[str, Any] = {}
    exporters.setdefault("log", [])
    exporters.setdefault("trace", [])
    exporters.setdefault("metric", [])
    if endpoint:
        exporters["log"].append(OTLPLogExporter(endpoint=endpoint))
        exporters["trace"].append(OTLPSpanExporter(endpoint=endpoint))
        exporters["metric"].append(OTLPMetricExporter(endpoint=endpoint))
    if connection_string:
        exporters["log"].append(AzureMonitorLogExporter(connection_string=connection_string))
        exporters["trace"].append(AzureMonitorTraceExporter(connection_string=connection_string))
        exporters["metric"].append(AzureMonitorMetricExporter(connection_string=connection_string))
    return exporters


def _configure_tracing(exporters: dict[str, list[Any]], resource: "Resource") -> None:
    from opentelemetry._events import set_event_logger_provider
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.metrics import set_meter_provider
    from opentelemetry.sdk._events import EventLoggerProvider
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.metrics.view import DropAggregation, View
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import set_tracer_provider

    # Tracing
    tracer_provider = TracerProvider(resource=resource)
    for exporter in exporters.get("trace", []):
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    set_tracer_provider(tracer_provider)

    # Logging
    logger_provider = LoggerProvider(resource=resource)
    for exporter in exporters.get("log", []):
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(logger_provider)
    logger = get_logger()
    if not any(isinstance(handler, LoggingHandler) for handler in logger.handlers):
        handler = LoggingHandler(logger_provider=logger_provider)
        logger.addHandler(handler)
    logger.setLevel(logging.NOTSET)

    # Events
    event_logger_provider = EventLoggerProvider(logger_provider)
    set_event_logger_provider(event_logger_provider)

    # metrics

    metric_readers = [
        PeriodicExportingMetricReader(exporter, export_interval_millis=5000) for exporter in exporters.get("metric", [])
    ]
    meter_provider = MeterProvider(
        metric_readers=metric_readers,
        resource=resource,
        views=[
            # Dropping all instrument names except for those starting with "agent_framework"
            View(instrument_name="*", aggregation=DropAggregation()),
            View(instrument_name="agent_framework*"),
            View(instrument_name="gen_ai*"),
        ],
    )
    # Sets the global default meter provider
    set_meter_provider(meter_provider)


OTEL_ENABLED_ENV_VAR = "ENABLE_OTEL"
SENSITIVE_DATA_ENV_VAR = "ENABLE_SENSITIVE_DATA"
MONITOR_CONNECTION_STRING_ENV_VAR = "MONITOR_CONNECTION_STRING"
MONITOR_LIVE_METRICS_ENV_VAR = "MONITOR_LIVE_METRICS"
OTLP_ENDPOINT_ENV_VAR = "OTLP_ENDPOINT"


class OtelSettings(AFBaseSettings):
    """Settings for Open Telemetry.

    The settings are first loaded from environment variables with
    the prefix 'AGENT_FRAMEWORK_GENAI_'.
    If the environment variables are not found, the settings can
    be loaded from a .env file with the encoding 'utf-8'.
    If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the
    settings are missing.

    Warning:
        Sensitive events should only be enabled on test and development environments.

    Args:
        enable_otel: Enable OpenTelemetry diagnostics. Default is False.
                    (Env var ENABLE_OTEL)
        enable_sensitive_data: Enable OpenTelemetry sensitive events. Default is False.
                    (Env var ENABLE_SENSITIVE_DATA)
        application_insights_connection_string: The Azure Monitor connection string. Default is None.
                    (Env var APPLICATION_INSIGHTS_CONNECTION_STRING)
        application_insights_live_metrics: Enable Azure Monitor live metrics. Default is False.
                    (Env var APPLICATION_INSIGHTS_LIVE_METRICS)
        otlp_endpoint:  The OpenTelemetry Protocol (OTLP) endpoint. Default is None.
                    (Env var OTLP_ENDPOINT)
    """

    env_prefix: ClassVar[str] = ""

    enable_otel: bool = False
    enable_sensitive_data: bool = False
    application_insights_connection_string: str | None = None
    application_insights_live_metrics: bool = False
    otlp_endpoint: str | None = None
    _executed_setup: bool = PrivateAttr(default=False)

    @property
    def ENABLED(self) -> bool:
        """Check if model diagnostics are enabled.

        Model diagnostics are enabled if either diagnostic is enabled or diagnostic with sensitive events is enabled.
        """
        return self.enable_otel or self.enable_sensitive_data

    @property
    def SENSITIVE_DATA_ENABLED(self) -> bool:
        """Check if sensitive events are enabled.

        Sensitive events are enabled if the diagnostic with sensitive events is enabled.
        """
        return self.enable_sensitive_data

    @property
    def is_setup(self) -> bool:
        """Check if the setup has been executed."""
        return self._executed_setup

    def setup_telemetry(self) -> None:
        """Setup telemetry based on the settings.

        If both connection_string and otlp_endpoint both will be used.
        """
        if not self.ENABLED or self._executed_setup:
            return

        if not self.application_insights_connection_string and not self.otlp_endpoint:
            logger.warning("Telemetry is enabled but no connection string or OTLP endpoint is provided.")
            return
        if self.application_insights_connection_string and self.otlp_endpoint:
            logger.warning("Both connection string and OTLP endpoint are provided. Azure Monitor will be used.")

        from opentelemetry.sdk.resources import Resource
        from opentelemetry.semconv.attributes import service_attributes

        resource = Resource.create({service_attributes.SERVICE_NAME: "agent_framework"})
        global_logger = logging.getLogger()
        global_logger.setLevel(logging.NOTSET)
        if self.application_insights_connection_string:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(
                connection_string=self.application_insights_connection_string,
                logger_name="agent_framework",
                resource=resource,
                enable_live_metrics=self.application_insights_live_metrics,
            )
        if self.otlp_endpoint:
            exporters = _get_exporters(endpoint=self.otlp_endpoint)
            _configure_tracing(exporters, resource)

        self._executed_setup = True


global OTEL_SETTINGS
OTEL_SETTINGS: OtelSettings = OtelSettings()


def setup_telemetry(
    enable_otel: bool | None = None,
    enable_sensitive_data: bool | None = None,
    otlp_endpoint: str | None = None,
    application_insights_connection_string: str | None = None,
    enable_live_metrics: bool | None = None,
) -> None:
    """Setup telemetry with optionally provided settings.

    All of these values can be set through environment variables or you can pass them here,
    in the case where both are present, the provided value takes precedence.

    If you have both connection_string and otlp_endpoint, the connection_string will be used.

    Args:
        enable_otel: Enable OpenTelemetry diagnostics. Default is False.
        enable_sensitive_data: Enable OpenTelemetry sensitive events. Default is False.
        otlp_endpoint:  The OpenTelemetry Protocol (OTLP) endpoint. Default is None.
        application_insights_connection_string: The Azure Monitor connection string. Default is None.
        enable_live_metrics: Enable Azure Monitor live metrics. Default is False.

    """
    global OTEL_SETTINGS
    if enable_otel is not None:
        OTEL_SETTINGS.enable_otel = enable_otel
    if enable_sensitive_data is not None:
        OTEL_SETTINGS.enable_sensitive_data = enable_sensitive_data
    if otlp_endpoint is not None:
        OTEL_SETTINGS.otlp_endpoint = otlp_endpoint
    if application_insights_connection_string is not None:
        OTEL_SETTINGS.application_insights_connection_string = application_insights_connection_string
    if enable_live_metrics is not None:
        OTEL_SETTINGS.application_insights_live_metrics = enable_live_metrics
    OTEL_SETTINGS.setup_telemetry()


# region Chat Client Telemetry


def _get_duration_histogram() -> "Histogram":
    return meter.create_histogram(
        name=Meters.LLM_OPERATION_DURATION,
        unit=OtelAttr.DURATION_UNIT,
        description="Captures the duration of operations of function-invoking chat clients",
        explicit_bucket_boundaries_advisory=OPERATION_DURATION_BUCKET_BOUNDARIES,
    )


def _get_token_usage_histogram() -> "Histogram":
    return meter.create_histogram(
        name=Meters.LLM_TOKEN_USAGE,
        unit=OtelAttr.T_UNIT,
        description="Captures the token usage of chat clients",
        explicit_bucket_boundaries_advisory=TOKEN_USAGE_BUCKET_BOUNDARIES,
    )


# region ChatClientProtocol


def _trace_get_response(
    func: Callable[..., Awaitable["ChatResponse"]],
    *,
    provider_name: str = "unknown",
) -> Callable[..., Awaitable["ChatResponse"]]:
    """Decorator to trace chat completion activities.

    Args:
        func: The function to trace.
        provider_name: The model provider name.
    """

    def decorator(func: Callable[..., Awaitable["ChatResponse"]]) -> Callable[..., Awaitable["ChatResponse"]]:
        """Inner decorator."""

        @wraps(func)
        async def trace_get_response(
            self: "ChatClientProtocol",
            messages: "str | ChatMessage | list[str] | list[ChatMessage]",
            **kwargs: Any,
        ) -> "ChatResponse":
            global OTEL_SETTINGS
            if not OTEL_SETTINGS.ENABLED:
                # If model diagnostics are not enabled, just return the completion
                return await func(
                    self,
                    messages=messages,
                    **kwargs,
                )
            setup_telemetry()
            if "token_usage_histogram" not in self.additional_properties:
                self.additional_properties["token_usage_histogram"] = _get_token_usage_histogram()
            if "operation_duration_histogram" not in self.additional_properties:
                self.additional_properties["operation_duration_histogram"] = _get_duration_histogram()
            model_id = str(kwargs.get("ai_model_id") or getattr(self, "ai_model_id", "unknown"))
            service_url = str(
                service_url_func()
                if (service_url_func := getattr(self, "service_url", None)) and callable(service_url_func)
                else "unknown"
            )
            attributes = _get_span_attributes(
                operation_name=OtelAttr.CHAT_COMPLETION_OPERATION,
                provider_name=provider_name,
                model_id=model_id,
                service_url=service_url,
                **kwargs,
            )
            with _get_span(attributes=attributes, span_name_attribute=SpanAttributes.LLM_REQUEST_MODEL) as span:
                if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED and messages:
                    _capture_messages(span=span, provider_name=provider_name, messages=messages)
                start_time_stamp = perf_counter()
                end_time_stamp: float | None = None
                try:
                    response = await func(self, messages=messages, **kwargs)
                    end_time_stamp = perf_counter()
                except Exception as exception:
                    end_time_stamp = perf_counter()
                    _capture_exception(span=span, exception=exception, timestamp=time_ns())
                    raise
                else:
                    duration = (end_time_stamp or perf_counter()) - start_time_stamp
                    attributes = _get_response_attributes(attributes, response, duration=duration)
                    _capture_response(
                        span=span,
                        attributes=attributes,
                        token_usage_histogram=self.additional_properties["token_usage_histogram"],
                        operation_duration_histogram=self.additional_properties["operation_duration_histogram"],
                    )
                    if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED and response.messages:
                        _capture_messages(
                            span=span,
                            provider_name=provider_name,
                            messages=response.messages,
                            finish_reason=response.finish_reason,
                            output=True,
                        )
                    return response

        return trace_get_response

    return decorator(func)


def _trace_get_streaming_response(
    func: Callable[..., AsyncIterable["ChatResponseUpdate"]],
    *,
    provider_name: str = "unknown",
) -> Callable[..., AsyncIterable["ChatResponseUpdate"]]:
    """Decorator to trace streaming chat completion activities.

    Args:
        func: The function to trace.
        provider_name: The model provider name.
    """

    def decorator(
        func: Callable[..., AsyncIterable["ChatResponseUpdate"]],
    ) -> Callable[..., AsyncIterable["ChatResponseUpdate"]]:
        """Inner decorator."""

        @wraps(func)
        async def trace_get_streaming_response(
            self: "ChatClientProtocol", messages: "str | ChatMessage | list[str] | list[ChatMessage]", **kwargs: Any
        ) -> AsyncIterable["ChatResponseUpdate"]:
            global OTEL_SETTINGS
            if not OTEL_SETTINGS.ENABLED:
                # If model diagnostics are not enabled, just return the completion
                async for update in func(self, messages=messages, **kwargs):
                    yield update
                return
            setup_telemetry()
            if "token_usage_histogram" not in self.additional_properties:
                self.additional_properties["token_usage_histogram"] = _get_token_usage_histogram()
            if "operation_duration_histogram" not in self.additional_properties:
                self.additional_properties["operation_duration_histogram"] = _get_duration_histogram()

            model_id = kwargs.get("ai_model_id") or getattr(self, "ai_model_id", None)
            service_url = str(
                service_url_func()
                if (service_url_func := getattr(self, "service_url", None)) and callable(service_url_func)
                else "unknown"
            )
            attributes = _get_span_attributes(
                operation_name=OtelAttr.CHAT_COMPLETION_OPERATION,
                provider_name=provider_name,
                model_id=model_id,
                service_url=service_url,
                **kwargs,
            )
            all_updates: list["ChatResponseUpdate"] = []
            with _get_span(attributes=attributes, span_name_attribute=SpanAttributes.LLM_REQUEST_MODEL) as span:
                if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED and messages:
                    _capture_messages(
                        span=span,
                        provider_name=provider_name,
                        messages=messages,
                    )
                start_time_stamp = perf_counter()
                end_time_stamp: float | None = None
                try:
                    async for update in func(self, messages=messages, **kwargs):
                        all_updates.append(update)
                        yield update
                    end_time_stamp = perf_counter()
                except Exception as exception:
                    end_time_stamp = perf_counter()
                    _capture_exception(span=span, exception=exception, timestamp=time_ns())
                    raise
                else:
                    duration = (end_time_stamp or perf_counter()) - start_time_stamp
                    from ._types import ChatResponse

                    response = ChatResponse.from_chat_response_updates(all_updates)
                    attributes = _get_response_attributes(attributes, response, duration=duration)
                    _capture_response(
                        span=span,
                        attributes=attributes,
                        token_usage_histogram=self.additional_properties["token_usage_histogram"],
                        operation_duration_histogram=self.additional_properties["operation_duration_histogram"],
                    )

                    if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED and response.messages:
                        _capture_messages(
                            span=span,
                            provider_name=provider_name,
                            messages=response.messages,
                            finish_reason=response.finish_reason,
                            output=True,
                        )

        return trace_get_streaming_response

    return decorator(func)


def use_telemetry(
    chat_client: type[TChatClient],
) -> type[TChatClient]:
    """Class decorator that enables telemetry for a chat client.

    This needs to be applied on the class itself, not a instance of it.

    To set the proper provider name, the chat client class should have a class variable
    OTEL_PROVIDER_NAME.
    """
    if getattr(chat_client, OPEN_TELEMETRY_CHAT_CLIENT_MARKER, False):
        # Already decorated
        return chat_client

    provider_name = str(getattr(chat_client, "OTEL_PROVIDER_NAME", "unknown"))

    if provider_name not in GenAISystem.__members__:
        # that list is not complete, so just logging, no consequences.
        logger.debug(
            f"The provider name '{provider_name}' is not recognized. "
            f"Consider using one of the following: {', '.join(GenAISystem.__members__.keys())}"
        )
    try:
        chat_client.get_response = _trace_get_response(chat_client.get_response, provider_name=provider_name)  # type: ignore
    except AttributeError as exc:
        raise ChatClientInitializationError(
            f"The chat client {chat_client.__name__} does not have a get_response method.", exc
        ) from exc
    try:
        chat_client.get_streaming_response = _trace_get_streaming_response(  # type: ignore
            chat_client.get_streaming_response, provider_name=provider_name
        )
    except AttributeError as exc:
        raise ChatClientInitializationError(
            f"The chat client {chat_client.__name__} does not have a get_streaming_response method.", exc
        ) from exc

    setattr(chat_client, OPEN_TELEMETRY_CHAT_CLIENT_MARKER, True)

    return chat_client


# region Agent


def _trace_agent_run(
    run_func: Callable[..., Awaitable["AgentRunResponse"]],
    provider_name: str,
) -> Callable[..., Awaitable["AgentRunResponse"]]:
    """Decorator to trace chat completion activities.

    Args:
        run_func: The function to trace.
        provider_name: The system name used for Open Telemetry.
    """

    @wraps(run_func)
    async def trace_run(
        self: "AgentProtocol",
        messages: "str | ChatMessage | list[str] | list[ChatMessage] | None" = None,
        *,
        thread: "AgentThread | None" = None,
        **kwargs: Any,
    ) -> "AgentRunResponse":
        global OTEL_SETTINGS

        if not OTEL_SETTINGS.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            return await run_func(self, messages=messages, thread=thread, **kwargs)
        setup_telemetry()
        attributes = _get_span_attributes(
            operation_name=OtelAttr.AGENT_INVOKE_OPERATION,
            provider_name=provider_name,
            agent_id=self.id,
            agent_name=self.display_name,
            agent_description=self.description,
            thread_id=thread.service_thread_id if thread else None,
            **kwargs,
        )
        with _get_span(attributes=attributes, span_name_attribute=OtelAttr.AGENT_NAME) as span:
            if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED and messages:
                _capture_messages(
                    span=span,
                    provider_name=provider_name,
                    messages=messages,
                    system_instructions=getattr(self, "instructions", None),
                )
            try:
                response = await run_func(self, messages=messages, thread=thread, **kwargs)
            except Exception as exception:
                _capture_exception(span=span, exception=exception, timestamp=time_ns())
                raise
            else:
                attributes = _get_response_attributes(attributes, response)
                _capture_response(span=span, attributes=attributes)
                if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED and response.messages:
                    _capture_messages(
                        span=span,
                        provider_name=provider_name,
                        messages=response.messages,
                        output=True,
                    )
                return response

    return trace_run


def _trace_agent_run_stream(
    run_streaming_func: Callable[..., AsyncIterable["AgentRunResponseUpdate"]],
    provider_name: str,
) -> Callable[..., AsyncIterable["AgentRunResponseUpdate"]]:
    """Decorator to trace streaming agent run activities.

    Args:
        agent: The agent that is wrapped.
        run_streaming_func: The function to trace.
        provider_name: The system name used for Open Telemetry.
    """

    @wraps(run_streaming_func)
    async def trace_run_streaming(
        self: "AgentProtocol",
        messages: "str | ChatMessage | list[str] | list[ChatMessage] | None" = None,
        *,
        thread: "AgentThread | None" = None,
        **kwargs: Any,
    ) -> AsyncIterable["AgentRunResponseUpdate"]:
        global OTEL_SETTINGS

        if not OTEL_SETTINGS.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            async for streaming_agent_response in run_streaming_func(self, messages=messages, thread=thread, **kwargs):
                yield streaming_agent_response
            return

        from ._types import AgentRunResponse

        all_updates: list["AgentRunResponseUpdate"] = []

        setup_telemetry()
        attributes = _get_span_attributes(
            operation_name=OtelAttr.AGENT_INVOKE_OPERATION,
            provider_name=provider_name,
            agent_id=self.id,
            agent_name=self.display_name,
            agent_description=self.description,
            thread_id=thread.service_thread_id if thread else None,
            **kwargs,
        )
        with _get_span(attributes=attributes, span_name_attribute=OtelAttr.AGENT_NAME) as span:
            if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED and messages:
                _capture_messages(
                    span=span,
                    provider_name=provider_name,
                    messages=messages,
                    system_instructions=getattr(self, "instructions", None),
                )
            try:
                async for update in run_streaming_func(self, messages=messages, thread=thread, **kwargs):
                    all_updates.append(update)
                    yield update
            except Exception as exception:
                _capture_exception(span=span, exception=exception, timestamp=time_ns())
                raise
            else:
                response = AgentRunResponse.from_agent_run_response_updates(all_updates)
                attributes = _get_response_attributes(attributes, response)
                _capture_response(span=span, attributes=attributes)
                if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED and response.messages:
                    _capture_messages(
                        span=span,
                        provider_name=provider_name,
                        messages=response.messages,
                        output=True,
                    )

    return trace_run_streaming


def use_agent_telemetry(
    agent: type[TAgent],
) -> type[TAgent]:
    """Class decorator that enables telemetry for an agent."""
    provider_name = str(getattr(agent, "AGENT_SYSTEM_NAME", "Unknown"))
    try:
        agent.run = _trace_agent_run(agent.run, provider_name)  # type: ignore
    except AttributeError as exc:
        raise AgentInitializationError(f"The agent {agent.__name__} does not have a run method.", exc) from exc
    try:
        agent.run_stream = _trace_agent_run_stream(agent.run_stream, provider_name)  # type: ignore
    except AttributeError as exc:
        raise AgentInitializationError(f"The agent {agent.__name__} does not have a run_stream method.", exc) from exc
    setattr(agent, OPEN_TELEMETRY_AGENT_MARKER, True)
    return agent


# region Otel Helpers


def get_function_span_attributes(function: "AIFunction[Any, Any]", tool_call_id: str | None = None) -> dict[str, str]:
    """Get the span attributes for the given function.

    Args:
        function: The function for which to get the span attributes.
        tool_call_id: The id of the tool_call that was requested.

    Returns:
        dict[str, str]: The span attributes.
    """
    attributes: dict[str, str] = {
        OtelAttr.OPERATION: OtelAttr.TOOL_EXECUTION_OPERATION,
        OtelAttr.TOOL_NAME: function.name,
        OtelAttr.TOOL_CALL_ID: tool_call_id or "unknown",
        OtelAttr.TOOL_TYPE: "function",
    }
    if function.description:
        attributes[OtelAttr.TOOL_DESCRIPTION] = function.description
    return attributes


def get_function_span(
    attributes: dict[str, str],
) -> "_AgnosticContextManager[Span]":
    """Starts a span for the given function.

    Args:
        attributes: The span attributes.

    Returns:
        trace.Span: The started span as a context manager.
    """
    return tracer.start_as_current_span(
        name=f"{attributes[OtelAttr.OPERATION]} {attributes[OtelAttr.TOOL_NAME]}",
        attributes=attributes,
        set_status_on_exception=False,
        end_on_exit=True,
        record_exception=False,
    )


@contextmanager
def _get_span(
    attributes: dict[str, Any],
    span_name_attribute: str,
) -> Generator[Span, Any, Any]:
    """Start a span for a agent run."""
    span = tracer.start_span(f"{attributes[OtelAttr.OPERATION]} {attributes[span_name_attribute]}")
    span.set_attributes(attributes)
    with use_span(
        span=span,
        end_on_exit=True,
        record_exception=False,
        set_status_on_exception=False,
    ) as current_span:
        yield current_span


def _get_span_attributes(**kwargs: Any) -> dict[str, Any]:
    """Get the span attributes from a kwargs dictionary."""
    attributes: dict[str, Any] = {}
    if operation_name := kwargs.get("operation_name"):
        attributes[OtelAttr.OPERATION] = operation_name
    if choice_count := kwargs.get("choice_count", 1):
        attributes[OtelAttr.CHOICE_COUNT] = choice_count
    if operation_name := kwargs.get("operation_name"):
        attributes[OtelAttr.OPERATION] = operation_name
    if system_name := kwargs.get("system_name"):
        attributes[SpanAttributes.LLM_SYSTEM] = system_name
    if provider_name := kwargs.get("provider_name"):
        attributes[OtelAttr.PROVIDER_NAME] = provider_name
    attributes[SpanAttributes.LLM_REQUEST_MODEL] = kwargs.get("model_id", "unknown")
    if service_url := kwargs.get("service_url"):
        attributes[OtelAttr.ADDRESS] = service_url
    if conversation_id := kwargs.get("conversation_id"):
        attributes[OtelAttr.CONVERSATION_ID] = conversation_id
    if seed := kwargs.get("seed"):
        attributes[OtelAttr.SEED] = seed
    if frequency_penalty := kwargs.get("frequency_penalty"):
        attributes[OtelAttr.FREQUENCY_PENALTY] = frequency_penalty
    if max_tokens := kwargs.get("max_tokens"):
        attributes[SpanAttributes.LLM_REQUEST_MAX_TOKENS] = max_tokens
    if stop := kwargs.get("stop"):
        attributes[OtelAttr.STOP_SEQUENCES] = stop
    if temperature := kwargs.get("temperature"):
        attributes[SpanAttributes.LLM_REQUEST_TEMPERATURE] = temperature
    if top_p := kwargs.get("top_p"):
        attributes[SpanAttributes.LLM_REQUEST_TOP_P] = top_p
    if presence_penalty := kwargs.get("presence_penalty"):
        attributes[OtelAttr.PRESENCE_PENALTY] = presence_penalty
    if top_k := kwargs.get("top_k"):
        attributes[OtelAttr.TOP_K] = top_k
    if encoding_formats := kwargs.get("encoding_formats"):
        attributes[OtelAttr.ENCODING_FORMATS] = json.dumps(
            encoding_formats if isinstance(encoding_formats, list) else [encoding_formats]
        )
    if error := kwargs.get("error"):
        attributes[OtelAttr.ERROR_TYPE] = type(error).__name__
    # agent attributes
    if agent_id := kwargs.get("agent_id"):
        attributes[OtelAttr.AGENT_ID] = agent_id
    if agent_name := kwargs.get("agent_name"):
        attributes[OtelAttr.AGENT_NAME] = agent_name
    if agent_description := kwargs.get("agent_description"):
        attributes[OtelAttr.AGENT_DESCRIPTION] = agent_description
    if thread_id := kwargs.get("thread_id"):
        # override if thread is set
        attributes[OtelAttr.CONVERSATION_ID] = thread_id
    return attributes


def _capture_exception(span: Span, exception: Exception, timestamp: int | None = None) -> None:
    """Set an error for spans."""
    span.set_attribute(OtelAttr.ERROR_TYPE, type(exception).__name__)
    span.record_exception(exception=exception, timestamp=timestamp)
    span.set_status(status=StatusCode.ERROR, description=repr(exception))


def _capture_messages(
    span: Span,
    provider_name: str,
    messages: "str | ChatMessage | list[str] | list[ChatMessage]",
    system_instructions: str | list[str] | None = None,
    output: bool = False,
    finish_reason: "FinishReason | None" = None,
) -> None:
    """Log messages with extra information."""
    from ._clients import prepare_messages

    prepped = prepare_messages(messages)
    for index, message in enumerate(prepped):
        logger.info(
            message.model_dump_json(exclude_none=True),
            extra={
                OtelAttr.EVENT_NAME: OtelAttr.CHOICE if output else ROLE_EVENT_MAP.get(message.role.value),
                OtelAttr.PROVIDER_NAME: provider_name,
                ChatMessageListTimestampFilter.INDEX_KEY: index,
            },
        )
    otel_messages = [_to_otel_message(message) for message in prepped]
    if finish_reason:
        otel_messages[-1]["finish_reason"] = FINISH_REASON_MAP[finish_reason.value]
    span.set_attribute(OtelAttr.OUTPUT_MESSAGES if output else OtelAttr.INPUT_MESSAGES, json.dumps(otel_messages))
    if system_instructions:
        if not isinstance(system_instructions, list):
            system_instructions = [system_instructions]
        otel_sys_instructions = [{"type": "text", "content": instruction} for instruction in system_instructions]
        span.set_attribute(OtelAttr.SYSTEM_INSTRUCTIONS, json.dumps(otel_sys_instructions))


def _to_otel_message(message: "ChatMessage") -> dict[str, Any]:
    """Create a otel representation of a message."""
    return {"role": message.role.value, "parts": [_to_otel_part(content) for content in message.contents]}


def _to_otel_part(content: "Contents") -> dict[str, Any] | None:
    """Create a otel representation of a Content."""
    match content.type:
        case "text":
            return {"type": "text", "content": content.text}
        case "function_call":
            return {"type": "tool_call", "id": content.call_id, "name": content.name, "arguments": content.arguments}
        case "function_result":
            return {"type": "tool_call_response", "id": content.call_id, "response": content.result}
        case _:
            # GenericPart in otel output messages json spec.
            # just required type, and arbitrary other fields.
            return content.model_dump(exclude_none=True)
    return None


def _get_response_attributes(
    attributes: dict[str, Any],
    response: "ChatResponse | AgentRunResponse",
    duration: float | None = None,
) -> dict[str, Any]:
    """Get the response attributes from a response."""
    if response.response_id:
        attributes[OtelAttr.RESPONSE_ID] = response.response_id
    finish_reason = getattr(response, "finish_reason", None)
    if not finish_reason:
        finish_reason = (
            getattr(response.raw_representation, "finish_reason", None) if response.raw_representation else None
        )
    if finish_reason:
        attributes[OtelAttr.FINISH_REASONS] = json.dumps([finish_reason.value])
    if ai_model_id := getattr(response, "ai_model_id", None):
        attributes[SpanAttributes.LLM_RESPONSE_MODEL] = ai_model_id
    if usage := response.usage_details:
        if usage.input_token_count:
            attributes[OtelAttr.INPUT_TOKENS] = usage.input_token_count
        if usage.output_token_count:
            attributes[OtelAttr.OUTPUT_TOKENS] = usage.output_token_count
    if duration:
        attributes[Meters.LLM_OPERATION_DURATION] = duration
    return attributes


GEN_AI_METRIC_ATTRIBUTES = (
    OtelAttr.OPERATION,
    OtelAttr.PROVIDER_NAME,
    SpanAttributes.LLM_REQUEST_MODEL,
    SpanAttributes.LLM_RESPONSE_MODEL,
    OtelAttr.ADDRESS,
    OtelAttr.PORT,
)


def _capture_response(
    span: Span,
    attributes: dict[str, Any],
    operation_duration_histogram: "Histogram | None" = None,
    token_usage_histogram: "Histogram | None" = None,
) -> None:
    """Set the response for a given span."""
    span.set_attributes(attributes)
    attrs: dict[str, Any] = {k: v for k, v in attributes.items() if k in GEN_AI_METRIC_ATTRIBUTES}
    if token_usage_histogram and (input_tokens := attributes.get(OtelAttr.INPUT_TOKENS)):
        token_usage_histogram.record(
            input_tokens, attributes={**attrs, SpanAttributes.LLM_TOKEN_TYPE: OtelAttr.T_TYPE_INPUT}
        )
    if token_usage_histogram and (output_tokens := attributes.get(OtelAttr.OUTPUT_TOKENS)):
        token_usage_histogram.record(output_tokens, {**attrs, SpanAttributes.LLM_TOKEN_TYPE: OtelAttr.T_TYPE_OUTPUT})
    if operation_duration_histogram and (duration := attributes.get(Meters.LLM_OPERATION_DURATION)):
        if OtelAttr.ERROR_TYPE in attributes:
            attrs[OtelAttr.ERROR_TYPE] = attributes[OtelAttr.ERROR_TYPE]
        operation_duration_histogram.record(duration, attributes=attrs)
