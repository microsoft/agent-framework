# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableAgentExecutor implementations.

Focuses on critical behavioral flows for executor strategies.
Run with: pytest tests/test_executors.py -v
"""

from unittest.mock import Mock

import pytest

from agent_framework_durabletask import DurableAgentThread
from agent_framework_durabletask._executors import (
    ClientAgentExecutor,
    OrchestrationAgentExecutor,
)


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
    """Test that run_durable_agent raises NotImplementedError until wired."""

    async def test_client_executor_run_not_implemented(self) -> None:
        """Verify ClientAgentExecutor run raises NotImplementedError until implementation."""
        mock_client = Mock()
        executor = ClientAgentExecutor(mock_client)

        with pytest.raises(NotImplementedError, match="ClientAgentProvider.run_durable_agent"):
            await executor.run_durable_agent("test_agent", "test message")

    def test_orchestration_executor_run_not_implemented(self) -> None:
        """Verify OrchestrationAgentExecutor run raises NotImplementedError until implementation."""
        mock_context = Mock()
        executor = OrchestrationAgentExecutor(mock_context)

        with pytest.raises(NotImplementedError, match="OrchestrationAgentProvider.run_durable_agent"):
            executor.run_durable_agent("test_agent", "test message")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
