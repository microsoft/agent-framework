# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for MultiAgent Concurrency Sample

Tests the multi-agent concurrency sample for parallel agent execution.

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite running for durable orchestrations (or Azure Storage account configured)

Usage:
    # Start Azurite (if not already running)
    azurite &

    # Run tests
    uv run pytest packages/azurefunctions/tests/integration_tests/test_05_multi_agent_orchestration_concurrency.py -v
"""

import pytest

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.orchestration,
    pytest.mark.sample("05_multi_agent_orchestration_concurrency"),
    pytest.mark.usefixtures("function_app_for_test"),
]


class TestSampleMultiAgentConcurrency:
    """Tests for 05_multi_agent_orchestration_concurrency sample."""

    @pytest.fixture(autouse=True)
    def _setup(self, sample_helper) -> None:
        """Provide the helper for each test."""
        self.helper = sample_helper

    def test_concurrent_agents(self, base_url: str) -> None:
        """Test multiple agents running concurrently."""
        # Start orchestration
        response = self.helper.post_text(f"{base_url}/api/multiagent/run", "What is temperature?")
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data

        # Wait for completion
        status = self.helper.wait_for_orchestration(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"
        output = status["output"]
        assert "physicist" in output
        assert "chemist" in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
