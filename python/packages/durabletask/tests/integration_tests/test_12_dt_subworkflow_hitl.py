# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for the composed sub-workflow HITL sample (12_subworkflow_hitl).

Exercises human-in-the-loop **inside a nested sub-workflow** on a standalone
durabletask worker:
- An outer ``moderation_pipeline`` embeds an inner ``human_review`` workflow via a
  ``WorkflowExecutor`` node (``review_sub``); on the durable host the inner workflow
  runs as a child orchestration.
- The inner ``review_gate`` pauses via ``request_info``. The pending request surfaces
  at the top-level instance with a **qualified** id ``review_sub~0~{requestId}`` (the
  ``~{ordinal}~`` hop addresses the specific child the node dispatched).
- The client responds with that qualified id against the *top-level* instance and the
  host routes it to the owning child orchestration, resuming to an approved/rejected
  outcome.

This sample hosts **no AI agents**, so it needs only the DTS emulator (no model
credentials), which makes it a deterministic end-to-end check of the nested-HITL
addressing.
"""

import logging
import time
from typing import Any

import pytest

from agent_framework_durabletask import DurableWorkflowClient
from agent_framework_durabletask._workflows.naming import SUBWORKFLOW_REQUEST_SEPARATOR

logging.basicConfig(level=logging.WARNING)

# Must match the outer workflow name in samples/04-hosting/durabletask/12_subworkflow_hitl/worker.py
WORKFLOW_NAME = "moderation_pipeline"
# The WorkflowExecutor node id that embeds the inner HITL workflow.
SUBWORKFLOW_NODE_ID = "review_sub"

# Module-level markers. No requires_azure_openai: the sample hosts no agents.
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("12_subworkflow_hitl"),
    pytest.mark.integration_test,
    pytest.mark.requires_dts,
]


def _wait_for_hitl_request(
    client: DurableWorkflowClient, instance_id: str, timeout_seconds: int = 90
) -> list[dict[str, Any]]:
    """Poll until the workflow (or a nested sub-workflow) records a pending HITL request."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        pending = client.get_pending_hitl_requests(instance_id, workflow_name=WORKFLOW_NAME)
        if pending:
            return pending
        time.sleep(2)
    raise AssertionError(f"Timed out waiting for a nested HITL request on instance {instance_id}")


class TestSubworkflowHITL:
    """Nested (sub-workflow) human-in-the-loop on a standalone durabletask worker."""

    @pytest.fixture(autouse=True)
    def setup(self, workflow_client: DurableWorkflowClient) -> None:
        """Bind the DurableWorkflowClient for the current sample worker."""
        self.client = workflow_client

    def _run_case(self, submission: dict[str, Any], *, approve: bool) -> tuple[dict[str, Any], Any]:
        """Start a moderation case, answer the nested HITL pause, return (request, output)."""
        instance_id = self.client.start_workflow(input=submission, workflow_name=WORKFLOW_NAME)

        pending = _wait_for_hitl_request(self.client, instance_id)
        request = pending[0]

        self.client.send_hitl_response(
            instance_id,
            request["request_id"],
            {"approved": approve, "reviewer_notes": "Looks good." if approve else "Violates content policy."},
            workflow_name=WORKFLOW_NAME,
        )

        output = self.client.await_workflow_output(instance_id, workflow_name=WORKFLOW_NAME, timeout_seconds=180)
        return request, output

    def test_nested_request_id_is_qualified_with_ordinal(self) -> None:
        """The nested pending request surfaces with a ``review_sub~0~{id}`` qualified id."""
        instance_id = self.client.start_workflow(
            input={
                "content_id": "article-100",
                "title": "Quarterly Roadmap",
                "body": "A summary of the upcoming features planned for the next quarter.",
            },
            workflow_name=WORKFLOW_NAME,
        )

        pending = _wait_for_hitl_request(self.client, instance_id)

        assert len(pending) == 1
        request = pending[0]
        # The qualifier carries the node id and the child's ordinal (0 for the single
        # dispatch), then the inner bare request id: ``review_sub~0~{requestId}``.
        expected_prefix = f"{SUBWORKFLOW_NODE_ID}{SUBWORKFLOW_REQUEST_SEPARATOR}0{SUBWORKFLOW_REQUEST_SEPARATOR}"
        assert request["request_id"].startswith(expected_prefix), request["request_id"]
        # The bare inner id is non-empty after the qualifier.
        assert request["request_id"][len(expected_prefix) :]
        # The originating executor is the inner workflow's review gate.
        assert request["source_executor_id"] == "review_gate"

        # Drain the pause so the worker does not leave the instance hanging.
        self.client.send_hitl_response(
            instance_id,
            request["request_id"],
            {"approved": True, "reviewer_notes": "ok"},
            workflow_name=WORKFLOW_NAME,
        )
        self.client.await_workflow_output(instance_id, workflow_name=WORKFLOW_NAME, timeout_seconds=180)

    def test_nested_hitl_approval(self) -> None:
        """Responding 'approved' to the nested request resumes the outer workflow to APPROVED."""
        _request, output = self._run_case(
            {
                "content_id": "article-001",
                "title": "Introduction to AI in Healthcare",
                "body": (
                    "Artificial intelligence is improving healthcare by enabling faster diagnosis, "
                    "personalized treatment plans, and better patient outcomes."
                ),
            },
            approve=True,
        )

        assert output is not None
        assert "APPROVED" in str(output).upper()

    def test_nested_hitl_rejection(self) -> None:
        """Responding 'rejected' to the nested request resumes the outer workflow to REJECTED."""
        _request, output = self._run_case(
            {
                "content_id": "article-002",
                "title": "Get Rich Quick",
                "body": "Click here NOW to make $10,000 overnight! GUARANTEED! Limited time offer!",
            },
            approve=False,
        )

        assert output is not None
        assert "REJECTED" in str(output).upper()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
