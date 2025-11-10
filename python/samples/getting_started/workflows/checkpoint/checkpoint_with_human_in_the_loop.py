# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from pathlib import Path

# NOTE: the Azure client imports above are real dependencies. When running this
# sample outside of Azure-enabled environments you may wish to swap in the
# `agent_framework.builtin` chat client or mock the writer executor. We keep the
# concrete import here so readers can see an end-to-end configuration.
from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessage,
    Executor,
    FileCheckpointStorage,
    RequestInfoEvent,
    Role,
    Workflow,
    WorkflowBuilder,
    WorkflowCheckpoint,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowStatusEvent,
    get_checkpoint_summary,
    handler,
    response_handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Checkpoint + human-in-the-loop quickstart.

This getting-started sample keeps the moving pieces to a minimum:

1. A brief is turned into a consistent prompt for an AI copywriter.
2. The copywriter (an `AgentExecutor`) drafts release notes.
3. A reviewer gateway sends a request for approval for every draft.
4. The workflow records checkpoints between each superstep so you can stop the
   program, restart later, and optionally pre-supply human answers on resume.

Key concepts demonstrated
-------------------------
- Minimal executor pipeline with checkpoint persistence.
- Human-in-the-loop pause/resume with checkpoint restoration.

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
class HumanApprovalRequest:
    """Request sent to the human reviewer."""

    # These fields are intentionally simple because they are serialised into
    # checkpoints. Keeping them primitive types guarantees the new
    # `pending_requests_from_checkpoint` helper can reconstruct them on resume.
    prompt: str = ""
    draft: str = ""
    iteration: int = 0


class ReviewGateway(Executor):
    """Routes agent drafts to humans and optionally back for revisions."""

    def __init__(self, id: str, writer_id: str) -> None:
        super().__init__(id=id)
        self._writer_id = writer_id

    @handler
    async def on_agent_response(self, response: AgentExecutorResponse, ctx: WorkflowContext) -> None:
        # Capture the agent output so we can surface it to the reviewer and persist iterations.
        draft = response.agent_run_response.text or ""
        iteration = int((await ctx.get_executor_state() or {}).get("iteration", 0)) + 1
        await ctx.set_executor_state({"iteration": iteration, "last_draft": draft})
        # Emit a human approval request.
        await ctx.request_info(
            request_data=HumanApprovalRequest(
                prompt="Review the draft. Reply 'approve' or provide edit instructions.",
                draft=draft,
                iteration=iteration,
            ),
            response_type=str,
        )

    @response_handler
    async def on_human_feedback(
        self,
        original_request: HumanApprovalRequest,
        feedback: str,
        ctx: WorkflowContext[AgentExecutorRequest | str, str],
    ) -> None:
        # The `original_request` is the request we sent earlier that is now being answered.
        reply = feedback.strip()
        state = await ctx.get_executor_state() or {}
        draft = state.get("last_draft") or (original_request.draft or "")

        if reply.lower() == "approve":
            # Workflow is completed when the human approves.
            await ctx.yield_output(draft)
            return

        # Any other response loops us back to the writer with fresh guidance.
        guidance = reply or "Tighten the copy and emphasise customer benefit."
        iteration = int(state.get("iteration", 1)) + 1
        await ctx.set_executor_state({"iteration": iteration, "last_draft": draft})
        prompt = (
            "Revise the launch note. Respond with the new copy only.\n\n"
            f"Previous draft:\n{draft}\n\n"
            f"Human guidance: {guidance}"
        )
        await ctx.send_message(
            AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=prompt)], should_respond=True),
            target_id=self._writer_id,
        )


def create_workflow(checkpoint_storage: FileCheckpointStorage) -> Workflow:
    """Assemble the workflow graph used by both the initial run and resume."""

    # The Azure client is created once so our agent executor can issue calls to the hosted
    # model. The agent id is stable across runs which keeps checkpoints deterministic.
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
    agent = chat_client.create_agent(instructions="Write concise, warm release notes that sound human and helpful.")

    writer = AgentExecutor(agent, id="writer")
    gateway = ReviewGateway(id="review_gateway", writer_id=writer.id)
    prepare = BriefPreparer(id="prepare_brief", agent_id=writer.id)

    # Wire the workflow DAG. Edges mirror the numbered steps described in the
    # module docstring. Because `WorkflowBuilder` is declarative, reading these
    # edges is often the quickest way to understand execution order.
    workflow_builder = (
        WorkflowBuilder(max_iterations=6)
        .set_start_executor(prepare)
        .add_edge(prepare, writer)
        .add_edge(writer, gateway)
        .add_edge(gateway, writer)  # revisions loop
        .with_checkpointing(checkpoint_storage=checkpoint_storage)
    )

    return workflow_builder.build()


def render_checkpoint_summary(checkpoints: list["WorkflowCheckpoint"]) -> None:
    """Pretty-print saved checkpoints with the new framework summaries."""

    print("\nCheckpoint summary:")
    for summary in [get_checkpoint_summary(cp) for cp in sorted(checkpoints, key=lambda c: c.timestamp)]:
        # Compose a single line per checkpoint so the user can scan the output
        # and pick the resume point that still has outstanding human work.
        line = (
            f"- {summary.checkpoint_id} | timestamp={summary.timestamp} | iter={summary.iteration_count} "
            f"| targets={summary.targets} | states={summary.executor_ids}"
        )
        if summary.status:
            line += f" | status={summary.status}"
        if summary.pending_request_info_events:
            line += f" | pending_request_id={summary.pending_request_info_events[0].request_id}"
        print(line)


def prompt_for_responses(requests: dict[str, HumanApprovalRequest]) -> dict[str, str]:
    """Interactive CLI prompt for any live RequestInfo requests."""

    responses: dict[str, str] = {}
    for request_id, request in requests.items():
        print("\n=== Human approval needed ===")
        print(f"request_id: {request_id}")
        print(f"Iteration: {request.iteration}")
        print(request.prompt)
        print("Draft: \n---\n" + request.draft + "\n---")
        response = input("Type 'approve' or enter revision guidance (or 'exit' to quit): ").strip()
        if response.lower() == "exit":
            raise SystemExit("Stopped by user.")
        responses[request_id] = response

    return responses


async def run_interactive_session(
    workflow: Workflow,
    initial_message: str | None = None,
    checkpoint_id: str | None = None,
) -> str:
    """Run the workflow until it either finishes or pauses for human input."""

    requests: dict[str, HumanApprovalRequest] = {}
    responses: dict[str, str] | None = None
    completed_output: str | None = None

    while True:
        if responses:
            event_stream = workflow.send_responses_streaming(responses)
            requests.clear()
            responses = None
        else:
            if initial_message:
                print(f"\nStarting workflow with brief: {initial_message}\n")
                event_stream = workflow.run_stream(initial_message)
            elif checkpoint_id:
                print("\nStarting workflow from checkpoint...\n")
                event_stream = workflow.run_stream(checkpoint_id)
            else:
                raise ValueError("Either initial_message or checkpoint_id must be provided")

        async for event in event_stream:
            if isinstance(event, WorkflowStatusEvent):
                print(event)
            if isinstance(event, WorkflowOutputEvent):
                completed_output = event.data
            if isinstance(event, RequestInfoEvent):
                if isinstance(event.data, HumanApprovalRequest):
                    requests[event.request_id] = event.data
                else:
                    raise ValueError("Unexpected request data type")

        if completed_output:
            break

        if requests:
            responses = prompt_for_responses(requests)
            continue

        raise RuntimeError("Workflow stopped without completing or requesting input")

    return completed_output


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
    result = await run_interactive_session(workflow, initial_message=brief)
    print(f"Workflow completed with: {result}")

    checkpoints = await storage.list_checkpoints()
    if not checkpoints:
        print("No checkpoints recorded.")
        return

    # Show the user what is available before we prompt for the index. The
    # summary helper keeps this output consistent with other tooling.
    render_checkpoint_summary(checkpoints)

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
    summary = get_checkpoint_summary(chosen)
    if summary.status == "completed":
        print("Selected checkpoint already reflects a completed workflow; nothing to resume.")
        return

    new_workflow = create_workflow(checkpoint_storage=storage)
    # Resume with a fresh workflow instance. The checkpoint carries the
    # persistent state while this object holds the runtime wiring.
    result = await run_interactive_session(new_workflow, checkpoint_id=chosen.checkpoint_id)
    print(f"Workflow completed with: {result}")


if __name__ == "__main__":
    asyncio.run(main())
