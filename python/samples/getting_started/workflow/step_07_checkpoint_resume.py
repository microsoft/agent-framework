# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
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
- Finding a specific checkpoint by searching for message content
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


class ReverseTextExecutor(Executor):
    """An executor that reverses text."""

    @handler
    async def reverse_text(self, text: str, ctx: WorkflowContext) -> None:
        """Execute the task by reversing the input string."""
        result = text[::-1]
        print(f"ReverseTextExecutor: '{text}' -> '{result}'")
        await ctx.send_message(result)
        await ctx.add_event(WorkflowCompletedEvent(result))


def find_hello_world_checkpoint(checkpoint_dir: Path) -> str | None:
    """Find the checkpoint containing 'HELLO WORLD'."""
    for checkpoint_file in checkpoint_dir.glob("*.json"):
        with checkpoint_file.open() as f:
            data = json.load(f)

        messages = data.get("messages", {})
        for executor_messages in messages.values():
            for message in executor_messages:
                if message.get("data") == "HELLO WORLD":
                    return data["checkpoint_id"]
    return None


async def main():
    # Clear existing checkpoints, if they exist
    checkpoint_dir = Path(TEMP_DIR)
    for file in checkpoint_dir.glob("*.json"):
        file.unlink()

    # Create executors and workflow
    upper_case_executor = UpperCaseExecutor(id="upper_case_executor")
    reverse_text_executor = ReverseTextExecutor(id="reverse_text_executor")

    # Create a checkpoint storage
    checkpoint_storage = FileCheckpointStorage(storage_path=TEMP_DIR)

    workflow = (
        WorkflowBuilder()
        .add_edge(upper_case_executor, reverse_text_executor)
        .set_start_executor(upper_case_executor)
        .with_checkpointing(checkpoint_storage=checkpoint_storage)
        .build()
    )

    # Run workflow with initial message
    print("Running workflow with initial message...")
    async for event in workflow.run_streaming(message="hello world"):
        print(f"Event: {event}")

    # Find checkpoint with "HELLO WORLD"
    checkpoint_id = find_hello_world_checkpoint(checkpoint_dir)

    if not checkpoint_id:
        print("Could not find checkpoint with 'HELLO WORLD'!")
        return

    print(f"\nFound checkpoint: {checkpoint_id}")

    # Resume from checkpoint using the same workflow instance
    # Note: You could also create a new workflow instance and call
    # run_stream_from_checkpoint() on it - useful for loading checkpoints
    # in a different process or after application restart
    # print("Resuming from checkpoint...")
    # async for event in workflow.run_streaming_from_checkpoint(checkpoint_id, checkpoint_storage=checkpoint_storage):
    #     print(f"Resumed Event: {event}")

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
