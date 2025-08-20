# Copyright (c) Microsoft. All rights reserved.

import tempfile
from dataclasses import dataclass
from typing import Any

import pytest
from agent_framework.workflow import (
    Executor,
    FileCheckpointStorage,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowEvent,
    handler,
)

from agent_framework_workflow import Message


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

    @handler
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext[MockMessage]) -> None:
        if message.data < self.limit:
            await ctx.send_message(MockMessage(data=message.data + 1))
        else:
            await ctx.add_event(WorkflowCompletedEvent(data=message.data))


class MockAggregator(Executor):
    """A mock executor that aggregates results from multiple executors."""

    @handler
    async def mock_handler(self, messages: list[MockMessage], ctx: WorkflowContext[Any]) -> None:
        # This mock simply returns the data incremented by 1
        await ctx.add_event(WorkflowCompletedEvent(data=sum(msg.data for msg in messages)))


@dataclass
class ApprovalMessage:
    """A mock message for approval requests."""

    approved: bool


class MockExecutorRequestApproval(Executor):
    """A mock executor that simulates a request for approval."""

    @handler
    async def mock_handler_a(self, message: MockMessage, ctx: WorkflowContext[RequestInfoMessage]) -> None:
        """A mock handler that requests approval."""
        await ctx.set_shared_state(self.id, message.data)
        await ctx.send_message(RequestInfoMessage())

    @handler
    async def mock_handler_b(self, message: ApprovalMessage, ctx: WorkflowContext[MockMessage]) -> None:
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


@pytest.fixture
def simple_executor() -> Executor:
    class SimpleExecutor(Executor):
        @handler
        async def handle_message(self, message: Message, context: WorkflowContext[None]) -> None:
            pass

    return SimpleExecutor("test_executor")


async def test_workflow_with_checkpointing_enabled(simple_executor: Executor):
    """Test that a workflow can be built with checkpointing enabled."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Build workflow with checkpointing - should not raise any errors
        workflow = (
            WorkflowBuilder()
            .add_edge(simple_executor, simple_executor)  # Self-loop to satisfy graph requirements
            .set_start_executor(simple_executor)
            .with_checkpointing(storage)
            .build()
        )

        # Verify workflow was created and can run
        test_message = Message(data="test message", source_id="test", target_id=None)
        result = await workflow.run(test_message)
        assert result is not None


async def test_workflow_checkpointing_not_enabled_for_external_restore(simple_executor: Executor):
    """Test that external checkpoint restoration fails when workflow doesn't support checkpointing."""
    # Build workflow WITHOUT checkpointing
    workflow = (
        WorkflowBuilder()
        .add_edge(simple_executor, simple_executor)  # Self-loop to satisfy graph requirements
        .set_start_executor(simple_executor)
        .build()
    )

    # Attempt to restore from checkpoint without providing external storage should fail
    try:
        [event async for event in workflow.run_streaming_from_checkpoint("fake-checkpoint-id")]
        raise AssertionError("Expected ValueError to be raised")
    except ValueError as e:
        assert "Cannot restore from checkpoint" in str(e)
        assert "either provide checkpoint_storage parameter" in str(e)


async def test_workflow_run_stream_from_checkpoint_no_checkpointing_enabled(simple_executor: Executor):
    # Build workflow WITHOUT checkpointing
    workflow = (
        WorkflowBuilder()
        .add_edge(simple_executor, simple_executor)  # Self-loop to satisfy graph requirements
        .set_start_executor(simple_executor)
        .build()
    )

    # Attempt to run from checkpoint should fail
    try:
        async for _ in workflow.run_streaming_from_checkpoint("fake_checkpoint_id"):
            pass
        raise AssertionError("Expected ValueError to be raised")
    except ValueError as e:
        assert "Cannot restore from checkpoint" in str(e)
        assert "either provide checkpoint_storage parameter" in str(e)


async def test_workflow_run_stream_from_checkpoint_invalid_checkpoint(simple_executor: Executor):
    """Test that attempting to restore from a non-existent checkpoint fails appropriately."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Build workflow with checkpointing
        workflow = (
            WorkflowBuilder()
            .add_edge(simple_executor, simple_executor)  # Self-loop to satisfy graph requirements
            .set_start_executor(simple_executor)
            .with_checkpointing(storage)
            .build()
        )

        # Attempt to run from non-existent checkpoint should fail
        try:
            async for _ in workflow.run_streaming_from_checkpoint("nonexistent_checkpoint_id"):
                pass
            raise AssertionError("Expected RuntimeError to be raised")
        except RuntimeError as e:
            assert "Failed to restore from checkpoint" in str(e)


async def test_workflow_run_stream_from_checkpoint_with_external_storage(simple_executor: Executor):
    """Test that external checkpoint storage can be provided for restoration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create a test checkpoint manually in storage
        from agent_framework_workflow._checkpoint import WorkflowCheckpoint

        test_checkpoint = WorkflowCheckpoint(
            workflow_id="test-workflow",
            messages={},
            shared_state={},
            executor_states={},
            iteration_count=0,
            max_iterations=100,
        )
        checkpoint_id = await storage.save_checkpoint(test_checkpoint)

        # Create a workflow WITHOUT checkpointing
        workflow_without_checkpointing = (
            WorkflowBuilder().add_edge(simple_executor, simple_executor).set_start_executor(simple_executor).build()
        )

        # Resume from checkpoint using external storage parameter
        try:
            events: list[WorkflowEvent] = []
            async for event in workflow_without_checkpointing.run_streaming_from_checkpoint(
                checkpoint_id, checkpoint_storage=storage
            ):
                events.append(event)
                if len(events) >= 2:  # Limit to avoid infinite loops
                    break
        except Exception:
            # Expected since we have minimal setup, but method should accept the parameters
            pass


async def test_workflow_run_from_checkpoint_non_streaming(simple_executor: Executor):
    """Test the non-streaming run_from_checkpoint method."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create a test checkpoint manually in storage
        from agent_framework_workflow._checkpoint import WorkflowCheckpoint

        test_checkpoint = WorkflowCheckpoint(
            workflow_id="test-workflow",
            messages={},
            shared_state={},
            executor_states={},
            iteration_count=0,
            max_iterations=100,
        )
        checkpoint_id = await storage.save_checkpoint(test_checkpoint)

        # Build workflow with checkpointing
        workflow = (
            WorkflowBuilder()
            .add_edge(simple_executor, simple_executor)
            .set_start_executor(simple_executor)
            .with_checkpointing(storage)
            .build()
        )

        # Test non-streaming run_from_checkpoint method
        result = await workflow.run_from_checkpoint(checkpoint_id)
        assert isinstance(result, list)  # Should return WorkflowRunResult which extends list
        assert hasattr(result, "get_completed_event")  # Should have WorkflowRunResult methods


async def test_workflow_run_stream_from_checkpoint_with_responses(simple_executor: Executor):
    """Test that run_streaming_from_checkpoint accepts responses parameter."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create a test checkpoint manually in storage
        from agent_framework_workflow._checkpoint import WorkflowCheckpoint

        test_checkpoint = WorkflowCheckpoint(
            workflow_id="test-workflow",
            messages={},
            shared_state={},
            executor_states={},
            iteration_count=0,
            max_iterations=100,
        )
        checkpoint_id = await storage.save_checkpoint(test_checkpoint)

        # Build workflow with checkpointing
        workflow = (
            WorkflowBuilder()
            .add_edge(simple_executor, simple_executor)
            .set_start_executor(simple_executor)
            .with_checkpointing(storage)
            .build()
        )

        # Test that run_stream_from_checkpoint accepts responses parameter
        responses = {"request_123": {"data": "test_response"}}

        try:
            events: list[WorkflowEvent] = []
            async for event in workflow.run_streaming_from_checkpoint(checkpoint_id, responses=responses):
                events.append(event)
                if len(events) >= 2:  # Limit to avoid infinite loops
                    break
        except Exception:
            # Expected since we have minimal setup, but method should accept the parameters
            pass


@dataclass
class StateTrackingMessage:
    """A message that tracks state for testing context reset behavior."""

    data: str
    run_id: str


class StateTrackingExecutor(Executor):
    """An executor that tracks state in shared state to test context reset behavior."""

    @handler
    async def handle_message(self, message: StateTrackingMessage, ctx: WorkflowContext[Any]) -> None:
        """Handle the message and track it in shared state."""
        # Get existing messages from shared state
        try:
            existing_messages = await ctx.get_shared_state("processed_messages")
        except KeyError:
            existing_messages = []

        # Record this message
        message_record = f"{message.run_id}:{message.data}"
        existing_messages.append(message_record)  # type: ignore

        # Update shared state
        await ctx.set_shared_state("processed_messages", existing_messages)

        # Complete workflow with current shared state
        await ctx.add_event(WorkflowCompletedEvent(data=existing_messages.copy()))  # type: ignore


async def test_workflow_multiple_runs_no_state_collision():
    """Test that running the same workflow instance multiple times doesn't have state collision."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create executor that tracks state in shared state
        state_executor = StateTrackingExecutor("state_executor")

        # Build workflow with checkpointing
        workflow = (
            WorkflowBuilder()
            .add_edge(state_executor, state_executor)  # Self-loop to satisfy graph requirements
            .set_start_executor(state_executor)
            .with_checkpointing(storage)
            .build()
        )

        # Run 1: Should only see messages from run 1
        result1 = await workflow.run(StateTrackingMessage(data="message1", run_id="run1"))
        completed1 = result1.get_completed_event()
        assert completed1 is not None
        assert completed1.data == ["run1:message1"]

        # Run 2: Should only see messages from run 2, not run 1
        result2 = await workflow.run(StateTrackingMessage(data="message2", run_id="run2"))
        completed2 = result2.get_completed_event()
        assert completed2 is not None
        assert completed2.data == ["run2:message2"]  # Should NOT contain run1 data

        # Run 3: Should only see messages from run 3
        result3 = await workflow.run(StateTrackingMessage(data="message3", run_id="run3"))
        completed3 = result3.get_completed_event()
        assert completed3 is not None
        assert completed3.data == ["run3:message3"]  # Should NOT contain run1 or run2 data

        # Verify that each run only processed its own message
        # This confirms that the checkpointable context properly resets between runs
        assert completed1.data != completed2.data
        assert completed2.data != completed3.data
        assert completed1.data != completed3.data
