# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for single agent functionality.

Tests basic agent operations including:
- Agent registration and retrieval
- Single agent interactions
- Conversation continuity across multiple messages
- Multi-threaded agent usage
- Empty thread ID handling
"""

from typing import Any

import pytest
from dt_testutils import create_agent_client

# Module-level markers - applied to all tests in this module
pytestmark = [
    pytest.mark.sample("01_single_agent"),
    pytest.mark.integration_test,
    pytest.mark.requires_azure_openai,
    pytest.mark.requires_dts,
]


class TestSingleAgent:
    """Test suite for single agent functionality."""

    @pytest.fixture(autouse=True)
    def setup(self, worker_process: dict[str, Any], dts_endpoint: str) -> None:
        """Setup test fixtures."""
        self.endpoint: str = dts_endpoint
        self.taskhub: str = str(worker_process["taskhub"])

        # Create agent client
        _, self.agent_client = create_agent_client(self.endpoint, self.taskhub)

    def test_agent_registration(self) -> None:
        """Test that the Joker agent is registered and accessible."""
        agent = self.agent_client.get_agent("Joker")
        assert agent is not None
        assert agent.name == "Joker"

    def test_single_interaction(self):
        """Test a single interaction with the agent."""
        agent = self.agent_client.get_agent("Joker")
        thread = agent.get_new_thread()

        response = agent.run("Tell me a short joke about programming.", thread=thread)

        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0

    def test_conversation_continuity(self):
        """Test that conversation context is maintained across turns."""
        agent = self.agent_client.get_agent("Joker")
        thread = agent.get_new_thread()

        # First turn: Ask for a joke about a specific topic
        response1 = agent.run("Tell me a joke about cats.", thread=thread)
        assert response1 is not None
        assert len(response1.text) > 0

        # Second turn: Ask a follow-up that requires context
        response2 = agent.run("Can you make it funnier?", thread=thread)
        assert response2 is not None
        assert len(response2.text) > 0

        # The agent should understand "it" refers to the previous joke

    def test_multiple_threads(self):
        """Test that different threads maintain separate contexts."""
        agent = self.agent_client.get_agent("Joker")

        # Create two separate threads
        thread1 = agent.get_new_thread()
        thread2 = agent.get_new_thread()

        assert thread1.session_id != thread2.session_id

        # Send different messages to each thread
        response1 = agent.run("Tell me a joke about dogs.", thread=thread1)
        response2 = agent.run("Tell me a joke about birds.", thread=thread2)

        assert response1 is not None
        assert response2 is not None
        assert response1.text != response2.text
