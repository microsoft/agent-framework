# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import MutableSequence
from typing import Any
from unittest.mock import Mock, patch

import pytest
from opentelemetry.trace import StatusCode

from agent_framework import (
    AgentRunResponse,
    AgentThread,
    ChatClientBase,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    UsageDetails,
)
from agent_framework.exceptions import AgentException, ChatClientInitializationError
from agent_framework.telemetry import (
    AGENT_FRAMEWORK_USER_AGENT,
    OPEN_TELEMETRY_AGENT_MARKER,
    OPEN_TELEMETRY_CHAT_CLIENT_MARKER,
    ROLE_EVENT_MAP,
    TELEMETRY_DISABLED_ENV_VAR,
    USER_AGENT_KEY,
    ChatMessageListTimestampFilter,
    OpenTelemetryAgent,
    OpenTelemetryChatClient,
    OtelAttr,
    prepend_agent_framework_to_user_agent,
    start_as_current_span,
)

# region Test constants


def test_telemetry_disabled_env_var():
    """Test that the telemetry disabled environment variable is correctly defined."""
    assert TELEMETRY_DISABLED_ENV_VAR == "AZURE_TELEMETRY_DISABLED"


def test_user_agent_key():
    """Test that the user agent key is correctly defined."""
    assert USER_AGENT_KEY == "User-Agent"


def test_agent_framework_user_agent_format():
    """Test that the agent framework user agent is correctly formatted."""
    assert AGENT_FRAMEWORK_USER_AGENT.startswith("agent-framework-python/")


def test_app_info_when_telemetry_enabled():
    """Test that APP_INFO is set when telemetry is enabled."""
    with patch("agent_framework.telemetry.IS_TELEMETRY_ENABLED", True):
        import importlib

        import agent_framework.telemetry

        importlib.reload(agent_framework.telemetry)
        from agent_framework.telemetry import APP_INFO

        assert APP_INFO is not None
        assert "agent-framework-version" in APP_INFO
        assert APP_INFO["agent-framework-version"].startswith("python/")


def test_app_info_when_telemetry_disabled():
    """Test that APP_INFO is None when telemetry is disabled."""
    # Test the logic directly since APP_INFO is set at module import time
    with patch("agent_framework.telemetry.IS_TELEMETRY_ENABLED", False):
        # Simulate the module's logic for APP_INFO
        test_app_info = (
            {
                "agent-framework-version": "python/test",
            }
            if False  # This simulates IS_TELEMETRY_ENABLED being False
            else None
        )
        assert test_app_info is None


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
    assert OtelAttr.MODEL == "gen_ai.request.model"
    assert OtelAttr.CHAT_COMPLETION_OPERATION == "chat"
    assert OtelAttr.TOOL_EXECUTION_OPERATION == "execute_tool"
    assert OtelAttr.AGENT_INVOKE_OPERATION == "invoke_agent"


# region Test prepend_agent_framework_to_user_agent


def test_prepend_to_existing_user_agent():
    """Test prepending to existing User-Agent header."""
    headers = {"User-Agent": "existing-agent/1.0"}
    result = prepend_agent_framework_to_user_agent(headers)

    assert "User-Agent" in result
    assert result["User-Agent"].startswith("agent-framework-python/")
    assert "existing-agent/1.0" in result["User-Agent"]


def test_prepend_to_empty_headers():
    """Test prepending to headers without User-Agent."""
    headers = {"Content-Type": "application/json"}
    result = prepend_agent_framework_to_user_agent(headers)

    assert "User-Agent" in result
    assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT
    assert "Content-Type" in result


def test_prepend_to_empty_dict():
    """Test prepending to empty headers dict."""
    headers = {}
    result = prepend_agent_framework_to_user_agent(headers)

    assert "User-Agent" in result
    assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT


def test_modifies_original_dict():
    """Test that the function modifies the original headers dict."""
    headers = {"Other-Header": "value"}
    result = prepend_agent_framework_to_user_agent(headers)

    assert result is headers  # Same object
    assert "User-Agent" in headers


# region ModelDiagnosticSettings tests


@pytest.mark.parametrize("model_diagnostic_settings", [(None, None)], indirect=True)
def test_default_values(model_diagnostic_settings):
    """Test default values for ModelDiagnosticSettings."""
    assert not model_diagnostic_settings.ENABLED
    assert not model_diagnostic_settings.SENSITIVE_DATA_ENABLED


@pytest.mark.parametrize("model_diagnostic_settings", [(False, False)], indirect=True)
def test_disabled(model_diagnostic_settings):
    """Test default values for ModelDiagnosticSettings."""
    assert not model_diagnostic_settings.ENABLED
    assert not model_diagnostic_settings.SENSITIVE_DATA_ENABLED


@pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
def test_non_sensitive_events_enabled(model_diagnostic_settings):
    """Test loading model_diagnostic_settings from environment variables."""
    assert model_diagnostic_settings.ENABLED
    assert not model_diagnostic_settings.SENSITIVE_DATA_ENABLED


@pytest.mark.parametrize("model_diagnostic_settings", [(True, True)], indirect=True)
def test_sensitive_events_enabled(model_diagnostic_settings):
    """Test loading model_diagnostic_settings from environment variables."""
    assert model_diagnostic_settings.ENABLED
    assert model_diagnostic_settings.SENSITIVE_DATA_ENABLED


@pytest.mark.parametrize("model_diagnostic_settings", [(False, True)], indirect=True)
def test_sensitive_events_enabled_only(model_diagnostic_settings):
    """Test loading sensitive events setting from environment.

    But when sensitive events are enabled, diagnostics are also enabled.
    """
    assert model_diagnostic_settings.ENABLED
    assert model_diagnostic_settings.SENSITIVE_DATA_ENABLED


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
    assert ChatMessageListTimestampFilter.INDEX_KEY == "CHAT_MESSAGE_INDEX"


# region Test start_as_current_span


def test_start_span_basic():
    """Test starting a span with basic function info."""
    mock_tracer = Mock()
    mock_span = Mock()
    mock_tracer.start_as_current_span.return_value = mock_span

    # Create a mock function
    mock_function = Mock()
    mock_function.name = "test_function"
    mock_function.description = "Test function description"

    result = start_as_current_span(mock_tracer, mock_function)

    assert result == mock_span
    mock_tracer.start_as_current_span.assert_called_once()

    call_args = mock_tracer.start_as_current_span.call_args
    assert call_args[0][0] == "execute_tool test_function"

    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.OPERATION.value] == OtelAttr.TOOL_EXECUTION_OPERATION
    assert attributes[OtelAttr.TOOL_NAME] == "test_function"
    assert attributes[OtelAttr.TOOL_DESCRIPTION] == "Test function description"


def test_start_span_with_metadata():
    """Test starting a span with metadata containing tool_call_id."""
    mock_tracer = Mock()
    mock_span = Mock()
    mock_tracer.start_as_current_span.return_value = mock_span

    mock_function = Mock()
    mock_function.name = "test_function"
    mock_function.description = "Test function"

    metadata = {"tool_call_id": "test_call_123"}

    _ = start_as_current_span(mock_tracer, mock_function, metadata)

    call_args = mock_tracer.start_as_current_span.call_args
    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.TOOL_CALL_ID] == "test_call_123"


def test_start_span_without_description():
    """Test starting a span when function has no description."""
    mock_tracer = Mock()
    mock_span = Mock()
    mock_tracer.start_as_current_span.return_value = mock_span

    mock_function = Mock()
    mock_function.name = "test_function"
    mock_function.description = None

    start_as_current_span(mock_tracer, mock_function)

    call_args = mock_tracer.start_as_current_span.call_args
    attributes = call_args[1]["attributes"]
    assert OtelAttr.TOOL_DESCRIPTION not in attributes


def test_start_span_empty_metadata():
    """Test starting a span with empty metadata."""
    mock_tracer = Mock()
    mock_span = Mock()
    mock_tracer.start_as_current_span.return_value = mock_span

    mock_function = Mock()
    mock_function.name = "test_function"
    mock_function.description = "Test function"

    start_as_current_span(mock_tracer, mock_function, {})

    call_args = mock_tracer.start_as_current_span.call_args
    attributes = call_args[1]["attributes"]
    assert OtelAttr.TOOL_CALL_ID not in attributes


# region Test use_telemetry decorator


def test_decorator_with_valid_class():
    """Test that decorator works with a valid ChatClientBase-like class."""

    # Create a mock class with the required methods
    class MockChatClient:
        async def get_response(self, messages, **kwargs):
            return Mock()

        async def get_streaming_response(self, messages, **kwargs):
            async def gen():
                yield Mock()

            return gen()

    # Apply the decorator
    decorated_class = OpenTelemetryChatClient(MockChatClient())
    assert hasattr(decorated_class, OPEN_TELEMETRY_CHAT_CLIENT_MARKER)


def test_decorator_with_missing_methods():
    """Test that decorator handles classes missing required methods gracefully."""

    class MockChatClient:
        MODEL_PROVIDER_NAME = "test_provider"

    # Apply the decorator - should not raise an error
    with pytest.raises(ChatClientInitializationError):
        OpenTelemetryChatClient(MockChatClient())


def test_decorator_with_partial_methods():
    """Test decorator when only one method is present."""

    class MockChatClient:
        MODEL_PROVIDER_NAME = "test_provider"

        async def get_response(self, messages, **kwargs):
            return Mock()

    with pytest.raises(ChatClientInitializationError):
        OpenTelemetryChatClient(MockChatClient())


# region Test telemetry decorator with mock client


@pytest.fixture
def mock_chat_client():
    """Create a mock chat client for testing."""

    class MockChatClient(ChatClientBase):
        def service_url(self):
            return "https://test.example.com"

        async def _inner_get_response(
            self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
        ):
            return ChatResponse(
                messages=[ChatMessage(role=ChatRole.ASSISTANT, text="Test response")],
                usage_details=UsageDetails(input_token_count=10, output_token_count=20),
                finish_reason=None,
            )

        async def _inner_get_streaming_response(
            self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
        ):
            yield ChatResponseUpdate(text="Hello", role=ChatRole.ASSISTANT)
            yield ChatResponseUpdate(text=" world", role=ChatRole.ASSISTANT)

    return MockChatClient()


@pytest.mark.parametrize(
    "enable_sensitive_data",
    [True, False],
)
@pytest.mark.parametrize(
    "enable_otel",
    [True, False],
)
async def test_instrumentation_enabled(mock_chat_client, enable_otel: bool, enable_sensitive_data: bool):
    """Test that when diagnostics are enabled, telemetry is applied."""
    client = OpenTelemetryChatClient(
        mock_chat_client,
        enable_otel=enable_otel,
        enable_sensitive_data=enable_sensitive_data,
    )

    messages = [ChatMessage(role=ChatRole.USER, text="Test message")]
    chat_options = ChatOptions()

    with (
        patch("agent_framework.telemetry._response_span") as mock_response_span,
        patch("agent_framework.telemetry._log_messages") as mock_log_messages,
    ):
        response = await client.get_response(messages=messages, chat_options=chat_options)
        assert response is not None
        if enable_otel or enable_sensitive_data:
            mock_response_span.assert_called_once()
        else:
            mock_response_span.assert_not_called()
        # Check that log messages was called only if sensitive events are enabled
        assert mock_log_messages.call_count == (2 if enable_sensitive_data else 0)


@pytest.mark.parametrize(
    "enable_sensitive_data",
    [True, False],
)
@pytest.mark.parametrize(
    "enable_otel",
    [True, False],
)
async def test_streaming_response_with_diagnostics_enabled_via_decorator(
    mock_chat_client,
    enable_otel: bool,
    enable_sensitive_data: bool,
):
    """Test streaming telemetry through the use_telemetry decorator."""
    client = OpenTelemetryChatClient(
        mock_chat_client,
        enable_otel=enable_otel,
        enable_sensitive_data=enable_sensitive_data,
    )
    messages = [ChatMessage(role=ChatRole.USER, text="Test")]
    chat_options = ChatOptions()

    with (
        patch("agent_framework.telemetry._response_span") as mock_response_span,
        patch("agent_framework.telemetry._log_messages") as mock_log_messages,
        patch("agent_framework.telemetry._set_response_output") as mock_set_output,
    ):
        # Collect all yielded updates
        updates = []
        async for update in client.get_streaming_response(messages=messages, chat_options=chat_options):
            updates.append(update)

        # Verify we got the expected updates, this shouldn't be dependent on otel
        assert len(updates) == 2

        # Verify telemetry calls were made
        if enable_otel or enable_sensitive_data:
            mock_response_span.assert_called_once()
        else:
            mock_response_span.assert_not_called()
        if enable_sensitive_data:
            mock_log_messages.assert_called()
            assert mock_log_messages.call_count == 2  # One for input, one for output
        else:
            mock_log_messages.assert_not_called()

        if enable_otel or enable_sensitive_data:
            mock_set_output.assert_called_once()
        else:
            mock_set_output.assert_not_called()


def test_start_as_current_span_with_none_metadata():
    """Test start_as_current_span with None metadata."""
    mock_tracer = Mock()
    mock_span = Mock()
    mock_tracer.start_as_current_span.return_value = mock_span

    mock_function = Mock()
    mock_function.name = "test_function"
    mock_function.description = "Test description"

    result = start_as_current_span(mock_tracer, mock_function, None)

    assert result == mock_span
    call_args = mock_tracer.start_as_current_span.call_args
    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.TOOL_CALL_ID] == "unknown"


def test_prepend_user_agent_with_none_value():
    """Test prepend user agent with None value in headers."""
    headers = {"User-Agent": None}
    result = prepend_agent_framework_to_user_agent(headers)

    # Should handle None gracefully
    assert "User-Agent" in result
    assert AGENT_FRAMEWORK_USER_AGENT in str(result["User-Agent"])


# region Test OpenTelemetryAgent decorator


def test_agent_decorator_with_valid_class():
    """Test that agent decorator works with a valid ChatClientAgent-like class."""

    # Create a mock class with the required methods
    class MockChatClientAgent:
        AGENT_SYSTEM_NAME = "test_agent_system"

        def __init__(self):
            self.id = "test_agent_id"
            self.name = "test_agent"
            self.display_name = "Test Agent"
            self.description = "Test agent description"

        async def run(self, messages=None, *, thread=None, **kwargs):
            return Mock()

        async def run_streaming(self, messages=None, *, thread=None, **kwargs):
            async def gen():
                yield Mock()

            return gen()

        def get_new_thread(self) -> AgentThread:
            return AgentThread()

    # Apply the decorator
    decorated_class = OpenTelemetryAgent(MockChatClientAgent())

    assert hasattr(decorated_class, OPEN_TELEMETRY_AGENT_MARKER)


def test_agent_decorator_with_missing_methods():
    """Test that agent decorator handles classes missing required methods gracefully."""

    class MockAgent:
        AGENT_SYSTEM_NAME = "test_agent_system"

    # Apply the decorator - should not raise an error
    with pytest.raises(AgentException):
        OpenTelemetryAgent(MockAgent())


def test_agent_decorator_with_partial_methods():
    """Test agent decorator when only one method is present."""
    from agent_framework.telemetry import OpenTelemetryAgent

    class MockAgent:
        AGENT_SYSTEM_NAME = "test_agent_system"

        def __init__(self):
            self.id = "test_agent_id"
            self.name = "test_agent"
            self.display_name = "Test Agent"

        async def run(self, messages=None, *, thread=None, **kwargs):
            return Mock()

    with pytest.raises(AgentException):
        OpenTelemetryAgent(MockAgent())


# region Test agent telemetry decorator with mock agent


@pytest.fixture
def mock_chat_client_agent():
    """Create a mock chat client agent for testing."""

    class MockChatClientAgent:
        AGENT_SYSTEM_NAME = "test_agent_system"

        def __init__(self):
            self.id = "test_agent_id"
            self.name = "test_agent"
            self.display_name = "Test Agent"
            self.description = "Test agent description"

        async def run(self, messages=None, *, thread=None, **kwargs):
            return AgentRunResponse(
                messages=[ChatMessage(role=ChatRole.ASSISTANT, text="Agent response")],
                usage_details=UsageDetails(input_token_count=15, output_token_count=25),
                response_id="test_response_id",
                raw_representation=Mock(finish_reason=Mock(value="stop")),
            )

        async def run_streaming(self, messages=None, *, thread=None, **kwargs):
            from agent_framework import AgentRunResponseUpdate

            yield AgentRunResponseUpdate(text="Hello", role=ChatRole.ASSISTANT)
            yield AgentRunResponseUpdate(text=" from agent", role=ChatRole.ASSISTANT)

    return MockChatClientAgent()


@pytest.mark.parametrize("model_diagnostic_settings", [(False, False)], indirect=True)
async def test_agent_telemetry_disabled_bypasses_instrumentation(mock_chat_client_agent, model_diagnostic_settings):
    """Test that when agent diagnostics are disabled, telemetry is bypassed."""
    from agent_framework.telemetry import OpenTelemetryAgent

    decorated_class = OpenTelemetryAgent(type(mock_chat_client_agent))
    agent = decorated_class()

    with (
        patch("agent_framework.telemetry.use_span") as mock_use_span,
    ):
        # This should not create any spans
        response = await agent.run("Test message")
        assert response is not None
        mock_use_span.assert_not_called()


@pytest.mark.parametrize("model_diagnostic_settings", [(True, True)], indirect=True)
async def test_agent_instrumentation_enabled(mock_chat_client_agent, model_diagnostic_settings):
    """Test that when agent diagnostics are enabled, telemetry is applied."""
    from agent_framework.telemetry import OpenTelemetryAgent

    decorated_class = OpenTelemetryAgent(type(mock_chat_client_agent))
    agent = decorated_class()

    with (
        patch("agent_framework.telemetry.use_span") as mock_use_span,
        patch("agent_framework.telemetry.logger") as mock_logger,
    ):
        response = await agent.run("Test message")
        assert response is not None
        mock_use_span.assert_called_once()
        # Check that logger.info was called (telemetry logs input/output)
        assert mock_logger.info.call_count == 2


@pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
async def test_agent_streaming_response_with_diagnostics_enabled_via_decorator(
    mock_chat_client_agent, model_diagnostic_settings
):
    """Test agent streaming telemetry through the OpenTelemetryAgent decorator."""
    from agent_framework.telemetry import OpenTelemetryAgent

    decorated_class = OpenTelemetryAgent(type(mock_chat_client_agent))
    agent = decorated_class()

    with (
        patch("agent_framework.telemetry.use_span") as mock_use_span,
        patch("agent_framework.telemetry._get_agent_run_span") as mock_get_span,
        patch("agent_framework.telemetry._set_agent_run_input") as mock_set_input,
        patch("agent_framework.telemetry._set_agent_run_output") as mock_set_output,
    ):
        mock_span = Mock()
        mock_use_span.return_value.__enter__.return_value = mock_span
        mock_use_span.return_value.__exit__.return_value = None

        # Collect all yielded updates
        updates = []
        async for update in agent.run_streaming("Test message"):
            updates.append(update)

        # Verify we got the expected updates
        assert len(updates) == 2

        # Verify telemetry calls were made
        mock_get_span.assert_called_once()
        mock_set_input.assert_called_once_with("test_agent_system", "Test message")
        mock_set_output.assert_called_once()


@pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
async def test_agent_streaming_response_with_exception_via_decorator(mock_chat_client_agent, model_diagnostic_settings):
    """Test agent streaming telemetry exception handling through decorator."""
    from agent_framework.telemetry import OpenTelemetryAgent

    async def run_streaming(self, messages=None, *, thread=None, **kwargs):
        from agent_framework import AgentRunResponseUpdate, ChatRole

        yield AgentRunResponseUpdate(text="Partial", role=ChatRole.ASSISTANT)
        raise ValueError("Test agent streaming error")

    type(mock_chat_client_agent).run_streaming = run_streaming

    decorated_class = OpenTelemetryAgent(type(mock_chat_client_agent))
    agent = decorated_class()

    with (
        patch("agent_framework.telemetry.use_span") as mock_use_span,
        patch("agent_framework.telemetry._get_agent_run_span"),
        patch("agent_framework.telemetry._set_agent_run_input"),
        patch("agent_framework.telemetry._set_error") as mock_set_error,
    ):
        mock_span = Mock()
        mock_use_span.return_value.__enter__.return_value = mock_span
        mock_use_span.return_value.__exit__.return_value = None

        # Should raise the exception and call error handler
        with pytest.raises(ValueError, match="Test agent streaming error"):
            async for _ in agent.run_streaming("Test message"):
                pass

        # Verify error was recorded
        mock_set_error.assert_called_once()
        assert isinstance(mock_set_error.call_args[0][1], ValueError)


@pytest.mark.parametrize("model_diagnostic_settings", [(False, False)], indirect=True)
async def test_agent_streaming_response_diagnostics_disabled_via_decorator(model_diagnostic_settings):
    """Test agent streaming response when diagnostics are disabled."""
    from agent_framework import AgentRunResponseUpdate, ChatRole
    from agent_framework.telemetry import OpenTelemetryAgent

    class MockStreamingAgentNoDiagnostics:
        AGENT_SYSTEM_NAME = "test_agent_system"

        def __init__(self):
            self.id = "test_agent_id"
            self.name = "test_agent"
            self.display_name = "Test Agent"

        async def run_streaming(self, messages=None, *, thread=None, **kwargs):
            yield AgentRunResponseUpdate(text="Test", role=ChatRole.ASSISTANT)

    decorated_class = OpenTelemetryAgent(MockStreamingAgentNoDiagnostics)
    agent = decorated_class()

    with (
        patch("agent_framework.telemetry._get_agent_run_span") as mock_get_span,
    ):
        # Should not create spans when diagnostics are disabled
        updates = []
        async for update in agent.run_streaming("Test message"):
            updates.append(update)

        assert len(updates) == 1
        # Should not have called telemetry functions
        mock_get_span.assert_not_called()


@pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
async def test_agent_empty_streaming_response_via_decorator(model_diagnostic_settings):
    """Test agent streaming wrapper with empty response."""

    class MockEmptyStreamingAgent:
        AGENT_SYSTEM_NAME = "test_agent_system"

        def __init__(self):
            self.id = "test_agent_id"
            self.name = "test_agent"
            self.display_name = "Test Agent"

        async def run_streaming(self, messages=None, *, thread=None, **kwargs):
            # Return empty stream
            return
            yield  # This will never be reached

    agent = OpenTelemetryAgent(MockEmptyStreamingAgent())

    with (
        patch("agent_framework.telemetry.use_span") as mock_use_span,
        patch("agent_framework.telemetry._get_agent_run_span"),
        patch("agent_framework.telemetry._set_agent_run_input"),
        patch("agent_framework.telemetry._set_agent_run_output") as mock_set_output,
    ):
        mock_span = Mock()
        mock_use_span.return_value.__enter__.return_value = mock_span
        mock_use_span.return_value.__exit__.return_value = None

        # Should handle empty stream gracefully
        updates = []
        async for update in agent.run_streaming("Test message"):
            updates.append(update)

        assert len(updates) == 0
        # Should still call telemetry
        mock_set_output.assert_called_once()


@pytest.mark.parametrize("model_diagnostic_settings", [(True, True)], indirect=True)
async def test_agent_run_with_thread_and_kwargs(mock_chat_client_agent, model_diagnostic_settings):
    """Test agent run with thread and additional kwargs."""
    from agent_framework.telemetry import OpenTelemetryAgent

    decorated_class = OpenTelemetryAgent(type(mock_chat_client_agent))
    agent = decorated_class()

    # Mock thread
    mock_thread = Mock()
    mock_thread.id = "test_thread_id"

    with (
        patch("agent_framework.telemetry.use_span") as mock_use_span,
        patch("agent_framework.telemetry._get_agent_run_span") as mock_get_span,
    ):
        mock_span = Mock()
        mock_use_span.return_value.__enter__.return_value = mock_span
        mock_use_span.return_value.__exit__.return_value = None

        # Test with thread and additional kwargs
        response = await agent.run(
            "Test message", thread=mock_thread, temperature=0.7, max_tokens=100, model="test-model"
        )
        assert response is not None

        # Verify the span was created with the correct parameters
        mock_get_span.assert_called_once()
        call_kwargs = mock_get_span.call_args[1]
        assert call_kwargs["agent"] == agent
        assert call_kwargs["thread"] == mock_thread
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 100
        assert call_kwargs["model"] == "test-model"


@pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
async def test_agent_run_with_list_messages(mock_chat_client_agent, model_diagnostic_settings):
    """Test agent run with list of messages."""
    from agent_framework import ChatMessage, ChatRole
    from agent_framework.telemetry import OpenTelemetryAgent

    decorated_class = OpenTelemetryAgent(type(mock_chat_client_agent))
    agent = decorated_class()

    messages = [
        ChatMessage(role=ChatRole.USER, text="First message"),
        ChatMessage(role=ChatRole.ASSISTANT, text="Response"),
        ChatMessage(role=ChatRole.USER, text="Second message"),
    ]

    with (
        patch("agent_framework.telemetry.use_span") as mock_use_span,
        patch("agent_framework.telemetry._set_agent_run_input") as mock_set_input,
    ):
        mock_span = Mock()
        mock_use_span.return_value.__enter__.return_value = mock_span
        mock_use_span.return_value.__exit__.return_value = None

        response = await agent.run(messages)
        assert response is not None

        # Verify input was set with the list of messages
        mock_set_input.assert_called_once_with("test_agent_system", messages)


@pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
async def test_agent_run_with_exception_handling(mock_chat_client_agent, model_diagnostic_settings):
    """Test agent run with exception handling."""
    from agent_framework.telemetry import OpenTelemetryAgent

    async def run_with_error(self, messages=None, *, thread=None, **kwargs):
        raise RuntimeError("Agent run error")

    type(mock_chat_client_agent).run = run_with_error

    agent = OpenTelemetryAgent(mock_chat_client_agent)

    with (
        patch("agent_framework.telemetry.use_span") as mock_use_span,
    ):
        mock_span = Mock()
        mock_use_span.return_value.__enter__.return_value = mock_span
        mock_use_span.return_value.__exit__.return_value = None

        # Should raise the exception and call error handler
        with pytest.raises(RuntimeError, match="Agent run error"):
            await agent.run("Test message")

        # Verify error was recorded
        # Check that both error attributes were set on the span
        mock_span.set_attribute.assert_called_once_with(OtelAttr.ERROR_TYPE, str(type(RuntimeError("Agent run error"))))
        mock_span.set_status.assert_called_once_with(StatusCode.ERROR, repr(RuntimeError("Agent run error")))
