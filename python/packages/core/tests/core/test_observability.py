# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import AsyncIterable, Awaitable, MutableSequence, Sequence
from typing import Any
from unittest.mock import Mock

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    AgentResponse,
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ResponseStream,
    SupportsAgentRun,
    UsageDetails,
    prepend_agent_framework_to_user_agent,
    tool,
)
from agent_framework.observability import (
    ROLE_EVENT_MAP,
    AgentTelemetryLayer,
    ChatTelemetryLayer,
    MessageListTimestampFilter,
    OtelAttr,
    _capture_messages,
    get_function_span,
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
    assert OtelAttr.SYSTEM == "gen_ai.system"
    assert OtelAttr.REQUEST_MODEL == "gen_ai.request.model"
    assert OtelAttr.CHAT_COMPLETION_OPERATION == "chat"
    assert OtelAttr.TOOL_EXECUTION_OPERATION == "execute_tool"
    assert OtelAttr.AGENT_INVOKE_OPERATION == "invoke_agent"


# region Test MessageListTimestampFilter


def test_filter_without_index_key():
    """Test filter method when record doesn't have INDEX_KEY."""
    log_filter = MessageListTimestampFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg="test message", args=(), exc_info=None
    )
    original_created = record.created

    result = log_filter.filter(record)

    assert result is True
    assert record.created == original_created


def test_filter_with_index_key():
    """Test filter method when record has INDEX_KEY."""
    log_filter = MessageListTimestampFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg="test message", args=(), exc_info=None
    )
    original_created = record.created

    # Add the index key
    setattr(record, MessageListTimestampFilter.INDEX_KEY, 5)

    result = log_filter.filter(record)

    assert result is True
    # Should increment by 5 microseconds (5 * 1e-6)
    assert record.created == original_created + 5 * 1e-6


def test_index_key_constant():
    """Test that INDEX_KEY constant is correctly defined."""
    assert MessageListTimestampFilter.INDEX_KEY == "chat_message_index"


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


@pytest.fixture
def mock_chat_client():
    """Create a mock chat client for testing."""

    class MockChatClient(ChatTelemetryLayer, BaseChatClient[Any]):
        def service_url(self):
            return "https://test.example.com"

        def _inner_get_response(
            self, *, messages: MutableSequence[Message], stream: bool, options: dict[str, Any], **kwargs: Any
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            if stream:
                return self._get_streaming_response(messages=messages, options=options, **kwargs)

            async def _get() -> ChatResponse:
                return await self._get_non_streaming_response(messages=messages, options=options, **kwargs)

            return _get()

        async def _get_non_streaming_response(
            self, *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
        ) -> ChatResponse:
            return ChatResponse(
                messages=[Message("assistant", ["Test response"])],
                usage_details=UsageDetails(input_token_count=10, output_token_count=20),
                finish_reason=None,
            )

        def _get_streaming_response(
            self, *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
        ) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
            async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                yield ChatResponseUpdate(contents=[Content.from_text("Hello")], role="assistant")
                yield ChatResponseUpdate(contents=[Content.from_text(" world")], role="assistant", finish_reason="stop")

            def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
                response_format = options.get("response_format")
                output_format_type = response_format if isinstance(response_format, type) else None
                return ChatResponse.from_updates(updates, output_format_type=output_format_type)

            return ResponseStream(_stream(), finalizer=_finalize)

    return MockChatClient


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_chat_client_observability(mock_chat_client, span_exporter: InMemorySpanExporter, enable_sensitive_data):
    """Test that when diagnostics are enabled, telemetry is applied."""
    client = mock_chat_client()

    messages = [Message(role="user", text="Test message")]
    span_exporter.clear()
    response = await client.get_response(messages=messages, model_id="Test")
    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "chat Test"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.CHAT_COMPLETION_OPERATION
    assert span.attributes[OtelAttr.REQUEST_MODEL] == "Test"
    assert span.attributes[OtelAttr.INPUT_TOKENS] == 10
    assert span.attributes[OtelAttr.OUTPUT_TOKENS] == 20
    if enable_sensitive_data:
        assert span.attributes[OtelAttr.INPUT_MESSAGES] is not None
        assert span.attributes[OtelAttr.OUTPUT_MESSAGES] is not None


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_chat_client_streaming_observability(
    mock_chat_client, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test streaming telemetry through the chat telemetry mixin."""
    client = mock_chat_client()
    messages = [Message(role="user", text="Test")]
    span_exporter.clear()
    # Collect all yielded updates
    updates = []
    stream = client.get_response(stream=True, messages=messages, model_id="Test")
    async for update in stream:
        updates.append(update)
    await stream.get_final_response()

    # Verify we got the expected updates, this shouldn't be dependent on otel
    assert len(updates) == 2
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "chat Test"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.CHAT_COMPLETION_OPERATION
    assert span.attributes[OtelAttr.REQUEST_MODEL] == "Test"
    if enable_sensitive_data:
        assert span.attributes[OtelAttr.INPUT_MESSAGES] is not None
        assert span.attributes[OtelAttr.OUTPUT_MESSAGES] is not None


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_chat_client_observability_with_instructions(
    mock_chat_client, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that system_instructions from options are captured in LLM span."""
    import json

    client = mock_chat_client()

    messages = [Message(role="user", text="Test message")]
    options = {"model_id": "Test", "instructions": "You are a helpful assistant."}
    span_exporter.clear()
    response = await client.get_response(messages=messages, options=options)

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Verify system_instructions attribute is set
    assert OtelAttr.SYSTEM_INSTRUCTIONS in span.attributes
    system_instructions = json.loads(span.attributes[OtelAttr.SYSTEM_INSTRUCTIONS])
    assert len(system_instructions) == 1
    assert system_instructions[0]["content"] == "You are a helpful assistant."

    # Verify input_messages contains system message
    input_messages = json.loads(span.attributes[OtelAttr.INPUT_MESSAGES])
    assert any(msg.get("role") == "system" for msg in input_messages)


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_chat_client_streaming_observability_with_instructions(
    mock_chat_client, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test streaming telemetry captures system_instructions from options."""
    import json

    client = mock_chat_client()
    messages = [Message(role="user", text="Test")]
    options = {"model_id": "Test", "instructions": "You are a helpful assistant."}
    span_exporter.clear()

    updates = []
    stream = client.get_response(stream=True, messages=messages, options=options)
    async for update in stream:
        updates.append(update)
    await stream.get_final_response()

    assert len(updates) == 2
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Verify system_instructions attribute is set
    assert OtelAttr.SYSTEM_INSTRUCTIONS in span.attributes
    system_instructions = json.loads(span.attributes[OtelAttr.SYSTEM_INSTRUCTIONS])
    assert len(system_instructions) == 1
    assert system_instructions[0]["content"] == "You are a helpful assistant."


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_chat_client_observability_without_instructions(
    mock_chat_client, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that system_instructions attribute is not set when instructions are not provided."""
    client = mock_chat_client()

    messages = [Message(role="user", text="Test message")]
    options = {"model_id": "Test"}  # No instructions
    span_exporter.clear()
    response = await client.get_response(messages=messages, options=options)

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Verify system_instructions attribute is NOT set
    assert OtelAttr.SYSTEM_INSTRUCTIONS not in span.attributes


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_chat_client_observability_with_empty_instructions(
    mock_chat_client, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that system_instructions attribute is not set when instructions is an empty string."""
    client = mock_chat_client()

    messages = [Message(role="user", text="Test message")]
    options = {"model_id": "Test", "instructions": ""}  # Empty string
    span_exporter.clear()
    response = await client.get_response(messages=messages, options=options)

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Empty string should not set system_instructions
    assert OtelAttr.SYSTEM_INSTRUCTIONS not in span.attributes


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_chat_client_observability_with_list_instructions(
    mock_chat_client, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that list-type instructions are correctly captured."""
    import json

    client = mock_chat_client()

    messages = [Message(role="user", text="Test message")]
    options = {"model_id": "Test", "instructions": ["Instruction 1", "Instruction 2"]}
    span_exporter.clear()
    response = await client.get_response(messages=messages, options=options)

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Verify system_instructions attribute contains both instructions
    assert OtelAttr.SYSTEM_INSTRUCTIONS in span.attributes
    system_instructions = json.loads(span.attributes[OtelAttr.SYSTEM_INSTRUCTIONS])
    assert len(system_instructions) == 2
    assert system_instructions[0]["content"] == "Instruction 1"
    assert system_instructions[1]["content"] == "Instruction 2"


async def test_chat_client_without_model_id_observability(mock_chat_client, span_exporter: InMemorySpanExporter):
    """Test telemetry shouldn't fail when the model_id is not provided for unknown reason."""
    client = mock_chat_client()
    messages = [Message(role="user", text="Test")]
    span_exporter.clear()
    response = await client.get_response(messages=messages)

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == "chat unknown"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.CHAT_COMPLETION_OPERATION
    assert span.attributes[OtelAttr.REQUEST_MODEL] == "unknown"


async def test_chat_client_streaming_without_model_id_observability(
    mock_chat_client, span_exporter: InMemorySpanExporter
):
    """Test streaming telemetry shouldn't fail when the model_id is not provided for unknown reason."""
    client = mock_chat_client()
    messages = [Message(role="user", text="Test")]
    span_exporter.clear()
    # Collect all yielded updates
    updates = []
    stream = client.get_response(stream=True, messages=messages)
    async for update in stream:
        updates.append(update)
    await stream.get_final_response()

    # Verify we got the expected updates, this shouldn't be dependent on otel
    assert len(updates) == 2
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "chat unknown"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.CHAT_COMPLETION_OPERATION
    assert span.attributes[OtelAttr.REQUEST_MODEL] == "unknown"


def test_prepend_user_agent_with_none_value():
    """Test prepend user agent with None value in headers."""
    headers = {"User-Agent": None}
    result = prepend_agent_framework_to_user_agent(headers)

    # Should handle None gracefully
    assert "User-Agent" in result
    assert AGENT_FRAMEWORK_USER_AGENT in str(result["User-Agent"])


@pytest.fixture
def mock_chat_agent():
    """Create a mock chat client agent for testing."""

    class _MockChatClientAgent:
        AGENT_PROVIDER_NAME = "test_agent_system"

        def __init__(self):
            self.id = "test_agent_id"
            self.name = "test_agent"
            self.description = "Test agent description"
            self.default_options: dict[str, Any] = {"model_id": "TestModel"}

        def run(self, messages=None, *, session=None, stream=False, **kwargs):
            if stream:
                return self._run_stream_impl(messages=messages, **kwargs)
            return self._run_impl(messages=messages, **kwargs)

        async def _run_impl(self, messages=None, *, session=None, **kwargs):
            return AgentResponse(
                messages=[Message("assistant", ["Agent response"])],
                usage_details=UsageDetails(input_token_count=15, output_token_count=25),
                response_id="test_response_id",
            )

        async def _run_stream_impl(self, messages=None, *, session=None, **kwargs):
            from agent_framework import AgentResponse, AgentResponseUpdate, ResponseStream

            async def _stream():
                yield AgentResponseUpdate(contents=[Content.from_text("Hello")], role="assistant")
                yield AgentResponseUpdate(contents=[Content.from_text(" from agent")], role="assistant")

            return ResponseStream(
                _stream(),
                finalizer=AgentResponse.from_updates,
            )

    class MockChatClientAgent(AgentTelemetryLayer, _MockChatClientAgent):
        pass

    return MockChatClientAgent


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_agent_instrumentation_enabled(
    mock_chat_agent: SupportsAgentRun, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that when agent diagnostics are enabled, telemetry is applied."""

    agent = mock_chat_agent()

    span_exporter.clear()
    response = await agent.run("Test message")
    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "invoke_agent test_agent"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.AGENT_INVOKE_OPERATION
    assert span.attributes[OtelAttr.AGENT_ID] == "test_agent_id"
    assert span.attributes[OtelAttr.AGENT_NAME] == "test_agent"
    assert span.attributes[OtelAttr.AGENT_DESCRIPTION] == "Test agent description"
    assert span.attributes[OtelAttr.REQUEST_MODEL] == "TestModel"
    assert span.attributes[OtelAttr.INPUT_TOKENS] == 15
    assert span.attributes[OtelAttr.OUTPUT_TOKENS] == 25
    if enable_sensitive_data:
        assert span.attributes[OtelAttr.OUTPUT_MESSAGES] is not None


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_agent_streaming_response_with_diagnostics_enabled(
    mock_chat_agent: SupportsAgentRun, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test agent streaming telemetry through the agent telemetry mixin."""
    agent = mock_chat_agent()
    span_exporter.clear()
    updates = []
    stream = agent.run("Test message", stream=True)
    async for update in stream:
        updates.append(update)
    await stream.get_final_response()

    # Verify we got the expected updates
    assert len(updates) == 2
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "invoke_agent test_agent"
    assert span.attributes[OtelAttr.OPERATION.value] == OtelAttr.AGENT_INVOKE_OPERATION
    assert span.attributes[OtelAttr.AGENT_ID] == "test_agent_id"
    assert span.attributes[OtelAttr.AGENT_NAME] == "test_agent"
    assert span.attributes[OtelAttr.AGENT_DESCRIPTION] == "Test agent description"
    assert span.attributes[OtelAttr.REQUEST_MODEL] == "TestModel"
    if enable_sensitive_data:
        assert span.attributes.get(OtelAttr.OUTPUT_MESSAGES) is not None  # Streaming, so no usage yet


async def test_function_call_with_error_handling(span_exporter: InMemorySpanExporter):
    """Test that function call errors are properly captured in telemetry."""

    # Create a function that raises an error using the decorator
    @tool(name="failing_function", description="A function that fails")
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

    settings = ObservabilitySettings()
    assert settings.enable_console_exporters is False


def test_console_exporters_opt_in_true(monkeypatch):
    """Test console exporters are added when ENABLE_CONSOLE_EXPORTERS is true."""
    from agent_framework.observability import ObservabilitySettings

    monkeypatch.setenv("ENABLE_CONSOLE_EXPORTERS", "true")

    settings = ObservabilitySettings()
    assert settings.enable_console_exporters is True


def test_console_exporters_default_false(monkeypatch):
    """Test console exporters default to False when not set."""
    from agent_framework.observability import ObservabilitySettings

    monkeypatch.delenv("ENABLE_CONSOLE_EXPORTERS", raising=False)

    settings = ObservabilitySettings()
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


# region Test OtelAttr enum


def test_otel_attr_repr_and_str():
    """Test OtelAttr __repr__ and __str__ return the string value."""
    assert repr(OtelAttr.OPERATION) == "gen_ai.operation.name"
    assert str(OtelAttr.OPERATION) == "gen_ai.operation.name"
    assert str(OtelAttr.TOOL_EXECUTION_OPERATION) == "execute_tool"


# region Test create_metric_views


def test_create_metric_views():
    """Test create_metric_views returns expected views."""
    from agent_framework.observability import create_metric_views

    views = create_metric_views()

    assert len(views) == 3
    # Check that views are View objects
    from opentelemetry.sdk.metrics.view import View

    for view in views:
        assert isinstance(view, View)


# region Test ObservabilitySettings.is_setup


def test_observability_settings_is_setup_initial(monkeypatch):
    """Test is_setup returns False initially."""
    from agent_framework.observability import ObservabilitySettings

    monkeypatch.delenv("ENABLE_INSTRUMENTATION", raising=False)
    settings = ObservabilitySettings()
    assert settings.is_setup is False


# region Test enable_instrumentation function


def test_enable_instrumentation_function(monkeypatch):
    """Test enable_instrumentation function enables instrumentation."""
    import importlib

    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "false")
    monkeypatch.setenv("ENABLE_SENSITIVE_DATA", "false")

    observability = importlib.import_module("agent_framework.observability")
    importlib.reload(observability)

    assert observability.OBSERVABILITY_SETTINGS.enable_instrumentation is False

    observability.enable_instrumentation()
    assert observability.OBSERVABILITY_SETTINGS.enable_instrumentation is True


def test_enable_instrumentation_with_sensitive_data(monkeypatch):
    """Test enable_instrumentation function with sensitive_data parameter."""
    import importlib

    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "false")
    monkeypatch.setenv("ENABLE_SENSITIVE_DATA", "false")

    observability = importlib.import_module("agent_framework.observability")
    importlib.reload(observability)

    observability.enable_instrumentation(enable_sensitive_data=True)
    assert observability.OBSERVABILITY_SETTINGS.enable_instrumentation is True
    assert observability.OBSERVABILITY_SETTINGS.enable_sensitive_data is True


# region Test _to_otel_part content types


def test_to_otel_part_text():
    """Test _to_otel_part with text content."""
    from agent_framework import Content
    from agent_framework.observability import _to_otel_part

    content = Content(type="text", text="Hello world")
    result = _to_otel_part(content)

    assert result == {"type": "text", "content": "Hello world"}


def test_to_otel_part_text_reasoning():
    """Test _to_otel_part with text_reasoning content."""
    from agent_framework import Content
    from agent_framework.observability import _to_otel_part

    content = Content(type="text_reasoning", text="Thinking about this...")
    result = _to_otel_part(content)

    assert result == {"type": "reasoning", "content": "Thinking about this..."}


def test_to_otel_part_uri():
    """Test _to_otel_part with uri content."""
    from agent_framework import Content
    from agent_framework.observability import _to_otel_part

    content = Content(type="uri", uri="https://example.com/image.png", media_type="image/png")
    result = _to_otel_part(content)

    assert result == {
        "type": "uri",
        "uri": "https://example.com/image.png",
        "mime_type": "image/png",
        "modality": "image",
    }


def test_to_otel_part_uri_no_media_type():
    """Test _to_otel_part with uri content without media_type."""
    from agent_framework import Content
    from agent_framework.observability import _to_otel_part

    content = Content(type="uri", uri="https://example.com/file")
    result = _to_otel_part(content)

    assert result == {
        "type": "uri",
        "uri": "https://example.com/file",
        "mime_type": None,
        "modality": None,
    }


def test_to_otel_part_data():
    """Test _to_otel_part with data content."""
    from agent_framework import Content
    from agent_framework.observability import _to_otel_part

    data = b"binary data"
    content = Content.from_data(data=data, media_type="application/octet-stream")
    result = _to_otel_part(content)

    assert result["type"] == "blob"
    assert result["mime_type"] == "application/octet-stream"
    assert result["modality"] == "application"


def test_to_otel_part_function_call():
    """Test _to_otel_part with function_call content."""
    from agent_framework import Content
    from agent_framework.observability import _to_otel_part

    content = Content(type="function_call", call_id="call_123", name="test_function", arguments='{"arg1": "value1"}')
    result = _to_otel_part(content)

    assert result == {
        "type": "tool_call",
        "id": "call_123",
        "name": "test_function",
        "arguments": '{"arg1": "value1"}',
    }


def test_to_otel_part_function_result():
    """Test _to_otel_part with function_result content."""
    from agent_framework import Content
    from agent_framework.observability import _to_otel_part

    content = Content(type="function_result", call_id="call_123", result="Success")
    result = _to_otel_part(content)

    assert result["type"] == "tool_call_response"
    assert result["id"] == "call_123"


# region Test workflow observability functions


def test_workflow_tracer_disabled(monkeypatch):
    """Test workflow_tracer returns NoOpTracer when disabled."""
    import importlib

    from opentelemetry import trace

    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "false")

    observability = importlib.import_module("agent_framework.observability")
    importlib.reload(observability)

    tracer = observability.workflow_tracer()
    assert isinstance(tracer, trace.NoOpTracer)


def test_create_workflow_span(span_exporter):
    """Test create_workflow_span creates a span."""
    from agent_framework.observability import create_workflow_span

    span_exporter.clear()
    with create_workflow_span("test_workflow", attributes={"key": "value"}):
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test_workflow"
    assert spans[0].attributes["key"] == "value"


def test_create_processing_span(span_exporter):
    """Test create_processing_span creates a span with correct attributes."""
    from agent_framework.observability import OtelAttr, create_processing_span

    span_exporter.clear()
    with create_processing_span(
        executor_id="exec_1",
        executor_type="TestExecutor",
        message_type="standard",
        payload_type="str",
    ):
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert OtelAttr.EXECUTOR_PROCESS_SPAN in spans[0].name
    assert spans[0].attributes[OtelAttr.EXECUTOR_ID] == "exec_1"
    assert spans[0].attributes[OtelAttr.EXECUTOR_TYPE] == "TestExecutor"


def test_create_edge_group_processing_span(span_exporter):
    """Test create_edge_group_processing_span creates correct span."""
    from agent_framework.observability import OtelAttr, create_edge_group_processing_span

    span_exporter.clear()
    with create_edge_group_processing_span(
        edge_group_type="ConditionalEdge",
        edge_group_id="edge_1",
        message_source_id="source_1",
        message_target_id="target_1",
    ):
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert OtelAttr.EDGE_GROUP_PROCESS_SPAN in spans[0].name
    assert spans[0].attributes[OtelAttr.EDGE_GROUP_TYPE] == "ConditionalEdge"
    assert spans[0].attributes[OtelAttr.EDGE_GROUP_ID] == "edge_1"
    assert spans[0].attributes[OtelAttr.MESSAGE_SOURCE_ID] == "source_1"
    assert spans[0].attributes[OtelAttr.MESSAGE_TARGET_ID] == "target_1"


def test_create_edge_group_processing_span_invalid_link(span_exporter):
    """Test create_edge_group_processing_span handles invalid trace context gracefully."""
    from agent_framework.observability import create_edge_group_processing_span

    span_exporter.clear()
    # Invalid trace context should be handled gracefully
    trace_contexts = [{"traceparent": "invalid-format"}]
    span_ids = ["invalid"]

    with create_edge_group_processing_span(
        edge_group_type="ConditionalEdge",
        source_trace_contexts=trace_contexts,
        source_span_ids=span_ids,
    ):
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1  # Should still create the span


# region Test EdgeGroupDeliveryStatus enum


def test_edge_group_delivery_status_str_and_repr():
    """Test EdgeGroupDeliveryStatus __str__ and __repr__ return the value."""
    from agent_framework.observability import EdgeGroupDeliveryStatus

    assert str(EdgeGroupDeliveryStatus.DELIVERED) == "delivered"
    assert repr(EdgeGroupDeliveryStatus.DELIVERED) == "delivered"
    assert str(EdgeGroupDeliveryStatus.EXCEPTION) == "exception"


# region Test _create_otlp_exporters with no endpoints


def test_create_otlp_exporters_no_endpoints():
    """Test _create_otlp_exporters returns empty list when no endpoints provided."""
    from agent_framework.observability import _create_otlp_exporters

    exporters = _create_otlp_exporters(protocol="grpc")
    assert exporters == []


# region Test exception handling in chat client traces


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_chat_client_observability_exception(mock_chat_client, span_exporter: InMemorySpanExporter):
    """Test that exceptions are captured in spans."""

    class FailingChatClient(mock_chat_client):
        async def _inner_get_response(self, *, messages, options, **kwargs):
            raise ValueError("Test error")

    client = FailingChatClient()
    messages = [Message(role="user", text="Test")]

    span_exporter.clear()
    with pytest.raises(ValueError, match="Test error"):
        await client.get_response(messages=messages, model_id="Test")

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.status.status_code == StatusCode.ERROR


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_chat_client_streaming_observability_exception(mock_chat_client, span_exporter: InMemorySpanExporter):
    """Test that exceptions in streaming are captured in spans.

    Note: Currently the streaming telemetry doesn't capture exceptions as errors
    in the span status because the span is closed before the exception propagates.
    This test verifies a span is created, but the status may not be ERROR.
    """

    class FailingStreamingChatClient(mock_chat_client):
        def _get_streaming_response(self, *, messages, options, **kwargs):
            async def _stream():
                yield ChatResponseUpdate(contents=[Content.from_text("Hello")], role="assistant")
                raise ValueError("Streaming error")

            return ResponseStream(_stream(), finalizer=ChatResponse.from_updates)

    client = FailingStreamingChatClient()
    messages = [Message(role="user", text="Test")]

    span_exporter.clear()
    with pytest.raises(ValueError, match="Streaming error"):
        async for _ in client.get_response(messages=messages, stream=True, model_id="Test"):
            pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    # Note: Streaming exceptions may not be captured as ERROR status
    # because the span closes before the exception is fully propagated


# region Test get_meter and get_tracer


def test_get_meter():
    """Test get_meter returns a meter with various parameters."""
    from agent_framework.observability import get_meter

    # Basic call
    meter = get_meter()
    assert meter is not None

    # With custom parameters
    meter = get_meter(name="custom_meter", version="1.0.0", attributes={"custom": "attribute"})
    assert meter is not None


def test_get_tracer():
    """Test get_tracer returns a tracer with various parameters."""
    from agent_framework.observability import get_tracer

    # Basic call
    tracer = get_tracer()
    assert tracer is not None

    # With custom parameters
    tracer = get_tracer(
        instrumenting_module_name="custom_module",
        instrumenting_library_version="2.0.0",
        attributes={"custom": "attr"},
    )
    assert tracer is not None


# region Test _get_response_attributes


def test_get_response_attributes_with_response_id():
    """Test _get_response_attributes includes response_id."""
    from unittest.mock import Mock

    from agent_framework.observability import OtelAttr, _get_response_attributes

    response = Mock()
    response.response_id = "resp_123"
    response.finish_reason = None
    response.raw_representation = None
    response.usage_details = None

    attrs = {}
    result = _get_response_attributes(attrs, response)

    assert result[OtelAttr.RESPONSE_ID] == "resp_123"


def test_get_response_attributes_with_finish_reason():
    """Test _get_response_attributes includes finish_reason."""
    from unittest.mock import Mock

    from agent_framework.observability import OtelAttr, _get_response_attributes

    response = Mock()
    response.response_id = None
    response.finish_reason = "stop"
    response.raw_representation = None
    response.usage_details = None

    attrs = {}
    result = _get_response_attributes(attrs, response)

    assert OtelAttr.FINISH_REASONS in result


def test_get_response_attributes_with_model_id():
    """Test _get_response_attributes includes model_id."""
    from unittest.mock import Mock

    from agent_framework.observability import _get_response_attributes

    response = Mock()
    response.response_id = None
    response.finish_reason = None
    response.raw_representation = None
    response.usage_details = None
    response.model_id = "gpt-4"

    attrs = {}
    result = _get_response_attributes(attrs, response)

    assert result[OtelAttr.RESPONSE_MODEL] == "gpt-4"


def test_get_response_attributes_with_usage():
    """Test _get_response_attributes includes usage details."""
    from unittest.mock import Mock

    from agent_framework.observability import OtelAttr, _get_response_attributes

    response = Mock()
    response.response_id = None
    response.finish_reason = None
    response.raw_representation = None
    response.usage_details = {"input_token_count": 100, "output_token_count": 50}

    attrs = {}
    result = _get_response_attributes(attrs, response)

    assert result[OtelAttr.INPUT_TOKENS] == 100
    assert result[OtelAttr.OUTPUT_TOKENS] == 50


def test_get_response_attributes_capture_usage_false():
    """Test _get_response_attributes skips usage when capture_usage is False."""
    from unittest.mock import Mock

    from agent_framework.observability import OtelAttr, _get_response_attributes

    response = Mock()
    response.response_id = None
    response.finish_reason = None
    response.raw_representation = None
    response.usage_details = {"input_token_count": 100, "output_token_count": 50}

    attrs = {}
    result = _get_response_attributes(attrs, response, capture_usage=False)

    assert OtelAttr.INPUT_TOKENS not in result
    assert OtelAttr.OUTPUT_TOKENS not in result


# region Test _get_exporters_from_env


def test_get_exporters_from_env_no_endpoints(monkeypatch):
    """Test _get_exporters_from_env returns empty list when no endpoints set."""
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
    assert exporters == []


# region Test ObservabilitySettings._configure


def test_observability_settings_configure_not_enabled(monkeypatch):
    """Test _configure does nothing when instrumentation is not enabled."""
    from agent_framework.observability import ObservabilitySettings

    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "false")
    settings = ObservabilitySettings()

    # Should not raise, should just return early
    settings._configure()
    assert settings.is_setup is False


def test_observability_settings_configure_already_setup(monkeypatch):
    """Test _configure does nothing when already set up."""
    from agent_framework.observability import ObservabilitySettings

    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "true")
    # Clear OTEL endpoints to avoid import errors
    for key in [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = ObservabilitySettings()

    # Manually mark as set up
    settings._executed_setup = True

    # Should not re-configure
    settings._configure()
    assert settings.is_setup is True


# region Test _to_otel_part edge cases


def test_to_otel_part_generic():
    """Test _to_otel_part with unknown content type uses to_dict fallback."""
    from agent_framework import Content
    from agent_framework.observability import _to_otel_part

    # Create a content with type that falls to default case
    content = Content(type="annotations", text="some text")
    result = _to_otel_part(content)

    # Should return result from to_dict
    assert result is not None
    assert isinstance(result, dict)


# region Test finish_reason from raw_representation


def test_get_response_attributes_finish_reason_from_raw():
    """Test _get_response_attributes gets finish_reason from raw_representation."""
    from unittest.mock import Mock

    from agent_framework.observability import OtelAttr, _get_response_attributes

    raw_rep = Mock()
    raw_rep.finish_reason = "length"

    response = Mock()
    response.response_id = None
    response.finish_reason = None  # No direct finish_reason
    response.raw_representation = raw_rep
    response.usage_details = None

    attrs = {}
    result = _get_response_attributes(attrs, response)

    assert OtelAttr.FINISH_REASONS in result


# region Test agent instrumentation


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_agent_observability(span_exporter: InMemorySpanExporter, enable_sensitive_data):
    """Test AgentTelemetryLayer with a mock agent."""

    class _MockAgent:
        AGENT_PROVIDER_NAME = "test_provider"

        def __init__(self):
            self._id = "test_agent"
            self._name = "Test Agent"
            self._description = "A test agent"
            self._default_options = {}

        @property
        def id(self):
            return self._id

        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return self._description

        @property
        def default_options(self):
            return self._default_options

        async def run(
            self,
            messages=None,
            *,
            stream: bool = False,
            session=None,
            **kwargs,
        ):
            if stream:
                return ResponseStream(
                    self._run_stream(messages=messages, session=session),
                    finalizer=lambda x: AgentResponse.from_updates(x),
                )
            return AgentResponse(messages=[Message("assistant", ["Test response"])])

        async def _run_stream(
            self,
            messages=None,
            *,
            session=None,
            **kwargs,
        ):
            from agent_framework import AgentResponseUpdate

            yield AgentResponseUpdate(contents=[Content.from_text("Test")], role="assistant")

    class MockAgent(AgentTelemetryLayer, _MockAgent):
        pass

    agent = MockAgent()

    span_exporter.clear()
    response = await agent.run(messages="Hello")

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_agent_observability_with_exception(span_exporter: InMemorySpanExporter, enable_sensitive_data):
    """Test agent instrumentation captures exceptions."""

    class _FailingAgent:
        AGENT_PROVIDER_NAME = "test_provider"

        def __init__(self):
            self._id = "failing_agent"
            self._name = "Failing Agent"
            self._description = "An agent that fails"
            self._default_options = {}

        @property
        def id(self):
            return self._id

        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return self._description

        @property
        def default_options(self):
            return self._default_options

        async def run(self, messages=None, *, stream: bool = False, session=None, **kwargs):
            raise RuntimeError("Agent failed")

    class FailingAgent(AgentTelemetryLayer, _FailingAgent):
        pass

    agent = FailingAgent()

    span_exporter.clear()
    with pytest.raises(RuntimeError, match="Agent failed"):
        await agent.run(messages="Hello")

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code == StatusCode.ERROR


# region Test agent streaming observability


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_agent_streaming_observability(span_exporter: InMemorySpanExporter, enable_sensitive_data):
    """Test agent streaming instrumentation."""
    from agent_framework import AgentResponseUpdate

    class _StreamingAgent:
        AGENT_PROVIDER_NAME = "test_provider"

        def __init__(self):
            self._id = "streaming_agent"
            self._name = "Streaming Agent"
            self._description = "A streaming test agent"
            self._default_options = {}

        @property
        def id(self):
            return self._id

        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return self._description

        @property
        def default_options(self):
            return self._default_options

        def run(self, messages=None, *, stream=False, session=None, **kwargs):
            if stream:
                return self._run_stream_impl(messages=messages, **kwargs)
            return self._run_impl(messages=messages, **kwargs)

        async def _run_impl(self, messages=None, *, session=None, **kwargs):
            return AgentResponse(messages=[Message("assistant", ["Test"])])

        def _run_stream_impl(self, messages=None, *, session=None, **kwargs):
            async def _stream():
                yield AgentResponseUpdate(contents=[Content.from_text("Hello ")], role="assistant")
                yield AgentResponseUpdate(contents=[Content.from_text("World")], role="assistant")

            return ResponseStream(
                _stream(),
                finalizer=AgentResponse.from_updates,
            )

    class StreamingAgent(AgentTelemetryLayer, _StreamingAgent):
        pass

    agent = StreamingAgent()

    span_exporter.clear()
    updates = []
    stream = agent.run(messages="Hello", stream=True)
    async for update in stream:
        updates.append(update)
    await stream.get_final_response()

    assert len(updates) == 2
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1


# region Test AgentTelemetryLayer error cases


async def test_agent_telemetry_layer_missing_run():
    """Test AgentTelemetryLayer raises error when run method is missing."""

    class InvalidAgent:
        AGENT_PROVIDER_NAME = "test"

        @property
        def id(self):
            return "test"

        @property
        def name(self):
            return "test"

        @property
        def description(self):
            return "test"

    # AgentTelemetryLayer cannot be applied to a class without run method
    # The error will occur when trying to call run on the instance
    class InvalidInstrumentedAgent(AgentTelemetryLayer, InvalidAgent):
        pass

    agent = InvalidInstrumentedAgent()
    # The agent can be instantiated but will fail when run is called
    # because run is not defined
    with pytest.raises(AttributeError):
        # This will fail because InvalidAgent doesn't have a run method
        # that AgentTelemetryLayer's run can delegate to

        await agent.run("test")


# region Test _capture_messages with finish_reason


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_capture_messages_with_finish_reason(mock_chat_client, span_exporter: InMemorySpanExporter):
    """Test that finish_reason is captured in output messages."""
    import json

    class ClientWithFinishReason(mock_chat_client):
        async def _inner_get_response(self, *, messages, options, **kwargs):
            return ChatResponse(
                messages=[Message(role="assistant", text="Done")],
                usage_details=UsageDetails(input_token_count=5, output_token_count=10),
                finish_reason="stop",
            )

    client = ClientWithFinishReason()
    messages = [Message(role="user", text="Test")]

    span_exporter.clear()
    response = await client.get_response(messages=messages, model_id="Test")

    assert response is not None
    assert response.finish_reason == "stop"
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Check output messages include finish_reason
    output_messages = json.loads(span.attributes[OtelAttr.OUTPUT_MESSAGES])
    assert output_messages[-1].get("finish_reason") == "stop"


# region Test agent streaming exception


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_agent_streaming_exception(span_exporter: InMemorySpanExporter, enable_sensitive_data):
    """Test agent streaming captures exceptions."""
    from agent_framework import AgentResponseUpdate

    class _FailingStreamingAgent:
        AGENT_PROVIDER_NAME = "test_provider"

        def __init__(self):
            self._id = "failing_stream"
            self._name = "Failing Stream"
            self._description = "A failing streaming agent"
            self._default_options = {}

        @property
        def id(self):
            return self._id

        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return self._description

        @property
        def default_options(self):
            return self._default_options

        def run(self, messages=None, *, stream=False, session=None, **kwargs):
            if stream:
                return self._run_stream_impl(messages=messages, **kwargs)
            return self._run_impl(messages=messages, **kwargs)

        async def _run_impl(self, messages=None, *, session=None, **kwargs):
            return AgentResponse(messages=[])

        def _run_stream_impl(self, messages=None, *, session=None, **kwargs):
            async def _stream():
                yield AgentResponseUpdate(contents=[Content.from_text("Starting")], role="assistant")
                raise RuntimeError("Stream failed")

            return ResponseStream(
                _stream(),
                finalizer=AgentResponse.from_updates,
            )

    class FailingStreamingAgent(AgentTelemetryLayer, _FailingStreamingAgent):
        pass

    agent = FailingStreamingAgent()

    span_exporter.clear()
    with pytest.raises(RuntimeError, match="Stream failed"):
        stream = agent.run(messages="Hello", stream=True)
        async for _ in stream:
            pass

    # Note: When an exception occurs during streaming iteration, the span
    # may not be properly closed/exported because the result_hook (which
    # closes the span) is not called. This is a known limitation.


# region Test instrumentation when disabled


@pytest.mark.parametrize("enable_instrumentation", [False], indirect=True)
async def test_chat_client_when_disabled(mock_chat_client, span_exporter: InMemorySpanExporter):
    """Test that no spans are created when instrumentation is disabled."""
    client = mock_chat_client()
    messages = [Message(role="user", text="Test")]

    span_exporter.clear()
    response = await client.get_response(messages=messages, model_id="Test")

    assert response is not None
    spans = span_exporter.get_finished_spans()
    # No spans should be created when disabled
    assert len(spans) == 0


@pytest.mark.parametrize("enable_instrumentation", [False], indirect=True)
async def test_chat_client_streaming_when_disabled(mock_chat_client, span_exporter: InMemorySpanExporter):
    """Test streaming creates no spans when instrumentation is disabled."""
    client = mock_chat_client()
    messages = [Message(role="user", text="Test")]

    span_exporter.clear()
    updates = []
    async for update in client.get_response(messages=messages, stream=True, model_id="Test"):
        updates.append(update)

    assert len(updates) == 2  # Still works functionally
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 0


@pytest.mark.parametrize("enable_instrumentation", [False], indirect=True)
async def test_agent_when_disabled(span_exporter: InMemorySpanExporter):
    """Test agent creates no spans when instrumentation is disabled."""

    class _TestAgent:
        AGENT_PROVIDER_NAME = "test"

        def __init__(self):
            self._id = "test"
            self._name = "Test"
            self._description = "Test"
            self._default_options = {}

        @property
        def id(self):
            return self._id

        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return self._description

        @property
        def default_options(self):
            return self._default_options

        async def run(self, messages=None, *, stream: bool = False, session=None, **kwargs):
            if stream:
                return ResponseStream(
                    self._run_stream(messages=messages, **kwargs),
                    lambda x: AgentResponse.from_updates(x),
                )
            return AgentResponse(messages=[])

        async def _run_stream(self, messages=None, *, session=None, **kwargs):
            from agent_framework import AgentResponseUpdate

            yield AgentResponseUpdate(contents=[Content.from_text("test")], role="assistant")

    class TestAgent(AgentTelemetryLayer, _TestAgent):
        pass

    agent = TestAgent()

    span_exporter.clear()
    await agent.run(messages="Hello")

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 0


@pytest.mark.parametrize("enable_instrumentation", [False], indirect=True)
async def test_agent_streaming_when_disabled(span_exporter: InMemorySpanExporter):
    """Test agent streaming creates no spans when disabled."""
    from agent_framework import AgentResponseUpdate

    class _TestAgent:
        AGENT_PROVIDER_NAME = "test"

        def __init__(self):
            self._id = "test"
            self._name = "Test"
            self._description = "Test"
            self._default_options = {}

        @property
        def id(self):
            return self._id

        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return self._description

        @property
        def default_options(self):
            return self._default_options

        def run(self, messages=None, *, stream=False, session=None, **kwargs):
            if stream:
                return self._run_stream(messages=messages, **kwargs)
            return self._run(messages=messages, **kwargs)

        async def _run(self, messages=None, *, session=None, **kwargs):
            return AgentResponse(messages=[])

        async def _run_stream(self, messages=None, *, session=None, **kwargs):
            yield AgentResponseUpdate(contents=[Content.from_text("test")], role="assistant")

    class TestAgent(AgentTelemetryLayer, _TestAgent):
        pass

    agent = TestAgent()

    span_exporter.clear()
    updates = []
    async for u in agent.run(messages="Hello", stream=True):
        updates.append(u)

    assert len(updates) == 1
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 0


# region Test _configure_providers


def test_configure_providers_with_span_exporters(monkeypatch):
    """Test _configure_providers correctly handles span exporters."""
    from unittest.mock import Mock, patch

    from opentelemetry.sdk.trace.export import SpanExporter

    from agent_framework.observability import ObservabilitySettings

    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "true")
    for key in [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = ObservabilitySettings()

    # Create mock span exporter
    mock_span_exporter = Mock(spec=SpanExporter)

    with patch("opentelemetry.trace.set_tracer_provider") as mock_set_tracer:
        settings._configure_providers([mock_span_exporter])

    mock_set_tracer.assert_called_once()


# region Test histograms


def test_get_duration_histogram():
    """Test _get_duration_histogram creates histogram."""
    from agent_framework.observability import _get_duration_histogram

    histogram = _get_duration_histogram()
    assert histogram is not None


def test_get_token_usage_histogram():
    """Test _get_token_usage_histogram creates histogram."""
    from agent_framework.observability import _get_token_usage_histogram

    histogram = _get_token_usage_histogram()
    assert histogram is not None


# region Test capture_exception


def test_capture_exception(span_exporter: InMemorySpanExporter):
    """Test capture_exception adds exception info to span."""
    from time import time_ns

    from opentelemetry.trace import StatusCode

    from agent_framework.observability import capture_exception, get_tracer

    span_exporter.clear()
    tracer = get_tracer()

    with tracer.start_as_current_span("test_span") as span:
        exception = ValueError("Test error")
        capture_exception(span=span, exception=exception, timestamp=time_ns())

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code == StatusCode.ERROR
    # Verify exception was recorded
    assert len(spans[0].events) > 0


# region Test _get_span


def test_get_span_creates_span(span_exporter: InMemorySpanExporter):
    """Test _get_span creates a span with correct attributes."""
    from agent_framework.observability import OtelAttr, _get_span

    span_exporter.clear()
    attributes = {
        OtelAttr.OPERATION: "test_operation",
        OtelAttr.TOOL_NAME: "test_tool",
    }

    with _get_span(attributes=attributes, span_name_attribute=OtelAttr.TOOL_NAME):
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert "test_tool" in spans[0].name


# region Test _get_span_attributes


def test_get_span_attributes():
    """Test _get_span_attributes creates correct attribute dict."""
    from agent_framework.observability import OtelAttr, _get_span_attributes

    attrs = _get_span_attributes(
        operation_name="chat",
        provider_name="openai",
        model="gpt-4",
        service_url="https://api.openai.com",
    )

    assert attrs[OtelAttr.OPERATION] == "chat"
    assert OtelAttr.ADDRESS in attrs


def test_get_span_attributes_with_agent_info():
    """Test _get_span_attributes with agent-specific info."""
    from agent_framework.observability import OtelAttr, _get_span_attributes

    attrs = _get_span_attributes(
        operation_name="invoke_agent",
        provider_name="test",
        agent_id="agent_1",
        agent_name="Test Agent",
        agent_description="A test agent",
        thread_id="thread_123",
    )

    assert attrs[OtelAttr.AGENT_ID] == "agent_1"
    assert attrs[OtelAttr.AGENT_NAME] == "Test Agent"
    assert attrs[OtelAttr.AGENT_DESCRIPTION] == "A test agent"


# region Test _capture_response


def test_capture_response(span_exporter: InMemorySpanExporter):
    """Test _capture_response sets span attributes and records to histograms."""
    from agent_framework.observability import OtelAttr, _capture_response, get_tracer

    span_exporter.clear()
    tracer = get_tracer()

    # Create real histograms
    from agent_framework.observability import _get_duration_histogram, _get_token_usage_histogram

    token_histogram = _get_token_usage_histogram()
    duration_histogram = _get_duration_histogram()

    attrs = {
        "gen_ai.request.model": "test-model",
        OtelAttr.INPUT_TOKENS: 100,
        OtelAttr.OUTPUT_TOKENS: 50,
    }

    with tracer.start_as_current_span("test_span") as span:
        _capture_response(
            span=span,
            attributes=attrs,
            token_usage_histogram=token_histogram,
            operation_duration_histogram=duration_histogram,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    # Verify attributes were set on the span
    assert spans[0].attributes.get(OtelAttr.INPUT_TOKENS) == 100
    assert spans[0].attributes.get(OtelAttr.OUTPUT_TOKENS) == 50


async def test_layer_ordering_span_sequence_with_function_calling(span_exporter: InMemorySpanExporter):
    """Test that with correct layer ordering, spans appear in the expected sequence.

    When using the correct layer ordering (ChatMiddlewareLayer, FunctionInvocationLayer,
    ChatTelemetryLayer, BaseChatClient), the spans should appear in this order:
    1. First 'chat' span (initial LLM call that returns function call)
    2. 'execute_tool' span (function invocation)
    3. Second 'chat' span (follow-up LLM call with function result)

    This validates that telemetry is correctly applied inside the function calling loop,
    so each LLM call gets its own span.
    """
    from agent_framework import Content
    from agent_framework._middleware import ChatMiddlewareLayer
    from agent_framework._tools import FunctionInvocationLayer

    @tool(name="get_weather", description="Get the weather for a location")
    def get_weather(location: str) -> str:
        return f"The weather in {location} is sunny."

    # Correct layer ordering: FunctionInvocationLayer BEFORE ChatTelemetryLayer
    # This ensures each inner LLM call gets its own telemetry span
    class MockChatClientWithLayers(
        ChatMiddlewareLayer,
        FunctionInvocationLayer,
        ChatTelemetryLayer,
        BaseChatClient,
    ):
        OTEL_PROVIDER_NAME = "test_provider"

        def __init__(self):
            super().__init__()
            self.call_count = 0
            self.model_id = "test-model"

        def service_url(self):
            return "https://test.example.com"

        def _inner_get_response(
            self, *, messages: MutableSequence[Message], stream: bool, options: dict[str, Any], **kwargs: Any
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            async def _get() -> ChatResponse:
                self.call_count += 1
                if self.call_count == 1:
                    return ChatResponse(
                        messages=[
                            Message(
                                role="assistant",
                                contents=[
                                    Content.from_function_call(
                                        call_id="call_123",
                                        name="get_weather",
                                        arguments='{"location": "Seattle"}',
                                    )
                                ],
                            )
                        ],
                    )
                return ChatResponse(
                    messages=[Message(role="assistant", text="The weather in Seattle is sunny!")],
                )

            return _get()

    client = MockChatClientWithLayers()
    span_exporter.clear()

    response = await client.get_response(
        messages=[Message(role="user", text="What's the weather in Seattle?")],
        options={"tools": [get_weather], "tool_choice": "auto"},
    )

    assert response is not None
    assert client.call_count == 2, f"Expected 2 inner LLM calls, got {client.call_count}"

    spans = span_exporter.get_finished_spans()

    assert len(spans) == 3, f"Expected 3 spans (chat, execute_tool, chat), got {len(spans)}: {[s.name for s in spans]}"

    # Sort spans by start time to get the logical order
    sorted_spans = sorted(spans, key=lambda s: s.start_time or 0)

    # First span: initial chat (LLM call that returns function call request)
    assert sorted_spans[0].name.startswith("chat"), f"First span should be 'chat', got '{sorted_spans[0].name}'"

    # Second span: execute_tool (function invocation)
    assert sorted_spans[1].name.startswith("execute_tool"), (
        f"Second span should be 'execute_tool', got '{sorted_spans[1].name}'"
    )
    assert sorted_spans[1].attributes.get(OtelAttr.TOOL_NAME) == "get_weather"
    assert sorted_spans[1].attributes.get(OtelAttr.OPERATION.value) == OtelAttr.TOOL_EXECUTION_OPERATION

    # Third span: second chat (LLM call with function result)
    assert sorted_spans[2].name.startswith("chat"), f"Third span should be 'chat', got '{sorted_spans[2].name}'"


# region Test non-ASCII character handling in JSON serialization


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_capture_messages_preserves_non_ascii_characters(mock_chat_client, span_exporter: InMemorySpanExporter):
    """Test that non-ASCII characters (e.g., Japanese) are preserved in span attributes."""
    import json

    japanese_text = "こんにちは世界"  # "Hello World" in Japanese

    class ClientWithJapanese(mock_chat_client):
        async def _inner_get_response(self, *, messages, options, **kwargs):
            return ChatResponse(
                messages=[Message(role="assistant", text=japanese_text)],
                usage_details=UsageDetails(input_token_count=5, output_token_count=10),
            )

    client = ClientWithJapanese()
    messages = [Message(role="user", text=japanese_text)]

    span_exporter.clear()
    response = await client.get_response(messages=messages, model_id="Test")

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Verify input messages preserve Japanese characters
    input_messages_json = span.attributes[OtelAttr.INPUT_MESSAGES]
    assert japanese_text in input_messages_json
    # Ensure it's not escaped to Unicode
    assert "\\u" not in input_messages_json

    # Verify output messages preserve Japanese characters
    output_messages_json = span.attributes[OtelAttr.OUTPUT_MESSAGES]
    assert japanese_text in output_messages_json
    assert "\\u" not in output_messages_json

    # Verify JSON is valid and contains the text
    input_messages = json.loads(input_messages_json)
    assert input_messages[0]["parts"][0]["content"] == japanese_text
    output_messages = json.loads(output_messages_json)
    assert output_messages[0]["parts"][0]["content"] == japanese_text


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_system_instructions_preserves_non_ascii_characters(span_exporter: InMemorySpanExporter):
    """Test that non-ASCII characters are preserved in system instructions span attribute."""
    import json

    from opentelemetry import trace

    chinese_text = "你好世界"  # "Hello World" in Chinese

    tracer = trace.get_tracer("test")
    span_exporter.clear()

    with tracer.start_as_current_span("test_span") as span:
        _capture_messages(
            span=span,
            provider_name="test_provider",
            messages=[Message(role="user", text="Test")],
            system_instructions=chinese_text,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Verify system instructions preserve Chinese characters
    system_instructions_json = span.attributes[OtelAttr.SYSTEM_INSTRUCTIONS]
    assert chinese_text in system_instructions_json
    assert "\\u" not in system_instructions_json

    # Verify JSON is valid and contains the text
    system_instructions = json.loads(system_instructions_json)
    assert system_instructions[0]["content"] == chinese_text


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_tool_arguments_preserves_non_ascii_characters(span_exporter: InMemorySpanExporter):
    """Test that non-ASCII characters are preserved in tool arguments span attribute."""
    import json

    korean_text = "안녕하세요"  # "Hello" in Korean

    @tool
    def greet(message: str) -> str:
        """Greet with a message."""
        return f"Greeted: {message}"

    span_exporter.clear()
    await greet.invoke(message=korean_text)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Verify tool arguments preserve Korean characters
    tool_arguments_json = span.attributes[OtelAttr.TOOL_ARGUMENTS]
    assert korean_text in tool_arguments_json
    assert "\\u" not in tool_arguments_json

    # Verify JSON is valid and contains the text
    tool_arguments = json.loads(tool_arguments_json)
    assert tool_arguments["message"] == korean_text


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_tool_result_preserves_non_ascii_characters(span_exporter: InMemorySpanExporter):
    """Test that non-ASCII characters are preserved in tool result span attribute."""
    arabic_text = "مرحبا بالعالم"  # "Hello World" in Arabic

    @tool
    def echo(text: str) -> str:
        """Echo the text back."""
        return text

    span_exporter.clear()
    result = await echo.invoke(text=arabic_text)

    assert result == arabic_text
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Verify tool result preserves Arabic characters
    tool_result = span.attributes[OtelAttr.TOOL_RESULT]
    assert arabic_text in tool_result


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_tool_arguments_pydantic_preserves_non_ascii_characters(
    span_exporter: InMemorySpanExporter,
) -> None:
    """Test that non-ASCII characters are preserved in tool arguments when using a Pydantic model."""
    import json

    from pydantic import BaseModel

    japanese_text = "こんにちは"  # "Hello" in Japanese

    class Greeting(BaseModel):
        message: str

    @tool
    def greet_with_model(greeting: Greeting) -> str:
        """Greet with a message contained in a Pydantic model."""
        # When invoked via the tool's input_model, greeting is passed as a dict
        if isinstance(greeting, dict):
            return f"Greeted: {greeting['message']}"
        return f"Greeted: {greeting.message}"

    span_exporter.clear()
    # Use the tool's input_model to properly pass the Pydantic model argument
    input_model = greet_with_model.input_model
    await greet_with_model.invoke(arguments=input_model(greeting=Greeting(message=japanese_text)))

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Verify tool arguments preserve Japanese characters
    tool_arguments_json = span.attributes[OtelAttr.TOOL_ARGUMENTS]
    assert japanese_text in tool_arguments_json
    assert "\\u" not in tool_arguments_json

    # Verify JSON is valid and contains the text
    tool_arguments = json.loads(tool_arguments_json)
    assert tool_arguments["greeting"]["message"] == japanese_text


# region Test merged options for instructions


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_agent_instructions_from_default_options(
    mock_chat_agent, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that instructions from default_options are captured in agent telemetry."""
    import json

    agent = mock_chat_agent()
    agent.default_options = {"model_id": "TestModel", "instructions": "Default system instructions."}

    messages = [Message(role="user", text="Test message")]
    span_exporter.clear()
    response = await agent.run(messages)

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Instructions from default_options should be captured
    assert OtelAttr.SYSTEM_INSTRUCTIONS in span.attributes
    system_instructions = json.loads(span.attributes[OtelAttr.SYSTEM_INSTRUCTIONS])
    assert len(system_instructions) == 1
    assert system_instructions[0]["content"] == "Default system instructions."


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_agent_instructions_from_options_override(
    mock_chat_agent, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that instructions from options are captured when no default_options instructions exist."""
    import json

    agent = mock_chat_agent()
    agent.default_options = {"model_id": "TestModel"}  # No default instructions

    messages = [Message(role="user", text="Test message")]
    span_exporter.clear()
    response = await agent.run(messages, options={"instructions": "Override instructions."})

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert OtelAttr.SYSTEM_INSTRUCTIONS in span.attributes
    system_instructions = json.loads(span.attributes[OtelAttr.SYSTEM_INSTRUCTIONS])
    assert len(system_instructions) == 1
    assert system_instructions[0]["content"] == "Override instructions."


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_agent_instructions_merged_from_default_and_options(
    mock_chat_agent, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that instructions from both default_options and options are merged (concatenated)."""
    import json

    agent = mock_chat_agent()
    agent.default_options = {"model_id": "TestModel", "instructions": "Default instructions."}

    messages = [Message(role="user", text="Test message")]
    span_exporter.clear()
    response = await agent.run(messages, options={"instructions": "Additional instructions."})

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Merged instructions should contain both default and override, concatenated with newline
    assert OtelAttr.SYSTEM_INSTRUCTIONS in span.attributes
    system_instructions = json.loads(span.attributes[OtelAttr.SYSTEM_INSTRUCTIONS])
    assert len(system_instructions) == 1
    assert "Default instructions." in system_instructions[0]["content"]
    assert "Additional instructions." in system_instructions[0]["content"]


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_agent_streaming_instructions_from_default_options(
    mock_chat_agent, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that streaming agent telemetry captures instructions from default_options."""
    import json

    agent = mock_chat_agent()
    agent.default_options = {"model_id": "TestModel", "instructions": "Default streaming instructions."}

    messages = [Message(role="user", text="Test message")]
    span_exporter.clear()
    updates = []
    stream = agent.run(messages, stream=True)
    async for update in stream:
        updates.append(update)
    await stream.get_final_response()

    assert len(updates) == 2
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert OtelAttr.SYSTEM_INSTRUCTIONS in span.attributes
    system_instructions = json.loads(span.attributes[OtelAttr.SYSTEM_INSTRUCTIONS])
    assert len(system_instructions) == 1
    assert system_instructions[0]["content"] == "Default streaming instructions."


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_agent_streaming_instructions_merged_from_default_and_options(
    mock_chat_agent, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that streaming agent telemetry captures merged instructions from default_options and options."""
    import json

    agent = mock_chat_agent()
    agent.default_options = {"model_id": "TestModel", "instructions": "Default instructions."}

    messages = [Message(role="user", text="Test message")]
    span_exporter.clear()
    updates = []
    stream = agent.run(messages, stream=True, options={"instructions": "Stream override."})
    async for update in stream:
        updates.append(update)
    await stream.get_final_response()

    assert len(updates) == 2
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert OtelAttr.SYSTEM_INSTRUCTIONS in span.attributes
    system_instructions = json.loads(span.attributes[OtelAttr.SYSTEM_INSTRUCTIONS])
    assert len(system_instructions) == 1
    assert "Default instructions." in system_instructions[0]["content"]
    assert "Stream override." in system_instructions[0]["content"]


@pytest.mark.parametrize("enable_sensitive_data", [True], indirect=True)
async def test_agent_no_instructions_in_default_or_options(
    mock_chat_agent, span_exporter: InMemorySpanExporter, enable_sensitive_data
):
    """Test that system_instructions is not set when neither default_options nor options have instructions."""
    agent = mock_chat_agent()
    agent.default_options = {"model_id": "TestModel"}  # No instructions

    messages = [Message(role="user", text="Test message")]
    span_exporter.clear()
    response = await agent.run(messages)

    assert response is not None
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert OtelAttr.SYSTEM_INSTRUCTIONS not in span.attributes


# region Additional coverage tests


def test_get_instructions_from_options_none():
    """Test _get_instructions_from_options returns None for None input."""
    from agent_framework.observability import _get_instructions_from_options

    assert _get_instructions_from_options(None) is None


def test_get_instructions_from_options_non_dict():
    """Test _get_instructions_from_options returns None for non-dict input."""
    from agent_framework.observability import _get_instructions_from_options

    assert _get_instructions_from_options("not a dict") is None
    assert _get_instructions_from_options(42) is None


def test_get_instructions_from_options_dict_with_instructions():
    """Test _get_instructions_from_options extracts instructions from dict."""
    from agent_framework.observability import _get_instructions_from_options

    assert _get_instructions_from_options({"instructions": "do stuff"}) == "do stuff"
    assert _get_instructions_from_options({"other_key": "value"}) is None


def test_get_span_attributes_with_non_dict_options():
    """Test _get_span_attributes handles non-dict options gracefully."""
    from agent_framework.observability import _get_span_attributes

    # Pass options as a non-dict value; should not crash
    attrs = _get_span_attributes(
        operation_name="chat",
        provider_name="test",
        all_options="not_a_dict",
    )
    assert attrs[OtelAttr.OPERATION] == "chat"


def test_capture_response_with_error_type(span_exporter: InMemorySpanExporter):
    """Test _capture_response includes error_type in duration histogram attributes."""
    from agent_framework.observability import OtelAttr, _capture_response, get_tracer

    span_exporter.clear()
    tracer = get_tracer()

    from agent_framework.observability import _get_duration_histogram, _get_token_usage_histogram

    token_histogram = _get_token_usage_histogram()
    duration_histogram = _get_duration_histogram()

    attrs = {
        "gen_ai.request.model": "test-model",
        OtelAttr.ERROR_TYPE: "ValueError",
    }

    with tracer.start_as_current_span("test_span") as span:
        _capture_response(
            span=span,
            attributes=attrs,
            token_usage_histogram=token_histogram,
            operation_duration_histogram=duration_histogram,
            duration=0.5,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes.get(OtelAttr.ERROR_TYPE) == "ValueError"


def test_configure_otel_providers_with_env_file_path(monkeypatch, tmp_path):
    """Test configure_otel_providers with env_file_path creates new settings."""
    import importlib

    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "false")
    for key in [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    ]:
        monkeypatch.delenv(key, raising=False)

    observability = importlib.import_module("agent_framework.observability")
    importlib.reload(observability)

    env_file = tmp_path / ".env"
    env_file.write_text("ENABLE_INSTRUMENTATION=true\n")

    observability.configure_otel_providers(
        env_file_path=str(env_file),
        enable_sensitive_data=True,
        vs_code_extension_port=None,
    )

    assert observability.OBSERVABILITY_SETTINGS.enable_instrumentation is True
    assert observability.OBSERVABILITY_SETTINGS.enable_sensitive_data is True


def test_configure_otel_providers_with_env_file_and_vs_code_port(monkeypatch, tmp_path):
    """Test configure_otel_providers with env_file_path and vs_code_extension_port."""
    import importlib

    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "false")
    for key in [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    ]:
        monkeypatch.delenv(key, raising=False)

    observability = importlib.import_module("agent_framework.observability")
    importlib.reload(observability)

    env_file = tmp_path / ".env"
    env_file.write_text("ENABLE_INSTRUMENTATION=true\n")

    observability.configure_otel_providers(
        env_file_path=str(env_file),
        env_file_encoding="utf-8",
        vs_code_extension_port=4317,
    )

    assert observability.OBSERVABILITY_SETTINGS.enable_instrumentation is True
    assert observability.OBSERVABILITY_SETTINGS.vs_code_extension_port == 4317


def test_get_exporters_from_env_with_env_file_path(monkeypatch, tmp_path):
    """Test _get_exporters_from_env loads dotenv when env_file_path is provided."""
    from agent_framework.observability import _get_exporters_from_env

    for key in [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    ]:
        monkeypatch.delenv(key, raising=False)

    # Create a .env file with no OTEL endpoints so it returns empty
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_VAR=value\n")

    exporters = _get_exporters_from_env(env_file_path=str(env_file))
    assert exporters == []


def test_create_resource_with_env_file_path(monkeypatch, tmp_path):
    """Test create_resource loads dotenv when env_file_path is provided."""
    from agent_framework.observability import create_resource

    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_VERSION", raising=False)
    monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("OTEL_SERVICE_NAME=my_test_service\n")

    resource = create_resource(env_file_path=str(env_file))
    assert resource.attributes.get("service.name") == "my_test_service"


def test_get_meter_typeerror_fallback():
    """Test get_meter falls back when TypeError is raised (old OTel versions)."""
    from unittest.mock import patch as mock_patch

    from agent_framework.observability import get_meter

    call_count = 0

    def mock_get_meter(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if "attributes" in kwargs:
            raise TypeError("unexpected keyword argument 'attributes'")
        from opentelemetry import metrics

        return metrics.get_meter_provider().get_meter(*args, **{k: v for k, v in kwargs.items() if k != "attributes"})

    with mock_patch("agent_framework.observability.metrics.get_meter", side_effect=mock_get_meter):
        meter = get_meter(name="test", attributes={"key": "val"})
        assert meter is not None
        assert call_count == 2
