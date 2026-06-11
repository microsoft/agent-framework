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

import pytest
from durabletask.client import OrchestrationStatus

# Agent names from the 05_multi_agent_orchestration_concurrency sample
PHYSICIST_AGENT_NAME: str = "PhysicistAgent"
CHEMIST_AGENT_NAME: str = "ChemistAgent"

# Configure logging
logging.basicConfig(level=logging.WARNING)

# Module-level markers
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("05_multi_agent_orchestration_concurrency"),
    pytest.mark.integration_test,
    pytest.mark.requires_dts,
]


class TestMultiAgentOrchestrationConcurrency:
    """Test suite for multi-agent orchestration with concurrency."""

    @pytest.fixture(autouse=True)
    def setup(self, agent_client_factory: type, orchestration_helper) -> None:
        """Setup test fixtures."""
        # Create agent client using the factory fixture
        self.dts_client, self.agent_client = agent_client_factory.create()
        self.orch_helper = orchestration_helper

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
