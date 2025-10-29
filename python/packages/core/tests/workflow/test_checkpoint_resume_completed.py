# Copyright (c) Microsoft. All rights reserved.

import tempfile
from pathlib import Path

import pytest

from agent_framework import (
    Executor,
    FileCheckpointStorage,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework._workflows._events import (
    WorkflowEvent,
    WorkflowStartedEvent,
    WorkflowStatusEvent,
)


class CountingExecutor(Executor):
    """Executor that tracks how many times it executes."""

    execution_count: int = 0

    def __init__(self, executor_id: str, next_executor_id: str | None = None) -> None:
        super().__init__(id=executor_id)
        self.next_executor_id = next_executor_id

    @handler
    async def handle_message(self, message: str, ctx: WorkflowContext[str, str]) -> None:
        CountingExecutor.execution_count += 1
        output = f"{self.id}:{message}"

        if self.next_executor_id:
            await ctx.send_message(output, self.next_executor_id)
        else:
            await ctx.yield_output(output)


@pytest.fixture(autouse=True)
def reset_execution_count() -> None:
    """Reset the execution count before each test."""
    CountingExecutor.execution_count = 0


async def test_resume_from_completed_checkpoint_emits_no_events() -> None:
    """Test that resuming from a completed checkpoint (0 messages) emits no events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FileCheckpointStorage(Path(tmpdir))

        # Create a simple workflow with 2 executors
        first = CountingExecutor("first", "second")
        second = CountingExecutor("second", None)

        workflow = (
            WorkflowBuilder().set_start_executor(first).add_edge(first, second).with_checkpointing(storage).build()
        )

        # Run workflow to completion
        _ = [event async for event in workflow.run_stream("hello")]
        assert any(isinstance(e, WorkflowStatusEvent) for e in _)
        assert CountingExecutor.execution_count == 2

        # Get all checkpoints - last one should have 0 messages
        checkpoints = sorted(await storage.list_checkpoints(), key=lambda c: c.timestamp)
        assert len(checkpoints) > 0

        final_checkpoint = checkpoints[-1]
        assert sum(len(v) for v in final_checkpoint.messages.values()) == 0

        # Reset execution count
        CountingExecutor.execution_count = 0

        # Resume from final checkpoint - should emit NO events
        resumed_events = [
            event
            async for event in workflow.run_stream_from_checkpoint(
                final_checkpoint.checkpoint_id,
                checkpoint_storage=storage,
            )
        ]

        assert len(resumed_events) == 0, (
            f"Expected 0 events, got {len(resumed_events)}: {[type(e).__name__ for e in resumed_events]}"
        )
        assert CountingExecutor.execution_count == 0, "No executors should have run"


async def test_resume_from_checkpoint_with_messages_continues_execution() -> None:
    """Test that resuming from a checkpoint with messages continues execution normally."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FileCheckpointStorage(Path(tmpdir))

        # Create a simple workflow with 3 executors
        first = CountingExecutor("first", "second")
        second = CountingExecutor("second", "third")
        third = CountingExecutor("third", None)

        workflow = (
            WorkflowBuilder()
            .set_start_executor(first)
            .add_edge(first, second)
            .add_edge(second, third)
            .with_checkpointing(storage)
            .build()
        )

        # Run workflow to completion
        _ = [event async for event in workflow.run_stream("hello")]
        assert CountingExecutor.execution_count == 3

        # Get checkpoint after first executor (should have 1 message)
        checkpoints = sorted(await storage.list_checkpoints(), key=lambda c: c.timestamp)
        assert len(checkpoints) >= 2

        # Find checkpoint with messages
        checkpoint_with_messages = None
        for cp in checkpoints:
            if sum(len(v) for v in cp.messages.values()) > 0:
                checkpoint_with_messages = cp
                break

        assert checkpoint_with_messages is not None

        # Reset execution count
        CountingExecutor.execution_count = 0

        # Resume from checkpoint with messages - should continue execution
        resumed_events = [
            event
            async for event in workflow.run_stream_from_checkpoint(
                checkpoint_with_messages.checkpoint_id,
                checkpoint_storage=storage,
            )
        ]

        # Should emit events (started, status, etc.)
        assert len(resumed_events) > 0
        assert any(isinstance(e, WorkflowStartedEvent) for e in resumed_events)
        assert any(isinstance(e, WorkflowStatusEvent) for e in resumed_events)

        # Should have executed remaining executors
        assert CountingExecutor.execution_count > 0


async def test_resume_from_mid_execution_checkpoint() -> None:
    """Test resuming from a checkpoint in the middle of execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FileCheckpointStorage(Path(tmpdir))

        # Create a 4-executor workflow
        first = CountingExecutor("first", "second")
        second = CountingExecutor("second", "third")
        third = CountingExecutor("third", "fourth")
        fourth = CountingExecutor("fourth", None)

        workflow = (
            WorkflowBuilder()
            .set_start_executor(first)
            .add_edge(first, second)
            .add_edge(second, third)
            .add_edge(third, fourth)
            .with_checkpointing(storage)
            .build()
        )

        # Run to completion
        _ = [event async for event in workflow.run_stream("test")]
        assert CountingExecutor.execution_count == 4

        checkpoints = sorted(await storage.list_checkpoints(), key=lambda c: c.timestamp)

        # Test each checkpoint
        for i, cp in enumerate(checkpoints):
            CountingExecutor.execution_count = 0
            message_count = sum(len(v) for v in cp.messages.values())

            resumed_events: list[WorkflowEvent] = [
                event
                async for event in workflow.run_stream_from_checkpoint(
                    cp.checkpoint_id,
                    checkpoint_storage=storage,
                )
            ]

            if message_count == 0:
                # Final checkpoint - should emit NO events
                assert len(resumed_events) == 0, f"Checkpoint {i} with 0 messages emitted {len(resumed_events)} events"
                assert CountingExecutor.execution_count == 0
            else:
                # Checkpoint with messages - should continue execution
                assert len(resumed_events) > 0, f"Checkpoint {i} with {message_count} messages emitted no events"
                assert any(isinstance(e, WorkflowStartedEvent) for e in resumed_events)
                # Should have processed the pending messages
                assert CountingExecutor.execution_count > 0


async def test_early_break_in_runner_when_no_messages() -> None:
    """Test that the runner breaks early when there are no messages to process."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FileCheckpointStorage(Path(tmpdir))

        first = CountingExecutor("first", "second")
        second = CountingExecutor("second", None)

        workflow = (
            WorkflowBuilder().set_start_executor(first).add_edge(first, second).with_checkpointing(storage).build()
        )

        # Run workflow
        _ = [event async for event in workflow.run_stream("test")]
        assert CountingExecutor.execution_count == 2

        # Get final checkpoint
        checkpoints = await storage.list_checkpoints()
        final_checkpoint = sorted(checkpoints, key=lambda c: c.timestamp)[-1]

        # Reset and resume - should not run any iterations
        CountingExecutor.execution_count = 0

        resumed_events = [
            event
            async for event in workflow.run_stream_from_checkpoint(
                final_checkpoint.checkpoint_id,
                checkpoint_storage=storage,
            )
        ]

        assert len(resumed_events) == 0
        assert CountingExecutor.execution_count == 0
