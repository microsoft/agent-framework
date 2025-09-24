# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessage,
    Executor,
    FileCheckpointStorage,
    RequestInfoExecutor,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential

if TYPE_CHECKING:
    from agent_framework import Workflow
    from agent_framework._workflow._checkpoint import WorkflowCheckpoint

"""
Sample: Checkpointing and Resuming a Workflow (with an Agent stage)

Purpose:
This sample shows how to enable checkpointing at superstep boundaries, persist both
executor-local state and shared workflow state, and then resume execution from a specific
checkpoint. The workflow demonstrates a simple text-processing pipeline that includes
an LLM-backed AgentExecutor stage.

Pipeline:
1) UpperCaseExecutor converts input to uppercase and records state.
2) ReverseTextExecutor reverses the string.
3) SubmitToLowerAgent prepares an AgentExecutorRequest for the lowercasing agent.
4) lower_agent (AgentExecutor) converts text to lowercase via Azure OpenAI.
5) FinalizeFromAgent yields the final result.

What you learn:
- How to persist executor state using ctx.get_state and ctx.set_state.
- How to persist shared workflow state using ctx.set_shared_state for cross-executor visibility.
- How to configure FileCheckpointStorage and call with_checkpointing on WorkflowBuilder.
- How to list and inspect checkpoints programmatically.
- How to interactively choose a checkpoint to resume from (instead of always resuming
    from the most recent or a hard-coded one) using run_stream_from_checkpoint.
- How workflows complete by yielding outputs when idle, not via explicit completion events.

Prerequisites:
- Azure AI or Azure OpenAI available for AzureChatClient.
- Authentication with azure-identity via AzureCliCredential. Run az login locally.
- Filesystem access for writing JSON checkpoint files in a temp directory.
"""

# Define the temporary directory for storing checkpoints.
# These files allow the workflow to be resumed later.
DIR = os.path.dirname(__file__)
TEMP_DIR = os.path.join(DIR, "tmp", "checkpoints")
os.makedirs(TEMP_DIR, exist_ok=True)


class UpperCaseExecutor(Executor):
    """Uppercases the input text and persists both local and shared state."""

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        result = text.upper()
        print(f"UpperCaseExecutor: '{text}' -> '{result}'")

        # Persist executor-local state so it is captured in checkpoints
        # and available after resume for observability or logic.
        prev = await ctx.get_state() or {}
        count = int(prev.get("count", 0)) + 1
        await ctx.set_state({
            "count": count,
            "last_input": text,
            "last_output": result,
        })

        # Write to shared_state so downstream executors and any resumed runs can read it.
        await ctx.set_shared_state("original_input", text)
        await ctx.set_shared_state("upper_output", result)

        # Send transformed text to the next executor.
        await ctx.send_message(result)


class SubmitToLowerAgent(Executor):
    """Builds an AgentExecutorRequest to send to the lowercasing agent while keeping shared-state visibility."""

    def __init__(self, id: str, agent_id: str):
        super().__init__(id=id)
        self._agent_id = agent_id

    @handler
    async def submit(self, text: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        # Demonstrate reading shared_state written by UpperCaseExecutor.
        # Shared state survives across checkpoints and is visible to all executors.
        orig = await ctx.get_shared_state("original_input")
        upper = await ctx.get_shared_state("upper_output")
        print(f"LowerAgent (shared_state): original_input='{orig}', upper_output='{upper}'")

        # Build a minimal, deterministic prompt for the AgentExecutor.
        prompt = f"Convert the following text to lowercase. Return ONLY the transformed text.\n\nText: {text}"

        # Send to the AgentExecutor. should_respond=True instructs the agent to produce a reply.
        await ctx.send_message(
            AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=prompt)], should_respond=True),
            target_id=self._agent_id,
        )


class FinalizeFromAgent(Executor):
    """Consumes the AgentExecutorResponse and yields the final result."""

    @handler
    async def finalize(self, response: AgentExecutorResponse, ctx: WorkflowContext[Any, str]) -> None:
        result = response.agent_run_response.text or ""

        # Persist executor-local state for auditability when inspecting checkpoints.
        prev = await ctx.get_state() or {}
        count = int(prev.get("count", 0)) + 1
        await ctx.set_state({
            "count": count,
            "last_output": result,
            "final": True,
        })

        # Yield the final result so external consumers see the final value.
        await ctx.yield_output(result)


class ReverseTextExecutor(Executor):
    """Reverses the input text and persists local state."""

    @handler
    async def reverse_text(self, text: str, ctx: WorkflowContext[str]) -> None:
        result = text[::-1]
        print(f"ReverseTextExecutor: '{text}' -> '{result}'")

        # Persist executor-local state so checkpoint inspection can reveal progress.
        prev = await ctx.get_state() or {}
        count = int(prev.get("count", 0)) + 1
        await ctx.set_state({
            "count": count,
            "last_input": text,
            "last_output": result,
        })

        # Forward the reversed string to the next stage.
        await ctx.send_message(result)


def create_workflow(checkpoint_storage: FileCheckpointStorage) -> "Workflow":
    # Instantiate the pipeline executors.
    upper_case_executor = UpperCaseExecutor(id="upper-case")
    reverse_text_executor = ReverseTextExecutor(id="reverse-text")

    # Configure the agent stage that lowercases the text.
    chat_client = AzureChatClient(credential=AzureCliCredential())
    lower_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=("You transform text to lowercase. Reply with ONLY the transformed text.")
        ),
        id="lower_agent",
    )

    # Bridge to the agent and terminalization stage.
    submit_lower = SubmitToLowerAgent(id="submit_lower", agent_id=lower_agent.id)
    finalize = FinalizeFromAgent(id="finalize")

    # Build the workflow with checkpointing enabled.
    return (
        WorkflowBuilder(max_iterations=5)
        .add_edge(upper_case_executor, reverse_text_executor)  # Uppercase -> Reverse
        .add_edge(reverse_text_executor, submit_lower)  # Reverse -> Build Agent request
        .add_edge(submit_lower, lower_agent)  # Submit to AgentExecutor
        .add_edge(lower_agent, finalize)  # Agent output -> Finalize
        .set_start_executor(upper_case_executor)  # Entry point
        .with_checkpointing(checkpoint_storage=checkpoint_storage)  # Enable persistence
        .build()
    )


def _render_checkpoint_summary(checkpoints: list["WorkflowCheckpoint"]) -> None:
    """Display human-friendly checkpoint metadata using framework summaries."""

    if not checkpoints:
        return

    print("\nCheckpoint summary:")
    for cp in sorted(checkpoints, key=lambda c: c.timestamp):
        summary = RequestInfoExecutor.checkpoint_summary(cp)
        msg_count = sum(len(v) for v in cp.messages.values())
        state_keys = sorted(cp.executor_states.keys())
        orig = cp.shared_state.get("original_input")
        upper = cp.shared_state.get("upper_output")

        line = (
            f"- {summary.checkpoint_id} | iter={summary.iteration_count} | messages={msg_count} | states={state_keys}"
        )
        if summary.status:
            line += f" | status={summary.status}"
        line += f" | shared_state: original_input='{orig}', upper_output='{upper}'"
        print(line)


async def main():
    # Clear existing checkpoints in this sample directory for a clean run.
    checkpoint_dir = Path(TEMP_DIR)
    for file in checkpoint_dir.glob("*.json"):
        file.unlink()

    # Backing store for checkpoints written by with_checkpointing.
    checkpoint_storage = FileCheckpointStorage(storage_path=TEMP_DIR)

    workflow = create_workflow(checkpoint_storage=checkpoint_storage)

    # Run the full workflow once and observe events as they stream.
    print("Running workflow with initial message...")
    async for event in workflow.run_stream(message="hello world"):
        print(f"Event: {event}")

    # Inspect checkpoints written during the run.
    all_checkpoints = await checkpoint_storage.list_checkpoints()
    if not all_checkpoints:
        print("No checkpoints found!")
        return

    # All checkpoints created by this run share the same workflow_id.
    workflow_id = all_checkpoints[0].workflow_id

    _render_checkpoint_summary(all_checkpoints)

    # Offer an interactive selection of checkpoints to resume from.
    sorted_cps = sorted([cp for cp in all_checkpoints if cp.workflow_id == workflow_id], key=lambda c: c.timestamp)

    print("\nAvailable checkpoints to resume from:")
    for idx, cp in enumerate(sorted_cps):
        summary = RequestInfoExecutor.checkpoint_summary(cp)
        line = f"  [{idx}] id={summary.checkpoint_id} iter={summary.iteration_count}"
        if summary.status:
            line += f" status={summary.status}"
        msg_count = sum(len(v) for v in cp.messages.values())
        line += f" messages={msg_count}"
        print(line)

    user_input = input(
        "\nEnter checkpoint index (or paste checkpoint id) to resume from, or press Enter to skip resume: "
    ).strip()

    if not user_input:
        print("No checkpoint selected. Exiting without resuming.")
        return

    chosen_cp_id: str | None = None

    # Try as index first
    if user_input.isdigit():
        idx = int(user_input)
        if 0 <= idx < len(sorted_cps):
            chosen_cp_id = sorted_cps[idx].checkpoint_id
    # Fall back to direct id match
    if chosen_cp_id is None:
        for cp in sorted_cps:
            if cp.checkpoint_id.startswith(user_input):  # allow prefix match for convenience
                chosen_cp_id = cp.checkpoint_id
                break

    if chosen_cp_id is None:
        print("Input did not match any checkpoint. Exiting without resuming.")
        return

    # You can reuse the same workflow graph definition and resume from a prior checkpoint.
    # This second workflow instance does not enable checkpointing to show that resumption
    # reads from stored state but need not write new checkpoints.
    new_workflow = create_workflow(checkpoint_storage=checkpoint_storage)

    print(f"\nResuming from checkpoint: {chosen_cp_id}")
    async for event in new_workflow.run_stream_from_checkpoint(chosen_cp_id, checkpoint_storage=checkpoint_storage):
        print(f"Resumed Event: {event}")

    """
    Sample Output:

    Running workflow with initial message...
    UpperCaseExecutor: 'hello world' -> 'HELLO WORLD'
    Event: ExecutorInvokeEvent(executor_id=upper_case_executor)
    Event: ExecutorCompletedEvent(executor_id=upper_case_executor)
    ReverseTextExecutor: 'HELLO WORLD' -> 'DLROW OLLEH'
    Event: ExecutorInvokeEvent(executor_id=reverse_text_executor)
    Event: ExecutorCompletedEvent(executor_id=reverse_text_executor)
    LowerAgent (shared_state): original_input='hello world', upper_output='HELLO WORLD'
    Event: ExecutorInvokeEvent(executor_id=submit_lower)
    Event: ExecutorInvokeEvent(executor_id=lower_agent)
    Event: ExecutorInvokeEvent(executor_id=finalize)

    Checkpoint summary:
    - dfc63e72-8e8d-454f-9b6d-0d740b9062e6 | label='after_initial_execution' | iter=0 | messages=1 | states=['upper_case_executor'] | shared_state: original_input='hello world', upper_output='HELLO WORLD'
    - a78c345a-e5d9-45ba-82c0-cb725452d91b | label='superstep_1' | iter=1 | messages=1 | states=['reverse_text_executor', 'upper_case_executor'] | shared_state: original_input='hello world', upper_output='HELLO WORLD'
    - 637c1dbd-a525-4404-9583-da03980537a2 | label='superstep_2' | iter=2 | messages=0 | states=['finalize', 'lower_agent', 'reverse_text_executor', 'submit_lower', 'upper_case_executor'] | shared_state: original_input='hello world', upper_output='HELLO WORLD'

    Available checkpoints to resume from:
        [0] id=dfc63e72-... iter=0 messages=1 label='after_initial_execution'
        [1] id=a78c345a-... iter=1 messages=1 label='superstep_1'
        [2] id=637c1dbd-... iter=2 messages=0 label='superstep_2'

    Enter checkpoint index (or paste checkpoint id) to resume from, or press Enter to skip resume: 1

    Resuming from checkpoint: a78c345a-e5d9-45ba-82c0-cb725452d91b
    LowerAgent (shared_state): original_input='hello world', upper_output='HELLO WORLD'
    Resumed Event: ExecutorInvokeEvent(executor_id=submit_lower)
    Resumed Event: ExecutorInvokeEvent(executor_id=lower_agent)
    Resumed Event: ExecutorInvokeEvent(executor_id=finalize)
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
