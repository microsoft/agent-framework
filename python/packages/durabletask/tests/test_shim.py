# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableAIAgent shim and DurableAgentProvider.

Focuses on critical message normalization, delegation, and protocol compliance.
Run with: pytest tests/test_shim.py -v
"""

from typing import Any
from unittest.mock import Mock

import pytest
from agent_framework import AgentProtocol, ChatMessage
from pydantic import BaseModel

from agent_framework_durabletask import DurableAgentThread
from agent_framework_durabletask._executors import DurableAgentExecutor
from agent_framework_durabletask._models import RunRequest
from agent_framework_durabletask._shim import DurableAgentProvider, DurableAIAgent


class ResponseFormatModel(BaseModel):
    """Test Pydantic model for response format testing."""

    result: str


@pytest.fixture
def mock_executor() -> Mock:
    """Create a mock executor for testing."""
    mock = Mock(spec=DurableAgentExecutor)
    mock.run_durable_agent = Mock(return_value=None)
    mock.get_new_thread = Mock(return_value=DurableAgentThread())

    # Mock get_run_request to create actual RunRequest objects
    def create_run_request(
        message: str,
        options: dict[str, Any] | None = None,
    ) -> RunRequest:
        import uuid

        opts = dict(options) if options else {}
        response_format = opts.pop("response_format", None)
        enable_tool_calls = opts.pop("enable_tool_calls", True)
        wait_for_response = opts.pop("wait_for_response", True)
        return RunRequest(
            message=message,
            correlation_id=str(uuid.uuid4()),
            response_format=response_format,
            enable_tool_calls=enable_tool_calls,
            wait_for_response=wait_for_response,
            options=opts,
        )

    mock.get_run_request = Mock(side_effect=create_run_request)
    return mock


@pytest.fixture
def test_agent(mock_executor: Mock) -> DurableAIAgent[Any]:
    """Create a test agent with mock executor."""
    return DurableAIAgent(mock_executor, "test_agent")


class TestDurableAIAgentMessageNormalization:
    """Test that DurableAIAgent properly normalizes various message input types."""

    def test_run_accepts_string_message(self, test_agent: DurableAIAgent[Any], mock_executor: Mock) -> None:
        """Verify run accepts and normalizes string messages."""
        test_agent.run("Hello, world!")

        mock_executor.run_durable_agent.assert_called_once()
        # Verify agent_name and run_request were passed correctly as kwargs
        _, kwargs = mock_executor.run_durable_agent.call_args
        assert kwargs["agent_name"] == "test_agent"
        assert kwargs["run_request"].message == "Hello, world!"

    def test_run_accepts_chat_message(self, test_agent: DurableAIAgent[Any], mock_executor: Mock) -> None:
        """Verify run accepts and normalizes ChatMessage objects."""
        chat_msg = ChatMessage(role="user", text="Test message")
        test_agent.run(chat_msg)

        mock_executor.run_durable_agent.assert_called_once()
        _, kwargs = mock_executor.run_durable_agent.call_args
        assert kwargs["run_request"].message == "Test message"

    def test_run_accepts_list_of_strings(self, test_agent: DurableAIAgent[Any], mock_executor: Mock) -> None:
        """Verify run accepts and joins list of strings."""
        test_agent.run(["First message", "Second message"])

        mock_executor.run_durable_agent.assert_called_once()
        _, kwargs = mock_executor.run_durable_agent.call_args
        assert kwargs["run_request"].message == "First message\nSecond message"

    def test_run_accepts_list_of_chat_messages(self, test_agent: DurableAIAgent[Any], mock_executor: Mock) -> None:
        """Verify run accepts and joins list of ChatMessage objects."""
        messages = [
            ChatMessage(role="user", text="Message 1"),
            ChatMessage(role="assistant", text="Message 2"),
        ]
        test_agent.run(messages)

        mock_executor.run_durable_agent.assert_called_once()
        _, kwargs = mock_executor.run_durable_agent.call_args
        assert kwargs["run_request"].message == "Message 1\nMessage 2"

    def test_run_handles_none_message(self, test_agent: DurableAIAgent[Any], mock_executor: Mock) -> None:
        """Verify run handles None message gracefully."""
        test_agent.run(None)

        mock_executor.run_durable_agent.assert_called_once()
        _, kwargs = mock_executor.run_durable_agent.call_args
        assert kwargs["run_request"].message == ""

    def test_run_handles_empty_list(self, test_agent: DurableAIAgent[Any], mock_executor: Mock) -> None:
        """Verify run handles empty list gracefully."""
        test_agent.run([])

        mock_executor.run_durable_agent.assert_called_once()
        _, kwargs = mock_executor.run_durable_agent.call_args
        assert kwargs["run_request"].message == ""


class TestDurableAIAgentParameterFlow:
    """Test that parameters flow correctly through the shim to executor."""

    def test_run_forwards_thread_parameter(self, test_agent: DurableAIAgent[Any], mock_executor: Mock) -> None:
        """Verify run forwards thread parameter to executor."""
        thread = DurableAgentThread(service_thread_id="test-thread")
        test_agent.run("message", thread=thread)

        mock_executor.run_durable_agent.assert_called_once()
        _, kwargs = mock_executor.run_durable_agent.call_args
        assert kwargs["thread"] == thread

    def test_run_forwards_response_format(self, test_agent: DurableAIAgent[Any], mock_executor: Mock) -> None:
        """Verify run forwards response_format parameter to executor."""
        test_agent.run("message", options={"response_format": ResponseFormatModel})

        mock_executor.run_durable_agent.assert_called_once()
        _, kwargs = mock_executor.run_durable_agent.call_args
        assert kwargs["run_request"].response_format == ResponseFormatModel


class TestDurableAIAgentProtocolCompliance:
    """Test that DurableAIAgent implements AgentProtocol correctly."""

    def test_agent_implements_protocol(self, test_agent: DurableAIAgent[Any]) -> None:
        """Verify DurableAIAgent implements AgentProtocol."""
        assert isinstance(test_agent, AgentProtocol)

    def test_agent_has_required_properties(self, test_agent: DurableAIAgent[Any]) -> None:
        """Verify DurableAIAgent has all required AgentProtocol properties."""
        assert hasattr(test_agent, "id")
        assert hasattr(test_agent, "name")
        assert hasattr(test_agent, "display_name")
        assert hasattr(test_agent, "description")

    def test_agent_id_defaults_to_name(self, mock_executor: Mock) -> None:
        """Verify agent id defaults to name when not provided."""
        agent: DurableAIAgent[Any] = DurableAIAgent(mock_executor, "my_agent")

        assert agent.id == "my_agent"
        assert agent.name == "my_agent"

    def test_agent_id_can_be_customized(self, mock_executor: Mock) -> None:
        """Verify agent id can be set independently from name."""
        agent: DurableAIAgent[Any] = DurableAIAgent(mock_executor, "my_agent", agent_id="custom-id")

        assert agent.id == "custom-id"
        assert agent.name == "my_agent"


class TestDurableAIAgentThreadManagement:
    """Test thread creation and management."""

    def test_get_new_thread_delegates_to_executor(self, test_agent: DurableAIAgent[Any], mock_executor: Mock) -> None:
        """Verify get_new_thread delegates to executor."""
        mock_thread = DurableAgentThread()
        mock_executor.get_new_thread.return_value = mock_thread

        thread = test_agent.get_new_thread()

        mock_executor.get_new_thread.assert_called_once_with("test_agent")
        assert thread == mock_thread

    def test_get_new_thread_forwards_kwargs(self, test_agent: DurableAIAgent[Any], mock_executor: Mock) -> None:
        """Verify get_new_thread forwards kwargs to executor."""
        mock_thread = DurableAgentThread(service_thread_id="thread-123")
        mock_executor.get_new_thread.return_value = mock_thread

        test_agent.get_new_thread(service_thread_id="thread-123")

        mock_executor.get_new_thread.assert_called_once()
        _, kwargs = mock_executor.get_new_thread.call_args
        assert kwargs["service_thread_id"] == "thread-123"


class TestDurableAgentProviderInterface:
    """Test that DurableAgentProvider defines the correct interface."""

    def test_provider_cannot_be_instantiated(self) -> None:
        """Verify DurableAgentProvider is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            DurableAgentProvider()  # type: ignore[abstract]

    def test_provider_defines_get_agent_method(self) -> None:
        """Verify DurableAgentProvider defines get_agent abstract method."""
        assert hasattr(DurableAgentProvider, "get_agent")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
