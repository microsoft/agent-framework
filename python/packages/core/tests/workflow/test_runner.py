# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework import (
    AgentExecutorResponse,
    AgentResponse,
    Executor,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
    WorkflowCheckpointException,
    WorkflowContext,
    WorkflowConvergenceException,
    WorkflowEvent,
    WorkflowRunnerException,
    WorkflowRunState,
    handler,
)
from agent_framework._workflows._const import EXECUTOR_STATE_KEY
from agent_framework._workflows._edge import FanOutEdgeGroup, SingleEdgeGroup
from agent_framework._workflows._runner import Runner
from agent_framework._workflows._runner_context import (
    InProcRunnerContext,
    RunnerContext,
    WorkflowMessage,
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

    runner = Runner(
        edge_groups,
        executors,
        state=State(),
        ctx=InProcRunnerContext(),
        workflow_name="test_name",
        graph_signature_hash="test_hash",
    )

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

    runner = Runner(edges, executors, state, ctx, "test_name", graph_signature_hash="test_hash")

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

    runner = Runner(edges, executors, state, ctx, "test_name", graph_signature_hash="test_hash", max_iterations=5)

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


async def test_runner_run_iteration_preserves_message_order_per_edge_runner() -> None:
    """Test that _run_iteration preserves message order to the same target path."""

    class RecordingEdgeRunner:
        def __init__(self) -> None:
            self.received: list[int] = []

        async def send_message(self, message: WorkflowMessage, state: State, ctx: RunnerContext) -> bool:
            message_data = message.data
            assert isinstance(message_data, MockMessage)
            self.received.append(message_data.data)
            return True

    ctx = InProcRunnerContext()
    state = State()
    runner = Runner([], {}, state, ctx, "test_name", graph_signature_hash="test_hash")

    edge_runner = RecordingEdgeRunner()
    runner._edge_runner_map = {"source": [edge_runner]}  # type: ignore[assignment]

    for index in range(5):
        await ctx.send_message(WorkflowMessage(data=MockMessage(data=index), source_id="source"))

    await runner._run_iteration()

    assert edge_runner.received == [0, 1, 2, 3, 4]


async def test_runner_run_iteration_delivers_different_edge_runners_concurrently() -> None:
    """Test that different edge runners for the same source are executed concurrently."""

    class BlockingEdgeRunner:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.call_count = 0

        async def send_message(self, message: WorkflowMessage, state: State, ctx: RunnerContext) -> bool:
            self.call_count += 1
            self.started.set()
            await self.release.wait()
            return True

    class ProbeEdgeRunner:
        def __init__(self) -> None:
            self.probe_completed = asyncio.Event()
            self.call_count = 0

        async def send_message(self, message: WorkflowMessage, state: State, ctx: RunnerContext) -> bool:
            self.call_count += 1
            self.probe_completed.set()
            return True

    ctx = InProcRunnerContext()
    state = State()
    runner = Runner([], {}, state, ctx, "test_name", graph_signature_hash="test_hash")

    blocking_edge_runner = BlockingEdgeRunner()
    probe_edge_runner = ProbeEdgeRunner()
    runner._edge_runner_map = {"source": [blocking_edge_runner, probe_edge_runner]}  # type: ignore[assignment]

    await ctx.send_message(WorkflowMessage(data=MockMessage(data=1), source_id="source"))

    iteration_task = asyncio.create_task(runner._run_iteration())

    await blocking_edge_runner.started.wait()
    await asyncio.wait_for(probe_edge_runner.probe_completed.wait(), timeout=2.0)

    blocking_edge_runner.release.set()
    await iteration_task

    assert blocking_edge_runner.call_count == 1
    assert probe_edge_runner.call_count == 1


async def test_fanout_edge_runner_delivers_to_multiple_targets_concurrently() -> None:
    """Test that FanOutEdgeRunner delivers messages to multiple targets concurrently.

    This verifies that when a message is broadcast through a FanOutEdgeGroup (no target_id),
    the runner delivers to all targets concurrently rather than sequentially.
    """

    class BlockingExecutor(Executor):
        """An executor that blocks until released, used to detect concurrent execution."""

        def __init__(self, id: str) -> None:
            super().__init__(id=id)
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.call_count = 0

        @handler
        async def handle(self, message: MockMessage, ctx: WorkflowContext[MockMessage, int]) -> None:
            self.call_count += 1
            self.started.set()
            await self.release.wait()

    class ProbeExecutor(Executor):
        """An executor that completes immediately, used to probe concurrent execution."""

        def __init__(self, id: str) -> None:
            super().__init__(id=id)
            self.probe_completed = asyncio.Event()
            self.call_count = 0

        @handler
        async def handle(self, message: MockMessage, ctx: WorkflowContext[MockMessage, int]) -> None:
            self.call_count += 1
            self.probe_completed.set()

    source = MockExecutor(id="source")
    blocking_target = BlockingExecutor(id="blocking_target")
    probe_target = ProbeExecutor(id="probe_target")

    # FanOutEdgeGroup broadcasts messages to multiple targets
    edge_group = FanOutEdgeGroup(source_id=source.id, target_ids=[blocking_target.id, probe_target.id])

    executors: dict[str, Executor] = {
        source.id: source,
        blocking_target.id: blocking_target,
        probe_target.id: probe_target,
    }

    ctx = InProcRunnerContext()
    state = State()
    runner = Runner([edge_group], executors, state, ctx, "test_name", graph_signature_hash="test_hash")

    # Queue a message from source (will be delivered to both targets via FanOut)
    await ctx.send_message(WorkflowMessage(data=MockMessage(data=1), source_id=source.id))

    iteration_task = asyncio.create_task(runner._run_iteration())

    # Wait for the blocking executor to start
    await blocking_target.started.wait()

    # If FanOut delivers concurrently, the probe should complete while blocking is still waiting
    # If sequential, this would timeout because probe wouldn't start until blocking finishes
    await asyncio.wait_for(probe_target.probe_completed.wait(), timeout=2.0)

    # Release the blocking executor to allow iteration to complete
    blocking_target.release.set()
    await iteration_task

    # Both executors should have been called exactly once
    assert blocking_target.call_count == 1
    assert probe_target.call_count == 1


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

    runner = Runner(edges, executors, state, ctx, "test_name", graph_signature_hash="test_hash")

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
    runner = Runner([], {}, State(), ctx, "test_name", graph_signature_hash="test_hash")

    await ctx.send_message(
        WorkflowMessage(
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

    runner = Runner(edges, executors, shared_state, ctx, "test_name", graph_signature_hash="test_hash")

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


class FailingExecutor(Executor):
    """An executor that fails during execution."""

    def __init__(self, id: str, fail_on_data: int = 5):
        super().__init__(id=id)
        self.fail_on_data = fail_on_data

    @handler
    async def handle(self, message: MockMessage, ctx: WorkflowContext[MockMessage, int]) -> None:
        if message.data == self.fail_on_data:
            raise RuntimeError("Simulated executor failure")
        await ctx.send_message(MockMessage(data=message.data + 1))


async def test_runner_iteration_exception_drains_events():
    """Test that when an executor raises an exception, events are drained before propagating."""
    executor_a = FailingExecutor(id="executor_a", fail_on_data=2)
    executor_b = MockExecutor(id="executor_b")

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

    runner = Runner(edges, executors, state, ctx, "test_name", graph_signature_hash="test_hash")

    await executor_a.execute(
        MockMessage(data=0),
        ["START"],
        state,
        ctx,
    )

    events: list[WorkflowEvent] = []
    with pytest.raises(RuntimeError, match="Simulated executor failure"):
        async for event in runner.run_until_convergence():
            events.append(event)

    # There should be some events emitted before the failure
    assert len(events) > 0


async def test_runner_reset_iteration_count():
    """Test that reset_iteration_count works correctly."""
    executor_a = MockExecutor(id="executor_a")
    state = State()
    ctx = InProcRunnerContext()

    runner = Runner([], {executor_a.id: executor_a}, state, ctx, "test_name", graph_signature_hash="test_hash")
    runner._iteration = 10

    runner.reset_iteration_count()

    assert runner._iteration == 0


class CheckpointingContext(InProcRunnerContext):
    """A context that supports checkpointing for testing."""

    def __init__(self, storage: InMemoryCheckpointStorage | None = None):
        super().__init__()
        self._storage = storage or InMemoryCheckpointStorage()
        self._checkpointing_enabled = True

    def has_checkpointing(self) -> bool:
        return self._checkpointing_enabled

    async def create_checkpoint(
        self,
        workflow_name: str,
        graph_signature_hash: str,
        state: State,
        previous_checkpoint_id: str | None,
        iteration: int,
    ) -> str:
        checkpoint = WorkflowCheckpoint(
            workflow_name=workflow_name,
            graph_signature_hash=graph_signature_hash,
            state=state.export(),
            previous_checkpoint_id=previous_checkpoint_id,
            iteration_count=iteration,
        )
        return await self._storage.save(checkpoint)

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        try:
            return await self._storage.load(checkpoint_id)
        except WorkflowCheckpointException:
            return None

    async def apply_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        # Restore messages from checkpoint
        for source_id, messages in checkpoint.messages.items():
            for msg_data in messages:
                await self.send_message(WorkflowMessage(data=msg_data, source_id=source_id))


class FailingCheckpointContext(InProcRunnerContext):
    """A context that fails during checkpoint creation."""

    def has_checkpointing(self) -> bool:
        return True

    async def create_checkpoint(
        self,
        workflow_name: str,
        graph_signature_hash: str,
        state: State,
        previous_checkpoint_id: str | None,
        iteration: int,
    ) -> str:
        raise RuntimeError("Simulated checkpoint failure")


async def test_runner_checkpoint_creation_failure():
    """Test that checkpoint creation failure is handled gracefully."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    edges = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {
        executor_a.id: executor_a,
        executor_b.id: executor_b,
    }
    state = State()
    ctx = FailingCheckpointContext()

    runner = Runner(edges, executors, state, ctx, "test_name", graph_signature_hash="test_hash")

    await executor_a.execute(
        MockMessage(data=0),
        ["START"],
        state,
        ctx,
    )

    # Should complete without raising, even though checkpointing fails
    result: int | None = None
    async for event in runner.run_until_convergence():
        if event.type == "output":
            result = event.data

    assert result == 10


async def test_runner_restore_from_checkpoint_with_external_storage():
    """Test restoring from checkpoint using external storage when context has no checkpointing."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    edges = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {
        executor_a.id: executor_a,
        executor_b.id: executor_b,
    }
    state = State()
    ctx = InProcRunnerContext()  # No checkpointing enabled

    runner = Runner(edges, executors, state, ctx, "test_name", graph_signature_hash="test_hash")

    # Create a checkpoint manually
    storage = InMemoryCheckpointStorage()
    checkpoint = WorkflowCheckpoint(
        workflow_name="test_name",
        graph_signature_hash="test_hash",
        state={"test_key": "test_value"},
        iteration_count=5,
    )
    checkpoint_id = await storage.save(checkpoint)

    # Restore using external storage
    await runner.restore_from_checkpoint(checkpoint_id, checkpoint_storage=storage)

    assert runner._resumed_from_checkpoint is True
    assert runner._iteration == 5
    assert state.get("test_key") == "test_value"


async def test_runner_restore_from_checkpoint_no_storage():
    """Test that restore fails when no checkpointing and no external storage."""
    state = State()
    ctx = InProcRunnerContext()

    runner = Runner([], {}, state, ctx, "test_name", graph_signature_hash="test_hash")

    with pytest.raises(WorkflowCheckpointException, match="Cannot load checkpoint"):
        await runner.restore_from_checkpoint("nonexistent-id")


async def test_runner_restore_from_checkpoint_not_found():
    """Test that restore fails when checkpoint is not found."""
    storage = InMemoryCheckpointStorage()
    ctx = CheckpointingContext(storage)
    state = State()

    runner = Runner([], {}, state, ctx, "test_name", graph_signature_hash="test_hash")

    with pytest.raises(WorkflowCheckpointException, match="not found"):
        await runner.restore_from_checkpoint("nonexistent-id")


async def test_runner_restore_from_checkpoint_graph_hash_mismatch():
    """Test that restore fails when graph hash doesn't match."""
    storage = InMemoryCheckpointStorage()
    ctx = CheckpointingContext(storage)
    state = State()

    runner = Runner([], {}, state, ctx, "test_name", graph_signature_hash="current_hash")

    # Create a checkpoint with a different graph hash
    checkpoint = WorkflowCheckpoint(
        workflow_name="test_name",
        graph_signature_hash="different_hash",
        state={},
        iteration_count=5,
    )
    checkpoint_id = await storage.save(checkpoint)

    with pytest.raises(WorkflowCheckpointException, match="Workflow graph has changed"):
        await runner.restore_from_checkpoint(checkpoint_id)


async def test_runner_restore_from_checkpoint_generic_exception():
    """Test that generic exceptions during restore are wrapped in WorkflowCheckpointException."""
    state = State()

    # Create a mock context that raises a generic exception
    mock_ctx = MagicMock(spec=InProcRunnerContext)
    mock_ctx.has_checkpointing.return_value = True
    mock_ctx.load_checkpoint = AsyncMock(side_effect=ValueError("Unexpected error"))

    runner = Runner([], {}, state, mock_ctx, "test_name", graph_signature_hash="test_hash")

    with pytest.raises(WorkflowCheckpointException, match="Failed to restore from checkpoint"):
        await runner.restore_from_checkpoint("some-id")


async def test_runner_restore_executor_states_invalid_states_type():
    """Test that restore fails when executor states is not a dict."""
    executor_a = MockExecutor(id="executor_a")
    state = State()
    state.set(EXECUTOR_STATE_KEY, "not_a_dict")
    state.commit()

    ctx = InProcRunnerContext()
    runner = Runner([], {executor_a.id: executor_a}, state, ctx, "test_name", graph_signature_hash="test_hash")

    with pytest.raises(WorkflowCheckpointException, match="not a dictionary"):
        await runner._restore_executor_states()


async def test_runner_restore_executor_states_invalid_executor_id_type():
    """Test that restore fails when executor ID is not a string."""
    executor_a = MockExecutor(id="executor_a")
    state = State()
    state.set(EXECUTOR_STATE_KEY, {123: {"key": "value"}})  # Non-string key
    state.commit()

    ctx = InProcRunnerContext()
    runner = Runner([], {executor_a.id: executor_a}, state, ctx, "test_name", graph_signature_hash="test_hash")

    with pytest.raises(WorkflowCheckpointException, match="not a string"):
        await runner._restore_executor_states()


async def test_runner_restore_executor_states_invalid_state_type():
    """Test that restore fails when executor state is not a dict[str, Any]."""
    executor_a = MockExecutor(id="executor_a")
    state = State()
    state.set(EXECUTOR_STATE_KEY, {"executor_a": "not_a_dict"})
    state.commit()

    ctx = InProcRunnerContext()
    runner = Runner([], {executor_a.id: executor_a}, state, ctx, "test_name", graph_signature_hash="test_hash")

    with pytest.raises(WorkflowCheckpointException, match="not a dict"):
        await runner._restore_executor_states()


async def test_runner_restore_executor_states_invalid_state_keys():
    """Test that restore fails when executor state dict has non-string keys."""
    executor_a = MockExecutor(id="executor_a")
    state = State()
    state.set(EXECUTOR_STATE_KEY, {"executor_a": {123: "value"}})  # Non-string key in state
    state.commit()

    ctx = InProcRunnerContext()
    runner = Runner([], {executor_a.id: executor_a}, state, ctx, "test_name", graph_signature_hash="test_hash")

    with pytest.raises(WorkflowCheckpointException, match="not a dict"):
        await runner._restore_executor_states()


async def test_runner_restore_executor_states_missing_executor():
    """Test that restore fails when executor is not found."""
    state = State()
    state.set(EXECUTOR_STATE_KEY, {"missing_executor": {"key": "value"}})
    state.commit()

    ctx = InProcRunnerContext()
    runner = Runner([], {}, state, ctx, "test_name", graph_signature_hash="test_hash")

    with pytest.raises(WorkflowCheckpointException, match="not found during state restoration"):
        await runner._restore_executor_states()


async def test_runner_set_executor_state_invalid_existing_states():
    """Test that _set_executor_state fails when existing states is not a dict."""
    executor_a = MockExecutor(id="executor_a")
    state = State()
    state.set(EXECUTOR_STATE_KEY, "not_a_dict")

    ctx = InProcRunnerContext()
    runner = Runner([], {executor_a.id: executor_a}, state, ctx, "test_name", graph_signature_hash="test_hash")

    with pytest.raises(WorkflowCheckpointException, match="not a dictionary"):
        await runner._set_executor_state("executor_a", {"key": "value"})


async def test_runner_with_pre_loop_events():
    """Test that pre-loop events are yielded correctly."""
    ctx = InProcRunnerContext()
    state = State()

    runner = Runner([], {}, state, ctx, "test_name", graph_signature_hash="test_hash")

    # Add an event before running
    await ctx.add_event(WorkflowEvent.output(executor_id="test_executor", data="pre-loop-output"))

    events: list[WorkflowEvent] = []
    async for event in runner.run_until_convergence():
        events.append(event)

    # Should have the pre-loop output event
    output_events = [e for e in events if e.type == "output"]
    assert len(output_events) == 1
    assert output_events[0].data == "pre-loop-output"


class EventEmittingExecutor(Executor):
    """An executor that emits events during execution."""

    @handler
    async def handle(self, message: MockMessage, ctx: WorkflowContext[MockMessage, int]) -> None:
        # Emit event during processing
        await ctx.yield_output(f"processed-{message.data}")
        if message.data < 3:
            await ctx.send_message(MockMessage(data=message.data + 1))


async def test_runner_drains_straggler_events():
    """Test that events emitted at the end of iteration are drained."""
    executor_a = EventEmittingExecutor(id="executor_a")
    executor_b = EventEmittingExecutor(id="executor_b")

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

    runner = Runner(edges, executors, state, ctx, "test_name", graph_signature_hash="test_hash")

    await executor_a.execute(
        MockMessage(data=0),
        ["START"],
        state,
        ctx,
    )

    events: list[WorkflowEvent] = []
    async for event in runner.run_until_convergence():
        events.append(event)

    # Should have output events from both executors
    output_events = [e for e in events if e.type == "output"]
    assert len(output_events) > 0


async def test_runner_restore_executor_states_no_states():
    """Test that restore does nothing when there are no executor states."""
    executor_a = MockExecutor(id="executor_a")
    state = State()  # No executor states set
    state.commit()

    ctx = InProcRunnerContext()
    runner = Runner([], {executor_a.id: executor_a}, state, ctx, "test_name", graph_signature_hash="test_hash")

    # Should complete without error when no executor states exist
    await runner._restore_executor_states()


async def test_runner_checkpoint_with_resumed_flag():
    """Test that resumed flag prevents initial checkpoint creation."""
    storage = InMemoryCheckpointStorage()
    ctx = CheckpointingContext(storage)
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    edges = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
        SingleEdgeGroup(executor_b.id, executor_a.id),
    ]

    executors: dict[str, Executor] = {
        executor_a.id: executor_a,
        executor_b.id: executor_b,
    }
    state = State()

    runner = Runner(edges, executors, state, ctx, "test_name", graph_signature_hash="test_hash")
    runner._mark_resumed(5)

    # Add a message to trigger the checkpoint creation path
    await ctx.send_message(WorkflowMessage(data=MockMessage(data=8), source_id="START"))

    await executor_a.execute(
        MockMessage(data=8),
        ["START"],
        state,
        ctx,
    )

    # Run until convergence
    async for _ in runner.run_until_convergence():
        pass

    # After completing, resumed flag should be reset
    assert runner._resumed_from_checkpoint is False


class ExecutorThatFailsWithEvents(Executor):
    """An executor that emits events and then raises an exception after receiving messages."""

    def __init__(self, id: str, runner_ctx: RunnerContext, fail_on_iteration: int = 1):
        super().__init__(id=id)
        self._runner_ctx = runner_ctx
        self._fail_on_iteration = fail_on_iteration
        self._iteration_count = 0

    @handler
    async def handle(self, message: MockMessage, ctx: WorkflowContext[MockMessage, int]) -> None:
        self._iteration_count += 1
        # First emit an output event to the workflow context
        await ctx.yield_output(f"output-before-failure-{message.data}")
        # Add some events directly to the runner context
        await self._runner_ctx.add_event(WorkflowEvent.output(executor_id=self.id, data="pending-event"))
        # Fail on the specified iteration
        if self._iteration_count >= self._fail_on_iteration:
            raise RuntimeError("Executor failed with pending events")
        # Otherwise, send to next
        await ctx.send_message(MockMessage(data=message.data + 1))


class PassthroughExecutor(Executor):
    """An executor that passes messages through to the failing executor."""

    @handler
    async def handle(self, message: MockMessage, ctx: WorkflowContext[MockMessage, int]) -> None:
        await ctx.send_message(MockMessage(data=message.data))


async def test_runner_drains_events_on_iteration_exception():
    """Test that events are drained when iteration task raises an exception (lines 128-129)."""
    ctx = InProcRunnerContext()
    # executor_b will fail with pending events after receiving a message
    executor_a = PassthroughExecutor(id="executor_a")
    executor_b = ExecutorThatFailsWithEvents(id="executor_b", runner_ctx=ctx, fail_on_iteration=1)

    edges = [
        SingleEdgeGroup(executor_a.id, executor_b.id),
    ]

    executors: dict[str, Executor] = {
        executor_a.id: executor_a,
        executor_b.id: executor_b,
    }
    state = State()

    runner = Runner(edges, executors, state, ctx, "test_name", graph_signature_hash="test_hash")

    # Execute through executor_a which will pass to executor_b during the runner iteration
    await executor_a.execute(
        MockMessage(data=0),
        ["START"],
        state,
        ctx,
    )

    events: list[WorkflowEvent] = []
    with pytest.raises(RuntimeError, match="Executor failed with pending events"):
        async for event in runner.run_until_convergence():
            events.append(event)

    # Events should include the ones emitted before the exception
    output_events = [e for e in events if e.type == "output"]
    # Should have drained the pending events before propagating the exception
    assert len(output_events) >= 1


class SlowEventEmittingExecutor(Executor):
    """An executor that emits events with delays to test straggler event draining."""

    def __init__(self, id: str, iterations_to_emit: int = 2):
        super().__init__(id=id)
        self.iterations_to_emit = iterations_to_emit
        self.current_iteration = 0

    @handler
    async def handle(self, message: MockMessage, ctx: WorkflowContext[MockMessage, int]) -> None:
        self.current_iteration += 1
        # Emit output event
        await ctx.yield_output(f"iteration-{self.current_iteration}")
        # Continue sending messages until we reach the target iterations
        if self.current_iteration < self.iterations_to_emit:
            await ctx.send_message(MockMessage(data=message.data + 1))


async def test_runner_drains_straggler_events_at_iteration_end():
    """Test that events emitted at the very end of iteration are drained (lines 135-136)."""
    # Create executors that ping-pong messages and emit events
    executor_a = SlowEventEmittingExecutor(id="executor_a", iterations_to_emit=3)
    executor_b = SlowEventEmittingExecutor(id="executor_b", iterations_to_emit=3)

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

    runner = Runner(edges, executors, state, ctx, "test_name", graph_signature_hash="test_hash")

    await executor_a.execute(
        MockMessage(data=0),
        ["START"],
        state,
        ctx,
    )

    events: list[WorkflowEvent] = []
    async for event in runner.run_until_convergence():
        events.append(event)

    # Check that output events were collected (including straggler events)
    output_events = [e for e in events if e.type == "output"]
    # We should have output events from both executors
    assert len(output_events) >= 2
