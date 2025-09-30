# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

from agent_framework import (
    Executor,
    FileCheckpointStorage,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)

CHECKPOINT_DIR = Path(__file__).with_suffix("").parent / "tmp" / "sub_workflow_checkpoints"

"""
Sample: Checkpointing for workflows that embed sub-workflows.

This sample shows how a parent workflow that wraps a sub-workflow can:
- run until the sub-workflow emits a human approval request via RequestInfoExecutor
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
class ReviewRequest(RequestInfoMessage):
    """Human approval request surfaced via RequestInfoExecutor."""

    topic: str = ""
    iteration: int = 1
    draft_excerpt: str = ""
    due_iso: str = ""
    reviewer_guidance: list[str] = field(default_factory=list)  # type: ignore


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
    async def request_review(self, draft: DraftPackage, ctx: WorkflowContext[ReviewRequest]) -> None:
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
        await ctx.send_message(request, target_id="sub_review_requests")

    @handler
    async def forward_decision(
        self,
        decision: RequestResponse[ReviewRequest, str],
        ctx: WorkflowContext[RequestResponse[ReviewRequest, str]],
    ) -> None:
        await ctx.send_message(decision, target_id="draft_finaliser")


class DraftFinaliser(Executor):
    """Applies the human decision and emits the final draft."""

    def __init__(self) -> None:
        super().__init__(id="draft_finaliser")

    @handler
    async def on_review_decision(
        self,
        decision: RequestResponse[ReviewRequest, str],
        ctx: WorkflowContext[DraftTask, FinalDraft],
    ) -> None:
        reply = (decision.data or "").strip().lower()
        original = decision.original_request
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
        self._final: FinalDraft | None = None

    @handler
    async def kick_off(self, topic: str, ctx: WorkflowContext[DraftTask]) -> None:
        task = DraftTask(topic=topic, due=_utc_now() + timedelta(hours=2))
        await ctx.send_message(task, target_id="launch_subworkflow")

    @handler
    async def collect_final(self, draft: FinalDraft, ctx: WorkflowContext[None, FinalDraft]) -> None:
        approved_at = draft.approved_at
        normalised = draft
        if isinstance(approved_at, str):
            with contextlib.suppress(ValueError):
                parsed = datetime.fromisoformat(approved_at)
                normalised = replace(draft, approved_at=parsed)
                approved_at = parsed

        self._final = normalised

        approved_display = approved_at.isoformat() if hasattr(approved_at, "isoformat") else str(approved_at)

        print("\n>>> Parent workflow received approved draft:")
        print(f"- Topic: {normalised.topic}")
        print(f"- Iterations: {normalised.iterations}")
        print(f"- Approved at: {approved_display}")
        print(f"- Content: {normalised.content}\n")

        await ctx.yield_output(normalised)

    @property
    def final_result(self) -> FinalDraft | None:
        return self._final


# ---------------------------------------------------------------------------
# Workflow construction helpers
# ---------------------------------------------------------------------------


def build_sub_workflow() -> WorkflowExecutor:
    writer = DraftWriter()
    router = DraftReviewRouter()
    request_info = RequestInfoExecutor(id="sub_review_requests")
    finaliser = DraftFinaliser()

    sub_workflow = (
        WorkflowBuilder()
        .set_start_executor(writer)
        .add_edge(writer, router)
        .add_edge(router, request_info)
        .add_edge(request_info, router, condition=lambda msg: isinstance(msg, RequestResponse))
        .add_edge(router, finaliser, condition=lambda msg: isinstance(msg, RequestResponse))
        .add_edge(request_info, finaliser)
        .add_edge(finaliser, writer)  # permits revision loops
        .build()
    )

    return WorkflowExecutor(sub_workflow, id="launch_subworkflow")


def build_parent_workflow(storage: FileCheckpointStorage) -> tuple[LaunchCoordinator, Workflow]:
    coordinator = LaunchCoordinator()
    sub_executor = build_sub_workflow()
    parent_request_info = RequestInfoExecutor(id="parent_review_gateway")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(coordinator)
        .add_edge(coordinator, sub_executor)
        .add_edge(sub_executor, coordinator, condition=lambda msg: isinstance(msg, FinalDraft))
        .add_edge(
            sub_executor,
            parent_request_info,
            condition=lambda msg: isinstance(msg, RequestInfoMessage),
        )
        .add_edge(parent_request_info, sub_executor)
        .with_checkpointing(storage)
        .build()
    )

    return coordinator, workflow


async def main() -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    for file in CHECKPOINT_DIR.glob("*.json"):
        file.unlink()

    storage = FileCheckpointStorage(CHECKPOINT_DIR)

    _, workflow = build_parent_workflow(storage)

    print("\n=== Stage 1: run until sub-workflow requests human review ===")
    request_id: str | None = None
    async for event in workflow.run_stream("Contoso Gadget Launch"):
        if isinstance(event, RequestInfoEvent) and request_id is None:
            request_id = event.request_id
            print(f"Captured review request id: {request_id}")
        if isinstance(event, WorkflowStatusEvent) and event.state is WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
            break

    if request_id is None:
        print("Sub-workflow completed without requesting review.")
        return

    checkpoints = await storage.list_checkpoints(workflow.id)
    if not checkpoints:
        print("No checkpoints written.")
        return

    checkpoints.sort(key=lambda cp: cp.timestamp)
    resume_checkpoint = checkpoints[-1]
    print(f"Using checkpoint {resume_checkpoint.checkpoint_id} at iteration {resume_checkpoint.iteration_count}")

    checkpoint_path = storage.storage_path / f"{resume_checkpoint.checkpoint_id}.json"
    if checkpoint_path.exists():
        snapshot = json.loads(checkpoint_path.read_text())
        exec_states = snapshot.get("executor_states", {})
        sub_pending = exec_states.get("sub_review_requests", {}).get("request_events", {})
        parent_pending = exec_states.get("parent_review_gateway", {}).get("request_events", {})
        print(f"Pending review requests (sub executor snapshot): {list(sub_pending.keys())}")
        print(f"Pending review requests (parent executor snapshot): {list(parent_pending.keys())}")

    print("\n=== Stage 2: resume from checkpoint and approve draft ===")
    # Rebuild fresh instances to mimic a separate process resuming
    coordinator2, workflow2 = build_parent_workflow(storage)

    approval_response = "approve"
    final_event: WorkflowOutputEvent | None = None
    async for event in workflow2.run_stream_from_checkpoint(
        resume_checkpoint.checkpoint_id,
        responses={request_id: approval_response},
    ):
        if isinstance(event, WorkflowOutputEvent):
            final_event = event

    if final_event is None:
        print("Workflow did not complete after resume.")
        return

    final = final_event.data
    print("\n=== Final Draft (from resumed run) ===")
    print(final)

    if coordinator2.final_result is None:
        print("Coordinator did not capture final result via handler.")
    else:
        print("Coordinator stored final draft successfully.")

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
