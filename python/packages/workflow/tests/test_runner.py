# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass

from agent_framework.workflow import Executor, WorkflowCompletedEvent, WorkflowContext, WorkflowEvent, message_handler

from agent_framework_workflow._edge import Edge
from agent_framework_workflow._runner import Runner
from agent_framework_workflow._runner_context import InProcRunnerContext, RunnerContext
from agent_framework_workflow._shared_state import SharedState


@dataclass
class MockMessage:
    """A mock message for testing purposes."""

    data: int


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    @message_handler(output_types=[MockMessage])
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext) -> None:
        """A mock handler that does nothing."""
        if message.data < 10:
            await ctx.send_message(MockMessage(data=message.data + 1))
        else:
            await ctx.add_event(WorkflowCompletedEvent(data=message.data))


def test_create_runner():
    """Test creating a runner with edges and shared state."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        Edge(source=executor_a, target=executor_b),
        Edge(source=executor_b, target=executor_a),
    ]

    runner = Runner(edges, shared_state=SharedState(), ctx=InProcRunnerContext())

    assert runner.context is not None and isinstance(runner.context, RunnerContext)


async def test_runner_run_until_convergence():
    """Test running the runner with a simple workflow."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        Edge(source=executor_a, target=executor_b),
        Edge(source=executor_b, target=executor_a),
    ]

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    runner = Runner(edges, shared_state, ctx)
    async for event in runner.run_until_convergence():
        assert isinstance(event, WorkflowEvent)
        if isinstance(event, WorkflowCompletedEvent):
            assert event.data == 10


async def test_runner_run_until_convergence_not_completed():
    """Test running the runner with a simple workflow."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    # Create a loop
    edges = [
        Edge(source=executor_a, target=executor_b),
        Edge(source=executor_b, target=executor_a),
    ]

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    runner = Runner(edges, shared_state, ctx, max_iterations=5)
    async for event in runner.run_until_convergence():
        assert not isinstance(event, WorkflowCompletedEvent)
