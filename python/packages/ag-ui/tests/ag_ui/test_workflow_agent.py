# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentFrameworkWorkflow wrapper behavior."""

from __future__ import annotations

from typing import Any, cast

import pytest
from agent_framework import (
    InMemoryCheckpointStorage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
)
from agent_framework._workflows._executor import Executor

from agent_framework_ag_ui import AgentFrameworkWorkflow


async def _run(
    agent: AgentFrameworkWorkflow,
    payload: dict[str, Any],
    **run_kwargs: Any,
) -> list[Any]:
    return [event async for event in agent.run(payload, **run_kwargs)]


async def test_workflow_wrapper_rejects_workflow_and_factory_at_once() -> None:
    """Workflow wrapper should reject ambiguous workflow source configuration."""

    @executor(id="start")
    async def start(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.yield_output("ok")  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]

    workflow = WorkflowBuilder(start_executor=start).build()
    with pytest.raises(ValueError, match="workflow_factory"):
        AgentFrameworkWorkflow(workflow=workflow, workflow_factory=lambda _thread_id: workflow)


async def test_workflow_wrapper_factory_is_thread_scoped() -> None:
    """Thread-scoped workflow factories should isolate workflow instances by thread id."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.request_info({"message": "Choose an option", "options": ["a", "b"]}, dict, request_id="choice")

    factory_calls: dict[str, int] = {}

    def workflow_factory(thread_id: str) -> Workflow:
        factory_calls[thread_id] = factory_calls.get(thread_id, 0) + 1
        return WorkflowBuilder(start_executor=requester).build()

    agent = AgentFrameworkWorkflow(workflow_factory=workflow_factory)

    first_events = await _run(
        agent,
        {
            "thread_id": "thread-a",
            "messages": [{"role": "user", "content": "start"}],
        },
    )
    first_finished = [event for event in first_events if event.type == "RUN_FINISHED"][0].model_dump()
    first_interrupt = first_finished.get("interrupt")
    assert isinstance(first_interrupt, list)
    assert first_interrupt[0]["id"] == "choice"
    assert factory_calls["thread-a"] == 1

    second_events = await _run(
        agent,
        {
            "thread_id": "thread-a",
            "messages": [],
            "resume": {"interrupts": [{"id": "choice", "value": {"selection": "a"}}]},
        },
    )
    second_types = [event.type for event in second_events]
    assert "RUN_ERROR" not in second_types
    second_finished = [event for event in second_events if event.type == "RUN_FINISHED"][0].model_dump()
    assert "interrupt" not in second_finished
    assert factory_calls["thread-a"] == 1

    third_events = await _run(
        agent,
        {
            "thread_id": "thread-b",
            "messages": [{"role": "user", "content": "start"}],
        },
    )
    third_finished = [event for event in third_events if event.type == "RUN_FINISHED"][0].model_dump()
    third_interrupt = third_finished.get("interrupt")
    assert isinstance(third_interrupt, list)
    assert third_interrupt[0]["id"] == "choice"
    assert factory_calls["thread-b"] == 1

    agent.clear_thread_workflow("thread-a")
    await _run(
        agent,
        {
            "thread_id": "thread-a",
            "messages": [{"role": "user", "content": "restart"}],
        },
    )
    assert factory_calls["thread-a"] == 2


async def test_workflow_wrapper_without_workflow_raises_not_implemented() -> None:
    """Without workflow/workflow_factory, run should raise NotImplementedError."""
    agent = AgentFrameworkWorkflow()

    with pytest.raises(NotImplementedError, match="No workflow is attached"):
        _ = [event async for event in agent.run({"messages": [{"role": "user", "content": "start"}]})]


async def test_workflow_wrapper_factory_return_type_is_validated() -> None:
    """Factory outputs must be Workflow instances."""
    agent = AgentFrameworkWorkflow(workflow_factory=lambda _thread_id: cast(Any, object()))

    with pytest.raises(TypeError, match="workflow_factory must return a Workflow instance"):
        _ = [event async for event in agent.run({"thread_id": "thread-a", "messages": []})]


# region checkpointing


class _StartExecutor(Executor):
    @handler
    async def run(self, message: Any, ctx: WorkflowContext[str]) -> None:
        del message
        await ctx.send_message("hello", target_id="middle")


class _MiddleExecutor(Executor):
    @handler
    async def process(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"{message}-processed", target_id="finish")


class _FinishExecutor(Executor):
    @handler
    async def finish(self, message: str, ctx: WorkflowContext[Any, str]) -> None:
        await ctx.yield_output(f"{message}-done")


def _build_multi_superstep_workflow(storage: InMemoryCheckpointStorage | None = None) -> Workflow:
    """Build a start -> middle -> finish workflow that creates a checkpoint per superstep."""
    start = _StartExecutor(id="start")
    middle = _MiddleExecutor(id="middle")
    finish = _FinishExecutor(id="finish")
    builder = WorkflowBuilder(max_iterations=10, start_executor=start)
    if storage is not None:
        builder = WorkflowBuilder(max_iterations=10, start_executor=start, checkpoint_storage=storage)
    return builder.add_edge(start, middle).add_edge(middle, finish).build()


async def test_workflow_run_creates_checkpoints_via_storage_kwarg() -> None:
    """Passing checkpoint_storage to run() should create workflow checkpoints (parity with core)."""
    storage = InMemoryCheckpointStorage()
    workflow = _build_multi_superstep_workflow()
    agent = AgentFrameworkWorkflow(workflow=workflow)

    events = await _run(
        agent,
        {"thread_id": "thread-cp", "messages": [{"role": "user", "content": "start"}]},
        checkpoint_storage=storage,
    )

    event_types = [event.type for event in events]
    assert "RUN_STARTED" in event_types
    assert "RUN_FINISHED" in event_types
    assert "RUN_ERROR" not in event_types

    checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
    # One checkpoint per superstep boundary: at least the initial superstep plus follow-ups.
    assert len(checkpoints) >= 2


async def test_workflow_run_resumes_from_checkpoint_id() -> None:
    """run(checkpoint_id=...) should restore persisted state and finish the workflow."""
    storage = InMemoryCheckpointStorage()
    workflow = _build_multi_superstep_workflow(storage)
    agent = AgentFrameworkWorkflow(workflow=workflow)

    # First run: execute to completion while checkpoints are written.
    first_events = await _run(
        agent,
        {"thread_id": "thread-cp", "messages": [{"role": "user", "content": "start"}]},
    )
    assert "RUN_ERROR" not in [event.type for event in first_events]

    checkpoints = sorted(
        await storage.list_checkpoints(workflow_name=workflow.name),
        key=lambda checkpoint: checkpoint.timestamp,
    )
    assert checkpoints, "expected the run to create at least one checkpoint"
    # Resume from the earliest checkpoint so middle -> finish replays and re-produces output.
    resume_checkpoint_id = checkpoints[0].checkpoint_id

    # Resume on the same thread (same underlying workflow instance) from the checkpoint.
    resumed_events = await _run(
        agent,
        {"thread_id": "thread-cp", "messages": []},
        checkpoint_id=resume_checkpoint_id,
        checkpoint_storage=storage,
    )

    resumed_types = [event.type for event in resumed_events]
    assert "RUN_STARTED" in resumed_types
    assert "RUN_FINISHED" in resumed_types
    assert "RUN_ERROR" not in resumed_types

    # The resumed run should reproduce the final assistant output ("hello-processed-done").
    resumed_text = "".join(
        getattr(event, "delta", "") for event in resumed_events if event.type == "TEXT_MESSAGE_CONTENT"
    )
    assert "done" in resumed_text


async def test_workflow_run_reads_checkpoint_params_from_input_data() -> None:
    """Checkpoint params smuggled through input_data should be honored (endpoint call convention)."""
    storage = InMemoryCheckpointStorage()
    workflow = _build_multi_superstep_workflow()
    agent = AgentFrameworkWorkflow(workflow=workflow)

    events = await _run(
        agent,
        {
            "thread_id": "thread-cp-input",
            "messages": [{"role": "user", "content": "start"}],
            "__ag_ui_checkpoint_storage": storage,
        },
    )

    assert "RUN_ERROR" not in [event.type for event in events]
    checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
    assert len(checkpoints) >= 1


async def test_workflow_run_without_checkpointing_is_unchanged() -> None:
    """Existing run(input_data) calls keep working unchanged when no checkpoint args are given."""
    workflow = _build_multi_superstep_workflow()
    agent = AgentFrameworkWorkflow(workflow=workflow)

    events = await _run(agent, {"thread_id": "thread-plain", "messages": [{"role": "user", "content": "start"}]})

    event_types = [event.type for event in events]
    assert "RUN_STARTED" in event_types
    assert "RUN_FINISHED" in event_types
    assert "RUN_ERROR" not in event_types
