# Copyright (c) Microsoft. All rights reserved.

import contextlib
import json
import logging
from collections.abc import AsyncIterable, Awaitable, Callable, Generator, Mapping
from enum import Enum
from functools import wraps
from time import perf_counter, time_ns
from typing import TYPE_CHECKING, Any, ClassVar, Final, TypeVar

from opentelemetry import metrics, trace
from opentelemetry.semconv_ai import GenAISystem, Meters, SpanAttributes
from pydantic import BaseModel, PrivateAttr

from . import __version__ as version_info
from ._logging import get_logger
from ._pydantic import AFBaseSettings
from .exceptions import AgentInitializationError, ChatClientInitializationError

if TYPE_CHECKING:  # pragma: no cover
    from azure.core.credentials import TokenCredential
    from opentelemetry.sdk._events import EventLoggerProvider
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs._internal.export import LogExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import MetricExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SpanExporter
    from opentelemetry.trace import Tracer
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

    # Workflow attributes
    WORKFLOW_ID = "workflow.id"
    WORKFLOW_DEFINITION = "workflow.definition"
    WORKFLOW_BUILD_SPAN = "workflow.build"
    WORKFLOW_RUN_SPAN = "workflow.run"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_ERROR = "workflow.error"
    # Workflow Build attributes
    BUILD_STARTED = "build.started"
    BUILD_VALIDATION_COMPLETED = "build.validation_completed"
    BUILD_COMPLETED = "build.completed"
    BUILD_ERROR = "build.error"
    BUILD_ERROR_MESSAGE = "build.error.message"
    BUILD_ERROR_TYPE = "build.error.type"
    # Workflow executor attributes
    EXECUTOR_PROCESS_SPAN = "executor.process"
    EXECUTOR_ID = "executor.id"
    EXECUTOR_TYPE = "executor.type"
    # Edge group attributes
    EDGE_GROUP_PROCESS_SPAN = "edge_group.process"
    EDGE_GROUP_TYPE = "edge_group.type"
    EDGE_GROUP_ID = "edge_group.id"
    EDGE_GROUP_DELIVERED = "edge_group.delivered"
    EDGE_GROUP_DELIVERY_STATUS = "edge_group.delivery_status"
    # Message attributes
    MESSAGE_SEND_SPAN = "message.send"
    MESSAGE_SOURCE_ID = "message.source_id"
    MESSAGE_TARGET_ID = "message.target_id"
    MESSAGE_TYPE = "message.type"
    MESSAGE_DESTINATION_EXECUTOR_ID = "message.destination_executor_id"

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
        """Return the string representation of the enum member."""
        return self.value

    def __str__(self) -> str:
        """Return the string representation of the enum member."""
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


def _get_otlp_exporters(endpoints: list[str]) -> list["LogExporter | SpanExporter | MetricExporter"]:
    """Create standard OTLP Exporters for the supplied endpoints."""
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    exporters: list["LogExporter | SpanExporter | MetricExporter"] = []

    for endpoint in endpoints:
        exporters.append(OTLPLogExporter(endpoint=endpoint))
        exporters.append(OTLPSpanExporter(endpoint=endpoint))
        exporters.append(OTLPMetricExporter(endpoint=endpoint))
    return exporters


def _get_azure_monitor_exporters(
    connection_strings: list[str],
    credential: "TokenCredential | None" = None,
) -> list["LogExporter | SpanExporter | MetricExporter"]:
    """Create Azure Monitor Exporters, based on the connection strings and optionally the credential."""
    from azure.monitor.opentelemetry.exporter import (
        AzureMonitorLogExporter,
        AzureMonitorMetricExporter,
        AzureMonitorTraceExporter,
    )

    exporters: list["LogExporter | SpanExporter | MetricExporter"] = []
    for conn_string in connection_strings:
        exporters.append(AzureMonitorLogExporter(connection_string=conn_string, credential=credential))
        exporters.append(AzureMonitorTraceExporter(connection_string=conn_string, credential=credential))
        exporters.append(AzureMonitorMetricExporter(connection_string=conn_string, credential=credential))
    return exporters


def get_exporters(
    otlp_endpoints: list[str] | None = None,
    connection_strings: list[str] | None = None,
    credential: "TokenCredential | None" = None,
) -> list["LogExporter | SpanExporter | MetricExporter"]:
    """Add additional exporters to the existing configuration.

    If you supply exporters, those will be added to the relevant providers directly.
    If you supply endpoints or connection strings, new exporters will be created and added.
    OTLP_endpoints will be used to create a `OTLPLogExporter`, `OTLPMetricExporter` and `OTLPSpanExporter`
    Connection_strings will be used to create AzureMonitorExporters.

    If a endpoint or connection string is already configured, through the environment variables, it will be skipped.
    If you call this method twice with the same additional endpoint or connection string, it will be added twice.

    Args:
        otlp_endpoints: A list of OpenTelemetry Protocol (OTLP) endpoints. Default is None.
        connection_strings: A list of Azure Monitor connection strings. Default is None.
        credential: The credential to use for Azure Monitor Entra ID authentication. Default is None.
    """
    new_exporters: list["LogExporter | SpanExporter | MetricExporter"] = []
    if otlp_endpoints:
        new_exporters.extend(_get_otlp_exporters(endpoints=otlp_endpoints))

    if connection_strings:
        new_exporters.extend(
            _get_azure_monitor_exporters(
                connection_strings=connection_strings,
                credential=credential,
            )
        )
    return new_exporters


def _create_resource() -> "Resource":
    import os

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.attributes import service_attributes

    service_name = os.getenv("OTEL_SERVICE_NAME", "agent_framework")

    return Resource.create({service_attributes.SERVICE_NAME: service_name})


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
        applicationinsights_connection_string: The Azure Monitor connection string. Default is None.
                    (Env var APPLICATIONINSIGHTS_CONNECTION_STRING)
        applicationinsights_live_metrics: Enable Azure Monitor live metrics. Default is False.
                    (Env var APPLICATIONINSIGHTS_LIVE_METRICS)
        otlp_endpoint:  The OpenTelemetry Protocol (OTLP) endpoint. Default is None.
                    (Env var OTLP_ENDPOINT)
    """

    env_prefix: ClassVar[str] = ""

    enable_otel: bool = False
    enable_sensitive_data: bool = False
    applicationinsights_connection_string: str | list[str] | None = None
    applicationinsights_live_metrics: bool = False
    otlp_endpoint: str | list[str] | None = None
    _resource: "Resource" = PrivateAttr(default_factory=_create_resource)
    _executed_setup: bool = PrivateAttr(default=False)
    _tracer_provider: "TracerProvider | None" = PrivateAttr(default=None)
    _meter_provider: "MeterProvider | None" = PrivateAttr(default=None)
    _logger_provider: "LoggerProvider | None" = PrivateAttr(default=None)
    _event_logger_provider: "EventLoggerProvider | None" = PrivateAttr(default=None)

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

    @property
    def resource(self) -> "Resource":
        """Get the resource."""
        return self._resource

    @resource.setter
    def resource(self, value: "Resource") -> None:
        """Set the resource."""
        self._resource = value

    def setup_observability(
        self,
        credential: "TokenCredential | None" = None,
        additional_exporters: list["LogExporter | SpanExporter | MetricExporter"] | None = None,
        force_setup: bool = False,
    ) -> None:
        """Setup telemetry based on the settings.

        Args:
            credential: The credential to use for Azure Monitor Entra ID authentication. Default is None.
            additional_exporters: A list of additional exporters to add to the configuration. Default is None.
            force_setup: Force the setup to be executed even if it has already been executed. Default is False.
        """
        if (not self.ENABLED) or (self._executed_setup and not force_setup):
            return

        global_logger = logging.getLogger()
        global_logger.setLevel(logging.NOTSET)
        exporters: list["LogExporter | SpanExporter | MetricExporter"] = additional_exporters or []
        if self.otlp_endpoint:
            exporters.extend(
                _get_otlp_exporters(
                    self.otlp_endpoint if isinstance(self.otlp_endpoint, list) else [self.otlp_endpoint]
                )
            )
        if self.applicationinsights_connection_string:
            exporters.extend(
                _get_azure_monitor_exporters(
                    connection_strings=(
                        self.applicationinsights_connection_string
                        if isinstance(self.applicationinsights_connection_string, list)
                        else [self.applicationinsights_connection_string]
                    ),
                    credential=credential,
                )
            )
        self._configure_providers(exporters)
        self._executed_setup = True
        if self.applicationinsights_connection_string and self.applicationinsights_live_metrics:
            from azure.monitor.opentelemetry import configure_azure_monitor

            conn_strings = (
                self.applicationinsights_connection_string
                if isinstance(self.applicationinsights_connection_string, list)
                else [self.applicationinsights_connection_string]
            )
            for con_str in conn_strings:
                # only configure using this for live_metrics, ignore the rest.
                configure_azure_monitor(
                    connection_string=con_str,
                    credential=credential,
                    logger_name="agent_framework",
                    resource=self.resource,
                    enable_live_metrics=self.applicationinsights_live_metrics,
                    disable_logging=True,
                    disable_metric=True,
                    disable_tracing=True,
                )

    def check_endpoint_already_configured(self, otlp_endpoint: str) -> bool:
        """Check if the endpoint is already configured.

        Returns:
            True if the endpoint is already configured, False otherwise.
        """
        if not self.otlp_endpoint:
            return False
        return otlp_endpoint not in (
            self.otlp_endpoint if isinstance(self.otlp_endpoint, list) else [self.otlp_endpoint]
        )

    def check_connection_string_already_configured(self, connection_string: str) -> bool:
        """Check if the connection string is already configured.

        Returns:
            True if the connection string is already configured, False otherwise.
        """
        if not self.applicationinsights_connection_string:
            return False
        return connection_string not in (
            self.applicationinsights_connection_string
            if isinstance(self.applicationinsights_connection_string, list)
            else [self.applicationinsights_connection_string]
        )

    def _configure_providers(self, exporters: list["LogExporter | MetricExporter | SpanExporter"]) -> None:
        """Configure tracing, logging, events and metrics with the provided exporters."""
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._events import EventLoggerProvider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs._internal.export import LogExporter
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import MetricExporter, PeriodicExportingMetricReader
        from opentelemetry.sdk.metrics.view import DropAggregation, View
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

        # Use SimpleSpanProcessor for in-memory exporter (tests) so spans are
        # exported synchronously and immediately available via
        # InMemorySpanExporter.get_finished_spans(). For all other exporters
        # keep using the BatchSpanProcessor behavior.

        # Tracing
        if not self._executed_setup:
            new_tracer_provider = TracerProvider(resource=self.resource)
            # setting global tracer provider, other libaries can use this,
            # but if another global tracer provider is already set this will not override it.
            trace.set_tracer_provider(new_tracer_provider)
        tracer_provider = trace.get_tracer_provider()
        for exporter in exporters:
            if not isinstance(exporter, SpanExporter):
                continue
            if (add_span_processor := getattr(tracer_provider, "add_span_processor", None)) and callable(
                add_span_processor
            ):
                add_span_processor(BatchSpanProcessor(exporter))

        # Logging
        if not self._logger_provider:
            self._logger_provider = LoggerProvider(resource=self.resource)

        [
            self._logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
            for exporter in exporters
            if isinstance(exporter, LogExporter)
        ]
        logger = get_logger()
        if not any(isinstance(handler, LoggingHandler) for handler in logger.handlers):
            handler = LoggingHandler(logger_provider=self._logger_provider)
            logger.addHandler(handler)
        logger.setLevel(logging.NOTSET)
        set_logger_provider(self._logger_provider)
        # Events
        if not self._event_logger_provider:
            self._event_logger_provider = EventLoggerProvider(self._logger_provider)

        # metrics
        meter_provider = MeterProvider(
            metric_readers=[
                PeriodicExportingMetricReader(exporter, export_interval_millis=5000)
                for exporter in exporters
                if isinstance(exporter, MetricExporter)
            ],
            resource=self.resource,
            views=[
                # Dropping all instrument names except for those starting with "agent_framework"
                View(instrument_name="*", aggregation=DropAggregation()),
                View(instrument_name="agent_framework*"),
                View(instrument_name="gen_ai*"),
            ],
        )
        metrics.set_meter_provider(meter_provider)


global OTEL_SETTINGS
OTEL_SETTINGS: OtelSettings = OtelSettings()


def get_tracer(
    instrumenting_module_name: str = "agent_framework",
    instrumenting_library_version: str = version_info,
    schema_url: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> "trace.Tracer":
    """Returns a `Tracer` for use by the given instrumentation library.

    This function is a convenience wrapper for
    trace.get_tracer()
    replicating the behavior of opentelemetry.trace.TracerProvider.get_tracer.

    If tracer_provider is omitted the current configured one is used.
    """
    return trace.get_tracer(
        instrumenting_module_name=instrumenting_module_name,
        instrumenting_library_version=instrumenting_library_version,
        schema_url=schema_url,
        attributes=attributes,
    )


def get_meter(
    name: str = "agent_framework",
    version: str = version_info,
    schema_url: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> "metrics.Meter":
    """Returns a `Meter` for Agent Framework.

    This is a convenience wrapper for
    metrics.get_meter() replicating the behavior of
    opentelemetry.metrics.get_meter().

    Args:
        name: Optional name, default is "agent_framework". The name of the
            instrumenting library.

        version: Optional. The version of `agent_framework`, default is the
            current version of the package.

        schema_url: Optional. Specifies the Schema URL of the emitted telemetry.
        attributes: Optional. Attributes that are associated with the emitted telemetry.
    """
    return metrics.get_meter(name=name, version=version, schema_url=schema_url, attributes=attributes)


def setup_observability(
    enable_sensitive_data: bool | None = None,
    otlp_endpoint: str | list[str] | None = None,
    applicationinsights_connection_string: str | list[str] | None = None,
    credential: "TokenCredential | None" = None,
    enable_live_metrics: bool | None = None,
    exporters: list["LogExporter | SpanExporter | MetricExporter"] | None = None,
) -> None:
    """Setup telemetry with optionally provided settings, it is implied that you want to enable telemetry.

    All of these values can be set through environment variables or you can pass them here,
    in the case where both are present, the provided value takes precedence.

    If you have both connection_string and otlp_endpoint, the connection_string will be used.

    Args:
        enable_sensitive_data: Enable OpenTelemetry sensitive events. Default is False.
        otlp_endpoint:  The OpenTelemetry Protocol (OTLP) endpoint. Default is None.
            Will be used to create a `OTLPLogExporter`, `OTLPMetricExporter` and `OTLPSpanExporter`
        applicationinsights_connection_string: The Azure Monitor connection string. Default is None.
            Will be used to create AzureMonitorExporters.
        credential: The credential to use for Azure Monitor Entra ID authentication.
            Default is None.
        enable_live_metrics: Enable Azure Monitor live metrics. Default is False.
        exporters: a list of exporters, for logs, metrics or spans, or any combination,
            these will be added directly, and allows you to customize the spans completely

    """
    global OTEL_SETTINGS
    # Update the otel settings with the provided values
    OTEL_SETTINGS.enable_otel = True
    if enable_sensitive_data is not None:
        OTEL_SETTINGS.enable_sensitive_data = enable_sensitive_data
    if enable_live_metrics is not None:
        OTEL_SETTINGS.applicationinsights_live_metrics = enable_live_metrics
    # Run the initial setup, which will create the providers, and add env setting exporters
    new_exporters: list["LogExporter | SpanExporter | MetricExporter"] = []
    if OTEL_SETTINGS.ENABLED and (otlp_endpoint or applicationinsights_connection_string or exporters):
        # create the exporters, after checking if they are already configured through the env.
        new_exporters = exporters or []
        if otlp_endpoint:
            if isinstance(otlp_endpoint, str):
                otlp_endpoint = [otlp_endpoint]
            new_exporters.extend(
                _get_otlp_exporters(
                    endpoints=[
                        endpoint
                        for endpoint in otlp_endpoint
                        if not OTEL_SETTINGS.check_endpoint_already_configured(endpoint)
                    ]
                )
            )
        if applicationinsights_connection_string:
            if isinstance(applicationinsights_connection_string, str):
                applicationinsights_connection_string = [applicationinsights_connection_string]
            new_exporters.extend(
                _get_azure_monitor_exporters(
                    connection_strings=[
                        conn_str
                        for conn_str in applicationinsights_connection_string
                        if not OTEL_SETTINGS.check_connection_string_already_configured(conn_str)
                    ],
                    credential=credential,
                )
            )
    OTEL_SETTINGS.setup_observability(
        credential=credential, additional_exporters=new_exporters, force_setup=bool(new_exporters)
    )


# region Chat Client Telemetry


def _get_duration_histogram() -> "metrics.Histogram":
    return get_meter().create_histogram(
        name=Meters.LLM_OPERATION_DURATION,
        unit=OtelAttr.DURATION_UNIT,
        description="Captures the duration of operations of function-invoking chat clients",
        explicit_bucket_boundaries_advisory=OPERATION_DURATION_BUCKET_BOUNDARIES,
    )


def _get_token_usage_histogram() -> "metrics.Histogram":
    return get_meter().create_histogram(
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
                    capture_exception(span=span, exception=exception, timestamp=time_ns())
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
                    capture_exception(span=span, exception=exception, timestamp=time_ns())
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


def use_observability(
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
                capture_exception(span=span, exception=exception, timestamp=time_ns())
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
                capture_exception(span=span, exception=exception, timestamp=time_ns())
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


def use_agent_observability(
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
) -> "_AgnosticContextManager[trace.Span]":
    """Starts a span for the given function.

    Args:
        attributes: The span attributes.

    Returns:
        trace.trace.Span: The started span as a context manager.
    """
    return get_tracer().start_as_current_span(
        name=f"{attributes[OtelAttr.OPERATION]} {attributes[OtelAttr.TOOL_NAME]}",
        attributes=attributes,
        set_status_on_exception=False,
        end_on_exit=True,
        record_exception=False,
    )


@contextlib.contextmanager
def _get_span(
    attributes: dict[str, Any],
    span_name_attribute: str,
) -> Generator["trace.Span", Any, Any]:
    """Start a span for a agent run."""
    span = get_tracer().start_span(f"{attributes[OtelAttr.OPERATION]} {attributes[span_name_attribute]}")
    span.set_attributes(attributes)
    with trace.use_span(
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


def capture_exception(span: trace.Span, exception: Exception, timestamp: int | None = None) -> None:
    """Set an error for spans."""
    span.set_attribute(OtelAttr.ERROR_TYPE, type(exception).__name__)
    span.record_exception(exception=exception, timestamp=timestamp)
    span.set_status(status=trace.StatusCode.ERROR, description=repr(exception))


def _capture_messages(
    span: trace.Span,
    provider_name: str,
    messages: "str | ChatMessage | list[str] | list[ChatMessage]",
    system_instructions: str | list[str] | None = None,
    output: bool = False,
    finish_reason: "FinishReason | None" = None,
) -> None:
    """Log messages with extra information."""
    from ._clients import prepare_messages

    prepped = prepare_messages(messages)
    otel_messages: list[dict[str, Any]] = []
    for index, message in enumerate(prepped):
        otel_messages.append(_to_otel_message(message))
        try:
            message_data = message.model_dump(exclude_none=True)
        except Exception:
            message_data = {"role": message.role.value, "contents": message.contents}
        logger.info(
            message_data,
            extra={
                OtelAttr.EVENT_NAME: OtelAttr.CHOICE if output else ROLE_EVENT_MAP.get(message.role.value),
                OtelAttr.PROVIDER_NAME: provider_name,
                ChatMessageListTimestampFilter.INDEX_KEY: index,
            },
        )
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
            response: Any | None = None
            if content.result:
                if isinstance(content.result, list):
                    res: list[Any] = []
                    for item in content.result:  # type: ignore
                        from ._types import BaseContent

                        if isinstance(item, BaseContent):
                            res.append(_to_otel_part(item))  # type: ignore
                        elif isinstance(item, BaseModel):
                            res.append(item.model_dump(exclude_none=True))
                        else:
                            res.append(json.dumps(item))
                    response = json.dumps(res)
                else:
                    response = json.dumps(content.result)
            return {"type": "tool_call_response", "id": content.call_id, "response": response}
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
    span: trace.Span,
    attributes: dict[str, Any],
    operation_duration_histogram: "metrics.Histogram | None" = None,
    token_usage_histogram: "metrics.Histogram | None" = None,
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


class EdgeGroupDeliveryStatus(Enum):
    """Enum for edge group delivery status values."""

    DELIVERED = "delivered"
    DROPPED_TYPE_MISMATCH = "dropped type mismatch"
    DROPPED_TARGET_MISMATCH = "dropped target mismatch"
    DROPPED_CONDITION_FALSE = "dropped condition evaluated to false"
    EXCEPTION = "exception"
    BUFFERED = "buffered"

    def __str__(self) -> str:
        """Return the string representation of the enum."""
        return self.value

    def __repr__(self) -> str:
        """Return the string representation of the enum."""
        return self.value


def workflow_tracer() -> "Tracer":
    """Get a workflow tracer or a no-op tracer if not enabled."""
    global OTEL_SETTINGS
    return get_tracer() if OTEL_SETTINGS.ENABLED else trace.NoOpTracer()


def create_workflow_span(
    name: str,
    attributes: Mapping[str, str | int] | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
) -> "_AgnosticContextManager[trace.Span]":
    """Create a generic workflow span."""
    return workflow_tracer().start_as_current_span(name, kind=kind, attributes=attributes)


def create_processing_span(
    executor_id: str,
    executor_type: str,
    message_type: str,
    source_trace_contexts: list[dict[str, str]] | None = None,
    source_span_ids: list[str] | None = None,
) -> "_AgnosticContextManager[trace.Span]":
    """Create an executor processing span with optional links to source spans.

    Processing spans are created as children of the current workflow span and
    linked (not nested) to the source publishing spans for causality tracking.
    This supports multiple links for fan-in scenarios.
    """
    # Create links to source spans for causality without nesting
    links: list[trace.Link] = []
    if source_trace_contexts and source_span_ids:
        # Create links for all source spans (supporting fan-in with multiple sources)
        for trace_context, span_id in zip(source_trace_contexts, source_span_ids, strict=False):
            # If linking fails, continue without link (graceful degradation)
            with contextlib.suppress(ValueError, TypeError, AttributeError):
                # Extract trace and span IDs from the trace context
                # This is a simplified approach - in production you'd want more robust parsing
                traceparent = trace_context.get("traceparent", "")
                if traceparent:
                    # traceparent format: "00-{trace_id}-{parent_span_id}-{trace_flags}"
                    parts = traceparent.split("-")
                    if len(parts) >= 3:
                        trace_id_hex = parts[1]
                        # Use the source_span_id that was saved from the publishing span

                        # Create span context for linking
                        span_context = trace.SpanContext(
                            trace_id=int(trace_id_hex, 16),
                            span_id=int(span_id, 16),
                            is_remote=True,
                        )
                        links.append(trace.Link(span_context))

    return workflow_tracer().start_as_current_span(
        OtelAttr.EXECUTOR_PROCESS_SPAN,
        kind=trace.SpanKind.INTERNAL,
        attributes={
            OtelAttr.EXECUTOR_ID: executor_id,
            OtelAttr.EXECUTOR_TYPE: executor_type,
            OtelAttr.MESSAGE_TYPE: message_type,
        },
        links=links,
    )


def create_edge_group_processing_span(
    edge_group_type: str,
    edge_group_id: str | None = None,
    message_source_id: str | None = None,
    message_target_id: str | None = None,
    source_trace_contexts: list[dict[str, str]] | None = None,
    source_span_ids: list[str] | None = None,
) -> "_AgnosticContextManager[trace.Span]":
    """Create an edge group processing span with optional links to source spans.

    Edge group processing spans track the processing operations in edge runners
    before message delivery, including condition checking and routing decisions.
    trace.Links to source spans provide causality tracking without unwanted nesting.

    Args:
        edge_group_type: The type of the edge group (class name).
        edge_group_id: The unique ID of the edge group.
        message_source_id: The source ID of the message being processed.
        message_target_id: The target ID of the message being processed.
        source_trace_contexts: Optional trace contexts from source spans for linking.
        source_span_ids: Optional source span IDs for linking.
    """
    attributes: dict[str, str] = {
        OtelAttr.EDGE_GROUP_TYPE: edge_group_type,
    }

    if edge_group_id is not None:
        attributes[OtelAttr.EDGE_GROUP_ID] = edge_group_id
    if message_source_id is not None:
        attributes[OtelAttr.MESSAGE_SOURCE_ID] = message_source_id
    if message_target_id is not None:
        attributes[OtelAttr.MESSAGE_TARGET_ID] = message_target_id

    # Create links to source spans for causality without nesting
    links: list[trace.Link] = []
    if source_trace_contexts and source_span_ids:
        # Create links for all source spans (supporting fan-in with multiple sources)
        for trace_context, span_id in zip(source_trace_contexts, source_span_ids, strict=False):
            try:
                # Extract trace and span IDs from the trace context
                # This is a simplified approach - in production you'd want more robust parsing
                traceparent = trace_context.get("traceparent", "")
                if traceparent:
                    # traceparent format: "00-{trace_id}-{parent_span_id}-{trace_flags}"
                    parts = traceparent.split("-")
                    if len(parts) >= 3:
                        trace_id_hex = parts[1]
                        # Use the source_span_id that was saved from the publishing span

                        # Create span context for linking
                        span_context = trace.SpanContext(
                            trace_id=int(trace_id_hex, 16),
                            span_id=int(span_id, 16),
                            is_remote=True,
                        )
                        links.append(trace.Link(span_context))
            except (ValueError, TypeError, AttributeError):
                # If linking fails, continue without link (graceful degradation)
                pass

    return workflow_tracer().start_as_current_span(
        OtelAttr.EDGE_GROUP_PROCESS_SPAN,
        kind=trace.SpanKind.INTERNAL,
        attributes=attributes,
        links=links,
    )
