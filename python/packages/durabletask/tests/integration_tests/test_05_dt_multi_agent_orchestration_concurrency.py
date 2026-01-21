# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for multi-agent orchestration with concurrency.

Tests concurrent execution patterns:
- Parallel agent execution
- Concurrent orchestration tasks
- Independent thread management in parallel
- Result aggregation from concurrent calls
"""

import json
import logging
from typing import Any

import pytest
from dt_testutils import OrchestrationHelper, create_agent_client
from durabletask.client import OrchestrationStatus

# Agent names from the 05_multi_agent_orchestration_concurrency sample
PHYSICIST_AGENT_NAME: str = "PhysicistAgent"
CHEMIST_AGENT_NAME: str = "ChemistAgent"

# Configure logging
logging.basicConfig(level=logging.WARNING)

# Module-level markers
pytestmark = [
    pytest.mark.sample("05_multi_agent_orchestration_concurrency"),
    pytest.mark.integration_test,
    pytest.mark.requires_dts,
]


class TestMultiAgentOrchestrationConcurrency:
    """Test suite for multi-agent orchestration with concurrency."""

    @pytest.fixture(autouse=True)
    def setup(self, worker_process: dict[str, Any], dts_endpoint: str) -> None:
        """Setup test fixtures."""
        self.endpoint = dts_endpoint
        self.taskhub = worker_process["taskhub"]

        # Create agent client and DTS client
        self.dts_client, self.agent_client = create_agent_client(self.endpoint, self.taskhub)

        # Create orchestration helper
        self.orch_helper = OrchestrationHelper(self.dts_client)

    def test_agents_registered(self):
        """Test that both agents are registered."""
        physicist = self.agent_client.get_agent(PHYSICIST_AGENT_NAME)
        chemist = self.agent_client.get_agent(CHEMIST_AGENT_NAME)

        assert physicist is not None
        assert physicist.name == PHYSICIST_AGENT_NAME
        assert chemist is not None
        assert chemist.name == CHEMIST_AGENT_NAME

    def test_different_prompts(self):
        """Test concurrent orchestration with different prompts."""
        prompts = [
            "What is temperature?",
            "Explain molecules.",
        ]

        for prompt in prompts:
            instance_id = self.dts_client.schedule_new_orchestration(
                orchestrator="multi_agent_concurrent_orchestration",
                input=prompt,
            )

            metadata, output = self.orch_helper.wait_for_orchestration_with_output(
                instance_id=instance_id,
                timeout=120.0,
            )

            assert metadata.runtime_status == OrchestrationStatus.COMPLETED
            result = json.loads(output)
            assert "physicist" in result
            assert "chemist" in result
