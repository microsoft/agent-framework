# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, override

from agent_framework import (
    Executor,
    FileCheckpointStorage,
    RequestInfoEvent,
    SubWorkflowRequestMessage,
    SubWorkflowResponseMessage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
    response_handler,
    tool,
)

CHECKPOINT_DIR = Path(__file__).with_suffix("").parent / "tmp" / "sub_workflow_checkpoints"

"""
Sample: Checkpointing for workflows that embed sub-workflows.

This sample shows how a parent workflow that wraps a sub-workflow can:
- run until the sub-workflow emits a human approval request
- persist a checkpoint that captures the pending request (including complex payloads)
- resume later, supplying the human decision directly at restore time

It is intentionally similar in spirit to the orchestration checkpoint sample but
uses ``WorkflowExecutor`` so we exercise the full parent/sub-workflow round-trip.
"""


def _utc_now() -> datetime:
    return datetime.now()


# ---------------------------------------------------------------------------
# Messages exchanged inside the sub-workflow
# ---------------------------------------------------------------------------


@dataclass
class DraftTask:
    """Task handed from the parent to the sub-workflow writer."""

    topic: str
    due: datetime
    iteration: int = 1


@dataclass
class DraftPackage:
    """Intermediate draft produced by the sub-workflow writer."""

    topic: str
    content: str
    iteration: int
    created_at: datetime = field(default_factory=_utc_now)


@dataclass
class FinalDraft:
    """Final deliverable returned to the parent workflow."""

    topic: str
    content: str
    iterations: int
    approved_at: datetime


@dataclass
class ReviewRequest:
    """Human approval request surfaced via `request_info`."""

    id: str = str(uuid.uuid4())
    topic: str = ""
    iteration: int = 1
    draft_excerpt: str = ""
    due_iso: str = ""
    reviewer_guidance: list[str] = field(default_factory=list)  # type: ignore


@dataclass
class ReviewDecision:
    """The review decision to be sent to downstream executors along with the original request."""

    decision: str
    original_request: ReviewRequest


# ---------------------------------------------------------------------------
# Sub-workflow executors
# ---------------------------------------------------------------------------


class DraftWriter(Executor):
    """Produces an initial draft for the supplied topic."""

    def __init__(self) -> None:
        super().__init__(id="draft_writer")

    @handler
    async def create_draft(self, task: DraftTask, ctx: WorkflowContext[DraftPackage]) -> None:
        draft = DraftPackage(
            topic=task.topic,
            content=(
                f"Launch plan for {task.topic}.\n\n"
                "- Outline the customer message.\n"
                "- Highlight three differentiators.\n"
                "- Close with a next-step CTA.\n"
                f"(iteration {task.iteration})"
            ),
            iteration=task.iteration,
        )
        await ctx.send_message(draft, target_id="draft_review")


class DraftReviewRouter(Executor):
    """Turns draft packages into human approval requests."""

    def __init__(self) -> None:
        super().__init__(id="draft_review")

    @handler
    async def request_review(self, draft: DraftPackage, ctx: WorkflowContext) -> None:
        """Request a review upon receiving a draft."""
        excerpt = draft.content.splitlines()[0]
        request = ReviewRequest(
            topic=draft.topic,
            iteration=draft.iteration,
            draft_excerpt=excerpt,
            due_iso=draft.created_at.isoformat(),
            reviewer_guidance=[
                "Ensure tone matches launch messaging",
                "Confirm CTA is action-oriented",
            ],
        )
        await ctx.request_info(request_data=request, response_type=str)

    @response_handler
    async def forward_decision(
        self,
        original_request: ReviewRequest,
        decision: str,
        ctx: WorkflowContext[ReviewDecision],
    ) -> None:
        """Route the decision to the next executor."""
        await ctx.send_message(ReviewDecision(decision=decision, original_request=original_request))


class DraftFinaliser(Executor):
    """Applies the human decision and emits the final draft."""

    def __init__(self) -> None:
        super().__init__(id="draft_finaliser")

    @handler
    async def on_review_decision(
        self,
        review_decision: ReviewDecision,
        ctx: WorkflowContext[DraftTask, FinalDraft],
    ) -> None:
        reply = review_decision.decision.strip().lower()
        original = review_decision.original_request
        topic = original.topic if original else "unknown topic"
        iteration = original.iteration if original else 1

        if reply != "approve":
            # Loop back with a follow-up task. In a real workflow you would
            # incorporate the human guidance; here we just increment the counter.
            next_task = DraftTask(
                topic=topic,
                due=_utc_now() + timedelta(hours=1),
                iteration=iteration + 1,
            )
            await ctx.send_message(next_task, target_id="draft_writer")
            return

        final = FinalDraft(
            topic=topic,
            content=f"Approved launch narrative for {topic} (iteration {iteration}).",
            iterations=iteration,
            approved_at=_utc_now(),
        )
        await ctx.yield_output(final)


# ---------------------------------------------------------------------------
# Parent workflow executors
# ---------------------------------------------------------------------------


class LaunchCoordinator(Executor):
    """Owns the top-level workflow and collects the final draft."""

    def __init__(self) -> None:
        super().__init__(id="launch_coordinator")
        # Track pending requests to match responses
        self._pending_requests: dict[str, SubWorkflowRequestMessage] = {}

    @handler
    async def kick_off(self, topic: str, ctx: WorkflowContext[DraftTask]) -> None:
        task = DraftTask(topic=topic, due=_utc_now() + timedelta(hours=2))
        await ctx.send_message(task)

    @handler
    async def collect_final(self, draft: FinalDraft, ctx: WorkflowContext[None, FinalDraft]) -> None:
        approved_at = draft.approved_at
        normalised = draft
        if isinstance(approved_at, str):
            with contextlib.suppress(ValueError):
                parsed = datetime.fromisoformat(approved_at)
                normalised = replace(draft, approved_at=parsed)
                approved_at = parsed

        approved_display = approved_at.isoformat() if hasattr(approved_at, "isoformat") else str(approved_at)

        print("\n>>> Parent workflow received approved draft:")
        print(f"- Topic: {normalised.topic}")
        print(f"- Iterations: {normalised.iterations}")
        print(f"- Approved at: {approved_display}")
        print(f"- Content: {normalised.content}\n")

        await ctx.yield_output(normalised)

    @handler
    async def handler_sub_workflow_request(
        self,
        request: SubWorkflowRequestMessage,
        ctx: WorkflowContext,
    ) -> None:
        """Handle requests from the sub-workflow.

        Note that the message type must be SubWorkflowRequestMessage to intercept the request.
        """
        if not isinstance(request.source_event.data, ReviewRequest):
            raise TypeError(f"Expected 'ReviewRequest', got {type(request.source_event.data)}")

        # Record the request for response matching
        review_request = request.source_event.data
        self._pending_requests[review_request.id] = request

        # Send the request without modification
        await ctx.request_info(request_data=review_request, response_type=str)

    @response_handler
    async def handle_request_response(
        self,
        original_request: ReviewRequest,
        response: str,
        ctx: WorkflowContext[SubWorkflowResponseMessage],
    ) -> None:
        """Process the response and send it back to the sub-workflow.

        Note that the response must be sent back using SubWorkflowResponseMessage to route
        the response back to the sub-workflow.
        """
        request_message = self._pending_requests.pop(original_request.id, None)

        if request_message is None:
            raise ValueError("No matching pending request found for the resource response")

        await ctx.send_message(request_message.create_response(response))

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Capture any additional state needed for checkpointing."""
        return {
            "pending_requests": self._pending_requests,
        }

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore any additional state needed from checkpointing."""
        self._pending_requests = state.get("pending_requests", {})


# ---------------------------------------------------------------------------
# Workflow construction helpers
# ---------------------------------------------------------------------------


def build_sub_workflow() -> WorkflowExecutor:
    """Assemble the sub-workflow used by the parent workflow executor."""
    sub_workflow = (
        WorkflowBuilder()
        .register_executor(DraftWriter, name="writer")
        .register_executor(DraftReviewRouter, name="router")
        .register_executor(DraftFinaliser, name="finaliser")
        .set_start_executor("writer")
        .add_edge("writer", "router")
        .add_edge("router", "finaliser")
        .add_edge("finaliser", "writer")  # permits revision loops
        .build()
    )

    return WorkflowExecutor(sub_workflow, id="launch_subworkflow")


def build_parent_workflow(storage: FileCheckpointStorage) -> Workflow:
    """Assemble the parent workflow that embeds the sub-workflow."""
    return (
        WorkflowBuilder()
        .register_executor(LaunchCoordinator, name="coordinator")
        .register_executor(build_sub_workflow, name="sub_executor")
        .set_start_executor("coordinator")
        .add_edge("coordinator", "sub_executor")
        .add_edge("sub_executor", "coordinator")
        .with_checkpointing(storage)
        .build()
    )


async def main() -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    for file in CHECKPOINT_DIR.glob("*.json"):
        file.unlink()

    storage = FileCheckpointStorage(CHECKPOINT_DIR)

    workflow = build_parent_workflow(storage)

    print("\n=== Stage 1: run until sub-workflow requests human review ===")

    request_id: str | None = None
    async for event in workflow.run_stream("Contoso Gadget Launch"):
        if isinstance(event, RequestInfoEvent) and request_id is None:
            request_id = event.request_id
            print(f"Captured review request id: {request_id}")
        if isinstance(event, WorkflowStatusEvent) and event.state is WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
            break

    if request_id is None:
        raise RuntimeError("Sub-workflow completed without requesting review.")

    checkpoints = await storage.list_checkpoints(workflow.id)
    if not checkpoints:
        raise RuntimeError("No checkpoints found.")

    # Print the checkpoint to show pending requests
    # We didn't handle the request above so the request is still pending the last checkpoint
    checkpoints.sort(key=lambda cp: cp.timestamp)
    resume_checkpoint = checkpoints[-1]
    print(f"Using checkpoint {resume_checkpoint.checkpoint_id} at iteration {resume_checkpoint.iteration_count}")

    checkpoint_path = storage.storage_path / f"{resume_checkpoint.checkpoint_id}.json"
    if checkpoint_path.exists():
        checkpoint_content_dict = json.loads(checkpoint_path.read_text())
        print(f"Pending review requests: {checkpoint_content_dict.get('pending_request_info_events', {})}")

    print("\n=== Stage 2: resume from checkpoint ===")

    # Rebuild fresh instances to mimic a separate process resuming
    workflow2 = build_parent_workflow(storage)

    request_info_event: RequestInfoEvent | None = None
    async for event in workflow2.run_stream(checkpoint_id=resume_checkpoint.checkpoint_id):
        if isinstance(event, RequestInfoEvent):
            request_info_event = event

    if request_info_event is None:
        raise RuntimeError("No request_info_event captured.")

    print("\n=== Stage 3: approve draft ==")

    approval_response = "approve"
    output_event: WorkflowOutputEvent | None = None
    async for event in workflow2.send_responses_streaming({request_info_event.request_id: approval_response}):
        if isinstance(event, WorkflowOutputEvent):
            output_event = event

    if output_event is None:
        raise RuntimeError("Workflow did not complete after resume.")

    output = output_event.data
    print("\n=== Final Draft (from resumed run) ===")
    print(output)

    """"
    Sample Output:

    === Stage 1: run until sub-workflow requests human review ===
    Captured review request id: 032c9f3a-ad1b-4a52-89be-a168d6663011
    Using checkpoint 54f376c2-f849-44e4-9d8d-e627fd27ab96 at iteration 2
    Pending review requests (sub executor snapshot): []
    Pending review requests (parent executor snapshot): ['032c9f3a-ad1b-4a52-89be-a168d6663011']

    === Stage 2: resume from checkpoint and approve draft ===

    >>> Parent workflow received approved draft:
    - Topic: Contoso Gadget Launch
    - Iterations: 1
    - Approved at: 2025-09-25T14:29:34.479164
    - Content: Approved launch narrative for Contoso Gadget Launch (iteration 1).


    === Final Draft (from resumed run) ===
    FinalDraft(topic='Contoso Gadget Launch', content='Approved launch narrative for Contoso
    Gadget Launch (iteration 1).', iterations=1, approved_at=datetime.datetime(2025, 9, 25, 14, 29, 34, 479164))
    Coordinator stored final draft successfully.
    """


if __name__ == "__main__":
    asyncio.run(main())
