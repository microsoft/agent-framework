# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for Workflow Human-in-the-Loop (HITL) Sample

Tests the workflow HITL sample demonstrating content moderation with human approval
using the MAF request_info / @response_handler pattern.

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite running for durable orchestrations (or Azure Storage account configured)

Usage:
    # Start Azurite (if not already running)
    azurite &

    # Run tests
    uv run pytest packages/azurefunctions/tests/integration_tests/test_12_workflow_hitl.py -v
"""

import time

import pytest
from testutils import SampleTestHelper, skip_if_azure_functions_integration_tests_disabled

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.sample("12_workflow_hitl"),
    pytest.mark.usefixtures("function_app_for_test"),
    skip_if_azure_functions_integration_tests_disabled,
]


@pytest.mark.orchestration
class TestWorkflowHITL:
    """Tests for 12_workflow_hitl sample."""

    @pytest.fixture(autouse=True)
    def _set_base_url(self, base_url: str) -> None:
        """Store the base URL for tests."""
        self.base_url = base_url

    def _wait_for_hitl_request(self, instance_id: str, timeout: int = 40) -> dict:
        """Polls for a pending HITL request."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            status_response = SampleTestHelper.get(f"{self.base_url}/api/workflow/status/{instance_id}")
            if status_response.status_code == 200:
                status = status_response.json()
                pending_requests = status.get("pendingHumanInputRequests", [])
                if pending_requests:
                    return status
            time.sleep(2)
        raise AssertionError(f"Timed out waiting for HITL request for instance {instance_id}")

    def test_hitl_workflow_approval(self) -> None:
        """Test HITL workflow with human approval."""
        payload = {
            "content_id": "article-test-001",
            "title": "Introduction to AI in Healthcare",
            "body": (
                "Artificial intelligence is revolutionizing healthcare by enabling faster diagnosis, "
                "personalized treatment plans, and improved patient outcomes. Machine learning algorithms "
                "can analyze medical images with remarkable accuracy."
            ),
            "author": "Dr. Jane Smith",
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{self.base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        assert "instanceId" in data
        assert "statusQueryGetUri" in data
        instance_id = data["instanceId"]

        # Wait for the workflow to reach the HITL pause point
        status = self._wait_for_hitl_request(instance_id)

        # Confirm status is valid
        assert status["runtimeStatus"] in ["Running", "Pending"]

        # Get the request ID from pending requests
        pending_requests = status.get("pendingHumanInputRequests", [])
        assert len(pending_requests) > 0, "Expected pending HITL request"
        request_id = pending_requests[0]["requestId"]

        # Send approval
        approval_response = SampleTestHelper.post_json(
            f"{self.base_url}/api/workflow/respond/{instance_id}/{request_id}",
            {"approved": True, "reviewer_notes": "Content is appropriate and well-written."},
        )
        assert approval_response.status_code == 200

        # Wait for orchestration to complete
        final_status = SampleTestHelper.wait_for_orchestration(data["statusQueryGetUri"])
        assert final_status["runtimeStatus"] == "Completed"
        assert "output" in final_status

    def test_hitl_workflow_rejection(self) -> None:
        """Test HITL workflow with human rejection."""
        payload = {
            "content_id": "article-test-002",
            "title": "Get Rich Quick Scheme",
            "body": (
                "Click here NOW to make $10,000 overnight! This SECRET method is GUARANTEED to work! "
                "Limited time offer - act NOW before it's too late!"
            ),
            "author": "Definitely Not Spam",
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{self.base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        instance_id = data["instanceId"]

        # Wait for the workflow to reach the HITL pause point
        status = self._wait_for_hitl_request(instance_id)

        # Get the request ID from pending requests
        pending_requests = status.get("pendingHumanInputRequests", [])
        assert len(pending_requests) > 0, "Expected pending HITL request"
        request_id = pending_requests[0]["requestId"]

        # Send rejection
        rejection_response = SampleTestHelper.post_json(
            f"{self.base_url}/api/workflow/respond/{instance_id}/{request_id}",
            {"approved": False, "reviewer_notes": "Content appears to be spam/scam material."},
        )
        assert rejection_response.status_code == 200

        # Wait for orchestration to complete
        final_status = SampleTestHelper.wait_for_orchestration(data["statusQueryGetUri"])
        assert final_status["runtimeStatus"] == "Completed"
        assert "output" in final_status
        # The output should indicate rejection
        output = final_status["output"]
        assert "rejected" in str(output).lower()

    def test_hitl_workflow_status_endpoint(self) -> None:
        """Test that the workflow status endpoint shows pending HITL requests."""
        payload = {
            "content_id": "article-test-003",
            "title": "Test Article",
            "body": "This is a test article for checking status endpoint functionality.",
            "author": "Test Author",
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{self.base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        instance_id = data["instanceId"]

        # Wait for HITL pause
        status = self._wait_for_hitl_request(instance_id)

        # Check status
        assert "instanceId" in status
        assert status["instanceId"] == instance_id
        assert "runtimeStatus" in status
        assert "pendingHumanInputRequests" in status

        # Clean up: approve to complete
        pending_requests = status.get("pendingHumanInputRequests", [])
        if pending_requests:
            request_id = pending_requests[0]["requestId"]
            SampleTestHelper.post_json(
                f"{self.base_url}/api/workflow/respond/{instance_id}/{request_id}",
                {"approved": True, "reviewer_notes": ""},
            )

        # Wait for completion
        SampleTestHelper.wait_for_orchestration(data["statusQueryGetUri"])

    def test_hitl_workflow_with_neutral_content(self) -> None:
        """Test HITL workflow with neutral content that should get medium risk."""
        payload = {
            "content_id": "article-test-004",
            "title": "Product Review",
            "body": (
                "This product works as advertised. The build quality is average and the price "
                "is reasonable. I would recommend it for basic use cases but not for professional work."
            ),
            "author": "Regular User",
        }

        # Start orchestration
        response = SampleTestHelper.post_json(f"{self.base_url}/api/workflow/run", payload)
        assert response.status_code == 202
        data = response.json()
        instance_id = data["instanceId"]

        # Wait for HITL pause
        status = self._wait_for_hitl_request(instance_id)

        pending_requests = status.get("pendingHumanInputRequests", [])
        assert len(pending_requests) > 0
        request_id = pending_requests[0]["requestId"]

        # Approve
        SampleTestHelper.post_json(
            f"{self.base_url}/api/workflow/respond/{instance_id}/{request_id}",
            {"approved": True, "reviewer_notes": "Approved after review."},
        )

        # Wait for completion
        final_status = SampleTestHelper.wait_for_orchestration(data["statusQueryGetUri"])
        assert final_status["runtimeStatus"] == "Completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
