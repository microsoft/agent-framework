# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Checkpointing and Resuming a Workflow

Purpose:
This sample shows how to enable checkpointing for a long-running workflow
that can be paused and resumed.

What you learn:
- How to configure checkpointing storage (InMemoryCheckpointStorage for testing)
- How to resume a workflow from a checkpoint after interruption
- How to implement executor state management with checkpoint hooks
- How to handle workflow interruptions and automatic recovery

Pipeline:
This sample shows a workflow that computes factor pairs for numbers up to a given limit:
1) A start executor that receives the upper limit and creates the initial task
2) A worker executor that processes each number to find its factor pairs
3) The worker uses checkpoint hooks to save/restore its internal state

Prerequisites:
- Basic understanding of workflow concepts, including executors, edges, events, etc.
"""

import asyncio
from dataclasses import dataclass
from random import random
from typing import Any, override

from agent_framework import (
    Executor,
    InMemoryCheckpointStorage,
    SuperStepCompletedEvent,
    WorkflowBuilder,
    WorkflowCheckpoint,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
)


@dataclass
class ComputeTask:
    """Task containing the list of numbers remaining to be processed."""

    remaining_numbers: list[int]


class StartExecutor(Executor):
    """Initiates the workflow by providing the upper limit for factor pair computation."""

    @handler
    async def start(self, upper_limit: int, ctx: WorkflowContext[ComputeTask]) -> None:
        """Start the workflow with a list of numbers to process."""
        print(f"StartExecutor: Starting factor pair computation up to {upper_limit}")
        await ctx.send_message(ComputeTask(remaining_numbers=list(range(1, upper_limit + 1))))


class WorkerExecutor(Executor):
    """Processes numbers to compute their factor pairs and manages executor state for checkpointing."""

    def __init__(self, id: str) -> None:
        super().__init__(id=id)
        self._composite_number_pairs: dict[int, list[tuple[int, int]]] = {}

    @handler
    async def compute(
        self,
        task: ComputeTask,
        ctx: WorkflowContext[ComputeTask, dict[int, list[tuple[int, int]]]],
    ) -> None:
        """Process the next number in the task, computing its factor pairs."""
        next_number = task.remaining_numbers.pop(0)

        print(f"WorkerExecutor: Computing factor pairs for {next_number}")
        pairs: list[tuple[int, int]] = []
        for i in range(1, next_number):
            if next_number % i == 0:
                pairs.append((i, next_number // i))
        self._composite_number_pairs[next_number] = pairs

        if not task.remaining_numbers:
            # All numbers processed - output the results
            await ctx.yield_output(self._composite_number_pairs)
        else:
            # More numbers to process - continue with remaining task
            await ctx.send_message(task)

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Save the executor's internal state for checkpointing."""
        return {"composite_number_pairs": self._composite_number_pairs}

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore the executor's internal state from a checkpoint."""
        self._composite_number_pairs = state.get("composite_number_pairs", {})


async def main():
    # Build workflow with checkpointing enabled
    workflow_builder = (
        WorkflowBuilder()
        .register_executor(lambda: StartExecutor(id="start"), name="start")
        .register_executor(lambda: WorkerExecutor(id="worker"), name="worker")
        .set_start_executor("start")
        .add_edge("start", "worker")
        .add_edge("worker", "worker")  # Self-loop for iterative processing
    )
    checkpoint_storage = InMemoryCheckpointStorage()
    workflow_builder = workflow_builder.with_checkpointing(checkpoint_storage=checkpoint_storage)

    # Run workflow with automatic checkpoint recovery
    latest_checkpoint: WorkflowCheckpoint | None = None
    while True:
        workflow = workflow_builder.build()

        # Start from checkpoint or fresh execution
        print(f"\n** Workflow {workflow.id} started **")
        event_stream = (
            workflow.run_stream(message=10)
            if latest_checkpoint is None
            else workflow.run_stream(checkpoint_id=latest_checkpoint.checkpoint_id)
        )

        output: str | None = None
        async for event in event_stream:
            if isinstance(event, WorkflowOutputEvent):
                output = event.data
                break
            if isinstance(event, SuperStepCompletedEvent) and random() < 0.5:
                # Randomly simulate system interruptions
                # The `SuperStepCompletedEvent` ensures we only interrupt after
                # the current super-step is fully complete and checkpointed.
                # If we interrupt mid-step, the workflow may resume from an earlier point.
                print("\n** Simulating workflow interruption. Stopping execution. **")
                break

        # Find the latest checkpoint to resume from
        all_checkpoints = await checkpoint_storage.list_checkpoints()
        if not all_checkpoints:
            raise RuntimeError("No checkpoints available to resume from.")
        latest_checkpoint = all_checkpoints[-1]
        print(
            f"Checkpoint {latest_checkpoint.checkpoint_id}: "
            f"(iter={latest_checkpoint.iteration_count}, messages={latest_checkpoint.messages})"
        )

        if output is not None:
            print(f"\nWorkflow completed successfully with output: {output}")
            break


if __name__ == "__main__":
    asyncio.run(main())
