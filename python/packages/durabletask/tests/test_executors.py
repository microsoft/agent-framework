# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableAgentExecutor implementations.

Focuses on critical behavioral flows for executor strategies.
Run with: pytest tests/test_executors.py -v
"""

import time
from unittest.mock import Mock

import pytest
from agent_framework import AgentRunResponse

from agent_framework_durabletask import DurableAgentThread
from agent_framework_durabletask._constants import DEFAULT_MAX_POLL_RETRIES, DEFAULT_POLL_INTERVAL_SECONDS
from agent_framework_durabletask._executors import (
    ClientAgentExecutor,
    OrchestrationAgentExecutor,
)
from agent_framework_durabletask._models import RunRequest


class TestExecutorThreadCreation:
    """Test that executors properly create DurableAgentThread with parameters."""

    def test_client_executor_creates_durable_thread(self) -> None:
        """Verify ClientAgentExecutor creates DurableAgentThread instances."""
        mock_client = Mock()
        executor = ClientAgentExecutor(mock_client)

        thread = executor.get_new_thread("test_agent")

        assert isinstance(thread, DurableAgentThread)

    def test_client_executor_forwards_kwargs_to_thread(self) -> None:
        """Verify ClientAgentExecutor forwards kwargs to DurableAgentThread creation."""
        mock_client = Mock()
        executor = ClientAgentExecutor(mock_client)

        thread = executor.get_new_thread("test_agent", service_thread_id="client-123")

        assert isinstance(thread, DurableAgentThread)
        assert thread.service_thread_id == "client-123"

    def test_orchestration_executor_creates_durable_thread(self) -> None:
        """Verify OrchestrationAgentExecutor creates DurableAgentThread instances."""
        mock_context = Mock()
        executor = OrchestrationAgentExecutor(mock_context)

        thread = executor.get_new_thread("test_agent")

        assert isinstance(thread, DurableAgentThread)

    def test_orchestration_executor_forwards_kwargs_to_thread(self) -> None:
        """Verify OrchestrationAgentExecutor forwards kwargs to DurableAgentThread creation."""
        mock_context = Mock()
        executor = OrchestrationAgentExecutor(mock_context)

        thread = executor.get_new_thread("test_agent", service_thread_id="orch-456")

        assert isinstance(thread, DurableAgentThread)
        assert thread.service_thread_id == "orch-456"


class TestExecutorRunNotImplemented:
    """Test that run_durable_agent works as implemented."""

    def test_client_executor_run_returns_response(self) -> None:
        """Verify ClientAgentExecutor.run_durable_agent returns AgentRunResponse (synchronous)."""
        mock_client = Mock()
        mock_client.signal_entity = Mock()
        mock_client.get_entity = Mock(return_value=None)
        # Use minimal polling parameters to avoid long test times
        executor = ClientAgentExecutor(mock_client, max_poll_retries=1, poll_interval_seconds=0.01)

        # Create a RunRequest
        run_request = RunRequest(message="test message", correlation_id="test-123")

        # This should return a timeout response (since mock doesn't have state)
        result = executor.run_durable_agent("test_agent", run_request)

        # Verify it returns an AgentRunResponse (synchronous, not a coroutine)
        assert isinstance(result, AgentRunResponse)
        assert result is not None

    def test_orchestration_executor_run_not_implemented(self) -> None:
        """Verify OrchestrationAgentExecutor run raises NotImplementedError until implementation."""
        mock_context = Mock()
        executor = OrchestrationAgentExecutor(mock_context)

        # Create a RunRequest
        run_request = RunRequest(message="test message", correlation_id="test-123")

        with pytest.raises(NotImplementedError, match="OrchestrationAgentProvider.run_durable_agent"):
            executor.run_durable_agent("test_agent", run_request)


class TestClientAgentExecutorPollingConfiguration:
    """Test polling configuration parameters for ClientAgentExecutor."""

    def test_executor_uses_default_polling_parameters(self) -> None:
        """Verify executor initializes with default polling parameters."""
        mock_client = Mock()
        executor = ClientAgentExecutor(mock_client)

        assert executor.max_poll_retries == DEFAULT_MAX_POLL_RETRIES
        assert executor.poll_interval_seconds == DEFAULT_POLL_INTERVAL_SECONDS

    def test_executor_accepts_custom_polling_parameters(self) -> None:
        """Verify executor accepts and stores custom polling parameters."""
        mock_client = Mock()
        executor = ClientAgentExecutor(mock_client, max_poll_retries=20, poll_interval_seconds=0.5)

        assert executor.max_poll_retries == 20
        assert executor.poll_interval_seconds == 0.5

    def test_executor_respects_custom_max_poll_retries(self) -> None:
        """Verify executor respects custom max_poll_retries during polling."""

        mock_client = Mock()
        mock_client.signal_entity = Mock()
        mock_client.get_entity = Mock(return_value=None)

        # Create executor with only 2 retries
        executor = ClientAgentExecutor(mock_client, max_poll_retries=2, poll_interval_seconds=0.01)

        # Create a RunRequest
        run_request = RunRequest(message="test message", correlation_id="test-123")

        # Run the agent
        result = executor.run_durable_agent("test_agent", run_request)

        # Verify it returns AgentRunResponse (should timeout after 2 attempts)
        assert isinstance(result, AgentRunResponse)

        # Verify get_entity was called 2 times (max_poll_retries)
        assert mock_client.get_entity.call_count == 2

    def test_executor_respects_custom_poll_interval(self) -> None:
        """Verify executor respects custom poll_interval_seconds during polling."""

        mock_client = Mock()
        mock_client.signal_entity = Mock()
        mock_client.get_entity = Mock(return_value=None)

        # Create executor with very short interval
        executor = ClientAgentExecutor(mock_client, max_poll_retries=3, poll_interval_seconds=0.01)

        # Create a RunRequest
        run_request = RunRequest(message="test message", correlation_id="test-123")

        # Measure time taken
        start = time.time()
        result = executor.run_durable_agent("test_agent", run_request)
        elapsed = time.time() - start

        # Should take roughly 3 * 0.01 = 0.03 seconds (plus overhead)
        # Be generous with timing to avoid flakiness
        assert elapsed < 0.2  # Should be quick with 0.01 interval
        assert isinstance(result, AgentRunResponse)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
