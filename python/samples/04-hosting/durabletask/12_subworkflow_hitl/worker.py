# Copyright (c) Microsoft. All rights reserved.

"""Worker hosting a composed workflow whose Human-in-the-Loop pause lives in a sub-workflow.

This sample combines composition (``11_subworkflow``) with human-in-the-loop
(``09_workflow_hitl``): the HITL ``request_info`` happens **inside an inner
workflow** that an outer workflow embeds via ``WorkflowExecutor``. On the durable
host the inner workflow runs as its own child orchestration, so its pending request
is recorded on the *child* instance. The parent records the child instance id in its
custom status, which lets the client discover the nested request behind a single
top-level addressing surface.

``DurableAIAgentWorker.configure_workflow`` walks the composition and registers a
durable orchestration for each workflow:

- ``dafx-moderation_pipeline`` - the outer workflow.
- ``dafx-human_review`` - the inner workflow (run as a child orchestration), which
  contains the HITL pause.

Composition layout::

    moderation_pipeline (outer)
      intake (executor)
        -> review_sub = WorkflowExecutor(human_review)
             review_gate (executor: request_info -> response_handler)
        -> publish (executor)

The client sees the inner pending request with a **qualified** request id
(``review_sub~0~{requestId}``) and posts the response back to the *top-level*
instance; the host routes it to the owning child orchestration automatically.

Prerequisites:
- Start a Durable Task Scheduler (e.g. the DTS emulator on ``localhost:8080``).
  (This sample uses no AI agents, so no model credentials are required.)

Run the worker (this process), then run ``client.py`` in another process.
"""

import asyncio
import logging
import os
from dataclasses import dataclass

from agent_framework import (
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
    response_handler,
)
from agent_framework.azure import DurableAIAgentWorker
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker
from pydantic import BaseModel
from typing_extensions import Never

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INNER_WORKFLOW_NAME = "human_review"
OUTER_WORKFLOW_NAME = "moderation_pipeline"


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class ContentSubmission:
    """Content submitted for moderation (outer workflow input)."""

    content_id: str
    title: str
    body: str


@dataclass
class HumanApprovalRequest:
    """Request surfaced to the human reviewer (carried in the orchestration status)."""

    content_id: str
    title: str
    body: str
    prompt: str


class HumanApprovalResponse(BaseModel):
    """Response the external client sends back via the HITL response endpoint/method."""

    approved: bool
    reviewer_notes: str = ""


@dataclass
class ModerationDecision:
    """The inner workflow's output: the human's decision for a submission."""

    content_id: str
    approved: bool
    reviewer_notes: str


# ============================================================================
# Inner workflow (contains the HITL pause)
# ============================================================================


class ReviewGateExecutor(Executor):
    """Inner-workflow executor that pauses for human approval via request_info."""

    def __init__(self) -> None:
        super().__init__(id="review_gate")

    @handler
    async def request_review(self, submission: ContentSubmission, ctx: WorkflowContext) -> None:
        prompt = (
            f"Please review the following content for publication:\n\n"
            f"Title: {submission.title}\n"
            f"Content: {submission.body}\n\n"
            f"Approve or reject this content."
        )
        approval_request = HumanApprovalRequest(
            content_id=submission.content_id,
            title=submission.title,
            body=submission.body,
            prompt=prompt,
        )
        # Pause the (inner) workflow and wait for a human response. On the durable
        # host this pauses the child orchestration running this inner workflow.
        await ctx.request_info(request_data=approval_request, response_type=HumanApprovalResponse)

    @response_handler
    async def handle_approval_response(
        self,
        original_request: HumanApprovalRequest,
        response: HumanApprovalResponse,
        ctx: WorkflowContext[Never, ModerationDecision],
    ) -> None:
        logger.info(
            "Human review received for content %s: approved=%s",
            original_request.content_id,
            response.approved,
        )
        # Yield the decision as the inner workflow's output; the WorkflowExecutor
        # forwards it to the outer workflow as a message to the next node.
        await ctx.yield_output(
            ModerationDecision(
                content_id=original_request.content_id,
                approved=response.approved,
                reviewer_notes=response.reviewer_notes,
            )
        )


def create_inner_workflow() -> Workflow:
    """Build the inner ``human_review`` workflow (a single HITL gate)."""
    review_gate = ReviewGateExecutor()
    return WorkflowBuilder(name=INNER_WORKFLOW_NAME, start_executor=review_gate).build()


# ============================================================================
# Outer workflow (embeds the inner workflow)
# ============================================================================


class IntakeExecutor(Executor):
    """Outer-workflow entry point that normalizes the submission before review."""

    def __init__(self) -> None:
        super().__init__(id="intake")

    @handler
    async def intake(self, submission: ContentSubmission, ctx: WorkflowContext[ContentSubmission]) -> None:
        logger.info("Intake received submission %s", submission.content_id)
        await ctx.send_message(submission)


class PublishExecutor(Executor):
    """Outer-workflow executor that consumes the inner workflow's forwarded decision."""

    def __init__(self) -> None:
        super().__init__(id="publish")

    @handler
    async def handle_decision(self, decision: ModerationDecision, ctx: WorkflowContext[Never, str]) -> None:
        if decision.approved:
            message = (
                f"Content '{decision.content_id}' APPROVED and published. "
                f"Reviewer notes: {decision.reviewer_notes or 'None'}"
            )
        else:
            message = f"Content '{decision.content_id}' REJECTED. Reviewer notes: {decision.reviewer_notes or 'None'}"
        logger.info(message)
        await ctx.yield_output(message)


def create_workflow() -> Workflow:
    """Build the outer ``moderation_pipeline`` workflow embedding the HITL sub-workflow."""
    inner_workflow = create_inner_workflow()

    intake = IntakeExecutor()
    # WorkflowExecutor embeds the inner (HITL) workflow as a single node. On the
    # durable host this node runs as a child orchestration, and the inner pause
    # surfaces to the client as a qualified request id (``review_sub~0~{requestId}``).
    review_sub = WorkflowExecutor(inner_workflow, id="review_sub")
    publish = PublishExecutor()

    return (
        WorkflowBuilder(name=OUTER_WORKFLOW_NAME, start_executor=intake)
        .add_edge(intake, review_sub)
        .add_edge(review_sub, publish)
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
    """Register the outer workflow and its nested HITL sub-workflow on the worker."""
    agent_worker = DurableAIAgentWorker(worker)

    workflow = create_workflow()
    # A single call registers the outer workflow plus the nested human_review
    # sub-workflow (each as its own durable orchestration).
    agent_worker.configure_workflow(workflow)
    logger.info(
        "✓ Configured workflow '%s' with embedded HITL sub-workflow '%s'",
        OUTER_WORKFLOW_NAME,
        INNER_WORKFLOW_NAME,
    )

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
