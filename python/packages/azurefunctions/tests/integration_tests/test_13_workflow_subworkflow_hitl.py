# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for the Sub-workflow HITL Sample (13_subworkflow_hitl)

Tests nested human-in-the-loop through the Azure Functions host: the HITL pause
lives inside an inner workflow embedded via ``WorkflowExecutor``, so the pending
request surfaces at the top-level instance with a **qualified** request id
(``review_sub~0~{requestId}``). The caller responds against the top-level instance
and the host routes it to the owning child orchestration.

This sample hosts no AI agents, so it exercises the AF nested-HITL plumbing
deterministically (no model latency / variability).

The function app is automatically started by the test fixture.

Prerequisites:
- Azurite running for durable orchestrations
- Durable Task Scheduler emulator running on localhost:8080

Usage:
    uv run pytest packages/azurefunctions/tests/integration_tests/test_13_workflow_subworkflow_hitl.py -v
"""

import time
import uuid

import pytest

from agent_framework_azurefunctions import WorkflowHitlContext

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("13_subworkflow_hitl"),
    pytest.mark.usefixtures("function_app_for_test"),
]

# Must match the outer workflow name in samples/.../13_subworkflow_hitl/function_app.py
WORKFLOW_NAME = "moderation_pipeline"
# The WorkflowExecutor node id that embeds the inner HITL workflow.
SUBWORKFLOW_NODE_ID = "review_sub"


@pytest.mark.orchestration
class TestSubworkflowHITL:
    """Tests for the 13_subworkflow_hitl sample (nested HITL behind one surface)."""

    @pytest.fixture(autouse=True)
    def _setup(self, base_url: str, sample_helper) -> None:
        """Provide the helper and base URL for each test."""
        self.base_url = base_url
        self.helper = sample_helper

    def _wait_for_hitl_request(self, instance_id: str, timeout: int = 40) -> dict:
        """Poll the top-level status endpoint until a (nested) HITL request appears."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            status_response = self.helper.get(f"{self.base_url}/api/workflow/{WORKFLOW_NAME}/status/{instance_id}")
            if status_response.status_code == 200:
                status = status_response.json()
                if status.get("pendingHumanInputRequests"):
                    return status
            time.sleep(2)
        raise AssertionError(f"Timed out waiting for a nested HITL request for instance {instance_id}")

    def _start(self, payload: dict) -> dict:
        """Start the outer workflow and return the run response JSON."""
        response = self.helper.post_json(f"{self.base_url}/api/workflow/{WORKFLOW_NAME}/run", payload)
        assert response.status_code == 202
        return response.json()

    def test_nested_request_surfaces_with_qualified_id(self) -> None:
        """The nested pending request is surfaced with a ``review_sub~0~{id}`` qualified id."""
        data = self._start({
            "content_id": "article-100",
            "title": "Quarterly Roadmap",
            "body": "A summary of the upcoming features planned for the next quarter.",
        })
        instance_id = data["instanceId"]

        status = self._wait_for_hitl_request(instance_id)
        pending = status.get("pendingHumanInputRequests", [])
        assert len(pending) == 1
        request_id = pending[0]["requestId"]

        # The qualifier carries the node id and the child's ordinal (0 for the single
        # dispatch), then the inner bare request id: ``review_sub~0~{requestId}``.
        expected_prefix = f"{SUBWORKFLOW_NODE_ID}~0~"
        assert request_id.startswith(expected_prefix), request_id
        assert request_id[len(expected_prefix) :]  # non-empty inner id

        # The respondUrl always targets the top-level instance.
        assert f"/api/workflow/{WORKFLOW_NAME}/respond/{instance_id}/" in pending[0]["respondUrl"]

        # Drain the pause so the instance does not hang.
        approve = self.helper.post_json(
            f"{self.base_url}/api/workflow/{WORKFLOW_NAME}/respond/{instance_id}/{request_id}",
            {"approved": True, "reviewer_notes": "ok"},
        )
        assert approve.status_code == 200
        self.helper.wait_for_orchestration(data["statusQueryGetUri"])

    def test_nested_hitl_approval(self) -> None:
        """Responding 'approved' to the nested request resumes the outer workflow to APPROVED."""
        data = self._start({
            "content_id": "article-001",
            "title": "Introduction to AI in Healthcare",
            "body": (
                "Artificial intelligence is improving healthcare by enabling faster diagnosis, "
                "personalized treatment plans, and better patient outcomes."
            ),
        })
        instance_id = data["instanceId"]

        status = self._wait_for_hitl_request(instance_id)
        request_id = status["pendingHumanInputRequests"][0]["requestId"]

        approval = self.helper.post_json(
            f"{self.base_url}/api/workflow/{WORKFLOW_NAME}/respond/{instance_id}/{request_id}",
            {"approved": True, "reviewer_notes": "Looks good."},
        )
        assert approval.status_code == 200

        final_status = self.helper.wait_for_orchestration(data["statusQueryGetUri"])
        assert final_status["runtimeStatus"] == "Completed"
        assert "APPROVED" in str(final_status.get("output")).upper()

    def test_nested_hitl_rejection(self) -> None:
        """Responding 'rejected' to the nested request resumes the outer workflow to REJECTED."""
        data = self._start({
            "content_id": "article-002",
            "title": "Get Rich Quick",
            "body": "Click here NOW to make $10,000 overnight! GUARANTEED! Limited time offer!",
        })
        instance_id = data["instanceId"]

        status = self._wait_for_hitl_request(instance_id)
        request_id = status["pendingHumanInputRequests"][0]["requestId"]

        rejection = self.helper.post_json(
            f"{self.base_url}/api/workflow/{WORKFLOW_NAME}/respond/{instance_id}/{request_id}",
            {"approved": False, "reviewer_notes": "Violates content policy."},
        )
        assert rejection.status_code == 200

        final_status = self.helper.wait_for_orchestration(data["statusQueryGetUri"])
        assert final_status["runtimeStatus"] == "Completed"
        assert "REJECTED" in str(final_status.get("output")).upper()

    def test_nested_notify_respond_url_matches_helper(self) -> None:
        """The URL the nested NotifyExecutor builds equals the server's qualified respondUrl.

        Proves the address-propagation path end-to-end: the inner ``notify`` executor
        (running in the child orchestration) builds a respond URL from the propagated
        root instance + ``review_sub~0~`` prefix, given only the inner bare request id,
        and that URL is byte-for-byte the qualified ``respondUrl`` the top-level status
        endpoint exposes -- and POSTing to it resumes the nested run.
        """
        data = self._start({
            "content_id": "article-200",
            "title": "Tide Pool Ecology",
            "body": "Intertidal zones host a surprising diversity of resilient marine life.",
        })
        instance_id = data["instanceId"]

        status = self._wait_for_hitl_request(instance_id)
        pending = status.get("pendingHumanInputRequests", [])
        assert len(pending) == 1
        qualified_id = pending[0]["requestId"]

        # The qualified id is ``review_sub~0~{bare}``; the inner review gate now
        # generates an explicit uuid4 as the bare id.
        prefix = f"{SUBWORKFLOW_NODE_ID}~0~"
        assert qualified_id.startswith(prefix), qualified_id
        bare_id = qualified_id[len(prefix) :]
        uuid.UUID(bare_id)  # raises if the inner id is not a valid uuid4

        # Rebuild the URL exactly as the nested NotifyExecutor does: the root instance
        # and root workflow name, the propagated path prefix, and only the bare id.
        hitl = WorkflowHitlContext(
            instance_id=instance_id,
            workflow_name=WORKFLOW_NAME,
            base_url_override=self.base_url,
            request_path_prefix=prefix,
        )
        helper_url = hitl.build_respond_url(bare_id)
        assert helper_url == pending[0]["respondUrl"]

        # Responding via the helper-built URL resumes the nested run to completion.
        approve = self.helper.post_json(helper_url, {"approved": True, "reviewer_notes": "ok"})
        assert approve.status_code == 200
        final_status = self.helper.wait_for_orchestration(data["statusQueryGetUri"])
        assert final_status["runtimeStatus"] == "Completed"
        assert "APPROVED" in str(final_status.get("output")).upper()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
