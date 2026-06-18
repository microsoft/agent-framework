# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableAIAgentWorker.

Focuses on critical worker flows: agent registration, validation, callbacks, and lifecycle.
"""

from unittest.mock import Mock

import pytest

from agent_framework_durabletask import DurableAIAgentWorker


@pytest.fixture
def mock_grpc_worker() -> Mock:
    """Create a mock TaskHubGrpcWorker for testing."""
    mock = Mock()
    mock.add_entity = Mock(return_value="dafx-test_agent")
    mock.start = Mock()
    mock.stop = Mock()
    return mock


@pytest.fixture
def mock_agent() -> Mock:
    """Create a mock agent for testing."""
    agent = Mock()
    agent.name = "test_agent"
    return agent


@pytest.fixture
def agent_worker(mock_grpc_worker: Mock) -> DurableAIAgentWorker:
    """Create a DurableAIAgentWorker with mock worker."""
    return DurableAIAgentWorker(mock_grpc_worker)


class TestDurableAIAgentWorkerRegistration:
    """Test agent registration behavior."""

    def test_add_agent_accepts_agent_with_name(
        self, agent_worker: DurableAIAgentWorker, mock_agent: Mock, mock_grpc_worker: Mock
    ) -> None:
        """Verify that agents with names can be registered."""
        agent_worker.add_agent(mock_agent)

        # Verify entity was registered with underlying worker
        mock_grpc_worker.add_entity.assert_called_once()
        # Verify agent name is tracked
        assert "test_agent" in agent_worker.registered_agent_names

    def test_add_agent_rejects_agent_without_name(self, agent_worker: DurableAIAgentWorker) -> None:
        """Verify that agents without names are rejected."""
        agent_no_name = Mock()
        agent_no_name.name = None

        with pytest.raises(ValueError, match="Agent must have a name"):
            agent_worker.add_agent(agent_no_name)

    def test_add_agent_rejects_empty_name(self, agent_worker: DurableAIAgentWorker) -> None:
        """Verify that agents with empty names are rejected."""
        agent_empty_name = Mock()
        agent_empty_name.name = ""

        with pytest.raises(ValueError, match="Agent must have a name"):
            agent_worker.add_agent(agent_empty_name)

    def test_add_agent_rejects_duplicate_names(self, agent_worker: DurableAIAgentWorker, mock_agent: Mock) -> None:
        """Verify duplicate agent names are not allowed."""
        agent_worker.add_agent(mock_agent)

        # Try to register another agent with the same name
        duplicate_agent = Mock()
        duplicate_agent.name = "test_agent"

        with pytest.raises(ValueError, match="already registered"):
            agent_worker.add_agent(duplicate_agent)

    def test_registered_agent_names_tracks_multiple_agents(self, agent_worker: DurableAIAgentWorker) -> None:
        """Verify registered_agent_names tracks all registered agents."""
        agent1 = Mock()
        agent1.name = "agent1"
        agent2 = Mock()
        agent2.name = "agent2"
        agent3 = Mock()
        agent3.name = "agent3"

        agent_worker.add_agent(agent1)
        agent_worker.add_agent(agent2)
        agent_worker.add_agent(agent3)

        registered = agent_worker.registered_agent_names
        assert "agent1" in registered
        assert "agent2" in registered
        assert "agent3" in registered
        assert len(registered) == 3


class TestDurableAIAgentWorkerCallbacks:
    """Test callback configuration behavior."""

    def test_worker_level_callback_accepted(self, mock_grpc_worker: Mock) -> None:
        """Verify worker-level callback can be set."""
        mock_callback = Mock()
        agent_worker = DurableAIAgentWorker(mock_grpc_worker, callback=mock_callback)

        assert agent_worker is not None

    def test_agent_level_callback_accepted(self, agent_worker: DurableAIAgentWorker, mock_agent: Mock) -> None:
        """Verify agent-level callback can be set during registration."""
        mock_callback = Mock()

        # Should not raise exception
        agent_worker.add_agent(mock_agent, callback=mock_callback)

        assert "test_agent" in agent_worker.registered_agent_names

    def test_none_callback_accepted(self, mock_grpc_worker: Mock, mock_agent: Mock) -> None:
        """Verify None callback is valid (no callbacks required)."""
        agent_worker = DurableAIAgentWorker(mock_grpc_worker, callback=None)
        agent_worker.add_agent(mock_agent, callback=None)

        assert "test_agent" in agent_worker.registered_agent_names


class TestDurableAIAgentWorkerLifecycle:
    """Test worker lifecycle behavior."""

    def test_start_delegates_to_underlying_worker(
        self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock
    ) -> None:
        """Verify start() delegates to wrapped worker."""
        agent_worker.start()

        mock_grpc_worker.start.assert_called_once()

    def test_stop_delegates_to_underlying_worker(
        self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock
    ) -> None:
        """Verify stop() delegates to wrapped worker."""
        agent_worker.stop()

        mock_grpc_worker.stop.assert_called_once()

    def test_start_works_with_no_agents(self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock) -> None:
        """Verify worker can start even with no agents registered."""
        agent_worker.start()

        mock_grpc_worker.start.assert_called_once()

    def test_start_works_with_multiple_agents(self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock) -> None:
        """Verify worker can start with multiple agents registered."""
        agent1 = Mock()
        agent1.name = "agent1"
        agent2 = Mock()
        agent2.name = "agent2"

        agent_worker.add_agent(agent1)
        agent_worker.add_agent(agent2)
        agent_worker.start()

        mock_grpc_worker.start.assert_called_once()
        assert len(agent_worker.registered_agent_names) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
