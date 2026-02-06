# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

import pytest

from agent_framework import (
    AgentExecutorResponse,
    AgentResponse,
    Executor,
    WorkflowContext,
    WorkflowConvergenceException,
    WorkflowEvent,
    WorkflowRunnerException,
    WorkflowRunState,
    handler,
)
from agent_framework._workflows._edge import SingleEdgeGroup
from agent_framework._workflows._runner import Runner
from agent_framework._workflows._runner_context import (
    InProcRunnerContext,
    Message,
    RunnerContext,
)
from agent_framework._workflows._state import State


@dataclass
class MockMessage:
    """A mock message for testing purposes."""

    data: int


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    @handler
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext[MockMessage, int]) -> None:
        if message.data < 10:
            await ctx.send_message(MockMessage(data=message.data + 1))
        else:
            await ctx.yield_output(message.data)
            pass


def test_create_runner():
    """Test creating a runner with edges and state."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edge_groups = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {
        executor_a.id: executor_a,
        executor_b.id: executor_b,
    }

    runner = Runner(edge_groups, executors, state=State(), ctx=InProcRunnerContext())

    assert runner.context is not None and isinstance(runner.context, RunnerContext)


async def test_runner_run_until_convergence():
    """Test running the runner with a simple workflow."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {
        executor_a.id: executor_a,
        executor_b.id: executor_b,
    }
    state = State()
    ctx = InProcRunnerContext()

    runner = Runner(edges, executors, state, ctx)

    result: int | None = None
    await executor_a.execute(
        MockMessage(data=0),
        ["START"],  # source_executor_ids
        state,  # state
        ctx,  # runner_context
    )
    async for event in runner.run_until_convergence():
        assert isinstance(event, WorkflowEvent)
        if event.type == "output":
            result = event.data

    assert result is not None and result == 10

    # iteration count shouldn't be reset after convergence
    assert runner._iteration == 10  # type: ignore


async def test_runner_run_until_convergence_not_completed():
    """Test running the runner with a simple workflow."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {
        executor_a.id: executor_a,
        executor_b.id: executor_b,
    }
    state = State()
    ctx = InProcRunnerContext()

    runner = Runner(edges, executors, state, ctx, max_iterations=5)

    await executor_a.execute(
        MockMessage(data=0),
        ["START"],  # source_executor_ids
        state,  # state
        ctx,  # runner_context
    )
    with pytest.raises(
        WorkflowConvergenceException,
        match="Runner did not converge after 5 iterations.",
    ):
        async for event in runner.run_until_convergence():
            assert event.type != "status" or event.state != WorkflowRunState.IDLE


async def test_runner_already_running():
    """Test that running the runner while it is already running raises an error."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {
        executor_a.id: executor_a,
        executor_b.id: executor_b,
    }
    state = State()
    ctx = InProcRunnerContext()

    runner = Runner(edges, executors, state, ctx)

    await executor_a.execute(
        MockMessage(data=0),
        ["START"],  # source_executor_ids
        state,  # state
        ctx,  # runner_context
    )

    with pytest.raises(WorkflowRunnerException, match="Runner is already running."):

        async def _run():
            async for _ in runner.run_until_convergence():
                pass

        await asyncio.gather(_run(), _run())


async def test_runner_emits_runner_completion_for_agent_response_without_targets():
    ctx = InProcRunnerContext()
    runner = Runner([], {}, State(), ctx)

    await ctx.send_message(
        Message(
            data=AgentExecutorResponse("agent", AgentResponse()),
            source_id="agent",
        )
    )

    events: list[WorkflowEvent] = [event async for event in runner.run_until_convergence()]
    # The runner should complete without errors when handling AgentExecutorResponse without targets
    # No specific events are expected since there are no executors to process the message
    assert isinstance(events, list)  # Just verify the runner completed without errors


class SlowExecutor(Executor):
    """An executor that takes time to process, used for cancellation testing."""

    def __init__(self, id: str, work_duration: float = 0.5):
        super().__init__(id=id)
        self.started_count = 0
        self.completed_count = 0
        self.work_duration = work_duration

    @handler
    async def handle(self, message: MockMessage, ctx: WorkflowContext[MockMessage, int]) -> None:
        self.started_count += 1
        await asyncio.sleep(self.work_duration)
        self.completed_count += 1
        if message.data < 2:
            await ctx.send_message(MockMessage(data=message.data + 1))
        else:
            await ctx.yield_output(message.data)


async def test_runner_cancellation_stops_active_executor():
    """Test that cancelling a workflow properly cancels the active executor."""
    executor_a = SlowExecutor(id="executor_a", work_duration=0.3)
    executor_b = SlowExecutor(id="executor_b", work_duration=1.0)

    edges = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {
        executor_a.id: executor_a,
        executor_b.id: executor_b,
    }
    shared_state = State()
    ctx = InProcRunnerContext()

    runner = Runner(edges, executors, shared_state, ctx)

    await executor_a.execute(
        MockMessage(data=0),
        ["START"],
        shared_state,
        ctx,
    )

    async def run_workflow():
        async for _ in runner.run_until_convergence():
            pass

    task = asyncio.create_task(run_workflow())

    # Wait for executor_a to complete (0.3s) and executor_b to start but not finish
    await asyncio.sleep(0.5)

    # Cancel while executor_b is mid-execution (it takes 1.0s)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Give time for any leaked tasks to complete (if cancellation didn't work)
    await asyncio.sleep(1.5)

    # executor_a should have completed once, executor_b should have started but not completed
    assert executor_a.completed_count == 1
    assert executor_b.started_count == 1
    assert executor_b.completed_count == 0  # Should NOT have completed due to cancellation
