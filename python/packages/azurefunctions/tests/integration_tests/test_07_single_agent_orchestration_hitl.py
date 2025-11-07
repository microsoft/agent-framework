# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for Human-in-the-Loop (HITL) Orchestration Sample

Tests the HITL orchestration sample for content generation with human approval workflow.

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite running for durable orchestrations (or Azure Storage account configured)

Usage:
    # Start Azurite (if not already running)
    azurite &

    # Run tests
    uv run pytest packages/azurefunctions/tests/integration_tests/test_07_single_agent_orchestration_hitl.py -v
"""

import time

import pytest

from .testutils import SampleTestHelper, skip_if_azure_functions_integration_tests_disabled

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.sample("07_single_agent_orchestration_hitl"),
    pytest.mark.usefixtures("function_app_for_test"),
    skip_if_azure_functions_integration_tests_disabled,
]


@pytest.mark.orchestration
class TestSampleHITLOrchestration:
    """Tests for 07_single_agent_orchestration_hitl sample."""

    @pytest.fixture(autouse=True)
    def _set_hitl_base_url(self, base_url: str) -> None:
        """Prepare the HITL API base URL for the module's tests."""
        self.hitl_base_url = f"{base_url}/api/hitl"

    def test_hitl_orchestration_approval(self) -> None:
        """Test HITL orchestration with human approval."""
        # Start orchestration
        response = SampleTestHelper.post_json(
            f"{self.hitl_base_url}/run",
            {"topic": "artificial intelligence", "max_review_attempts": 3, "approval_timeout_hours": 1.0},
        )
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data
        assert data["topic"] == "artificial intelligence"
        instance_id = data["instanceId"]

        # Wait a bit for the orchestration to generate initial content
        time.sleep(5)

        # Check status to ensure it's waiting for approval
        status_response = SampleTestHelper.get(data["statusQueryGetUri"])
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["runtimeStatus"] in ["Running", "Pending"]

        # Send approval
        approval_response = SampleTestHelper.post_json(
            f"{self.hitl_base_url}/approve/{instance_id}", {"approved": True, "feedback": ""}
        )
        assert approval_response.status_code == 200
        approval_data = approval_response.json()
        assert approval_data["approved"] is True

        # Wait for orchestration to complete
        status = SampleTestHelper.wait_for_orchestration(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"
        assert "output" in status
        assert "content" in status["output"]

    def test_hitl_orchestration_rejection_with_feedback(self) -> None:
        """Test HITL orchestration with rejection and subsequent approval."""
        # Start orchestration
        response = SampleTestHelper.post_json(
            f"{self.hitl_base_url}/run",
            {"topic": "machine learning", "max_review_attempts": 3, "approval_timeout_hours": 1.0},
        )
        assert response.status_code == 202
        data = response.json()
        instance_id = data["instanceId"]

        # Wait for initial content generation
        time.sleep(5)

        # Send rejection with feedback
        rejection_response = SampleTestHelper.post_json(
            f"{self.hitl_base_url}/approve/{instance_id}",
            {"approved": False, "feedback": "Please make it more concise and focus on practical applications."},
        )
        assert rejection_response.status_code == 200

        # Wait for regeneration
        time.sleep(5)

        # Check status - should still be running
        status_response = SampleTestHelper.get(data["statusQueryGetUri"])
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["runtimeStatus"] in ["Running", "Pending"]

        # Now approve the revised content
        approval_response = SampleTestHelper.post_json(
            f"{self.hitl_base_url}/approve/{instance_id}", {"approved": True, "feedback": ""}
        )
        assert approval_response.status_code == 200

        # Wait for completion
        status = SampleTestHelper.wait_for_orchestration(data["statusQueryGetUri"])
        assert status["runtimeStatus"] == "Completed"
        assert "output" in status

    def test_hitl_orchestration_missing_topic(self) -> None:
        """Test HITL orchestration with missing topic."""
        response = SampleTestHelper.post_json(f"{self.hitl_base_url}/run", {"max_review_attempts": 3})
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_hitl_get_status(self) -> None:
        """Test getting orchestration status."""
        # Start orchestration
        response = SampleTestHelper.post_json(
            f"{self.hitl_base_url}/run",
            {"topic": "quantum computing", "max_review_attempts": 2, "approval_timeout_hours": 1.0},
        )
        assert response.status_code == 202
        data = response.json()
        instance_id = data["instanceId"]

        # Get status
        status_response = SampleTestHelper.get(f"{self.hitl_base_url}/status/{instance_id}")
        assert status_response.status_code == 200
        status = status_response.json()
        assert "instanceId" in status
        assert "runtimeStatus" in status
        assert status["instanceId"] == instance_id

        # Cleanup: approve to complete orchestration
        time.sleep(5)
        SampleTestHelper.post_json(f"{self.hitl_base_url}/approve/{instance_id}", {"approved": True, "feedback": ""})

    def test_hitl_approval_invalid_payload(self) -> None:
        """Test sending approval with invalid payload."""
        # Start orchestration first
        response = SampleTestHelper.post_json(
            f"{self.hitl_base_url}/run",
            {"topic": "test topic", "max_review_attempts": 1, "approval_timeout_hours": 1.0},
        )
        assert response.status_code == 202
        data = response.json()
        instance_id = data["instanceId"]

        time.sleep(3)

        # Send approval without 'approved' field
        approval_response = SampleTestHelper.post_json(
            f"{self.hitl_base_url}/approve/{instance_id}", {"feedback": "Some feedback"}
        )
        assert approval_response.status_code == 400
        error_data = approval_response.json()
        assert "error" in error_data

        # Cleanup
        SampleTestHelper.post_json(f"{self.hitl_base_url}/approve/{instance_id}", {"approved": True, "feedback": ""})

    def test_hitl_status_invalid_instance(self) -> None:
        """Test getting status for non-existent instance."""
        response = SampleTestHelper.get(f"{self.hitl_base_url}/status/invalid-instance-id")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
