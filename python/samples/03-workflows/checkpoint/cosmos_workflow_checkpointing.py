# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: T201

"""Sample: Workflow Checkpointing with Cosmos DB NoSQL.

Purpose:
This sample shows how to use Azure Cosmos DB NoSQL as a persistent checkpoint
storage backend for workflows, enabling durable pause-and-resume across
process restarts.

What you learn:
- How to configure CosmosCheckpointStorage for workflow checkpointing
- How to run a workflow that automatically persists checkpoints to Cosmos DB
- How to resume a workflow from a Cosmos DB checkpoint
- How to list and inspect available checkpoints

Prerequisites:
- An Azure Cosmos DB account (or local emulator)
- Environment variables set (see below)

Environment variables:
  AZURE_COSMOS_ENDPOINT            - Cosmos DB account endpoint
  AZURE_COSMOS_DATABASE_NAME       - Database name
  AZURE_COSMOS_CONTAINER_NAME      - Container name for checkpoints
Optional:
  AZURE_COSMOS_KEY                 - Account key (if not using Azure credentials)
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Any

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowCheckpoint,
    WorkflowContext,
    handler,
)

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover

from agent_framework_azure_cosmos import CosmosCheckpointStorage


@dataclass
class ComputeTask:
    """Task containing the list of numbers remaining to be processed."""

    remaining_numbers: list[int]


class StartExecutor(Executor):
    """Initiates the workflow by providing the upper limit."""

    @handler
    async def start(self, upper_limit: int, ctx: WorkflowContext[ComputeTask]) -> None:
        """Start the workflow with numbers up to the given limit."""
        print(f"StartExecutor: Starting computation up to {upper_limit}")
        await ctx.send_message(ComputeTask(remaining_numbers=list(range(1, upper_limit + 1))))


class WorkerExecutor(Executor):
    """Processes numbers and manages executor state for checkpointing."""

    def __init__(self, id: str) -> None:
        """Initialize the worker executor."""
        super().__init__(id=id)
        self._results: dict[int, list[tuple[int, int]]] = {}

    @handler
    async def compute(
        self,
        task: ComputeTask,
        ctx: WorkflowContext[ComputeTask, dict[int, list[tuple[int, int]]]],
    ) -> None:
        """Process the next number, computing its factor pairs."""
        next_number = task.remaining_numbers.pop(0)
        print(f"WorkerExecutor: Processing {next_number}")

        pairs: list[tuple[int, int]] = []
        for i in range(1, next_number):
            if next_number % i == 0:
                pairs.append((i, next_number // i))
        self._results[next_number] = pairs

        if not task.remaining_numbers:
            await ctx.yield_output(self._results)
        else:
            await ctx.send_message(task)

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        return {"results": self._results}

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        self._results = state.get("results", {})


async def main() -> None:
    """Run the workflow checkpointing sample with Cosmos DB."""
    cosmos_endpoint = os.getenv("AZURE_COSMOS_ENDPOINT")
    cosmos_database_name = os.getenv("AZURE_COSMOS_DATABASE_NAME")
    cosmos_container_name = os.getenv("AZURE_COSMOS_CONTAINER_NAME")
    cosmos_key = os.getenv("AZURE_COSMOS_KEY")

    if not cosmos_endpoint or not cosmos_database_name or not cosmos_container_name:
        print("Please set AZURE_COSMOS_ENDPOINT, AZURE_COSMOS_DATABASE_NAME, and AZURE_COSMOS_CONTAINER_NAME.")
        return

    # Authentication: supports both managed identity/RBAC and key-based auth.
    # When AZURE_COSMOS_KEY is set, key-based auth is used.
    # Otherwise, falls back to DefaultAzureCredential (properly closed via async with).
    if cosmos_key:
        async with CosmosCheckpointStorage(
            endpoint=cosmos_endpoint,
            credential=cosmos_key,
            database_name=cosmos_database_name,
            container_name=cosmos_container_name,
        ) as checkpoint_storage:
            await _run_workflow(checkpoint_storage)
    else:
        from azure.identity.aio import DefaultAzureCredential

        async with (
            DefaultAzureCredential() as credential,
            CosmosCheckpointStorage(
                endpoint=cosmos_endpoint,
                credential=credential,
                database_name=cosmos_database_name,
                container_name=cosmos_container_name,
            ) as checkpoint_storage,
        ):
            await _run_workflow(checkpoint_storage)


async def _run_workflow(checkpoint_storage: CosmosCheckpointStorage) -> None:
    """Build and run the workflow with Cosmos DB checkpointing."""
    start = StartExecutor(id="start")
    worker = WorkerExecutor(id="worker")
    workflow_builder = (
        WorkflowBuilder(start_executor=start, checkpoint_storage=checkpoint_storage)
        .add_edge(start, worker)
        .add_edge(worker, worker)
    )

    # --- First run: execute the workflow ---
    print("\n=== First Run ===\n")
    workflow = workflow_builder.build()

    output = None
    async for event in workflow.run(message=8, stream=True):
        if event.type == "output":
            output = event.data

    print(f"Factor pairs computed: {output}")

    # List checkpoints saved in Cosmos DB
    checkpoint_ids = await checkpoint_storage.list_checkpoint_ids(
        workflow_name=workflow.name,
    )
    print(f"\nCheckpoints in Cosmos DB: {len(checkpoint_ids)}")
    for cid in checkpoint_ids:
        print(f"  - {cid}")

    # Get the latest checkpoint
    latest: WorkflowCheckpoint | None = await checkpoint_storage.get_latest(
        workflow_name=workflow.name,
    )

    if latest is None:
        print("No checkpoint found to resume from.")
        return

    print(f"\nLatest checkpoint: {latest.checkpoint_id}")
    print(f"  iteration_count: {latest.iteration_count}")
    print(f"  timestamp: {latest.timestamp}")

    # --- Second run: resume from the latest checkpoint ---
    print("\n=== Resuming from Checkpoint ===\n")
    workflow2 = workflow_builder.build()

    output2 = None
    async for event in workflow2.run(checkpoint_id=latest.checkpoint_id, stream=True):
        if event.type == "output":
            output2 = event.data

    if output2:
        print(f"Resumed workflow produced: {output2}")
    else:
        print("Resumed workflow completed (no remaining work — already finished).")


if __name__ == "__main__":
    asyncio.run(main())
