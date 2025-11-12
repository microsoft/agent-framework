# Copyright (c) Microsoft. All rights reserved.


"""
Sample: Checkpointing and Resuming a Workflow

Purpose:
This sample shows how to enable checkpointing for a long-running workflow
that may result in intermittent failures. If a failure occurs, the workflow
can be resumed from the last successful checkpoint rather than starting
over from the beginning.

What you learn:
- How to configure different checkpointing storages:
    - FilesystemCheckpointStorage for local filesystem storage of checkpoints
    - InMemoryCheckpointStorage for ephemeral in-memory checkpointing (useful for testing)
- How to resume a workflow from a checkpoint
- How to inspect checkpoints programmatically

Pipeline:
This sample shows a workflow that will run the samples in one of the directories under `samples/getting_started/`.
Note: For demonstration purposes, the workflow will not actually run all the samples, but will simulate
running them by printing their names.
1) A start executor that will read the list of sample files to run.
2) A distributor executor that will distribute the sample files to multiple worker executors.
3) Multiple worker executors that will simulate running the sample files. These executors will
    randomly fail to demonstrate checkpointing and resuming.
4) A collector executor that will collect the results from the worker executors.

Prerequisites:
- Basic understanding of workflow concepts, including executors, edges, events, etc.
"""

import asyncio
import random
from typing import Any, Never, override

from agent_framework import (
    Executor,
    InMemoryCheckpointStorage,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
)
from anyio import Path


class StartExecutor(Executor):
    """Executor that starts the workflow by providing a list of sample files to run."""

    @handler
    async def start(self, directory: str, ctx: WorkflowContext[list[str]]) -> None:
        """Start the workflow by listing sample files in the given directory."""
        # Validate the input directory
        directory_path = Path(directory)
        if not await directory_path.is_dir():
            raise ValueError(f"Directory '{directory}' does not exist or is not a directory.")
        # Validate that the directory is a subdirectory of samples/getting_started
        expected_parent = Path(__file__).parent.parent.parent
        if expected_parent not in directory_path.parents:
            raise ValueError(f"Directory '{directory}' is not a subdirectory of '{expected_parent}'.")

        sample_files = await self._find_all_sample_files(directory_path)
        print(f"StartExecutor: Found {len(sample_files)} sample files to run.")

        # Save the expected files in shared state for the collector to validate
        await ctx.set_shared_state("expected_files", sample_files)
        # Send the list of sample files to the next executor
        await ctx.send_message(sample_files)

    async def _find_all_sample_files(self, directory: Path) -> list[str]:
        """Recursively find all Python sample files in the given directory."""
        sample_files: list[str] = []
        async for file_path in directory.rglob("*.py"):
            sample_files.append(str(file_path))
        return sample_files


class Distributor(Executor):
    """Executor that distributes sample files to worker executors."""

    def __init__(self, id: str, worker_ids: list[str]):
        super().__init__(id=id)
        self._worker_ids = worker_ids

    @handler
    async def distribute(self, sample_files: list[str], ctx: WorkflowContext[list[str]]) -> None:
        """Distribute sample files to worker executors."""
        distribution_lists: list[list[str]] = [[] for _ in range(len(self._worker_ids))]
        for index, sample_file in enumerate(sample_files):
            distribution_lists[index % len(self._worker_ids)].append(sample_file)

        for worker_id, files in zip(self._worker_ids, distribution_lists, strict=True):
            print(f"Distributor: Distributing {len(files)} files to worker '{worker_id}'.")
            await ctx.send_message(files, target_id=worker_id)


class WorkerExecutor(Executor):
    """Executor that simulates running sample files."""

    def __init__(self, id: str):
        super().__init__(id=id)
        self._processed_files: list[str] = []

    @handler
    async def run_samples(self, sample_files: list[str], ctx: WorkflowContext[list[str]]) -> None:
        """Simulate running the sample files."""
        for sample_file in sample_files:
            if sample_file in self._processed_files:
                continue

            # Simulate some processing time
            await asyncio.sleep(0.5)
            # Simulate random failure
            if random.random() < 0.2:  # 20% chance to fail
                break

            self._processed_files.append(sample_file)

        print(f"WorkerExecutor '{self.id}': Processed {len(self._processed_files)} of {len(sample_files)} files.")
        await ctx.send_message(self._processed_files)

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Save the executor state for checkpointing."""
        return {"processed_files": self._processed_files}

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore the executor state from a checkpoint."""
        self._processed_files = state.get("processed_files", [])


class Collector(Executor):
    """Executor that collects results from worker executors."""

    def __init__(self, id: str):
        super().__init__(id=id)
        self._processed_files: list[str] = []

    @handler
    async def collect(self, worker_results: list[str], ctx: WorkflowContext[Never, str]) -> None:
        """Collect results from worker executors."""
        expected_files: list[str] = await ctx.get_shared_state("expected_files")

        for file in worker_results:
            if file not in expected_files:
                raise ValueError(f"Collector: Received unexpected file result '{file}'.")
            if file in self._processed_files:
                raise ValueError(f"Collector: Duplicate result for file '{file}'.")

        self._processed_files.extend(worker_results)

        if len(self._processed_files) == len(expected_files):
            print("Collector: All sample files have been processed.")
            await ctx.yield_output("All samples processed successfully.")

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Save the executor state for checkpointing."""
        return {"processed_files": self._processed_files}

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore the executor state from a checkpoint."""
        self._processed_files = state.get("processed_files", [])


async def main():
    # Create the executors
    start_executor = StartExecutor(id="start")
    workers = [WorkerExecutor(id=f"worker_{i}") for i in range(3)]
    distributor = Distributor(id="distributor", worker_ids=[w.id for w in workers])
    collector = Collector(id="collector")

    # Create the workflow builder with a start executor
    workflow_builder = WorkflowBuilder().set_start_executor(start_executor).add_edge(start_executor, distributor)
    # Connect the distributor to each worker and each worker to the collector
    for worker in workers:
        workflow_builder = workflow_builder.add_edge(distributor, worker)
        workflow_builder = workflow_builder.add_edge(worker, collector)
    # Add checkpointing with in-memory storage
    checkpoint_storage = InMemoryCheckpointStorage()
    workflow_builder = workflow_builder.with_checkpointing(checkpoint_storage=checkpoint_storage)

    # Build the workflow
    workflow = workflow_builder.build()

    directory_to_run = str(Path(__file__).parent.parent)  # samples/getting_started/workflows/

    event_stream = workflow.run_stream(message=directory_to_run)

    while True:
        async for event in event_stream:
            if isinstance(event, WorkflowOutputEvent):
                print(f"Workflow completed successfully with output: {event.data}")
                break

        print(
            "Workflow did not produce a final output, attempting to resume from the "
            "second checkpoint that is created right after the distributor runs."
        )

        # Attempt to restore from the last checkpoint
        all_checkpoints = await checkpoint_storage.list_checkpoints()
        if not all_checkpoints:
            raise RuntimeError("No checkpoints available to resume from.")

        # Checkpoints are ordered by creation time, so pick the second one
        latest_checkpoint = all_checkpoints[1]
        print(f"Resuming from checkpoint: {latest_checkpoint.checkpoint_id}")
        event_stream = workflow.run_stream(checkpoint_id=latest_checkpoint.checkpoint_id)


if __name__ == "__main__":
    asyncio.run(main())
