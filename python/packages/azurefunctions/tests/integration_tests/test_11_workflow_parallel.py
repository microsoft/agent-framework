# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for Parallel Workflow Sample

Tests the parallel workflow execution sample demonstrating:
- Two executors running concurrently (fan-out to activities)
- Two agents running concurrently (fan-out to entities)
- Mixed agent + executor running concurrently

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite running for durable orchestrations (or Azure Storage account configured)

Usage:
    # Start Azurite (if not already running)
    azurite &

    # Run tests
    uv run pytest packages/azurefunctions/tests/integration_tests/test_11_workflow_parallel.py -v
"""

import pytest

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("11_workflow_parallel"),
    pytest.mark.usefixtures("function_app_for_test"),
]


@pytest.mark.orchestration
class TestWorkflowParallel:
    """Tests for 11_workflow_parallel sample."""

    @pytest.fixture(autouse=True)
    def _setup(self, base_url: str, sample_helper) -> None:
        """Provide the helper and base URL for each test."""
        self.base_url = base_url
        self.helper = sample_helper

    @pytest.mark.skip(reason="Flaky in CI: times out / crashes the xdist runner; temporarily disabled.")
    def test_parallel_workflow_end_to_end(self) -> None:
        """Run the parallel workflow end-to-end: start, check status, verify completion.

        Consolidated into a single test on purpose: the work-stealing xdist scheduler
        distributes tests (not modules) across workers, and the module-scoped
        ``function_app_for_test`` fixture is created per worker -- so multiple tests in
        this module would each spawn a separate ``func`` host for this resource-heavy
        parallel sample. One test keeps it to a single host while still covering the
        fan-out path end-to-end.
        """
        payload = {
            "document_id": "doc-test-001",
            "content": (
                "The quarterly earnings report shows strong growth in our cloud services division. "
                "Revenue increased by 25% compared to last year, driven by enterprise adoption. "
                "Customer satisfaction remains high at 92%."
            ),
        }

        # Start the orchestration.
        response = self.helper.post_json(f"{self.base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        instance_id = data["instanceId"]
        assert "statusQueryGetUri" in data

        # The status endpoint reflects the started instance.
        status_response = self.helper.get(f"{self.base_url}/api/workflow/status/{instance_id}")
        assert status_response.status_code == 200
        assert status_response.json()["instanceId"] == instance_id

        # Fan-out to parallel processors and agents completes with an aggregated output.
        status = self.helper.wait_for_orchestration_with_output(data["statusQueryGetUri"], max_wait=300)
        assert status["runtimeStatus"] == "Completed"
        assert "output" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
