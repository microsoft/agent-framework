# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
from pathlib import Path

from agent_framework import (
    ChatAgent,
    FileCheckpointStorage,
    MagenticBuilder,
    MagenticPlanReviewDecision,
    MagenticPlanReviewReply,
    MagenticPlanReviewRequest,
    RequestInfoEvent,
    WorkflowCompletedEvent,
)
from agent_framework.openai import OpenAIChatClient

"""
Sample: Magentic Orchestration + Checkpointing

The goal of this sample is to show the exact mechanics needed to pause a Magentic
workflow that requires human plan review, persist the outstanding request via a
checkpoint, and later resume the workflow by feeding in the saved response.

Concepts highlighted here:
1. **Deterministic executor IDs** - the orchestrator and plan-review request executor
   must keep stable IDs so the checkpoint state aligns when we rebuild the graph.
2. **Executor snapshotting** - checkpoints capture the `RequestInfoExecutor` state,
   specifically the pending plan-review request map, at superstep boundaries.
3. **Resume with responses** - `Workflow.run_stream_from_checkpoint` accepts a
   `responses` mapping so we can inject the stored human reply during restoration.

Prerequisites:
- OpenAI environment variables configured for `OpenAIChatClient`.
"""

TASK = (
    "Draft a concise internal brief describing how our research and implementation teams should collaborate "
    "to launch a beta feature for data-driven email summarization. Highlight the key milestones, "
    "risks, and communication cadence."
)

# Dedicated folder for captured checkpoints. Keeping it under the sample directory
# makes it easy to inspect the JSON blobs produced by each run.
CHECKPOINT_DIR = Path(__file__).parent / "tmp" / "magentic_checkpoints"


def build_workflow(checkpoint_storage: FileCheckpointStorage):
    """Construct the Magentic workflow graph with checkpointing enabled."""

    # Two vanilla ChatAgents act as participants in the orchestration. They do not need
    # extra state handling because their inputs/outputs are fully described by chat messages.
    researcher = ChatAgent(
        name="ResearcherAgent",
        description="Collects background facts and references for the project.",
        instructions=("You are the research lead. Gather crisp bullet points the team should know."),
        chat_client=OpenAIChatClient(),
    )

    writer = ChatAgent(
        name="WriterAgent",
        description="Synthesizes the final brief for stakeholders.",
        instructions=("You convert the research notes into a structured brief with milestones and risks."),
        chat_client=OpenAIChatClient(),
    )

    # The builder wires in the Magentic orchestrator, sets the plan review path, and
    # stores the checkpoint backend so the runtime knows where to persist snapshots.
    return (
        MagenticBuilder()
        .participants(researcher=researcher, writer=writer)
        .with_plan_review()
        .with_standard_manager(
            chat_client=OpenAIChatClient(),
            max_round_count=10,
            max_stall_count=3,
        )
        .with_checkpointing(checkpoint_storage)
        .build()
    )


async def main() -> None:
    # Stage 0: make sure the checkpoint folder is empty so we inspect only checkpoints
    # written by this invocation. This prevents stale files from previous runs from
    # confusing the analysis.
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    for file in CHECKPOINT_DIR.glob("*.json"):
        file.unlink()

    checkpoint_storage = FileCheckpointStorage(CHECKPOINT_DIR)

    print("\n=== Stage 1: run until plan review request (checkpointing active) ===")
    workflow = build_workflow(checkpoint_storage)

    # Run the workflow until the first RequestInfoEvent is surfaced. The event carries the
    # request_id we must reuse on resume. In a real system this is where the UI would present
    # the plan for human review.
    plan_review_request_id: str | None = None
    async for event in workflow.run_stream(TASK):
        if isinstance(event, RequestInfoEvent) and event.request_type is MagenticPlanReviewRequest:
            plan_review_request_id = event.request_id
            print(f"Captured plan review request: {plan_review_request_id}")
            break

    if plan_review_request_id is None:
        print("No plan review request emitted; nothing to resume.")
        return

    checkpoints = await checkpoint_storage.list_checkpoints(workflow.workflow.id)
    if not checkpoints:
        print("No checkpoints persisted.")
        return

    checkpoints.sort(key=lambda cp: cp.timestamp)
    resume_checkpoint = checkpoints[-1]
    print(f"Using checkpoint {resume_checkpoint.checkpoint_id} at iteration {resume_checkpoint.iteration_count}")

    # Show that the checkpoint JSON indeed contains the pending plan-review request record.
    checkpoint_path = checkpoint_storage.storage_path / f"{resume_checkpoint.checkpoint_id}.json"
    if checkpoint_path.exists():
        with checkpoint_path.open() as f:
            snapshot = json.load(f)
        request_map = snapshot.get("executor_states", {}).get("magentic_plan_review", {}).get("request_events", {})
        print(f"Pending plan-review requests persisted in checkpoint: {list(request_map.keys())}")

    print("\n=== Stage 2: resume from checkpoint and approve plan ===")
    resumed_workflow = build_workflow(checkpoint_storage)

    approval = MagenticPlanReviewReply(decision=MagenticPlanReviewDecision.APPROVE)
    # Resume execution and supply the recorded approval in a single call.
    # `run_stream_from_checkpoint` rebuilds executor state, applies the provided responses,
    # and then continues the workflow. Because we only captured the initial plan review
    # checkpoint, the resumed run should complete almost immediately.
    final_event: WorkflowCompletedEvent | None = None
    async for event in resumed_workflow.workflow.run_stream_from_checkpoint(
        resume_checkpoint.checkpoint_id,
        responses={plan_review_request_id: approval},
    ):
        if isinstance(event, WorkflowCompletedEvent):
            final_event = event

    if final_event is None:
        print("Workflow did not complete after resume.")
        return

    # Final sanity check: display the assistant's answer as proof the orchestration reached
    # a natural completion after resuming from the checkpoint.
    result = final_event.data
    if not result:
        print("No result data from workflow.")
        return
    text = getattr(result, "text", None) or str(result)
    print("\n=== Final Answer ===")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
