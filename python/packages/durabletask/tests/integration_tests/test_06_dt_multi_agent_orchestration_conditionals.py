# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for multi-agent orchestration with conditionals.

Tests conditional orchestration patterns:
- Conditional branching in orchestrations
- Agent-based decision making
- Activity function execution
- Structured output handling
- Conditional routing based on agent responses
"""

import logging
from typing import Any

import pytest
from dt_testutils import OrchestrationHelper, create_agent_client
from durabletask.client import OrchestrationStatus

# Agent names from the 06_multi_agent_orchestration_conditionals sample
SPAM_AGENT_NAME: str = "SpamDetectionAgent"
EMAIL_AGENT_NAME: str = "EmailAssistantAgent"

# Configure logging
logging.basicConfig(level=logging.WARNING)

# Module-level markers
pytestmark = [
    pytest.mark.sample("06_multi_agent_orchestration_conditionals"),
    pytest.mark.integration_test,
    pytest.mark.requires_dts,
]


class TestMultiAgentOrchestrationConditionals:
    """Test suite for multi-agent orchestration with conditionals."""

    @pytest.fixture(autouse=True)
    def setup(self, worker_process: dict[str, Any], dts_endpoint: str) -> None:
        """Setup test fixtures."""
        self.endpoint: str = dts_endpoint
        self.taskhub: str = str(worker_process["taskhub"])

        # Create agent client and DTS client
        self.dts_client, self.agent_client = create_agent_client(self.endpoint, self.taskhub)

        # Create orchestration helper
        self.orch_helper = OrchestrationHelper(self.dts_client)

    def test_agents_registered(self):
        """Test that both agents are registered."""
        spam_agent = self.agent_client.get_agent(SPAM_AGENT_NAME)
        email_agent = self.agent_client.get_agent(EMAIL_AGENT_NAME)

        assert spam_agent is not None
        assert spam_agent.name == SPAM_AGENT_NAME
        assert email_agent is not None
        assert email_agent.name == EMAIL_AGENT_NAME

    def test_conditional_branching(self):
        """Test that conditional branching works correctly."""
        # Test with obvious spam
        spam_payload = {
            "email_id": "spam-001",
            "email_content": "Buy cheap medications online! No prescription needed! Limited time offer!",
        }

        spam_instance_id = self.dts_client.schedule_new_orchestration(
            orchestrator="spam_detection_orchestration",
            input=spam_payload,
        )

        # Test with legitimate email
        legit_payload = {
            "email_id": "legit-001",
            "email_content": "Hi team, please review the attached document before our meeting tomorrow.",
        }

        legit_instance_id = self.dts_client.schedule_new_orchestration(
            orchestrator="spam_detection_orchestration",
            input=legit_payload,
        )

        # Both should complete successfully (different branches)
        spam_metadata = self.orch_helper.wait_for_orchestration(
            instance_id=spam_instance_id,
            timeout=120.0,
        )
        legit_metadata = self.orch_helper.wait_for_orchestration(
            instance_id=legit_instance_id,
            timeout=120.0,
        )

        assert spam_metadata.runtime_status == OrchestrationStatus.COMPLETED
        assert legit_metadata.runtime_status == OrchestrationStatus.COMPLETED
