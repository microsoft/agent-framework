# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for Workflow No Shared State Sample

Tests the workflow sample that runs without shared state,
demonstrating conditional routing with spam detection and email response.

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite running for durable orchestrations (or Azure Storage account configured)

Usage:
    # Start Azurite (if not already running)
    azurite &

    # Run tests
    uv run pytest packages/azurefunctions/tests/integration_tests/test_10_workflow_no_shared_state.py -v
"""

import pytest
from testutils import SampleTestHelper, skip_if_azure_functions_integration_tests_disabled

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.sample("10_workflow_no_shared_state"),
    pytest.mark.usefixtures("function_app_for_test"),
    skip_if_azure_functions_integration_tests_disabled,
]


@pytest.mark.orchestration
class TestWorkflowNoSharedState:
    """Tests for 10_workflow_no_shared_state sample."""

    def test_workflow_with_spam_email(self, base_url: str) -> None:
        """Test workflow with spam email - should detect and handle as spam."""
        payload = {
            "email_id": "email-test-001",
            "email_content": (
                "URGENT! You've won $1,000,000! Click here immediately to claim your prize! "
                "Limited time offer - act now!"
            ),
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data

        # Wait for completion
        status = SampleTestHelper.wait_for_orchestration_with_output(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"
        assert "output" in status

    def test_workflow_with_legitimate_email(self, base_url: str) -> None:
        """Test workflow with legitimate email - should draft a response."""
        payload = {
            "email_id": "email-test-002",
            "email_content": (
                "Hi team, just a reminder about our sprint planning meeting tomorrow at 10 AM. "
                "Please review the agenda in Jira."
            ),
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data

        # Wait for completion
        status = SampleTestHelper.wait_for_orchestration_with_output(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"
        assert "output" in status

    def test_workflow_status_endpoint(self, base_url: str) -> None:
        """Test that the status endpoint works correctly."""
        payload = {
            "email_id": "email-test-003",
            "email_content": "Quick question: When is the next team meeting scheduled?",
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        instance_id = data["instanceId"]

        # Check status using the workflow status endpoint
        status_response = SampleTestHelper.get(f"{base_url}/api/workflow/status/{instance_id}")
        assert status_response.status_code == 200
        status = status_response.json()
        assert "instanceId" in status
        assert status["instanceId"] == instance_id
        assert "runtimeStatus" in status

        # Wait for completion to clean up
        SampleTestHelper.wait_for_orchestration(data["statusQueryGetUri"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
