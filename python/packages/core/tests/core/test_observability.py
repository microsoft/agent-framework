# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import MutableSequence
from typing import Any
from unittest.mock import Mock

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.semconv_ai import SpanAttributes
from opentelemetry.trace import StatusCode

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    AgentProtocol,
    AgentRunResponse,
    AgentThread,
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Role,
    UsageDetails,
    ai_function,
    prepend_agent_framework_to_user_agent,
)
from agent_framework.exceptions import AgentInitializationError, ChatClientInitializationError
from agent_framework.observability import (
    OPEN_TELEMETRY_AGENT_MARKER,
    OPEN_TELEMETRY_CHAT_CLIENT_MARKER,
    ROLE_EVENT_MAP,
    ChatMessageListTimestampFilter,
    OtelAttr,
    get_function_span,
    use_agent_instrumentation,
    use_instrumentation,
)

# region Test constants


def test_role_event_map():
    """Test that ROLE_EVENT_MAP contains expected mappings."""
    assert ROLE_EVENT_MAP["system"] == OtelAttr.SYSTEM_MESSAGE
    assert ROLE_EVENT_MAP["user"] == OtelAttr.USER_MESSAGE
    assert ROLE_EVENT_MAP["assistant"] == OtelAttr.ASSISTANT_MESSAGE
    assert ROLE_EVENT_MAP["tool"] == OtelAttr.TOOL_MESSAGE


def test_enum_values():
    """Test that OtelAttr enum has expected values."""
    assert OtelAttr.OPERATION == "gen_ai.operation.name"
    assert SpanAttributes.LLM_SYSTEM == "gen_ai.system"
    assert SpanAttributes.LLM_REQUEST_MODEL == "gen_ai.request.model"
    assert OtelAttr.CHAT_COMPLETION_OPERATION == "chat"
    assert OtelAttr.TOOL_EXECUTION_OPERATION == "execute_tool"
    assert OtelAttr.AGENT_INVOKE_OPERATION == "invoke_agent"


# region Test ChatMessageListTimestampFilter


def test_filter_without_index_key():
    """Test filter method when record doesn't have INDEX_KEY."""
    log_filter = ChatMessageListTimestampFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg="test message", args=(), exc_info=None
    )
    original_created = record.created

    result = log_filter.filter(record)

    assert result is True
    assert record.created == original_created


def test_filter_with_index_key():
    """Test filter method when record has INDEX_KEY."""
    log_filter = ChatMessageListTimestampFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg="test message", args=(), exc_info=None
    )
    original_created = record.created

    # Add the index key
    setattr(record, ChatMessageListTimestampFilter.INDEX_KEY, 5)

    result = log_filter.filter(record)

    assert result is True
    # Should increment by 5 microseconds (5 * 1e-6)
    assert record.created == original_created + 5 * 1e-6


def test_index_key_constant():
    """Test that INDEX_KEY constant is correctly defined."""
    assert ChatMessageListTimestampFilter.INDEX_KEY == "chat_message_index"


# region Test get_function_span


def test_start_span_basic(span_exporter: InMemorySpanExporter):
    """Test starting a span with basic function info."""
    # Create a mock function
    mock_function = Mock()
    mock_function.name = "test_function"
    mock_function.description = "Test function description"
    attributes = {
        OtelAttr.OPERATION: OtelAttr.TOOL_EXECUTION_OPERATION,
        OtelAttr.TOOL_NAME: "test_function",
        OtelAttr.TOOL_DESCRIPTION: "Test function description",
        OtelAttr.TOOL_TYPE: "function",
    }
    span_exporter.clear()
    with get_function_span(attributes) as function_span:
        assert function_span is not None
        function_span.set_attribute("test_attr", "test_value")

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "execute_tool test_function"
    assert span.attributes["test_attr"] == "test_value"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.TOOL_EXECUTION_OPERATION
    assert span.attributes[OtelAttr.TOOL_NAME] == "test_function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "Test function description"


def test_start_span_with_tool_call_id(span_exporter: InMemorySpanExporter):
    """Test starting a span with tool_call_id."""

    tool_call_id = "test_call_123"
    attributes = {
        OtelAttr.OPERATION: OtelAttr.TOOL_EXECUTION_OPERATION,
        OtelAttr.TOOL_NAME: "test_function",
        OtelAttr.TOOL_DESCRIPTION: "Test function",
        OtelAttr.TOOL_TYPE: "function",
        OtelAttr.TOOL_CALL_ID: tool_call_id,
    }

    span_exporter.clear()
    with get_function_span(attributes) as function_span:
        assert function_span is not None
        function_span.set_attribute("test_attr", "test_value")
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "execute_tool test_function"
    assert span.attributes["test_attr"] == "test_value"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == tool_call_id
    # Verify all attributes
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.TOOL_EXECUTION_OPERATION
    assert span.attributes[OtelAttr.TOOL_NAME] == "test_function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "Test function"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"


# region Test use_instrumentation decorator


def test_decorator_with_valid_class():
    """Test that decorator works with a valid BaseChatClient-like class."""

    # Create a mock class with the required methods
    class MockChatClient:
        async def get_response(self, messages, **kwargs):
            return Mock()

        async def get_streaming_response(self, messages, **kwargs):
            async def gen():
                yield Mock()

            return gen()

    # Apply the decorator
    decorated_class = use_instrumentation(MockChatClient)
    assert hasattr(decorated_class, OPEN_TELEMETRY_CHAT_CLIENT_MARKER)


def test_decorator_with_missing_methods():
    """Test that decorator handles classes missing required methods gracefully."""

    class MockChatClient:
        OTEL_PROVIDER_NAME = "test_provider"

    # Apply the decorator - should not raise an error
    with pytest.raises(ChatClientInitializationError):
        use_instrumentation(MockChatClient)


def test_decorator_with_partial_methods():
    """Test decorator when only one method is present."""

    class MockChatClient:
        OTEL_PROVIDER_NAME = "test_provider"

        async def get_response(self, messages, **kwargs):
            return Mock()

    with pytest.raises(ChatClientInitializationError):
        use_instrumentation(MockChatClient)


# region Test telemetry decorator with mock client


@pytest.fixture
def mock_chat_client():
    """Create a mock chat client for testing."""

    class MockChatClient(BaseChatClient):
        def service_url(self):
            return "https://test.example.com"

        async def _inner_get_response(
            self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
        ):
            return ChatResponse(
                messages=[ChatMessage(role=Role.ASSISTANT, text="Test response")],
                usage_details=UsageDetails(input_token_count=10, output_token_count=20),
                finish_reason=None,
            )

        async def _inner_get_streaming_response(
            self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
        ):
            yield ChatResponseUpdate(text="Hello", role=Role.ASSISTANT)
            yield ChatResponseUpdate(text=" world", role=Role.ASSISTANT)

    return MockChatClient


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_chat_client_observability(mock_chat_client, span_exporter: InMemorySpanExporter, enable_sensitive_data):
    """Test that when diagnostics are enabled, telemetry is applied."""
    client = use_instrumentation(mock_chat_client)()

    messages = [ChatMessage(role=Role.USER, text="Test message")]
    span_exporter.clear()
    response = await client.get_response(messages=messages, model_id="Test")
    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "chat Test"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.CHAT_COMPLETION_OPERATION
    assert span.attributes[SpanAttributes.LLM_REQUEST_MODEL] == "Test"
    assert span.attributes[OtelAttr.INPUT_TOKENS] == 10
    assert span.attributes[OtelAttr.OUTPUT_TOKENS] == 20
    if enable_sensitive_data:
        assert span.attributes[OtelAttr.INPUT_MESSAGES] is not None
        assert span.attributes[OtelAttr.OUTPUT_MESSAGES] is not None


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_chat_client_streaming_observability(
    mock_chat_client, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test streaming telemetry through the use_instrumentation decorator."""
    client = use_instrumentation(mock_chat_client)()
    messages = [ChatMessage(role=Role.USER, text="Test")]
    span_exporter.clear()
    # Collect all yielded updates
    updates = []
    async for update in client.get_streaming_response(messages=messages, model_id="Test"):
        updates.append(update)

    # Verify we got the expected updates, this shouldn't be dependent on otel
    assert len(updates) == 2
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "chat Test"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.CHAT_COMPLETION_OPERATION
    assert span.attributes[SpanAttributes.LLM_REQUEST_MODEL] == "Test"
    if enable_sensitive_data:
        assert span.attributes[OtelAttr.INPUT_MESSAGES] is not None
        assert span.attributes[OtelAttr.OUTPUT_MESSAGES] is not None


async def test_chat_client_without_model_id_observability(mock_chat_client, span_exporter: InMemorySpanExporter):
    """Test telemetry shouldn't fail when the model_id is not provided for unknown reason."""
    client = use_instrumentation(mock_chat_client)()
    messages = [ChatMessage(role=Role.USER, text="Test")]
    span_exporter.clear()
    response = await client.get_response(messages=messages)

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == "chat unknown"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.CHAT_COMPLETION_OPERATION
    assert span.attributes[SpanAttributes.LLM_REQUEST_MODEL] == "unknown"


async def test_chat_client_streaming_without_model_id_observability(
    mock_chat_client, span_exporter: InMemorySpanExporter
):
    """Test streaming telemetry shouldn't fail when the model_id is not provided for unknown reason."""
    client = use_instrumentation(mock_chat_client)()
    messages = [ChatMessage(role=Role.USER, text="Test")]
    span_exporter.clear()
    # Collect all yielded updates
    updates = []
    async for update in client.get_streaming_response(messages=messages):
        updates.append(update)

    # Verify we got the expected updates, this shouldn't be dependent on otel
    assert len(updates) == 2
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "chat unknown"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.CHAT_COMPLETION_OPERATION
    assert span.attributes[SpanAttributes.LLM_REQUEST_MODEL] == "unknown"


def test_prepend_user_agent_with_none_value():
    """Test prepend user agent with None value in headers."""
    headers = {"User-Agent": None}
    result = prepend_agent_framework_to_user_agent(headers)

    # Should handle None gracefully
    assert "User-Agent" in result
    assert AGENT_FRAMEWORK_USER_AGENT in str(result["User-Agent"])


# region Test use_agent_instrumentation decorator


def test_agent_decorator_with_valid_class():
    """Test that agent decorator works with a valid ChatAgent-like class."""

    # Create a mock class with the required methods
    class MockChatClientAgent:
        AGENT_PROVIDER_NAME = "test_agent_system"

        def __init__(self):
            self.id = "test_agent_id"
            self.name = "test_agent"
            self.display_name = "Test Agent"
            self.description = "Test agent description"

        async def run(self, messages=None, *, thread=None, **kwargs):
            return Mock()

        async def run_stream(self, messages=None, *, thread=None, **kwargs):
            async def gen():
                yield Mock()

            return gen()

        def get_new_thread(self) -> AgentThread:
            return AgentThread()

    # Apply the decorator
    decorated_class = use_agent_instrumentation(MockChatClientAgent)

    assert hasattr(decorated_class, OPEN_TELEMETRY_AGENT_MARKER)


def test_agent_decorator_with_missing_methods():
    """Test that agent decorator handles classes missing required methods gracefully."""

    class MockAgent:
        AGENT_PROVIDER_NAME = "test_agent_system"

    # Apply the decorator - should not raise an error
    with pytest.raises(AgentInitializationError):
        use_agent_instrumentation(MockAgent)


def test_agent_decorator_with_partial_methods():
    """Test agent decorator when only one method is present."""
    from agent_framework.observability import use_agent_instrumentation

    class MockAgent:
        AGENT_PROVIDER_NAME = "test_agent_system"

        def __init__(self):
            self.id = "test_agent_id"
            self.name = "test_agent"
            self.display_name = "Test Agent"

        async def run(self, messages=None, *, thread=None, **kwargs):
            return Mock()

    with pytest.raises(AgentInitializationError):
        use_agent_instrumentation(MockAgent)


# region Test agent telemetry decorator with mock agent


@pytest.fixture
def mock_chat_agent():
    """Create a mock chat client agent for testing."""

    class MockChatClientAgent:
        AGENT_PROVIDER_NAME = "test_agent_system"

        def __init__(self):
            self.id = "test_agent_id"
            self.name = "test_agent"
            self.display_name = "Test Agent"
            self.description = "Test agent description"
            self.chat_options = ChatOptions(model_id="TestModel")

        async def run(self, messages=None, *, thread=None, **kwargs):
            return AgentRunResponse(
                messages=[ChatMessage(role=Role.ASSISTANT, text="Agent response")],
                usage_details=UsageDetails(input_token_count=15, output_token_count=25),
                response_id="test_response_id",
                raw_representation=Mock(finish_reason=Mock(value="stop")),
            )

        async def run_stream(self, messages=None, *, thread=None, **kwargs):
            from agent_framework import AgentRunResponseUpdate

            yield AgentRunResponseUpdate(text="Hello", role=Role.ASSISTANT)
            yield AgentRunResponseUpdate(text=" from agent", role=Role.ASSISTANT)

    return MockChatClientAgent


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_agent_instrumentation_enabled(
    mock_chat_agent: AgentProtocol, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that when agent diagnostics are enabled, telemetry is applied."""

    agent = use_agent_instrumentation(mock_chat_agent)()

    span_exporter.clear()
    response = await agent.run("Test message")
    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "invoke_agent Test Agent"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.AGENT_INVOKE_OPERATION
    assert span.attributes[OtelAttr.AGENT_ID] == "test_agent_id"
    assert span.attributes[OtelAttr.AGENT_NAME] == "Test Agent"
    assert span.attributes[OtelAttr.AGENT_DESCRIPTION] == "Test agent description"
    assert span.attributes[SpanAttributes.LLM_REQUEST_MODEL] == "TestModel"
    assert span.attributes[OtelAttr.INPUT_TOKENS] == 15
    assert span.attributes[OtelAttr.OUTPUT_TOKENS] == 25
    if enable_sensitive_data:
        assert span.attributes[OtelAttr.OUTPUT_MESSAGES] is not None


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_agent_streaming_response_with_diagnostics_enabled_via_decorator(
    mock_chat_agent: AgentProtocol, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test agent streaming telemetry through the use_agent_instrumentation decorator."""
    agent = use_agent_instrumentation(mock_chat_agent)()
    span_exporter.clear()
    updates = []
    async for update in agent.run_stream("Test message"):
        updates.append(update)

    # Verify we got the expected updates
    assert len(updates) == 2
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "invoke_agent Test Agent"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.AGENT_INVOKE_OPERATION
    assert span.attributes[OtelAttr.AGENT_ID] == "test_agent_id"
    assert span.attributes[OtelAttr.AGENT_NAME] == "Test Agent"
    assert span.attributes[OtelAttr.AGENT_DESCRIPTION] == "Test agent description"
    assert span.attributes[SpanAttributes.LLM_REQUEST_MODEL] == "TestModel"
    if enable_sensitive_data:
        assert span.attributes.get(OtelAttr.OUTPUT_MESSAGES) is not None  # Streaming, so no usage yet


async def test_function_call_with_error_handling(span_exporter: InMemorySpanExporter):
    """Test that function call errors are properly captured in telemetry."""

    # Create a function that raises an error using the decorator
    @ai_function(name="failing_function", description="A function that fails")
    async def failing_function(param: str) -> str:
        raise ValueError("Function execution failed")

    span_exporter.clear()

    # Execute function and expect it to raise an error
    with pytest.raises(ValueError, match="Function execution failed"):
        await failing_function.invoke(param="test_value", tool_call_id="test_call_456")

    # Verify span was created and error was captured
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Verify span name and basic attributes
    assert span.name == "execute_tool failing_function"
    assert span.attributes is not None
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.TOOL_EXECUTION_OPERATION
    assert span.attributes[OtelAttr.TOOL_NAME] == "failing_function"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "test_call_456"

    # Verify error status was set
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description is not None
    assert "Function execution failed" in span.status.description

    # Verify error type attribute was set
    assert span.attributes[OtelAttr.ERROR_TYPE] == "ValueError"

    # Verify exception event was recorded
    assert len(span.events) > 0
    exception_event = next((e for e in span.events if e.name == "exception"), None)
    assert exception_event is not None
    assert exception_event.attributes is not None
    assert exception_event.attributes["exception.type"] == "ValueError"
    exception_message = exception_event.attributes["exception.message"]
    assert isinstance(exception_message, str)
    assert "Function execution failed" in exception_message


# region Test OTEL environment variable parsing


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_get_exporters_from_env_with_grpc_endpoint(monkeypatch):
    """Test _get_exporters_from_env with OTEL_EXPORTER_OTLP_ENDPOINT (gRPC)."""
    from agent_framework.observability import _get_exporters_from_env

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")

    exporters = _get_exporters_from_env()

    # Should return 3 exporters (trace, metrics, logs)
    assert len(exporters) == 3


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_get_exporters_from_env_with_http_endpoint(monkeypatch):
    """Test _get_exporters_from_env with OTEL_EXPORTER_OTLP_ENDPOINT (HTTP)."""
    from agent_framework.observability import _get_exporters_from_env

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http")

    exporters = _get_exporters_from_env()

    # Should return 3 exporters (trace, metrics, logs)
    assert len(exporters) == 3


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_get_exporters_from_env_with_individual_endpoints(monkeypatch):
    """Test _get_exporters_from_env with individual signal endpoints."""
    from agent_framework.observability import _get_exporters_from_env

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4317")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://localhost:4319")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")

    exporters = _get_exporters_from_env()

    # Should return 3 exporters (trace, metrics, logs)
    assert len(exporters) == 3


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_get_exporters_from_env_with_headers(monkeypatch):
    """Test _get_exporters_from_env with OTEL_EXPORTER_OTLP_HEADERS."""
    from agent_framework.observability import _get_exporters_from_env

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "key1=value1,key2=value2")

    exporters = _get_exporters_from_env()

    # Should return 3 exporters with headers
    assert len(exporters) == 3


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_get_exporters_from_env_with_signal_specific_headers(monkeypatch):
    """Test _get_exporters_from_env with signal-specific headers."""
    from agent_framework.observability import _get_exporters_from_env

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4317")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS", "trace-key=trace-value")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")

    exporters = _get_exporters_from_env()

    # Should have at least the traces exporter
    assert len(exporters) >= 1


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_get_exporters_from_env_without_env_vars(monkeypatch):
    """Test _get_exporters_from_env returns empty list when no env vars set."""
    from agent_framework.observability import _get_exporters_from_env

    # Clear all OTEL env vars
    for key in [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    ]:
        monkeypatch.delenv(key, raising=False)

    exporters = _get_exporters_from_env()

    # Should return empty list
    assert len(exporters) == 0


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_get_exporters_from_env_missing_grpc_dependency(monkeypatch):
    """Test _get_exporters_from_env raises ImportError when gRPC exporters not installed."""

    from agent_framework.observability import _get_exporters_from_env

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")

    # Mock the import to raise ImportError
    original_import = __builtins__.__import__

    def mock_import(name, *args, **kwargs):
        if "opentelemetry.exporter.otlp.proto.grpc" in name:
            raise ImportError("No module named 'opentelemetry.exporter.otlp.proto.grpc'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(__builtins__, "__import__", mock_import)

    with pytest.raises(ImportError, match="opentelemetry-exporter-otlp-proto-grpc"):
        _get_exporters_from_env()


# region Test create_resource


def test_create_resource_from_env(monkeypatch):
    """Test create_resource reads OTEL environment variables."""
    from agent_framework.observability import create_resource

    monkeypatch.setenv("OTEL_SERVICE_NAME", "test-service")
    monkeypatch.setenv("OTEL_SERVICE_VERSION", "1.0.0")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.environment=production,host.name=server1")

    resource = create_resource()

    assert resource.attributes["service.name"] == "test-service"
    assert resource.attributes["service.version"] == "1.0.0"
    assert resource.attributes["deployment.environment"] == "production"
    assert resource.attributes["host.name"] == "server1"


def test_create_resource_with_parameters_override_env(monkeypatch):
    """Test create_resource parameters override environment variables."""
    from agent_framework.observability import create_resource

    monkeypatch.setenv("OTEL_SERVICE_NAME", "env-service")
    monkeypatch.setenv("OTEL_SERVICE_VERSION", "0.1.0")

    resource = create_resource(service_name="param-service", service_version="2.0.0")

    # Parameters should override env vars
    assert resource.attributes["service.name"] == "param-service"
    assert resource.attributes["service.version"] == "2.0.0"


def test_create_resource_with_custom_attributes(monkeypatch):
    """Test create_resource accepts custom attributes."""
    from agent_framework.observability import create_resource

    resource = create_resource(custom_attr="custom_value", another_attr=123)

    assert resource.attributes["custom_attr"] == "custom_value"
    assert resource.attributes["another_attr"] == 123


# region Test _create_otlp_exporters


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_create_otlp_exporters_grpc_with_single_endpoint():
    """Test _create_otlp_exporters creates gRPC exporters with single endpoint."""
    from agent_framework.observability import _create_otlp_exporters

    exporters = _create_otlp_exporters(endpoint="http://localhost:4317", protocol="grpc")

    # Should return 3 exporters (trace, metrics, logs)
    assert len(exporters) == 3


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_create_otlp_exporters_http_with_single_endpoint():
    """Test _create_otlp_exporters creates HTTP exporters with single endpoint."""
    from agent_framework.observability import _create_otlp_exporters

    exporters = _create_otlp_exporters(endpoint="http://localhost:4318", protocol="http")

    # Should return 3 exporters (trace, metrics, logs)
    assert len(exporters) == 3


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_create_otlp_exporters_with_individual_endpoints():
    """Test _create_otlp_exporters with individual signal endpoints."""
    from agent_framework.observability import _create_otlp_exporters

    exporters = _create_otlp_exporters(
        protocol="grpc",
        traces_endpoint="http://localhost:4317",
        metrics_endpoint="http://localhost:4318",
        logs_endpoint="http://localhost:4319",
    )

    # Should return 3 exporters
    assert len(exporters) == 3


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_create_otlp_exporters_with_headers():
    """Test _create_otlp_exporters with headers."""
    from agent_framework.observability import _create_otlp_exporters

    exporters = _create_otlp_exporters(
        endpoint="http://localhost:4317", protocol="grpc", headers={"Authorization": "Bearer token"}
    )

    # Should return 3 exporters with headers
    assert len(exporters) == 3


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_create_otlp_exporters_grpc_missing_dependency():
    """Test _create_otlp_exporters raises ImportError when gRPC exporters not installed."""
    import sys
    from unittest.mock import patch

    from agent_framework.observability import _create_otlp_exporters

    # Mock the import to raise ImportError
    with (
        patch.dict(sys.modules, {"opentelemetry.exporter.otlp.proto.grpc.trace_exporter": None}),
        pytest.raises(ImportError, match="opentelemetry-exporter-otlp-proto-grpc"),
    ):
        _create_otlp_exporters(endpoint="http://localhost:4317", protocol="grpc")


# region Test configure_otel_providers with views


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_configure_otel_providers_with_views(monkeypatch):
    """Test configure_otel_providers accepts views parameter."""
    from opentelemetry.sdk.metrics import View
    from opentelemetry.sdk.metrics.view import DropAggregation

    from agent_framework.observability import configure_otel_providers

    # Clear all OTEL env vars
    for key in [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    ]:
        monkeypatch.delenv(key, raising=False)

    # Create a view that drops all metrics
    views = [View(instrument_name="*", aggregation=DropAggregation())]

    # Should not raise an error
    configure_otel_providers(views=views)


@pytest.mark.skipif(
    True,
    reason="Skipping OTLP exporter tests - optional dependency not installed by default",
)
def test_configure_otel_providers_without_views(monkeypatch):
    """Test configure_otel_providers works without views parameter."""
    from agent_framework.observability import configure_otel_providers

    # Clear all OTEL env vars
    for key in [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    ]:
        monkeypatch.delenv(key, raising=False)

    # Should not raise an error with default empty views
    configure_otel_providers()


# region Test console exporters opt-in


def test_console_exporters_opt_in_false(monkeypatch):
    """Test console exporters are not added when ENABLE_CONSOLE_EXPORTERS is false."""
    from agent_framework.observability import ObservabilitySettings

    monkeypatch.setenv("ENABLE_CONSOLE_EXPORTERS", "false")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    settings = ObservabilitySettings(env_file_path="test.env")
    assert settings.enable_console_exporters is False


def test_console_exporters_opt_in_true(monkeypatch):
    """Test console exporters are added when ENABLE_CONSOLE_EXPORTERS is true."""
    from agent_framework.observability import ObservabilitySettings

    monkeypatch.setenv("ENABLE_CONSOLE_EXPORTERS", "true")

    settings = ObservabilitySettings(env_file_path="test.env")
    assert settings.enable_console_exporters is True


def test_console_exporters_default_false(monkeypatch):
    """Test console exporters default to False when not set."""
    from agent_framework.observability import ObservabilitySettings

    monkeypatch.delenv("ENABLE_CONSOLE_EXPORTERS", raising=False)

    settings = ObservabilitySettings(env_file_path="test.env")
    assert settings.enable_console_exporters is False


# region Test _parse_headers helper


def test_parse_headers_valid():
    """Test _parse_headers with valid header string."""
    from agent_framework.observability import _parse_headers

    headers = _parse_headers("key1=value1,key2=value2")
    assert headers == {"key1": "value1", "key2": "value2"}


def test_parse_headers_with_spaces():
    """Test _parse_headers handles spaces around keys and values."""
    from agent_framework.observability import _parse_headers

    headers = _parse_headers("key1 = value1 , key2 = value2 ")
    assert headers == {"key1": "value1", "key2": "value2"}


def test_parse_headers_empty_string():
    """Test _parse_headers with empty string."""
    from agent_framework.observability import _parse_headers

    headers = _parse_headers("")
    assert headers == {}


def test_parse_headers_invalid_format():
    """Test _parse_headers ignores invalid pairs."""
    from agent_framework.observability import _parse_headers

    headers = _parse_headers("key1=value1,invalid,key2=value2")
    # Should only include valid pairs
    assert headers == {"key1": "value1", "key2": "value2"}
