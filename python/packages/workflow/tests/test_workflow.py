# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass

import pytest
from agent_framework.workflow import (
    Executor,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowEvent,
    handler,
)


@dataclass
class MockMessage:
    """A mock message for testing purposes."""

    data: int


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    def __init__(self, id: str, limit: int = 10):
        """Initialize the mock executor with a limit."""
        super().__init__(id=id)
        self.limit = limit

    @handler(output_types=[MockMessage])
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext) -> None:
        if message.data < self.limit:
            await ctx.send_message(MockMessage(data=message.data + 1))
        else:
            await ctx.add_event(WorkflowCompletedEvent(data=message.data))


class MockAggregator(Executor):
    """A mock executor that aggregates results from multiple executors."""

    @handler
    async def mock_handler(self, messages: list[MockMessage], ctx: WorkflowContext) -> None:
        # This mock simply returns the data incremented by 1
        await ctx.add_event(WorkflowCompletedEvent(data=sum(msg.data for msg in messages)))


@dataclass
class ApprovalMessage:
    """A mock message for approval requests."""

    approved: bool


class MockExecutorRequestApproval(Executor):
    """A mock executor that simulates a request for approval."""

    @handler(output_types=[RequestInfoMessage])
    async def mock_handler_a(self, message: MockMessage, ctx: WorkflowContext) -> None:
        """A mock handler that requests approval."""
        await ctx.set_shared_state(self.id, message.data)
        await ctx.send_message(RequestInfoMessage())

    @handler(output_types=[MockMessage])
    async def mock_handler_b(self, message: ApprovalMessage, ctx: WorkflowContext) -> None:
        """A mock handler that processes the approval response."""
        data = await ctx.get_shared_state(self.id)
        if message.approved:
            await ctx.add_event(WorkflowCompletedEvent(data=data))
        else:
            await ctx.send_message(MockMessage(data=data))


async def test_workflow_run_streaming():
    """Test the workflow run stream."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .build()
    )

    result: int | None = None
    async for event in workflow.run_streaming(MockMessage(data=0)):
        assert isinstance(event, WorkflowEvent)
        if isinstance(event, WorkflowCompletedEvent):
            result = event.data

    assert result is not None and result == 10


async def test_workflow_run_stream_not_completed():
    """Test the workflow run stream."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .set_max_iterations(5)
        .build()
    )

    with pytest.raises(RuntimeError):
        async for _ in workflow.run_streaming(MockMessage(data=0)):
            pass


async def test_workflow_run():
    """Test the workflow run."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .build()
    )

    events = await workflow.run(MockMessage(data=0))
    completed_event = events.get_completed_event()
    assert isinstance(completed_event, WorkflowCompletedEvent)
    assert completed_event.data == 10


async def test_workflow_run_not_completed():
    """Test the workflow run."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .set_max_iterations(5)
        .build()
    )

    with pytest.raises(RuntimeError):
        await workflow.run(MockMessage(data=0))


async def test_workflow_send_responses_streaming():
    """Test the workflow run with approval."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutorRequestApproval(id="executor_b")
    request_info_executor = RequestInfoExecutor()

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .add_edge(executor_b, request_info_executor)
        .add_edge(request_info_executor, executor_b)
        .build()
    )

    request_info_event: RequestInfoEvent | None = None
    async for event in workflow.run_streaming(MockMessage(data=0)):
        if isinstance(event, RequestInfoEvent):
            request_info_event = event

    assert request_info_event is not None
    result: int | None = None
    async for event in workflow.send_responses_streaming({
        request_info_event.request_id: ApprovalMessage(approved=True)
    }):
        if isinstance(event, WorkflowCompletedEvent):
            result = event.data

    assert result is not None and result == 1  # The data should be incremented by 1 from the initial message


async def test_workflow_send_responses():
    """Test the workflow run with approval."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutorRequestApproval(id="executor_b")
    request_info_executor = RequestInfoExecutor()

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .add_edge(executor_b, request_info_executor)
        .add_edge(request_info_executor, executor_b)
        .build()
    )

    events = await workflow.run(MockMessage(data=0))
    request_info_events = events.get_request_info_events()

    assert len(request_info_events) == 1

    result = await workflow.send_responses({request_info_events[0].request_id: ApprovalMessage(approved=True)})

    completed_event = result.get_completed_event()
    assert isinstance(completed_event, WorkflowCompletedEvent)
    assert completed_event.data == 1  # The data should be incremented by 1 from the initial message


async def test_fan_out():
    """Test a fan-out workflow."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b", limit=1)
    executor_c = MockExecutor(id="executor_c", limit=2)  # This executor will not complete the workflow

    workflow = (
        WorkflowBuilder().set_start_executor(executor_a).add_fan_out_edges(executor_a, [executor_b, executor_c]).build()
    )

    events = await workflow.run(MockMessage(data=0))

    # Each executor will emit two events: ExecutorInvokeEvent and ExecutorCompletedEvent
    # executor_b will also emit a WorkflowCompletedEvent
    assert len(events) == 7

    completed_event = events.get_completed_event()
    assert completed_event is not None and completed_event.data == 1


async def test_fan_out_multiple_completed_events():
    """Test a fan-out workflow with multiple completed events."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b", limit=1)
    executor_c = MockExecutor(id="executor_c", limit=1)

    workflow = (
        WorkflowBuilder().set_start_executor(executor_a).add_fan_out_edges(executor_a, [executor_b, executor_c]).build()
    )

    events = await workflow.run(MockMessage(data=0))

    # Each executor will emit two events: ExecutorInvokeEvent and ExecutorCompletedEvent
    # executor_a and executor_b will also emit a WorkflowCompletedEvent
    assert len(events) == 8

    with pytest.raises(ValueError):
        events.get_completed_event()


async def test_fan_in():
    """Test a fan-in workflow."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")
    executor_c = MockExecutor(id="executor_c")
    aggregator = MockAggregator(id="aggregator")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_fan_out_edges(executor_a, [executor_b, executor_c])
        .add_fan_in_edges([executor_b, executor_c], aggregator)
        .build()
    )

    events = await workflow.run(MockMessage(data=0))

    # Each executor will emit two events: ExecutorInvokeEvent and ExecutorCompletedEvent
    # aggregator will also emit a WorkflowCompletedEvent
    assert len(events) == 9

    completed_event = events.get_completed_event()
    assert completed_event is not None and completed_event.data == 4
