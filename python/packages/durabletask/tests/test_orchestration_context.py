# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableAIAgentOrchestrationContext.

Focuses on critical orchestration workflows: agent retrieval and integration.
Run with: pytest tests/test_orchestration_context.py -v
"""

from unittest.mock import Mock

import pytest
from agent_framework import AgentProtocol

from agent_framework_durabletask import DurableAgentThread
from agent_framework_durabletask._orchestration_context import DurableAIAgentOrchestrationContext
from agent_framework_durabletask._shim import DurableAIAgent


@pytest.fixture
def mock_orchestration_context() -> Mock:
    """Create a mock OrchestrationContext for testing."""
    return Mock()


@pytest.fixture
def agent_context(mock_orchestration_context: Mock) -> DurableAIAgentOrchestrationContext:
    """Create a DurableAIAgentOrchestrationContext with mock context."""
    return DurableAIAgentOrchestrationContext(mock_orchestration_context)


class TestDurableAIAgentOrchestrationContextGetAgent:
    """Test core workflow: retrieving agents from orchestration context."""

    def test_get_agent_returns_durable_agent_shim(self, agent_context: DurableAIAgentOrchestrationContext) -> None:
        """Verify get_agent returns a DurableAIAgent instance."""
        agent = agent_context.get_agent("assistant")

        assert isinstance(agent, DurableAIAgent)
        assert isinstance(agent, AgentProtocol)

    def test_get_agent_shim_has_correct_name(self, agent_context: DurableAIAgentOrchestrationContext) -> None:
        """Verify retrieved agent has the correct name."""
        agent = agent_context.get_agent("my_agent")

        assert agent.name == "my_agent"

    def test_get_agent_multiple_times_returns_new_instances(
        self, agent_context: DurableAIAgentOrchestrationContext
    ) -> None:
        """Verify multiple get_agent calls return independent instances."""
        agent1 = agent_context.get_agent("assistant")
        agent2 = agent_context.get_agent("assistant")

        assert agent1 is not agent2  # Different object instances

    def test_get_agent_different_agents(self, agent_context: DurableAIAgentOrchestrationContext) -> None:
        """Verify context can retrieve multiple different agents."""
        agent1 = agent_context.get_agent("agent1")
        agent2 = agent_context.get_agent("agent2")

        assert agent1.name == "agent1"
        assert agent2.name == "agent2"


class TestDurableAIAgentOrchestrationContextIntegration:
    """Test integration scenarios between orchestration context and agent shim."""

    def test_orchestration_agent_has_working_run_method(
        self, agent_context: DurableAIAgentOrchestrationContext
    ) -> None:
        """Verify agent from context has callable run method (even if not yet implemented)."""
        agent = agent_context.get_agent("assistant")

        assert hasattr(agent, "run")
        assert callable(agent.run)

    def test_orchestration_agent_can_create_threads(self, agent_context: DurableAIAgentOrchestrationContext) -> None:
        """Verify agent from context can create DurableAgentThread instances."""
        agent = agent_context.get_agent("assistant")

        thread = agent.get_new_thread()

        assert isinstance(thread, DurableAgentThread)

    def test_orchestration_agent_thread_with_parameters(
        self, agent_context: DurableAIAgentOrchestrationContext
    ) -> None:
        """Verify agent can create threads with custom parameters."""
        agent = agent_context.get_agent("assistant")

        thread = agent.get_new_thread(service_thread_id="orch-session-456")

        assert isinstance(thread, DurableAgentThread)
        assert thread.service_thread_id == "orch-session-456"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
