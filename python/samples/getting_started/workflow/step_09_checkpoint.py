# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path
from typing import Any

from agent_framework import ChatMessage, ChatRole
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    FileCheckpointStorage,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from azure.identity import AzureCliCredential

"""
Checkpointing & Resume (with an Agent Stage)

What it does:
- Demonstrates checkpointing and resume at superstep boundaries with shared state.
- Flow: UpperCase -> Reverse -> SubmitToLowerAgent -> LowerAgent (AgentExecutor) -> Finalize.
- Resumes from the checkpoint after Reverse to run only the agent + finalize stages.

Prerequisites:
- Azure AI/ Azure OpenAI for `AzureChatClient` agent.
- Authentication via `azure-identity` — uses `AzureCliCredential()` (run `az login`).
- Filesystem access to write checkpoints (local temp folder).
"""

# Define the temporary directory for storing checkpoints
DIR = os.path.dirname(__file__)
TEMP_DIR = os.path.join(DIR, "tmp", "checkpoints")
os.makedirs(TEMP_DIR, exist_ok=True)


class UpperCaseExecutor(Executor):
    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        result = text.upper()
        print(f"UpperCaseExecutor: '{text}' -> '{result}'")
        # Persist executor state into checkpointable context
        prev = await ctx.get_state() or {}
        count = int(prev.get("count", 0)) + 1
        await ctx.set_state({
            "count": count,
            "last_input": text,
            "last_output": result,
        })
        # Write to shared_state so downstream executors (and checkpoints) can see it
        await ctx.set_shared_state("original_input", text)
        await ctx.set_shared_state("upper_output", result)
        await ctx.send_message(result)


class SubmitToLowerAgent(Executor):
    """Prepare AgentExecutorRequest to lower-case the text and keep shared-state visibility."""

    def __init__(self, agent_id: str, id: str | None = None):
        super().__init__(id=id)
        self._agent_id = agent_id

    @handler
    async def submit(self, text: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        # Read from shared_state written by UpperCaseExecutor (for demo visibility)
        orig = await ctx.get_shared_state("original_input")
        upper = await ctx.get_shared_state("upper_output")
        print(f"LowerAgent (shared_state): original_input='{orig}', upper_output='{upper}'")

        prompt = f"Convert the following text to lowercase. Return ONLY the transformed text.\n\nText: {text}"
        await ctx.send_message(
            AgentExecutorRequest(messages=[ChatMessage(ChatRole.USER, text=prompt)], should_respond=True),
            target_id=self._agent_id,
        )


class FinalizeFromAgent(Executor):
    @handler
    async def finalize(self, response: AgentExecutorResponse, ctx: WorkflowContext[Any]) -> None:
        result = response.agent_run_response.text or ""
        # Persist executor state into checkpointable context
        prev = await ctx.get_state() or {}
        count = int(prev.get("count", 0)) + 1
        await ctx.set_state({
            "count": count,
            "last_output": result,
            "final": True,
        })
        await ctx.add_event(WorkflowCompletedEvent(result))


class ReverseTextExecutor(Executor):
    def __init__(self, id: str):
        """Initialize the executor with an ID."""
        super().__init__(id=id)

    @handler
    async def reverse_text(self, text: str, ctx: WorkflowContext[str]) -> None:
        result = text[::-1]
        print(f"ReverseTextExecutor: '{text}' -> '{result}'")
        # Persist executor state into checkpointable context
        prev = await ctx.get_state() or {}
        count = int(prev.get("count", 0)) + 1
        await ctx.set_state({
            "count": count,
            "last_input": text,
            "last_output": result,
        })
        await ctx.send_message(result)


async def find_checkpoint_with_message(
    checkpoint_storage: FileCheckpointStorage, workflow_id: str, needle: str
) -> str | None:
    """Find the checkpoint that contains a message data value exactly equal to 'needle'."""
    checkpoints = await checkpoint_storage.list_checkpoints(workflow_id=workflow_id)
    # Sort by timestamp ascending so earlier checkpoints appear first
    checkpoints.sort(key=lambda cp: cp.timestamp)
    for checkpoint in checkpoints:
        for executor_messages in checkpoint.messages.values():
            for message in executor_messages:
                if message.get("data") == needle:
                    return checkpoint.checkpoint_id
    return None


async def main():
    # Clear existing checkpoints in this sample directory
    checkpoint_dir = Path(TEMP_DIR)
    for file in checkpoint_dir.glob("*.json"):
        file.unlink()

    upper_case_executor = UpperCaseExecutor(id="upper_case_executor")
    reverse_text_executor = ReverseTextExecutor(id="reverse_text_executor")
    # Agent for lower-casing
    chat_client = AzureChatClient(credential=AzureCliCredential())
    lower_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=("You transform text to lowercase. Reply with ONLY the transformed text.")
        ),
        id="lower_agent",
    )
    submit_lower = SubmitToLowerAgent(agent_id=lower_agent.id, id="submit_lower")
    finalize = FinalizeFromAgent(id="finalize")

    checkpoint_storage = FileCheckpointStorage(storage_path=TEMP_DIR)

    workflow = (
        WorkflowBuilder(max_iterations=5)
        .add_edge(upper_case_executor, reverse_text_executor)
        .add_edge(reverse_text_executor, submit_lower)
        .add_edge(submit_lower, lower_agent)
        .add_edge(lower_agent, finalize)
        .set_start_executor(upper_case_executor)
        .with_checkpointing(checkpoint_storage=checkpoint_storage)
        .build()
    )

    print("Running workflow with initial message...")
    async for event in workflow.run_streaming(message="hello world"):
        print(f"Event: {event}")

    # Inspect checkpoints
    all_checkpoints = await checkpoint_storage.list_checkpoints()
    if not all_checkpoints:
        print("No checkpoints found!")
        return

    # All checkpoints from this run share one workflow_id
    workflow_id = all_checkpoints[0].workflow_id

    # Dump a quick summary including shared_state keys of interest
    print("\nCheckpoint summary:")
    for cp in sorted(all_checkpoints, key=lambda c: c.timestamp):
        msg_count = sum(len(v) for v in cp.messages.values())
        state_keys = sorted(list(cp.executor_states.keys())) if hasattr(cp, "executor_states") else []
        orig = cp.shared_state.get("original_input") if hasattr(cp, "shared_state") else None
        upper = cp.shared_state.get("upper_output") if hasattr(cp, "shared_state") else None
        print(
            f"- {cp.checkpoint_id} | "
            f"iter={cp.iteration_count} | messages={msg_count} | states={state_keys} | "
            f"shared_state: original_input='{orig}', upper_output='{upper}'"
        )

    # Find the checkpoint with DLROW OLLEH
    # This will have us resume at the third (last) executor (node)
    checkpoint_id = await find_checkpoint_with_message(checkpoint_storage, workflow_id, "DLROW OLLEH")
    if not checkpoint_id:
        print("Could not find checkpoint with 'DLROW OLLEH'!")
        return

    # The previous workflow can also be used.
    # Showing that the workflow can run from a previous checkpoint,
    # when checkpointing is not enabled for the particular instance.
    new_workflow = (
        WorkflowBuilder(max_iterations=5)
        .add_edge(upper_case_executor, reverse_text_executor)
        .add_edge(reverse_text_executor, submit_lower)
        .add_edge(submit_lower, lower_agent)
        .add_edge(lower_agent, finalize)
        .set_start_executor(upper_case_executor)
        .build()
    )

    print(f"\nResuming from checkpoint: {checkpoint_id}")
    async for event in new_workflow.run_streaming_from_checkpoint(checkpoint_id, checkpoint_storage=checkpoint_storage):
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
    Event: WorkflowCompletedEvent(data=dlrow olleh)

    Checkpoint summary:
    - dfc63e72-8e8d-454f-9b6d-0d740b9062e6 | label='after_initial_execution' | iter=0 | messages=1 | states=['upper_case_executor'] | shared_state: original_input='hello world', upper_output='HELLO WORLD'
    - a78c345a-e5d9-45ba-82c0-cb725452d91b | label='superstep_1' | iter=1 | messages=1 | states=['reverse_text_executor', 'upper_case_executor'] | shared_state: original_input='hello world', upper_output='HELLO WORLD'
    - 637c1dbd-a525-4404-9583-da03980537a2 | label='superstep_2' | iter=2 | messages=0 | states=['finalize', 'lower_agent', 'reverse_text_executor', 'submit_lower', 'upper_case_executor'] | shared_state: original_input='hello world', upper_output='HELLO WORLD'

    Resuming from checkpoint: a78c345a-e5d9-45ba-82c0-cb725452d91b
    LowerAgent (shared_state): original_input='hello world', upper_output='HELLO WORLD'
    Resumed Event: ExecutorInvokeEvent(executor_id=submit_lower)
    Resumed Event: ExecutorInvokeEvent(executor_id=lower_agent)
    Resumed Event: ExecutorInvokeEvent(executor_id=finalize)
    Resumed Event: WorkflowCompletedEvent(data=dlrow olleh)
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
