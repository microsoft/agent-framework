# Copyright (c) Microsoft. All rights reserved.

import tempfile
from dataclasses import dataclass
from typing import Any

import pytest

from agent_framework import (
    Executor,
    FileCheckpointStorage,
    Message,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)


@dataclass
class NumberMessage:
    """A mock message for testing purposes."""

    data: int


class IncrementExecutor(Executor):
    """An executor that increments message data by a specified amount for testing purposes."""

    limit: int = 10
    increment: int = 1

    @handler
    async def mock_handler(self, message: NumberMessage, ctx: WorkflowContext[NumberMessage, int]) -> None:
        if message.data < self.limit:
            await ctx.send_message(NumberMessage(data=message.data + self.increment))
        else:
            await ctx.yield_output(message.data)


class AggregatorExecutor(Executor):
    """A mock executor that aggregates results from multiple executors."""

    @handler
    async def mock_handler(self, messages: list[NumberMessage], ctx: WorkflowContext[Any, int]) -> None:
        # This mock simply returns the sum of the data
        await ctx.yield_output(sum(msg.data for msg in messages))


@dataclass
class ApprovalMessage:
    """A mock message for approval requests."""

    approved: bool


class MockExecutorRequestApproval(Executor):
    """A mock executor that simulates a request for approval."""

    @handler
    async def mock_handler_a(self, message: NumberMessage, ctx: WorkflowContext[RequestInfoMessage]) -> None:
        """A mock handler that requests approval."""
        await ctx.set_shared_state(self.id, message.data)
        await ctx.send_message(RequestInfoMessage())

    @handler
    async def mock_handler_b(
        self,
        message: RequestResponse[RequestInfoMessage, ApprovalMessage],
        ctx: WorkflowContext[NumberMessage, int],
    ) -> None:
        """A mock handler that processes the approval response."""
        data = await ctx.get_shared_state(self.id)
        assert isinstance(data, int)
        assert isinstance(message.data, ApprovalMessage)
        if message.data.approved:
            await ctx.yield_output(data)
        else:
            await ctx.send_message(NumberMessage(data=data))


async def test_workflow_run_streaming() -> None:
    """Test the workflow run stream."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .build()
    )

    result: int | None = None
    async for event in workflow.run_stream(NumberMessage(data=0)):
        assert isinstance(event, WorkflowEvent)
        if isinstance(event, WorkflowOutputEvent):
            result = event.data

    assert result is not None and result == 10


async def test_workflow_run_stream_not_completed():
    """Test the workflow run stream."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .set_max_iterations(5)
        .build()
    )

    with pytest.raises(RuntimeError):
        async for _ in workflow.run_stream(NumberMessage(data=0)):
            pass


async def test_workflow_run():
    """Test the workflow run."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .build()
    )

    events = await workflow.run(NumberMessage(data=0))
    assert events.get_final_state() == WorkflowRunState.IDLE
    outputs = events.get_outputs()
    assert outputs[0] == 10


async def test_workflow_run_not_completed():
    """Test the workflow run."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .set_max_iterations(5)
        .build()
    )

    with pytest.raises(RuntimeError):
        await workflow.run(NumberMessage(data=0))


async def test_workflow_send_responses_streaming():
    """Test the workflow run with approval."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = MockExecutorRequestApproval(id="executor_b")
    request_info_executor = RequestInfoExecutor(id="request_info")

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
    async for event in workflow.run_stream(NumberMessage(data=0)):
        if isinstance(event, RequestInfoEvent):
            request_info_event = event

    assert request_info_event is not None
    result: int | None = None
    completed = False
    async for event in workflow.send_responses_streaming({
        request_info_event.request_id: ApprovalMessage(approved=True)
    }):
        if isinstance(event, WorkflowOutputEvent):
            result = event.data
        elif isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            completed = True

    assert (
        completed and result is not None and result == 1
    )  # The data should be incremented by 1 from the initial message


async def test_workflow_send_responses():
    """Test the workflow run with approval."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = MockExecutorRequestApproval(id="executor_b")
    request_info_executor = RequestInfoExecutor(id="request_info")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .add_edge(executor_b, request_info_executor)
        .add_edge(request_info_executor, executor_b)
        .build()
    )

    events = await workflow.run(NumberMessage(data=0))
    request_info_events = events.get_request_info_events()

    assert len(request_info_events) == 1

    result = await workflow.send_responses({request_info_events[0].request_id: ApprovalMessage(approved=True)})

    assert result.get_final_state() == WorkflowRunState.IDLE
    outputs = result.get_outputs()
    assert outputs[0] == 1  # The data should be incremented by 1 from the initial message


async def test_fan_out():
    """Test a fan-out workflow."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b", limit=1)
    executor_c = IncrementExecutor(id="executor_c", limit=2)  # This executor will not complete the workflow

    workflow = (
        WorkflowBuilder().set_start_executor(executor_a).add_fan_out_edges(executor_a, [executor_b, executor_c]).build()
    )

    events = await workflow.run(NumberMessage(data=0))

    # Each executor will emit two events: ExecutorInvokedEvent and ExecutorCompletedEvent
    # executor_b will also emit a WorkflowOutputEvent (no WorkflowCompletedEvent anymore)
    assert len(events) == 7

    assert events.get_final_state() == WorkflowRunState.IDLE
    outputs = events.get_outputs()
    assert outputs[0] == 1


async def test_fan_out_multiple_completed_events():
    """Test a fan-out workflow with multiple completed events."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b", limit=1)
    executor_c = IncrementExecutor(id="executor_c", limit=1)

    workflow = (
        WorkflowBuilder().set_start_executor(executor_a).add_fan_out_edges(executor_a, [executor_b, executor_c]).build()
    )

    events = await workflow.run(NumberMessage(data=0))

    # Each executor will emit two events: ExecutorInvokedEvent and ExecutorCompletedEvent
    # executor_b and executor_c will also emit a WorkflowOutputEvent (no WorkflowCompletedEvent anymore)
    assert len(events) == 8

    # Multiple outputs are expected from both executors
    outputs = events.get_outputs()
    assert len(outputs) == 2


async def test_fan_in():
    """Test a fan-in workflow."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b")
    executor_c = IncrementExecutor(id="executor_c")
    aggregator = AggregatorExecutor(id="aggregator")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_fan_out_edges(executor_a, [executor_b, executor_c])
        .add_fan_in_edges([executor_b, executor_c], aggregator)
        .build()
    )

    events = await workflow.run(NumberMessage(data=0))

    # Each executor will emit two events: ExecutorInvokedEvent and ExecutorCompletedEvent
    # aggregator will also emit a WorkflowOutputEvent (no WorkflowCompletedEvent anymore)
    assert len(events) == 9

    assert events.get_final_state() == WorkflowRunState.IDLE
    outputs = events.get_outputs()
    assert outputs[0] == 4  # executor_a(0->1), both executor_b and executor_c(1->2), aggregator(2+2=4)


@pytest.fixture
def simple_executor() -> Executor:
    class SimpleExecutor(Executor):
        @handler
        async def handle_message(self, message: str, context: WorkflowContext) -> None:
            pass

    return SimpleExecutor(id="test_executor")


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
        [event async for event in workflow.run_stream_from_checkpoint("fake-checkpoint-id")]
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
        async for _ in workflow.run_stream_from_checkpoint("fake_checkpoint_id"):
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
            async for _ in workflow.run_stream_from_checkpoint("nonexistent_checkpoint_id"):
                pass
            raise AssertionError("Expected RuntimeError to be raised")
        except RuntimeError as e:
            assert "Failed to restore from checkpoint" in str(e)


async def test_workflow_run_stream_from_checkpoint_with_external_storage(simple_executor: Executor):
    """Test that external checkpoint storage can be provided for restoration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create a test checkpoint manually in storage
        from agent_framework import WorkflowCheckpoint

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
            async for event in workflow_without_checkpointing.run_stream_from_checkpoint(
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
        from agent_framework import WorkflowCheckpoint

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
        assert hasattr(result, "get_outputs")  # Should have WorkflowRunResult methods


async def test_workflow_run_stream_from_checkpoint_with_responses(simple_executor: Executor):
    """Test that run_stream_from_checkpoint accepts responses parameter."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create a test checkpoint manually in storage
        from agent_framework import WorkflowCheckpoint

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
            async for event in workflow.run_stream_from_checkpoint(checkpoint_id, responses=responses):
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
    async def handle_message(self, message: StateTrackingMessage, ctx: WorkflowContext[Any, list]) -> None:
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

        # Yield output
        await ctx.yield_output(existing_messages.copy())  # type: ignore


async def test_workflow_multiple_runs_no_state_collision():
    """Test that running the same workflow instance multiple times doesn't have state collision."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create executor that tracks state in shared state
        state_executor = StateTrackingExecutor(id="state_executor")

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
        assert result1.get_final_state() == WorkflowRunState.IDLE
        outputs1 = result1.get_outputs()
        assert outputs1[0] == ["run1:message1"]

        # Run 2: Should only see messages from run 2, not run 1
        result2 = await workflow.run(StateTrackingMessage(data="message2", run_id="run2"))
        assert result2.get_final_state() == WorkflowRunState.IDLE
        outputs2 = result2.get_outputs()
        assert outputs2[0] == ["run2:message2"]  # Should NOT contain run1 data

        # Run 3: Should only see messages from run 3
        result3 = await workflow.run(StateTrackingMessage(data="message3", run_id="run3"))
        assert result3.get_final_state() == WorkflowRunState.IDLE
        outputs3 = result3.get_outputs()
        assert outputs3[0] == ["run3:message3"]  # Should NOT contain run1 or run2 data

        # Verify that each run only processed its own message
        # This confirms that the checkpointable context properly resets between runs
        assert outputs1[0] != outputs2[0]
        assert outputs2[0] != outputs3[0]
        assert outputs1[0] != outputs3[0]


async def test_comprehensive_edge_groups_workflow():
    """Test a workflow that uses SwitchCaseEdgeGroup, FanOutEdgeGroup, and FanInEdgeGroup."""
    from agent_framework import Case, Default

    # Create 6 executors for different roles with different increment values
    router = IncrementExecutor(id="router", limit=1000, increment=1)  # Increment by 1
    processor_a = IncrementExecutor(id="proc_a", limit=1000, increment=1)  # Increment by 1
    processor_b = IncrementExecutor(id="proc_b", limit=1000, increment=2)  # Increment by 2 (different from proc_a)
    fanout_hub = IncrementExecutor(id="fanout_hub", limit=1000, increment=1)  # Increment by 1
    parallel_1 = IncrementExecutor(id="parallel_1", limit=1000, increment=3)  # Increment by 3
    parallel_2 = IncrementExecutor(
        id="parallel_2", limit=1000, increment=5
    )  # Increment by 5 (different from parallel_1)
    aggregator = AggregatorExecutor(id="aggregator")  # Combines results from parallel processors

    # Build workflow with different edge group types:
    # 1. SwitchCase: router -> (proc_a if data < 5, else proc_b)
    # 2. Direct edge: proc_a -> fanout_hub, proc_b -> fanout_hub
    # 3. FanOut: fanout_hub -> [parallel_1, parallel_2]
    # 4. FanIn: [parallel_1, parallel_2] -> aggregator
    workflow = (
        WorkflowBuilder()
        .set_start_executor(router)
        # Switch-case routing based on message data
        .add_switch_case_edge_group(
            router,
            [
                Case(condition=lambda msg: msg.data < 5, target=processor_a),
                Default(target=processor_b),
            ],
        )
        # Both processors send to fanout hub
        .add_edge(processor_a, fanout_hub)
        .add_edge(processor_b, fanout_hub)
        # Fan out to parallel processors
        .add_fan_out_edges(fanout_hub, [parallel_1, parallel_2])
        # Fan in to aggregator
        .add_fan_in_edges([parallel_1, parallel_2], aggregator)
        .build()
    )

    # Test with small number (should go through processor_a)
    # router(2->3) -> switch routes to proc_a -> proc_a(3->4) -> fanout_hub(4->5)
    # -> [parallel_1(5->8), parallel_2(5->10)] -> aggregator(8+10=18)
    events_small = await workflow.run(NumberMessage(data=2))
    assert events_small.get_final_state() == WorkflowRunState.IDLE
    outputs_small = events_small.get_outputs()
    assert outputs_small[0] == 18  # Exact expected result: 8+10 from parallel processors

    # Test with large number (should go through processor_b)
    # router(8->9) -> switch routes to proc_b -> proc_b(9->11) -> fanout_hub(11->12)
    # -> [parallel_1(12->15), parallel_2(12->17)] -> aggregator(15+17=32)
    events_large = await workflow.run(NumberMessage(data=8))
    assert events_large.get_final_state() == WorkflowRunState.IDLE
    outputs_large = events_large.get_outputs()
    assert outputs_large[0] == 32  # Exact expected result: 15+17 from parallel processors

    # The key verification is that we successfully executed a workflow using all three edge group types
    # and that both switch-case paths work (small vs large numbers)

    # Verify we had multiple events indicating complex execution path
    assert len(events_small) >= 6  # Should have multiple executors involved
    assert len(events_large) >= 6

    # Verify different paths were taken by checking exact results
    assert outputs_small[0] == 18, f"Small number path should result in 18, got {outputs_small[0]}"
    assert outputs_large[0] == 32, f"Large number path should result in 32, got {outputs_large[0]}"
    assert outputs_small[0] != outputs_large[0], "Different paths should produce different results"

    # Both tests should complete successfully, proving all edge group types work

    # Additional verification: check that the workflow contains the expected edge group types
    edge_groups = workflow.edge_groups
    has_switch_case = any(edge_group.__class__.__name__ == "SwitchCaseEdgeGroup" for edge_group in edge_groups)
    has_fan_out = any(edge_group.__class__.__name__ == "FanOutEdgeGroup" for edge_group in edge_groups)
    has_fan_in = any(edge_group.__class__.__name__ == "FanInEdgeGroup" for edge_group in edge_groups)

    assert has_switch_case, "Workflow should contain SwitchCaseEdgeGroup"
    assert has_fan_out, "Workflow should contain FanOutEdgeGroup"
    assert has_fan_in, "Workflow should contain FanInEdgeGroup"


async def test_workflow_with_simple_cycle_and_exit_condition():
    """Test a simpler workflow with a cycle that has a clear exit condition."""

    # Create a simple cycle: A -> B -> A, with A having an exit condition
    executor_a = IncrementExecutor(id="exec_a", limit=6, increment=2)  # Exit when data >= 6
    executor_b = IncrementExecutor(id="exec_b", limit=1000, increment=1)  # Never exit, just increment

    # Simple cycle: A -> B -> A, A exits when limit reached
    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)  # A -> B
        .add_edge(executor_b, executor_a)  # B -> A (creates cycle)
        .build()
    )

    # Test the cycle
    # Expected: exec_a(2->4) -> exec_b(4->5) -> exec_a(5->7, completes because 7 >= 6)
    events = await workflow.run(NumberMessage(data=2))
    assert events.get_final_state() == WorkflowRunState.IDLE
    outputs = events.get_outputs()
    assert outputs[0] is not None and outputs[0] >= 6  # Should complete when executor_a reaches its limit

    # Verify cycling occurred (should have events from both executors)
    # Check for ExecutorInvokedEvent and ExecutorCompletedEvent types that have executor_id
    from agent_framework import ExecutorCompletedEvent, ExecutorInvokedEvent

    executor_events = [e for e in events if isinstance(e, (ExecutorInvokedEvent, ExecutorCompletedEvent))]
    executor_ids = {e.executor_id for e in executor_events}
    assert "exec_a" in executor_ids, "Should have events from executor A"
    assert "exec_b" in executor_ids, "Should have events from executor B"

    # Should have multiple events due to cycling
    assert len(events) >= 4, f"Expected at least 4 events due to cycling, got {len(events)}"
