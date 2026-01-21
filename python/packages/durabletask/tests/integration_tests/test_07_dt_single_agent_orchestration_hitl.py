# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for single agent orchestration with human-in-the-loop.

Tests human-in-the-loop (HITL) patterns:
- External event waiting and handling
- Timeout handling in orchestrations
- Iterative refinement with human feedback
- Activity function integration
- Approval workflow patterns
"""

import logging
from typing import Any

import pytest
from dt_testutils import OrchestrationHelper, create_agent_client
from durabletask.client import OrchestrationStatus

# Constants from the 07_single_agent_orchestration_hitl sample
WRITER_AGENT_NAME: str = "WriterAgent"
HUMAN_APPROVAL_EVENT: str = "HumanApproval"

# Configure logging
logging.basicConfig(level=logging.WARNING)

# Module-level markers
pytestmark = [
    pytest.mark.sample("07_single_agent_orchestration_hitl"),
    pytest.mark.integration_test,
    pytest.mark.requires_dts,
]


class TestSingleAgentOrchestrationHITL:
    """Test suite for single agent orchestration with human-in-the-loop."""

    @pytest.fixture(autouse=True)
    def setup(self, worker_process: dict[str, Any], dts_endpoint: str) -> None:
        """Setup test fixtures."""
        self.endpoint: str = str(worker_process["endpoint"])
        self.taskhub: str = str(worker_process["taskhub"])

        logging.info(f"Using taskhub: {self.taskhub} at endpoint: {self.endpoint}")

        # Create agent client and DTS client
        self.dts_client, self.agent_client = create_agent_client(self.endpoint, self.taskhub)

        # Create orchestration helper
        self.orch_helper = OrchestrationHelper(self.dts_client)

    def test_agent_registered(self):
        """Test that the Writer agent is registered."""
        agent = self.agent_client.get_agent(WRITER_AGENT_NAME)
        assert agent is not None
        assert agent.name == WRITER_AGENT_NAME

    def test_hitl_orchestration_with_approval(self):
        """Test HITL orchestration with immediate approval."""
        payload = {
            "topic": "The benefits of continuous learning",
            "max_review_attempts": 3,
            "approval_timeout_seconds": 60,
        }

        # Start the orchestration
        instance_id = self.dts_client.schedule_new_orchestration(
            orchestrator="content_generation_hitl_orchestration",
            input=payload,
        )

        assert instance_id is not None

        # Wait for orchestration to reach notification point
        notification_received = self.orch_helper.wait_for_notification(instance_id, timeout_seconds=90)
        assert notification_received, "Failed to receive notification from orchestration"

        # Send approval event
        approval_data = {"approved": True, "feedback": ""}
        self.orch_helper.raise_event(
            instance_id=instance_id,
            event_name=HUMAN_APPROVAL_EVENT,
            event_data=approval_data,
        )

        # Wait for completion
        metadata = self.orch_helper.wait_for_orchestration(
            instance_id=instance_id,
            timeout=90.0,
        )

        assert metadata is not None
        assert metadata.runtime_status == OrchestrationStatus.COMPLETED

    def test_hitl_orchestration_with_rejection_and_feedback(self):
        """Test HITL orchestration with rejection and iterative refinement."""
        payload = {
            "topic": "Artificial Intelligence in healthcare",
            "max_review_attempts": 3,
            "approval_timeout_seconds": 60,
        }

        # Start the orchestration
        instance_id = self.dts_client.schedule_new_orchestration(
            orchestrator="content_generation_hitl_orchestration",
            input=payload,
        )

        # Wait for orchestration to reach notification point
        notification_received = self.orch_helper.wait_for_notification(instance_id, timeout_seconds=90)
        assert notification_received, "Failed to receive notification from orchestration"

        # First rejection with feedback
        rejection_data = {
            "approved": False,
            "feedback": "Please make it more concise and add specific examples.",
        }
        self.orch_helper.raise_event(
            instance_id=instance_id,
            event_name=HUMAN_APPROVAL_EVENT,
            event_data=rejection_data,
        )

        # Wait for orchestration to refine and reach notification point again
        notification_received = self.orch_helper.wait_for_notification(instance_id, timeout_seconds=90)
        assert notification_received, "Failed to receive notification after refinement"

        # Second approval
        approval_data = {"approved": True, "feedback": ""}
        self.orch_helper.raise_event(
            instance_id=instance_id,
            event_name=HUMAN_APPROVAL_EVENT,
            event_data=approval_data,
        )

        # Wait for completion
        metadata = self.orch_helper.wait_for_orchestration(
            instance_id=instance_id,
            timeout=90.0,
        )

        assert metadata is not None
        assert metadata.runtime_status == OrchestrationStatus.COMPLETED

    def test_hitl_orchestration_timeout(self):
        """Test HITL orchestration timeout behavior."""
        payload = {
            "topic": "Cloud computing fundamentals",
            "max_review_attempts": 1,
            "approval_timeout_seconds": 0.1,  # Short timeout for testing
        }

        # Start the orchestration
        instance_id = self.dts_client.schedule_new_orchestration(
            orchestrator="content_generation_hitl_orchestration",
            input=payload,
        )

        # Don't send any approval - let it timeout
        # The orchestration should fail due to timeout
        try:
            metadata = self.orch_helper.wait_for_orchestration(
                instance_id=instance_id,
                timeout=90.0,
            )
            # If it completes, it should be failed status due to timeout
            assert metadata.runtime_status == OrchestrationStatus.FAILED
        except (RuntimeError, TimeoutError):
            # Expected - orchestration should timeout and fail
            pass
