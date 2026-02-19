# Copyright (c) Microsoft. All rights reserved.

import asyncio
import tempfile
from collections.abc import AsyncIterable, Awaitable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import uuid4

import pytest

from agent_framework import (
    AgentExecutor,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    Executor,
    FileCheckpointStorage,
    Message,
    ResponseStream,
    WorkflowBuilder,
    WorkflowCheckpointException,
    WorkflowContext,
    WorkflowConvergenceException,
    WorkflowEvent,
    WorkflowMessage,
    WorkflowRunState,
    handler,
    response_handler,
)


@dataclass
class NumberMessage:
    """A mock message for testing purposes."""

    data: int


class IncrementExecutor(Executor):
    """An executor that increments message data by a specified amount for testing purposes."""

    def __init__(self, id: str, *, limit: int = 10, increment: int = 1) -> None:
        super().__init__(id=id)
        self.limit = limit
        self.increment = increment

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
class MockRequest:
    """A mock request message for testing purposes."""

    request_id: str = field(default_factory=lambda: str(uuid4()))
    prompt: str = ""


@dataclass
class ApprovalMessage:
    """A mock message for approval requests."""

    approved: bool


class MockExecutorRequestApproval(Executor):
    """A mock executor that simulates a request for approval."""

    @handler
    async def mock_handler_a(self, message: NumberMessage, ctx: WorkflowContext) -> None:
        """A mock handler that requests approval."""
        ctx.set_state(self.id, message.data)
        await ctx.request_info(MockRequest(prompt="Mock approval request"), ApprovalMessage)

    @response_handler
    async def mock_handler_b(
        self,
        original_request: MockRequest,
        response: ApprovalMessage,
        ctx: WorkflowContext[NumberMessage, int],
    ) -> None:
        """A mock handler that processes the approval response."""
        data = ctx.get_state(self.id)
        assert isinstance(data, int)
        if response.approved:
            await ctx.yield_output(data)
        else:
            await ctx.send_message(NumberMessage(data=data))


async def test_workflow_run_streaming() -> None:
    """Test the workflow run stream."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder(start_executor=executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .build()
    )

    result: int | None = None
    async for event in workflow.run(NumberMessage(data=0), stream=True):
        assert isinstance(event, WorkflowEvent)
        if event.type == "output":
            result = event.data

    assert result is not None and result == 10


async def test_workflow_run_stream_not_completed():
    """Test the workflow run stream."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder(max_iterations=5, start_executor=executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .build()
    )

    with pytest.raises(WorkflowConvergenceException):
        async for _ in workflow.run(NumberMessage(data=0), stream=True):
            pass


async def test_workflow_run():
    """Test the workflow run."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder(start_executor=executor_a)
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
        WorkflowBuilder(max_iterations=5, start_executor=executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .build()
    )

    with pytest.raises(WorkflowConvergenceException):
        await workflow.run(NumberMessage(data=0))


async def test_fan_out():
    """Test a fan-out workflow."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b", limit=1)
    executor_c = IncrementExecutor(id="executor_c", limit=2)  # This executor will not complete the workflow

    workflow = (
        WorkflowBuilder(start_executor=executor_a).add_fan_out_edges(executor_a, [executor_b, executor_c]).build()
    )

    events = await workflow.run(NumberMessage(data=0))

    # Each executor will emit two events: executor_invoked (type='executor_invoked')
    # and executor_completed (type='executor_completed')
    # executor_b will also emit an output event (type='output')
    # Each superstep will emit a started event (type='started') and status event (type='status')
    # This workflow will converge in 2 supersteps because executor_c will send one more message
    # after executor_b completes
    assert len(events) == 11

    assert events.get_final_state() == WorkflowRunState.IDLE
    outputs = events.get_outputs()
    assert outputs[0] == 1


async def test_fan_out_multiple_completed_events():
    """Test a fan-out workflow with multiple completed events."""
    executor_a = IncrementExecutor(id="executor_a")
    executor_b = IncrementExecutor(id="executor_b", limit=1)
    executor_c = IncrementExecutor(id="executor_c", limit=1)

    workflow = (
        WorkflowBuilder(start_executor=executor_a).add_fan_out_edges(executor_a, [executor_b, executor_c]).build()
    )

    events = await workflow.run(NumberMessage(data=0))

    # Each executor will emit two events: executor_invoked (type='executor_invoked')
    # and executor_completed (type='executor_completed')
    # executor_b and executor_c will also emit an output event (type='output')
    # Each superstep will emit a started event (type='started') and status event (type='status')
    # This workflow will converge in 1 superstep because executor_a and executor_b will not send further messages
    assert len(events) == 10

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
        WorkflowBuilder(start_executor=executor_a)
        .add_fan_out_edges(executor_a, [executor_b, executor_c])
        .add_fan_in_edges([executor_b, executor_c], aggregator)
        .build()
    )

    events = await workflow.run(NumberMessage(data=0))

    # Each executor will emit two events: executor_invoked (type='executor_invoked')
    # and executor_completed (type='executor_completed')
    # aggregator will also emit an output event (type='output')
    # Each superstep will emit a started event (type='started') and status event (type='status')
    assert len(events) == 13

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
            WorkflowBuilder(start_executor=simple_executor, checkpoint_storage=storage)
            .add_edge(simple_executor, simple_executor)  # Self-loop to satisfy graph requirements
            .build()
        )

        # Verify workflow was created and can run
        test_message = WorkflowMessage(data="test message", source_id="test", target_id=None)
        result = await workflow.run(test_message)
        assert result is not None


async def test_workflow_checkpointing_not_enabled_for_external_restore(
    simple_executor: Executor,
):
    """Test that external checkpoint restoration fails when workflow doesn't support checkpointing."""
    # Build workflow WITHOUT checkpointing
    workflow = (
        WorkflowBuilder(start_executor=simple_executor)
        .add_edge(simple_executor, simple_executor)  # Self-loop to satisfy graph requirements
        .build()
    )

    # Attempt to restore from checkpoint without providing external storage should fail
    try:
        [event async for event in workflow.run(checkpoint_id="fake-checkpoint-id", stream=True)]
        raise AssertionError("Expected ValueError to be raised")
    except ValueError as e:
        assert "Cannot restore from checkpoint" in str(e)
        assert "either provide checkpoint_storage parameter" in str(e)


async def test_workflow_run_stream_from_checkpoint_no_checkpointing_enabled(
    simple_executor: Executor,
):
    # Build workflow WITHOUT checkpointing
    workflow = (
        WorkflowBuilder(start_executor=simple_executor)
        .add_edge(simple_executor, simple_executor)  # Self-loop to satisfy graph requirements
        .build()
    )

    # Attempt to run from checkpoint should fail
    try:
        async for _ in workflow.run(checkpoint_id="fake_checkpoint_id", stream=True):
            pass
        raise AssertionError("Expected ValueError to be raised")
    except ValueError as e:
        assert "Cannot restore from checkpoint" in str(e)
        assert "either provide checkpoint_storage parameter" in str(e)


async def test_workflow_run_stream_from_checkpoint_invalid_checkpoint(
    simple_executor: Executor,
):
    """Test that attempting to restore from a non-existent checkpoint fails appropriately."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Build workflow with checkpointing
        workflow = (
            WorkflowBuilder(start_executor=simple_executor, checkpoint_storage=storage)
            .add_edge(simple_executor, simple_executor)  # Self-loop to satisfy graph requirements
            .build()
        )

        # Attempt to run from non-existent checkpoint should fail
        with pytest.raises(WorkflowCheckpointException, match="No checkpoint found with ID nonexistent_checkpoint_id"):
            async for _ in workflow.run(checkpoint_id="nonexistent_checkpoint_id", stream=True):
                pass


async def test_workflow_run_stream_from_checkpoint_with_external_storage(
    simple_executor: Executor,
):
    """Test that external checkpoint storage can be provided for restoration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create a test checkpoint manually in storage
        from agent_framework import WorkflowCheckpoint

        test_checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-graph-signature",
            previous_checkpoint_id=None,
            messages={},
            state={},
            iteration_count=0,
        )
        checkpoint_id = await storage.save(test_checkpoint)

        # Create a workflow WITHOUT checkpointing
        workflow_without_checkpointing = (
            WorkflowBuilder(start_executor=simple_executor).add_edge(simple_executor, simple_executor).build()
        )

        # Resume from checkpoint using external storage parameter
        try:
            events: list[WorkflowEvent] = []
            async for event in workflow_without_checkpointing.run(
                checkpoint_id=checkpoint_id, checkpoint_storage=storage, stream=True
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

        # Build workflow with checkpointing
        workflow = (
            WorkflowBuilder(start_executor=simple_executor, checkpoint_storage=storage)
            .add_edge(simple_executor, simple_executor)
            .build()
        )

        # Create a test checkpoint manually in storage
        from agent_framework import WorkflowCheckpoint

        test_checkpoint = WorkflowCheckpoint(
            workflow_name=workflow.name,
            graph_signature_hash=workflow.graph_signature_hash,
            previous_checkpoint_id=None,
            messages={},
            state={},
            iteration_count=0,
        )
        checkpoint_id = await storage.save(test_checkpoint)

        # Test non-streaming run method with checkpoint_id
        result = await workflow.run(checkpoint_id=checkpoint_id)
        assert isinstance(result, list)  # Should return WorkflowRunResult which extends list
        assert hasattr(result, "get_outputs")  # Should have WorkflowRunResult methods


async def test_workflow_run_stream_from_checkpoint_with_responses(
    simple_executor: Executor,
):
    """Test that workflow can be resumed from checkpoint with pending request_info events."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Build workflow with checkpointing
        workflow = (
            WorkflowBuilder(start_executor=simple_executor, checkpoint_storage=storage)
            .add_edge(simple_executor, simple_executor)
            .build()
        )

        # Create a test checkpoint manually in storage
        from agent_framework import WorkflowCheckpoint

        test_checkpoint = WorkflowCheckpoint(
            workflow_name=workflow.name,
            graph_signature_hash=workflow.graph_signature_hash,
            messages={},
            state={},
            pending_request_info_events={
                "request_123": WorkflowEvent.request_info(
                    request_id="request_123",
                    source_executor_id=simple_executor.id,
                    request_data="Mock",
                    response_type=str,
                ),
            },
            iteration_count=0,
        )
        checkpoint_id = await storage.save(test_checkpoint)

        # Resume from checkpoint - pending request events should be emitted
        events: list[WorkflowEvent] = []
        async for event in workflow.run(checkpoint_id=checkpoint_id, stream=True):
            events.append(event)

        # Verify that the pending request event was emitted
        assert next(event for event in events if event.type == "request_info" and event.request_id == "request_123")

        assert len(events) > 0  # Just ensure we processed some events


@dataclass
class StateTrackingMessage:
    """A message that tracks state for testing context reset behavior."""

    data: str
    run_id: str


class StateTrackingExecutor(Executor):
    """An executor that tracks state in workflow state to test context reset behavior."""

    @handler
    async def handle_message(
        self,
        message: StateTrackingMessage,
        ctx: WorkflowContext[StateTrackingMessage, list[str]],
    ) -> None:
        """Handle the message and track it in workflow state."""
        # Get existing messages from workflow state
        existing_messages = ctx.get_state("processed_messages") or []

        # Record this message
        message_record = f"{message.run_id}:{message.data}"
        existing_messages.append(message_record)  # type: ignore

        # Update workflow state
        ctx.set_state("processed_messages", existing_messages)

        # Yield output
        await ctx.yield_output(existing_messages.copy())  # type: ignore


async def test_workflow_multiple_runs_no_state_collision():
    """Test that running the same workflow instance multiple times doesn't have state collision."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create executor that tracks state in workflow state
        state_executor = StateTrackingExecutor(id="state_executor")

        # Build workflow with checkpointing
        workflow = (
            WorkflowBuilder(start_executor=state_executor, checkpoint_storage=storage)
            .add_edge(state_executor, state_executor)  # Self-loop to satisfy graph requirements
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


async def test_workflow_checkpoint_runtime_only_configuration(
    simple_executor: Executor,
):
    """Test that checkpointing can be configured ONLY at runtime, not at build time."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Build workflow WITHOUT checkpointing at build time
        workflow = WorkflowBuilder(start_executor=simple_executor).add_edge(simple_executor, simple_executor).build()

        # Run with runtime checkpoint storage - should create checkpoints
        test_message = WorkflowMessage(data="runtime checkpoint test", source_id="test", target_id=None)
        result = await workflow.run(test_message, checkpoint_storage=storage)
        assert result is not None
        assert result.get_final_state() == WorkflowRunState.IDLE

        # Verify checkpoints were created
        checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
        assert len(checkpoints) > 0

        # Find a superstep checkpoint to resume from
        checkpoints.sort(key=lambda cp: cp.timestamp)
        resume_checkpoint = next(
            (cp for cp in checkpoints if (cp.metadata or {}).get("checkpoint_type") == "superstep"),
            checkpoints[-1],
        )

        # Create new workflow instance (still without build-time checkpointing)
        workflow_resume = (
            WorkflowBuilder(start_executor=simple_executor).add_edge(simple_executor, simple_executor).build()
        )

        # Resume from checkpoint using runtime checkpoint storage
        result_resumed = await workflow_resume.run(
            checkpoint_id=resume_checkpoint.checkpoint_id, checkpoint_storage=storage
        )
        assert result_resumed is not None
        assert result_resumed.get_final_state() in (
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        )


async def test_workflow_checkpoint_runtime_overrides_buildtime(
    simple_executor: Executor,
):
    """Test that runtime checkpoint storage overrides build-time configuration."""
    with (
        tempfile.TemporaryDirectory() as temp_dir1,
        tempfile.TemporaryDirectory() as temp_dir2,
    ):
        buildtime_storage = FileCheckpointStorage(temp_dir1)
        runtime_storage = FileCheckpointStorage(temp_dir2)

        # Build workflow with build-time checkpointing
        workflow = (
            WorkflowBuilder(start_executor=simple_executor, checkpoint_storage=buildtime_storage)
            .add_edge(simple_executor, simple_executor)
            .build()
        )

        # Run with runtime checkpoint storage override
        test_message = WorkflowMessage(data="override test", source_id="test", target_id=None)
        result = await workflow.run(test_message, checkpoint_storage=runtime_storage)
        assert result is not None

        # Verify checkpoints were created in runtime storage, not build-time storage
        buildtime_checkpoints = await buildtime_storage.list_checkpoints(workflow_name=workflow.name)
        runtime_checkpoints = await runtime_storage.list_checkpoints(workflow_name=workflow.name)

        assert len(runtime_checkpoints) > 0, "Runtime storage should have checkpoints"
        assert len(buildtime_checkpoints) == 0, "Build-time storage should have no checkpoints when overridden"


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
        WorkflowBuilder(start_executor=router)
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
        WorkflowBuilder(start_executor=executor_a)
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
    # Check for executor events that have executor_id
    from agent_framework import WorkflowEvent

    executor_events = [
        e for e in events if isinstance(e, WorkflowEvent) and e.type in ("executor_invoked", "executor_completed")
    ]
    executor_ids = {e.executor_id for e in executor_events}
    assert "exec_a" in executor_ids, "Should have events from executor A"
    assert "exec_b" in executor_ids, "Should have events from executor B"

    # Should have multiple events due to cycling
    assert len(events) >= 4, f"Expected at least 4 events due to cycling, got {len(events)}"


async def test_workflow_concurrent_execution_prevention():
    """Test that concurrent workflow executions are prevented."""
    # Create a simple workflow that takes some time to execute
    executor = IncrementExecutor(id="slow_executor", limit=3, increment=1)
    workflow = WorkflowBuilder(start_executor=executor).build()

    # Create a task that will run the workflow
    async def run_workflow():
        return await workflow.run(NumberMessage(data=0))

    # Start the first workflow execution
    task1 = asyncio.create_task(run_workflow())

    # Give it a moment to start
    await asyncio.sleep(0.01)

    # Try to start a second concurrent execution - this should fail
    with pytest.raises(
        RuntimeError,
        match="Workflow is already running. Concurrent executions are not allowed.",
    ):
        await workflow.run(NumberMessage(data=0))

    # Wait for the first task to complete
    result = await task1
    assert result.get_final_state() == WorkflowRunState.IDLE

    # After the first execution completes, we should be able to run again
    result2 = await workflow.run(NumberMessage(data=0))
    assert result2.get_final_state() == WorkflowRunState.IDLE


async def test_workflow_concurrent_execution_prevention_streaming():
    """Test that concurrent workflow streaming executions are prevented."""
    # Create a simple workflow
    executor = IncrementExecutor(id="slow_executor", limit=3, increment=1)
    workflow = WorkflowBuilder(start_executor=executor).build()

    # Create an async generator that will consume the stream slowly
    async def consume_stream_slowly():
        result: list[WorkflowEvent] = []
        async for event in workflow.run(NumberMessage(data=0), stream=True):
            result.append(event)
            await asyncio.sleep(0.01)  # Slow consumption
        return result

    # Start the first streaming execution
    task1 = asyncio.create_task(consume_stream_slowly())

    # Give it a moment to start
    await asyncio.sleep(0.02)

    # Try to start a second concurrent execution - this should fail
    with pytest.raises(
        RuntimeError,
        match="Workflow is already running. Concurrent executions are not allowed.",
    ):
        await workflow.run(NumberMessage(data=0))

    # Wait for the first task to complete
    result = await task1
    assert len(result) > 0  # Should have received some events

    # After the first execution completes, we should be able to run again
    result2 = await workflow.run(NumberMessage(data=0))
    assert result2.get_final_state() == WorkflowRunState.IDLE


async def test_workflow_concurrent_execution_prevention_mixed_methods():
    """Test that concurrent executions are prevented across different execution methods."""
    # Create a simple workflow
    executor = IncrementExecutor(id="slow_executor", limit=3, increment=1)
    workflow = WorkflowBuilder(start_executor=executor).build()

    # Start a streaming execution
    async def consume_stream():
        result: list[WorkflowEvent] = []
        async for event in workflow.run(NumberMessage(data=0), stream=True):
            result.append(event)
            await asyncio.sleep(0.01)
        return result

    task1 = asyncio.create_task(consume_stream())
    await asyncio.sleep(0.02)  # Let it start

    # Try different execution methods - all should fail
    with pytest.raises(
        RuntimeError,
        match="Workflow is already running. Concurrent executions are not allowed.",
    ):
        await workflow.run(NumberMessage(data=0))

    with pytest.raises(
        RuntimeError,
        match="Workflow is already running. Concurrent executions are not allowed.",
    ):
        async for _ in workflow.run(NumberMessage(data=0), stream=True):
            break

    # Wait for the original task to complete
    await task1

    # Now all methods should work again
    result = await workflow.run(NumberMessage(data=0))
    assert result.get_final_state() == WorkflowRunState.IDLE


class _StreamingTestAgent(BaseAgent):
    """Test agent that supports both streaming and non-streaming modes."""

    def __init__(self, *, reply_text: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._reply_text = reply_text

    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                # Simulate streaming by yielding character by character
                for char in self._reply_text:
                    yield AgentResponseUpdate(contents=[Content.from_text(text=char)])

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", [self._reply_text])])

        return _run()


async def test_agent_streaming_vs_non_streaming() -> None:
    """Test that stream=True/False both emit output events (type='output') with the right data types."""
    agent = _StreamingTestAgent(id="test_agent", name="TestAgent", reply_text="Hello World")
    agent_exec = AgentExecutor(agent, id="agent_exec")

    workflow = WorkflowBuilder(start_executor=agent_exec).build()

    # Test non-streaming mode with run()
    result = await workflow.run("test message")

    # Filter for agent events (result is a list of events)
    agent_run_events = [e for e in result if e.type == "output" and isinstance(e.data, AgentResponse)]
    agent_update_events = [e for e in result if e.type == "output" and isinstance(e.data, AgentResponseUpdate)]

    # In non-streaming mode, should have output event with AgentResponse, no AgentResponseUpdate
    assert len(agent_run_events) == 1, "Expected exactly one output event with AgentResponse in non-streaming mode"
    assert len(agent_update_events) == 0, "Expected no output event with AgentResponseUpdate in non-streaming mode"
    assert agent_run_events[0].executor_id == "agent_exec"
    assert agent_run_events[0].data is not None
    assert agent_run_events[0].data.messages[0].text == "Hello World"

    # Test streaming mode with run(stream=True)
    stream_events: list[WorkflowEvent] = []
    async for event in workflow.run("test message", stream=True):
        stream_events.append(event)

    # Filter for agent events
    agent_response = [
        cast(AgentResponse, e.data) for e in stream_events if e.type == "output" and isinstance(e.data, AgentResponse)
    ]
    agent_response_updates = [
        e.data for e in stream_events if e.type == "output" and isinstance(e.data, AgentResponseUpdate)
    ]

    # In streaming mode, should have AgentResponseUpdate, no AgentResponse
    assert len(agent_response) == 0, "Expected no AgentResponse in streaming mode"
    assert len(agent_response_updates) > 0, "Expected AgentResponseUpdate events in streaming mode"

    # Verify we got incremental updates (one per character in "Hello World")
    assert len(agent_response_updates) == len("Hello World"), "Expected one update per character"

    # Verify the updates build up to the full message
    accumulated_text = "".join([
        e.contents[0].text
        for e in agent_response_updates
        if e.contents
        and isinstance(e.contents[0], Content)
        and e.contents[0].type == "text"
        and e.contents[0].text is not None
    ])
    assert accumulated_text == "Hello World", f"Expected 'Hello World', got '{accumulated_text}'"


async def test_workflow_run_parameter_validation(simple_executor: Executor) -> None:
    """Test that stream properly validate parameter combinations."""
    workflow = WorkflowBuilder(start_executor=simple_executor).add_edge(simple_executor, simple_executor).build()

    test_message = WorkflowMessage(data="test", source_id="test", target_id=None)

    # Valid: message only (new run)
    result = await workflow.run(test_message)
    assert result.get_final_state() == WorkflowRunState.IDLE

    # Invalid: both message and checkpoint_id
    with pytest.raises(ValueError, match="Cannot provide both 'message' and 'checkpoint_id'"):
        await workflow.run(test_message, checkpoint_id="fake_id")

    # Invalid: both message and checkpoint_id (streaming)
    with pytest.raises(ValueError, match="Cannot provide both 'message' and 'checkpoint_id'"):
        async for _ in workflow.run(test_message, checkpoint_id="fake_id", stream=True):
            pass

    # Invalid: none of message or checkpoint_id
    with pytest.raises(ValueError, match="Must provide at least one of"):
        await workflow.run()

    # Invalid: none of message or checkpoint_id (streaming)
    with pytest.raises(ValueError, match="Must provide at least one of"):
        async for _ in workflow.run(stream=True):
            pass


async def test_workflow_run_stream_parameter_validation(
    simple_executor: Executor,
) -> None:
    """Test stream=True specific parameter validation scenarios."""
    workflow = WorkflowBuilder(start_executor=simple_executor).add_edge(simple_executor, simple_executor).build()

    test_message = WorkflowMessage(data="test", source_id="test", target_id=None)

    # Valid: message only (new run)
    events: list[WorkflowEvent] = []
    async for event in workflow.run(test_message, stream=True):
        events.append(event)
    assert any(e.type == "status" and e.state == WorkflowRunState.IDLE for e in events)

    # Invalid combinations already tested in test_workflow_run_parameter_validation
    # This test ensures streaming works correctly for valid parameters


# region Output executor filtering tests


class OutputProducerExecutor(Executor):
    """An executor that produces a unique output value for testing output filtering."""

    def __init__(self, id: str, output_value: int) -> None:
        super().__init__(id=id)
        self.output_value = output_value

    @handler
    async def handle_message(self, message: NumberMessage, ctx: WorkflowContext[NumberMessage, int]) -> None:
        await ctx.yield_output(self.output_value)


class PassthroughExecutor(Executor):
    """An executor that passes through messages and produces an output."""

    def __init__(self, id: str, output_value: int) -> None:
        super().__init__(id=id)
        self.output_value = output_value

    @handler
    async def handle_message(self, message: NumberMessage, ctx: WorkflowContext[NumberMessage, int]) -> None:
        await ctx.yield_output(self.output_value)
        await ctx.send_message(message)


async def test_output_executors_empty_yields_all_outputs() -> None:
    """Test that when _output_executors is empty (default), all outputs are yielded."""
    # Create executors that each produce different outputs
    executor_a = PassthroughExecutor(id="executor_a", output_value=10)
    executor_b = OutputProducerExecutor(id="executor_b", output_value=20)

    # Build workflow with a -> b
    workflow = WorkflowBuilder(start_executor=executor_a).add_edge(executor_a, executor_b).build()

    result = await workflow.run(NumberMessage(data=0))
    outputs = result.get_outputs()

    # Both executors' outputs should be present
    assert len(outputs) == 2
    assert outputs == [10, 20]

    output_events = [event for event in result if event.type == "output"]
    assert len(output_events) == 2
    assert output_events[0].executor_id == "executor_a"
    assert output_events[1].executor_id == "executor_b"


async def test_output_executors_filters_outputs_non_streaming() -> None:
    """Test that only outputs from specified executors are yielded in non-streaming mode."""
    # Create executors that each produce different outputs
    executor_a = PassthroughExecutor(id="executor_a", output_value=10)
    executor_b = OutputProducerExecutor(id="executor_b", output_value=20)

    # Build workflow with a -> b
    workflow = (
        WorkflowBuilder(start_executor=executor_a, output_executors=[executor_b])
        .add_edge(executor_a, executor_b)
        .build()
    )

    result = await workflow.run(NumberMessage(data=0))
    outputs = result.get_outputs()

    # Only executor_b's output should be present
    assert len(outputs) == 1
    assert outputs[0] == 20

    output_events = [event for event in result if event.type == "output"]
    assert len(output_events) == 1
    assert output_events[0].executor_id == "executor_b"


async def test_output_executors_filters_outputs_streaming() -> None:
    """Test that only outputs from specified executors are yielded in streaming mode."""
    # Create executors that each produce different outputs
    executor_a = PassthroughExecutor(id="executor_a", output_value=100)
    executor_b = OutputProducerExecutor(id="executor_b", output_value=200)

    # Build workflow with a -> b
    workflow = (
        WorkflowBuilder(start_executor=executor_a, output_executors=[executor_a])
        .add_edge(executor_a, executor_b)
        .build()
    )

    # Collect outputs from streaming
    output_events: list[WorkflowEvent] = []
    async for event in workflow.run(NumberMessage(data=0), stream=True):
        if event.type == "output":
            output_events.append(event)

    # Only executor_a's output should be present
    assert len(output_events) == 1
    assert output_events[0].data == 100
    assert output_events[0].executor_id == "executor_a"


async def test_output_executors_with_multiple_specified_executors() -> None:
    """Test filtering with multiple executors in the output list."""
    # Create three executors with pass-through to reach all of them
    executor_a = PassthroughExecutor(id="executor_a", output_value=1)
    executor_b = PassthroughExecutor(id="executor_b", output_value=2)
    executor_c = OutputProducerExecutor(id="executor_c", output_value=3)

    # Build workflow with a -> b -> c
    workflow = (
        WorkflowBuilder(start_executor=executor_a, output_executors=[executor_a, executor_c])
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_c)
        .build()
    )

    result = await workflow.run(NumberMessage(data=0))
    outputs = result.get_outputs()

    # Only executor_a and executor_c outputs should be present
    assert len(outputs) == 2
    assert 1 in outputs  # executor_a
    assert 3 in outputs  # executor_c
    assert 2 not in outputs  # executor_b should be filtered out


async def test_output_executors_with_nonexistent_executor_id() -> None:
    """Test that specifying a non-existent executor ID doesn't break the workflow."""
    executor_a = OutputProducerExecutor(id="executor_a", output_value=42)

    workflow = WorkflowBuilder(start_executor=executor_a).build()

    # Set output_executors to an ID that doesn't exist
    workflow._output_executors = ["nonexistent_executor"]  # type: ignore

    result = await workflow.run(NumberMessage(data=0))
    outputs = result.get_outputs()

    # No outputs should be yielded since the executor ID doesn't match
    assert len(outputs) == 0


async def test_output_executors_filtering_with_fan_in() -> None:
    """Test output filtering in a fan-in workflow."""

    class FanOutStartExecutor(Executor):
        """Executor that sends messages to fan-out targets."""

        @handler
        async def handle(self, message: NumberMessage, ctx: WorkflowContext[NumberMessage, int]) -> None:
            await ctx.yield_output(999)  # This should be filtered out
            await ctx.send_message(NumberMessage(data=5))

    class FanOutTargetExecutor(Executor):
        """Executor that processes fan-out messages."""

        def __init__(self, id: str, increment: int) -> None:
            super().__init__(id=id)
            self.increment = increment

        @handler
        async def handle(self, message: NumberMessage, ctx: WorkflowContext[NumberMessage, int]) -> None:
            await ctx.yield_output(888)  # This should be filtered out
            await ctx.send_message(NumberMessage(data=message.data + self.increment))

    # Create executors for fan-in pattern
    executor_start = FanOutStartExecutor(id="executor_start")
    executor_a = FanOutTargetExecutor(id="executor_a", increment=10)
    executor_b = FanOutTargetExecutor(id="executor_b", increment=20)
    aggregator = AggregatorExecutor(id="aggregator")

    # Build fan-in workflow: start -> [a, b] -> aggregator
    workflow = (
        WorkflowBuilder(start_executor=executor_start, output_executors=[aggregator])
        .add_fan_out_edges(executor_start, [executor_a, executor_b])
        .add_fan_in_edges([executor_a, executor_b], aggregator)
        .build()
    )

    result = await workflow.run(NumberMessage(data=0))
    outputs = result.get_outputs()

    # Only aggregator output should be present
    # executor_a sends 5+10=15, executor_b sends 5+20=25, aggregator sums: 15+25=40
    assert len(outputs) == 1
    assert outputs[0] == 40


async def test_output_executors_filtering_with_run_responses() -> None:
    """Test output filtering works correctly with run(responses=...) method."""
    executor = MockExecutorRequestApproval(id="approval_executor")

    workflow = WorkflowBuilder(start_executor=executor, output_executors=[executor]).build()

    # Run workflow which will request approval
    result = await workflow.run(NumberMessage(data=42))

    # Get request info events
    request_events = result.get_request_info_events()
    assert len(request_events) == 1

    # Send approval response
    responses = {request_events[0].request_id: ApprovalMessage(approved=True)}
    response_result = await workflow.run(responses=responses)
    outputs = response_result.get_outputs()

    # Output should be yielded since approval_executor is in output_executors
    assert len(outputs) == 1
    assert outputs[0] == 42


async def test_output_executors_filtering_with_run_responses_streaming() -> None:
    """Test output filtering works correctly with run(responses=..., stream=True) method."""
    executor = MockExecutorRequestApproval(id="approval_executor")

    workflow = WorkflowBuilder(start_executor=executor).build()

    # Run workflow which will request approval
    events_list: list[WorkflowEvent] = []
    async for event in workflow.run(NumberMessage(data=99), stream=True):
        events_list.append(event)

    # Get request info events
    request_events = [e for e in events_list if e.type == "request_info"]
    assert len(request_events) == 1

    # Set output_executors to exclude the approval executor
    workflow._output_executors = ["other_executor"]  # type: ignore

    # Send approval response via streaming
    responses = {request_events[0].request_id: ApprovalMessage(approved=True)}
    output_events: list[WorkflowEvent] = []
    async for event in workflow.run(responses=responses, stream=True):
        if event.type == "output":
            output_events.append(event)

    # No outputs should be yielded since approval_executor is not in output_executors
    assert len(output_events) == 0


# endregion
