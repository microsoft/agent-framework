# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessage,
    Executor,
    FileCheckpointStorage,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential

# NOTE: the Azure client imports above are real dependencies. When running this
# sample outside of Azure-enabled environments you may wish to swap in the
# `agent_framework.builtin` chat client or mock the writer executor. We keep the
# concrete import here so readers can see an end-to-end configuration.

if TYPE_CHECKING:
    from agent_framework import Workflow
    from agent_framework._workflow._checkpoint import WorkflowCheckpoint

"""
Sample: Checkpoint + human-in-the-loop quickstart.

This getting-started sample keeps the moving pieces to a minimum:

1. A brief is turned into a consistent prompt for an AI copywriter.
2. The copywriter (an `AgentExecutor`) drafts release notes.
3. A reviewer gateway routes every draft through `RequestInfoExecutor` so a human
   can approve or request tweaks.
4. The workflow records checkpoints between each superstep so you can stop the
   program, restart later, and optionally pre-supply human answers on resume.

Key concepts demonstrated
-------------------------
- Minimal executor pipeline with checkpoint persistence.
- Human-in-the-loop pause/resume by pairing `RequestInfoExecutor` with
  checkpoint restoration.
- Supplying responses at restore time (`run_stream_from_checkpoint(..., responses=...)`).

Typical pause/resume flow
-------------------------
1. Run the workflow until a human approval request is emitted.
2. If the human is offline, exit the program. A checkpoint with
   ``status=awaiting human response`` now exists.
3. Later, restart the script, select that checkpoint, and provide the stored
   human decision when prompted to pre-supply responses.
   Doing so applies the answer immediately on resume, so the system does **not**
   re-emit the same `RequestInfoEvent`.
"""

# Directory used for the sample's temporary checkpoint files. We isolate the
# demo artefacts so that repeated runs do not collide with other samples and so
# the clean-up step at the end of the script can simply delete the directory.
TEMP_DIR = Path(__file__).with_suffix("").parent / "tmp" / "checkpoints_hitl"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


class BriefPreparer(Executor):
    """Normalises the user brief and sends a single AgentExecutorRequest."""

    # The first executor in the workflow. By keeping it tiny we make it easier
    # to reason about the state that will later be captured in the checkpoint.
    # It is responsible for tidying the human-provided brief and kicking off the
    # agent run with a deterministic prompt structure.

    def __init__(self, id: str, agent_id: str) -> None:
        super().__init__(id=id)
        self._agent_id = agent_id

    @handler
    async def prepare(self, brief: str, ctx: WorkflowContext[AgentExecutorRequest, str]) -> None:
        # Collapse errant whitespace so the prompt is stable between runs.
        normalized = " ".join(brief.split()).strip()
        if not normalized.endswith("."):
            normalized += "."
        # Persist the cleaned brief in shared state so downstream executors and
        # future checkpoints can recover the original intent.
        await ctx.set_shared_state("brief", normalized)
        prompt = (
            "You are drafting product release notes. Summarise the brief below in two sentences. "
            "Keep it positive and end with a call to action.\n\n"
            f"BRIEF: {normalized}"
        )
        # Hand the prompt to the writer agent. We always route through the
        # workflow context so the runtime can capture messages for checkpointing.
        await ctx.send_message(
            AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=prompt)], should_respond=True),
            target_id=self._agent_id,
        )


@dataclass
class HumanApprovalRequest(RequestInfoMessage):
    """Message sent to the human reviewer via RequestInfoExecutor."""

    # These fields are intentionally simple because they are serialised into
    # checkpoints. Keeping them primitive types guarantees the new
    # `pending_requests_from_checkpoint` helper can reconstruct them on resume.
    prompt: str = ""
    draft: str = ""
    iteration: int = 0


class ReviewGateway(Executor):
    """Routes agent drafts to humans and optionally back for revisions."""

    def __init__(self, id: str, reviewer_id: str, writer_id: str, finalize_id: str) -> None:
        super().__init__(id=id)
        self._reviewer_id = reviewer_id
        self._writer_id = writer_id
        self._finalize_id = finalize_id

    @handler
    async def on_agent_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[HumanApprovalRequest, str],
    ) -> None:
        # Capture the agent output so we can surface it to the reviewer and
        # persist iterations. The `RequestInfoExecutor` relies on this state to
        # rehydrate when checkpoints are restored.
        draft = response.agent_run_response.text or ""
        iteration = int((await ctx.get_state() or {}).get("iteration", 0)) + 1
        await ctx.set_state({"iteration": iteration, "last_draft": draft})
        # Emit a human approval request. Because this flows through
        # RequestInfoExecutor it will pause the workflow until an answer is
        # supplied either interactively or via pre-supplied responses.
        await ctx.send_message(
            HumanApprovalRequest(
                prompt="Review the draft. Reply 'approve' or provide edit instructions.",
                draft=draft,
                iteration=iteration,
            ),
            target_id=self._reviewer_id,
        )

    @handler
    async def on_human_feedback(
        self,
        feedback: RequestResponse[HumanApprovalRequest, str],
        ctx: WorkflowContext[AgentExecutorRequest | str, str],
    ) -> None:
        # The RequestResponse wrapper gives us both the human data and the
        # original request message, even when resuming from checkpoints.
        reply = (feedback.data or "").strip()
        state = await ctx.get_state() or {}
        draft = state.get("last_draft") or (feedback.original_request.draft if feedback.original_request else "")

        if reply.lower() == "approve":
            # When the human signs off we can short-circuit the workflow and
            # send the approved draft to the final executor.
            await ctx.send_message(draft, target_id=self._finalize_id)
            return

        # Any other response loops us back to the writer with fresh guidance.
        guidance = reply or "Tighten the copy and emphasise customer benefit."
        iteration = int(state.get("iteration", 1)) + 1
        await ctx.set_state({"iteration": iteration, "last_draft": draft})
        prompt = (
            "Revise the launch note. Respond with the new copy only.\n\n"
            f"Previous draft:\n{draft}\n\n"
            f"Human guidance: {guidance}"
        )
        await ctx.send_message(
            AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=prompt)], should_respond=True),
            target_id=self._writer_id,
        )


class FinaliseExecutor(Executor):
    """Publishes the approved text."""

    @handler
    async def publish(self, text: str, ctx: WorkflowContext[Any, str]) -> None:
        # Store the output so diagnostics or a UI could fetch the final copy.
        await ctx.set_state({"published_text": text})
        # Yield the final output so the workflow completes cleanly.
        await ctx.yield_output(text)


def create_workflow(*, checkpoint_storage: FileCheckpointStorage | None = None) -> "Workflow":
    """Assemble the workflow graph used by both the initial run and resume."""

    # The Azure client is created once so our agent executor can issue calls to
    # the hosted model. The agent id is stable across runs which keeps
    # checkpoints deterministic.
    chat_client = AzureChatClient(credential=AzureCliCredential())
    writer = AgentExecutor(
        chat_client.create_agent(
            instructions="Write concise, warm release notes that sound human and helpful.",
        ),
        id="writer",
    )
    # RequestInfoExecutor is the lynchpin for human-in-the-loop: every draft is
    # routed through it so checkpoints can pause while waiting for responses.
    review = RequestInfoExecutor(id="request_info")
    finalise = FinaliseExecutor(id="finalise")
    gateway = ReviewGateway(
        id="review_gateway",
        reviewer_id=review.id,
        writer_id=writer.id,
        finalize_id=finalise.id,
    )
    prepare = BriefPreparer(id="prepare_brief", agent_id=writer.id)

    # Wire the workflow DAG. Edges mirror the numbered steps described in the
    # module docstring. Because `WorkflowBuilder` is declarative, reading these
    # edges is often the quickest way to understand execution order.
    builder = (
        WorkflowBuilder(max_iterations=6)
        .set_start_executor(prepare)
        .add_edge(prepare, writer)
        .add_edge(writer, gateway)
        .add_edge(gateway, review)
        .add_edge(review, gateway)  # human resumes loop
        .add_edge(gateway, writer)  # revisions
        .add_edge(gateway, finalise)
    )
    # Opt-in to persistence when the caller provides storage. The workflow
    # object itself is identical whether or not checkpointing is enabled.
    if checkpoint_storage:
        builder = builder.with_checkpointing(checkpoint_storage=checkpoint_storage)
    return builder.build()


def _render_checkpoint_summary(checkpoints: list["WorkflowCheckpoint"]) -> None:
    """Pretty-print saved checkpoints with the new framework summaries."""

    print("\nCheckpoint summary:")
    for summary in [
        RequestInfoExecutor.checkpoint_summary(cp) for cp in sorted(checkpoints, key=lambda c: c.timestamp)
    ]:
        # Compose a single line per checkpoint so the user can scan the output
        # and pick the resume point that still has outstanding human work.
        line = (
            f"- {summary.checkpoint_id} | iter={summary.iteration_count} "
            f"| targets={summary.targets} | states={summary.executor_states}"
        )
        if summary.status:
            line += f" | status={summary.status}"
        if summary.draft_preview:
            line += f" | draft_preview={summary.draft_preview}"
        if summary.pending_requests:
            line += f" | pending_request_id={summary.pending_requests[0].request_id}"
        print(line)


def _print_events(events: list[Any]) -> tuple[str | None, list[tuple[str, HumanApprovalRequest]]]:
    """Echo workflow events to the console and collect outstanding requests."""

    completed_output: str | None = None
    requests: list[tuple[str, HumanApprovalRequest]] = []

    for event in events:
        print(f"Event: {event}")
        if isinstance(event, WorkflowOutputEvent):
            completed_output = event.data
        if isinstance(event, RequestInfoEvent) and isinstance(event.data, HumanApprovalRequest):
            # Capture pending human approvals so the caller can ask the user for
            # input after the current batch of events is processed.
            requests.append((event.request_id, event.data))
        elif isinstance(event, WorkflowStatusEvent) and event.state in {
            WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        }:
            print(f"Workflow state: {event.state.name}")

    return completed_output, requests


def _prompt_for_responses(requests: list[tuple[str, HumanApprovalRequest]]) -> dict[str, str] | None:
    """Interactive CLI prompt for any live RequestInfo requests."""

    if not requests:
        return None
    answers: dict[str, str] = {}
    for request_id, request in requests:
        # Keep the prompt conversational so testers can use the script without
        # memorising the workflow APIs.
        print("\n=== Human approval needed ===")
        print(f"request_id: {request_id}")
        if request.iteration:
            print(f"Iteration: {request.iteration}")
        print(request.prompt)
        print("Draft: \n---\n" + request.draft + "\n---")
        answer = input("Type 'approve' or enter revision guidance (or 'exit' to quit): ").strip()  # noqa: ASYNC250
        if answer.lower() == "exit":
            raise SystemExit("Stopped by user.")
        answers[request_id] = answer
    return answers


def _maybe_pre_supply_responses(cp: "WorkflowCheckpoint") -> dict[str, str] | None:
    """Offer to collect responses before resuming a checkpoint."""

    pending = RequestInfoExecutor.pending_requests_from_checkpoint(cp)
    if not pending:
        return None

    print(
        "This checkpoint still has pending human input. Provide the responses now so the resume step "
        "applies them immediately and does not re-emit the original RequestInfo event."
    )
    choice = input("Pre-supply responses for this checkpoint? [y/N]: ").strip().lower()  # noqa: ASYNC250
    if choice not in {"y", "yes"}:
        return None

    answers: dict[str, str] = {}
    for item in pending:
        iteration = item.iteration or 0
        print(f"\nPending draft (iteration {iteration} | request_id={item.request_id}):")
        draft_text = (item.draft or "").strip()
        if draft_text:
            # The shortened preview in the summary may truncate text; here we
            # show the full draft so the reviewer can make an informed choice.
            print("Draft:\n---\n" + draft_text + "\n---")
        else:
            print("Draft: [not captured in checkpoint payload - refer to your notes/log]")
        prompt_text = (item.prompt or "Review the draft").strip()
        print(prompt_text)
        answer = input("Response ('approve' or guidance, 'exit' to abort): ").strip()  # noqa: ASYNC250
        if answer.lower() == "exit":
            raise SystemExit("Resume aborted by user.")
        answers[item.request_id] = answer
    return answers


async def _consume(stream: AsyncIterable[Any]) -> list[Any]:
    """Materialise an async event stream into a list."""

    return [event async for event in stream]


async def run_interactive_session(workflow: "Workflow", initial_message: str) -> str | None:
    """Run the workflow until it either finishes or pauses for human input."""

    pending_responses: dict[str, str] | None = None
    completed_output: str | None = None
    first = True

    while completed_output is None:
        if first:
            # Kick off the workflow with the initial brief. The returned events
            # include RequestInfo events when the agent produces a draft.
            events = await _consume(workflow.run_stream(initial_message))
            first = False
        elif pending_responses:
            # Feed any answers the user just typed back into the workflow.
            events = await _consume(workflow.send_responses_streaming(pending_responses))
        else:
            break

        completed_output, requests = _print_events(events)
        if completed_output is None:
            pending_responses = _prompt_for_responses(requests)

    return completed_output


async def resume_from_checkpoint(
    workflow: "Workflow",
    checkpoint_id: str,
    storage: FileCheckpointStorage,
    pre_supplied: dict[str, str] | None,
) -> None:
    """Resume a stored checkpoint and continue until completion or another pause."""

    print(f"\nResuming from checkpoint: {checkpoint_id}")
    events = await _consume(
        workflow.run_stream_from_checkpoint(
            checkpoint_id,
            checkpoint_storage=storage,
            responses=pre_supplied,
        )
    )
    completed_output, requests = _print_events(events)
    if pre_supplied and not requests and completed_output is None:
        # When the checkpoint only needed the provided answers we let the user
        # know the workflow is waiting for the next superstep (usually another
        # agent response).
        print("Pre-supplied responses applied automatically; workflow is now waiting for the next step.")

    pending = _prompt_for_responses(requests)
    while completed_output is None and pending:
        events = await _consume(workflow.send_responses_streaming(pending))
        completed_output, requests = _print_events(events)
        if completed_output is None:
            pending = _prompt_for_responses(requests)
        else:
            break

    if completed_output:
        print(f"Workflow completed with: {completed_output}")


async def main() -> None:
    """Entry point used by both the initial run and subsequent resumes."""

    for file in TEMP_DIR.glob("*.json"):
        # Start each execution with a clean slate so the demonstration is
        # deterministic even if the directory had stale checkpoints.
        file.unlink()

    storage = FileCheckpointStorage(storage_path=TEMP_DIR)
    workflow = create_workflow(checkpoint_storage=storage)

    brief = (
        "Introduce our limited edition smart coffee grinder. Mention the $249 price, highlight the "
        "sensor that auto-adjusts the grind, and invite customers to pre-order on the website."
    )

    print("Running workflow (human approval required)...")
    completed = await run_interactive_session(workflow, initial_message=brief)
    if completed:
        print(f"Initial run completed with final copy: {completed}")
    else:
        print("Initial run paused for human input.")

    checkpoints = await storage.list_checkpoints()
    if not checkpoints:
        print("No checkpoints recorded.")
        return

    # Show the user what is available before we prompt for the index. The
    # summary helper keeps this output consistent with other tooling.
    _render_checkpoint_summary(checkpoints)

    sorted_cps = sorted(checkpoints, key=lambda c: c.timestamp)
    print("\nAvailable checkpoints:")
    for idx, cp in enumerate(sorted_cps):
        print(f"  [{idx}] id={cp.checkpoint_id} iter={cp.iteration_count}")

    # For the pause/resume demo we typically pick the latest checkpoint whose summary
    # status reads "awaiting human response" - that is the saved state that proves the
    # workflow can rehydrate, collect the pending answer, and continue after a break.
    selection = input("\nResume from which checkpoint? (press Enter to skip): ").strip()  # noqa: ASYNC250
    if not selection:
        print("No resume selected. Exiting.")
        return

    try:
        idx = int(selection)
    except ValueError:
        print("Invalid input; exiting.")
        return

    if not 0 <= idx < len(sorted_cps):
        print("Index out of range; exiting.")
        return

    chosen = sorted_cps[idx]
    summary = RequestInfoExecutor.checkpoint_summary(chosen)
    if summary.status == "completed":
        print("Selected checkpoint already reflects a completed workflow; nothing to resume.")
        return

    # If the user wants, capture their decisions now so the resume call can
    # push them into the workflow and avoid re-prompting.
    pre_responses = _maybe_pre_supply_responses(chosen)

    resumed_workflow = create_workflow()
    # Resume with a fresh workflow instance. The checkpoint carries the
    # persistent state while this object holds the runtime wiring.
    await resume_from_checkpoint(resumed_workflow, chosen.checkpoint_id, storage, pre_responses)


if __name__ == "__main__":
    asyncio.run(main())
