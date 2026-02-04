# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for single agent orchestration with chaining.

Tests orchestration patterns with sequential agent calls:
- Orchestration registration and execution
- Sequential agent calls on same thread
- Conversation continuity in orchestrations
- Thread context preservation
"""

import json
import logging
from typing import Any

import pytest
from dt_testutils import OrchestrationHelper, create_agent_client
from durabletask.client import OrchestrationStatus

# Agent name from the 04_single_agent_orchestration_chaining sample
WRITER_AGENT_NAME: str = "WriterAgent"

# Configure logging
logging.basicConfig(level=logging.WARNING)

# Module-level markers - applied to all tests in this module
pytestmark = [
    pytest.mark.sample("04_single_agent_orchestration_chaining"),
    pytest.mark.integration_test,
    pytest.mark.requires_azure_openai,
    pytest.mark.requires_dts,
]


class TestSingleAgentOrchestrationChaining:
    """Test suite for single agent orchestration with chaining."""

    @pytest.fixture(autouse=True)
    def setup(self, worker_process: dict[str, Any], dts_endpoint: str) -> None:
        """Setup test fixtures."""
        self.endpoint: str = dts_endpoint
        self.taskhub: str = str(worker_process["taskhub"])

        # Create agent client and DTS client
        self.dts_client, self.agent_client = create_agent_client(self.endpoint, self.taskhub)

        # Create orchestration helper
        self.orch_helper = OrchestrationHelper(self.dts_client)

    def test_agent_registered(self):
        """Test that the Writer agent is registered."""
        agent = self.agent_client.get_agent(WRITER_AGENT_NAME)
        assert agent is not None
        assert agent.name == WRITER_AGENT_NAME

    def test_chaining_context_preserved(self):
        """Test that context is preserved across agent runs in orchestration."""
        # Start the orchestration
        instance_id = self.dts_client.schedule_new_orchestration(
            orchestrator="single_agent_chaining_orchestration",
            input="",
        )

        # Wait for completion with output
        metadata, output = self.orch_helper.wait_for_orchestration_with_output(
            instance_id=instance_id,
            timeout=120.0,
        )

        assert metadata is not None
        assert output is not None

        # The final output should be a refined sentence
        final_text = json.loads(output)

        # Should be a meaningful sentence (not empty or error message)
        assert len(final_text) > 10
        assert not final_text.startswith("Error")

    def test_multiple_orchestration_instances(self):
        """Test that multiple orchestration instances can run independently."""
        # Start two orchestrations
        instance_id_1 = self.dts_client.schedule_new_orchestration(
            orchestrator="single_agent_chaining_orchestration",
            input="",
        )
        instance_id_2 = self.dts_client.schedule_new_orchestration(
            orchestrator="single_agent_chaining_orchestration",
            input="",
        )

        assert instance_id_1 != instance_id_2

        # Both should complete
        metadata_1 = self.orch_helper.wait_for_orchestration(
            instance_id=instance_id_1,
            timeout=120.0,
        )
        metadata_2 = self.orch_helper.wait_for_orchestration(
            instance_id=instance_id_2,
            timeout=120.0,
        )

        assert metadata_1.runtime_status == OrchestrationStatus.COMPLETED
        assert metadata_2.runtime_status == OrchestrationStatus.COMPLETED
