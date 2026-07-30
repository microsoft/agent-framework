# Copyright (c) Microsoft. All rights reserved.

"""Client that starts the composed workflow orchestration and prints the result.

The worker (``worker.py``) must be running first. Only the *outer* workflow is
started by the client; its embedded sub-workflow runs automatically as a durable
child orchestration when the outer workflow reaches the ``WorkflowExecutor`` node.

The workflow is started via ``DurableWorkflowClient.start_workflow`` - which
schedules the ``dafx-review_pipeline`` orchestration that
``DurableAIAgentWorker.configure_workflow`` auto-registers for the outer workflow.

Prerequisites:
- ``worker.py`` running and connected to the same Durable Task Scheduler.
- A Durable Task Scheduler reachable at ``ENDPOINT`` (default ``http://localhost:8080``).
"""

import asyncio
import logging
import os

from agent_framework.azure import DurableWorkflowClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from durabletask.azuremanaged.client import DurableTaskSchedulerClient

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The client targets the outer workflow; the sub-workflow runs as a child orchestration.
WORKFLOW_NAME = "review_pipeline"


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


def run_workflow(client: DurableWorkflowClient, review: str) -> None:
    """Start the outer workflow with a review and wait for the result."""
    instance_id = client.start_workflow(input=review)
    logger.info("Started workflow instance: %s", instance_id)

    output = client.await_workflow_output(instance_id)
    logger.info("Workflow output: %s", output)


async def main() -> None:
    """Run the composed workflow against a couple of product reviews."""
    client = DurableWorkflowClient(get_client(), workflow_name=WORKFLOW_NAME)

    logger.info("TEST 1: Positive review")
    run_workflow(
        client,
        "Absolutely love this espresso machine - it heats up fast and the coffee is consistently great.",
    )

    logger.info("TEST 2: Negative review")
    run_workflow(
        client,
        "Disappointed. The device stopped working after two weeks and support never replied.",
    )


if __name__ == "__main__":
    asyncio.run(main())
