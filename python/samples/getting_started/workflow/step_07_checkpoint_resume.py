# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework.workflow import (
    Executor,
    FileCheckpointStorage,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)

"""
This sample demonstrates workflow checkpointing and resumption capabilities.

The workflow processes a text string through two executors:
1. UpperCaseExecutor: Converts input to uppercase
2. ReverseTextExecutor: Reverses the text and emits completion event

The sample shows:
- Running a workflow with run_streaming() and automatic checkpoint creation
- Finding a specific checkpoint by using the checkpoint storage API to search for message content
- Resuming workflow execution from a checkpoint using run_streaming_from_checkpoint()
"""

# Define the temporary directory for storing checkpoints
DIR = os.path.dirname(__file__)
TEMP_DIR = os.path.join(DIR, "tmp", "checkpoints")
# Ensure the temporary directory exists
os.makedirs(TEMP_DIR, exist_ok=True)


class UpperCaseExecutor(Executor):
    """An executor that converts text to uppercase."""

    @handler(output_types=[str])
    async def to_upper_case(self, text: str, ctx: WorkflowContext) -> None:
        """Execute the task by converting the input string to uppercase."""
        result = text.upper()
        print(f"UpperCaseExecutor: '{text}' -> '{result}'")
        await ctx.send_message(result)


class LowerCaseExecutor(Executor):
    """An executor that converts text to lowercase."""

    @handler(output_types=[str])
    async def to_lower_case(self, text: str, ctx: WorkflowContext) -> None:
        """Execute the task by converting the input string to lowercase."""
        result = text.lower()
        print(f"LowerCaseExecutor: '{text}' -> '{result}'")
        # Final executor - only emit completion event, don't send message
        await ctx.add_event(WorkflowCompletedEvent(result))


class ReverseTextExecutor(Executor):
    """An executor that reverses text."""

    @handler(output_types=[str])
    async def reverse_text(self, text: str, ctx: WorkflowContext) -> None:
        """Execute the task by reversing the input string."""
        result = text[::-1]
        print(f"ReverseTextExecutor: '{text}' -> '{result}'")
        # Send message to next executor in the chain
        await ctx.send_message(result)


def find_expected_checkpoint(checkpoint_storage: FileCheckpointStorage, workflow_id: str) -> str | None:
    """Find the checkpoint containing 'DLROW OLLEH' using the checkpoint storage API."""
    # Get all checkpoints for this workflow
    checkpoints = checkpoint_storage.list_checkpoints(workflow_id=workflow_id)

    for checkpoint in checkpoints:
        messages = checkpoint.messages
        for executor_messages in messages.values():
            for message in executor_messages:
                if message.get("data") == "DLROW OLLEH":
                    return checkpoint.checkpoint_id
    return None


async def main():
    # Clear existing checkpoints, if they exist
    checkpoint_dir = Path(TEMP_DIR)
    for file in checkpoint_dir.glob("*.json"):
        file.unlink()

    # Create executors and workflow
    upper_case_executor = UpperCaseExecutor(id="upper_case_executor")
    reverse_text_executor = ReverseTextExecutor(id="reverse_text_executor")
    lower_case_executor = LowerCaseExecutor(id="lower_case_executor")

    # Create a checkpoint storage
    checkpoint_storage = FileCheckpointStorage(storage_path=TEMP_DIR)

    workflow = (
        WorkflowBuilder()
        .add_edge(upper_case_executor, reverse_text_executor)
        .add_edge(reverse_text_executor, lower_case_executor)
        .set_start_executor(upper_case_executor)
        .with_checkpointing(checkpoint_storage=checkpoint_storage)
        .build()
    )

    # Run workflow with initial message
    print("Running workflow with initial message...")
    async for event in workflow.run_streaming(message="hello world"):
        print(f"Event: {event}")

    # Get all checkpoints and find one with "HELLO WORLD"
    # Note: We need to get the workflow_id from one of the checkpoints since it's generated automatically
    all_checkpoints = checkpoint_storage.list_checkpoints()
    if not all_checkpoints:
        print("No checkpoints found!")
        return

    workflow_id = all_checkpoints[0].workflow_id  # All checkpoints from this run will have the same workflow_id
    checkpoint_id = find_expected_checkpoint(checkpoint_storage, workflow_id)

    if not checkpoint_id:
        print("Could not find checkpoint with 'DLROW OLLEH'!")
        return

    print(f"\nFound checkpoint: {checkpoint_id}")

    # Resume from checkpoint using the same workflow instance
    # Note: You could also create a new workflow instance and call
    # run_stream_from_checkpoint() on it - useful for loading checkpoints
    # in a different process or after application restart
    print("Resuming from checkpoint...")
    async for event in workflow.run_streaming_from_checkpoint(checkpoint_id, checkpoint_storage=checkpoint_storage):
        print(f"Resumed Event: {event}")

    """
    Sample Output:

    Running workflow with initial message...
    UpperCaseExecutor: 'hello world' -> 'HELLO WORLD'
    Event: ExecutorInvokeEvent(executor_id=upper_case_executor)
    Event: ExecutorCompletedEvent(executor_id=upper_case_executor)
    ReverseTextExecutor: 'HELLO WORLD' -> 'DLROW OLLEH'
    Event: ExecutorInvokeEvent(executor_id=reverse_text_executor)
    Event: WorkflowCompletedEvent(data=DLROW OLLEH)
    Event: ExecutorCompletedEvent(executor_id=reverse_text_executor)

    Found checkpoint: 3700c897-0d79-476f-8761-701b7f8fbab7
    Resuming from checkpoint...
    ReverseTextExecutor: 'HELLO WORLD' -> 'DLROW OLLEH'
    Resumed Event: ExecutorInvokeEvent(executor_id=reverse_text_executor)
    Resumed Event: WorkflowCompletedEvent(data=DLROW OLLEH)
    Resumed Event: ExecutorCompletedEvent(executor_id=reverse_text_executor)
    """


if __name__ == "__main__":
    asyncio.run(main())
