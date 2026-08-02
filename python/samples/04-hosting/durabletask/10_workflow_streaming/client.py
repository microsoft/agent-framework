# Copyright (c) Microsoft. All rights reserved.

"""Client that starts the workflow and streams its progress event-by-event.

The worker (``worker.py``) must be running first. This client demonstrates the
async ``DurableWorkflowClient`` API:

1. ``run_workflow(input, wait=False)`` starts the workflow and returns its
   instance id without blocking.
2. ``stream_workflow(instance_id)`` yields typed ``WorkflowEvent`` objects
   (``executor_invoked`` / ``executor_completed`` / ``output`` / ...) as the
   workflow progresses, by polling the orchestration custom status. This is
   brokerless; each event's ``data`` is already reconstructed into its original
   typed object, so the client never deserializes anything by hand. Granularity
   is per executor / per yielded output, not token-level.
3. ``await_workflow_output(...)`` returns the final reconstructed output.

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


async def main() -> None:
    """Start a workflow and stream its typed progress events to the console."""
    client = DurableWorkflowClient(get_client())

    # Start without waiting so we can stream progress as it happens.
    instance_id = await client.run_workflow(input="Write a short note about durable workflows.", wait=False)
    logger.info("Started workflow instance: %s", instance_id)

    logger.info("Streaming workflow events:")
    async for event in client.stream_workflow(instance_id, poll_interval_seconds=1.0):
        if event.type == "output":
            logger.info("  [output] from %s: %s", event.executor_id, event.data)
        else:
            logger.info("  [%s] %s", event.type, event.executor_id)

    # The stream ends when the workflow reaches a terminal state; read the result.
    output = await client.await_workflow_output(instance_id)
    logger.info("Final output: %s", output)


if __name__ == "__main__":
    asyncio.run(main())
