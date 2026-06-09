# Copyright (c) Microsoft. All rights reserved.

"""Client that starts the standalone workflow orchestration and prints the result.

The worker (``worker.py``) must be running first. The workflow is started via
``DurableWorkflowClient.start_workflow`` - which schedules the orchestrator that
``DurableAIAgentWorker.configure_workflow`` auto-registers, so the caller never
needs to know its internal name.

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


def run_workflow(client: DurableWorkflowClient, email_content: str) -> None:
    """Start the workflow with an email and wait for the result."""
    instance_id = client.start_workflow(input=email_content)
    logger.info("Started workflow instance: %s", instance_id)

    output = client.await_workflow_output(instance_id)
    logger.info("Workflow output: %s", output)


async def main() -> None:
    """Run the workflow against a legitimate email and a spam email."""
    client = DurableWorkflowClient(get_client())

    logger.info("TEST 1: Legitimate email")
    run_workflow(
        client,
        "Hi team, just a reminder about our sprint planning meeting tomorrow at 10 AM. "
        "Please review the agenda in Jira.",
    )

    logger.info("TEST 2: Spam email")
    run_workflow(
        client,
        "URGENT! You've won $1,000,000! Click here now to claim your prize! Limited time offer!",
    )


if __name__ == "__main__":
    asyncio.run(main())
