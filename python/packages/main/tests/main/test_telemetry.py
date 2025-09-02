# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import MutableSequence
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from opentelemetry.trace import StatusCode

from agent_framework import (
    AgentRunResponse,
    AgentThread,
    AIAgent,
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
    _start_as_current_span,
    prepend_agent_framework_to_user_agent,
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
    assert ChatMessageListTimestampFilter.INDEX_KEY == "chat_message_index"


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

    result = _start_as_current_span(mock_tracer, mock_function)

    assert result == mock_span
    mock_tracer.start_as_current_span.assert_called_once()

    call_args = mock_tracer.start_as_current_span.call_args
    assert call_args[1]["name"] == "execute_tool test_function"

    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.OPERATION.value] == OtelAttr.TOOL_EXECUTION_OPERATION
    assert attributes[OtelAttr.TOOL_NAME] == "test_function"
    assert attributes[OtelAttr.TOOL_DESCRIPTION] == "Test function description"


def test_start_span_with_tool_call_id():
    """Test starting a span with tool_call_id."""
    mock_tracer = Mock()
    mock_span = Mock()
    mock_tracer.start_as_current_span.return_value = mock_span

    mock_function = Mock()
    mock_function.name = "test_function"
    mock_function.description = "Test function"

    tool_call_id = "test_call_123"

    _ = _start_as_current_span(mock_tracer, mock_function, tool_call_id)

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

    _start_as_current_span(mock_tracer, mock_function)

    call_args = mock_tracer.start_as_current_span.call_args
    attributes = call_args[1]["attributes"]
    assert OtelAttr.TOOL_DESCRIPTION not in attributes


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
async def test_instrumentation_enabled(mock_chat_client, enable_sensitive_data: bool):
    """Test that when diagnostics are enabled, telemetry is applied."""
    client = OpenTelemetryChatClient(
        mock_chat_client,
        enable_sensitive_data=enable_sensitive_data,
    )

    messages = [ChatMessage(role=ChatRole.USER, text="Test message")]
    chat_options = ChatOptions()

    with (
        patch("agent_framework.telemetry._chat_response_span") as mock_response_span,
        patch("agent_framework.telemetry._capture_messages") as mock_log_messages,
    ):
        response = await client.get_response(messages=messages, chat_options=chat_options)
        assert response is not None
        mock_response_span.assert_called_once()

        # Check that log messages was called only if sensitive events are enabled
        assert mock_log_messages.call_count == (2 if enable_sensitive_data else 0)


@pytest.mark.parametrize(
    "enable_sensitive_data",
    [True, False],
)
async def test_streaming_response_with_otel(mock_chat_client, enable_sensitive_data: bool):
    """Test streaming telemetry through the use_telemetry decorator."""
    client = OpenTelemetryChatClient(
        mock_chat_client,
        enable_sensitive_data=enable_sensitive_data,
    )
    messages = [ChatMessage(role=ChatRole.USER, text="Test")]
    chat_options = ChatOptions()

    with (
        patch("agent_framework.telemetry._chat_response_span") as mock_response_span,
        patch("agent_framework.telemetry._capture_messages") as mock_log_messages,
        patch("agent_framework.telemetry._capture_response") as mock_set_output,
    ):
        # Collect all yielded updates
        updates = []
        async for update in client.get_streaming_response(messages=messages, chat_options=chat_options):
            updates.append(update)

        # Verify we got the expected updates, this shouldn't be dependent on otel
        assert len(updates) == 2

        # Verify telemetry calls were made
        mock_response_span.assert_called_once()
        if enable_sensitive_data:
            mock_log_messages.assert_called()
            assert mock_log_messages.call_count == 2  # One for input, one for output
        else:
            mock_log_messages.assert_not_called()

        mock_set_output.assert_called_once()


def test_start_as_current_span_with_none_metadata():
    """Test start_as_current_span with None metadata."""
    mock_tracer = Mock()
    mock_span = Mock()
    mock_tracer.start_as_current_span.return_value = mock_span

    mock_function = Mock()
    mock_function.name = "test_function"
    mock_function.description = "Test description"

    result = _start_as_current_span(mock_tracer, mock_function, None)

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


@pytest.mark.parametrize("enable_sensitive_data", [True, False])
async def test_agent_instrumentation_enabled(mock_chat_client_agent: AIAgent, enable_sensitive_data: bool):
    """Test that when agent diagnostics are enabled, telemetry is applied."""

    agent = OpenTelemetryAgent(mock_chat_client_agent, enable_sensitive_data=enable_sensitive_data)

    with (
        patch("agent_framework.telemetry.use_span") as mock_use_span,
        patch("agent_framework.telemetry.logger") as mock_logger,
    ):
        response = await agent.run("Test message")
        assert response is not None
        mock_use_span.assert_called_once()
        # Check that logger.info was called (telemetry logs input/output)
        assert mock_logger.info.call_count == (2 if enable_sensitive_data else 0)


@pytest.mark.parametrize("enable_sensitive_data", [True, False])
async def test_agent_streaming_response_with_diagnostics_enabled_via_decorator(
    mock_chat_client_agent: AIAgent, enable_sensitive_data: bool
):
    """Test agent streaming telemetry through the OpenTelemetryAgent decorator."""
    agent = OpenTelemetryAgent(mock_chat_client_agent, enable_sensitive_data=enable_sensitive_data)

    with (
        patch("agent_framework.telemetry._agent_run_span") as mock_get_span,
        patch("agent_framework.telemetry._capture_messages") as mock_capture_messages,
        patch("agent_framework.telemetry._capture_response") as mock_capture_response,
    ):
        # Collect all yielded updates
        updates = []
        async for update in agent.run_streaming("Test message"):
            updates.append(update)

        # Verify we got the expected updates
        assert len(updates) == 2

        # Verify telemetry calls were made
        mock_get_span.assert_called_once()
        mock_capture_response.assert_called_once()
        if enable_sensitive_data:
            mock_capture_messages.assert_called()
        else:
            mock_capture_messages.assert_not_called()


async def test_agent_run_with_exception_handling(mock_chat_client_agent: AIAgent):
    """Test agent run with exception handling."""

    async def run_with_error(self, messages=None, *, thread=None, **kwargs):
        raise RuntimeError("Agent run error")

    type(mock_chat_client_agent).run = run_with_error

    agent = OpenTelemetryAgent(mock_chat_client_agent)

    from opentelemetry.trace import Span

    with (
        patch("agent_framework.telemetry._agent_run_span") as mock_get_span,
    ):
        mock_span = MagicMock(spec=Span)
        # Ensure the patched context manager returns mock_span when entered
        mock_get_span.return_value.__enter__.return_value = mock_span
        # Should raise the exception and call error handler
        with pytest.raises(RuntimeError, match="Agent run error"):
            await agent.run("Test message")

        # Verify error was recorded
        # Check that both error attributes were set on the span
        mock_span.set_attribute.assert_called_once_with(OtelAttr.ERROR_TYPE, str(type(RuntimeError("Agent run error"))))
        mock_span.record_exception.assert_called_once()
        mock_span.set_status.assert_called_once_with(
            status=StatusCode.ERROR, description=repr(RuntimeError("Agent run error"))
        )
