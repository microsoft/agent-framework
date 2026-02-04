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
from testutils import SampleTestHelper, skip_if_azure_functions_integration_tests_disabled

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.sample("11_workflow_parallel"),
    pytest.mark.usefixtures("function_app_for_test"),
    skip_if_azure_functions_integration_tests_disabled,
]


@pytest.mark.orchestration
class TestWorkflowParallel:
    """Tests for 11_workflow_parallel sample."""

    def test_parallel_workflow_document_analysis(self, base_url: str) -> None:
        """Test parallel workflow with a standard document."""
        payload = {
            "document_id": "doc-test-001",
            "content": (
                "The quarterly earnings report shows strong growth in our cloud services division. "
                "Revenue increased by 25% compared to last year, driven by enterprise adoption. "
                "Customer satisfaction remains high at 92%. However, we face challenges in the "
                "mobile segment where competition is intense. Overall, the outlook is positive "
                "with expected continued growth in the coming quarters."
            ),
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data

        # Wait for completion - parallel workflows may take longer
        status = SampleTestHelper.wait_for_orchestration_with_output(
            data["statusQueryGetUri"],
            max_wait=300,  # 5 minutes for parallel execution
        )
        assert status["runtimeStatus"] == "Completed"
        assert "output" in status

    def test_parallel_workflow_short_document(self, base_url: str) -> None:
        """Test parallel workflow with a short document."""
        payload = {
            "document_id": "doc-test-002",
            "content": "Quick update: Project completed successfully. Team performance exceeded expectations.",
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data

        # Wait for completion
        status = SampleTestHelper.wait_for_orchestration_with_output(data["statusQueryGetUri"], max_wait=300)
        assert status["runtimeStatus"] == "Completed"
        assert "output" in status

    def test_parallel_workflow_technical_document(self, base_url: str) -> None:
        """Test parallel workflow with a technical document."""
        payload = {
            "document_id": "doc-test-003",
            "content": (
                "The new microservices architecture has been deployed to production. "
                "Key improvements include: reduced latency by 40%, improved scalability "
                "to handle 10x traffic spikes, and enhanced monitoring with distributed tracing. "
                "The Kubernetes cluster is now running on version 1.28 with auto-scaling enabled. "
                "Next steps include implementing service mesh and improving CI/CD pipelines."
            ),
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data

        # Wait for completion
        status = SampleTestHelper.wait_for_orchestration_with_output(data["statusQueryGetUri"], max_wait=300)
        assert status["runtimeStatus"] == "Completed"

    def test_workflow_status_endpoint(self, base_url: str) -> None:
        """Test that the workflow status endpoint works correctly."""
        payload = {
            "document_id": "doc-test-004",
            "content": "Brief status update for testing purposes.",
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        instance_id = data["instanceId"]

        # Check status
        status_response = SampleTestHelper.get(f"{base_url}/api/workflow/status/{instance_id}")
        assert status_response.status_code == 200
        status = status_response.json()
        assert "instanceId" in status
        assert status["instanceId"] == instance_id

        # Wait for completion
        SampleTestHelper.wait_for_orchestration(data["statusQueryGetUri"], max_wait=300)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
