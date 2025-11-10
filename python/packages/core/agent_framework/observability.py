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
    from opentelemetry.sdk._logs._internal.export import LogExporter
    from opentelemetry.sdk.metrics.export import MetricExporter
    from opentelemetry.sdk.resources import Resource
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

__all__ = [
    "OBSERVABILITY_SETTINGS",
    "OtelAttr",
    "get_meter",
    "get_tracer",
    "setup_observability",
    "use_agent_observability",
    "use_observability",
]


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
    TOOL_DEFINITIONS = "gen_ai.tool.definitions"
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
    WORKFLOW_NAME = "workflow.name"
    WORKFLOW_DESCRIPTION = "workflow.description"
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
    MESSAGE_PAYLOAD_TYPE = "message.payload_type"
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
    try:
        from azure.monitor.opentelemetry.exporter import (
            AzureMonitorLogExporter,
            AzureMonitorMetricExporter,
            AzureMonitorTraceExporter,
        )
    except ImportError as e:
        raise ImportError(
            "azure-monitor-opentelemetry-exporter is required for Azure Monitor exporters. "
            "Install it with: pip install azure-monitor-opentelemetry-exporter>=1.0.0b41"
        ) from e

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


class ObservabilitySettings(AFBaseSettings):
    """Settings for Agent Framework Observability.

    If the environment variables are not found, the settings can
    be loaded from a .env file with the encoding 'utf-8'.
    If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the
    settings are missing.

    Warning:
        Sensitive events should only be enabled on test and development environments.

    Keyword Args:
        enable_otel: Enable OpenTelemetry diagnostics. Default is False.
            Can be set via environment variable ENABLE_OTEL.
        enable_sensitive_data: Enable OpenTelemetry sensitive events. Default is False.
            Can be set via environment variable ENABLE_SENSITIVE_DATA.
        applicationinsights_connection_string: The Azure Monitor connection string. Default is None.
            Can be set via environment variable APPLICATIONINSIGHTS_CONNECTION_STRING.
        otlp_endpoint: The OpenTelemetry Protocol (OTLP) endpoint. Default is None.
            Can be set via environment variable OTLP_ENDPOINT.
        vs_code_extension_port: The port the AI Toolkit or Azure AI Foundry VS Code extensions are listening on.
            Default is None.
            Can be set via environment variable VS_CODE_EXTENSION_PORT.

    Examples:
        .. code-block:: python

            from agent_framework import ObservabilitySettings

            # Using environment variables
            # Set ENABLE_OTEL=true
            # Set APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...
            settings = ObservabilitySettings()

            # Or passing parameters directly
            settings = ObservabilitySettings(
                enable_otel=True, applicationinsights_connection_string="InstrumentationKey=..."
            )
    """

    env_prefix: ClassVar[str] = ""

    enable_otel: bool = False
    enable_sensitive_data: bool = False
    applicationinsights_connection_string: str | list[str] | None = None
    otlp_endpoint: str | list[str] | None = None
    vs_code_extension_port: int | None = None
    _resource: "Resource" = PrivateAttr(default_factory=_create_resource)
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

    @property
    def resource(self) -> "Resource":
        """Get the resource."""
        return self._resource

    @resource.setter
    def resource(self, value: "Resource") -> None:
        """Set the resource."""
        self._resource = value

    def _configure(
        self,
        credential: "TokenCredential | None" = None,
        additional_exporters: list["LogExporter | SpanExporter | MetricExporter"] | None = None,
    ) -> None:
        """Configure application-wide observability based on the settings.

        This method is a helper method to create the log, trace and metric providers.
        This method is intended to be called once during the application startup. Calling it multiple times
        will have no effect.

        Args:
            credential: The credential to use for Azure Monitor Entra ID authentication. Default is None.
            additional_exporters: A list of additional exporters to add to the configuration. Default is None.
        """
        if not self.ENABLED or self._executed_setup:
            return

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

    def check_endpoint_already_configured(self, otlp_endpoint: str) -> bool:
        """Check if the endpoint is already configured.

        Returns:
            True if the endpoint is already configured, False otherwise.
        """
        if not self.otlp_endpoint:
            return False
        return otlp_endpoint in (self.otlp_endpoint if isinstance(self.otlp_endpoint, list) else [self.otlp_endpoint])

    def check_connection_string_already_configured(self, connection_string: str) -> bool:
        """Check if the connection string is already configured.

        Returns:
            True if the connection string is already configured, False otherwise.
        """
        if not self.applicationinsights_connection_string:
            return False
        return connection_string in (
            self.applicationinsights_connection_string
            if isinstance(self.applicationinsights_connection_string, list)
            else [self.applicationinsights_connection_string]
        )

    def _configure_providers(self, exporters: list["LogExporter | MetricExporter | SpanExporter"]) -> None:
        """Configure tracing, logging, events and metrics with the provided exporters."""
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs._internal.export import LogExporter
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import MetricExporter, PeriodicExportingMetricReader
        from opentelemetry.sdk.metrics.view import DropAggregation, View
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

        # Tracing
        tracer_provider = TracerProvider(resource=self.resource)
        trace.set_tracer_provider(tracer_provider)
        should_add_console_exporter = True
        for exporter in exporters:
            if isinstance(exporter, SpanExporter):
                tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
                should_add_console_exporter = False
        if should_add_console_exporter:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        # Logging
        logger_provider = LoggerProvider(resource=self.resource)
        should_add_console_exporter = True
        for exporter in exporters:
            if isinstance(exporter, LogExporter):
                logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
                should_add_console_exporter = False
        if should_add_console_exporter:
            from opentelemetry.sdk._logs._internal.export import ConsoleLogExporter

            logger_provider.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogExporter()))

        # Attach a handler with the provider to the root logger
        logger = logging.getLogger()
        handler = LoggingHandler(logger_provider=logger_provider)
        logger.addHandler(handler)
        set_logger_provider(logger_provider)

        # metrics
        metric_readers = [
            PeriodicExportingMetricReader(exporter, export_interval_millis=5000)
            for exporter in exporters
            if isinstance(exporter, MetricExporter)
        ]
        if not metric_readers:
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

            metric_readers = [PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=5000)]
        meter_provider = MeterProvider(
            metric_readers=metric_readers,
            resource=self.resource,
            views=[
                # Dropping all instrument names except for those starting with "agent_framework"
                View(instrument_name="*", aggregation=DropAggregation()),
                View(instrument_name="agent_framework*"),
                View(instrument_name="gen_ai*"),
            ],
        )
        metrics.set_meter_provider(meter_provider)


def get_tracer(
    instrumenting_module_name: str = "agent_framework",
    instrumenting_library_version: str = version_info,
    schema_url: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> "trace.Tracer":
    """Returns a Tracer for use by the given instrumentation library.

    This function is a convenience wrapper for trace.get_tracer() replicating
    the behavior of opentelemetry.trace.TracerProvider.get_tracer.
    If tracer_provider is omitted the current configured one is used.

    Args:
        instrumenting_module_name: The name of the instrumenting library.
            Default is "agent_framework".
        instrumenting_library_version: The version of the instrumenting library.
            Default is the current agent_framework version.
        schema_url: Optional schema URL for the emitted telemetry.
        attributes: Optional attributes associated with the emitted telemetry.

    Returns:
        A Tracer instance for creating spans.

    Examples:
        .. code-block:: python

            from agent_framework import get_tracer

            # Get default tracer
            tracer = get_tracer()

            # Use tracer to create spans
            with tracer.start_as_current_span("my_operation") as span:
                span.set_attribute("custom.attribute", "value")
                # Your operation here
                pass

            # Get tracer with custom module name
            custom_tracer = get_tracer(
                instrumenting_module_name="my_custom_module",
                instrumenting_library_version="1.0.0",
            )
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
    """Returns a Meter for Agent Framework.

    This is a convenience wrapper for metrics.get_meter() replicating the behavior
    of opentelemetry.metrics.get_meter().

    Args:
        name: The name of the instrumenting library. Default is "agent_framework".
        version: The version of agent_framework. Default is the current version
            of the package.
        schema_url: Optional schema URL of the emitted telemetry.
        attributes: Optional attributes associated with the emitted telemetry.

    Returns:
        A Meter instance for recording metrics.

    Examples:
        .. code-block:: python

            from agent_framework import get_meter

            # Get default meter
            meter = get_meter()

            # Create a counter metric
            request_counter = meter.create_counter(
                name="requests",
                description="Number of requests",
                unit="1",
            )
            request_counter.add(1, {"endpoint": "/api/chat"})

            # Create a histogram metric
            duration_histogram = meter.create_histogram(
                name="request_duration",
                description="Request duration in seconds",
                unit="s",
            )
            duration_histogram.record(0.125, {"status": "success"})
    """
    try:
        return metrics.get_meter(name=name, version=version, schema_url=schema_url, attributes=attributes)
    except TypeError:
        # Older OpenTelemetry releases do not support the attributes parameter.
        return metrics.get_meter(name=name, version=version, schema_url=schema_url)


global OBSERVABILITY_SETTINGS
OBSERVABILITY_SETTINGS: ObservabilitySettings = ObservabilitySettings()


def setup_observability(
    enable_sensitive_data: bool | None = None,
    otlp_endpoint: str | list[str] | None = None,
    applicationinsights_connection_string: str | list[str] | None = None,
    credential: "TokenCredential | None" = None,
    exporters: list["LogExporter | SpanExporter | MetricExporter"] | None = None,
    vs_code_extension_port: int | None = None,
) -> None:
    """Setup observability for the application with OpenTelemetry.

    This method creates the exporters and providers for the application based on
    the provided values and environment variables.

    Call this method once during application startup, before any telemetry is captured.
    DO NOT call this method multiple times, as it may lead to unexpected behavior.

    Note:
        If you have configured the providers manually, calling this method will not
        have any effect. The reverse is also true - if you call this method first,
        subsequent provider configurations will not take effect.

    Args:
        enable_sensitive_data: Enable OpenTelemetry sensitive events. Overrides
            the environment variable if set. Default is None.
        otlp_endpoint: The OpenTelemetry Protocol (OTLP) endpoint. Will be used
            to create OTLPLogExporter, OTLPMetricExporter and OTLPSpanExporter.
            Default is None.
        applicationinsights_connection_string: The Azure Monitor connection string.
            Will be used to create AzureMonitorExporters. Default is None.
        credential: The credential to use for Azure Monitor Entra ID authentication.
            Default is None.
        exporters: A list of exporters for logs, metrics or spans, or any combination.
            These will be added directly, allowing complete customization. Default is None.
        vs_code_extension_port: The port the AI Toolkit or AzureAI Foundry VS Code
            extensions are listening on. When set, additional OTEL exporters will be
            created with endpoint `http://localhost:{vs_code_extension_port}` unless
            already configured. Overrides the environment variable if set. Default is None.

    Examples:
        .. code-block:: python

            from agent_framework import setup_observability

            # With environment variables
            # Set ENABLE_OTEL=true, OTLP_ENDPOINT=http://localhost:4317
            setup_observability()

            # With parameters (no environment variables)
            setup_observability(
                enable_sensitive_data=True,
                otlp_endpoint="http://localhost:4317",
            )

            # With Azure Monitor
            setup_observability(
                applicationinsights_connection_string="InstrumentationKey=...",
            )

            # With custom exporters
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            setup_observability(
                exporters=[ConsoleSpanExporter()],
            )

            # Mixed: combine environment variables and parameters
            # Environment: OTLP_ENDPOINT=http://localhost:7431
            # Code adds additional endpoint
            setup_observability(
                enable_sensitive_data=True,
                otlp_endpoint="http://localhost:4317",  # Both endpoints will be used
            )

            # VS Code extension integration
            setup_observability(
                vs_code_extension_port=4317,  # Connects to AI Toolkit
            )
    """
    global OBSERVABILITY_SETTINGS
    # Update the observability settings with the provided values
    OBSERVABILITY_SETTINGS.enable_otel = True
    if enable_sensitive_data is not None:
        OBSERVABILITY_SETTINGS.enable_sensitive_data = enable_sensitive_data
    if vs_code_extension_port is not None:
        OBSERVABILITY_SETTINGS.vs_code_extension_port = vs_code_extension_port

    # Create exporters, after checking if they are already configured through the env.
    new_exporters: list["LogExporter | SpanExporter | MetricExporter"] = exporters or []
    if otlp_endpoint:
        if isinstance(otlp_endpoint, str):
            otlp_endpoint = [otlp_endpoint]
        new_exporters.extend(
            _get_otlp_exporters(
                endpoints=[
                    endpoint
                    for endpoint in otlp_endpoint
                    if not OBSERVABILITY_SETTINGS.check_endpoint_already_configured(endpoint)
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
                    if not OBSERVABILITY_SETTINGS.check_connection_string_already_configured(conn_str)
                ],
                credential=credential,
            )
        )
    if OBSERVABILITY_SETTINGS.vs_code_extension_port:
        endpoint = f"http://localhost:{OBSERVABILITY_SETTINGS.vs_code_extension_port}"
        if not OBSERVABILITY_SETTINGS.check_endpoint_already_configured(endpoint):
            new_exporters.extend(_get_otlp_exporters(endpoints=[endpoint]))

    OBSERVABILITY_SETTINGS._configure(credential=credential, additional_exporters=new_exporters)  # pyright: ignore[reportPrivateUsage]


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

    Keyword Args:
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
            global OBSERVABILITY_SETTINGS
            if not OBSERVABILITY_SETTINGS.ENABLED:
                # If model_id diagnostics are not enabled, just return the completion
                return await func(
                    self,
                    messages=messages,
                    **kwargs,
                )
            if "token_usage_histogram" not in self.additional_properties:
                self.additional_properties["token_usage_histogram"] = _get_token_usage_histogram()
            if "operation_duration_histogram" not in self.additional_properties:
                self.additional_properties["operation_duration_histogram"] = _get_duration_histogram()
            model_id = (
                kwargs.get("model_id")
                or (chat_options.model_id if (chat_options := kwargs.get("chat_options")) else None)
                or getattr(self, "model_id", None)
                or "unknown"
            )
            service_url = str(
                service_url_func()
                if (service_url_func := getattr(self, "service_url", None)) and callable(service_url_func)
                else "unknown"
            )
            attributes = _get_span_attributes(
                operation_name=OtelAttr.CHAT_COMPLETION_OPERATION,
                provider_name=provider_name,
                model=model_id,
                service_url=service_url,
                **kwargs,
            )
            with _get_span(attributes=attributes, span_name_attribute=SpanAttributes.LLM_REQUEST_MODEL) as span:
                if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and messages:
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
                    if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and response.messages:
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

    Keyword Args:
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
            global OBSERVABILITY_SETTINGS
            if not OBSERVABILITY_SETTINGS.ENABLED:
                # If model diagnostics are not enabled, just return the completion
                async for update in func(self, messages=messages, **kwargs):
                    yield update
                return
            if "token_usage_histogram" not in self.additional_properties:
                self.additional_properties["token_usage_histogram"] = _get_token_usage_histogram()
            if "operation_duration_histogram" not in self.additional_properties:
                self.additional_properties["operation_duration_histogram"] = _get_duration_histogram()

            model_id = (
                kwargs.get("model_id")
                or (chat_options.model_id if (chat_options := kwargs.get("chat_options")) else None)
                or getattr(self, "model_id", None)
                or "unknown"
            )
            service_url = str(
                service_url_func()
                if (service_url_func := getattr(self, "service_url", None)) and callable(service_url_func)
                else "unknown"
            )
            attributes = _get_span_attributes(
                operation_name=OtelAttr.CHAT_COMPLETION_OPERATION,
                provider_name=provider_name,
                model=model_id,
                service_url=service_url,
                **kwargs,
            )
            all_updates: list["ChatResponseUpdate"] = []
            with _get_span(attributes=attributes, span_name_attribute=SpanAttributes.LLM_REQUEST_MODEL) as span:
                if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and messages:
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

                    if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and response.messages:
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
    """Class decorator that enables OpenTelemetry observability for a chat client.

    This decorator automatically traces chat completion requests, captures metrics,
    and logs events for the decorated chat client class.

    Note:
        This decorator must be applied to the class itself, not an instance.
        The chat client class should have a class variable OTEL_PROVIDER_NAME to
        set the proper provider name for telemetry.

    Args:
        chat_client: The chat client class to enable observability for.

    Returns:
        The decorated chat client class with observability enabled.

    Raises:
        ChatClientInitializationError: If the chat client does not have required
            methods (get_response, get_streaming_response).

    Examples:
        .. code-block:: python

            from agent_framework import use_observability, setup_observability
            from agent_framework._clients import ChatClientProtocol


            # Decorate a custom chat client class
            @use_observability
            class MyCustomChatClient:
                OTEL_PROVIDER_NAME = "my_provider"

                async def get_response(self, messages, **kwargs):
                    # Your implementation
                    pass

                async def get_streaming_response(self, messages, **kwargs):
                    # Your implementation
                    pass


            # Setup observability
            setup_observability(otlp_endpoint="http://localhost:4317")

            # Now all calls will be traced
            client = MyCustomChatClient()
            response = await client.get_response("Hello")
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
        global OBSERVABILITY_SETTINGS

        if not OBSERVABILITY_SETTINGS.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            return await run_func(self, messages=messages, thread=thread, **kwargs)
        attributes = _get_span_attributes(
            operation_name=OtelAttr.AGENT_INVOKE_OPERATION,
            provider_name=provider_name,
            agent_id=self.id,
            agent_name=self.display_name,
            agent_description=self.description,
            thread_id=thread.service_thread_id if thread else None,
            chat_options=getattr(self, "chat_options", None),
            **kwargs,
        )
        with _get_span(attributes=attributes, span_name_attribute=OtelAttr.AGENT_NAME) as span:
            if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and messages:
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
                if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and response.messages:
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
        global OBSERVABILITY_SETTINGS

        if not OBSERVABILITY_SETTINGS.ENABLED:
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
            chat_options=getattr(self, "chat_options", None),
            **kwargs,
        )
        with _get_span(attributes=attributes, span_name_attribute=OtelAttr.AGENT_NAME) as span:
            if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and messages:
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
                if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and response.messages:
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
    """Class decorator that enables OpenTelemetry observability for an agent.

    This decorator automatically traces agent run requests, captures events,
    and logs interactions for the decorated agent class.

    Note:
        This decorator must be applied to the agent class itself, not an instance.
        The agent class should have a class variable AGENT_SYSTEM_NAME to set the
        proper system name for telemetry.

    Args:
        agent: The agent class to enable observability for.

    Returns:
        The decorated agent class with observability enabled.

    Raises:
        AgentInitializationError: If the agent does not have required methods
            (run, run_stream).

    Examples:
        .. code-block:: python

            from agent_framework import use_agent_observability, setup_observability
            from agent_framework._agents import AgentProtocol


            # Decorate a custom agent class
            @use_agent_observability
            class MyCustomAgent:
                AGENT_SYSTEM_NAME = "my_agent_system"

                async def run(self, messages=None, *, thread=None, **kwargs):
                    # Your implementation
                    pass

                async def run_stream(self, messages=None, *, thread=None, **kwargs):
                    # Your implementation
                    pass


            # Setup observability
            setup_observability(otlp_endpoint="http://localhost:4317")

            # Now all agent runs will be traced
            agent = MyCustomAgent()
            response = await agent.run("Perform a task")
    """
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
    """Start a span for a agent run.

    Note: `attributes` must contain the `span_name_attribute` key.
    """
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
    from ._tools import _tools_to_dict
    from ._types import ChatOptions

    attributes: dict[str, Any] = {}
    chat_options: ChatOptions | None = kwargs.get("chat_options")
    if chat_options is None:
        chat_options = ChatOptions()
    if operation_name := kwargs.get("operation_name"):
        attributes[OtelAttr.OPERATION] = operation_name
    if choice_count := kwargs.get("choice_count", 1):
        attributes[OtelAttr.CHOICE_COUNT] = choice_count
    if system_name := kwargs.get("system_name"):
        attributes[SpanAttributes.LLM_SYSTEM] = system_name
    if provider_name := kwargs.get("provider_name"):
        attributes[OtelAttr.PROVIDER_NAME] = provider_name
    if model_id := kwargs.get("model", chat_options.model_id):
        attributes[SpanAttributes.LLM_REQUEST_MODEL] = model_id
    if service_url := kwargs.get("service_url"):
        attributes[OtelAttr.ADDRESS] = service_url
    if conversation_id := kwargs.get("conversation_id", chat_options.conversation_id):
        attributes[OtelAttr.CONVERSATION_ID] = conversation_id
    if seed := kwargs.get("seed", chat_options.seed):
        attributes[OtelAttr.SEED] = seed
    if frequency_penalty := kwargs.get("frequency_penalty", chat_options.frequency_penalty):
        attributes[OtelAttr.FREQUENCY_PENALTY] = frequency_penalty
    if max_tokens := kwargs.get("max_tokens", chat_options.max_tokens):
        attributes[SpanAttributes.LLM_REQUEST_MAX_TOKENS] = max_tokens
    if stop := kwargs.get("stop", chat_options.stop):
        attributes[OtelAttr.STOP_SEQUENCES] = stop
    if temperature := kwargs.get("temperature", chat_options.temperature):
        attributes[SpanAttributes.LLM_REQUEST_TEMPERATURE] = temperature
    if top_p := kwargs.get("top_p", chat_options.top_p):
        attributes[SpanAttributes.LLM_REQUEST_TOP_P] = top_p
    if presence_penalty := kwargs.get("presence_penalty", chat_options.presence_penalty):
        attributes[OtelAttr.PRESENCE_PENALTY] = presence_penalty
    if top_k := kwargs.get("top_k"):
        attributes[OtelAttr.TOP_K] = top_k
    if encoding_formats := kwargs.get("encoding_formats"):
        attributes[OtelAttr.ENCODING_FORMATS] = json.dumps(
            encoding_formats if isinstance(encoding_formats, list) else [encoding_formats]
        )
    if tools := kwargs.get("tools", chat_options.tools):
        tools_as_json_list = _tools_to_dict(tools)
        if tools_as_json_list:
            attributes[OtelAttr.TOOL_DEFINITIONS] = json.dumps(tools_as_json_list)
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
    from ._types import prepare_messages

    prepped = prepare_messages(messages)
    otel_messages: list[dict[str, Any]] = []
    for index, message in enumerate(prepped):
        otel_messages.append(_to_otel_message(message))
        try:
            message_data = message.to_dict(exclude_none=True)
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
            return content.to_dict(exclude_none=True)
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
    if model_id := getattr(response, "model_id", None):
        attributes[SpanAttributes.LLM_RESPONSE_MODEL] = model_id
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
    global OBSERVABILITY_SETTINGS
    return get_tracer() if OBSERVABILITY_SETTINGS.ENABLED else trace.NoOpTracer()


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
    payload_type: str,
    source_trace_contexts: list[dict[str, str]] | None = None,
    source_span_ids: list[str] | None = None,
) -> "_AgnosticContextManager[trace.Span]":
    """Create an executor processing span with optional links to source spans.

    Processing spans are created as children of the current workflow span and
    linked (not nested) to the source publishing spans for causality tracking.
    This supports multiple links for fan-in scenarios.

    Args:
        executor_id: The unique ID of the executor processing the message.
        executor_type: The type of the executor (class name).
        message_type: The type of the message being processed ("standard" or "response").
        payload_type: The data type of the message being processed.
        source_trace_contexts: Optional trace contexts from source spans for linking.
        source_span_ids: Optional source span IDs for linking.
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
            OtelAttr.MESSAGE_PAYLOAD_TYPE: payload_type,
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
