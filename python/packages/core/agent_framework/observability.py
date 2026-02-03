# Copyright (c) Microsoft. All rights reserved.

import contextlib
import json
import logging
import os
from collections.abc import AsyncIterable, Awaitable, Callable, Generator, Mapping
from enum import Enum
from functools import wraps
from time import perf_counter, time_ns
from typing import TYPE_CHECKING, Any, ClassVar, Final, TypeVar

from dotenv import load_dotenv
from opentelemetry import metrics, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.attributes import service_attributes
from opentelemetry.semconv_ai import GenAISystem, Meters, SpanAttributes
from pydantic import PrivateAttr

from . import __version__ as version_info
from ._logging import get_logger
from ._pydantic import AFBaseSettings
from .exceptions import AgentInitializationError, ChatClientInitializationError

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry.sdk._logs.export import LogRecordExporter
    from opentelemetry.sdk.metrics.export import MetricExporter
    from opentelemetry.sdk.metrics.view import View
    from opentelemetry.sdk.trace.export import SpanExporter
    from opentelemetry.trace import Tracer
    from opentelemetry.util._decorator import _AgnosticContextManager  # type: ignore[reportPrivateUsage]

    from ._agents import AgentProtocol
    from ._clients import ChatClientProtocol
    from ._threads import AgentThread
    from ._tools import FunctionTool
    from ._types import (
        AgentResponse,
        AgentResponseUpdate,
        ChatMessage,
        ChatResponse,
        ChatResponseUpdate,
        Content,
        FinishReason,
    )

__all__ = [
    "OBSERVABILITY_SETTINGS",
    "OtelAttr",
    "configure_otel_providers",
    "create_metric_views",
    "create_resource",
    "enable_instrumentation",
    "get_meter",
    "get_tracer",
    "use_agent_instrumentation",
    "use_instrumentation",
]


TAgent = TypeVar("TAgent", bound="AgentProtocol")
TChatClient = TypeVar("TChatClient", bound="ChatClientProtocol[Any]")


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


# Parse headers helper
def _parse_headers(header_str: str) -> dict[str, str]:
    """Parse header string like 'key1=value1,key2=value2' into dict."""
    headers: dict[str, str] = {}
    if not header_str:
        return headers
    for pair in header_str.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            headers[key.strip()] = value.strip()
    return headers


def _create_otlp_exporters(
    endpoint: str | None = None,
    protocol: str = "grpc",
    headers: dict[str, str] | None = None,
    traces_endpoint: str | None = None,
    traces_headers: dict[str, str] | None = None,
    metrics_endpoint: str | None = None,
    metrics_headers: dict[str, str] | None = None,
    logs_endpoint: str | None = None,
    logs_headers: dict[str, str] | None = None,
) -> list["LogRecordExporter | SpanExporter | MetricExporter"]:
    """Create OTLP exporters for a given endpoint and protocol.

    Args:
        endpoint: The OTLP endpoint URL (used for all exporters if individual endpoints not specified).
        protocol: The protocol to use ("grpc" or "http"). Default is "grpc".
        headers: Optional headers to include in requests (used for all exporters if individual headers not specified).
        traces_endpoint: Optional specific endpoint for traces. Overrides endpoint parameter.
        traces_headers: Optional specific headers for traces. Overrides headers parameter.
        metrics_endpoint: Optional specific endpoint for metrics. Overrides endpoint parameter.
        metrics_headers: Optional specific headers for metrics. Overrides headers parameter.
        logs_endpoint: Optional specific endpoint for logs. Overrides endpoint parameter.
        logs_headers: Optional specific headers for logs. Overrides headers parameter.

    Returns:
        List containing OTLPLogExporter, OTLPSpanExporter, and OTLPMetricExporter.

    Raises:
        ImportError: If the required OTLP exporter package is not installed.
    """
    # Determine actual endpoints and headers to use
    actual_traces_endpoint = traces_endpoint or endpoint
    actual_metrics_endpoint = metrics_endpoint or endpoint
    actual_logs_endpoint = logs_endpoint or endpoint
    actual_traces_headers = traces_headers or headers
    actual_metrics_headers = metrics_headers or headers
    actual_logs_headers = logs_headers or headers

    exporters: list["LogRecordExporter | SpanExporter | MetricExporter"] = []

    if not actual_logs_endpoint and not actual_traces_endpoint and not actual_metrics_endpoint:
        return exporters

    if protocol == "grpc":
        # Import all gRPC exporters
        try:
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter as GRPCLogExporter
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter as GRPCMetricExporter,
            )
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as GRPCSpanExporter
        except ImportError as exc:
            raise ImportError(
                "opentelemetry-exporter-otlp-proto-grpc is required for OTLP gRPC exporters. "
                "Install it with: pip install opentelemetry-exporter-otlp-proto-grpc"
            ) from exc

        if actual_logs_endpoint:
            exporters.append(
                GRPCLogExporter(
                    endpoint=actual_logs_endpoint,
                    headers=actual_logs_headers if actual_logs_headers else None,
                )
            )
        if actual_traces_endpoint:
            exporters.append(
                GRPCSpanExporter(
                    endpoint=actual_traces_endpoint,
                    headers=actual_traces_headers if actual_traces_headers else None,
                )
            )
        if actual_metrics_endpoint:
            exporters.append(
                GRPCMetricExporter(
                    endpoint=actual_metrics_endpoint,
                    headers=actual_metrics_headers if actual_metrics_headers else None,
                )
            )

    elif protocol in ("http/protobuf", "http"):
        # Import all HTTP exporters
        try:
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter as HTTPLogExporter
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter as HTTPMetricExporter,
            )
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as HTTPSpanExporter
        except ImportError as exc:
            raise ImportError(
                "opentelemetry-exporter-otlp-proto-http is required for OTLP HTTP exporters. "
                "Install it with: pip install opentelemetry-exporter-otlp-proto-http"
            ) from exc

        if actual_logs_endpoint:
            exporters.append(
                HTTPLogExporter(
                    endpoint=actual_logs_endpoint,
                    headers=actual_logs_headers if actual_logs_headers else None,
                )
            )
        if actual_traces_endpoint:
            exporters.append(
                HTTPSpanExporter(
                    endpoint=actual_traces_endpoint,
                    headers=actual_traces_headers if actual_traces_headers else None,
                )
            )
        if actual_metrics_endpoint:
            exporters.append(
                HTTPMetricExporter(
                    endpoint=actual_metrics_endpoint,
                    headers=actual_metrics_headers if actual_metrics_headers else None,
                )
            )

    return exporters


def _get_exporters_from_env(
    env_file_path: str | None = None,
    env_file_encoding: str | None = None,
) -> list["LogRecordExporter | SpanExporter | MetricExporter"]:
    """Parse OpenTelemetry environment variables and create exporters.

    This function reads standard OpenTelemetry environment variables to configure
    OTLP exporters for traces, logs, and metrics.

    The following environment variables are supported:
    - OTEL_EXPORTER_OTLP_ENDPOINT: Base endpoint for all signals
    - OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: Endpoint specifically for traces
    - OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: Endpoint specifically for metrics
    - OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: Endpoint specifically for logs
    - OTEL_EXPORTER_OTLP_PROTOCOL: Protocol to use (grpc, http/protobuf)
    - OTEL_EXPORTER_OTLP_HEADERS: Headers for all signals
    - OTEL_EXPORTER_OTLP_TRACES_HEADERS: Headers specifically for traces
    - OTEL_EXPORTER_OTLP_METRICS_HEADERS: Headers specifically for metrics
    - OTEL_EXPORTER_OTLP_LOGS_HEADERS: Headers specifically for logs

    Args:
        env_file_path: Path to a .env file to load environment variables from.
            Default is None, which loads from '.env' if present.
        env_file_encoding: Encoding to use when reading the .env file.
            Default is None, which uses the system default encoding.

    Returns:
        List of configured exporters (empty if no relevant env vars are set).

    References:
        - https://opentelemetry.io/docs/languages/sdk-configuration/general/
        - https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/
    """
    # Load environment variables from .env file if present
    load_dotenv(dotenv_path=env_file_path, encoding=env_file_encoding)

    # Get base endpoint
    base_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    # Get signal-specific endpoints (these override base endpoint)
    traces_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or base_endpoint
    metrics_endpoint = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or base_endpoint
    logs_endpoint = os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") or base_endpoint

    # Get protocol (default is grpc)
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").lower()

    # Get base headers
    base_headers_str = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    base_headers = _parse_headers(base_headers_str)

    # Get signal-specific headers (these merge with base headers)
    traces_headers_str = os.getenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS", "")
    metrics_headers_str = os.getenv("OTEL_EXPORTER_OTLP_METRICS_HEADERS", "")
    logs_headers_str = os.getenv("OTEL_EXPORTER_OTLP_LOGS_HEADERS", "")

    traces_headers = {**base_headers, **_parse_headers(traces_headers_str)}
    metrics_headers = {**base_headers, **_parse_headers(metrics_headers_str)}
    logs_headers = {**base_headers, **_parse_headers(logs_headers_str)}

    # Create exporters using helper function
    return _create_otlp_exporters(
        protocol=protocol,
        traces_endpoint=traces_endpoint,
        traces_headers=traces_headers if traces_headers else None,
        metrics_endpoint=metrics_endpoint,
        metrics_headers=metrics_headers if metrics_headers else None,
        logs_endpoint=logs_endpoint,
        logs_headers=logs_headers if logs_headers else None,
    )


def create_resource(
    service_name: str | None = None,
    service_version: str | None = None,
    env_file_path: str | None = None,
    env_file_encoding: str | None = None,
    **attributes: Any,
) -> "Resource":
    """Create an OpenTelemetry Resource from environment variables and parameters.

    This function reads standard OpenTelemetry environment variables to configure
    the resource, which identifies your service in telemetry backends.

    The following environment variables are read:
    - OTEL_SERVICE_NAME: The name of the service (defaults to "agent_framework")
    - OTEL_SERVICE_VERSION: The version of the service (defaults to package version)
    - OTEL_RESOURCE_ATTRIBUTES: Additional resource attributes as key=value pairs

    Args:
        service_name: Override the service name. If not provided, reads from
            OTEL_SERVICE_NAME environment variable or defaults to "agent_framework".
        service_version: Override the service version. If not provided, reads from
            OTEL_SERVICE_VERSION environment variable or defaults to the package version.
        env_file_path: Path to a .env file to load environment variables from.
            Default is None, which loads from '.env' if present.
        env_file_encoding: Encoding to use when reading the .env file.
            Default is None, which uses the system default encoding.
        **attributes: Additional resource attributes to include. These will be merged
            with attributes from OTEL_RESOURCE_ATTRIBUTES environment variable.

    Returns:
        A configured OpenTelemetry Resource instance.

    Examples:
        .. code-block:: python

            from agent_framework.observability import create_resource

            # Use defaults from environment variables
            resource = create_resource()

            # Override service name
            resource = create_resource(service_name="my_service")

            # Add custom attributes
            resource = create_resource(
                service_name="my_service", service_version="1.0.0", deployment_environment="production"
            )

            # Load from custom .env file
            resource = create_resource(env_file_path="config/.env")
    """
    # Load environment variables from .env file if present
    load_dotenv(dotenv_path=env_file_path, encoding=env_file_encoding)

    # Start with provided attributes
    resource_attributes: dict[str, Any] = dict(attributes)

    # Set service name
    if service_name is None:
        service_name = os.getenv("OTEL_SERVICE_NAME", "agent_framework")
    resource_attributes[service_attributes.SERVICE_NAME] = service_name

    # Set service version
    if service_version is None:
        service_version = os.getenv("OTEL_SERVICE_VERSION", version_info)
    resource_attributes[service_attributes.SERVICE_VERSION] = service_version

    # Parse OTEL_RESOURCE_ATTRIBUTES environment variable
    # Format: key1=value1,key2=value2
    if resource_attrs_env := os.getenv("OTEL_RESOURCE_ATTRIBUTES"):
        resource_attributes.update(_parse_headers(resource_attrs_env))
    return Resource.create(resource_attributes)


def create_metric_views() -> list["View"]:
    """Create the default OpenTelemetry metric views for Agent Framework."""
    from opentelemetry.sdk.metrics.view import DropAggregation, View

    return [
        # Dropping all enable_instrumentation names except for those starting with "agent_framework"
        View(instrument_name="agent_framework*"),
        View(instrument_name="gen_ai*"),
        View(instrument_name="*", aggregation=DropAggregation()),
    ]


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
        enable_instrumentation: Enable OpenTelemetry diagnostics. Default is False.
            Can be set via environment variable ENABLE_INSTRUMENTATION.
        enable_sensitive_data: Enable OpenTelemetry sensitive events. Default is False.
            Can be set via environment variable ENABLE_SENSITIVE_DATA.
        enable_console_exporters: Enable console exporters for traces, logs, and metrics.
            Default is False. Can be set via environment variable ENABLE_CONSOLE_EXPORTERS.
        vs_code_extension_port: The port the AI Toolkit or Azure AI Foundry VS Code extensions are listening on.
            Default is None.
            Can be set via environment variable VS_CODE_EXTENSION_PORT.

    Examples:
        .. code-block:: python

            from agent_framework import ObservabilitySettings

            # Using environment variables
            # Set ENABLE_INSTRUMENTATION=true
            # Set ENABLE_CONSOLE_EXPORTERS=true
            settings = ObservabilitySettings()

            # Or passing parameters directly
            settings = ObservabilitySettings(enable_instrumentation=True, enable_console_exporters=True)
    """

    env_prefix: ClassVar[str] = ""

    enable_instrumentation: bool = False
    enable_sensitive_data: bool = False
    enable_console_exporters: bool = False
    vs_code_extension_port: int | None = None
    _resource: "Resource" = PrivateAttr()
    _executed_setup: bool = PrivateAttr(default=False)

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the settings and create the resource."""
        super().__init__(**kwargs)
        # Create resource with env file settings
        self._resource = create_resource(
            env_file_path=self.env_file_path,
            env_file_encoding=self.env_file_encoding,
        )

    @property
    def ENABLED(self) -> bool:
        """Check if model diagnostics are enabled.

        Model diagnostics are enabled if either diagnostic is enabled or diagnostic with sensitive events is enabled.
        """
        return self.enable_instrumentation

    @property
    def SENSITIVE_DATA_ENABLED(self) -> bool:
        """Check if sensitive events are enabled.

        Sensitive events are enabled if the diagnostic with sensitive events is enabled.
        """
        return self.enable_instrumentation and self.enable_sensitive_data

    @property
    def is_setup(self) -> bool:
        """Check if the setup has been executed."""
        return self._executed_setup

    def _configure(
        self,
        *,
        additional_exporters: list["LogRecordExporter | SpanExporter | MetricExporter"] | None = None,
        views: list["View"] | None = None,
    ) -> None:
        """Configure application-wide observability based on the settings.

        This method is a helper method to create the log, trace and metric providers.
        This method is intended to be called once during the application startup. Calling it multiple times
        will have no effect.

        Args:
            additional_exporters: A list of additional exporters to add to the configuration. Default is None.
            views: Optional list of OpenTelemetry views for metrics. Default is None.
        """
        if not self.ENABLED or self._executed_setup:
            return

        exporters: list["LogRecordExporter | SpanExporter | MetricExporter"] = []

        # 1. Add exporters from standard OTEL environment variables
        exporters.extend(
            _get_exporters_from_env(
                env_file_path=self.env_file_path,
                env_file_encoding=self.env_file_encoding,
            )
        )

        # 2. Add passed-in exporters
        if additional_exporters:
            exporters.extend(additional_exporters)

        # 3. Add console exporters if explicitly enabled
        if self.enable_console_exporters:
            from opentelemetry.sdk._logs.export import ConsoleLogRecordExporter
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            exporters.extend([ConsoleSpanExporter(), ConsoleLogRecordExporter(), ConsoleMetricExporter()])

        # 4. Add VS Code extension exporters if port is specified
        if self.vs_code_extension_port:
            endpoint = f"http://localhost:{self.vs_code_extension_port}"
            exporters.extend(_create_otlp_exporters(endpoint=endpoint, protocol="grpc"))

        # 5. Configure providers
        self._configure_providers(exporters, views=views)
        self._executed_setup = True

    def _configure_providers(
        self,
        exporters: list["LogRecordExporter | MetricExporter | SpanExporter"],
        views: list["View"] | None = None,
    ) -> None:
        """Configure tracing, logging, events and metrics with the provided exporters.

        Args:
            exporters: A list of exporters for logs, metrics and/or spans.
            views: Optional list of OpenTelemetry views for metrics. Default is empty list.
        """
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import MetricExporter, PeriodicExportingMetricReader
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

        span_exporters: list[SpanExporter] = []
        log_exporters: list[LogRecordExporter] = []
        metric_exporters: list[MetricExporter] = []
        for exp in exporters:
            if isinstance(exp, SpanExporter):
                span_exporters.append(exp)
            if isinstance(exp, LogRecordExporter):
                log_exporters.append(exp)
            if isinstance(exp, MetricExporter):
                metric_exporters.append(exp)

        # Tracing
        if span_exporters:
            tracer_provider = TracerProvider(resource=self._resource)
            trace.set_tracer_provider(tracer_provider)
            for exporter in span_exporters:
                tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

        # Logging
        if log_exporters:
            logger_provider = LoggerProvider(resource=self._resource)
            for log_exporter in log_exporters:
                logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
            # Attach a handler with the provider to the root logger
            logger = logging.getLogger()
            handler = LoggingHandler(logger_provider=logger_provider)
            logger.addHandler(handler)
            set_logger_provider(logger_provider)

        # metrics
        if metric_exporters:
            meter_provider = MeterProvider(
                metric_readers=[
                    PeriodicExportingMetricReader(exporter, export_interval_millis=5000)
                    for exporter in metric_exporters
                ],
                resource=self._resource,
                views=views or [],
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


def enable_instrumentation(
    *,
    enable_sensitive_data: bool | None = None,
) -> None:
    """Enable instrumentation for your application.

    Calling this method implies you want to enable observability in your application.

    This method does not configure exporters or providers.
    It only updates the global variables that trigger the instrumentation code.
    If you have already set the environment variable ENABLE_INSTRUMENTATION=true,
    calling this method has no effect, unless you want to enable or disable sensitive data events.

    Keyword Args:
        enable_sensitive_data: Enable OpenTelemetry sensitive events. Overrides
            the environment variable ENABLE_SENSITIVE_DATA if set. Default is None.
    """
    global OBSERVABILITY_SETTINGS
    OBSERVABILITY_SETTINGS.enable_instrumentation = True
    if enable_sensitive_data is not None:
        OBSERVABILITY_SETTINGS.enable_sensitive_data = enable_sensitive_data


def configure_otel_providers(
    *,
    enable_sensitive_data: bool | None = None,
    exporters: list["LogRecordExporter | SpanExporter | MetricExporter"] | None = None,
    views: list["View"] | None = None,
    vs_code_extension_port: int | None = None,
    env_file_path: str | None = None,
    env_file_encoding: str | None = None,
) -> None:
    """Configure otel providers and enable instrumentation for the application with OpenTelemetry.

    This method creates the exporters and providers for the application based on
    the provided values and environment variables and enables instrumentation.

    Call this method once during application startup, before any telemetry is captured.
    DO NOT call this method multiple times, as it may lead to unexpected behavior.

    The function automatically reads standard OpenTelemetry environment variables:
    - OTEL_EXPORTER_OTLP_ENDPOINT: Base OTLP endpoint for all signals
    - OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: OTLP endpoint for traces
    - OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: OTLP endpoint for metrics
    - OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: OTLP endpoint for logs
    - OTEL_EXPORTER_OTLP_PROTOCOL: Protocol (grpc/http)
    - OTEL_EXPORTER_OTLP_HEADERS: Headers for all signals
    - ENABLE_CONSOLE_EXPORTERS: Enable console output for telemetry

    Note:
        Since you can only setup one provider per signal type (logs, traces, metrics),
        you can choose to use this method and take the exporter and provider that we created.
        Alternatively, you can setup the providers yourself, or through another library
        (e.g., Azure Monitor) and just call `enable_instrumentation()` to enable instrumentation.

    Note:
        By default, the Agent Framework emits metrics with the prefixes `agent_framework`
        and `gen_ai` (OpenTelemetry GenAI semantic conventions). You can use the `views`
        parameter to filter which metrics are collected and exported. You can also use
        the `create_metric_views()` helper function to get default views.

    Keyword Args:
        enable_sensitive_data: Enable OpenTelemetry sensitive events. Overrides
            the environment variable ENABLE_SENSITIVE_DATA if set. Default is None.
        exporters: A list of custom exporters for logs, metrics or spans, or any combination.
            These will be added in addition to exporters configured via environment variables.
            Default is None.
        views: Optional list of OpenTelemetry views for metrics configuration.
            Views allow filtering and customizing which metrics are collected.
            Default is None (empty list).
        vs_code_extension_port: The port the AI Toolkit or Azure AI Foundry VS Code
            extensions are listening on. When set, additional OTEL exporters will be
            created with endpoint `http://localhost:{vs_code_extension_port}`.
            Overrides the environment variable VS_CODE_EXTENSION_PORT if set. Default is None.
        env_file_path: An optional path to a .env file to load environment variables from.
            Default is None.
        env_file_encoding: The encoding to use when loading the .env file. Default is None
            which uses the system default encoding.

    Examples:
        .. code-block:: python

            from agent_framework.observability import configure_otel_providers

            # Using environment variables (recommended)
            # Set ENABLE_INSTRUMENTATION=true
            # Set OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
            configure_otel_providers()

            # Enable console output for debugging
            # Set ENABLE_CONSOLE_EXPORTERS=true
            configure_otel_providers()

            # With custom exporters
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

            configure_otel_providers(
                exporters=[
                    OTLPSpanExporter(endpoint="http://custom:4317"),
                    OTLPLogExporter(endpoint="http://custom:4317"),
                ],
            )

            # VS Code extension integration
            configure_otel_providers(
                vs_code_extension_port=4317,  # Connects to AI Toolkit
            )

            # Enable sensitive data logging (development only)
            configure_otel_providers(
                enable_sensitive_data=True,
            )

            # With custom metrics views
            from opentelemetry.sdk.metrics.view import View

            configure_otel_providers(
                views=[
                    View(instrument_name="agent_framework*"),
                    View(instrument_name="gen_ai*"),
                ],
            )

        This example shows how to first setup your providers,
        and then ensure Agent Framework emits traces, logs and metrics

        .. code-block:: python

            # when azure monitor is installed
            from agent_framework.observability import enable_instrumentation
            from azure.monitor.opentelemetry import configure_azure_monitor

            connection_string = "InstrumentationKey=your_instrumentation_key_here;..."
            configure_azure_monitor(connection_string=connection_string)
            enable_instrumentation()

    References:
        - https://opentelemetry.io/docs/languages/sdk-configuration/general/
        - https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/
    """
    global OBSERVABILITY_SETTINGS
    if env_file_path:
        # Build kwargs, excluding None values
        settings_kwargs: dict[str, Any] = {
            "enable_instrumentation": True,
            "env_file_path": env_file_path,
        }
        if env_file_encoding is not None:
            settings_kwargs["env_file_encoding"] = env_file_encoding
        if enable_sensitive_data is not None:
            settings_kwargs["enable_sensitive_data"] = enable_sensitive_data
        if vs_code_extension_port is not None:
            settings_kwargs["vs_code_extension_port"] = vs_code_extension_port

        OBSERVABILITY_SETTINGS = ObservabilitySettings(**settings_kwargs)
    else:
        # Update the observability settings with the provided values
        OBSERVABILITY_SETTINGS.enable_instrumentation = True
        if enable_sensitive_data is not None:
            OBSERVABILITY_SETTINGS.enable_sensitive_data = enable_sensitive_data
        if vs_code_extension_port is not None:
            OBSERVABILITY_SETTINGS.vs_code_extension_port = vs_code_extension_port

    OBSERVABILITY_SETTINGS._configure(  # type: ignore[reportPrivateUsage]
        additional_exporters=exporters,
        views=views,
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

    Keyword Args:
        provider_name: The model provider name.
    """

    def decorator(func: Callable[..., Awaitable["ChatResponse"]]) -> Callable[..., Awaitable["ChatResponse"]]:
        """Inner decorator."""

        @wraps(func)
        async def trace_get_response(
            self: "ChatClientProtocol",
            messages: "str | ChatMessage | list[str] | list[ChatMessage]",
            *,
            options: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> "ChatResponse":
            global OBSERVABILITY_SETTINGS
            if not OBSERVABILITY_SETTINGS.ENABLED:
                # If model_id diagnostics are not enabled, just return the completion
                return await func(
                    self,
                    messages=messages,
                    options=options,
                    **kwargs,
                )
            if "token_usage_histogram" not in self.additional_properties:
                self.additional_properties["token_usage_histogram"] = _get_token_usage_histogram()
            if "operation_duration_histogram" not in self.additional_properties:
                self.additional_properties["operation_duration_histogram"] = _get_duration_histogram()
            options = options or {}
            model_id = kwargs.get("model_id") or options.get("model_id") or getattr(self, "model_id", None) or "unknown"
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
                    _capture_messages(
                        span=span,
                        provider_name=provider_name,
                        messages=messages,
                        system_instructions=options.get("instructions"),
                    )
                start_time_stamp = perf_counter()
                end_time_stamp: float | None = None
                try:
                    response = await func(self, messages=messages, options=options, **kwargs)
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
            self: "ChatClientProtocol",
            messages: "str | ChatMessage | list[str] | list[ChatMessage]",
            *,
            options: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> AsyncIterable["ChatResponseUpdate"]:
            global OBSERVABILITY_SETTINGS
            if not OBSERVABILITY_SETTINGS.ENABLED:
                # If model diagnostics are not enabled, just return the completion
                async for update in func(self, messages=messages, options=options, **kwargs):
                    yield update
                return
            if "token_usage_histogram" not in self.additional_properties:
                self.additional_properties["token_usage_histogram"] = _get_token_usage_histogram()
            if "operation_duration_histogram" not in self.additional_properties:
                self.additional_properties["operation_duration_histogram"] = _get_duration_histogram()

            options = options or {}
            model_id = kwargs.get("model_id") or options.get("model_id") or getattr(self, "model_id", None) or "unknown"
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
                        system_instructions=options.get("instructions"),
                    )
                start_time_stamp = perf_counter()
                end_time_stamp: float | None = None
                try:
                    async for update in func(self, messages=messages, options=options, **kwargs):
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


def use_instrumentation(
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

            from agent_framework import use_instrumentation, configure_otel_providers
            from agent_framework import ChatClientProtocol


            # Decorate a custom chat client class
            @use_instrumentation
            class MyCustomChatClient:
                OTEL_PROVIDER_NAME = "my_provider"

                async def get_response(self, messages, **kwargs):
                    # Your implementation
                    pass

                async def get_streaming_response(self, messages, **kwargs):
                    # Your implementation
                    pass


            # Setup observability
            configure_otel_providers(otlp_endpoint="http://localhost:4317")

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
    run_func: Callable[..., Awaitable["AgentResponse"]],
    provider_name: str,
    capture_usage: bool = True,
) -> Callable[..., Awaitable["AgentResponse"]]:
    """Decorator to trace chat completion activities.

    Args:
        run_func: The function to trace.
        provider_name: The system name used for Open Telemetry.
        capture_usage: Whether to capture token usage as a span attribute.
    """

    @wraps(run_func)
    async def trace_run(
        self: "AgentProtocol",
        messages: "str | ChatMessage | list[str] | list[ChatMessage] | None" = None,
        *,
        thread: "AgentThread | None" = None,
        **kwargs: Any,
    ) -> "AgentResponse":
        global OBSERVABILITY_SETTINGS

        if not OBSERVABILITY_SETTINGS.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            return await run_func(self, messages=messages, thread=thread, **kwargs)

        from ._types import merge_chat_options

        default_options = getattr(self, "default_options", {})
        options = merge_chat_options(default_options, kwargs.get("options", {}))
        attributes = _get_span_attributes(
            operation_name=OtelAttr.AGENT_INVOKE_OPERATION,
            provider_name=provider_name,
            agent_id=self.id,
            agent_name=self.name or self.id,
            agent_description=self.description,
            thread_id=thread.service_thread_id if thread else None,
            all_options=options,
            **kwargs,
        )
        with _get_span(attributes=attributes, span_name_attribute=OtelAttr.AGENT_NAME) as span:
            if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and messages:
                _capture_messages(
                    span=span,
                    provider_name=provider_name,
                    messages=messages,
                    system_instructions=_get_instructions_from_options(options),
                )
            try:
                response = await run_func(self, messages=messages, thread=thread, **kwargs)
            except Exception as exception:
                capture_exception(span=span, exception=exception, timestamp=time_ns())
                raise
            else:
                attributes = _get_response_attributes(attributes, response, capture_usage=capture_usage)
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
    run_streaming_func: Callable[..., AsyncIterable["AgentResponseUpdate"]],
    provider_name: str,
    capture_usage: bool,
) -> Callable[..., AsyncIterable["AgentResponseUpdate"]]:
    """Decorator to trace streaming agent run activities.

    Args:
        run_streaming_func: The function to trace.
        provider_name: The system name used for Open Telemetry.
        capture_usage: Whether to capture token usage as a span attribute.
    """

    @wraps(run_streaming_func)
    async def trace_run_streaming(
        self: "AgentProtocol",
        messages: "str | ChatMessage | list[str] | list[ChatMessage] | None" = None,
        *,
        thread: "AgentThread | None" = None,
        **kwargs: Any,
    ) -> AsyncIterable["AgentResponseUpdate"]:
        global OBSERVABILITY_SETTINGS

        if not OBSERVABILITY_SETTINGS.ENABLED:
            # If model diagnostics are not enabled, just return the completion
            async for streaming_agent_response in run_streaming_func(self, messages=messages, thread=thread, **kwargs):
                yield streaming_agent_response
            return

        from ._types import AgentResponse, merge_chat_options

        all_updates: list["AgentResponseUpdate"] = []

        default_options = getattr(self, "default_options", {})
        options = merge_chat_options(default_options, kwargs.get("options", {}))
        attributes = _get_span_attributes(
            operation_name=OtelAttr.AGENT_INVOKE_OPERATION,
            provider_name=provider_name,
            agent_id=self.id,
            agent_name=self.name or self.id,
            agent_description=self.description,
            thread_id=thread.service_thread_id if thread else None,
            all_options=options,
            **kwargs,
        )
        with _get_span(attributes=attributes, span_name_attribute=OtelAttr.AGENT_NAME) as span:
            if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and messages:
                _capture_messages(
                    span=span,
                    provider_name=provider_name,
                    messages=messages,
                    system_instructions=_get_instructions_from_options(options),
                )
            try:
                async for update in run_streaming_func(self, messages=messages, thread=thread, **kwargs):
                    all_updates.append(update)
                    yield update
            except Exception as exception:
                capture_exception(span=span, exception=exception, timestamp=time_ns())
                raise
            else:
                response = AgentResponse.from_agent_run_response_updates(all_updates)
                attributes = _get_response_attributes(attributes, response, capture_usage=capture_usage)
                _capture_response(span=span, attributes=attributes)
                if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and response.messages:
                    _capture_messages(
                        span=span,
                        provider_name=provider_name,
                        messages=response.messages,
                        output=True,
                    )

    return trace_run_streaming


def use_agent_instrumentation(
    agent: type[TAgent] | None = None,
    *,
    capture_usage: bool = True,
) -> type[TAgent] | Callable[[type[TAgent]], type[TAgent]]:
    """Class decorator that enables OpenTelemetry observability for an agent.

    This decorator automatically traces agent run requests, captures events,
    and logs interactions for the decorated agent class.

    Note:
        This decorator must be applied to the agent class itself, not an instance.
        The agent class should have a class variable AGENT_PROVIDER_NAME to set the
        proper system name for telemetry.

    Args:
        agent: The agent class to enable observability for.

    Keyword Args:
        capture_usage: Whether to capture token usage as a span attribute.
            Defaults to True, set to False when the agent has underlying traces
            that already capture token usage to avoid double counting.

    Returns:
        The decorated agent class with observability enabled.

    Raises:
        AgentInitializationError: If the agent does not have required methods
            (run, run_stream).

    Examples:
        .. code-block:: python

            from agent_framework import use_agent_instrumentation, configure_otel_providers
            from agent_framework._agents import AgentProtocol


            # Decorate a custom agent class
            @use_agent_instrumentation
            class MyCustomAgent:
                AGENT_PROVIDER_NAME = "my_agent_system"

                async def run(self, messages=None, *, thread=None, **kwargs):
                    # Your implementation
                    pass

                async def run_stream(self, messages=None, *, thread=None, **kwargs):
                    # Your implementation
                    pass


            # Setup observability
            configure_otel_providers(otlp_endpoint="http://localhost:4317")

            # Now all agent runs will be traced
            agent = MyCustomAgent()
            response = await agent.run("Perform a task")
    """

    def decorator(agent: type[TAgent]) -> type[TAgent]:
        provider_name = str(getattr(agent, "AGENT_PROVIDER_NAME", "Unknown"))
        try:
            agent.run = _trace_agent_run(agent.run, provider_name, capture_usage=capture_usage)  # type: ignore
        except AttributeError as exc:
            raise AgentInitializationError(f"The agent {agent.__name__} does not have a run method.", exc) from exc
        try:
            agent.run_stream = _trace_agent_run_stream(agent.run_stream, provider_name, capture_usage=capture_usage)  # type: ignore
        except AttributeError as exc:
            raise AgentInitializationError(
                f"The agent {agent.__name__} does not have a run_stream method.", exc
            ) from exc
        setattr(agent, OPEN_TELEMETRY_AGENT_MARKER, True)
        return agent

    if agent is None:
        return decorator
    return decorator(agent)


# region Otel Helpers


def get_function_span_attributes(function: "FunctionTool[Any, Any]", tool_call_id: str | None = None) -> dict[str, str]:
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
    operation = attributes.get(OtelAttr.OPERATION, "operation")
    span_name = attributes.get(span_name_attribute, "unknown")
    span = get_tracer().start_span(f"{operation} {span_name}")
    span.set_attributes(attributes)
    with trace.use_span(
        span=span,
        end_on_exit=True,
        record_exception=False,
        set_status_on_exception=False,
    ) as current_span:
        yield current_span


def _get_instructions_from_options(options: Any) -> str | None:
    """Extract instructions from options dict."""
    if options is None:
        return None
    if isinstance(options, dict):
        return options.get("instructions")
    return None


# Mapping configuration for extracting span attributes
# Each entry: source_keys -> (otel_attribute_key, transform_func, check_options_first, default_value)
# - source_keys: single key or list of keys to check (first non-None value wins)
# - otel_attribute_key: target OTEL attribute name
# - transform_func: optional transformation function, can return None to skip attribute
# - check_options_first: whether to check options dict before kwargs
# - default_value: optional default value if key is not found (use None to skip)
OTEL_ATTR_MAP: dict[str | tuple[str, ...], tuple[str, Callable[[Any], Any] | None, bool, Any]] = {
    "choice_count": (OtelAttr.CHOICE_COUNT, None, False, 1),
    "operation_name": (OtelAttr.OPERATION, None, False, None),
    "system_name": (SpanAttributes.LLM_SYSTEM, None, False, None),
    "provider_name": (OtelAttr.PROVIDER_NAME, None, False, None),
    "service_url": (OtelAttr.ADDRESS, None, False, None),
    "conversation_id": (OtelAttr.CONVERSATION_ID, None, True, None),
    "seed": (OtelAttr.SEED, None, True, None),
    "frequency_penalty": (OtelAttr.FREQUENCY_PENALTY, None, True, None),
    "max_tokens": (SpanAttributes.LLM_REQUEST_MAX_TOKENS, None, True, None),
    "stop": (OtelAttr.STOP_SEQUENCES, None, True, None),
    "temperature": (SpanAttributes.LLM_REQUEST_TEMPERATURE, None, True, None),
    "top_p": (SpanAttributes.LLM_REQUEST_TOP_P, None, True, None),
    "presence_penalty": (OtelAttr.PRESENCE_PENALTY, None, True, None),
    "top_k": (OtelAttr.TOP_K, None, True, None),
    "encoding_formats": (
        OtelAttr.ENCODING_FORMATS,
        lambda v: json.dumps(v if isinstance(v, list) else [v]),
        True,
        None,
    ),
    "agent_id": (OtelAttr.AGENT_ID, None, False, None),
    "agent_name": (OtelAttr.AGENT_NAME, None, False, None),
    "agent_description": (OtelAttr.AGENT_DESCRIPTION, None, False, None),
    # Multiple source keys - checks model_id in options, then model in kwargs, then model_id in kwargs
    ("model_id", "model"): (SpanAttributes.LLM_REQUEST_MODEL, None, True, None),
    # Tools with validation - returns None if no valid tools
    "tools": (
        OtelAttr.TOOL_DEFINITIONS,
        lambda tools: (
            json.dumps(tools_dict)
            if (tools_dict := __import__("agent_framework._tools", fromlist=["_tools_to_dict"])._tools_to_dict(tools))
            else None
        ),
        True,
        None,
    ),
    # Error type extraction
    "error": (OtelAttr.ERROR_TYPE, lambda e: type(e).__name__, False, None),
    # thread_id overrides conversation_id - processed after conversation_id due to dict ordering
    "thread_id": (OtelAttr.CONVERSATION_ID, None, False, None),
}


def _get_span_attributes(**kwargs: Any) -> dict[str, Any]:
    """Get the span attributes from a kwargs dictionary."""
    attributes: dict[str, Any] = {}
    options = kwargs.get("all_options", kwargs.get("options"))
    if options is not None and not isinstance(options, dict):
        options = None

    for source_keys, (otel_key, transform_func, check_options, default_value) in OTEL_ATTR_MAP.items():
        # Normalize to tuple of keys
        keys = (source_keys,) if isinstance(source_keys, str) else source_keys

        value = None
        for key in keys:
            if check_options and options is not None:
                value = options.get(key)
            if value is None:
                value = kwargs.get(key)
            if value is not None:
                break

        # Apply default value if no value found
        if value is None and default_value is not None:
            value = default_value

        if value is not None:
            result = transform_func(value) if transform_func else value
            # Allow transform_func to return None to skip attribute
            if result is not None:
                attributes[otel_key] = result

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

    prepped = prepare_messages(messages, system_instructions=system_instructions)
    otel_messages: list[dict[str, Any]] = []
    for index, message in enumerate(prepped):
        # Reuse the otel message representation for logging instead of calling to_dict()
        # to avoid expensive Pydantic serialization overhead
        otel_message = _to_otel_message(message)
        otel_messages.append(otel_message)
        logger.info(
            otel_message,
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


def _to_otel_part(content: "Content") -> dict[str, Any] | None:
    """Create a otel representation of a Content."""
    from ._types import _get_data_bytes_as_str

    match content.type:
        case "text":
            return {"type": "text", "content": content.text}
        case "text_reasoning":
            return {"type": "reasoning", "content": content.text}
        case "uri":
            return {
                "type": "uri",
                "uri": content.uri,
                "mime_type": content.media_type,
                "modality": content.media_type.split("/")[0] if content.media_type else None,
            }
        case "data":
            return {
                "type": "blob",
                "content": _get_data_bytes_as_str(content),
                "mime_type": content.media_type,
                "modality": content.media_type.split("/")[0] if content.media_type else None,
            }
        case "function_call":
            return {"type": "tool_call", "id": content.call_id, "name": content.name, "arguments": content.arguments}
        case "function_result":
            from ._types import prepare_function_call_results

            return {
                "type": "tool_call_response",
                "id": content.call_id,
                "response": prepare_function_call_results(content),
            }
        case _:
            # GenericPart in otel output messages json spec.
            # just required type, and arbitrary other fields.
            return content.to_dict(exclude_none=True)
    return None


def _get_response_attributes(
    attributes: dict[str, Any],
    response: "ChatResponse | AgentResponse",
    duration: float | None = None,
    *,
    capture_usage: bool = True,
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
    if capture_usage and (usage := response.usage_details):
        if usage.get("input_token_count"):
            attributes[OtelAttr.INPUT_TOKENS] = usage["input_token_count"]
        if usage.get("output_token_count"):
            attributes[OtelAttr.OUTPUT_TOKENS] = usage["output_token_count"]
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
        f"{OtelAttr.EXECUTOR_PROCESS_SPAN} {executor_id}",
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
        f"{OtelAttr.EDGE_GROUP_PROCESS_SPAN} {edge_group_type}",
        kind=trace.SpanKind.INTERNAL,
        attributes=attributes,
        links=links,
    )
