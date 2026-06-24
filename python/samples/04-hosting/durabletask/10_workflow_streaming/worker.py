# Copyright (c) Microsoft. All rights reserved.

"""Worker that hosts a multi-step MAF Workflow for streaming (no Azure Functions).

This sample is the streaming counterpart to ``08_workflow``. It hosts a simple
linear content pipeline so a client can watch progress event-by-event:

``writer`` (agent) -> ``reviewer`` (agent) -> ``publish`` (non-agent executor)

``DurableAIAgentWorker.configure_workflow`` auto-registers a durable entity for
each agent executor, a durable activity for each non-agent executor, and the
workflow orchestrator. As each executor runs, the orchestrator publishes coarse
workflow events (``executor_invoked`` / ``executor_completed`` / ``output``) to
the orchestration custom status, which the client streams by polling.

Prerequisites:
- Set ``FOUNDRY_PROJECT_ENDPOINT`` and ``FOUNDRY_MODEL``.
- Sign in with Azure CLI (``az login``) for ``AzureCliCredential``.
- Start a Durable Task Scheduler (e.g. the DTS emulator on ``localhost:8080``).

Run the worker (this process), then run ``client.py`` in another process.
"""

import asyncio
import logging
import os

from agent_framework import (
    Agent,
    AgentExecutorResponse,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.azure import DurableAIAgentWorker
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from dotenv import load_dotenv
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker
from typing_extensions import Never

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WRITER_AGENT_NAME = "WriterAgent"
REVIEWER_AGENT_NAME = "ReviewerAgent"

WRITER_INSTRUCTIONS = (
    "You are a concise technical writer. Write a short, single-paragraph draft on the requested topic."
)
REVIEWER_INSTRUCTIONS = (
    "You are an editor. Improve the draft you receive for clarity and tone, "
    "and return only the improved single-paragraph version."
)


class PublishExecutor(Executor):
    """Non-agent executor that 'publishes' the reviewed draft as the final output."""

    @handler
    async def publish(self, agent_response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
        reviewed_text = agent_response.agent_response.text
        await ctx.yield_output(f"Published:\n{reviewed_text}")


def _create_chat_client() -> FoundryChatClient:
    """Create an Azure AI Foundry chat client using AzureCliCredential."""
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AsyncAzureCliCredential(),
    )


def create_workflow() -> Workflow:
    """Build the linear writer -> reviewer -> publish pipeline."""
    chat_client = _create_chat_client()

    writer_agent = Agent(client=chat_client, name=WRITER_AGENT_NAME, instructions=WRITER_INSTRUCTIONS)
    reviewer_agent = Agent(client=chat_client, name=REVIEWER_AGENT_NAME, instructions=REVIEWER_INSTRUCTIONS)
    publish = PublishExecutor(id="publish")

    return (
        WorkflowBuilder(start_executor=writer_agent)
        .add_edge(writer_agent, reviewer_agent)
        .add_edge(reviewer_agent, publish)
        .build()
    )


def get_worker(
    taskhub: str | None = None, endpoint: str | None = None, log_handler: logging.Handler | None = None
) -> DurableTaskSchedulerWorker:
    """Create a configured DurableTaskSchedulerWorker."""
    taskhub_name = taskhub or os.getenv("TASKHUB", "default")
    endpoint_url = endpoint or os.getenv("ENDPOINT", "http://localhost:8080")

    credential = None if endpoint_url == "http://localhost:8080" else AzureCliCredential()

    return DurableTaskSchedulerWorker(
        host_address=endpoint_url,
        secure_channel=endpoint_url != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential,
        log_handler=log_handler,
    )


def setup_worker(worker: DurableTaskSchedulerWorker) -> DurableAIAgentWorker:
    """Register the workflow (agents + activities + orchestrator) on the worker."""
    agent_worker = DurableAIAgentWorker(worker)

    workflow = create_workflow()
    agent_worker.configure_workflow(workflow)
    logger.info("✓ Configured streaming workflow with %d executors", len(workflow.executors))

    return agent_worker


async def main() -> None:
    """Start the worker and block until interrupted."""
    worker = get_worker()
    setup_worker(worker)

    logger.info("Worker is ready and listening for work items. Press Ctrl+C to stop.")
    try:
        worker.start()
        while True:  # noqa: ASYNC110
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Worker shutdown initiated")

    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
