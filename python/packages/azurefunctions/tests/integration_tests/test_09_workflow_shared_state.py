# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for Workflow Shared State Sample

Tests the workflow shared state sample for conditional email processing
with shared state management.

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite running for durable orchestrations (or Azure Storage account configured)

Usage:
    # Start Azurite (if not already running)
    azurite &

    # Run tests
    uv run pytest packages/azurefunctions/tests/integration_tests/test_09_workflow_shared_state.py -v
"""

import pytest
from testutils import SampleTestHelper, skip_if_azure_functions_integration_tests_disabled

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.sample("09_workflow_shared_state"),
    pytest.mark.usefixtures("function_app_for_test"),
    skip_if_azure_functions_integration_tests_disabled,
]


@pytest.mark.orchestration
class TestWorkflowSharedState:
    """Tests for 09_workflow_shared_state sample."""

    def test_workflow_with_spam_email(self, base_url: str) -> None:
        """Test workflow with spam email content - should be detected and handled as spam."""
        spam_content = "URGENT! You have won $1,000,000! Click here to claim your prize now before it expires!"

        # Start orchestration with spam email
        response = SampleTestHelper.post_json(f"{base_url}/api/workflow/run", spam_content)
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data

        # Wait for completion
        status = SampleTestHelper.wait_for_orchestration_with_output(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"
        assert "output" in status

    def test_workflow_with_legitimate_email(self, base_url: str) -> None:
        """Test workflow with legitimate email content - should generate response."""
        legitimate_content = (
            "Hi team, just a reminder about the sprint planning meeting tomorrow at 10 AM. "
            "Please review the agenda items in Jira before the call."
        )

        # Start orchestration with legitimate email
        response = SampleTestHelper.post_json(f"{base_url}/api/workflow/run", legitimate_content)
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data

        # Wait for completion
        status = SampleTestHelper.wait_for_orchestration_with_output(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"
        assert "output" in status

    def test_workflow_with_phishing_email(self, base_url: str) -> None:
        """Test workflow with phishing email - should be detected as spam."""
        phishing_content = (
            "Dear Customer, Your account has been compromised! "
            "Click this link immediately to secure your account: http://totallylegit.suspicious.com/secure"
        )

        # Start orchestration with phishing email
        response = SampleTestHelper.post_json(f"{base_url}/api/workflow/run", phishing_content)
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data

        # Wait for completion
        status = SampleTestHelper.wait_for_orchestration_with_output(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
