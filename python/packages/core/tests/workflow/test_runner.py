# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

import pytest

from agent_framework import (
    AgentExecutorResponse,
    AgentRunResponse,
    Executor,
    WorkflowContext,
    WorkflowEvent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)
from agent_framework._workflow._edge import SingleEdgeGroup
from agent_framework._workflow._runner import Runner
from agent_framework._workflow._runner_context import InProcRunnerContext, Message, RunnerContext
from agent_framework._workflow._shared_state import SharedState


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
    """Test creating a runner with edges and shared state."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edge_groups = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {executor_a.id: executor_a, executor_b.id: executor_b}

    runner = Runner(edge_groups, executors, shared_state=SharedState(), ctx=InProcRunnerContext())

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

    executors: dict[str, Executor] = {executor_a.id: executor_a, executor_b.id: executor_b}
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    runner = Runner(edges, executors, shared_state, ctx)

    result: int | None = None
    await executor_a.execute(
        MockMessage(data=0),
        ["START"],  # source_executor_ids
        shared_state,  # shared_state
        ctx,  # runner_context
    )
    async for event in runner.run_until_convergence():
        assert isinstance(event, WorkflowEvent)
        if isinstance(event, WorkflowOutputEvent):
            result = event.data

    assert result is not None and result == 10


async def test_runner_run_until_convergence_not_completed():
    """Test running the runner with a simple workflow."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {executor_a.id: executor_a, executor_b.id: executor_b}
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    runner = Runner(edges, executors, shared_state, ctx, max_iterations=5)

    await executor_a.execute(
        MockMessage(data=0),
        ["START"],  # source_executor_ids
        shared_state,  # shared_state
        ctx,  # runner_context
    )
    with pytest.raises(RuntimeError, match="Runner did not converge after 5 iterations."):
        async for event in runner.run_until_convergence():
            assert not isinstance(event, WorkflowStatusEvent) or event.state != WorkflowRunState.IDLE


async def test_runner_already_running():
    """Test that running the runner while it is already running raises an error."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {executor_a.id: executor_a, executor_b.id: executor_b}
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    runner = Runner(edges, executors, shared_state, ctx)

    await executor_a.execute(
        MockMessage(data=0),
        ["START"],  # source_executor_ids
        shared_state,  # shared_state
        ctx,  # runner_context
    )

    with pytest.raises(RuntimeError, match="Runner is already running."):

        async def _run():
            async for _ in runner.run_until_convergence():
                pass

        await asyncio.gather(_run(), _run())


async def test_runner_emits_runner_completion_for_agent_response_without_targets():
    ctx = InProcRunnerContext()
    runner = Runner([], {}, SharedState(), ctx)

    await ctx.send_message(
        Message(
            data=AgentExecutorResponse("agent", AgentRunResponse()),
            source_id="agent",
        )
    )

    events: list[WorkflowEvent] = [event async for event in runner.run_until_convergence()]
    # The runner should complete without errors when handling AgentExecutorResponse without targets
    # No specific events are expected since there are no executors to process the message
    assert isinstance(events, list)  # Just verify the runner completed without errors
