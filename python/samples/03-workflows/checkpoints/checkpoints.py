# Copyright (c) Microsoft. All rights reserved.

"""
Checkpoints Workflow Sample

Demonstrates saving and resuming workflow state using checkpoints.
A workflow computes factor pairs for numbers, with simulated interruptions
and automatic recovery from the latest checkpoint.

What you'll learn:
- Configuring checkpoint storage (InMemoryCheckpointStorage)
- Resuming a workflow from a checkpoint after interruption
- Implementing executor state management with checkpoint hooks

Related samples:
- ../state-management/ — Share state across steps
- ../human-in-the-loop/ — Pause for human input

Docs: https://learn.microsoft.com/agent-framework/workflows/overview
"""

import asyncio
import sys
from dataclasses import dataclass
from random import random
from typing import Any

from agent_framework import (
    Executor,
    InMemoryCheckpointStorage,
    WorkflowBuilder,
    WorkflowCheckpoint,
    WorkflowContext,
    handler,
)

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover


# <step_definitions>
@dataclass
class ComputeTask:
    """Task containing the list of numbers remaining to be processed."""

    remaining_numbers: list[int]


class StartExecutor(Executor):
    """Initiates the workflow by providing the upper limit for factor pair computation."""

    @handler
    async def start(self, upper_limit: int, ctx: WorkflowContext[ComputeTask]) -> None:
        print(f"StartExecutor: Starting factor pair computation up to {upper_limit}")
        await ctx.send_message(ComputeTask(remaining_numbers=list(range(1, upper_limit + 1))))


class WorkerExecutor(Executor):
    """Processes numbers to compute their factor pairs with checkpoint support."""

    def __init__(self, id: str) -> None:
        super().__init__(id=id)
        self._composite_number_pairs: dict[int, list[tuple[int, int]]] = {}

    @handler
    async def compute(
        self,
        task: ComputeTask,
        ctx: WorkflowContext[ComputeTask, dict[int, list[tuple[int, int]]]],
    ) -> None:
        next_number = task.remaining_numbers.pop(0)

        print(f"WorkerExecutor: Computing factor pairs for {next_number}")
        pairs: list[tuple[int, int]] = []
        for i in range(1, next_number):
            if next_number % i == 0:
                pairs.append((i, next_number // i))
        self._composite_number_pairs[next_number] = pairs

        if not task.remaining_numbers:
            await ctx.yield_output(self._composite_number_pairs)
        else:
            await ctx.send_message(task)

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Save the executor's internal state for checkpointing."""
        return {"composite_number_pairs": self._composite_number_pairs}

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore the executor's internal state from a checkpoint."""
        self._composite_number_pairs = state.get("composite_number_pairs", {})
# </step_definitions>


# <running>
async def main():
    checkpoint_storage = InMemoryCheckpointStorage()

    # <workflow_definition>
    workflow_builder = (
        WorkflowBuilder(start_executor="start", checkpoint_storage=checkpoint_storage)
        .register_executor(lambda: StartExecutor(id="start"), name="start")
        .register_executor(lambda: WorkerExecutor(id="worker"), name="worker")
        .add_edge("start", "worker")
        .add_edge("worker", "worker")  # Self-loop for iterative processing
    )
    # </workflow_definition>

    latest_checkpoint: WorkflowCheckpoint | None = None
    while True:
        workflow = workflow_builder.build()

        print(f"\n** Workflow {workflow.id} started **")
        event_stream = (
            workflow.run(message=10, stream=True)
            if latest_checkpoint is None
            else workflow.run(checkpoint_id=latest_checkpoint.checkpoint_id, stream=True)
        )

        output: str | None = None
        async for event in event_stream:
            if event.type == "output":
                output = event.data
                break
            if event.type == "superstep_completed" and random() < 0.5:
                print("\n** Simulating workflow interruption. Stopping execution. **")
                break

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
# </running>


if __name__ == "__main__":
    asyncio.run(main())
