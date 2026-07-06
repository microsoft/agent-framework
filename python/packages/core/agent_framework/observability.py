# Copyright (c) Microsoft. All rights reserved.

"""Observability and OpenTelemetry helpers for Agent Framework.

Commonly used exports:
- enable_instrumentation
- disable_instrumentation
- enable_sensitive_telemetry
- configure_otel_providers
- AgentTelemetryLayer
- ChatTelemetryLayer
- get_tracer
- get_meter
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import sys
import weakref
from collections.abc import Awaitable, Callable, Generator, Mapping, Sequence
from enum import Enum
from time import perf_counter, time_ns
from typing import TYPE_CHECKING, Any, ClassVar, Final, Generic, Literal, TypedDict, cast, overload

from dotenv import load_dotenv
from opentelemetry import context as otel_context
from opentelemetry import metrics, trace

from . import __version__ as version_info
from ._settings import load_settings

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry.sdk._logs.export import LogRecordExporter
    from opentelemetry.sdk.metrics.export import MetricExporter
    from opentelemetry.sdk.metrics.view import View
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import SpanExporter
    from opentelemetry.trace import Tracer
    from opentelemetry.util._decorator import _AgnosticContextManager  # type: ignore[reportPrivateUsage]
    from pydantic import BaseModel

    from ._agents import SupportsAgentRun
    from ._clients import SupportsChatGetResponse
    from ._compaction import CompactionStrategy, TokenizerProtocol
    from ._middleware import MiddlewareTypes
    from ._sessions import AgentSession
    from ._tools import FunctionTool, ToolTypes
    from ._types import (
        AgentResponse,
        AgentResponseUpdate,
        AgentRunInputs,
        ChatOptions,
        ChatResponse,
        ChatResponseUpdate,
        Content,
        EmbeddingGenerationOptions,
        FinishReason,
        GeneratedEmbeddings,
        Message,
        ResponseStream,
        UsageDetails,
    )

    ResponseModelBoundT = TypeVar("ResponseModelBoundT", bound=BaseModel)

__all__ = [
    "OBSERVABILITY_SETTINGS",
    "AgentTelemetryLayer",
    "ChatTelemetryLayer",
    "EmbeddingTelemetryLayer",
    "OtelAttr",
    "configure_otel_providers",
    "create_mcp_client_span",
    "create_metric_views",
    "create_resource",
    "disable_instrumentation",
    "enable_instrumentation",
    "enable_sensitive_telemetry",
    "get_meter",
    "get_tracer",
    "set_mcp_span_error",
]


EmbeddingInputT = TypeVar("EmbeddingInputT", default="str")
EmbeddingT = TypeVar("EmbeddingT", default="list[float]")
AgentT = TypeVar("AgentT", bound="SupportsAgentRun")
ChatClientT = TypeVar("ChatClientT", bound="SupportsChatGetResponse[Any]")


logger = logging.getLogger("agent_framework")


INNER_RESPONSE_TELEMETRY_CAPTURED_FIELDS: Final[contextvars.ContextVar[set[str] | None]] = contextvars.ContextVar(
    "inner_response_telemetry_captured_fields", default=None
)
INNER_RESPONSE_ID_CAPTURED_FIELD: Final[str] = "response_id"
INNER_USAGE_CAPTURED_FIELD: Final[str] = "usage"

# Tracks accumulated token usage from all inner chat completion spans within an agent invoke.
INNER_ACCUMULATED_USAGE: Final[contextvars.ContextVar[UsageDetails | None]] = contextvars.ContextVar(
    "inner_accumulated_usage", default=None
)

OTEL_METRICS: Final[str] = "__otel_metrics__"
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
class MessageListTimestampFilter(logging.Filter):
    """A filter to increment the timestamp of INFO logs by 1 microsecond."""

    INDEX_KEY: ClassVar[str] = "chat_message_index"

    def filter(self, record: logging.LogRecord) -> bool:
        """Increment the timestamp of INFO logs by 1 microsecond."""
        if hasattr(record, self.INDEX_KEY):
            idx = getattr(record, self.INDEX_KEY)
            record.created += idx * 1e-6
        return True


logger.addFilter(MessageListTimestampFilter())


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
    CACHE_CREATION_INPUT_TOKENS = "gen_ai.usage.cache_creation.input_tokens"
    CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
    REASONING_OUTPUT_TOKENS = "gen_ai.usage.reasoning.output_tokens"
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
    SERVICE_NAME = "service.name"
    SERVICE_VERSION = "service.version"
    # Client attributes
    # replaced TOKEN with T, because both ruff and bandit,
    # complain about TOKEN being a potential secret
    T_UNIT = "tokens"
    T_TYPE = "gen_ai.token.type"
    T_TYPE_INPUT = "input"
    T_TYPE_OUTPUT = "output"
    DURATION_UNIT = "s"
    LLM_OPERATION_DURATION = "gen_ai.client.operation.duration"
    LLM_TOKEN_USAGE = "gen_ai.client.token.usage"  # nosec B105 # noqa: S105 - OpenTelemetry metric name, not a secret.

    # Agent attributes
    AGENT_NAME = "gen_ai.agent.name"
    AGENT_DESCRIPTION = "gen_ai.agent.description"
    CONVERSATION_ID = "gen_ai.conversation.id"
    DATA_SOURCE_ID = "gen_ai.data_source.id"
    OUTPUT_TYPE = "gen_ai.output.type"
    INPUT_MESSAGES = "gen_ai.input.messages"
    OUTPUT_MESSAGES = "gen_ai.output.messages"
    SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions"
    SYSTEM = "gen_ai.system"
    REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
    REQUEST_TEMPERATURE = "gen_ai.request.temperature"
    REQUEST_TOP_P = "gen_ai.request.top_p"
    REQUEST_MODEL = "gen_ai.request.model"
    RESPONSE_MODEL = "gen_ai.response.model"

    # Workflow attributes
    WORKFLOW_ID = "workflow.id"
    WORKFLOW_BUILDER_NAME = "workflow_builder.name"
    WORKFLOW_BUILDER_DESCRIPTION = "workflow_builder.description"
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
    EMBEDDING_OPERATION = "embeddings"
    TOOL_EXECUTION_OPERATION = "execute_tool"
    # Describes GenAI agent creation and is usually applicable when working with remote agent services.
    AGENT_CREATE_OPERATION = "create_agent"
    AGENT_INVOKE_OPERATION = "invoke_agent"

    # MCP attributes (https://opentelemetry.io/docs/specs/semconv/gen-ai/mcp/)
    MCP_METHOD_NAME = "mcp.method.name"
    MCP_PROTOCOL_VERSION = "mcp.protocol.version"
    MCP_SESSION_ID = "mcp.session.id"
    PROMPT_NAME = "gen_ai.prompt.name"
    NETWORK_TRANSPORT = "network.transport"
    NETWORK_PROTOCOL_NAME = "network.protocol.name"

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
USAGE_DETAIL_TO_OTEL_ATTR: Final[tuple[tuple[str, OtelAttr], ...]] = (
    ("input_token_count", OtelAttr.INPUT_TOKENS),
    ("output_token_count", OtelAttr.OUTPUT_TOKENS),
    ("cache_creation_input_token_count", OtelAttr.CACHE_CREATION_INPUT_TOKENS),
    ("cache_read_input_token_count", OtelAttr.CACHE_READ_INPUT_TOKENS),
    ("reasoning_output_token_count", OtelAttr.REASONING_OUTPUT_TOKENS),
    ("anthropic.cache_creation_input_tokens", OtelAttr.CACHE_CREATION_INPUT_TOKENS),
    ("anthropic.cache_read_input_tokens", OtelAttr.CACHE_READ_INPUT_TOKENS),
    ("openai.cached_input_tokens", OtelAttr.CACHE_READ_INPUT_TOKENS),
    ("prompt/cached_tokens", OtelAttr.CACHE_READ_INPUT_TOKENS),
    ("openai.reasoning_tokens", OtelAttr.REASONING_OUTPUT_TOKENS),
    ("completion/reasoning_tokens", OtelAttr.REASONING_OUTPUT_TOKENS),
    ("reasoning_tokens", OtelAttr.REASONING_OUTPUT_TOKENS),
)


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
) -> list[LogRecordExporter | SpanExporter | MetricExporter]:
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

    exporters: list[LogRecordExporter | SpanExporter | MetricExporter] = []

    if not actual_logs_endpoint and not actual_traces_endpoint and not actual_metrics_endpoint:
        return exporters

    if protocol == "grpc":
        # Import all gRPC exporters
        try:
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
                OTLPLogExporter as GRPCLogExporter,
            )
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter as GRPCMetricExporter,
            )
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter as GRPCSpanExporter,
            )
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
) -> list[LogRecordExporter | SpanExporter | MetricExporter]:
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
            Default is None, which does not load a .env file.
        env_file_encoding: Encoding to use when reading the .env file.
            Default is None, which uses the system default encoding.

    Returns:
        List of configured exporters (empty if no relevant env vars are set).

    References:
        - https://opentelemetry.io/docs/languages/sdk-configuration/general/
        - https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/
    """
    # Load environment variables from a .env file only when explicitly provided
    if env_file_path is not None:
        load_dotenv(dotenv_path=env_file_path, encoding=env_file_encoding)

    # Get base endpoint
    base_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    # Get signal-specific endpoints (these override base endpoint and are used verbatim)
    traces_endpoint_specific = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    metrics_endpoint_specific = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
    logs_endpoint_specific = os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")

    # Get protocol (default is grpc)
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").lower()

    # Per the OTel spec, OTEL_EXPORTER_OTLP_ENDPOINT is a *base* URL for HTTP — the SDK
    # auto-appends /v1/{traces,metrics,logs} when it reads the env var directly. The
    # signal-specific endpoint env vars are *full* URLs used verbatim. Because we read
    # the env vars here and forward them as the ``endpoint=`` constructor argument
    # (which the SDK always treats as a full URL), we must replicate the auto-append
    # ourselves for HTTP when falling back to the base endpoint. For gRPC, the base
    # endpoint is used as-is.
    traces_endpoint: str | None
    metrics_endpoint: str | None
    logs_endpoint: str | None
    if protocol in ("http/protobuf", "http") and base_endpoint:
        base_for_http = base_endpoint.rstrip("/")
        traces_endpoint = traces_endpoint_specific or f"{base_for_http}/v1/traces"
        metrics_endpoint = metrics_endpoint_specific or f"{base_for_http}/v1/metrics"
        logs_endpoint = logs_endpoint_specific or f"{base_for_http}/v1/logs"
    else:
        traces_endpoint = traces_endpoint_specific or base_endpoint
        metrics_endpoint = metrics_endpoint_specific or base_endpoint
        logs_endpoint = logs_endpoint_specific or base_endpoint

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
) -> Resource:
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
            Default is None, which does not load a .env file.
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
    try:
        from opentelemetry.sdk.resources import Resource
    except ModuleNotFoundError as ex:
        raise ModuleNotFoundError(
            "`opentelemetry-sdk` is required to use `create_resource()`. "
            "Please install `opentelemetry-sdk` and update your dependencies."
        ) from ex

    if env_file_path is not None:
        load_dotenv(dotenv_path=env_file_path, encoding=env_file_encoding)

    resource_attributes: dict[str, Any] = dict(attributes)

    if service_name is None:
        service_name = os.getenv("OTEL_SERVICE_NAME", "agent_framework")
    resource_attributes[OtelAttr.SERVICE_NAME] = service_name

    if service_version is None:
        service_version = os.getenv("OTEL_SERVICE_VERSION", version_info)
    resource_attributes[OtelAttr.SERVICE_VERSION] = service_version

    if resource_attrs_env := os.getenv("OTEL_RESOURCE_ATTRIBUTES"):
        resource_attributes.update(_parse_headers(resource_attrs_env))
    return Resource.create(resource_attributes)


def create_metric_views() -> list[View]:
    """Create the default OpenTelemetry metric views for Agent Framework."""
    try:
        from opentelemetry.sdk.metrics.view import DropAggregation, View
    except ModuleNotFoundError as ex:
        raise ModuleNotFoundError(
            "`opentelemetry-sdk` is required to use `create_metric_views()`. "
            "Please install `opentelemetry-sdk` and update your dependencies."
        ) from ex

    return [
        View(instrument_name="agent_framework*"),
        View(instrument_name="gen_ai*"),
        View(instrument_name="*", aggregation=DropAggregation()),
    ]


class _ObservabilitySettingsData(TypedDict, total=False):
    """TypedDict schema for observability settings fields."""

    enable_instrumentation: bool | None
    enable_sensitive_data: bool | None
    enable_console_exporters: bool | None
    vs_code_extension_port: int | None


class ObservabilitySettings:
    """Settings for Agent Framework Observability.

    If the environment variables are not found, the settings can
    be loaded from a .env file with the encoding 'utf-8'.
    If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the
    settings are missing.

    Warning:
        Sensitive events should only be enabled on test and development environments.

    Keyword Args:
        enable_instrumentation: Enable OpenTelemetry diagnostics. Default is True.
            Can be disabled by setting environment variable ENABLE_INSTRUMENTATION=false.
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
            # Instrumentation is enabled by default; set ENABLE_INSTRUMENTATION=false to disable.
            # Set ENABLE_CONSOLE_EXPORTERS=true
            settings = ObservabilitySettings()

            # Or passing parameters directly
            settings = ObservabilitySettings(enable_console_exporters=True)
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the settings."""
        env_file_path = kwargs.pop("env_file_path", None)
        env_file_encoding = kwargs.pop("env_file_encoding", None)
        data = load_settings(
            _ObservabilitySettingsData,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            **kwargs,
        )
        # Sticky-disable flag, set by `disable_instrumentation()`. When True, this
        # singleton refuses to be re-enabled by any subsequent assignment to the
        # `enable_instrumentation` / `enable_sensitive_data` properties (including
        # direct third-party writes). It can only be cleared by an explicit
        # `enable_instrumentation(force=True)` / `enable_sensitive_telemetry(force=True)`
        # call, which is the user re-stating their intent.
        self._user_disabled: bool = False
        # `enable_instrumentation` is defaulted to True if not set
        instrumentation_value = data.get("enable_instrumentation")
        self._enable_instrumentation: bool = True if instrumentation_value is None else instrumentation_value
        self._enable_sensitive_data: bool = data.get("enable_sensitive_data") or False
        if self._enable_sensitive_data and not self._enable_instrumentation:
            logger.warning(
                "Sensitive data capture is enabled but instrumentation is disabled. "
                "Sensitive data will not be captured. Please enable instrumentation to capture sensitive data."
            )

        self.enable_console_exporters: bool = data.get("enable_console_exporters") or False
        self.vs_code_extension_port: int | None = data.get("vs_code_extension_port")
        self.env_file_path = env_file_path
        self.env_file_encoding = env_file_encoding
        self._executed_setup = False

    @property
    def enable_instrumentation(self) -> bool:
        """Whether instrumentation is enabled.

        Always returns False once ``disable_instrumentation()`` has been called,
        regardless of the stored value, until ``enable_instrumentation(force=True)``
        clears the sticky disable.
        """
        if self._user_disabled:
            return False
        return self._enable_instrumentation

    @enable_instrumentation.setter
    def enable_instrumentation(self, value: bool) -> None:
        if self._user_disabled and value:
            # Defense in depth: a third-party (or internal) write of True is
            # silently dropped while the user-disabled flag is set, so the
            # sticky disable cannot be circumvented by direct attribute writes.
            logger.debug(
                "Ignoring enable_instrumentation=True assignment: instrumentation was explicitly disabled via "
                "disable_instrumentation(). Call enable_instrumentation(force=True) to clear the disable."
            )
            return
        self._enable_instrumentation = value

    @property
    def enable_sensitive_data(self) -> bool:
        """Whether sensitive-data capture is enabled.

        Always returns False once ``disable_instrumentation()`` has been called.
        """
        if self._user_disabled:
            return False
        return self._enable_sensitive_data

    @enable_sensitive_data.setter
    def enable_sensitive_data(self, value: bool) -> None:
        if self._user_disabled and value:
            logger.debug(
                "Ignoring enable_sensitive_data=True assignment: instrumentation was explicitly disabled via "
                "disable_instrumentation(). Call enable_sensitive_telemetry(force=True) to clear the disable."
            )
            return
        self._enable_sensitive_data = value

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

    @property
    def is_user_disabled(self) -> bool:
        """Whether ``disable_instrumentation()`` has been called and the disable is still in effect.

        Integrations that perform telemetry setup as a side-effect (e.g. provisioning Azure Monitor
        providers from a Foundry project's connection string) should consult this flag before doing
        their setup work, so the user's explicit opt-out is respected end-to-end and not just at the
        framework's span-emission boundary.
        """
        return self._user_disabled

    def _configure(
        self,
        *,
        additional_exporters: list[LogRecordExporter | SpanExporter | MetricExporter] | None = None,
        views: list[View] | None = None,
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

        exporters: list[LogRecordExporter | SpanExporter | MetricExporter] = []

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
        exporters: list[LogRecordExporter | MetricExporter | SpanExporter],
        views: list[View] | None = None,
    ) -> None:
        """Configure tracing, logging, events and metrics with the provided exporters.

        Args:
            exporters: A list of exporters for logs, metrics and/or spans.
            views: Optional list of OpenTelemetry views for metrics. Default is empty list.
        """
        try:
            from opentelemetry._logs import set_logger_provider
            from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import MetricExporter, PeriodicExportingMetricReader
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
        except ModuleNotFoundError as ex:
            raise ModuleNotFoundError(
                "`opentelemetry-sdk` is required to use `configure_otel_providers()`. "
                "Please install `opentelemetry-sdk` and update your dependencies."
            ) from ex

        span_exporters: list[SpanExporter] = []
        log_exporters: list[LogRecordExporter] = []
        metric_exporters: list[MetricExporter] = []
        resource = create_resource(
            env_file_path=self.env_file_path,
            env_file_encoding=self.env_file_encoding,
        )
        for exp in exporters:
            if isinstance(exp, SpanExporter):
                span_exporters.append(exp)
            if isinstance(exp, LogRecordExporter):
                log_exporters.append(exp)
            if isinstance(exp, MetricExporter):
                metric_exporters.append(exp)

        # Tracing
        if span_exporters:
            tracer_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(tracer_provider)
            for exporter in span_exporters:
                tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

        # Logging
        if log_exporters:
            logger_provider = LoggerProvider(resource=resource)
            for log_exporter in log_exporters:
                logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
            # Attach a handler with the provider to the root logger
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
                resource=resource,
                views=views or [],
            )
            metrics.set_meter_provider(meter_provider)


def get_tracer(
    instrumenting_module_name: str = "agent_framework",
    instrumenting_library_version: str = version_info,
    schema_url: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> trace.Tracer:
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
) -> metrics.Meter:
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


OBSERVABILITY_SETTINGS: ObservabilitySettings = ObservabilitySettings()


def _read_bool_env(name: str, *, default: bool = False) -> bool:
    """Read a boolean from an environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def _read_int_env(name: str, *, default: int | None = None) -> int | None:
    """Read an optional integer from an environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def enable_sensitive_telemetry(*, force: bool = False) -> None:
    """Enable capture of sensitive data in telemetry for your application.

    Instrumentation is enabled by default; this method exists to opt-in to capturing
    sensitive event payloads (e.g., chat messages, tool arguments).

    This method does not configure exporters or providers. It also ensures that
    instrumentation is enabled (in case it was explicitly disabled via the
    ENABLE_INSTRUMENTATION environment variable).

    Keyword Args:
        force: When True, clears any sticky disable previously set by
            ``disable_instrumentation()`` before enabling. Without it, calls are
            no-ops if instrumentation has been explicitly disabled.

    Warning:
        Sensitive events should only be enabled on test and development environments.
    """
    global OBSERVABILITY_SETTINGS
    if OBSERVABILITY_SETTINGS._user_disabled and not force:  # type: ignore[reportPrivateUsage]
        logger.info(
            "enable_sensitive_telemetry() ignored: instrumentation was explicitly disabled via "
            "disable_instrumentation(). Pass force=True to re-enable."
        )
        return
    if force:
        OBSERVABILITY_SETTINGS._user_disabled = False  # type: ignore[reportPrivateUsage]
    OBSERVABILITY_SETTINGS.enable_instrumentation = True
    OBSERVABILITY_SETTINGS.enable_sensitive_data = True


def disable_instrumentation() -> None:
    """Explicitly disable Agent Framework instrumentation for this process.

    The disable is **sticky**: subsequent attempts by framework auto-setup paths,
    library integrations, ``enable_instrumentation()``, ``enable_sensitive_telemetry()``,
    ``configure_otel_providers()``, or direct writes to
    ``OBSERVABILITY_SETTINGS.enable_instrumentation`` are ignored and no spans, metrics,
    or logs are emitted by Agent Framework code paths.

    To override the disable later, call ``enable_instrumentation(force=True)`` or
    ``enable_sensitive_telemetry(force=True)``. This makes the user's intent to opt out
    win against framework code that would otherwise re-enable instrumentation
    automatically.

    Note:
        Disabling does not tear down already-configured OpenTelemetry providers,
        exporters, or in-flight spans; it gates future captures by Agent Framework
        instrumentation only. To stop emitting telemetry from third-party
        instrumentations as well, configure them separately.
    """
    global OBSERVABILITY_SETTINGS
    OBSERVABILITY_SETTINGS._user_disabled = True  # type: ignore[reportPrivateUsage]
    OBSERVABILITY_SETTINGS._enable_instrumentation = False  # type: ignore[reportPrivateUsage]
    OBSERVABILITY_SETTINGS._enable_sensitive_data = False  # type: ignore[reportPrivateUsage]


def enable_instrumentation(
    *,
    enable_sensitive_data: bool | None = None,
    force: bool = False,
) -> None:
    """Enable instrumentation for Microsoft Agent Framework.

    Note that instrumentation is enabled by default, so this method is only necessary
    if you need a programmatic way to enable it (e.g., if you are not sure whether the
    environment variable ENABLE_INSTRUMENTATION is set to True or False and want to
    ensure it is enabled).

    Keyword Args:
        enable_sensitive_data: Enable OpenTelemetry sensitive events. Overrides
            the environment variable ENABLE_SENSITIVE_DATA if set. Default is None.
        force: When True, clears any sticky disable previously set by
            ``disable_instrumentation()`` before enabling. Without it, calls are
            no-ops if instrumentation has been explicitly disabled.
    """
    global OBSERVABILITY_SETTINGS
    if OBSERVABILITY_SETTINGS._user_disabled and not force:  # type: ignore[reportPrivateUsage]
        logger.info(
            "enable_instrumentation() ignored: instrumentation was explicitly disabled via "
            "disable_instrumentation(). Pass force=True to re-enable."
        )
        return
    if force:
        OBSERVABILITY_SETTINGS._user_disabled = False  # type: ignore[reportPrivateUsage]
    OBSERVABILITY_SETTINGS.enable_instrumentation = True
    if enable_sensitive_data is not None:
        OBSERVABILITY_SETTINGS.enable_sensitive_data = enable_sensitive_data
    else:
        # Re-read from current environment in case env vars were set after import (e.g. load_dotenv())
        OBSERVABILITY_SETTINGS.enable_sensitive_data = _read_bool_env("ENABLE_SENSITIVE_DATA")


def configure_otel_providers(
    *,
    enable_sensitive_data: bool | None = None,
    enable_console_exporters: bool | None = None,
    exporters: list[LogRecordExporter | SpanExporter | MetricExporter] | None = None,
    views: list[View] | None = None,
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
        (e.g., Azure Monitor) and just call `enable_sensitive_telemetry()` to opt-in to sensitive data capture.

    Note:
        By default, the Agent Framework emits metrics with the prefixes `agent_framework`
        and `gen_ai` (OpenTelemetry GenAI semantic conventions). You can use the `views`
        parameter to filter which metrics are collected and exported. You can also use
        the `create_metric_views()` helper function to get default views.

    Keyword Args:
        enable_sensitive_data: Enable OpenTelemetry sensitive events. Overrides
            the environment variable ENABLE_SENSITIVE_DATA if set. Default is None.
        enable_console_exporters: Enable console exporters for traces, logs, and metrics.
            Overrides the environment variable ENABLE_CONSOLE_EXPORTERS if set. Default is None.
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
            from agent_framework.observability import enable_sensitive_telemetry
            from azure.monitor.opentelemetry import configure_azure_monitor

            connection_string = "InstrumentationKey=your_instrumentation_key_here;..."
            configure_azure_monitor(connection_string=connection_string)
            # Optional: opt into capturing sensitive data
            enable_sensitive_telemetry()

    References:
        - https://opentelemetry.io/docs/languages/sdk-configuration/general/
        - https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/
    """
    global OBSERVABILITY_SETTINGS
    if OBSERVABILITY_SETTINGS._user_disabled:  # type: ignore[reportPrivateUsage]
        logger.info(
            "configure_otel_providers(): instrumentation was explicitly disabled via "
            "disable_instrumentation(); providers and exporters will still be configured but "
            "Agent Framework will emit no telemetry until enable_instrumentation(force=True) is called."
        )
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
        if enable_console_exporters is not None:
            settings_kwargs["enable_console_exporters"] = enable_console_exporters
        if vs_code_extension_port is not None:
            settings_kwargs["vs_code_extension_port"] = vs_code_extension_port

        updated_settings = ObservabilitySettings(**settings_kwargs)
        OBSERVABILITY_SETTINGS.enable_instrumentation = updated_settings.enable_instrumentation
        OBSERVABILITY_SETTINGS.enable_sensitive_data = updated_settings.enable_sensitive_data
        OBSERVABILITY_SETTINGS.enable_console_exporters = updated_settings.enable_console_exporters
        OBSERVABILITY_SETTINGS.vs_code_extension_port = updated_settings.vs_code_extension_port
        OBSERVABILITY_SETTINGS.env_file_path = updated_settings.env_file_path
        OBSERVABILITY_SETTINGS.env_file_encoding = updated_settings.env_file_encoding
        OBSERVABILITY_SETTINGS._executed_setup = False  # type: ignore[reportPrivateUsage]
    else:
        # Re-read settings from current environment in case env vars were set
        # after import (e.g. via load_dotenv()). Explicit parameters take precedence.
        OBSERVABILITY_SETTINGS.enable_instrumentation = True
        OBSERVABILITY_SETTINGS.enable_sensitive_data = (
            enable_sensitive_data if enable_sensitive_data is not None else _read_bool_env("ENABLE_SENSITIVE_DATA")
        )
        OBSERVABILITY_SETTINGS.enable_console_exporters = (
            enable_console_exporters
            if enable_console_exporters is not None
            else _read_bool_env("ENABLE_CONSOLE_EXPORTERS")
        )
        OBSERVABILITY_SETTINGS.vs_code_extension_port = (
            vs_code_extension_port if vs_code_extension_port is not None else _read_int_env("VS_CODE_EXTENSION_PORT")
        )
        OBSERVABILITY_SETTINGS._executed_setup = False  # type: ignore[reportPrivateUsage]

    OBSERVABILITY_SETTINGS._configure(  # type: ignore[reportPrivateUsage]
        additional_exporters=exporters,
        views=views,
    )


# region Chat Client Telemetry


def _get_duration_histogram() -> metrics.Histogram:
    return get_meter().create_histogram(
        name=OtelAttr.LLM_OPERATION_DURATION,
        unit=OtelAttr.DURATION_UNIT,
        description="Captures the duration of operations of function-invoking chat clients",
        explicit_bucket_boundaries_advisory=OPERATION_DURATION_BUCKET_BOUNDARIES,
    )


def _get_token_usage_histogram() -> metrics.Histogram:
    return get_meter().create_histogram(
        name=OtelAttr.LLM_TOKEN_USAGE,
        unit=OtelAttr.T_UNIT,
        description="Captures the token usage of chat clients",
        explicit_bucket_boundaries_advisory=TOKEN_USAGE_BUCKET_BOUNDARIES,
    )


OptionsCoT = TypeVar(
    "OptionsCoT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ChatOptions[None]",
    covariant=True,
)


class ChatTelemetryLayer(Generic[OptionsCoT]):
    """Layer that wraps chat client get_response with OpenTelemetry tracing."""

    def __init__(self, *args: Any, otel_provider_name: str | None = None, **kwargs: Any) -> None:
        """Initialize telemetry attributes and histograms."""
        super().__init__(*args, **kwargs)
        self.token_usage_histogram = _get_token_usage_histogram()
        self.duration_histogram = _get_duration_histogram()
        self.otel_provider_name = otel_provider_name or getattr(self, "OTEL_PROVIDER_NAME", "unknown")

    @staticmethod
    def _backfill_request_model(span: trace.Span, attributes: dict[str, Any]) -> None:
        """Backfill REQUEST_MODEL and the span name from RESPONSE_MODEL when unknown.

        Chat-completion spans use REQUEST_MODEL as part of the span name. If the
        request model was not known at span creation time (e.g. the client could
        not resolve it before sending the request), update both the attribute and
        the span name to the actual model returned in the response. Mutates
        ``attributes`` in place.
        """
        response_model = attributes.get(OtelAttr.RESPONSE_MODEL)
        if response_model and attributes.get(OtelAttr.REQUEST_MODEL, "unknown") == "unknown":
            attributes[OtelAttr.REQUEST_MODEL] = response_model
            operation = attributes.get(OtelAttr.OPERATION, "operation")
            span.update_name(f"{operation} {response_model}")

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[ResponseModelBoundT],
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[ResponseModelBoundT]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: OptionsCoT | ChatOptions[None] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: OptionsCoT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Trace chat responses with OpenTelemetry spans and metrics.

        Args:
            messages: The message or messages to send to the model.
            stream: Whether to stream the response. Defaults to False.
            options: Chat options as a TypedDict.
            compaction_strategy: Optional compaction strategy to apply before model calls.
            tokenizer: Optional tokenizer used by token-aware compaction strategies.

        Keyword Args:
            function_invocation_kwargs: Keyword arguments forwarded only to tool invocation layers.
            client_kwargs: Additional client-specific keyword arguments for downstream chat clients.
        """
        from ._types import ChatResponse, ChatResponseUpdate, ResponseStream  # type: ignore[reportUnusedImport]

        global OBSERVABILITY_SETTINGS
        super_get_response = super().get_response  # type: ignore[misc]
        merged_client_kwargs = dict(client_kwargs) if client_kwargs is not None else {}

        if not OBSERVABILITY_SETTINGS.ENABLED:
            return super_get_response(  # type: ignore[no-any-return]
                messages=messages,
                stream=stream,
                options=options,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                function_invocation_kwargs=function_invocation_kwargs,
                client_kwargs=merged_client_kwargs,
            )

        opts: dict[str, Any] = options or {}  # type: ignore[assignment]
        provider_name = str(getattr(self, "otel_provider_name", "unknown"))
        model = merged_client_kwargs.get("model") or opts.get("model") or getattr(self, "model", None) or "unknown"
        service_url_func = getattr(self, "service_url", None)
        service_url = str(service_url_func() if callable(service_url_func) else "unknown")
        attributes = _get_span_attributes(
            operation_name=OtelAttr.CHAT_COMPLETION_OPERATION,
            provider_name=provider_name,
            model=model,
            service_url=service_url,
            **merged_client_kwargs,
        )

        if stream:
            agent_span = trace.get_current_span()
            span = _start_streaming_span(attributes, OtelAttr.REQUEST_MODEL)

            if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and messages and span.is_recording():
                system_instructions = _get_instructions_from_options(opts)
                _capture_current_agent_system_instructions(
                    agent_span,
                    span,
                    system_instructions,
                )
                _capture_messages(
                    span=span,
                    provider_name=provider_name,
                    messages=messages,
                    system_instructions=system_instructions,
                )

            span_state = {"closed": False}
            duration_state: dict[str, float] = {}
            start_time = perf_counter()

            def _close_span() -> None:
                if span_state["closed"]:
                    return
                span_state["closed"] = True
                span.end()

            def _record_duration() -> None:
                duration_state["duration"] = perf_counter() - start_time

            try:
                # Activate the chat span across the synchronous setup phase so spans
                # created by the underlying client while constructing the stream are
                # parented under it. The per-pull ``_activate_span`` registered below
                # covers iteration; this covers anything the subclass does between
                # being called and returning the ResponseStream. Attach/detach are
                # paired within this sync block, so there is no cross-context
                # detach risk (the span itself is ended later in cleanup hooks).
                with _activate_span(span):
                    result_stream = cast(
                        ResponseStream[ChatResponseUpdate, ChatResponse[Any]],
                        super_get_response(
                            messages=messages,
                            stream=True,
                            options=opts,
                            compaction_strategy=compaction_strategy,
                            tokenizer=tokenizer,
                            function_invocation_kwargs=function_invocation_kwargs,
                            client_kwargs=merged_client_kwargs,
                        ),
                    )
            except Exception as exception:
                capture_exception(span=span, exception=exception, timestamp=time_ns())
                _close_span()
                raise

            async def _finalize_stream() -> None:
                from ._types import ChatResponse

                try:
                    if result_stream._stream_error is not None:  # pyright: ignore[reportPrivateUsage]
                        # Stream errored; skip get_final_response() to avoid firing
                        # result hooks such as after_run context providers on error
                        # paths. Capture the error on the span before returning.
                        capture_exception(span=span, exception=result_stream._stream_error, timestamp=time_ns())  # pyright: ignore[reportPrivateUsage]
                        return
                    response: ChatResponse[Any] = await result_stream.get_final_response()
                    duration = duration_state.get("duration")
                    response_attributes = _get_response_attributes(attributes, response)
                    self._backfill_request_model(span, response_attributes)
                    _capture_response(
                        span=span,
                        attributes=response_attributes,
                        token_usage_histogram=getattr(self, "token_usage_histogram", None),
                        operation_duration_histogram=getattr(self, "duration_histogram", None),
                        duration=duration,
                    )
                    _mark_inner_response_telemetry_captured(response)
                    if (
                        OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED
                        and isinstance(response, ChatResponse)
                        and response.messages
                        and span.is_recording()
                    ):
                        _capture_messages(
                            span=span,
                            provider_name=provider_name,
                            messages=response.messages,
                            finish_reason=response.finish_reason,  # type: ignore[arg-type]
                            output=True,
                        )
                except Exception as exception:
                    capture_exception(span=span, exception=exception, timestamp=time_ns())
                finally:
                    _close_span()

            # The pull context manager attaches the span around each underlying iterator pull so
            # that child spans created during the pull (e.g. HTTP requests, inner tool execution)
            # are parented under this chat span. Attach and detach happen in the same async
            # context as the pull, avoiding cross-context cleanup issues. The weakref finalizer
            # ensures the span is closed even if the stream is garbage collected without being
            # consumed.
            wrapped_stream: ResponseStream[ChatResponseUpdate, ChatResponse[Any]] = (
                result_stream
                .with_cleanup_hook(_record_duration)
                .with_cleanup_hook(_finalize_stream)
                .with_pull_context_manager(lambda: _activate_span(span))
            )
            weakref.finalize(wrapped_stream, _close_span)
            return wrapped_stream

        async def _get_response() -> ChatResponse:
            agent_span = trace.get_current_span()
            with _get_span(attributes=attributes, span_name_attribute=OtelAttr.REQUEST_MODEL) as span:
                if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and messages and span.is_recording():
                    system_instructions = _get_instructions_from_options(opts)
                    _capture_current_agent_system_instructions(
                        agent_span,
                        span,
                        system_instructions,
                    )
                    _capture_messages(
                        span=span,
                        provider_name=provider_name,
                        messages=messages,
                        system_instructions=system_instructions,
                    )
                start_time_stamp = perf_counter()
                try:
                    response = cast(
                        ChatResponse[Any],
                        await super_get_response(
                            messages=messages,
                            stream=False,
                            options=opts,
                            compaction_strategy=compaction_strategy,
                            tokenizer=tokenizer,
                            function_invocation_kwargs=function_invocation_kwargs,
                            client_kwargs=merged_client_kwargs,
                        ),
                    )
                except Exception as exception:
                    capture_exception(span=span, exception=exception, timestamp=time_ns())
                    raise
                duration = perf_counter() - start_time_stamp
                response_attributes = _get_response_attributes(attributes, response)
                self._backfill_request_model(span, response_attributes)
                _capture_response(
                    span=span,
                    attributes=response_attributes,
                    token_usage_histogram=getattr(self, "token_usage_histogram", None),
                    operation_duration_histogram=getattr(self, "duration_histogram", None),
                    duration=duration,
                )
                _mark_inner_response_telemetry_captured(response)
                if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and response.messages and span.is_recording():
                    finish_reason = cast(
                        "FinishReason | None",
                        response.finish_reason if response.finish_reason in FINISH_REASON_MAP else None,
                    )
                    _capture_messages(
                        span=span,
                        provider_name=provider_name,
                        messages=response.messages,
                        finish_reason=finish_reason,
                        output=True,
                    )
                return response

        return _get_response()


EmbeddingOptionsT = TypeVar(
    "EmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="EmbeddingGenerationOptions",
    covariant=True,
)


class EmbeddingTelemetryLayer(Generic[EmbeddingInputT, EmbeddingT, EmbeddingOptionsT]):
    """Layer that wraps embedding client get_embeddings with OpenTelemetry tracing."""

    def __init__(self, *args: Any, otel_provider_name: str | None = None, **kwargs: Any) -> None:
        """Initialize telemetry attributes and histograms."""
        super().__init__(*args, **kwargs)
        self.token_usage_histogram = _get_token_usage_histogram()
        self.duration_histogram = _get_duration_histogram()
        self.otel_provider_name = otel_provider_name or getattr(self, "OTEL_PROVIDER_NAME", "unknown")

    async def get_embeddings(
        self,
        values: Sequence[EmbeddingInputT],
        *,
        options: EmbeddingOptionsT | None = None,
    ) -> GeneratedEmbeddings[EmbeddingT, EmbeddingOptionsT]:
        """Trace embedding generation with OpenTelemetry spans and metrics."""
        from ._types import GeneratedEmbeddings  # type: ignore[reportUnusedImport]

        global OBSERVABILITY_SETTINGS
        super_get_embeddings = super().get_embeddings  # type: ignore[misc]

        if not OBSERVABILITY_SETTINGS.ENABLED:
            return await super_get_embeddings(values, options=options)  # type: ignore[no-any-return]

        opts: dict[str, Any] = options or {}  # type: ignore[assignment]
        provider_name = str(getattr(self, "otel_provider_name", "unknown"))
        model = opts.get("model") or getattr(self, "model", None) or "unknown"
        service_url_func = getattr(self, "service_url", None)
        service_url = str(service_url_func() if callable(service_url_func) else "unknown")
        attributes = _get_span_attributes(
            operation_name=OtelAttr.EMBEDDING_OPERATION,
            provider_name=provider_name,
            model=model,
            service_url=service_url,
        )

        with _get_span(attributes=attributes, span_name_attribute=OtelAttr.REQUEST_MODEL) as span:
            start_time_stamp = perf_counter()
            try:
                result = cast(
                    GeneratedEmbeddings[EmbeddingT, EmbeddingOptionsT],
                    await super_get_embeddings(values, options=options),
                )
            except Exception as exception:
                capture_exception(span=span, exception=exception, timestamp=time_ns())
                raise
            duration = perf_counter() - start_time_stamp
            response_attributes: dict[str, Any] = {**attributes}
            usage = result.usage or {}
            if (input_tokens := usage.get("input_token_count")) is not None:
                response_attributes[OtelAttr.INPUT_TOKENS] = input_tokens
            _capture_response(
                span=span,
                attributes=response_attributes,
                token_usage_histogram=self.token_usage_histogram,
                operation_duration_histogram=self.duration_histogram,
                duration=duration,
            )
            return result


class AgentTelemetryLayer:
    """Layer that wraps agent run with OpenTelemetry tracing."""

    def __init__(
        self,
        *args: Any,
        otel_agent_provider_name: str | None = None,
        otel_provider_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize telemetry attributes and histograms."""
        self.otel_provider_name = (
            otel_agent_provider_name or otel_provider_name or getattr(self, "AGENT_PROVIDER_NAME", "unknown")
        )
        super().__init__(*args, **kwargs)
        self.token_usage_histogram = _get_token_usage_histogram()
        self.duration_histogram = _get_duration_histogram()

    def _trace_agent_invocation(
        self,
        *,
        messages: AgentRunInputs | None,
        session: AgentSession | None,
        merged_options: Mapping[str, Any],
        client_kwargs: Mapping[str, Any] | None,
        stream: bool,
        execute: Callable[[], Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]],
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Trace an agent invocation while delegating execution to ``execute``."""
        global OBSERVABILITY_SETTINGS
        from ._types import ResponseStream

        if not OBSERVABILITY_SETTINGS.ENABLED:
            return execute()

        provider_name = str(self.otel_provider_name)
        merged_client_kwargs = dict(client_kwargs) if client_kwargs is not None else {}
        get_otel_conversation_id = cast(
            "Callable[[AgentSession | None], str | None] | None",
            getattr(self, "_get_otel_conversation_id", None),
        )
        conversation_id = (
            get_otel_conversation_id(session)
            if callable(get_otel_conversation_id)
            else (session.service_session_id if (session and isinstance(session.service_session_id, str)) else None)
        )
        attributes = _get_span_attributes(
            operation_name=OtelAttr.AGENT_INVOKE_OPERATION,
            provider_name=provider_name,
            agent_id=getattr(self, "id", "unknown"),
            agent_name=getattr(self, "name", None) or getattr(self, "id", "unknown"),
            agent_description=getattr(self, "description", None),
            thread_id=conversation_id,
            all_options=dict(merged_options),
            **merged_client_kwargs,
        )

        if stream:
            # Do NOT set the inner-telemetry context vars here: this synchronous run() body executes
            # in the CALLER's context, but the ResponseStream may be consumed in a different context
            # (e.g. ``stream = agent.run(stream=True)`` then ``await asyncio.create_task(consume(stream))``).
            # The cleanup-hook reset (in _finalize_stream) runs in the consuming context, so a token
            # created here would raise ``ValueError: <Token ...> was created in a different Context``.
            # Instead the tokens are set lazily on the first pull (see _inner_telemetry_pull_context
            # below), so set and reset both happen in the consumer's context.
            inner_response_telemetry_captured_fields: set[str] = set()
            inner_response_telemetry_captured_fields_token: contextvars.Token[set[str] | None] | None = None
            inner_accumulated_usage_token: contextvars.Token[UsageDetails | None] | None = None
            span = _start_streaming_span(attributes, OtelAttr.AGENT_NAME)

            if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and messages and span.is_recording():
                _capture_messages(
                    span=span,
                    provider_name=provider_name,
                    messages=messages,
                    system_instructions=_get_instructions_from_options(dict(merged_options)),
                )

            span_state = {"closed": False}
            duration_state: dict[str, float] = {}
            start_time = perf_counter()

            def _close_span() -> None:
                if span_state["closed"]:
                    return
                span_state["closed"] = True
                span.end()

            def _record_duration() -> None:
                duration_state["duration"] = perf_counter() - start_time

            try:
                # Activate the agent span across the synchronous setup phase so spans
                # created by the underlying agent while constructing the stream are
                # parented under it. The per-pull ``_activate_span`` registered below
                # covers iteration; this covers anything the subclass does between
                # being called and returning the ResponseStream (subclasses that
                # instead return an Awaitable defer their work into the first pull,
                # where the per-pull activation already applies). Attach/detach are
                # paired within this sync block, so there is no cross-context detach
                # risk (the span itself is ended later in cleanup hooks).
                with _activate_span(span):
                    run_result: object = execute()
                if isinstance(run_result, ResponseStream):
                    result_stream: ResponseStream[AgentResponseUpdate, AgentResponse[Any]] = run_result  # pyright: ignore[reportUnknownVariableType]
                elif isinstance(run_result, Awaitable):
                    result_stream = ResponseStream.from_awaitable(run_result)  # type: ignore[arg-type]
                else:
                    raise RuntimeError("Streaming telemetry requires a ResponseStream result.")
            except Exception as exception:
                capture_exception(span=span, exception=exception, timestamp=time_ns())
                _close_span()
                raise

            async def _finalize_stream() -> None:
                from ._types import AgentResponse

                try:
                    if result_stream._stream_error is not None:  # pyright: ignore[reportPrivateUsage]
                        # Stream errored; skip get_final_response() to avoid firing
                        # result hooks such as after_run context providers on error
                        # paths. Capture the error on the span before returning.
                        capture_exception(span=span, exception=result_stream._stream_error, timestamp=time_ns())  # pyright: ignore[reportPrivateUsage]
                        return
                    response: AgentResponse[Any] = await result_stream.get_final_response()
                    duration = duration_state.get("duration")
                    response_attributes = _get_response_attributes(
                        attributes,
                        response,
                        capture_response_id=INNER_RESPONSE_ID_CAPTURED_FIELD
                        not in inner_response_telemetry_captured_fields,
                        capture_usage=INNER_USAGE_CAPTURED_FIELD not in inner_response_telemetry_captured_fields,
                    )
                    _apply_accumulated_usage(response_attributes, inner_response_telemetry_captured_fields)
                    _capture_response(span=span, attributes=response_attributes, duration=duration)
                    if (
                        OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED
                        and isinstance(response, AgentResponse)
                        and response.messages
                        and span.is_recording()
                    ):
                        _capture_messages(
                            span=span,
                            provider_name=provider_name,
                            messages=response.messages,
                            output=True,
                        )
                except Exception as exception:
                    capture_exception(span=span, exception=exception, timestamp=time_ns())
                finally:
                    # Reset only if the lazy set actually ran (it may not have if the stream was
                    # never pulled). These run in the consuming context — the same context the
                    # pull-context factory below set the tokens in — so the reset is cross-context safe.
                    if inner_response_telemetry_captured_fields_token is not None:
                        INNER_RESPONSE_TELEMETRY_CAPTURED_FIELDS.reset(inner_response_telemetry_captured_fields_token)
                    if inner_accumulated_usage_token is not None:
                        INNER_ACCUMULATED_USAGE.reset(inner_accumulated_usage_token)
                    _close_span()

            def _inner_telemetry_pull_context() -> contextlib.AbstractContextManager[Any]:
                # Invoked at the start of every pull (and during stream resolution), in the
                # consuming context. On the first pull it sets the inner-telemetry context vars so
                # that set and the reset in _finalize_stream both run in the consumer's context,
                # avoiding the cross-context Token reset failure. Setting happens before the
                # underlying iterator is pulled, so inner chat completion spans created during the
                # pull can still accumulate usage / mark captured fields.
                nonlocal inner_response_telemetry_captured_fields_token, inner_accumulated_usage_token
                if inner_response_telemetry_captured_fields_token is None:
                    inner_response_telemetry_captured_fields_token = INNER_RESPONSE_TELEMETRY_CAPTURED_FIELDS.set(
                        inner_response_telemetry_captured_fields
                    )
                    inner_accumulated_usage_token = INNER_ACCUMULATED_USAGE.set({})
                return _activate_span(span)

            # The pull context manager attaches the span around each underlying iterator pull so
            # that child spans created during the pull (e.g. inner chat completion spans from the
            # underlying ChatTelemetryLayer) are parented under this agent invoke span. Attach and
            # detach happen in the same async context as the pull, avoiding cross-context cleanup
            # issues. It also lazily sets the inner-telemetry context vars on the first pull (see
            # _inner_telemetry_pull_context). The weakref finalizer ensures the span is closed even
            # if the stream is garbage collected without being consumed.
            wrapped_stream: ResponseStream[AgentResponseUpdate, AgentResponse[Any]] = (
                result_stream
                .with_cleanup_hook(_record_duration)
                .with_cleanup_hook(_finalize_stream)
                .with_pull_context_manager(_inner_telemetry_pull_context)
            )
            weakref.finalize(wrapped_stream, _close_span)
            return wrapped_stream

        async def _run() -> AgentResponse[Any]:
            # Set the inner-telemetry context vars inside the coroutine so the set and the
            # reset in `finally` always happen in the same execution context. `run()` is a sync
            # method that returns this coroutine, which may be awaited in a different context than
            # the one that called `run()` (e.g. `asyncio.create_task(agent.run(...))`, as used by
            # BackgroundAgentsProvider). A contextvars.Token can only be reset in the context that
            # created it, so setting eagerly in `run()`/`_trace_agent_invocation` and resetting
            # here would raise "Token was created in a different Context".
            inner_response_telemetry_captured_fields: set[str] = set()
            inner_response_telemetry_captured_fields_token = INNER_RESPONSE_TELEMETRY_CAPTURED_FIELDS.set(
                inner_response_telemetry_captured_fields
            )
            inner_accumulated_usage_token = INNER_ACCUMULATED_USAGE.set({})
            try:
                with _get_span(attributes=attributes, span_name_attribute=OtelAttr.AGENT_NAME) as span:
                    try:
                        if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED and messages and span.is_recording():
                            _capture_messages(
                                span=span,
                                provider_name=provider_name,
                                messages=messages,
                                system_instructions=_get_instructions_from_options(dict(merged_options)),
                            )
                        start_time_stamp = perf_counter()
                        response: AgentResponse[Any] = await execute()
                        duration = perf_counter() - start_time_stamp
                        if response:
                            response_attributes = _get_response_attributes(
                                attributes,
                                response,
                                capture_response_id=INNER_RESPONSE_ID_CAPTURED_FIELD
                                not in inner_response_telemetry_captured_fields,
                                capture_usage=(
                                    INNER_USAGE_CAPTURED_FIELD not in inner_response_telemetry_captured_fields
                                ),
                            )
                            _apply_accumulated_usage(response_attributes, inner_response_telemetry_captured_fields)
                            _capture_response(span=span, attributes=response_attributes, duration=duration)
                            if (
                                OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED
                                and response.messages
                                and span.is_recording()
                            ):
                                _capture_messages(
                                    span=span,
                                    provider_name=provider_name,
                                    messages=response.messages,
                                    output=True,
                                )
                        return response
                    except Exception as exception:
                        capture_exception(span=span, exception=exception, timestamp=time_ns())
                        raise
            finally:
                INNER_RESPONSE_TELEMETRY_CAPTURED_FIELDS.reset(inner_response_telemetry_captured_fields_token)
                INNER_ACCUMULATED_USAGE.reset(inner_accumulated_usage_token)

        return _run()

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: ChatOptions[ResponseModelBoundT],
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[ResponseModelBoundT]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: ChatOptions[None] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        options: ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Trace agent runs with OpenTelemetry spans and metrics."""
        from ._types import merge_chat_options

        super_run = cast(
            "Callable[..., Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]]",
            super().run,  # type: ignore[misc]
        )
        super_run_kwargs: dict[str, Any] = {
            "messages": messages,
            "stream": stream,
            "session": session,
            "tools": tools,
            "options": options,
            "compaction_strategy": compaction_strategy,
            "tokenizer": tokenizer,
            "function_invocation_kwargs": function_invocation_kwargs,
            "client_kwargs": client_kwargs,
        }
        if middleware is not None:
            super_run_kwargs["middleware"] = middleware

        default_options = dict(getattr(self, "default_options", {}))
        merged_client_kwargs = dict(client_kwargs) if client_kwargs is not None else {}
        merged_options: dict[str, Any] = merge_chat_options(
            default_options, dict(options) if options is not None else {}
        )
        return self._trace_agent_invocation(
            messages=messages,
            session=session,
            merged_options=merged_options,
            client_kwargs=merged_client_kwargs,
            stream=stream,
            execute=lambda: super_run(**super_run_kwargs),
        )


# region Otel Helpers


def get_function_span_attributes(function: FunctionTool, tool_call_id: str | None = None) -> dict[str, str]:
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
) -> _AgnosticContextManager[trace.Span]:
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


# region MCP span helpers


@contextlib.contextmanager
def create_mcp_client_span(
    method_name: str,
    target: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Generator[trace.Span, Any, Any]:
    """Create an MCP client span per OTel MCP semantic conventions.

    Span name follows the format ``{mcp.method.name} {target}`` when a target
    is available, otherwise just ``{mcp.method.name}``.

    See: https://opentelemetry.io/docs/specs/semconv/gen-ai/mcp/#client

    Args:
        method_name: The MCP method name (e.g. ``initialize``, ``tools/call``).
        target: Optional low-cardinality target (tool name, prompt name).
        attributes: Additional span attributes.
    """
    span_name = f"{method_name} {target}" if target else method_name
    attrs: dict[str, Any] = {OtelAttr.MCP_METHOD_NAME: method_name}
    if attributes:
        attrs.update(attributes)
    tracer = get_tracer() if OBSERVABILITY_SETTINGS.ENABLED else trace.NoOpTracer()
    span = tracer.start_span(span_name, kind=trace.SpanKind.CLIENT, attributes=attrs)
    with trace.use_span(
        span=span,
        end_on_exit=True,
        record_exception=True,
        set_status_on_exception=True,
    ) as current_span:
        yield current_span


def set_mcp_span_error(
    span: trace.Span,
    error_type: str,
    description: str | None = None,
) -> None:
    """Set error status and ``error.type`` on an MCP span.

    Args:
        span: The span to mark as errored.
        error_type: The error type string (e.g. ``tool_error``, exception class name).
        description: Optional description (e.g. JSON-RPC error message).
    """
    span.set_attribute(OtelAttr.ERROR_TYPE, error_type)
    span.set_status(trace.StatusCode.ERROR, description=description)


# endregion


@contextlib.contextmanager
def _activate_span(span: trace.Span) -> Generator[None]:
    """Attach ``span`` as the current span in the OpenTelemetry context.

    Designed to be used as a per-pull context manager registered on a
    ``ResponseStream`` via ``with_pull_context_manager``: it attaches the span
    before each underlying iterator pull and detaches immediately after, so
    child spans created during the pull (HTTP clients, inner chat completions,
    tool execution) are correctly parented under ``span``.

    Because attach and detach happen within the same ``__anext__`` invocation
    (and therefore the same async task / contextvars context), there is no risk
    of "Failed to detach context" warnings from cross-context cleanup.
    """
    token = otel_context.attach(trace.set_span_in_context(span))
    try:
        yield
    finally:
        otel_context.detach(token)


@contextlib.contextmanager
def _get_span(
    attributes: dict[str, Any],
    span_name_attribute: str,
) -> Generator[trace.Span, Any, Any]:
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


def _start_streaming_span(attributes: dict[str, Any], span_name_attribute: str) -> trace.Span:
    """Start a non-current span for a streaming operation.

    Unlike :func:`_get_span`, the returned span is not attached to the current
    OpenTelemetry context. The caller is responsible for:

    - Ending the span via cleanup hooks on the wrapped
      :class:`~agent_framework._types.ResponseStream`.
    - Activating the span around each iterator pull via
      :func:`_activate_span` registered with ``with_pull_context_manager`` so
      that child spans created during stream production inherit it as parent.

    Streaming spans are closed asynchronously in cleanup hooks that run in a
    different async context than creation, so attaching the span at creation
    time would cause "Failed to detach context" errors from OpenTelemetry.
    """
    operation = attributes.get(OtelAttr.OPERATION, "operation")
    span_name = attributes.get(span_name_attribute, "unknown")
    span = get_tracer().start_span(f"{operation} {span_name}")
    span.set_attributes(attributes)
    return span


def _get_instructions_from_options(options: Any) -> str | list[str] | None:
    """Extract instructions from options dict."""
    if options is None:
        return None
    if isinstance(options, Mapping):
        instructions = cast(Mapping[str, Any], options).get("instructions")
        if isinstance(instructions, str):
            return instructions
        if isinstance(instructions, list) and all(isinstance(item, str) for item in instructions):  # type: ignore[reportUnknownVariableType]
            return instructions  # type: ignore[reportUnknownVariableType]
        return None
    return None


# region OTel tool definitions

# Per-item in-memory cache of computed OTel tool definitions, keyed by the tool
# object's identity. Tool objects (e.g. ``FunctionTool``, ``MCPTool``) are often
# reused across runs, so caching their converted definitions avoids repeating the
# isinstance checks, schema generation, and dict construction on every invocation.
# A ``WeakKeyDictionary`` lets entries be garbage collected with their tools.
# Unhashable / non-weak-referenceable specs (e.g. plain dicts) bypass the cache.
_TOOL_OTEL_DEFINITION_CACHE: weakref.WeakKeyDictionary[Any, dict[str, Any] | None] = weakref.WeakKeyDictionary()
# Sentinel distinguishing "not cached" from a cached ``None`` (unparseable tool).
_CACHE_MISS: Final = object()


def _tools_to_dict(
    tools: Any,
) -> list[dict[str, Any]] | None:
    """Convert tools into OpenTelemetry GenAI tool definitions.

    The output conforms to the OTel GenAI tool-definitions schema, where each
    entry is either a ``FunctionToolDefinition`` (``type="function"`` with
    ``name`` and optional ``description``/``parameters``) or a
    ``GenericToolDefinition`` (any ``type`` plus a ``name``). See
    https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-tool-definitions.json.

    Args:
        tools: The tools to parse. Can be a single tool or a sequence of tools.

    Returns:
        A list of OTel-conformant tool-definition dicts, or ``None`` when
        ``tools`` is empty or no tool can be represented.
    """
    from ._tools import normalize_tools

    normalized_tools = normalize_tools(tools)
    if not normalized_tools:
        return None
    results: list[dict[str, Any]] = []
    for tool_item in normalized_tools:
        otel_def = _tool_to_otel_definition(tool_item)
        if otel_def is not None:
            results.append(otel_def)
    return results or None


def _tool_to_otel_definition(tool_item: Any) -> dict[str, Any] | None:
    """Convert a single tool spec into an OTel GenAI tool-definition dict.

    Results are cached per tool object (keyed by identity) so repeated runs that
    reuse the same tool instances skip the conversion work. Specs that cannot be
    weakly referenced (e.g. plain dicts) are converted without caching.

    Returns ``None`` and emits a warning when the input cannot be represented
    as either a ``FunctionToolDefinition`` or a ``GenericToolDefinition``.
    """
    try:
        cached = _TOOL_OTEL_DEFINITION_CACHE.get(tool_item, _CACHE_MISS)
    except TypeError:
        # Unhashable spec (e.g. a plain dict); convert without caching.
        return _build_tool_otel_definition(tool_item)
    if cached is not _CACHE_MISS:
        return cast("dict[str, Any] | None", cached)

    definition = _build_tool_otel_definition(tool_item)
    with contextlib.suppress(TypeError):
        # Object may not support weak references; skip caching when that is the case.
        _TOOL_OTEL_DEFINITION_CACHE[tool_item] = definition
    return definition


def _build_tool_otel_definition(tool_item: Any) -> dict[str, Any] | None:
    """Convert a single tool spec into an OTel GenAI tool-definition dict (uncached)."""
    from pydantic import BaseModel

    from ._mcp import MCPTool
    from ._serialization import SerializationMixin
    from ._tools import FunctionTool

    if isinstance(tool_item, FunctionTool):
        definition: dict[str, Any] = {"type": "function", "name": tool_item.name}
        if tool_item.description:
            definition["description"] = tool_item.description
        parameters = tool_item.parameters()
        if parameters:
            definition["parameters"] = parameters
        return definition

    if isinstance(tool_item, MCPTool):
        definition = {"type": "mcp", "name": tool_item.name}
        if tool_item.description:
            definition["description"] = tool_item.description
        return definition

    raw: Mapping[str, Any] | None = None
    if isinstance(tool_item, BaseModel):
        raw = tool_item.model_dump(exclude_none=True)
    elif isinstance(tool_item, SerializationMixin):
        raw = tool_item.to_dict()
    elif isinstance(tool_item, Mapping):
        raw = cast("Mapping[str, Any]", tool_item)

    if raw is None:
        logger.warning(
            "Can't parse tool to OpenTelemetry tool definition: %s",
            type(tool_item).__name__,  # type: ignore[reportUnknownArgumentType]
        )
        return None
    return _otel_definition_from_mapping(raw)


def _otel_definition_from_mapping(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """Reshape a tool spec mapping into an OTel GenAI tool-definition dict.

    Handles the nested OpenAI Chat Completions function shape
    (``{"type": "function", "function": {...}}``) by flattening it into the
    OTel shape.
    """
    # OpenAI Chat Completions nests the function spec one level deeper; flatten it.
    nested_function = raw.get("function") if raw.get("type") == "function" else None
    if isinstance(nested_function, Mapping):
        nested = cast("Mapping[str, Any]", nested_function)
        name = nested.get("name")
        if not isinstance(name, str) or not name:
            logger.warning("Can't parse tool to OpenTelemetry tool definition: missing 'name'.")
            return None
        definition: dict[str, Any] = {"type": "function", "name": name}
        description = nested.get("description")
        if description:
            definition["description"] = description
        parameters = nested.get("parameters")
        if parameters:
            definition["parameters"] = parameters
        # Forward extra properties from both layers, preferring the inner spec.
        for source in (nested, raw):
            for key, value in source.items():
                if key in {"type", "function", "name", "description", "parameters"}:
                    continue
                definition.setdefault(key, value)
        return definition

    type_value = raw.get("type")
    if not isinstance(type_value, str) or not type_value:
        logger.warning("Can't parse tool to OpenTelemetry tool definition: missing 'type'.")
        return None

    name_value = raw.get("name")
    if not isinstance(name_value, str) or not name_value:
        # Hosted tools sometimes omit ``name`` (e.g. ``{"type": "code_interpreter"}``);
        # fall back to the type so the OTel definition stays valid.
        name_value = type_value

    if type_value == "function":
        definition = {"type": "function", "name": name_value}
        description = raw.get("description")
        if description:
            definition["description"] = description
        parameters = raw.get("parameters")
        if parameters:
            definition["parameters"] = parameters
        for key, value in raw.items():
            if key in {"type", "name", "description", "parameters"}:
                continue
            definition.setdefault(key, value)
        return definition

    definition = {"type": type_value, "name": name_value}
    for key, value in raw.items():
        if key in {"type", "name"}:
            continue
        definition[key] = value
    return definition


# endregion


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
    "system_name": (OtelAttr.SYSTEM, None, False, None),
    "provider_name": (OtelAttr.PROVIDER_NAME, None, False, None),
    "service_url": (OtelAttr.ADDRESS, None, False, None),
    "conversation_id": (OtelAttr.CONVERSATION_ID, None, True, None),
    "seed": (OtelAttr.SEED, None, True, None),
    "frequency_penalty": (OtelAttr.FREQUENCY_PENALTY, None, True, None),
    "max_tokens": (OtelAttr.REQUEST_MAX_TOKENS, None, True, None),
    "stop": (OtelAttr.STOP_SEQUENCES, None, True, None),
    "temperature": (OtelAttr.REQUEST_TEMPERATURE, None, True, None),
    "top_p": (OtelAttr.REQUEST_TOP_P, None, True, None),
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
    "model": (OtelAttr.REQUEST_MODEL, None, True, None),
    # Tools with validation - returns None if no valid tools
    "tools": (
        OtelAttr.TOOL_DEFINITIONS,
        lambda tools: json.dumps(tools_dict, ensure_ascii=False) if (tools_dict := _tools_to_dict(tools)) else None,
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
    options_mapping = cast(Mapping[str, Any], options) if isinstance(options, Mapping) else None

    for source_keys, (otel_key, transform_func, check_options, default_value) in OTEL_ATTR_MAP.items():
        # Normalize to tuple of keys
        keys = (source_keys,) if isinstance(source_keys, str) else source_keys

        value = None
        for key in keys:
            if check_options and options_mapping is not None:
                value = options_mapping.get(key)
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


def _capture_system_instructions(span: trace.Span, system_instructions: str | list[str] | None) -> None:
    """Capture system instructions on a span."""
    if not system_instructions:
        return
    otel_sys_instructions = [
        {"type": "text", "content": instruction} for instruction in _normalize_instructions(system_instructions)
    ]
    span.set_attribute(OtelAttr.SYSTEM_INSTRUCTIONS, json.dumps(otel_sys_instructions, ensure_ascii=False))


def _capture_current_agent_system_instructions(
    agent_span: trace.Span,
    chat_span: trace.Span,
    system_instructions: str | list[str] | None,
) -> None:
    """Capture final chat instructions on the current agent span when the chat span belongs to it."""
    if not system_instructions or not agent_span.is_recording():
        return

    agent_attributes_obj = getattr(agent_span, "attributes", None)
    if not isinstance(agent_attributes_obj, Mapping):
        return
    agent_attributes = cast(Mapping[str, Any], agent_attributes_obj)
    if agent_attributes.get(OtelAttr.OPERATION.value) != OtelAttr.AGENT_INVOKE_OPERATION:
        return

    if not _instructions_preserve_existing_agent_instructions(agent_attributes, system_instructions):
        return

    chat_parent = getattr(chat_span, "parent", None)
    agent_context = agent_span.get_span_context()
    if (
        chat_parent is None
        or chat_parent.span_id != agent_context.span_id
        or chat_parent.trace_id != agent_context.trace_id
    ):
        return

    _capture_system_instructions(agent_span, system_instructions)


def _normalize_instructions(system_instructions: str | list[str]) -> list[str]:
    """Normalize system instructions to telemetry text items."""
    return system_instructions if isinstance(system_instructions, list) else [system_instructions]


def _instructions_preserve_existing_agent_instructions(
    agent_attributes: Mapping[str, Any],
    system_instructions: str | list[str],
) -> bool:
    """Return True when chat instructions preserve the agent span's existing instructions."""
    existing = agent_attributes.get(OtelAttr.SYSTEM_INSTRUCTIONS)
    if not isinstance(existing, str):
        return True

    try:
        existing_items_obj = json.loads(existing)
    except json.JSONDecodeError:
        return False

    if not isinstance(existing_items_obj, list):
        return False
    existing_items = cast(list[object], existing_items_obj)

    existing_contents: list[str] = []
    for item in existing_items:
        if not isinstance(item, Mapping):
            continue
        content = cast(Mapping[str, Any], item).get("content")
        if isinstance(content, str):
            existing_contents.append(content)

    existing_text = "\n".join(existing_contents)
    new_text = "\n".join(_normalize_instructions(system_instructions))
    return new_text == existing_text or new_text.startswith(f"{existing_text}\n")


def _capture_messages(
    span: trace.Span,
    provider_name: str,
    messages: AgentRunInputs,
    system_instructions: str | list[str] | None = None,
    output: bool = False,
    finish_reason: FinishReason | None = None,
) -> None:
    """Log messages with extra information."""
    from ._types import normalize_messages

    normalized_messages = normalize_messages(messages)
    otel_messages: list[dict[str, Any]] = []
    for index, message in enumerate(normalized_messages):
        # Reuse the otel message representation for logging instead of calling to_dict()
        # to avoid expensive Pydantic serialization overhead
        otel_message = _to_otel_message(message)
        logger.info(
            otel_message,
            extra={
                OtelAttr.EVENT_NAME: OtelAttr.CHOICE if output else ROLE_EVENT_MAP.get(message.role),
                OtelAttr.PROVIDER_NAME: provider_name,
                MessageListTimestampFilter.INDEX_KEY: index,
            },
        )
        otel_messages.append(otel_message)
    if finish_reason:
        otel_messages[-1]["finish_reason"] = FINISH_REASON_MAP[finish_reason]
    span.set_attribute(
        OtelAttr.OUTPUT_MESSAGES if output else OtelAttr.INPUT_MESSAGES, json.dumps(otel_messages, ensure_ascii=False)
    )
    _capture_system_instructions(span, system_instructions)


def _to_otel_message(message: Message) -> dict[str, Any]:
    """Create a otel representation of a message."""
    return {"role": message.role, "parts": [_to_otel_part(content) for content in message.contents]}


def _to_otel_part(content: Content) -> dict[str, Any] | None:
    """Create a otel representation of a Content."""
    from ._types import _get_data_bytes_as_str  # pyright: ignore[reportPrivateUsage]

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
            return {
                "type": "tool_call_response",
                "id": content.call_id,
                "response": content.result if content.result is not None else "",
            }
        case _:
            # GenericPart in otel output messages json spec.
            # just required type, and arbitrary other fields.
            return content.to_dict(exclude_none=True)
    return None


def _mark_inner_response_telemetry_captured(response: ChatResponse | AgentResponse) -> None:
    """Record when an inner chat telemetry span already captured response metadata."""
    captured_fields = INNER_RESPONSE_TELEMETRY_CAPTURED_FIELDS.get()
    if captured_fields is None:
        return
    if response.response_id:
        captured_fields.add(INNER_RESPONSE_ID_CAPTURED_FIELD)
    if response.usage_details:
        captured_fields.add(INNER_USAGE_CAPTURED_FIELD)
        accumulated = INNER_ACCUMULATED_USAGE.get()
        if accumulated is not None:
            from ._types import add_usage_details

            INNER_ACCUMULATED_USAGE.set(add_usage_details(accumulated, response.usage_details))


def _apply_accumulated_usage(attributes: dict[str, Any], captured_fields: set[str]) -> None:
    """Apply accumulated usage from inner chat spans to the invoke_agent span attributes."""
    if INNER_USAGE_CAPTURED_FIELD not in captured_fields:
        return
    accumulated = INNER_ACCUMULATED_USAGE.get()
    if not accumulated:
        return
    _apply_usage_attributes(attributes, accumulated)


def _apply_usage_attributes(attributes: dict[str, Any], usage: Mapping[str, Any]) -> None:
    """Apply known usage details as standard OTel GenAI attributes."""
    for usage_key, otel_attr in USAGE_DETAIL_TO_OTEL_ATTR:
        value = usage.get(usage_key)
        if value is None or isinstance(value, bool) or not isinstance(value, int):
            continue
        attributes.setdefault(otel_attr, value)


def _get_response_attributes(
    attributes: dict[str, Any],
    response: ChatResponse | AgentResponse,
    *,
    capture_response_id: bool = True,
    capture_usage: bool = True,
) -> dict[str, Any]:
    """Get the response attributes from a response."""
    if capture_response_id and response.response_id:
        attributes[OtelAttr.RESPONSE_ID] = response.response_id
    finish_reason = getattr(response, "finish_reason", None)
    if not finish_reason:
        finish_reason = (
            getattr(response.raw_representation, "finish_reason", None) if response.raw_representation else None
        )
    if isinstance(finish_reason, str) and finish_reason:
        attributes[OtelAttr.FINISH_REASONS] = json.dumps([finish_reason])
    if model := getattr(response, "model", None):
        attributes[OtelAttr.RESPONSE_MODEL] = model
    if capture_usage and (usage := response.usage_details):
        _apply_usage_attributes(attributes, usage)
    return attributes


GEN_AI_METRIC_ATTRIBUTES = (
    OtelAttr.OPERATION,
    OtelAttr.PROVIDER_NAME,
    OtelAttr.REQUEST_MODEL,
    OtelAttr.RESPONSE_MODEL,
    OtelAttr.ADDRESS,
    OtelAttr.PORT,
)


def _capture_response(
    span: trace.Span,
    attributes: dict[str, Any],
    operation_duration_histogram: metrics.Histogram | None = None,
    token_usage_histogram: metrics.Histogram | None = None,
    duration: float | None = None,
) -> None:
    """Set the response for a given span."""
    span.set_attributes(attributes)
    attrs: dict[str, Any] = {k: v for k, v in attributes.items() if k in GEN_AI_METRIC_ATTRIBUTES}
    if token_usage_histogram and (input_tokens := attributes.get(OtelAttr.INPUT_TOKENS)) is not None:
        token_usage_histogram.record(input_tokens, attributes={**attrs, OtelAttr.T_TYPE: OtelAttr.T_TYPE_INPUT})
    if token_usage_histogram and (output_tokens := attributes.get(OtelAttr.OUTPUT_TOKENS)) is not None:
        token_usage_histogram.record(output_tokens, {**attrs, OtelAttr.T_TYPE: OtelAttr.T_TYPE_OUTPUT})
    if operation_duration_histogram and duration is not None:
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


def workflow_tracer() -> Tracer:
    """Get a workflow tracer or a no-op tracer if not enabled."""
    global OBSERVABILITY_SETTINGS
    return get_tracer() if OBSERVABILITY_SETTINGS.ENABLED else trace.NoOpTracer()


def create_workflow_span(
    name: str,
    attributes: Mapping[str, str | int] | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
) -> _AgnosticContextManager[trace.Span]:
    """Create a generic workflow span."""
    return workflow_tracer().start_as_current_span(name, kind=kind, attributes=attributes)


def create_processing_span(
    executor_id: str,
    executor_type: str,
    message_type: str,
    payload_type: str,
    source_trace_contexts: list[dict[str, str]] | None = None,
    source_span_ids: list[str] | None = None,
) -> _AgnosticContextManager[trace.Span]:
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
) -> _AgnosticContextManager[trace.Span]:
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
