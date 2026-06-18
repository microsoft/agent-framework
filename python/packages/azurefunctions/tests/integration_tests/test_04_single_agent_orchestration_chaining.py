# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for Orchestration Chaining Sample

Tests the orchestration chaining sample for sequential agent execution.

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite running for durable orchestrations (or Azure Storage account configured)

Usage:
    # Start Azurite (if not already running)
    azurite &

    # Run tests
    uv run pytest packages/azurefunctions/tests/integration_tests/test_04_single_agent_orchestration_chaining.py -v
"""

import pytest

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("04_single_agent_orchestration_chaining"),
    pytest.mark.usefixtures("function_app_for_test"),
]


@pytest.mark.orchestration
class TestSampleOrchestrationChaining:
    """Tests for 04_single_agent_orchestration_chaining sample."""

    @pytest.fixture(autouse=True)
    def _setup(self, sample_helper) -> None:
        """Provide the helper for each test."""
        self.helper = sample_helper

    def test_orchestration_chaining(self, base_url: str) -> None:
        """Test sequential agent calls in orchestration."""
        # Start orchestration
        response = self.helper.post_json(f"{base_url}/api/singleagent/run", {})
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data

        # Wait for completion with output available
        status = self.helper.wait_for_orchestration_with_output(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"
        assert "output" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
