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
    WorkflowCheckpoint,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity._credentials import AzureCliCredential

"""
Sample: Magentic Orchestration + Checkpointing

The goal of this sample is to show the exact mechanics needed to pause a Magentic
workflow that requires human plan review, persist the outstanding request via a
checkpoint, and later resume the workflow by feeding in the saved response.

Concepts highlighted here:
1. **Deterministic executor IDs** - the orchestrator and plan-review request executor
   must keep stable IDs so the checkpoint state aligns when we rebuild the graph.
2. **Executor snapshotting** - checkpoints capture the pending plan-review request
   map, at superstep boundaries.
3. **Resume with responses** - `Workflow.send_responses_streaming` accepts a
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
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
    )

    writer = ChatAgent(
        name="WriterAgent",
        description="Synthesizes the final brief for stakeholders.",
        instructions=("You convert the research notes into a structured brief with milestones and risks."),
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
    )

    # The builder wires in the Magentic orchestrator, sets the plan review path, and
    # stores the checkpoint backend so the runtime knows where to persist snapshots.
    return (
        MagenticBuilder()
        .participants(researcher=researcher, writer=writer)
        .with_plan_review()
        .with_standard_manager(
            chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
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

        if isinstance(event, WorkflowStatusEvent) and event.state is WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
            break

    if plan_review_request_id is None:
        print("No plan review request emitted; nothing to resume.")
        return

    checkpoints = await checkpoint_storage.list_checkpoints(workflow.id)
    if not checkpoints:
        print("No checkpoints persisted.")
        return

    resume_checkpoint = max(
        checkpoints,
        key=lambda cp: (cp.iteration_count, cp.timestamp),
    )
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

    # Construct an approval reply to supply when the plan review request is re-emitted.
    approval = MagenticPlanReviewReply(decision=MagenticPlanReviewDecision.APPROVE)

    # Resume execution and capture the re-emitted plan review request.
    request_info_event: RequestInfoEvent | None = None
    async for event in resumed_workflow.run_stream(checkpoint_id=resume_checkpoint.checkpoint_id):
        if isinstance(event, RequestInfoEvent) and isinstance(event.data, MagenticPlanReviewRequest):
            request_info_event = event

    if request_info_event is None:
        print("No plan review request re-emitted on resume; cannot approve.")
        return
    print(f"Resumed plan review request: {request_info_event.request_id}")

    # Supply the approval and continue to run to completion.
    final_event: WorkflowOutputEvent | None = None
    async for event in resumed_workflow.send_responses_streaming({request_info_event.request_id: approval}):
        if isinstance(event, WorkflowOutputEvent):
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

    # ------------------------------------------------------------------
    # Stage 3: demonstrate resuming from a later checkpoint (post-plan)
    # ------------------------------------------------------------------

    def _pending_message_count(cp: WorkflowCheckpoint) -> int:
        return sum(len(msg_list) for msg_list in cp.messages.values() if isinstance(msg_list, list))

    all_checkpoints = await checkpoint_storage.list_checkpoints(resume_checkpoint.workflow_id)
    later_checkpoints_with_messages = [
        cp
        for cp in all_checkpoints
        if cp.iteration_count > resume_checkpoint.iteration_count and _pending_message_count(cp) > 0
    ]

    if later_checkpoints_with_messages:
        post_plan_checkpoint = max(
            later_checkpoints_with_messages,
            key=lambda cp: (cp.iteration_count, cp.timestamp),
        )
    else:
        later_checkpoints = [cp for cp in all_checkpoints if cp.iteration_count > resume_checkpoint.iteration_count]

        if not later_checkpoints:
            print("\nNo additional checkpoints recorded beyond plan approval; sample complete.")
            return

        post_plan_checkpoint = max(
            later_checkpoints,
            key=lambda cp: (cp.iteration_count, cp.timestamp),
        )
    print("\n=== Stage 3: resume from post-plan checkpoint ===")
    pending_messages = _pending_message_count(post_plan_checkpoint)
    print(
        f"Resuming from checkpoint {post_plan_checkpoint.checkpoint_id} at iteration "
        f"{post_plan_checkpoint.iteration_count} (pending messages: {pending_messages})"
    )
    if pending_messages == 0:
        print("Checkpoint has no pending messages; no additional work expected on resume.")

    final_event_post: WorkflowOutputEvent | None = None
    post_emitted_events = False
    post_plan_workflow = build_workflow(checkpoint_storage)
    async for event in post_plan_workflow.run_stream(checkpoint_id=post_plan_checkpoint.checkpoint_id):
        post_emitted_events = True
        if isinstance(event, WorkflowOutputEvent):
            final_event_post = event

    if final_event_post is None:
        if not post_emitted_events:
            print("No new events were emitted; checkpoint already captured a completed run.")
            print("\n=== Final Answer (post-plan resume) ===")
            print(text)
            return
        print("Workflow did not complete after post-plan resume.")
        return

    post_result = final_event_post.data
    if not post_result:
        print("No result data from post-plan resume.")
        return

    post_text = getattr(post_result, "text", None) or str(post_result)
    print("\n=== Final Answer (post-plan resume) ===")
    print(post_text)

    """
    Sample Output:

    === Stage 1: run until plan review request (checkpointing active) ===
    Captured plan review request: 3a1a4a09-4ed1-4c90-9cf6-9ac488d452c0
    Using checkpoint 4c76d77a-6ff8-4d2b-84f6-824771ffac7e at iteration 1
    Pending plan-review requests persisted in checkpoint: ['3a1a4a09-4ed1-4c90-9cf6-9ac488d452c0']

    === Stage 2: resume from checkpoint and approve plan ===

    === Final Answer ===
    Certainly! Here's your concise internal brief on how the research and implementation teams should collaborate for
    the beta launch of the data-driven email summarization feature:

    ---

    **Internal Brief: Collaboration Plan for Data-driven Email Summarization Beta Launch**

    **Collaboration Approach**
    - **Joint Kickoff:** Research and Implementation teams hold a project kickoff to align on objectives, requirements,
        and success metrics.
    - **Ongoing Coordination:** Teams collaborate closely; researchers share model developments and insights, while
        implementation ensures smooth integration and user experience.
    - **Real-time Feedback Loop:** Implementation provides early feedback on technical integration and UX, while
        Research evaluates initial performance and user engagement signals post-integration.

    **Key Milestones**
    1. **Requirement Finalization & Scoping** - Define MVP feature set and success criteria.
    2. **Model Prototyping & Evaluation** - Researchers develop and validate summarization models with agreed metrics.
    3. **Integration & Internal Testing** - Implementation team integrates the model; internal alpha testing and
        compliance checks.
    4. **Beta User Onboarding** - Recruit a select cohort of beta users and guide them through onboarding.
    5. **Beta Launch & Monitoring** - Soft-launch for beta group, with active monitoring of usage, feedback,
      and performance.
    6. **Iterative Improvements** - Address issues, refine features, and prepare for possible broader rollout.

    **Top Risks**
    - **Data Privacy & Compliance:** Strict protocols and compliance reviews to prevent data leakage.
    - **Model Quality (Bias, Hallucination):** Careful monitoring of summary accuracy; rapid iterations if critical
        errors occur.
    - **User Adoption:** Ensuring the beta solves genuine user needs, collecting actionable feedback early.
    - **Feedback Quality & Quantity:** Proactively schedule user outreach to ensure substantive beta feedback.

    **Communication Cadence**
    - **Weekly Team Syncs:** Short all-hands progress and blockers meeting.
    - **Bi-Weekly Stakeholder Check-ins:** Leadership and project leads address escalations and strategic decisions.
    - **Dedicated Slack Channel:** For real-time queries and updates.
    - **Documentation Hub:** Up-to-date project docs and FAQs on a shared internal wiki.
    - **Post-Milestone Retrospectives:** After critical phases (e.g., alpha, beta), reviewing what worked and what needs
        improvement.

    **Summary**
    Clear alignment, consistent communication, and iterative feedback are key to a successful beta. All team members are
        expected to surface issues quickly and keep documentation current as we drive toward launch.
    ---

    === Stage 3: resume from post-plan checkpoint ===
    Resuming from checkpoint 9a3b... at iteration 3 (pending messages: 0)
    No new events were emitted; checkpoint already captured a completed run.

    === Final Answer (post-plan resume) ===
    (same brief as above)
    """


if __name__ == "__main__":
    asyncio.run(main())
