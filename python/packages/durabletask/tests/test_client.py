# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableAIAgentClient.

Focuses on critical client workflows: agent retrieval, protocol compliance, and integration.
Run with: pytest tests/test_client.py -v
"""

from unittest.mock import Mock

import pytest
from agent_framework import AgentProtocol

from agent_framework_durabletask import DurableAgentThread, DurableAIAgentClient
from agent_framework_durabletask._shim import DurableAIAgent


@pytest.fixture
def mock_grpc_client() -> Mock:
    """Create a mock TaskHubGrpcClient for testing."""
    return Mock()


@pytest.fixture
def agent_client(mock_grpc_client: Mock) -> DurableAIAgentClient:
    """Create a DurableAIAgentClient with mock gRPC client."""
    return DurableAIAgentClient(mock_grpc_client)


class TestDurableAIAgentClientGetAgent:
    """Test core workflow: retrieving agents from the client."""

    def test_get_agent_returns_durable_agent_shim(self, agent_client: DurableAIAgentClient) -> None:
        """Verify get_agent returns a DurableAIAgent instance."""
        agent = agent_client.get_agent("assistant")

        assert isinstance(agent, DurableAIAgent)
        assert isinstance(agent, AgentProtocol)

    def test_get_agent_shim_has_correct_name(self, agent_client: DurableAIAgentClient) -> None:
        """Verify retrieved agent has the correct name."""
        agent = agent_client.get_agent("my_agent")

        assert agent.name == "my_agent"

    def test_get_agent_multiple_times_returns_new_instances(self, agent_client: DurableAIAgentClient) -> None:
        """Verify multiple get_agent calls return independent instances."""
        agent1 = agent_client.get_agent("assistant")
        agent2 = agent_client.get_agent("assistant")

        assert agent1 is not agent2  # Different object instances

    def test_get_agent_different_agents(self, agent_client: DurableAIAgentClient) -> None:
        """Verify client can retrieve multiple different agents."""
        agent1 = agent_client.get_agent("agent1")
        agent2 = agent_client.get_agent("agent2")

        assert agent1.name == "agent1"
        assert agent2.name == "agent2"


class TestDurableAIAgentClientIntegration:
    """Test integration scenarios between client and agent shim."""

    def test_client_agent_has_working_run_method(self, agent_client: DurableAIAgentClient) -> None:
        """Verify agent from client has callable run method (even if not yet implemented)."""
        agent = agent_client.get_agent("assistant")

        assert hasattr(agent, "run")
        assert callable(agent.run)

    def test_client_agent_can_create_threads(self, agent_client: DurableAIAgentClient) -> None:
        """Verify agent from client can create DurableAgentThread instances."""
        agent = agent_client.get_agent("assistant")

        thread = agent.get_new_thread()

        assert isinstance(thread, DurableAgentThread)

    def test_client_agent_thread_with_parameters(self, agent_client: DurableAIAgentClient) -> None:
        """Verify agent can create threads with custom parameters."""
        agent = agent_client.get_agent("assistant")

        thread = agent.get_new_thread(service_thread_id="client-session-123")

        assert isinstance(thread, DurableAgentThread)
        assert thread.service_thread_id == "client-session-123"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
