# Copyright (c) Microsoft. All rights reserved.

"""Worker that hosts a MAF Workflow composed of a nested sub-workflow.

This sample shows workflow *composition* on the Durable Task host. A
``WorkflowExecutor`` embeds an inner workflow as a node inside an outer workflow.
``DurableAIAgentWorker.configure_workflow`` walks the composition and
auto-registers a durable orchestration for *each* workflow:

- ``dafx-sentiment_analysis`` - the inner workflow, run as a durable **child
  orchestration** whenever the outer workflow reaches the ``WorkflowExecutor`` node.
- ``dafx-review_pipeline`` - the outer workflow.

Each workflow's agent executors become durable entities and its non-agent
executors become durable activities, scoped per workflow so the same executor id
in two workflows never collides.

Composition layout::

    review_pipeline (outer)
      intake (executor)
        -> sentiment_sub = WorkflowExecutor(sentiment_analysis)
             sentiment_agent (agent) -> sentiment_formatter (executor)
        -> reporter (executor)

The inner workflow yields a string; because ``allow_direct_output`` is left at its
default (``False``), that output is forwarded to the outer workflow as a message
delivered to ``reporter``, which produces the final result.

Prerequisites:
- Set ``FOUNDRY_PROJECT_ENDPOINT`` and ``FOUNDRY_MODEL``.
- Sign in with Azure CLI (``az login``) for ``AzureCliCredential``.
- Start a Durable Task Scheduler (e.g. the DTS emulator on ``localhost:8080``).

Run the worker (this process), then run ``client.py`` in another process.
"""

import asyncio
import logging
import os
from typing import Any

from agent_framework import (
    Agent,
    AgentExecutorResponse,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
)
from agent_framework.azure import DurableAIAgentWorker
from agent_framework.foundry import FoundryChatClient, FoundryChatOptions
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from dotenv import load_dotenv
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker
from pydantic import BaseModel, ValidationError
from typing_extensions import Never

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SENTIMENT_AGENT_NAME = "SentimentAgent"
INNER_WORKFLOW_NAME = "sentiment_analysis"
OUTER_WORKFLOW_NAME = "review_pipeline"

SENTIMENT_INSTRUCTIONS = (
    "You classify the sentiment of a customer product review. "
    "Return JSON with fields sentiment (one of 'positive', 'neutral', 'negative') "
    "and confidence (a number between 0 and 1)."
)


class SentimentResult(BaseModel):
    """Structured output from the sentiment agent."""

    sentiment: str
    confidence: float


class SentimentFormatterExecutor(Executor):
    """Inner-workflow executor that turns the agent's JSON into a summary line."""

    @handler
    async def format_sentiment(self, agent_response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
        text = agent_response.agent_response.text
        try:
            result = SentimentResult.model_validate_json(text)
            summary = f"{result.sentiment} (confidence {result.confidence:.0%})"
        except ValidationError:
            summary = "unknown (could not parse sentiment)"
        await ctx.yield_output(summary)


class IntakeExecutor(Executor):
    """Outer-workflow entry point that normalizes the review before analysis."""

    @handler
    async def intake(self, review: str, ctx: WorkflowContext[str]) -> None:
        normalized = review.strip()
        logger.info("Intake received review (%d chars)", len(normalized))
        await ctx.send_message(normalized)


class ReporterExecutor(Executor):
    """Outer-workflow executor that consumes the sub-workflow's forwarded output."""

    @handler
    async def report(self, sentiment_summary: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(f"Review analysis complete -> sentiment: {sentiment_summary}")


def _create_chat_client() -> FoundryChatClient:
    """Create a Microsoft Foundry chat client using AzureCliCredential."""
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AsyncAzureCliCredential(),
    )


def create_inner_workflow(chat_client: FoundryChatClient) -> Workflow:
    """Build the inner ``sentiment_analysis`` workflow (agent -> formatter)."""
    sentiment_agent = Agent(
        client=chat_client,
        name=SENTIMENT_AGENT_NAME,
        instructions=SENTIMENT_INSTRUCTIONS,
        default_options=FoundryChatOptions[Any](response_format=SentimentResult),
    )
    sentiment_formatter = SentimentFormatterExecutor(id="sentiment_formatter")

    return (
        WorkflowBuilder(name=INNER_WORKFLOW_NAME, start_executor=sentiment_agent)
        .add_edge(sentiment_agent, sentiment_formatter)
        .build()
    )


def create_workflow() -> Workflow:
    """Build the outer ``review_pipeline`` workflow that embeds the inner workflow."""
    chat_client = _create_chat_client()
    inner_workflow = create_inner_workflow(chat_client)

    intake = IntakeExecutor(id="intake")
    # WorkflowExecutor embeds the inner workflow as a single node in the outer
    # workflow. On the durable host this node runs as a child orchestration.
    sentiment_sub = WorkflowExecutor(inner_workflow, id="sentiment_sub")
    reporter = ReporterExecutor(id="reporter")

    return (
        WorkflowBuilder(name=OUTER_WORKFLOW_NAME, start_executor=intake)
        .add_edge(intake, sentiment_sub)
        .add_edge(sentiment_sub, reporter)
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
    """Register the outer workflow and its nested sub-workflow on the worker."""
    agent_worker = DurableAIAgentWorker(worker)

    workflow = create_workflow()
    # A single call walks the composition: it registers the outer workflow plus
    # every nested sub-workflow (here, sentiment_analysis) as its own durable
    # orchestration, deduped by workflow name.
    agent_worker.configure_workflow(workflow)
    logger.info("✓ Configured workflow '%s' with embedded sub-workflow '%s'", OUTER_WORKFLOW_NAME, INNER_WORKFLOW_NAME)

    return agent_worker


async def main() -> None:
    """Start the worker and block until interrupted."""
    worker = get_worker()
    setup_worker(worker)

    logger.info("Worker is ready and listening for work items. Press Ctrl+C to stop.")
    try:
        worker.start()
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Worker shutdown initiated")

    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
