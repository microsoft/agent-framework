# Copyright (c) Microsoft. All rights reserved.

import pytest
from typing_extensions import Never

from agent_framework import WorkflowBuilder, WorkflowContext, WorkflowRunState, WorkflowStatusEvent, handler
from agent_framework._workflow._checkpoint import InMemoryCheckpointStorage
from agent_framework._workflow._executor import Executor


class StartExecutor(Executor):
    @handler
    async def run(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(message, target_id="finish")


class FinishExecutor(Executor):
    @handler
    async def finish(self, message: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(message)


def build_workflow(storage: InMemoryCheckpointStorage, finish_id: str = "finish"):
    start = StartExecutor(id="start")
    finish = FinishExecutor(id=finish_id)

    builder = WorkflowBuilder(max_iterations=3).set_start_executor(start).add_edge(start, finish)
    builder = builder.with_checkpointing(checkpoint_storage=storage)
    return builder.build()


async def test_resume_fails_when_graph_mismatch() -> None:
    storage = InMemoryCheckpointStorage()
    workflow = build_workflow(storage, finish_id="finish")

    # Run once to create checkpoints
    _ = [event async for event in workflow.run_stream("hello")]  # noqa: F841

    checkpoints = await storage.list_checkpoints()
    assert checkpoints, "expected at least one checkpoint to be created"
    target_checkpoint = checkpoints[-1]

    # Build a structurally different workflow (different finish executor id)
    mismatched_workflow = build_workflow(storage, finish_id="finish_alt")

    with pytest.raises(ValueError, match="Workflow graph has changed"):
        _ = [
            event
            async for event in mismatched_workflow.run_stream_from_checkpoint(
                target_checkpoint.checkpoint_id,
                checkpoint_storage=storage,
            )
        ]


async def test_resume_succeeds_when_graph_matches() -> None:
    storage = InMemoryCheckpointStorage()
    workflow = build_workflow(storage, finish_id="finish")
    _ = [event async for event in workflow.run_stream("hello")]  # noqa: F841

    checkpoints = sorted(await storage.list_checkpoints(), key=lambda c: c.timestamp)
    target_checkpoint = checkpoints[0]

    resumed_workflow = build_workflow(storage, finish_id="finish")

    events = [
        event
        async for event in resumed_workflow.run_stream_from_checkpoint(
            target_checkpoint.checkpoint_id,
            checkpoint_storage=storage,
        )
    ]

    assert any(isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE for event in events)
