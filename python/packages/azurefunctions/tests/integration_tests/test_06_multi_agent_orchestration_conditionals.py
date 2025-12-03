# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for MultiAgent Conditionals Sample

Tests the multi-agent conditionals sample for conditional orchestration logic.

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite running for durable orchestrations (or Azure Storage account configured)

Usage:
    # Start Azurite (if not already running)
    azurite &

    # Run tests
    uv run pytest packages/azurefunctions/tests/integration_tests/test_06_multi_agent_orchestration_conditionals.py -v
"""

import pytest

from .testutils import SampleTestHelper, skip_if_azure_functions_integration_tests_disabled

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.orchestration,
    pytest.mark.sample("06_multi_agent_orchestration_conditionals"),
    pytest.mark.usefixtures("function_app_for_test"),
    skip_if_azure_functions_integration_tests_disabled,
]


class TestSampleMultiAgentConditionals:
    """Tests for 06_multi_agent_orchestration_conditionals sample."""

    def test_legitimate_email(self, base_url: str) -> None:
        """Test conditional logic with legitimate email."""
        response = SampleTestHelper.post_json(
            f"{base_url}/api/spamdetection/run",
            {
                "email_id": "email-test-001",
                "email_content": "Hi John, I hope you are doing well. Can you send me the report?",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data

        # Wait for completion
        status = SampleTestHelper.wait_for_orchestration(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"
        assert "Email sent:" in status["output"]

    def test_spam_email(self, base_url: str) -> None:
        """Test conditional logic with spam email."""
        response = SampleTestHelper.post_json(
            f"{base_url}/api/spamdetection/run",
            {"email_id": "email-test-002", "email_content": "URGENT! You have won $1,000,000! Click here now!"},
        )
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data

        # Wait for completion
        status = SampleTestHelper.wait_for_orchestration(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"
        assert "Email marked as spam:" in status["output"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
