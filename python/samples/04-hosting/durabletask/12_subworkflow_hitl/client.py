# Copyright (c) Microsoft. All rights reserved.

"""Client that drives the composed HITL workflow, responding to a nested sub-workflow request.

The worker (``worker.py``) must be running first. This client:

1. Starts the *outer* workflow with ``DurableWorkflowClient.start_workflow``.
2. Polls ``get_pending_hitl_requests`` until a request appears. Because the HITL pause
   happens inside a sub-workflow, the request surfaces with a **qualified** request id
   (``review_sub::{requestId}``).
3. Sends the decision with ``send_hitl_response`` against the *top-level* instance id and
   the qualified request id; the host routes it to the owning child orchestration.
4. Reads the final output with ``await_workflow_output``.

It runs two cases: approved content and rejected content.

Prerequisites:
- ``worker.py`` running and connected to the same Durable Task Scheduler.
- A Durable Task Scheduler reachable at ``ENDPOINT`` (default ``http://localhost:8080``).
"""

import asyncio
import logging
import os
import time
from typing import Any

from agent_framework.azure import DurableWorkflowClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from durabletask.azuremanaged.client import DurableTaskSchedulerClient

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The client targets the outer workflow; the HITL pause lives in the sub-workflow.
WORKFLOW_NAME = "moderation_pipeline"


def get_client(taskhub: str | None = None, endpoint: str | None = None) -> DurableTaskSchedulerClient:
    """Create a configured DurableTaskSchedulerClient."""
    taskhub_name = taskhub or os.getenv("TASKHUB", "default")
    endpoint_url = endpoint or os.getenv("ENDPOINT", "http://localhost:8080")

    credential = None if endpoint_url == "http://localhost:8080" else AzureCliCredential()

    return DurableTaskSchedulerClient(
        host_address=endpoint_url,
        secure_channel=endpoint_url != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential,
    )


def _wait_for_hitl_request(
    client: DurableWorkflowClient, instance_id: str, timeout_seconds: int = 60
) -> list[dict[str, Any]]:
    """Poll until the workflow (or one of its sub-workflows) has a pending HITL request.

    Stops early if the workflow reaches a terminal state without pausing, so a
    misconfiguration surfaces the real status instead of a misleading timeout.
    """
    terminal_statuses = {"COMPLETED", "FAILED", "TERMINATED"}
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        pending = client.get_pending_hitl_requests(instance_id)
        if pending:
            return pending
        status = client.get_runtime_status(instance_id)
        if status in terminal_statuses:
            raise RuntimeError(
                f"Workflow instance {instance_id} reached terminal state '{status}' before pausing for human input."
            )
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for a HITL request on instance {instance_id}")


def run_case(client: DurableWorkflowClient, submission: dict[str, Any], *, approve: bool) -> None:
    """Run one moderation case: start, respond to the nested HITL pause, print the result."""
    instance_id = client.start_workflow(input=submission)
    logger.info("Started workflow instance: %s", instance_id)

    pending = _wait_for_hitl_request(client, instance_id)
    request = pending[0]
    # The request id is qualified (e.g. "review_sub::<uuid>") because the pause lives
    # in a sub-workflow. We pass it back verbatim against the top-level instance id;
    # the host resolves it to the owning child orchestration.
    logger.info("Pending HITL request %s from %s", request["request_id"], request["source_executor_id"])

    decision = {
        "approved": approve,
        "reviewer_notes": "Looks good." if approve else "Violates content policy.",
    }
    client.send_hitl_response(instance_id, request["request_id"], decision)
    logger.info("Sent decision: approved=%s", approve)

    output = client.await_workflow_output(instance_id)
    logger.info("Workflow output: %s", output)


async def main() -> None:
    """Run an approved case and a rejected case."""
    client = DurableWorkflowClient(get_client(), workflow_name=WORKFLOW_NAME)

    logger.info("CASE 1: Appropriate content (will approve)")
    run_case(
        client,
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

    logger.info("CASE 2: Spammy content (will reject)")
    run_case(
        client,
        {
            "content_id": "article-002",
            "title": "Get Rich Quick",
            "body": "Click here NOW to make $10,000 overnight! GUARANTEED! Limited time offer!",
        },
        approve=False,
    )


if __name__ == "__main__":
    asyncio.run(main())
