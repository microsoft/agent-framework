# Copyright (c) Microsoft. All rights reserved.

import pytest
from typing_extensions import Never

from agent_framework import (
    WorkflowBuilder,
    WorkflowCheckpointException,
    WorkflowContext,
    WorkflowExecutor,
    WorkflowRunState,
    handler,
)
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage
from agent_framework._workflows._executor import Executor


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

    builder = WorkflowBuilder(max_iterations=3, start_executor=start, checkpoint_storage=storage).add_edge(
        start, finish
    )
    return builder.build()


async def test_resume_fails_when_graph_mismatch() -> None:
    storage = InMemoryCheckpointStorage()
    workflow = build_workflow(storage, finish_id="finish")

    # Run once to create checkpoints
    _ = [event async for event in workflow.run("hello", stream=True)]  # noqa: F841

    checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
    assert checkpoints, "expected at least one checkpoint to be created"
    target_checkpoint = checkpoints[-1]

    # Build a structurally different workflow (different finish executor id)
    mismatched_workflow = build_workflow(storage, finish_id="finish_alt")

    with pytest.raises(WorkflowCheckpointException, match="Workflow graph has changed"):
        _ = [
            event
            async for event in mismatched_workflow.run(
                checkpoint_id=target_checkpoint.checkpoint_id,
                checkpoint_storage=storage,
                stream=True,
            )
        ]


async def test_resume_succeeds_when_graph_matches() -> None:
    storage = InMemoryCheckpointStorage()
    workflow = build_workflow(storage, finish_id="finish")
    _ = [event async for event in workflow.run("hello", stream=True)]  # noqa: F841

    checkpoints = sorted(await storage.list_checkpoints(workflow_name=workflow.name), key=lambda c: c.timestamp)
    target_checkpoint = checkpoints[0]

    resumed_workflow = build_workflow(storage, finish_id="finish")

    events = [
        event
        async for event in resumed_workflow.run(
            checkpoint_id=target_checkpoint.checkpoint_id,
            checkpoint_storage=storage,
            stream=True,
        )
    ]

    assert any(event.type == "status" and event.state == WorkflowRunState.IDLE for event in events)


# -- Sub-workflow checkpoint validation tests --


class SubStartExecutor(Executor):
    @handler
    async def run(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(message)


class SubFinishExecutor(Executor):
    @handler
    async def finish(self, message: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(message)


def build_sub_workflow(sub_finish_id: str = "sub_finish"):
    sub_start = SubStartExecutor(id="sub_start")
    sub_finish = SubFinishExecutor(id=sub_finish_id)
    return WorkflowBuilder(start_executor=sub_start).add_edge(sub_start, sub_finish).build()


def build_parent_workflow(storage: InMemoryCheckpointStorage, sub_finish_id: str = "sub_finish"):
    sub_workflow = build_sub_workflow(sub_finish_id=sub_finish_id)
    sub_executor = WorkflowExecutor(sub_workflow, id="sub_wf", allow_direct_output=True)

    start = StartExecutor(id="start")
    finish = FinishExecutor(id="finish")

    builder = (
        WorkflowBuilder(max_iterations=3, start_executor=start, checkpoint_storage=storage)
        .add_edge(start, sub_executor)
        .add_edge(sub_executor, finish)
    )
    return builder.build()


async def test_resume_succeeds_when_sub_workflow_matches() -> None:
    storage = InMemoryCheckpointStorage()
    workflow = build_parent_workflow(storage, sub_finish_id="sub_finish")

    _ = [event async for event in workflow.run("hello", stream=True)]

    checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
    assert checkpoints, "expected at least one checkpoint to be created"
    target_checkpoint = checkpoints[-1]

    resumed_workflow = build_parent_workflow(storage, sub_finish_id="sub_finish")

    events = [
        event
        async for event in resumed_workflow.run(
            checkpoint_id=target_checkpoint.checkpoint_id,
            checkpoint_storage=storage,
            stream=True,
        )
    ]

    assert any(event.type == "status" and event.state == WorkflowRunState.IDLE for event in events)


async def test_resume_fails_when_sub_workflow_changes() -> None:
    storage = InMemoryCheckpointStorage()
    workflow = build_parent_workflow(storage, sub_finish_id="sub_finish")

    _ = [event async for event in workflow.run("hello", stream=True)]

    checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
    assert checkpoints, "expected at least one checkpoint to be created"
    target_checkpoint = checkpoints[-1]

    # Build parent with a structurally different sub-workflow (different executor id inside)
    mismatched_workflow = build_parent_workflow(storage, sub_finish_id="sub_finish_alt")

    with pytest.raises(WorkflowCheckpointException, match="Workflow graph has changed"):
        _ = [
            event
            async for event in mismatched_workflow.run(
                checkpoint_id=target_checkpoint.checkpoint_id,
                checkpoint_storage=storage,
                stream=True,
            )
        ]
