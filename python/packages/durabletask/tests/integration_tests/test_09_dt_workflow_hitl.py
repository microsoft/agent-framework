# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for the standalone durabletask HITL workflow sample (09_workflow_hitl).

Exercises the human-in-the-loop workflow path on a standalone durabletask worker:
- The ``InputRouter`` start executor receives a typed ``ContentSubmission`` that the
  shared engine reconstructs from the client's JSON payload (no manual parsing).
- An analysis agent produces a recommendation, then the workflow pauses for human
  approval via ``request_info``.
- The client retrieves the pending request, replies with ``send_hitl_response``, and
  the workflow resumes to an approved/rejected outcome read via ``await_workflow_output``.
"""

import logging
import time
from typing import Any

import pytest

from agent_framework_durabletask import DurableWorkflowClient

logging.basicConfig(level=logging.WARNING)

# Module-level markers
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("09_workflow_hitl"),
    pytest.mark.integration_test,
    pytest.mark.requires_dts,
    pytest.mark.requires_azure_openai,
]


def _wait_for_hitl_request(
    client: DurableWorkflowClient, instance_id: str, timeout_seconds: int = 90
) -> list[dict[str, Any]]:
    """Poll until the workflow records at least one pending HITL request."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        pending = client.get_pending_hitl_requests(instance_id)
        if pending:
            return pending
        time.sleep(2)
    raise AssertionError(f"Timed out waiting for a HITL request on instance {instance_id}")


class TestStandaloneWorkflowHITL:
    """Human-in-the-loop workflow execution on a standalone durabletask worker."""

    @pytest.fixture(autouse=True)
    def setup(self, workflow_client: DurableWorkflowClient) -> None:
        """Bind the DurableWorkflowClient for the current sample worker."""
        self.client = workflow_client

    def _run_case(self, submission: dict[str, Any], *, approve: bool) -> Any:
        """Start a moderation case, answer the HITL pause, and return the final output."""
        instance_id = self.client.start_workflow(input=submission)

        pending = _wait_for_hitl_request(self.client, instance_id)
        request = pending[0]
        assert request["request_id"]
        assert request["source_executor_id"]

        self.client.send_hitl_response(
            instance_id,
            request["request_id"],
            {"approved": approve, "reviewer_notes": "Looks good." if approve else "Violates content policy."},
        )

        return self.client.await_workflow_output(instance_id, timeout_seconds=180)

    def test_hitl_workflow_approval(self) -> None:
        """Appropriate content is approved after the reviewer says yes."""
        output = self._run_case(
            {
                "content_id": "article-001",
                "title": "Introduction to AI in Healthcare",
                "body": (
                    "Artificial intelligence is improving healthcare by enabling faster diagnosis, "
                    "personalized treatment plans, and better patient outcomes."
                ),
                "author": "Dr. Jane Smith",
            },
            approve=True,
        )

        assert output is not None
        assert "APPROVED" in str(output).upper()

    def test_hitl_workflow_rejection(self) -> None:
        """Spammy content is rejected after the reviewer says no."""
        output = self._run_case(
            {
                "content_id": "article-002",
                "title": "Get Rich Quick",
                "body": "Click here NOW to make $10,000 overnight! GUARANTEED! Limited time offer!",
                "author": "Definitely Not Spam",
            },
            approve=False,
        )

        assert output is not None
        assert "REJECTED" in str(output).upper()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
