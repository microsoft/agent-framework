# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for single agent functionality.

Tests basic agent operations including:
- Agent registration and retrieval
- Single agent interactions
- Conversation continuity across multiple messages
- Multi-threaded agent usage
- Empty thread ID handling
"""

import pytest

# Module-level markers - applied to all tests in this module
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("01_single_agent"),
    pytest.mark.integration_test,
    pytest.mark.requires_azure_openai,
    pytest.mark.requires_dts,
]


class TestSingleAgent:
    """Test suite for single agent functionality."""

    @pytest.fixture(autouse=True)
    def setup(self, agent_client_factory: type) -> None:
        """Setup test fixtures."""
        # Create agent client using the factory fixture
        _, self.agent_client = agent_client_factory.create()

    def test_agent_registration(self) -> None:
        """Test that the Joker agent is registered and accessible."""
        agent = self.agent_client.get_agent("Joker")
        assert agent is not None
        assert agent.name == "Joker"

    def test_single_interaction(self):
        """Test a single interaction with the agent."""
        agent = self.agent_client.get_agent("Joker")
        session = agent.create_session()

        response = agent.run("Tell me a short joke about programming.", session=session)

        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0

    def test_conversation_continuity(self):
        """Test that conversation context is maintained across turns."""
        agent = self.agent_client.get_agent("Joker")
        session = agent.create_session()

        # First turn: Ask for a joke about a specific topic
        response1 = agent.run("Tell me a joke about cats.", session=session)
        assert response1 is not None
        assert len(response1.text) > 0

        # Second turn: Ask a follow-up that requires context
        response2 = agent.run("Can you make it funnier?", session=session)
        assert response2 is not None
        assert len(response2.text) > 0

        # The agent should understand "it" refers to the previous joke

    def test_multiple_sessions(self):
        """Test that different sessions maintain separate contexts."""
        agent = self.agent_client.get_agent("Joker")

        # Create two separate sessions
        session1 = agent.create_session()
        session2 = agent.create_session()

        assert session1.durable_session_id != session2.durable_session_id

        # Send different messages to each session
        response1 = agent.run("Tell me a joke about dogs.", session=session1)
        response2 = agent.run("Tell me a joke about birds.", session=session2)

        assert response1 is not None
        assert response2 is not None
        assert response1.text != response2.text
