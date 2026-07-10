# Copyright (c) Microsoft. All rights reserved.
"""Composed workflow whose Human-in-the-Loop pause lives in a nested sub-workflow.

This sample combines composition with human-in-the-loop on Azure Durable
Functions: the HITL ``request_info`` happens **inside an inner workflow** that an
outer workflow embeds via ``WorkflowExecutor``. On the durable host the inner
workflow runs as its own child orchestration, so its pending request is recorded on
the *child* instance. The parent records the child instance id in its custom status,
which lets the host surface the nested request behind a single top-level addressing
surface.

``AgentFunctionApp`` walks the composition and registers a durable orchestration for
each workflow, but exposes HTTP routes only for the **top-level** workflow:

- ``dafx-moderation_pipeline`` - the outer workflow (HTTP routes).
- ``dafx-human_review`` - the inner workflow (run as a child orchestration), which
  contains the HITL pause (no direct routes).

Composition layout::

    moderation_pipeline (outer)
      intake (executor)
        -> review_sub = WorkflowExecutor(human_review)
             review_gate (executor: request_info -> response_handler)
        -> publish (executor)

The status endpoint surfaces the inner pending request with a **qualified** request
id (``review_sub~0~{requestId}``); the caller posts the response back to the
*top-level* instance and the host routes it to the owning child orchestration
automatically.

This sample hosts **no AI agents**, so it needs only the Durable Task Scheduler and
Azurite (no model credentials).

Prerequisites:
- Start Azurite: ``azurite --silent --location .``
- Start a Durable Task Scheduler emulator on ``localhost:8080``.
- Run: ``func start``
"""

import logging
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
from agent_framework_azurefunctions import AgentFunctionApp
from pydantic import BaseModel
from typing_extensions import Never

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
    """Response the external client sends back via the HITL response endpoint."""

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


def _create_workflow() -> Workflow:
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


# ============================================================================
# Application Entry Point
# ============================================================================


def launch(durable: bool = True) -> AgentFunctionApp | None:
    """Launch the function app or DevUI.

    Args:
        durable: If True, returns AgentFunctionApp for Azure Functions.
                 If False, launches DevUI for local MAF development.
    """
    if durable:
        # Azure Functions mode. The app automatically provides per-workflow HITL
        # endpoints for the top-level workflow ("moderation_pipeline"):
        # - POST /api/workflow/moderation_pipeline/run
        # - GET  /api/workflow/moderation_pipeline/status/{instanceId}
        #        (surfaces the nested request as review_sub~0~{requestId})
        # - POST /api/workflow/moderation_pipeline/respond/{instanceId}/{requestId}
        # - GET  /api/health
        workflow = _create_workflow()
        return AgentFunctionApp(workflow=workflow, enable_health_check=True)

    # Pure MAF mode with DevUI for local development.
    from pathlib import Path

    from agent_framework.devui import serve
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)

    logger.info("Starting Sub-workflow HITL Sample in MAF mode")
    logger.info("Available at: http://localhost:8097")
    logger.info("\nThis workflow demonstrates:")
    logger.info("- Human-in-the-loop inside a nested sub-workflow (WorkflowExecutor)")
    logger.info("- Qualified request ids (review_sub~0~{requestId}) behind a single surface")
    logger.info("\nFlow: Intake -> WorkflowExecutor(human_review: ReviewGate HITL) -> Publish")

    workflow = _create_workflow()
    serve(entities=[workflow], port=8097, auto_open=True)

    return None


# Default: Azure Functions mode
# Run with `python function_app.py --maf` for pure MAF mode with DevUI
app = launch(durable=True)


if __name__ == "__main__":
    import sys

    if "--maf" in sys.argv:
        launch(durable=False)
