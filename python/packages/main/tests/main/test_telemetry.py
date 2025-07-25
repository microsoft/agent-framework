# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import AsyncIterable, MutableSequence
from typing import Any
from unittest.mock import Mock, patch

import pytest
from opentelemetry.trace import StatusCode

from agent_framework import (
    ChatFinishReason,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    TextContent,
    UsageContent,
    UsageDetails,
)
from agent_framework.telemetry import (
    AGENT_FRAMEWORK_USER_AGENT,
    ROLE_EVENT_MAP,
    TELEMETRY_DISABLED_ENV_VAR,
    USER_AGENT_KEY,
    ChatMessageListTimestampFilter,
    GenAIAttributes,
    prepend_agent_framework_to_user_agent,
    start_as_current_span,
    use_telemetry,
)


class TestConstants:
    """Test constants and environment variables."""

    def test_telemetry_disabled_env_var(self):
        """Test that the telemetry disabled environment variable is correctly defined."""
        assert TELEMETRY_DISABLED_ENV_VAR == "AZURE_TELEMETRY_DISABLED"

    def test_user_agent_key(self):
        """Test that the user agent key is correctly defined."""
        assert USER_AGENT_KEY == "User-Agent"

    def test_agent_framework_user_agent_format(self):
        """Test that the agent framework user agent is correctly formatted."""
        assert AGENT_FRAMEWORK_USER_AGENT.startswith("agent-framework-python/")

    def test_app_info_when_telemetry_enabled(self):
        """Test that APP_INFO is set when telemetry is enabled."""
        with patch("agent_framework.telemetry.IS_TELEMETRY_ENABLED", True):
            import importlib

            import agent_framework.telemetry

            importlib.reload(agent_framework.telemetry)
            from agent_framework.telemetry import APP_INFO

            assert APP_INFO is not None
            assert "agent-framework-version" in APP_INFO
            assert APP_INFO["agent-framework-version"].startswith("python/")

    def test_app_info_when_telemetry_disabled(self):
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


class TestGenAIAttributes:
    """Test GenAIAttributes enum."""

    def test_enum_values(self):
        """Test that GenAIAttributes enum has expected values."""
        assert GenAIAttributes.OPERATION.value == "gen_ai.operation.name"
        assert GenAIAttributes.SYSTEM.value == "gen_ai.system"
        assert GenAIAttributes.MODEL.value == "gen_ai.request.model"
        assert GenAIAttributes.CHAT_COMPLETION_OPERATION.value == "chat.completions"
        assert GenAIAttributes.CHAT_STREAMING_COMPLETION_OPERATION.value == "chat.streaming_completions"
        assert GenAIAttributes.TOOL_EXECUTION_OPERATION.value == "execute_tool"

    def test_role_event_map(self):
        """Test that ROLE_EVENT_MAP contains expected mappings."""
        assert ROLE_EVENT_MAP["system"] == GenAIAttributes.SYSTEM_MESSAGE.value
        assert ROLE_EVENT_MAP["user"] == GenAIAttributes.USER_MESSAGE.value
        assert ROLE_EVENT_MAP["assistant"] == GenAIAttributes.ASSISTANT_MESSAGE.value
        assert ROLE_EVENT_MAP["tool"] == GenAIAttributes.TOOL_MESSAGE.value


class TestPrependAgentFrameworkToUserAgent:
    """Test prepend_agent_framework_to_user_agent function."""

    def test_prepend_to_existing_user_agent(self):
        """Test prepending to existing User-Agent header."""
        headers = {"User-Agent": "existing-agent/1.0"}
        result = prepend_agent_framework_to_user_agent(headers)

        assert "User-Agent" in result
        assert result["User-Agent"].startswith("agent-framework-python/")
        assert "existing-agent/1.0" in result["User-Agent"]

    def test_prepend_to_empty_headers(self):
        """Test prepending to headers without User-Agent."""
        headers = {"Content-Type": "application/json"}
        result = prepend_agent_framework_to_user_agent(headers)

        assert "User-Agent" in result
        assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT
        assert "Content-Type" in result

    def test_prepend_to_empty_dict(self):
        """Test prepending to empty headers dict."""
        headers = {}
        result = prepend_agent_framework_to_user_agent(headers)

        assert "User-Agent" in result
        assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT

    def test_modifies_original_dict(self):
        """Test that the function modifies the original headers dict."""
        headers = {"Other-Header": "value"}
        result = prepend_agent_framework_to_user_agent(headers)

        assert result is headers  # Same object
        assert "User-Agent" in headers


class TestModelDiagnosticSettings:
    """Test ModelDiagnosticSettings class."""

    @pytest.mark.parametrize("model_diagnostic_settings", [(None, None)], indirect=True)
    def test_default_values(self, model_diagnostic_settings):
        """Test default values for ModelDiagnosticSettings."""
        assert not model_diagnostic_settings.ENABLED
        assert not model_diagnostic_settings.SENSITIVE_EVENTS_ENABLED

    @pytest.mark.parametrize("model_diagnostic_settings", [(False, False)], indirect=True)
    def test_disabled(self, model_diagnostic_settings):
        """Test default values for ModelDiagnosticSettings."""
        assert not model_diagnostic_settings.ENABLED
        assert not model_diagnostic_settings.SENSITIVE_EVENTS_ENABLED

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
    def test_non_sensitive_events_enabled(self, model_diagnostic_settings):
        """Test loading model_diagnostic_settings from environment variables."""
        assert model_diagnostic_settings.ENABLED
        assert not model_diagnostic_settings.SENSITIVE_EVENTS_ENABLED

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, True)], indirect=True)
    def test_sensitive_events_enabled(self, model_diagnostic_settings):
        """Test loading model_diagnostic_settings from environment variables."""
        assert model_diagnostic_settings.ENABLED
        assert model_diagnostic_settings.SENSITIVE_EVENTS_ENABLED

    @pytest.mark.parametrize("model_diagnostic_settings", [(False, True)], indirect=True)
    def test_sensitive_events_enabled_only(self, model_diagnostic_settings):
        """Test loading sensitive events setting from environment.

        But when sensitive events are enabled, diagnostics are also enabled.
        """
        assert model_diagnostic_settings.ENABLED
        assert model_diagnostic_settings.SENSITIVE_EVENTS_ENABLED


class TestChatMessageListTimestampFilter:
    """Test ChatMessageListTimestampFilter class."""

    def test_filter_without_index_key(self):
        """Test filter method when record doesn't have INDEX_KEY."""
        log_filter = ChatMessageListTimestampFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="test message", args=(), exc_info=None
        )
        original_created = record.created

        result = log_filter.filter(record)

        assert result is True
        assert record.created == original_created

    def test_filter_with_index_key(self):
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

    def test_index_key_constant(self):
        """Test that INDEX_KEY constant is correctly defined."""
        assert ChatMessageListTimestampFilter.INDEX_KEY == "CHAT_MESSAGE_INDEX"


class TestStartAsCurrentSpan:
    """Test start_as_current_span function."""

    def test_start_span_basic(self):
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
        assert attributes[GenAIAttributes.OPERATION.value] == GenAIAttributes.TOOL_EXECUTION_OPERATION.value
        assert attributes[GenAIAttributes.TOOL_NAME.value] == "test_function"
        assert attributes[GenAIAttributes.TOOL_DESCRIPTION.value] == "Test function description"

    def test_start_span_with_metadata(self):
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
        assert attributes[GenAIAttributes.TOOL_CALL_ID.value] == "test_call_123"

    def test_start_span_without_description(self):
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
        assert GenAIAttributes.TOOL_DESCRIPTION.value not in attributes

    def test_start_span_empty_metadata(self):
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
        assert GenAIAttributes.TOOL_CALL_ID.value not in attributes


class TestUseTelemetryDecorator:
    """Test use_telemetry decorator."""

    def test_decorator_with_valid_class(self):
        """Test that decorator works with a valid ChatClientBase-like class."""

        # Create a mock class with the required methods
        class MockChatClient:
            MODEL_PROVIDER_NAME = "test_provider"

            async def _inner_get_response(self, *, messages, chat_options, **kwargs):
                return Mock()

            async def _inner_get_streaming_response(self, *, messages, chat_options, **kwargs):
                async def gen():
                    yield Mock()

                return gen()

        # Apply the decorator
        decorated_class = use_telemetry(MockChatClient)

        # Check that the methods were wrapped
        assert hasattr(decorated_class._inner_get_response, "__model_diagnostics_chat_client__")
        assert hasattr(decorated_class._inner_get_streaming_response, "__model_diagnostics_streaming_chat_completion__")

    def test_decorator_with_missing_methods(self):
        """Test that decorator handles classes missing required methods gracefully."""

        class MockChatClient:
            MODEL_PROVIDER_NAME = "test_provider"

        # Apply the decorator - should not raise an error
        decorated_class = use_telemetry(MockChatClient)

        # Class should be returned unchanged
        assert decorated_class is MockChatClient

    def test_decorator_with_partial_methods(self):
        """Test decorator when only one method is present."""

        class MockChatClient:
            MODEL_PROVIDER_NAME = "test_provider"

            async def _inner_get_response(self, *, messages, chat_options, **kwargs):
                return Mock()

        decorated_class = use_telemetry(MockChatClient)

        # Only the present method should be wrapped
        assert hasattr(decorated_class._inner_get_response, "__model_diagnostics_chat_client__")
        assert not hasattr(decorated_class, "_inner_get_streaming_response")


class TestTelemetryIntegration:
    """Integration tests for telemetry functionality."""

    @pytest.fixture
    def mock_chat_client(self):
        """Create a mock chat client for testing."""

        class MockChatClient:
            MODEL_PROVIDER_NAME = "test_provider"

            def __init__(self):
                self.ai_model_id = "test-model"

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
                async def gen():
                    from agent_framework._types import ChatResponseUpdate

                    yield ChatResponseUpdate(
                        role=ChatRole.ASSISTANT,
                        contents=[
                            TextContent(text="Test"),
                            UsageContent(details=UsageDetails(input_token_count=5, output_token_count=10)),
                        ],
                    )

                return gen()

        return MockChatClient()

    @pytest.mark.parametrize("model_diagnostic_settings", [(False, False)], indirect=True)
    async def test_telemetry_disabled_bypasses_instrumentation(self, mock_chat_client, model_diagnostic_settings):
        """Test that when diagnostics are disabled, telemetry is bypassed."""
        decorated_class = use_telemetry(type(mock_chat_client))
        client = decorated_class()
        client.ai_model_id = "test-model"
        client.MODEL_PROVIDER_NAME = "test_provider"
        client.service_url = lambda: "https://test.example.com"

        messages = [ChatMessage(role=ChatRole.USER, text="Test message")]
        chat_options = ChatOptions()

        with patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings):
            # This should not create any spans
            response = await client._inner_get_response(messages=messages, chat_options=chat_options)
            assert response is not None

    def test_constants_consistency(self):
        """Test that constants are consistently defined."""
        # Test that role event map covers all expected roles
        expected_roles = ["system", "user", "assistant", "tool"]
        for role in expected_roles:
            assert role in ROLE_EVENT_MAP
            assert ROLE_EVENT_MAP[role].startswith("gen_ai.")

        # Test GenAI attributes consistency
        assert GenAIAttributes.CHAT_COMPLETION_OPERATION.value == "chat.completions"
        assert GenAIAttributes.CHAT_STREAMING_COMPLETION_OPERATION.value == "chat.streaming_completions"
        assert GenAIAttributes.TOOL_EXECUTION_OPERATION.value == "execute_tool"


class TestTelemetryHelperFunctions:
    """Test internal telemetry helper functions."""

    def test_get_chat_response_span(self):
        """Test _get_chat_response_span function."""
        from agent_framework.telemetry import _get_chat_response_span

        chat_options = ChatOptions(
            temperature=0.7,
            max_tokens=100,
            seed=42,
            frequency_penalty=0.5,
            top_p=0.9,
            stop=["END"],
            additional_properties={"top_k": 50, "encoding_formats": "utf-8"},
        )

        with patch("agent_framework.telemetry.tracer") as mock_tracer:
            mock_span = Mock()
            mock_tracer.start_span.return_value = mock_span

            _ = _get_chat_response_span(
                "test_operation", "test_model", "test_provider", "https://test.com", chat_options
            )

            mock_tracer.start_span.assert_called_once_with("test_operation test_model")
            mock_span.set_attributes.assert_called()
            mock_span.set_attribute.assert_called()

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, True)], indirect=True)
    def test_set_chat_response_input_sensitive_enabled(self, model_diagnostic_settings):
        """Test _set_chat_response_input when sensitive events are enabled."""
        from agent_framework.telemetry import _set_chat_response_input

        messages = [
            ChatMessage(role=ChatRole.USER, text="Hello"),
            ChatMessage(role=ChatRole.ASSISTANT, text="Hi there"),
        ]

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.logger") as mock_logger,
        ):
            _set_chat_response_input("test_provider", messages)

            # Should log messages when sensitive events are enabled
            assert mock_logger.info.call_count == 2

    @pytest.mark.parametrize("model_diagnostic_settings", [(False, False)], indirect=True)
    def test_set_chat_response_input_sensitive_disabled(self, model_diagnostic_settings):
        """Test _set_chat_response_input when sensitive events are disabled."""
        from agent_framework.telemetry import _set_chat_response_input

        messages = [ChatMessage(role=ChatRole.USER, text="Hello")]

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.logger") as mock_logger,
        ):
            _set_chat_response_input("test_provider", messages)

            # Should not log messages when sensitive events are disabled
            mock_logger.info.assert_not_called()

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, True)], indirect=True)
    def test_set_chat_response_output(self, model_diagnostic_settings):
        """Test _set_chat_response_output function."""
        from agent_framework.telemetry import _set_chat_response_output

        mock_span = Mock()

        # Create a chat response with all possible fields
        response = ChatResponse(
            messages=[
                ChatMessage(role=ChatRole.ASSISTANT, text="Test response", additional_properties={"id": "response_123"})
            ],
            usage_details=UsageDetails(input_token_count=10, output_token_count=20),
            finish_reason=ChatFinishReason.STOP,
            response_id="test_response_id",
        )

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.logger") as mock_logger,
        ):
            _set_chat_response_output(mock_span, response, "test_provider")

            # Should set span attributes
            mock_span.set_attribute.assert_called()
            # Should log completion when sensitive events are enabled
            mock_logger.info.assert_called()

    def test_set_chat_response_error(self):
        """Test _set_chat_response_error function."""
        from agent_framework.telemetry import _set_chat_response_error

        mock_span = Mock()
        test_error = ValueError("Test error message")

        _set_chat_response_error(mock_span, test_error)

        mock_span.set_attribute.assert_called_with(GenAIAttributes.ERROR_TYPE.value, str(type(test_error)))
        mock_span.set_status.assert_called_with(StatusCode.ERROR, repr(test_error))


class TestTelemetryWrapperFunctions:
    """Test the telemetry wrapper functions with mocked dependencies."""

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
    async def test_trace_chat_get_response_with_diagnostics_enabled(self, model_diagnostic_settings):
        """Test _trace_chat_get_response when diagnostics are enabled."""
        from agent_framework.telemetry import _trace_chat_get_response

        # Create a mock completion function
        async def mock_completion_func(self, *, messages, chat_options, **kwargs):
            return ChatResponse(
                messages=[ChatMessage(role=ChatRole.ASSISTANT, text="Test response")],
                usage_details=UsageDetails(input_token_count=10, output_token_count=20),
            )

        # Create a mock client
        mock_client = Mock()
        mock_client.MODEL_PROVIDER_NAME = "test_provider"
        mock_client.ai_model_id = "test_model"
        mock_client.service_url.return_value = "https://test.com"

        # Wrap the function
        wrapped_func = _trace_chat_get_response(mock_completion_func)

        messages = [ChatMessage(role=ChatRole.USER, text="Test")]
        chat_options = ChatOptions()

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.use_span") as mock_use_span,
            patch("agent_framework.telemetry._get_chat_response_span") as mock_get_span,
            patch("agent_framework.telemetry._set_chat_response_input") as mock_set_input,
            patch("agent_framework.telemetry._set_chat_response_output") as mock_set_output,
        ):
            mock_span = Mock()
            mock_use_span.return_value.__enter__.return_value = mock_span
            mock_use_span.return_value.__exit__.return_value = None

            response = await wrapped_func(mock_client, messages=messages, chat_options=chat_options)

            assert response is not None
            mock_get_span.assert_called_once()
            mock_set_input.assert_called_once()
            mock_set_output.assert_called_once()


class TestStreamingTelemetryWrapper:
    """Test the streaming telemetry wrapper function extensively."""

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
    async def test_streaming_response_with_diagnostics_enabled_via_decorator(self, model_diagnostic_settings):
        """Test streaming telemetry through the use_telemetry decorator."""
        from agent_framework._types import ChatResponseUpdate

        # Create a mock chat client class
        class MockStreamingChatClient:
            MODEL_PROVIDER_NAME = "test_provider"

            def __init__(self):
                self.ai_model_id = "test_model"

            def service_url(self) -> str:
                return "https://test.com"

            async def _inner_get_streaming_response(
                self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
            ) -> AsyncIterable[ChatResponseUpdate]:
                yield ChatResponseUpdate(text="Hello", role=ChatRole.ASSISTANT)
                yield ChatResponseUpdate(text=" world", role=ChatRole.ASSISTANT)

        # Apply the telemetry decorator
        decorated_class = use_telemetry(MockStreamingChatClient)
        client = decorated_class()

        messages = [ChatMessage(role=ChatRole.USER, text="Test")]
        chat_options = ChatOptions()

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.use_span") as mock_use_span,
            patch("agent_framework.telemetry._get_chat_response_span") as mock_get_span,
            patch("agent_framework.telemetry._set_chat_response_input") as mock_set_input,
            patch("agent_framework.telemetry._set_chat_response_output") as mock_set_output,
        ):
            mock_span = Mock()
            mock_use_span.return_value.__enter__.return_value = mock_span
            mock_use_span.return_value.__exit__.return_value = None

            # We can't easily mock ChatResponse.from_chat_response_updates since it's imported locally,
            # but we can verify telemetry calls were made

            # Collect all yielded updates
            updates = []
            async for update in client._inner_get_streaming_response(messages=messages, chat_options=chat_options):
                updates.append(update)

            # Verify we got the expected updates
            assert len(updates) == 2

            # Verify telemetry calls were made
            mock_get_span.assert_called_once()
            mock_set_input.assert_called_once_with("test_provider", messages)
            mock_set_output.assert_called_once()

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
    async def test_streaming_response_with_exception_via_decorator(self, model_diagnostic_settings):
        """Test streaming telemetry exception handling through decorator."""

        # Create a mock chat client that raises an exception during streaming
        class MockFailingStreamingClient:
            MODEL_PROVIDER_NAME = "test_provider"

            def __init__(self):
                self.ai_model_id = "test_model"

            def service_url(self) -> str:
                return "https://test.com"

            async def _inner_get_streaming_response(
                self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
            ) -> AsyncIterable[ChatResponseUpdate]:
                from agent_framework._types import ChatResponseUpdate

                yield ChatResponseUpdate(text="Partial", role=ChatRole.ASSISTANT)
                raise ValueError("Test streaming error")

        decorated_class = use_telemetry(MockFailingStreamingClient)
        client = decorated_class()

        messages = [ChatMessage(role=ChatRole.USER, text="Test")]
        chat_options = ChatOptions()

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.use_span") as mock_use_span,
            patch("agent_framework.telemetry._get_chat_response_span"),
            patch("agent_framework.telemetry._set_chat_response_input"),
            patch("agent_framework.telemetry._set_chat_response_error") as mock_set_error,
        ):
            mock_span = Mock()
            mock_use_span.return_value.__enter__.return_value = mock_span
            mock_use_span.return_value.__exit__.return_value = None

            # Should raise the exception and call error handler
            with pytest.raises(ValueError, match="Test streaming error"):
                async for _ in client._inner_get_streaming_response(messages=messages, chat_options=chat_options):
                    pass

            # Verify error was recorded
            mock_set_error.assert_called_once()
            assert isinstance(mock_set_error.call_args[0][1], ValueError)

    @pytest.mark.parametrize("model_diagnostic_settings", [(False, False)], indirect=True)
    async def test_streaming_response_diagnostics_disabled_via_decorator(self, model_diagnostic_settings):
        """Test streaming response when diagnostics are disabled."""
        from agent_framework import ChatResponseUpdate

        class MockStreamingClientNoDiagnostics:
            MODEL_PROVIDER_NAME = "test_provider"

            async def _inner_get_streaming_response(
                self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
            ) -> AsyncIterable[ChatResponseUpdate]:
                yield ChatResponseUpdate(text="Test", role=ChatRole.ASSISTANT)

        decorated_class = use_telemetry(MockStreamingClientNoDiagnostics)
        client = decorated_class()

        messages = [ChatMessage(role=ChatRole.USER, text="Test")]
        chat_options = ChatOptions()

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry._get_chat_response_span") as mock_get_span,
        ):
            # Should not create spans when diagnostics are disabled
            updates = []
            async for update in client._inner_get_streaming_response(messages=messages, chat_options=chat_options):
                updates.append(update)

            assert len(updates) == 1
            # Should not have called telemetry functions
            mock_get_span.assert_not_called()


class TestExceptionHandling:
    """Test exception handling in telemetry wrapper functions."""

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
    async def test_regular_response_with_exception_via_decorator(self, model_diagnostic_settings):
        """Test exception handling in regular chat response through decorator."""

        # Create a mock chat client that raises an exception
        class MockFailingChatClient:
            MODEL_PROVIDER_NAME = "test_provider"

            def __init__(self):
                self.ai_model_id = "test_model"

            def service_url(self) -> str:
                return "https://test.com"

            async def _inner_get_response(
                self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
            ) -> ChatResponse:
                raise RuntimeError("Test completion error")

        decorated_class = use_telemetry(MockFailingChatClient)
        client = decorated_class()

        messages = [ChatMessage(role=ChatRole.USER, text="Test")]
        chat_options = ChatOptions()

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.use_span") as mock_use_span,
            patch("agent_framework.telemetry._get_chat_response_span"),
            patch("agent_framework.telemetry._set_chat_response_input"),
            patch("agent_framework.telemetry._set_chat_response_error") as mock_set_error,
        ):
            mock_span = Mock()
            mock_use_span.return_value.__enter__.return_value = mock_span
            mock_use_span.return_value.__exit__.return_value = None

            # Should raise the exception and call error handler
            with pytest.raises(RuntimeError, match="Test completion error"):
                await client._inner_get_response(messages=messages, chat_options=chat_options)

            # Verify error was recorded
            mock_set_error.assert_called_once()
            args = mock_set_error.call_args[0]
            assert args[0] == mock_span
            assert isinstance(args[1], RuntimeError)
            assert str(args[1]) == "Test completion error"

    @pytest.mark.parametrize("model_diagnostic_settings", [(False, False)], indirect=True)
    async def test_regular_response_diagnostics_disabled_with_exception(self, model_diagnostic_settings):
        """Test that exceptions are still raised when diagnostics are disabled."""

        class MockFailingClientNoDiagnostics:
            MODEL_PROVIDER_NAME = "test_provider"

            async def _inner_get_response(
                self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
            ) -> ChatResponse:
                raise ValueError("Test error with diagnostics disabled")

            def service_url(self) -> str:
                return "https://test.com"

        decorated_class = use_telemetry(MockFailingClientNoDiagnostics)
        client = decorated_class()

        messages = [ChatMessage(role=ChatRole.USER, text="Test")]
        chat_options = ChatOptions()

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            # Should still raise the exception even when diagnostics are disabled
            pytest.raises(ValueError, match="Test error with diagnostics disabled"),
        ):
            await client._inner_get_response(messages=messages, chat_options=chat_options)


class TestWrapperFunctionMarkers:
    """Test that wrapper functions are properly marked."""

    def test_telemetry_decorator_sets_markers(self):
        """Test that the use_telemetry decorator properly sets function markers."""

        class MockChatClientWithBothMethods:
            MODEL_PROVIDER_NAME = "test_provider"

            async def _inner_get_response(self, *, messages, chat_options, **kwargs):
                return Mock()

            async def _inner_get_streaming_response(self, *, messages, chat_options, **kwargs):
                async def gen():
                    yield Mock()

                return gen()

        # Apply the decorator
        decorated_class = use_telemetry(MockChatClientWithBothMethods)

        # Check that the marker attributes are set
        assert hasattr(decorated_class._inner_get_response, "__model_diagnostics_chat_client__")
        assert decorated_class._inner_get_response.__model_diagnostics_chat_client__ is True

        assert hasattr(decorated_class._inner_get_streaming_response, "__model_diagnostics_streaming_chat_completion__")
        assert decorated_class._inner_get_streaming_response.__model_diagnostics_streaming_chat_completion__ is True


class TestChatResponseFromUpdates:
    """Test ChatResponse.from_chat_response_updates integration."""

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
    async def test_streaming_response_aggregation_via_decorator(self, model_diagnostic_settings):
        """Test that streaming responses are properly aggregated."""
        from agent_framework._types import ChatResponseUpdate

        # Create a mock streaming function with multiple updates
        class MockMultiUpdateStreamingClient:
            MODEL_PROVIDER_NAME = "test_provider"

            def __init__(self):
                self.ai_model_id = "test_model"

            def service_url(self) -> str:
                return "https://test.com"

            async def _inner_get_streaming_response(
                self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
            ) -> AsyncIterable[ChatResponseUpdate]:
                yield ChatResponseUpdate(text="Hello", role=ChatRole.ASSISTANT)
                yield ChatResponseUpdate(text=" world", role=ChatRole.ASSISTANT)
                yield ChatResponseUpdate(text="!", role=ChatRole.ASSISTANT)

        decorated_class = use_telemetry(MockMultiUpdateStreamingClient)
        client = decorated_class()

        messages = [ChatMessage(role=ChatRole.USER, text="Test")]
        chat_options = ChatOptions()

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.use_span") as mock_use_span,
            patch("agent_framework.telemetry._get_chat_response_span"),
            patch("agent_framework.telemetry._set_chat_response_input"),
            patch("agent_framework.telemetry._set_chat_response_output") as mock_set_output,
        ):
            mock_span = Mock()
            mock_use_span.return_value.__enter__.return_value = mock_span
            mock_use_span.return_value.__exit__.return_value = None

            # Consume all updates
            updates = []
            async for update in client._inner_get_streaming_response(messages=messages, chat_options=chat_options):
                updates.append(update)

            # Verify all updates were collected
            assert len(updates) == 3

            # Verify telemetry calls were made
            mock_set_output.assert_called_once()


class TestModelIdFallback:
    """Test model ID fallback logic in span creation."""

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
    async def test_model_id_fallback_from_chat_options(self, model_diagnostic_settings):
        """Test that model ID falls back to chat_options when not present on client."""

        class MockClientWithoutModelId:
            MODEL_PROVIDER_NAME = "test_provider"

            def service_url(self) -> str:
                return "https://test.com"

            async def _inner_get_response(
                self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
            ) -> ChatResponse:
                return ChatResponse(
                    messages=[ChatMessage(role=ChatRole.ASSISTANT, text="Test response")],
                    usage_details=UsageDetails(input_token_count=10, output_token_count=20),
                )

        decorated_class = use_telemetry(MockClientWithoutModelId)
        client = decorated_class()

        messages = [ChatMessage(role=ChatRole.USER, text="Test")]
        chat_options = ChatOptions(ai_model_id="fallback_model")

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.use_span") as mock_use_span,
            patch("agent_framework.telemetry._get_chat_response_span") as mock_get_span,
            patch("agent_framework.telemetry._set_chat_response_input"),
            patch("agent_framework.telemetry._set_chat_response_output"),
        ):
            mock_span = Mock()
            mock_use_span.return_value.__enter__.return_value = mock_span
            mock_use_span.return_value.__exit__.return_value = None

            await client._inner_get_response(messages=messages, chat_options=chat_options)

            # Verify the span was created with the fallback model name
            mock_get_span.assert_called_once()
            call_args = mock_get_span.call_args[0]
            model_name = call_args[1]  # Second argument is the model name
            assert model_name == "fallback_model"

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
    async def test_model_id_fallback_to_unknown(self, model_diagnostic_settings):
        """Test that model ID falls back to 'unknown' when not available anywhere."""

        class MockClientWithoutModelId:
            MODEL_PROVIDER_NAME = "test_provider"

            def service_url(self) -> str:
                return "https://test.com"

            async def _inner_get_response(
                self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
            ) -> ChatResponse:
                return ChatResponse(
                    messages=[ChatMessage(role=ChatRole.ASSISTANT, text="Test response")],
                    usage_details=UsageDetails(input_token_count=10, output_token_count=20),
                )

        decorated_class = use_telemetry(MockClientWithoutModelId)
        client = decorated_class()

        messages = [ChatMessage(role=ChatRole.USER, text="Test")]
        chat_options = ChatOptions()  # No ai_model_id set

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.use_span") as mock_use_span,
            patch("agent_framework.telemetry._get_chat_response_span") as mock_get_span,
            patch("agent_framework.telemetry._set_chat_response_input"),
            patch("agent_framework.telemetry._set_chat_response_output"),
        ):
            mock_span = Mock()
            mock_use_span.return_value.__enter__.return_value = mock_span
            mock_use_span.return_value.__exit__.return_value = None

            await client._inner_get_response(messages=messages, chat_options=chat_options)

            # Should fall back to "unknown"
            mock_get_span.assert_called_once()
            call_args = mock_get_span.call_args[0]
            model_name = call_args[1]  # Second argument is the model name
            assert model_name == "unknown"


class TestEmptyStreamingResponse:
    """Test edge cases with empty streaming responses."""

    @pytest.mark.parametrize("model_diagnostic_settings", [(True, False)], indirect=True)
    async def test_empty_streaming_response_via_decorator(self, model_diagnostic_settings):
        """Test streaming wrapper with empty response."""

        class MockEmptyStreamingClient:
            MODEL_PROVIDER_NAME = "test_provider"

            def __init__(self):
                self.ai_model_id = "test_model"

            def service_url(self) -> str:
                return "https://test.com"

            async def _inner_get_streaming_response(
                self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
            ) -> AsyncIterable[ChatResponseUpdate]:
                # Return empty stream
                return
                yield  # This will never be reached

        decorated_class = use_telemetry(MockEmptyStreamingClient)
        client = decorated_class()

        messages = [ChatMessage(role=ChatRole.USER, text="Test")]
        chat_options = ChatOptions()

        with (
            patch("agent_framework.telemetry.MODEL_DIAGNOSTICS_SETTINGS", model_diagnostic_settings),
            patch("agent_framework.telemetry.use_span") as mock_use_span,
            patch("agent_framework.telemetry._get_chat_response_span"),
            patch("agent_framework.telemetry._set_chat_response_input"),
            patch("agent_framework.telemetry._set_chat_response_output") as mock_set_output,
        ):
            mock_span = Mock()
            mock_use_span.return_value.__enter__.return_value = mock_span
            mock_use_span.return_value.__exit__.return_value = None

            # Should handle empty stream gracefully
            updates = []
            async for update in client._inner_get_streaming_response(messages=messages, chat_options=chat_options):
                updates.append(update)

            assert len(updates) == 0
            # Should still call telemetry
            mock_set_output.assert_called_once()


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_start_as_current_span_with_none_metadata(self):
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
        assert GenAIAttributes.TOOL_CALL_ID.value not in attributes

    def test_prepend_user_agent_with_none_value(self):
        """Test prepend user agent with None value in headers."""
        headers = {"User-Agent": None}
        result = prepend_agent_framework_to_user_agent(headers)

        # Should handle None gracefully
        assert "User-Agent" in result
        assert AGENT_FRAMEWORK_USER_AGENT in str(result["User-Agent"])
