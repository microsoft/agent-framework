# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

import pytest
from agent_framework.workflow import Executor, WorkflowCompletedEvent, WorkflowContext, WorkflowEvent, handler

from agent_framework_workflow._edge import SingleEdgeGroup
from agent_framework_workflow._runner import Runner
from agent_framework_workflow._runner_context import InProcRunnerContext, RunnerContext
from agent_framework_workflow._shared_state import SharedState


@dataclass
class MockMessage:
    """A mock message for testing purposes."""

    data: int


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    @handler
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext[MockMessage]) -> None:
        if message.data < 10:
            await ctx.send_message(MockMessage(data=message.data + 1))
        else:
            await ctx.add_event(WorkflowCompletedEvent(data=message.data))


def test_create_runner():
    """Test creating a runner with edges and shared state."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edge_groups = [
        SingleEdgeGroup(executor_a, executor_b),
        SingleEdgeGroup(executor_b, executor_a),
    ]

    runner = Runner(edge_groups, shared_state=SharedState(), ctx=InProcRunnerContext())

    assert runner.context is not None and isinstance(runner.context, RunnerContext)


async def test_runner_run_until_convergence():
    """Test running the runner with a simple workflow."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        SingleEdgeGroup(executor_a, executor_b),
        SingleEdgeGroup(executor_b, executor_a),
    ]

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    runner = Runner(edges, shared_state, ctx)

    result: int | None = None
    await executor_a.execute(
        MockMessage(data=0),
        WorkflowContext(
            executor_id=executor_a.id,
            source_executor_ids=["START"],
            shared_state=shared_state,
            runner_context=ctx,
        ),
    )
    async for event in runner.run_until_convergence():
        assert isinstance(event, WorkflowEvent)
        if isinstance(event, WorkflowCompletedEvent):
            result = event.data

    assert result is not None and result == 10


async def test_runner_run_until_convergence_not_completed():
    """Test running the runner with a simple workflow."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        SingleEdgeGroup(executor_a, executor_b),
        SingleEdgeGroup(executor_b, executor_a),
    ]

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    runner = Runner(edges, shared_state, ctx, max_iterations=5)

    await executor_a.execute(
        MockMessage(data=0),
        WorkflowContext(
            executor_id=executor_a.id,
            source_executor_ids=["START"],
            shared_state=shared_state,
            runner_context=ctx,
        ),
    )
    with pytest.raises(RuntimeError, match="Runner did not converge after 5 iterations."):
        async for event in runner.run_until_convergence():
            assert not isinstance(event, WorkflowCompletedEvent)


async def test_runner_already_running():
    """Test that running the runner while it is already running raises an error."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        SingleEdgeGroup(executor_a, executor_b),
        SingleEdgeGroup(executor_b, executor_a),
    ]

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    runner = Runner(edges, shared_state, ctx)

    await executor_a.execute(
        MockMessage(data=0),
        WorkflowContext(
            executor_id=executor_a.id,
            source_executor_ids=["START"],
            shared_state=shared_state,
            runner_context=ctx,
        ),
    )

    with pytest.raises(RuntimeError, match="Runner is already running."):

        async def _run():
            async for _ in runner.run_until_convergence():
                pass

        await asyncio.gather(_run(), _run())
