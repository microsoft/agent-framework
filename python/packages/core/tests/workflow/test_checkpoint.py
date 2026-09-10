# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from concurrent.futures import Future as ConcurrentFuture
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from agent_framework import (
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
    WorkflowCheckpointException,
    WorkflowEvent,
)
from agent_framework._workflows._runner_context import WorkflowMessage


# Module-level dataclasses for pickle serialization in roundtrip tests
@dataclass
class _TestToolApprovalRequest:
    """Request data for tool approval in tests."""

    tool_name: str
    arguments: dict[str, Any]
    timestamp: datetime


@dataclass
class _TestExecutorState:
    """Executor state for tests."""

    counter: int
    history: list[str]


@dataclass
class _TestApprovalRequest:
    """Approval request data for tests."""

    action: str
    params: tuple[Any, ...]


@dataclass
class _TestCustomData:
    """Custom data for tests."""

    name: str
    value: int
    tags: list[str]


# region test WorkflowCheckpoint


def test_workflow_checkpoint_default_values():
    checkpoint = WorkflowCheckpoint(workflow_name="test-workflow", graph_signature_hash="test-hash")

    assert checkpoint.checkpoint_id != ""
    assert checkpoint.workflow_name == "test-workflow"
    assert checkpoint.graph_signature_hash == "test-hash"
    assert checkpoint.timestamp != ""
    assert checkpoint.messages == {}
    assert checkpoint.state == {}
    assert checkpoint.pending_request_info_events == {}
    assert checkpoint.iteration_count == 0
    assert checkpoint.metadata == {}
    assert checkpoint.version == "1.0"


def test_workflow_checkpoint_custom_values():
    custom_timestamp = datetime.now(timezone.utc).isoformat()
    checkpoint = WorkflowCheckpoint(
        checkpoint_id="test-checkpoint-123",
        workflow_name="test-workflow-456",
        graph_signature_hash="test-hash-456",
        timestamp=custom_timestamp,
        messages={"executor1": [{"data": "test"}]},  # type: ignore[arg-type, list-item]  # ty: ignore[invalid-argument-type]  # raw dict for serialization test
        pending_request_info_events={"req123": {"data": "test"}},  # type: ignore[arg-type, dict-item]  # ty: ignore[invalid-argument-type]  # raw dict for serialization test
        state={"key": "value"},
        iteration_count=5,
        metadata={"test": True},
        version="2.0",
    )

    assert checkpoint.checkpoint_id == "test-checkpoint-123"
    assert checkpoint.workflow_name == "test-workflow-456"
    assert checkpoint.graph_signature_hash == "test-hash-456"
    assert checkpoint.timestamp == custom_timestamp
    assert checkpoint.messages == {"executor1": [{"data": "test"}]}
    assert checkpoint.state == {"key": "value"}
    assert checkpoint.pending_request_info_events == {"req123": {"data": "test"}}
    assert checkpoint.iteration_count == 5
    assert checkpoint.metadata == {"test": True}
    assert checkpoint.version == "2.0"


def test_workflow_checkpoint_to_dict():
    checkpoint = WorkflowCheckpoint(
        checkpoint_id="test-id",
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        messages={"executor1": [{"data": "test"}]},  # type: ignore[arg-type, list-item]  # ty: ignore[invalid-argument-type]  # raw dict for serialization test
        state={"key": "value"},
        iteration_count=5,
    )

    result = checkpoint.to_dict()

    assert result["checkpoint_id"] == "test-id"
    assert result["workflow_name"] == "test-workflow"
    assert result["graph_signature_hash"] == "test-hash"
    assert result["messages"] == {"executor1": [{"data": "test"}]}
    assert result["state"] == {"key": "value"}
    assert result["iteration_count"] == 5


def test_workflow_checkpoint_previous_checkpoint_id():
    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        previous_checkpoint_id="previous-id-123",
    )

    assert checkpoint.previous_checkpoint_id == "previous-id-123"


# endregion

# region InMemoryCheckpointStorage


def test_checkpoint_storage_protocol_compliance():
    # This test ensures both implementations have all required methods
    memory_storage = InMemoryCheckpointStorage()

    with tempfile.TemporaryDirectory() as temp_dir:
        file_storage = FileCheckpointStorage(temp_dir)

        for storage in [memory_storage, file_storage]:
            # Test that all protocol methods exist and are callable
            assert hasattr(storage, "save")
            assert callable(storage.save)
            assert hasattr(storage, "load")
            assert callable(storage.load)
            assert hasattr(storage, "list_checkpoints")
            assert callable(storage.list_checkpoints)
            assert hasattr(storage, "delete")
            assert callable(storage.delete)
            assert hasattr(storage, "list_checkpoint_ids")
            assert callable(storage.list_checkpoint_ids)
            assert hasattr(storage, "get_latest")
            assert callable(storage.get_latest)


async def test_memory_checkpoint_storage_save_and_load():
    storage = InMemoryCheckpointStorage()
    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        messages={"executor1": [{"data": "hello"}]},  # type: ignore[arg-type, list-item]  # ty: ignore[invalid-argument-type]  # raw dict for serialization test
        pending_request_info_events={"req123": {"data": "test"}},  # type: ignore[arg-type, dict-item]  # ty: ignore[invalid-argument-type]  # raw dict for serialization test
    )

    # Save checkpoint
    saved_id = await storage.save(checkpoint)
    assert saved_id == checkpoint.checkpoint_id

    # Load checkpoint
    loaded_checkpoint = await storage.load(checkpoint.checkpoint_id)
    assert loaded_checkpoint is not None
    assert loaded_checkpoint.checkpoint_id == checkpoint.checkpoint_id
    assert loaded_checkpoint.workflow_name == checkpoint.workflow_name
    assert loaded_checkpoint.graph_signature_hash == checkpoint.graph_signature_hash
    assert loaded_checkpoint.messages == checkpoint.messages
    assert loaded_checkpoint.pending_request_info_events == checkpoint.pending_request_info_events


async def test_memory_checkpoint_storage_load_nonexistent():
    storage = InMemoryCheckpointStorage()

    with pytest.raises(WorkflowCheckpointException):
        await storage.load("nonexistent-id")


async def test_memory_checkpoint_storage_list():
    storage = InMemoryCheckpointStorage()

    # Create checkpoints for different workflows
    checkpoint1 = WorkflowCheckpoint(workflow_name="workflow-1", graph_signature_hash="hash-1")
    checkpoint2 = WorkflowCheckpoint(workflow_name="workflow-1", graph_signature_hash="hash-2")
    checkpoint3 = WorkflowCheckpoint(workflow_name="workflow-2", graph_signature_hash="hash-3")

    await storage.save(checkpoint1)
    await storage.save(checkpoint2)
    await storage.save(checkpoint3)

    # Test list_ids for workflow-1
    workflow1_checkpoint_ids = await storage.list_checkpoint_ids(workflow_name="workflow-1")
    assert len(workflow1_checkpoint_ids) == 2
    assert checkpoint1.checkpoint_id in workflow1_checkpoint_ids
    assert checkpoint2.checkpoint_id in workflow1_checkpoint_ids

    # Test list for workflow-1 (returns objects)
    workflow1_checkpoints = await storage.list_checkpoints(workflow_name="workflow-1")
    assert len(workflow1_checkpoints) == 2
    assert all(isinstance(cp, WorkflowCheckpoint) for cp in workflow1_checkpoints)
    assert {cp.checkpoint_id for cp in workflow1_checkpoints} == {checkpoint1.checkpoint_id, checkpoint2.checkpoint_id}

    # Test list_ids for workflow-2
    workflow2_checkpoint_ids = await storage.list_checkpoint_ids(workflow_name="workflow-2")
    assert len(workflow2_checkpoint_ids) == 1
    assert checkpoint3.checkpoint_id in workflow2_checkpoint_ids

    # Test list for workflow-2 (returns objects)
    workflow2_checkpoints = await storage.list_checkpoints(workflow_name="workflow-2")
    assert len(workflow2_checkpoints) == 1
    assert workflow2_checkpoints[0].checkpoint_id == checkpoint3.checkpoint_id

    # Test list_ids for non-existent workflow
    empty_checkpoint_ids = await storage.list_checkpoint_ids(workflow_name="nonexistent-workflow")
    assert len(empty_checkpoint_ids) == 0

    # Test list for non-existent workflow
    empty_checkpoints = await storage.list_checkpoints(workflow_name="nonexistent-workflow")
    assert len(empty_checkpoints) == 0


async def test_memory_checkpoint_storage_delete():
    storage = InMemoryCheckpointStorage()
    checkpoint = WorkflowCheckpoint(workflow_name="test-workflow", graph_signature_hash="test-hash")

    # Save checkpoint
    await storage.save(checkpoint)
    assert await storage.load(checkpoint.checkpoint_id) is not None

    # Delete checkpoint
    result = await storage.delete(checkpoint.checkpoint_id)
    assert result is True

    # Verify deletion
    with pytest.raises(WorkflowCheckpointException):
        await storage.load(checkpoint.checkpoint_id)

    # Try to delete again
    result = await storage.delete(checkpoint.checkpoint_id)
    assert result is False


async def test_memory_checkpoint_storage_get_latest():
    import asyncio

    storage = InMemoryCheckpointStorage()

    # Create checkpoints with small delays to ensure different timestamps
    checkpoint1 = WorkflowCheckpoint(workflow_name="workflow-1", graph_signature_hash="hash-1")
    await asyncio.sleep(0.01)
    checkpoint2 = WorkflowCheckpoint(workflow_name="workflow-1", graph_signature_hash="hash-2")
    await asyncio.sleep(0.01)
    checkpoint3 = WorkflowCheckpoint(workflow_name="workflow-2", graph_signature_hash="hash-3")

    await storage.save(checkpoint1)
    await storage.save(checkpoint2)
    await storage.save(checkpoint3)

    # Test get_latest for workflow-1
    latest = await storage.get_latest(workflow_name="workflow-1")
    assert latest is not None
    assert latest.checkpoint_id == checkpoint2.checkpoint_id

    # Test get_latest for workflow-2
    latest2 = await storage.get_latest(workflow_name="workflow-2")
    assert latest2 is not None
    assert latest2.checkpoint_id == checkpoint3.checkpoint_id

    # Test get_latest for non-existent workflow
    latest_none = await storage.get_latest(workflow_name="nonexistent-workflow")
    assert latest_none is None


async def test_workflow_checkpoint_chaining_via_previous_checkpoint_id():
    """Test that consecutive checkpoints created by a workflow are properly chained via previous_checkpoint_id."""
    from typing_extensions import Never

    from agent_framework import WorkflowBuilder, WorkflowContext, handler
    from agent_framework._workflows._executor import Executor

    class StartExecutor(Executor):
        @handler
        async def run(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(message, target_id="middle")

    class MiddleExecutor(Executor):
        @handler
        async def process(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(message + "-processed", target_id="finish")

    class FinishExecutor(Executor):
        @handler
        async def finish(self, message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
            await ctx.yield_output(message + "-done")

    storage = InMemoryCheckpointStorage()

    start = StartExecutor(id="start")
    middle = MiddleExecutor(id="middle")
    finish = FinishExecutor(id="finish")

    workflow = (
        WorkflowBuilder(max_iterations=10, start_executor=start, checkpoint_storage=storage)
        .add_edge(start, middle)
        .add_edge(middle, finish)
        .build()
    )

    # Run workflow - this creates checkpoints at each superstep
    _ = [event async for event in workflow.run("hello", stream=True)]

    # Get all checkpoints sorted by timestamp
    checkpoints = sorted(await storage.list_checkpoints(workflow_name=workflow.name), key=lambda c: c.timestamp)

    # Should have multiple checkpoints (one initial + one per superstep)
    assert len(checkpoints) >= 2, f"Expected at least 2 checkpoints, got {len(checkpoints)}"

    # Verify chaining: first checkpoint has no previous
    assert checkpoints[0].previous_checkpoint_id is None

    # Subsequent checkpoints should chain to the previous one
    for i in range(1, len(checkpoints)):
        assert checkpoints[i].previous_checkpoint_id == checkpoints[i - 1].checkpoint_id, (
            f"Checkpoint {i} should chain to checkpoint {i - 1}"
        )


async def test_workflow_checkpoint_ancestry_preserved_after_resume():
    """Resuming from a checkpoint must preserve ancestry: future checkpoints chain back to the resumed one."""
    from typing_extensions import Never

    from agent_framework import WorkflowBuilder, WorkflowContext, handler
    from agent_framework._workflows._executor import Executor

    class StartExecutor(Executor):
        @handler
        async def run(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(message, target_id="middle")

    class MiddleExecutor(Executor):
        @handler
        async def process(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(message + "-processed", target_id="finish")

    class FinishExecutor(Executor):
        @handler
        async def finish(self, message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
            await ctx.yield_output(message + "-done")

    storage = InMemoryCheckpointStorage()

    def _build_workflow() -> Any:
        start = StartExecutor(id="start")
        middle = MiddleExecutor(id="middle")
        finish = FinishExecutor(id="finish")
        return (
            WorkflowBuilder(
                name="resume-ancestry-test",
                max_iterations=10,
                start_executor=start,
                checkpoint_storage=storage,
            )
            .add_edge(start, middle)
            .add_edge(middle, finish)
            .build()
        )

    # First run: produce an initial chain of checkpoints
    workflow = _build_workflow()
    workflow_name = workflow.name
    _ = [event async for event in workflow.run("hello", stream=True)]

    initial_checkpoints = sorted(await storage.list_checkpoints(workflow_name=workflow_name), key=lambda c: c.timestamp)
    assert len(initial_checkpoints) >= 3, (
        f"Need at least 3 initial checkpoints to pick a middle one, got {len(initial_checkpoints)}"
    )
    initial_ids = {cp.checkpoint_id for cp in initial_checkpoints}

    # Pick an intermediate checkpoint to resume from (not the first, not the last)
    resume_from = initial_checkpoints[len(initial_checkpoints) // 2]

    # Resume on a fresh workflow instance (same graph signature) and run to completion
    resumed_workflow = _build_workflow()
    assert resumed_workflow.name == workflow_name
    _ = [event async for event in resumed_workflow.run(checkpoint_id=resume_from.checkpoint_id, stream=True)]

    # Inspect new checkpoints created after resuming
    all_checkpoints = sorted(await storage.list_checkpoints(workflow_name=workflow_name), key=lambda c: c.timestamp)
    new_checkpoints = [cp for cp in all_checkpoints if cp.checkpoint_id not in initial_ids]
    assert new_checkpoints, "Resuming from an intermediate checkpoint should produce new checkpoints"

    # The very first checkpoint created after resuming must chain back to the resumed checkpoint
    assert new_checkpoints[0].previous_checkpoint_id == resume_from.checkpoint_id, (
        "First post-resume checkpoint must chain to the checkpoint that was resumed from; "
        f"got previous_checkpoint_id={new_checkpoints[0].previous_checkpoint_id!r}, "
        f"expected {resume_from.checkpoint_id!r}"
    )

    # Subsequent post-resume checkpoints must continue chaining
    for i in range(1, len(new_checkpoints)):
        assert new_checkpoints[i].previous_checkpoint_id == new_checkpoints[i - 1].checkpoint_id, (
            f"Post-resume checkpoint {i} should chain to checkpoint {i - 1}"
        )

    # Walking the chain backwards from the most recent checkpoint must reach the original root
    # without breaks (i.e. the full ancestry across the resume boundary is intact).
    checkpoints_by_id = {cp.checkpoint_id: cp for cp in all_checkpoints}
    chain: list[str] = []
    cursor: str | None = new_checkpoints[-1].checkpoint_id
    while cursor is not None:
        chain.append(cursor)
        cursor = checkpoints_by_id[cursor].previous_checkpoint_id
    # Chain must include the resumed-from checkpoint and terminate at the original root
    assert resume_from.checkpoint_id in chain
    assert chain[-1] == initial_checkpoints[0].checkpoint_id
    assert checkpoints_by_id[chain[-1]].previous_checkpoint_id is None


async def test_workflow_entry_checkpoint_records_input_and_replays():
    """The entry checkpoint records the run's raw input, enabling a full replay from the start executor.

    The first checkpoint is created before any executor runs and captures the input
    message seeded onto the start executor's internal self-edge. Restoring it on a fresh instance
    re-delivers that input to the start executor, so the entire run - including the start executor -
    replays and produces the same output.
    """
    from typing_extensions import Never

    from agent_framework import WorkflowBuilder, WorkflowContext, handler
    from agent_framework._workflows._const import INTERNAL_SOURCE_ID
    from agent_framework._workflows._executor import Executor

    class StartExecutor(Executor):
        @handler
        async def run(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(message + "-start", target_id="finish")

    class FinishExecutor(Executor):
        @handler
        async def finish(self, message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
            await ctx.yield_output(message + "-done")

    storage = InMemoryCheckpointStorage()

    def _build_workflow() -> Any:
        start = StartExecutor(id="start")
        finish = FinishExecutor(id="finish")
        return (
            WorkflowBuilder(
                name="entry-replay-test",
                max_iterations=10,
                start_executor=start,
                checkpoint_storage=storage,
            )
            .add_edge(start, finish)
            .build()
        )

    # First run.
    workflow = _build_workflow()
    workflow_name = workflow.name
    first_outputs = (await workflow.run("hello")).get_outputs()
    assert first_outputs == ["hello-start-done"]

    # The entry checkpoint is created before any executor runs.
    checkpoints = await storage.list_checkpoints(workflow_name=workflow_name)
    entry = [cp for cp in checkpoints if cp.iteration_count == 0]
    assert len(entry) == 1, "A fresh checkpointed run must create exactly one entry checkpoint at iteration 0"
    entry_cp = entry[0]
    assert entry_cp.previous_checkpoint_id is None

    # The raw input is recorded as an in-flight message on the start executor's internal self-edge.
    seeded = entry_cp.messages.get(INTERNAL_SOURCE_ID("start"))
    assert seeded is not None and len(seeded) == 1, "Entry checkpoint must record the seeded input message"
    assert seeded[0].data == "hello"

    # Restore the entry checkpoint on a fresh instance: the start executor replays from the raw input
    # and the whole run reproduces the original output.
    replay_workflow = _build_workflow()
    replay_outputs = (await replay_workflow.run(checkpoint_id=entry_cp.checkpoint_id)).get_outputs()
    assert replay_outputs == first_outputs


async def test_workflow_one_checkpoint_per_superstep_lineage_and_replay():
    """A checkpointed run yields exactly one checkpoint per superstep plus the entry checkpoint,
    forms a single unbroken lineage, and can be replayed from any pre-terminal checkpoint.

    - Count: checkpoints == (# supersteps) + 1 (the iteration-0 entry checkpoint), with contiguous
      iteration counts ``0..N`` (no gaps or duplicates).
    - Lineage: the entry checkpoint has no parent and every later checkpoint chains to its predecessor.
    - Replay: restoring any non-terminal checkpoint on a fresh instance reproduces the final output.
    """
    from typing_extensions import Never

    from agent_framework import WorkflowBuilder, WorkflowContext, handler
    from agent_framework._workflows._executor import Executor

    class StartExecutor(Executor):
        @handler
        async def run(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(message + "-start", target_id="middle")

    class MiddleExecutor(Executor):
        @handler
        async def process(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(message + "-middle", target_id="finish")

    class FinishExecutor(Executor):
        @handler
        async def finish(self, message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
            await ctx.yield_output(message + "-done")

    storage = InMemoryCheckpointStorage()

    def _build_workflow() -> Any:
        start = StartExecutor(id="start")
        middle = MiddleExecutor(id="middle")
        finish = FinishExecutor(id="finish")
        return (
            WorkflowBuilder(
                name="per-superstep-test",
                max_iterations=10,
                start_executor=start,
                checkpoint_storage=storage,
            )
            .add_edge(start, middle)
            .add_edge(middle, finish)
            .build()
        )

    # First run: count supersteps via the emitted control-plane events.
    workflow = _build_workflow()
    workflow_name = workflow.name
    events = [event async for event in workflow.run("hello", stream=True)]
    first_outputs = [event.data for event in events if event.type == "output"]
    superstep_count = sum(1 for event in events if event.type == "superstep_completed")
    assert first_outputs == ["hello-start-middle-done"]
    assert superstep_count == 3, "start -> middle -> finish converges in three supersteps"

    checkpoints = sorted(
        await storage.list_checkpoints(workflow_name=workflow_name),
        key=lambda c: c.iteration_count,
    )

    # Count: one checkpoint per superstep plus the entry checkpoint, with contiguous iteration counts.
    assert len(checkpoints) == superstep_count + 1
    assert [cp.iteration_count for cp in checkpoints] == list(range(superstep_count + 1))

    # Lineage: the entry checkpoint has no parent; every later checkpoint chains to its predecessor.
    assert checkpoints[0].previous_checkpoint_id is None
    for prev, cur in zip(checkpoints, checkpoints[1:]):
        assert cur.previous_checkpoint_id == prev.checkpoint_id, (
            f"Checkpoint at iteration {cur.iteration_count} must chain to iteration {prev.iteration_count}"
        )

    # Replay: restoring any non-terminal checkpoint reproduces the final output. The terminal
    # checkpoint (highest iteration) is the converged state with no work left, so it is excluded.
    for cp in checkpoints[:-1]:
        replay_workflow = _build_workflow()
        replay_outputs = (await replay_workflow.run(checkpoint_id=cp.checkpoint_id)).get_outputs()
        assert replay_outputs == first_outputs, (
            f"Replay from the checkpoint at iteration {cp.iteration_count} must reproduce the final output"
        )


async def test_workflow_response_entry_checkpoint_records_response_and_replays():
    """Delivering responses records a response-entry checkpoint that captures the responses in-flight,
    making a human-in-the-loop continuation fully replayable.

    The response-entry checkpoint is created before the runner processes the responses. It sits at
    the same iteration as the pending-request (IDLE) checkpoint but is a distinct checkpoint that
    chains from it and carries the delivered response as an in-flight message (with no pending
    requests). Resuming from it on a fresh instance re-delivers the response and reproduces the output.
    """
    from typing_extensions import Never

    from agent_framework import WorkflowBuilder, WorkflowContext, WorkflowRunState, handler, response_handler
    from agent_framework._workflows._executor import Executor
    from agent_framework._workflows._request_info_mixin import RequestInfoMixin

    class HilExecutor(Executor, RequestInfoMixin):
        @handler
        async def start(self, message: str, ctx: WorkflowContext) -> None:
            await ctx.request_info(message, response_type=str, request_id="req1")

        @response_handler
        async def on_response(
            self,
            original_request: str,
            response: str,
            ctx: WorkflowContext[Never, str],  # type: ignore[valid-type]
        ) -> None:
            await ctx.yield_output(f"{original_request}->{response}")

    storage = InMemoryCheckpointStorage()

    def _build_workflow() -> Any:
        hil = HilExecutor(id="hil")
        return WorkflowBuilder(
            name="response-entry-test",
            max_iterations=10,
            start_executor=hil,
            checkpoint_storage=storage,
        ).build()

    # First run: pauses at IDLE_WITH_PENDING_REQUESTS awaiting the response.
    workflow = _build_workflow()
    workflow_name = workflow.name
    result = await workflow.run("approve")
    request_events = result.get_request_info_events()
    assert len(request_events) == 1
    request_id = request_events[0].request_id
    assert result.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS

    checkpoints_before = await storage.list_checkpoints(workflow_name=workflow_name)
    before_ids = {cp.checkpoint_id for cp in checkpoints_before}
    # The last checkpoint before responding sits at the pending-request boundary and records the request.
    pending_cp = max(checkpoints_before, key=lambda c: c.iteration_count)
    assert pending_cp.pending_request_info_events

    # Deliver the response; the workflow completes.
    final = await workflow.run(responses={request_id: "yes"})
    assert final.get_outputs() == ["approve->yes"]

    checkpoints_after = await storage.list_checkpoints(workflow_name=workflow_name)
    new_checkpoints = [cp for cp in checkpoints_after if cp.checkpoint_id not in before_ids]

    # The response-entry checkpoint sits at the SAME iteration as the pending-request checkpoint,
    # chains from it, has no pending requests (they were answered), and records the response in-flight.
    response_entry = next(cp for cp in new_checkpoints if cp.iteration_count == pending_cp.iteration_count)
    assert response_entry.checkpoint_id != pending_cp.checkpoint_id
    assert response_entry.previous_checkpoint_id == pending_cp.checkpoint_id
    assert not response_entry.pending_request_info_events
    assert response_entry.messages, "Response-entry checkpoint must record the delivered response in-flight"

    # Resuming from the response-entry checkpoint replays the continuation and reproduces the output.
    replay_workflow = _build_workflow()
    replay_outputs = (await replay_workflow.run(checkpoint_id=response_entry.checkpoint_id)).get_outputs()
    assert replay_outputs == ["approve->yes"]


async def test_memory_checkpoint_storage_roundtrip_json_native_types():
    """Test that JSON-native types (str, int, float, bool, None) roundtrip correctly."""
    storage = InMemoryCheckpointStorage()

    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        state={
            "string": "hello world",
            "integer": 42,
            "negative_int": -100,
            "float": 3.14159,
            "negative_float": -2.71828,
            "bool_true": True,
            "bool_false": False,
            "null_value": None,
            "zero": 0,
            "empty_string": "",
        },
    )

    await storage.save(checkpoint)
    loaded = await storage.load(checkpoint.checkpoint_id)

    assert loaded.state == checkpoint.state


async def test_memory_checkpoint_storage_roundtrip_datetime():
    """Test that datetime objects roundtrip correctly."""
    storage = InMemoryCheckpointStorage()

    now = datetime.now(timezone.utc)
    specific_datetime = datetime(2025, 6, 15, 10, 30, 45, 123456, tzinfo=timezone.utc)

    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        state={
            "current_time": now,
            "specific_time": specific_datetime,
            "nested": {"created_at": now, "updated_at": specific_datetime},
        },
    )

    await storage.save(checkpoint)
    loaded = await storage.load(checkpoint.checkpoint_id)

    assert loaded.state["current_time"] == now
    assert loaded.state["specific_time"] == specific_datetime
    assert loaded.state["nested"]["created_at"] == now
    assert loaded.state["nested"]["updated_at"] == specific_datetime


async def test_memory_checkpoint_storage_roundtrip_dataclass():
    """Test that dataclass objects roundtrip correctly."""
    storage = InMemoryCheckpointStorage()

    custom_obj = _TestCustomData(name="test", value=42, tags=["a", "b", "c"])

    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        state={
            "custom_data": custom_obj,
            "nested": {"inner_data": custom_obj},
        },
    )

    await storage.save(checkpoint)
    loaded = await storage.load(checkpoint.checkpoint_id)

    assert loaded.state["custom_data"] == custom_obj
    assert loaded.state["custom_data"].name == "test"
    assert loaded.state["custom_data"].value == 42
    assert loaded.state["custom_data"].tags == ["a", "b", "c"]
    assert loaded.state["nested"]["inner_data"] == custom_obj
    assert isinstance(loaded.state["custom_data"], _TestCustomData)


async def test_memory_checkpoint_storage_roundtrip_tuple_and_set():
    """Test that tuples and frozensets roundtrip correctly (type preserved in memory)."""
    storage = InMemoryCheckpointStorage()

    original_tuple = (1, "two", 3.0, None)
    original_frozenset = frozenset({1, 2, 3})

    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        state={
            "my_tuple": original_tuple,
            "my_frozenset": original_frozenset,
            "nested_tuple": {"inner": (10, 20, 30)},
        },
    )

    await storage.save(checkpoint)
    loaded = await storage.load(checkpoint.checkpoint_id)

    # In-memory storage preserves exact types (no JSON serialization)
    assert loaded.state["my_tuple"] == original_tuple
    assert isinstance(loaded.state["my_tuple"], tuple)
    assert loaded.state["my_frozenset"] == original_frozenset
    assert isinstance(loaded.state["my_frozenset"], frozenset)
    assert loaded.state["nested_tuple"]["inner"] == (10, 20, 30)
    assert isinstance(loaded.state["nested_tuple"]["inner"], tuple)


async def test_memory_checkpoint_storage_roundtrip_complex_nested_structures():
    """Test complex nested structures with mixed types roundtrip correctly."""
    storage = InMemoryCheckpointStorage()

    # Create complex nested structure mixing JSON-native and non-native types
    complex_state = {
        "level1": {
            "level2": {
                "level3": {
                    "deep_string": "hello",
                    "deep_int": 123,
                    "deep_datetime": datetime(2025, 1, 1, tzinfo=timezone.utc),
                    "deep_tuple": (1, 2, 3),
                }
            },
            "list_of_dicts": [
                {"a": 1, "b": datetime(2025, 2, 1, tzinfo=timezone.utc)},
                {"c": 2, "d": (4, 5, 6)},
            ],
        },
        "mixed_list": [
            "string",
            42,
            3.14,
            True,
            None,
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            (7, 8, 9),
        ],
    }

    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        state=complex_state,
    )

    await storage.save(checkpoint)
    loaded = await storage.load(checkpoint.checkpoint_id)

    # Verify deep nested values
    assert loaded.state["level1"]["level2"]["level3"]["deep_string"] == "hello"
    assert loaded.state["level1"]["level2"]["level3"]["deep_int"] == 123
    assert loaded.state["level1"]["level2"]["level3"]["deep_datetime"] == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert loaded.state["level1"]["level2"]["level3"]["deep_tuple"] == (1, 2, 3)
    assert isinstance(loaded.state["level1"]["level2"]["level3"]["deep_tuple"], tuple)

    # Verify list of dicts
    assert loaded.state["level1"]["list_of_dicts"][0]["a"] == 1
    assert loaded.state["level1"]["list_of_dicts"][0]["b"] == datetime(2025, 2, 1, tzinfo=timezone.utc)
    assert loaded.state["level1"]["list_of_dicts"][1]["d"] == (4, 5, 6)
    assert isinstance(loaded.state["level1"]["list_of_dicts"][1]["d"], tuple)

    # Verify mixed list with correct types
    assert loaded.state["mixed_list"][0] == "string"
    assert loaded.state["mixed_list"][1] == 42
    assert loaded.state["mixed_list"][5] == datetime(2025, 3, 1, tzinfo=timezone.utc)
    assert loaded.state["mixed_list"][6] == (7, 8, 9)
    assert isinstance(loaded.state["mixed_list"][6], tuple)


async def test_memory_checkpoint_storage_roundtrip_messages_with_complex_data():
    """Test that messages dict with Message objects roundtrips correctly."""
    storage = InMemoryCheckpointStorage()

    msg1 = WorkflowMessage(
        data={"text": "hello", "timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc)},
        source_id="source",
        target_id="target",
    )
    msg2 = WorkflowMessage(
        data=(1, 2, 3),
        source_id="s2",
        target_id=None,
    )
    msg3 = WorkflowMessage(
        data="simple string",
        source_id="s3",
        target_id="t3",
    )

    messages = {
        "executor1": [msg1, msg2],
        "executor2": [msg3],
    }

    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        messages=messages,
    )

    await storage.save(checkpoint)
    loaded = await storage.load(checkpoint.checkpoint_id)

    # Verify messages structure and types
    assert len(loaded.messages["executor1"]) == 2
    loaded_msg1 = loaded.messages["executor1"][0]
    loaded_msg2 = loaded.messages["executor1"][1]
    loaded_msg3 = loaded.messages["executor2"][0]

    # Verify Message type is preserved
    assert isinstance(loaded_msg1, WorkflowMessage)
    assert isinstance(loaded_msg2, WorkflowMessage)
    assert isinstance(loaded_msg3, WorkflowMessage)

    # Verify Message fields
    assert loaded_msg1.data["text"] == "hello"
    assert loaded_msg1.data["timestamp"] == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert loaded_msg1.source_id == "source"
    assert loaded_msg1.target_id == "target"

    assert loaded_msg2.data == (1, 2, 3)
    assert isinstance(loaded_msg2.data, tuple)
    assert loaded_msg2.source_id == "s2"
    assert loaded_msg2.target_id is None

    assert loaded_msg3.data == "simple string"
    assert loaded_msg3.source_id == "s3"
    assert loaded_msg3.target_id == "t3"


async def test_memory_checkpoint_storage_roundtrip_pending_request_info_events():
    """Test that pending_request_info_events with WorkflowEvent objects roundtrip correctly."""
    storage = InMemoryCheckpointStorage()

    # Create request_info events using the proper WorkflowEvent factory
    event1 = WorkflowEvent.request_info(
        request_id="req123",
        source_executor_id="executor1",
        request_data="What is your name?",
        response_type=str,
    )
    event2 = WorkflowEvent.request_info(
        request_id="req456",
        source_executor_id="executor2",
        request_data=_TestToolApprovalRequest(
            tool_name="search",
            arguments={"query": "test"},
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        response_type=bool,
    )

    pending_events = {
        "req123": event1,
        "req456": event2,
    }

    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        pending_request_info_events=pending_events,  # type: ignore[arg-type]
    )

    await storage.save(checkpoint)
    loaded = await storage.load(checkpoint.checkpoint_id)

    # Verify WorkflowEvent type is preserved
    loaded_event1 = loaded.pending_request_info_events["req123"]
    loaded_event2 = loaded.pending_request_info_events["req456"]

    assert isinstance(loaded_event1, WorkflowEvent)
    assert isinstance(loaded_event2, WorkflowEvent)

    # Verify event1 fields
    assert loaded_event1.type == "request_info"
    assert loaded_event1.request_id == "req123"
    assert loaded_event1.source_executor_id == "executor1"
    assert loaded_event1.data == "What is your name?"
    assert loaded_event1.response_type is str

    # Verify event2 fields with complex data
    assert loaded_event2.type == "request_info"
    assert loaded_event2.request_id == "req456"
    assert loaded_event2.source_executor_id == "executor2"
    assert isinstance(loaded_event2.data, _TestToolApprovalRequest)
    assert loaded_event2.data.tool_name == "search"
    assert loaded_event2.data.arguments == {"query": "test"}
    assert loaded_event2.data.timestamp == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert loaded_event2.response_type is bool


async def test_memory_checkpoint_storage_roundtrip_full_checkpoint():
    """Test complete WorkflowCheckpoint roundtrip with all fields populated using proper types."""
    storage = InMemoryCheckpointStorage()

    # Create proper WorkflowMessage objects
    msg1 = WorkflowMessage(data="msg1", source_id="s", target_id="t")
    msg2 = WorkflowMessage(data=datetime(2025, 1, 1, tzinfo=timezone.utc), source_id="a", target_id="b")

    # Create proper WorkflowEvent for pending request
    pending_event = WorkflowEvent.request_info(
        request_id="req1",
        source_executor_id="exec1",
        request_data=_TestApprovalRequest(action="approve", params=(1, 2, 3)),
        response_type=bool,
    )

    checkpoint = WorkflowCheckpoint(
        checkpoint_id="full-test-checkpoint",
        workflow_name="comprehensive-test",
        graph_signature_hash="hash-abc123",
        previous_checkpoint_id="previous-checkpoint-id",
        timestamp=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        messages={
            "exec1": [msg1],
            "exec2": [msg2],
        },
        state={
            "user_data": {"name": "test", "created": datetime(2025, 1, 1, tzinfo=timezone.utc)},
            "_executor_state": {
                "exec1": _TestExecutorState(counter=5, history=["a", "b", "c"]),
            },
        },
        pending_request_info_events={
            "req1": pending_event,
        },
        iteration_count=10,
        metadata={
            "superstep": 5,
            "started_at": datetime(2025, 6, 15, 11, 0, 0, tzinfo=timezone.utc),
        },
        version="1.0",
    )

    await storage.save(checkpoint)
    loaded = await storage.load(checkpoint.checkpoint_id)

    # Verify all scalar fields
    assert loaded.checkpoint_id == checkpoint.checkpoint_id
    assert loaded.workflow_name == checkpoint.workflow_name
    assert loaded.graph_signature_hash == checkpoint.graph_signature_hash
    assert loaded.previous_checkpoint_id == checkpoint.previous_checkpoint_id
    assert loaded.timestamp == checkpoint.timestamp
    assert loaded.iteration_count == checkpoint.iteration_count
    assert loaded.version == checkpoint.version

    # Verify complex nested state data
    assert loaded.state["user_data"]["created"] == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert loaded.state["_executor_state"]["exec1"].counter == 5
    assert loaded.state["_executor_state"]["exec1"].history == ["a", "b", "c"]
    assert isinstance(loaded.state["_executor_state"]["exec1"], _TestExecutorState)

    # Verify messages are proper Message objects
    loaded_msg1 = loaded.messages["exec1"][0]
    loaded_msg2 = loaded.messages["exec2"][0]
    assert isinstance(loaded_msg1, WorkflowMessage)
    assert isinstance(loaded_msg2, WorkflowMessage)
    assert loaded_msg1.data == "msg1"
    assert loaded_msg1.source_id == "s"
    assert loaded_msg2.data == datetime(2025, 1, 1, tzinfo=timezone.utc)

    # Verify pending events are proper WorkflowEvent objects
    loaded_event = loaded.pending_request_info_events["req1"]
    assert isinstance(loaded_event, WorkflowEvent)
    assert loaded_event.type == "request_info"
    assert loaded_event.request_id == "req1"
    assert isinstance(loaded_event.data, _TestApprovalRequest)
    assert loaded_event.data.params == (1, 2, 3)

    # Verify metadata
    assert loaded.metadata["superstep"] == 5
    assert loaded.metadata["started_at"] == datetime(2025, 6, 15, 11, 0, 0, tzinfo=timezone.utc)


async def test_memory_checkpoint_storage_roundtrip_bytes():
    """Test that bytes objects roundtrip correctly."""
    storage = InMemoryCheckpointStorage()

    binary_data = b"\x00\x01\x02\xff\xfe\xfd"
    unicode_bytes = "Hello 世界".encode()

    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        state={
            "binary_data": binary_data,
            "unicode_bytes": unicode_bytes,
            "nested": {"inner_bytes": binary_data},
        },
    )

    await storage.save(checkpoint)
    loaded = await storage.load(checkpoint.checkpoint_id)

    assert loaded.state["binary_data"] == binary_data
    assert loaded.state["unicode_bytes"] == unicode_bytes
    assert loaded.state["nested"]["inner_bytes"] == binary_data
    assert isinstance(loaded.state["binary_data"], bytes)


async def test_memory_checkpoint_storage_roundtrip_empty_collections():
    """Test that empty collections roundtrip correctly (types preserved in memory)."""
    storage = InMemoryCheckpointStorage()

    checkpoint = WorkflowCheckpoint(
        workflow_name="test-workflow",
        graph_signature_hash="test-hash",
        state={
            "empty_dict": {},
            "empty_list": [],
            "empty_tuple": (),
            "nested_empty": {"inner_dict": {}, "inner_list": []},
        },
        messages={},
        pending_request_info_events={},
    )

    await storage.save(checkpoint)
    loaded = await storage.load(checkpoint.checkpoint_id)

    assert loaded.state["empty_dict"] == {}
    assert loaded.state["empty_list"] == []
    # In-memory storage preserves exact types (no JSON serialization)
    assert loaded.state["empty_tuple"] == ()
    assert isinstance(loaded.state["empty_tuple"], tuple)
    assert loaded.state["nested_empty"]["inner_dict"] == {}
    assert loaded.messages == {}
    assert loaded.pending_request_info_events == {}


# endregion

# region FileCheckpointStorage


async def test_file_checkpoint_storage_save_and_load():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            messages={"executor1": [{"data": "hello", "source_id": "test", "target_id": None}]},  # type: ignore[arg-type, list-item]  # ty: ignore[invalid-argument-type]  # raw dict for serialization test
            state={"key": "value"},
            pending_request_info_events={"req123": {"data": "test"}},  # type: ignore[arg-type, dict-item]  # ty: ignore[invalid-argument-type]  # raw dict for serialization test
        )

        # Save checkpoint
        saved_id = await storage.save(checkpoint)
        assert saved_id == checkpoint.checkpoint_id

        # Verify file was created
        file_path = Path(temp_dir) / f"{checkpoint.checkpoint_id}.json"
        assert file_path.exists()

        # Load checkpoint
        loaded_checkpoint = await storage.load(checkpoint.checkpoint_id)
        assert loaded_checkpoint is not None
        assert loaded_checkpoint.checkpoint_id == checkpoint.checkpoint_id
        assert loaded_checkpoint.workflow_name == checkpoint.workflow_name
        assert loaded_checkpoint.graph_signature_hash == checkpoint.graph_signature_hash
        assert loaded_checkpoint.messages == checkpoint.messages
        assert loaded_checkpoint.state == checkpoint.state
        assert loaded_checkpoint.pending_request_info_events == checkpoint.pending_request_info_events


async def test_file_checkpoint_storage_concurrent_saves_same_id():
    """Concurrent saves of the same checkpoint ID must not fail on a shared temp path.

    Regression for https://github.com/microsoft/agent-framework/issues/7748:
    FileCheckpointStorage.save() used a fixed `<id>.json.tmp` temp path, so concurrent
    saves raced on it (one rename removed it before another's rename). Uses enough
    concurrent saves to reliably trip the race on the unfixed code.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            checkpoint_id="shared-id",
        )

        results = await asyncio.gather(*(storage.save(checkpoint) for _ in range(50)), return_exceptions=True)

        errors = [r for r in results if isinstance(r, BaseException)]
        assert not errors, f"concurrent saves raised internal filesystem errors: {errors[:1]!r}"
        assert all(r == "shared-id" for r in results)
        # One of the saves won; the destination is intact and parseable, not corrupted or truncated.
        assert (Path(temp_dir) / "shared-id.json").exists()
        loaded = await storage.load("shared-id")
        assert loaded.checkpoint_id == checkpoint.checkpoint_id
        assert loaded.workflow_name == checkpoint.workflow_name
        assert loaded.graph_signature_hash == checkpoint.graph_signature_hash


async def test_file_checkpoint_storage_destination_queue_registry_released():
    """The destination registry must be empty again once nothing is queued or running.

    Reviewer concern on #7757: the previous design kept a process-wide dict of
    `threading.Lock` keyed by destination path and never removed an entry. Because
    `WorkflowCheckpoint` generates a fresh UUID by default, every save retained one
    entry for the lifetime of the process. Entries are now reference-counted by
    queued-or-running operations and dropped by the last release, so repeated saves of
    one ID and saves of many distinct IDs both settle back to nothing held.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        from agent_framework._workflows import _checkpoint as checkpoint_module

        registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]
        baseline = len(registry)

        for _ in range(20):
            await storage.save(
                WorkflowCheckpoint(
                    workflow_name="test-workflow",
                    graph_signature_hash="test-hash",
                    checkpoint_id="shared-id",
                )
            )
        assert len(registry) == baseline, "same-ID saves left an entry behind"

        # The default: every checkpoint gets its own UUID, so each save is a distinct
        # destination. This is the case that grew without bound before.
        for _ in range(20):
            await storage.save(WorkflowCheckpoint(workflow_name="test-workflow", graph_signature_hash="test-hash"))
        assert len(registry) == baseline, "distinct-ID saves leaked registry entries"

        # Concurrent same-path saves share one entry while queued, and release it.
        await asyncio.gather(
            *(
                storage.save(
                    WorkflowCheckpoint(
                        workflow_name="test-workflow",
                        graph_signature_hash="test-hash",
                        checkpoint_id="concurrent-id",
                    )
                )
                for _ in range(8)
            )
        )
        assert len(registry) == baseline, "concurrent saves left an entry behind"


async def test_file_checkpoint_storage_concurrent_saves_across_instances():
    """Two FileCheckpointStorage instances to the same directory must serialize same-ID saves.

    Companion regression for a reviewer concern raised while fixing #7748: the
    previous per-instance, per-event-loop lock registry did not span a second
    FileCheckpointStorage instance pointed at the same directory, so concurrent
    saves could still reach os.replace together and trip the Windows PermissionError
    race. The fix switched to a process-wide, per-destination threading.Lock
    keyed by canonical path. Both instances must complete all saves without
    surfacing filesystem errors.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        storage_a = FileCheckpointStorage(temp_dir)
        storage_b = FileCheckpointStorage(temp_dir)
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            checkpoint_id="shared-id",
        )

        results = await asyncio.gather(
            *[storage_a.save(checkpoint) for _ in range(25)],
            *[storage_b.save(checkpoint) for _ in range(25)],
            return_exceptions=True,
        )

        errors = [r for r in results if isinstance(r, BaseException)]
        assert not errors, f"cross-instance concurrent saves raised: {errors[:1]!r}"
        assert all(r == "shared-id" for r in results)
        assert (Path(temp_dir) / "shared-id.json").exists()

        loaded = await storage_a.load("shared-id")
        assert loaded.checkpoint_id == checkpoint.checkpoint_id
        assert loaded.workflow_name == checkpoint.workflow_name


async def test_file_checkpoint_storage_cancel_drains_before_releasing(monkeypatch):
    """A cancelled save must not release the destination while its write is in flight.

    Reviewer concern on #7757: shielding alone let the caller observe `CancelledError`
    while the worker kept running, so a later save on another loop could take the
    destination, complete, and then be overwritten when the cancelled worker finally
    ran its `os.replace`. The cancellation path now drains the worker before
    propagating, which means the cancelled caller does not return until its own write
    has finished -- so nothing it wrote can land after a later save.
    """
    import threading

    from agent_framework._workflows import _checkpoint as checkpoint_module

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        real_replace = checkpoint_module.os.replace
        replace_started = threading.Event()
        release_first_replace = threading.Event()
        # `_replace_with_retry` may call os.replace more than once for a single write, so
        # count completed writes rather than attempts.
        attempts = 0
        replace_calls: list[str] = []
        calls_guard = threading.Lock()

        def gated_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
            nonlocal attempts
            with calls_guard:
                attempts += 1
                first = attempts == 1
            if first:
                replace_started.set()
                assert release_first_replace.wait(timeout=10)
            real_replace(src, dst)
            with calls_guard:
                replace_calls.append(os.path.basename(str(dst)))

        monkeypatch.setattr(checkpoint_module.os, "replace", gated_replace)

        def make(name: str) -> WorkflowCheckpoint:
            return WorkflowCheckpoint(workflow_name=name, graph_signature_hash="test-hash", checkpoint_id="shared-id")

        task_a = asyncio.create_task(storage.save(make("workflow-a")))
        assert await asyncio.to_thread(replace_started.wait, 10), "save A never reached os.replace"

        task_a.cancel()
        # The drain is the point: A must still be running, holding the destination,
        # because its own worker has not finished.
        for _ in range(20):
            await asyncio.sleep(0.01)
            if task_a.done():
                break
        assert not task_a.done(), "cancelled save returned while its write was still in flight"

        # A later save cannot take the destination while A is draining.
        task_b = asyncio.create_task(storage.save(make("workflow-b")))
        for _ in range(20):
            await asyncio.sleep(0.01)
            assert attempts == 1, "save B submitted a write while A was still draining"
        assert not task_b.done()

        release_first_replace.set()
        with pytest.raises(asyncio.CancelledError):
            await task_a
        await asyncio.wait_for(task_b, timeout=10)

        assert len(replace_calls) == 2
        # B ran second, so B's data is what survives.
        assert (await storage.load("shared-id")).workflow_name == "workflow-b"


async def test_file_checkpoint_storage_load_nonexistent():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        with pytest.raises(WorkflowCheckpointException):
            await storage.load("nonexistent-id")


async def test_file_checkpoint_storage_list():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create checkpoints for different workflows
        checkpoint1 = WorkflowCheckpoint(workflow_name="workflow-1", graph_signature_hash="hash-1")
        checkpoint2 = WorkflowCheckpoint(workflow_name="workflow-1", graph_signature_hash="hash-2")
        checkpoint3 = WorkflowCheckpoint(workflow_name="workflow-2", graph_signature_hash="hash-3")

        await storage.save(checkpoint1)
        await storage.save(checkpoint2)
        await storage.save(checkpoint3)

        # Test list_ids for workflow-1
        workflow1_checkpoint_ids = await storage.list_checkpoint_ids(workflow_name="workflow-1")
        assert len(workflow1_checkpoint_ids) == 2
        assert checkpoint1.checkpoint_id in workflow1_checkpoint_ids
        assert checkpoint2.checkpoint_id in workflow1_checkpoint_ids

        # Test list for workflow-1 (returns objects)
        workflow1_checkpoints = await storage.list_checkpoints(workflow_name="workflow-1")
        assert len(workflow1_checkpoints) == 2
        assert all(isinstance(cp, WorkflowCheckpoint) for cp in workflow1_checkpoints)
        checkpoint_ids = {cp.checkpoint_id for cp in workflow1_checkpoints}
        assert checkpoint_ids == {checkpoint1.checkpoint_id, checkpoint2.checkpoint_id}

        # Test list_ids for workflow-2
        workflow2_checkpoint_ids = await storage.list_checkpoint_ids(workflow_name="workflow-2")
        assert len(workflow2_checkpoint_ids) == 1
        assert checkpoint3.checkpoint_id in workflow2_checkpoint_ids

        # Test list for workflow-2 (returns objects)
        workflow2_checkpoints = await storage.list_checkpoints(workflow_name="workflow-2")
        assert len(workflow2_checkpoints) == 1
        assert workflow2_checkpoints[0].checkpoint_id == checkpoint3.checkpoint_id


async def test_file_checkpoint_storage_delete():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)
        checkpoint = WorkflowCheckpoint(workflow_name="test-workflow", graph_signature_hash="test-hash")

        # Save checkpoint
        await storage.save(checkpoint)
        file_path = Path(temp_dir) / f"{checkpoint.checkpoint_id}.json"
        assert file_path.exists()

        # Delete checkpoint
        result = await storage.delete(checkpoint.checkpoint_id)
        assert result is True
        assert not file_path.exists()

        # Try to delete again
        result = await storage.delete(checkpoint.checkpoint_id)
        assert result is False


async def test_file_checkpoint_storage_directory_creation():
    with tempfile.TemporaryDirectory() as temp_dir:
        nested_path = Path(temp_dir) / "nested" / "checkpoint" / "storage"
        storage = FileCheckpointStorage(nested_path)

        # Directory should be created
        assert nested_path.exists()
        assert nested_path.is_dir()

        # Should be able to save checkpoints
        checkpoint = WorkflowCheckpoint(workflow_name="test-workflow", graph_signature_hash="test-hash")
        await storage.save(checkpoint)

        file_path = nested_path / f"{checkpoint.checkpoint_id}.json"
        assert file_path.exists()


async def test_file_checkpoint_storage_corrupted_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create a corrupted JSON file
        corrupted_file = Path(temp_dir) / "corrupted.json"
        with open(corrupted_file, "w") as f:  # noqa: ASYNC230
            f.write("{ invalid json }")

        # list should handle the corrupted file gracefully
        checkpoints = await storage.list_checkpoints(workflow_name="any-workflow")
        assert checkpoints == []


async def test_file_checkpoint_storage_json_serialization():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create checkpoint with complex nested data
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            messages={"executor1": [{"data": {"nested": {"value": 42}}, "source_id": "test", "target_id": None}]},  # type: ignore[arg-type, list-item]  # ty: ignore[invalid-argument-type]  # raw dict for serialization test
            state={"list": [1, 2, 3], "dict": {"a": "b", "c": {"d": "e"}}, "bool": True, "null": None},
            pending_request_info_events={"req123": {"data": "test"}},  # type: ignore[arg-type, dict-item]  # ty: ignore[invalid-argument-type]  # raw dict for serialization test
        )

        # Save and load
        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        assert loaded is not None
        assert loaded.messages == checkpoint.messages
        assert loaded.state == checkpoint.state

        # Verify the JSON file is properly formatted
        file_path = Path(temp_dir) / f"{checkpoint.checkpoint_id}.json"
        with open(file_path) as f:  # noqa: ASYNC230
            data = json.load(f)

        assert data["messages"]["executor1"][0]["data"]["nested"]["value"] == 42
        assert data["state"]["list"] == [1, 2, 3]
        assert data["state"]["bool"] is True
        assert data["state"]["null"] is None
        assert data["pending_request_info_events"]["req123"]["data"] == "test"


async def test_file_checkpoint_storage_get_latest():
    import asyncio

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create checkpoints with small delays to ensure different timestamps
        checkpoint1 = WorkflowCheckpoint(workflow_name="workflow-1", graph_signature_hash="hash-1")
        await asyncio.sleep(0.01)
        checkpoint2 = WorkflowCheckpoint(workflow_name="workflow-1", graph_signature_hash="hash-2")
        await asyncio.sleep(0.01)
        checkpoint3 = WorkflowCheckpoint(workflow_name="workflow-2", graph_signature_hash="hash-3")

        await storage.save(checkpoint1)
        await storage.save(checkpoint2)
        await storage.save(checkpoint3)

        # Test get_latest for workflow-1
        latest = await storage.get_latest(workflow_name="workflow-1")
        assert latest is not None
        assert latest.checkpoint_id == checkpoint2.checkpoint_id

        # Test get_latest for workflow-2
        latest2 = await storage.get_latest(workflow_name="workflow-2")
        assert latest2 is not None
        assert latest2.checkpoint_id == checkpoint3.checkpoint_id

        # Test get_latest for non-existent workflow
        latest_none = await storage.get_latest(workflow_name="nonexistent-workflow")
        assert latest_none is None


async def test_file_checkpoint_storage_list_ids_corrupted_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create a valid checkpoint first
        checkpoint = WorkflowCheckpoint(workflow_name="test-workflow", graph_signature_hash="test-hash")
        await storage.save(checkpoint)

        # Create a corrupted JSON file
        corrupted_file = Path(temp_dir) / "corrupted.json"
        with open(corrupted_file, "w") as f:  # noqa: ASYNC230
            f.write("{ invalid json }")

        # list_ids should handle the corrupted file gracefully
        checkpoint_ids = await storage.list_checkpoint_ids(workflow_name="test-workflow")
        assert len(checkpoint_ids) == 1
        assert checkpoint.checkpoint_id in checkpoint_ids


async def test_file_checkpoint_storage_list_ids_empty():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Test list_ids on empty storage
        checkpoint_ids = await storage.list_checkpoint_ids(workflow_name="any-workflow")
        assert checkpoint_ids == []


async def test_file_checkpoint_storage_roundtrip_json_native_types():
    """Test that JSON-native types (str, int, float, bool, None) roundtrip correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={
                "string": "hello world",
                "integer": 42,
                "negative_int": -100,
                "float": 3.14159,
                "negative_float": -2.71828,
                "bool_true": True,
                "bool_false": False,
                "null_value": None,
                "zero": 0,
                "empty_string": "",
            },
        )

        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        assert loaded.state == checkpoint.state


async def test_file_checkpoint_storage_roundtrip_datetime():
    """Test that datetime objects roundtrip correctly via pickle encoding."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        now = datetime.now(timezone.utc)
        specific_datetime = datetime(2025, 6, 15, 10, 30, 45, 123456, tzinfo=timezone.utc)

        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={
                "current_time": now,
                "specific_time": specific_datetime,
                "nested": {"created_at": now, "updated_at": specific_datetime},
            },
        )

        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        assert loaded.state["current_time"] == now
        assert loaded.state["specific_time"] == specific_datetime
        assert loaded.state["nested"]["created_at"] == now
        assert loaded.state["nested"]["updated_at"] == specific_datetime


async def test_file_checkpoint_storage_roundtrip_dataclass():
    """Test that dataclass objects roundtrip correctly via pickle encoding."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(
            temp_dir,
            allowed_checkpoint_types=["tests.workflow.test_checkpoint:_TestCustomData"],
        )

        custom_obj = _TestCustomData(name="test", value=42, tags=["a", "b", "c"])

        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={
                "custom_data": custom_obj,
                "nested": {"inner_data": custom_obj},
            },
        )

        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        assert loaded.state["custom_data"] == custom_obj
        assert loaded.state["custom_data"].name == "test"
        assert loaded.state["custom_data"].value == 42
        assert loaded.state["custom_data"].tags == ["a", "b", "c"]
        assert loaded.state["nested"]["inner_data"] == custom_obj
        assert isinstance(loaded.state["custom_data"], _TestCustomData)


async def test_file_checkpoint_storage_roundtrip_tuple_and_set():
    """Test tuple/frozenset encoding behavior.

    Tuples, sets, and frozensets are pickled to preserve their type through
    the encode/decode roundtrip.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        original_tuple = (1, "two", 3.0, None)
        original_frozenset = frozenset({1, 2, 3})

        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={
                "my_tuple": original_tuple,
                "my_frozenset": original_frozenset,
                "nested_tuple": {"inner": (10, 20, 30)},
            },
        )

        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        # Tuples preserve their type through roundtrip
        assert loaded.state["my_tuple"] == original_tuple
        assert isinstance(loaded.state["my_tuple"], tuple)

        # Frozensets are pickled and preserve their type
        assert loaded.state["my_frozenset"] == original_frozenset
        assert isinstance(loaded.state["my_frozenset"], frozenset)

        # Nested tuples also preserve their type
        assert loaded.state["nested_tuple"]["inner"] == (10, 20, 30)
        assert isinstance(loaded.state["nested_tuple"]["inner"], tuple)


async def test_file_checkpoint_storage_roundtrip_complex_nested_structures():
    """Test complex nested structures with mixed types roundtrip correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create complex nested structure mixing JSON-native and non-native types
        complex_state = {
            "level1": {
                "level2": {
                    "level3": {
                        "deep_string": "hello",
                        "deep_int": 123,
                        "deep_datetime": datetime(2025, 1, 1, tzinfo=timezone.utc),
                        "deep_tuple": (1, 2, 3),
                    }
                },
                "list_of_dicts": [
                    {"a": 1, "b": datetime(2025, 2, 1, tzinfo=timezone.utc)},
                    {"c": 2, "d": (4, 5, 6)},
                ],
            },
            "mixed_list": [
                "string",
                42,
                3.14,
                True,
                None,
                datetime(2025, 3, 1, tzinfo=timezone.utc),
                (7, 8, 9),
            ],
        }

        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state=complex_state,
        )

        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        # Verify deep nested values
        assert loaded.state["level1"]["level2"]["level3"]["deep_string"] == "hello"
        assert loaded.state["level1"]["level2"]["level3"]["deep_int"] == 123
        assert loaded.state["level1"]["level2"]["level3"]["deep_datetime"] == datetime(2025, 1, 1, tzinfo=timezone.utc)
        # Tuples preserve their type through roundtrip
        assert loaded.state["level1"]["level2"]["level3"]["deep_tuple"] == (1, 2, 3)

        # Verify list of dicts
        assert loaded.state["level1"]["list_of_dicts"][0]["a"] == 1
        assert loaded.state["level1"]["list_of_dicts"][0]["b"] == datetime(2025, 2, 1, tzinfo=timezone.utc)
        # Tuples preserve their type through roundtrip
        assert loaded.state["level1"]["list_of_dicts"][1]["d"] == (4, 5, 6)

        # Verify mixed list with correct types
        assert loaded.state["mixed_list"][0] == "string"
        assert loaded.state["mixed_list"][1] == 42
        assert loaded.state["mixed_list"][5] == datetime(2025, 3, 1, tzinfo=timezone.utc)
        # Tuples preserve their type through roundtrip
        assert loaded.state["mixed_list"][6] == (7, 8, 9)
        assert isinstance(loaded.state["mixed_list"][6], tuple)


async def test_file_checkpoint_storage_roundtrip_messages_with_complex_data():
    """Test that messages dict with Message objects roundtrips correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        msg1 = WorkflowMessage(
            data={"text": "hello", "timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc)},
            source_id="source",
            target_id="target",
        )
        msg2 = WorkflowMessage(
            data=(1, 2, 3),
            source_id="s2",
            target_id=None,
        )
        msg3 = WorkflowMessage(
            data="simple string",
            source_id="s3",
            target_id="t3",
        )

        messages = {
            "executor1": [msg1, msg2],
            "executor2": [msg3],
        }

        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            messages=messages,
        )

        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        # Verify messages structure and types
        assert len(loaded.messages["executor1"]) == 2
        loaded_msg1 = loaded.messages["executor1"][0]
        loaded_msg2 = loaded.messages["executor1"][1]
        loaded_msg3 = loaded.messages["executor2"][0]

        # Verify WorkflowMessage type is preserved
        assert isinstance(loaded_msg1, WorkflowMessage)
        assert isinstance(loaded_msg2, WorkflowMessage)
        assert isinstance(loaded_msg3, WorkflowMessage)

        # Verify WorkflowMessage fields
        assert loaded_msg1.data["text"] == "hello"
        assert loaded_msg1.data["timestamp"] == datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert loaded_msg1.source_id == "source"
        assert loaded_msg1.target_id == "target"

        assert loaded_msg2.data == (1, 2, 3)
        assert isinstance(loaded_msg2.data, tuple)
        assert loaded_msg2.source_id == "s2"
        assert loaded_msg2.target_id is None

        assert loaded_msg3.data == "simple string"
        assert loaded_msg3.source_id == "s3"
        assert loaded_msg3.target_id == "t3"


async def test_file_checkpoint_storage_roundtrip_pending_request_info_events():
    """Test that pending_request_info_events with WorkflowEvent objects roundtrip correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(
            temp_dir,
            allowed_checkpoint_types=["tests.workflow.test_checkpoint:_TestToolApprovalRequest"],
        )

        # Create request_info events using the proper WorkflowEvent factory
        event1 = WorkflowEvent.request_info(
            request_id="req123",
            source_executor_id="executor1",
            request_data="What is your name?",
            response_type=str,
        )
        event2 = WorkflowEvent.request_info(
            request_id="req456",
            source_executor_id="executor2",
            request_data=_TestToolApprovalRequest(
                tool_name="search",
                arguments={"query": "test"},
                timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            response_type=bool,
        )

        pending_events = {
            "req123": event1,
            "req456": event2,
        }

        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            pending_request_info_events=pending_events,  # type: ignore[arg-type]
        )

        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        # Verify WorkflowEvent type is preserved
        loaded_event1 = loaded.pending_request_info_events["req123"]
        loaded_event2 = loaded.pending_request_info_events["req456"]

        assert isinstance(loaded_event1, WorkflowEvent)
        assert isinstance(loaded_event2, WorkflowEvent)

        # Verify event1 fields
        assert loaded_event1.type == "request_info"
        assert loaded_event1.request_id == "req123"
        assert loaded_event1.source_executor_id == "executor1"
        assert loaded_event1.data == "What is your name?"
        assert loaded_event1.response_type is str

        # Verify event2 fields with complex data
        assert loaded_event2.type == "request_info"
        assert loaded_event2.request_id == "req456"
        assert loaded_event2.source_executor_id == "executor2"
        assert isinstance(loaded_event2.data, _TestToolApprovalRequest)
        assert loaded_event2.data.tool_name == "search"
        assert loaded_event2.data.arguments == {"query": "test"}
        assert loaded_event2.data.timestamp == datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert loaded_event2.response_type is bool


async def test_file_checkpoint_storage_roundtrip_full_checkpoint():
    """Test complete WorkflowCheckpoint roundtrip with all fields populated using proper types."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(
            temp_dir,
            allowed_checkpoint_types=[
                "tests.workflow.test_checkpoint:_TestApprovalRequest",
                "tests.workflow.test_checkpoint:_TestExecutorState",
            ],
        )

        # Create proper WorkflowMessage objects
        msg1 = WorkflowMessage(data="msg1", source_id="s", target_id="t")
        msg2 = WorkflowMessage(data=datetime(2025, 1, 1, tzinfo=timezone.utc), source_id="a", target_id="b")

        # Create proper WorkflowEvent for pending request
        pending_event = WorkflowEvent.request_info(
            request_id="req1",
            source_executor_id="exec1",
            request_data=_TestApprovalRequest(action="approve", params=(1, 2, 3)),
            response_type=bool,
        )

        checkpoint = WorkflowCheckpoint(
            checkpoint_id="full-test-checkpoint",
            workflow_name="comprehensive-test",
            graph_signature_hash="hash-abc123",
            previous_checkpoint_id="previous-checkpoint-id",
            timestamp=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
            messages={
                "exec1": [msg1],
                "exec2": [msg2],
            },
            state={
                "user_data": {"name": "test", "created": datetime(2025, 1, 1, tzinfo=timezone.utc)},
                "_executor_state": {
                    "exec1": _TestExecutorState(counter=5, history=["a", "b", "c"]),
                },
            },
            pending_request_info_events={
                "req1": pending_event,
            },
            iteration_count=10,
            metadata={
                "superstep": 5,
                "started_at": datetime(2025, 6, 15, 11, 0, 0, tzinfo=timezone.utc),
            },
            version="1.0",
        )

        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        # Verify all scalar fields
        assert loaded.checkpoint_id == checkpoint.checkpoint_id
        assert loaded.workflow_name == checkpoint.workflow_name
        assert loaded.graph_signature_hash == checkpoint.graph_signature_hash
        assert loaded.previous_checkpoint_id == checkpoint.previous_checkpoint_id
        assert loaded.timestamp == checkpoint.timestamp
        assert loaded.iteration_count == checkpoint.iteration_count
        assert loaded.version == checkpoint.version

        # Verify complex nested state data
        assert loaded.state["user_data"]["created"] == datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert loaded.state["_executor_state"]["exec1"].counter == 5
        assert loaded.state["_executor_state"]["exec1"].history == ["a", "b", "c"]
        assert isinstance(loaded.state["_executor_state"]["exec1"], _TestExecutorState)

        # Verify messages are proper Message objects
        loaded_msg1 = loaded.messages["exec1"][0]
        loaded_msg2 = loaded.messages["exec2"][0]
        assert isinstance(loaded_msg1, WorkflowMessage)
        assert isinstance(loaded_msg2, WorkflowMessage)
        assert loaded_msg1.data == "msg1"
        assert loaded_msg1.source_id == "s"
        assert loaded_msg2.data == datetime(2025, 1, 1, tzinfo=timezone.utc)

        # Verify pending events are proper WorkflowEvent objects
        loaded_event = loaded.pending_request_info_events["req1"]
        assert isinstance(loaded_event, WorkflowEvent)
        assert loaded_event.type == "request_info"
        assert loaded_event.request_id == "req1"
        assert isinstance(loaded_event.data, _TestApprovalRequest)
        assert loaded_event.data.params == (1, 2, 3)

        # Verify metadata
        assert loaded.metadata["superstep"] == 5
        assert loaded.metadata["started_at"] == datetime(2025, 6, 15, 11, 0, 0, tzinfo=timezone.utc)


async def test_file_checkpoint_storage_roundtrip_bytes():
    """Test that bytes objects roundtrip correctly via pickle encoding."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        binary_data = b"\x00\x01\x02\xff\xfe\xfd"
        unicode_bytes = "Hello 世界".encode()

        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={
                "binary_data": binary_data,
                "unicode_bytes": unicode_bytes,
                "nested": {"inner_bytes": binary_data},
            },
        )

        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        assert loaded.state["binary_data"] == binary_data
        assert loaded.state["unicode_bytes"] == unicode_bytes
        assert loaded.state["nested"]["inner_bytes"] == binary_data
        assert isinstance(loaded.state["binary_data"], bytes)


async def test_file_checkpoint_storage_roundtrip_empty_collections():
    """Test that empty collections roundtrip correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={
                "empty_dict": {},
                "empty_list": [],
                "empty_tuple": (),
                "nested_empty": {"inner_dict": {}, "inner_list": []},
            },
            messages={},
            pending_request_info_events={},
        )

        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        assert loaded.state["empty_dict"] == {}
        assert loaded.state["empty_list"] == []
        # Empty tuples preserve their type through roundtrip
        assert loaded.state["empty_tuple"] == ()
        assert isinstance(loaded.state["empty_tuple"], tuple)
        assert loaded.state["nested_empty"]["inner_dict"] == {}
        assert loaded.messages == {}
        assert loaded.pending_request_info_events == {}


# endregion


async def test_file_checkpoint_storage_queued_saves_do_not_occupy_executor_threads(monkeypatch):
    """Queued same-path saves must wait on the event loop, not inside the executor.

    Reviewer concern on #7757: the previous design acquired the destination lock inside
    the worker, so every same-path save occupied an `asyncio.to_thread` worker while
    merely waiting. A burst could fill the default pool and stall unrelated work --
    including checkpoint loads -- and deadlock once the write that had to finish first
    was queued behind those waiters. Ownership is now taken before submission, so only
    the active write holds a worker.

    The gate is a deliberately small executor: with three same-path saves in flight and
    only two workers, an unrelated `to_thread` call still has to get a thread.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from agent_framework._workflows import _checkpoint as checkpoint_module

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        real_replace = checkpoint_module.os.replace
        first_replace_reached = threading.Event()
        release_first_replace = threading.Event()
        inside_worker = 0
        max_inside_worker = 0
        counter_guard = threading.Lock()

        def gated_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
            nonlocal inside_worker, max_inside_worker
            with counter_guard:
                inside_worker += 1
                max_inside_worker = max(max_inside_worker, inside_worker)
                first = inside_worker == 1 and not first_replace_reached.is_set()
            try:
                if first:
                    first_replace_reached.set()
                    assert release_first_replace.wait(timeout=10)
                real_replace(src, dst)
            finally:
                with counter_guard:
                    inside_worker -= 1

        monkeypatch.setattr(checkpoint_module.os, "replace", gated_replace)

        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ckpt-test")
        # `set_default_executor(None)` is rejected, so the original has to be put back
        # by attribute. Routed through an untyped local rather than ignore comments.
        loop: Any = asyncio.get_running_loop()
        previous_executor = loop._default_executor
        loop.set_default_executor(executor)
        try:
            saves = [
                asyncio.create_task(
                    storage.save(
                        WorkflowCheckpoint(
                            workflow_name=f"w{index}",
                            graph_signature_hash="test-hash",
                            checkpoint_id="shared-id",
                        )
                    )
                )
                for index in range(3)
            ]
            assert await asyncio.to_thread(first_replace_reached.wait, 10)

            # The decisive assertion: two saves are queued behind the parked one, and an
            # unrelated to_thread call must still be scheduled. Under the old design the
            # waiters held both workers and this timed out.
            marker = await asyncio.wait_for(asyncio.to_thread(lambda: "scheduled"), timeout=5)
            assert marker == "scheduled"

            release_first_replace.set()
            await asyncio.wait_for(asyncio.gather(*saves), timeout=10)
            assert max_inside_worker == 1, f"{max_inside_worker} writes ran concurrently for one destination"
        finally:
            loop._default_executor = previous_executor
            executor.shutdown(wait=True)


async def test_file_checkpoint_storage_cancel_before_submission_writes_nothing(monkeypatch):
    """A save cancelled while queued must never submit its write, and must not stall the queue.

    This is the other half of the cancellation contract: the reviewer asked that a
    cancelled write either be removed before submission or drained. A save cancelled
    while still waiting for the destination has nothing in the executor, so it is simply
    removed -- and it still has to hand ownership on, or every later save for that path
    would wait forever.
    """
    import threading

    from agent_framework._workflows import _checkpoint as checkpoint_module

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        real_replace = checkpoint_module.os.replace
        first_replace_reached = threading.Event()
        release_first_replace = threading.Event()
        # `_replace_with_retry` may call os.replace more than once for a single write, so
        # count completed writes rather than attempts.
        attempts = 0
        written: list[str] = []
        guard = threading.Lock()

        def gated_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
            nonlocal attempts
            with guard:
                attempts += 1
                first = attempts == 1
            if first:
                first_replace_reached.set()
                assert release_first_replace.wait(timeout=10)
            real_replace(src, dst)
            with guard:
                written.append(os.path.basename(str(dst)))

        monkeypatch.setattr(checkpoint_module.os, "replace", gated_replace)

        def make(name: str) -> WorkflowCheckpoint:
            return WorkflowCheckpoint(workflow_name=name, graph_signature_hash="test-hash", checkpoint_id="shared-id")

        holder = asyncio.create_task(storage.save(make("holder")))
        assert await asyncio.to_thread(first_replace_reached.wait, 10)

        queued = asyncio.create_task(storage.save(make("cancelled")))
        follower = asyncio.create_task(storage.save(make("follower")))

        # Wait on observable state rather than a sleep: both saves must actually be
        # queued behind the holder before cancelling, or this would be testing a
        # cancellation that raced the enqueue instead.
        registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]
        canonical = (Path(temp_dir) / "shared-id.json").resolve()
        for _ in range(400):
            entry = registry.get(canonical)
            if entry is not None and entry.pending == 3:
                break
            await asyncio.sleep(0.005)
        entry = registry.get(canonical)
        assert entry is not None and entry.pending == 3, (
            f"expected holder + two queued saves, got {entry.pending if entry else 'no entry'}"
        )

        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        # Nothing was submitted for the cancelled save: the only write in flight is the
        # holder's, still parked before its replace.
        assert attempts == 1, "the cancelled save submitted a write"
        assert written == []

        release_first_replace.set()
        await asyncio.wait_for(asyncio.gather(holder, follower), timeout=10)

        # Two writes total -- the holder and the follower. The cancelled save contributed
        # none, and crucially did not stall the follower behind it.
        assert len(written) == 2
        assert (await storage.load("shared-id")).workflow_name == "follower"
        assert not registry, "a cancelled save left its destination entry behind"


def test_file_checkpoint_storage_serializes_across_event_loops(monkeypatch, tmp_path):
    """Saves driven from separate event loops must still serialize per destination.

    Reviewer concern on #7757: ownership has to be established by something that is not
    bound to a loop, or two workers queued from different loops can reach `os.replace`
    together. The queue hands ownership over a `concurrent.futures.Future`, which any
    loop can await through `asyncio.wrap_future`, so a single chain orders both.

    Deliberately not an async test: it needs two real loops running at once.
    """
    import threading
    import time

    from agent_framework._workflows import _checkpoint as checkpoint_module

    real_replace = checkpoint_module.os.replace
    inside_replace = 0
    max_inside_replace = 0
    completed: list[str] = []
    guard = threading.Lock()
    both_enqueued = threading.Barrier(2, timeout=10)

    def observing_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
        nonlocal inside_replace, max_inside_replace
        with guard:
            inside_replace += 1
            max_inside_replace = max(max_inside_replace, inside_replace)
        try:
            # Widen the window a real overlap would land in.
            time.sleep(0.05)
            real_replace(src, dst)
        finally:
            with guard:
                inside_replace -= 1
                completed.append(os.path.basename(str(dst)))

    monkeypatch.setattr(checkpoint_module.os, "replace", observing_replace)

    errors: list[BaseException] = []

    def run_loop(name: str) -> None:
        async def main() -> None:
            storage = FileCheckpointStorage(str(tmp_path))
            # Make both loops reach save() at the same time so the queue, not timing,
            # is what orders them.
            await asyncio.to_thread(both_enqueued.wait)
            await storage.save(
                WorkflowCheckpoint(
                    workflow_name=name,
                    graph_signature_hash="test-hash",
                    checkpoint_id="cross-loop-id",
                )
            )

        try:
            asyncio.run(main())
        except BaseException as exc:  # noqa: BLE001 - surfaced to the test below
            errors.append(exc)

    threads = [threading.Thread(target=run_loop, args=(f"loop-{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "a save driven from its own event loop never finished"

    assert not errors, f"saves raised: {errors!r}"
    assert len(completed) == 2
    assert max_inside_replace == 1, f"{max_inside_replace} writes reached os.replace together across event loops"
    registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]
    assert not registry, "cross-loop saves left a destination entry behind"


async def test_file_checkpoint_storage_repeated_cancellation_still_drains(monkeypatch):
    """Cancelling again while a save is draining must not abandon the in-flight write.

    Once a task has a cancellation pending, its next await raises `CancelledError`
    immediately -- so a drain built on a single `await asyncio.shield(worker)` returns
    with the worker still running and the write can land after ownership is released.
    A task group or supervisor that cancels more than once reaches exactly that path,
    so the drain absorbs re-delivered cancellations until the worker is genuinely done.
    """
    import threading

    from agent_framework._workflows import _checkpoint as checkpoint_module

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        real_replace = checkpoint_module.os.replace
        replace_started = threading.Event()
        release_replace = threading.Event()
        finished_writes: list[str] = []
        guard = threading.Lock()

        def gated_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
            replace_started.set()
            assert release_replace.wait(timeout=10)
            real_replace(src, dst)
            with guard:
                finished_writes.append(os.path.basename(str(dst)))

        monkeypatch.setattr(checkpoint_module.os, "replace", gated_replace)

        task = asyncio.create_task(
            storage.save(
                WorkflowCheckpoint(
                    workflow_name="drained",
                    graph_signature_hash="test-hash",
                    checkpoint_id="shared-id",
                )
            )
        )
        assert await asyncio.to_thread(replace_started.wait, 10)

        # Cancel repeatedly while the worker is parked. Each one is re-delivered into
        # the drain, which must keep waiting rather than return early.
        for _ in range(5):
            task.cancel()
            await asyncio.sleep(0.01)
        assert not task.done(), "drain gave up while the write was still in flight"
        assert finished_writes == []

        release_replace.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        # The write it owned completed before it propagated, so nothing lands later.
        assert finished_writes == ["shared-id.json"]
        registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]
        assert not registry


async def test_file_checkpoint_storage_write_failing_during_drain_is_reported(monkeypatch, caplog):
    """A write that fails while draining must surface in the log, not vanish.

    The cancelled caller never sees the write's exception -- it receives
    `CancelledError` -- so the only place a failure can be noticed is the log.
    """
    import threading

    from agent_framework._workflows import _checkpoint as checkpoint_module

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        replace_started = threading.Event()
        release_replace = threading.Event()

        def failing_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
            replace_started.set()
            assert release_replace.wait(timeout=10)
            raise OSError("disk went away mid-publish")

        monkeypatch.setattr(checkpoint_module.os, "replace", failing_replace)

        task = asyncio.create_task(
            storage.save(
                WorkflowCheckpoint(
                    workflow_name="failing",
                    graph_signature_hash="test-hash",
                    checkpoint_id="shared-id",
                )
            )
        )
        assert await asyncio.to_thread(replace_started.wait, 10)

        task.cancel()
        await asyncio.sleep(0.01)
        with caplog.at_level(logging.WARNING, logger=checkpoint_module.logger.name):
            release_replace.set()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert any("failed while draining after cancellation" in record.message for record in caplog.records), (
            f"the drained write's failure was not reported: {[r.message for r in caplog.records]}"
        )
        registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]
        assert not registry, "a failed drained write left its destination entry behind"


def test_release_write_tolerates_an_already_dropped_entry():
    """Releasing a ticket whose entry is gone must be a no-op, not a KeyError.

    Defensive: the registry entry is dropped by whichever operation releases last, so a
    release must never assume its entry is still present.
    """
    from agent_framework._workflows import _checkpoint as checkpoint_module

    path = Path("/nonexistent/never-enqueued.json")
    ticket = checkpoint_module._WriteTicket(  # pyright: ignore[reportPrivateUsage]
        path=path,
        predecessor=None,
        completion=ConcurrentFuture(),
    )
    # No entry was ever created for this path.
    checkpoint_module._release_write(ticket)  # pyright: ignore[reportPrivateUsage]
    assert ticket.completion.done()
    assert path not in checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]


def test_file_checkpoint_storage_abandoned_loop_does_not_own_destination_forever(monkeypatch, tmp_path):
    """A loop that goes away mid-write must not leave its destination owned forever.

    Ownership is released as the write's last act on the worker thread, not only in the
    coroutine's `finally`. A thread outlives the loop that submitted it, so the write
    finishes and hands the destination on; releasing solely from the coroutine would
    leave the path owned for the life of the process and hang every later save to it.

    Deliberately not an async test: it has to close a loop out from under a pending task.
    """
    import threading
    import time

    from agent_framework._workflows import _checkpoint as checkpoint_module

    real_replace = checkpoint_module.os.replace
    parked = threading.Event()
    release_parked = threading.Event()

    def gated_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
        parked.set()
        assert release_parked.wait(timeout=20)
        real_replace(src, dst)

    monkeypatch.setattr(checkpoint_module.os, "replace", gated_replace)

    def make(name: str) -> WorkflowCheckpoint:
        return WorkflowCheckpoint(workflow_name=name, graph_signature_hash="test-hash", checkpoint_id="abandoned-id")

    abandoned_loop = asyncio.new_event_loop()
    # Closing a loop with a pending task makes asyncio report "Task was destroyed but it
    # is pending!" through the loop's exception handler. That is exactly the situation
    # under test, so silence it rather than leaving the noise in CI output.
    abandoned_loop.set_exception_handler(lambda loop, context: None)
    try:
        storage = FileCheckpointStorage(str(tmp_path))

        async def start_and_park() -> asyncio.Task[str]:
            task = abandoned_loop.create_task(storage.save(make("abandoned")))
            await asyncio.to_thread(parked.wait, 20)
            return task

        pending = abandoned_loop.run_until_complete(start_and_park())
        assert not pending.done()
    finally:
        # Abrupt: no cancellation, so the coroutine's `finally` never runs.
        abandoned_loop.close()

    # Let the orphaned worker finish. Its release happens on the thread.
    release_parked.set()
    deadline = time.monotonic() + 10
    while checkpoint_module._destination_queues and time.monotonic() < deadline:  # pyright: ignore[reportPrivateUsage]
        time.sleep(0.05)
    assert not checkpoint_module._destination_queues, (  # pyright: ignore[reportPrivateUsage]
        "the abandoned loop's destination entry was never released"
    )

    # A fresh loop must be able to save to the same destination.
    outcome: dict[str, bool] = {}

    def run_later_save() -> None:
        async def main() -> None:
            later_storage = FileCheckpointStorage(str(tmp_path))
            try:
                await asyncio.wait_for(later_storage.save(make("later")), timeout=10)
                outcome["saved"] = True
            except asyncio.TimeoutError:
                outcome["saved"] = False

        asyncio.run(main())

    thread = threading.Thread(target=run_later_save)
    thread.start()
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert outcome.get("saved") is True, "a later save to the abandoned destination hung"


async def test_file_checkpoint_storage_failed_save_releases_the_destination(monkeypatch):
    """A save that raises must not leave its destination owned.

    The failure path matters as much as cancellation: if a raising write kept ownership,
    one transient disk error would hang every later save to that checkpoint for the life
    of the process.
    """
    from agent_framework._workflows import _checkpoint as checkpoint_module

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        def exploding_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
            raise OSError("simulated disk failure")

        monkeypatch.setattr(checkpoint_module.os, "replace", exploding_replace)

        def make(name: str) -> WorkflowCheckpoint:
            return WorkflowCheckpoint(workflow_name=name, graph_signature_hash="test-hash", checkpoint_id="shared-id")

        with pytest.raises(OSError, match="simulated disk failure"):
            await storage.save(make("fails"))

        registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]
        assert not registry, "a failed save kept its destination"

        # And the path is still usable once the failure clears.
        monkeypatch.undo()
        await asyncio.wait_for(storage.save(make("after-failure")), timeout=10)
        assert (await storage.load("shared-id")).workflow_name == "after-failure"
        assert not registry


async def test_file_checkpoint_storage_cancelling_a_queued_save_does_not_let_the_next_overtake(monkeypatch):
    """A save cancelled while queued must not hand off before its predecessor finishes.

    Reviewer concern on #7757: `asyncio.wrap_future` chains cancellation into the future
    it wraps, so cancelling the middle of three queued saves cancelled the shared
    hand-off signal, and the unconditional release then let the third save reach
    `os.replace` while the first still owned the destination -- after which the first
    write could land last and overwrite the newer checkpoint. The hand-off for a
    cancelled ticket is now deferred until its predecessor actually completes.
    """
    import threading

    from agent_framework._workflows import _checkpoint as checkpoint_module

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        real_replace = checkpoint_module.os.replace
        holder_parked = threading.Event()
        release_holder = threading.Event()
        inside_replace = 0
        max_inside_replace = 0
        completed: list[str] = []
        guard = threading.Lock()

        def gated_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
            nonlocal inside_replace, max_inside_replace
            with guard:
                inside_replace += 1
                max_inside_replace = max(max_inside_replace, inside_replace)
                park = inside_replace == 1 and not holder_parked.is_set()
            try:
                if park:
                    holder_parked.set()
                    assert release_holder.wait(timeout=15)
                real_replace(src, dst)
                with guard:
                    completed.append(os.path.basename(str(dst)))
            finally:
                with guard:
                    inside_replace -= 1

        monkeypatch.setattr(checkpoint_module.os, "replace", gated_replace)

        def make(name: str) -> WorkflowCheckpoint:
            return WorkflowCheckpoint(workflow_name=name, graph_signature_hash="test-hash", checkpoint_id="shared-id")

        holder = asyncio.create_task(storage.save(make("holder")))
        assert await asyncio.to_thread(holder_parked.wait, 15)

        queued = asyncio.create_task(storage.save(make("cancelled")))
        third = asyncio.create_task(storage.save(make("third")))

        registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]
        canonical = (Path(temp_dir) / "shared-id.json").resolve()
        for _ in range(400):
            entry = registry.get(canonical)
            if entry is not None and entry.pending == 3:
                break
            await asyncio.sleep(0.005)
        entry = registry.get(canonical)
        assert entry is not None and entry.pending == 3

        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued

        # The holder is still parked inside its replace. The third save must not have
        # taken the destination on the back of the cancellation.
        for _ in range(30):
            await asyncio.sleep(0.01)
            with guard:
                assert max_inside_replace == 1, "a second write started while the holder still owned the path"
                assert completed == [], "a write completed while the holder was still parked"
        assert not third.done()

        release_holder.set()
        await asyncio.wait_for(asyncio.gather(holder, third), timeout=15)

        with guard:
            assert max_inside_replace == 1, "writes overlapped for one destination"
            assert len(completed) == 2, f"expected holder + third, got {completed}"
        assert (await storage.load("shared-id")).workflow_name == "third"
        assert not registry, "a cancelled queued save leaked its destination entry"


def test_file_checkpoint_storage_cancelled_worker_task_does_not_release_early(monkeypatch, tmp_path):
    """Cancelling the worker task must not release ownership while the thread writes.

    Reviewer concern on #7757: loop shutdown cancels `save()` and the task wrapping
    `asyncio.to_thread`, which makes `worker.done()` true while the function is still
    blocked in `os.replace`. Draining on that task therefore returned immediately and
    ownership was released with the write in flight. The drain now waits on the signal
    the worker thread resolves, which cancellation cannot mark done.

    Deliberately not an async test: it cancels every task the way shutdown does.
    """
    import threading
    import time

    from agent_framework._workflows import _checkpoint as checkpoint_module

    real_replace = checkpoint_module.os.replace
    parked = threading.Event()
    release_parked = threading.Event()

    def gated_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
        parked.set()
        assert release_parked.wait(timeout=15)
        real_replace(src, dst)

    monkeypatch.setattr(checkpoint_module.os, "replace", gated_replace)

    canonical = (tmp_path / "shared-id.json").resolve()
    observed: dict[str, bool] = {}

    async def main() -> None:
        storage = FileCheckpointStorage(str(tmp_path))
        task = asyncio.create_task(
            storage.save(
                WorkflowCheckpoint(workflow_name="holder", graph_signature_hash="test-hash", checkpoint_id="shared-id")
            )
        )
        await asyncio.to_thread(parked.wait, 15)

        # What loop shutdown does: cancel every remaining task, including the one
        # wrapping asyncio.to_thread.
        for pending in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
            pending.cancel()

        for _ in range(40):
            await asyncio.sleep(0.01)
            if canonical not in checkpoint_module._destination_queues:  # pyright: ignore[reportPrivateUsage]
                break
        # The write is still parked, so the destination must still be owned.
        observed["released_early"] = canonical not in checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]
        observed["still_writing"] = not release_parked.is_set()

        release_parked.set()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(main())

    assert observed["still_writing"], "the test never held the write open"
    assert not observed["released_early"], "ownership was released while the write was still in flight"
    # The worker thread releases once its write lands, so nothing is left owned.
    deadline = time.monotonic() + 10
    while checkpoint_module._destination_queues and time.monotonic() < deadline:  # pyright: ignore[reportPrivateUsage]
        time.sleep(0.05)
    assert not checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]


def test_file_checkpoint_storage_shutdown_before_the_write_starts_does_not_hang(monkeypatch, tmp_path):
    """Loop shutdown before the write reaches the executor must not strand the save.

    Submitting through `asyncio.ensure_future(asyncio.to_thread(...))` makes the write a
    Task, and shutdown cancels every task -- potentially before it has reached the
    executor. Nothing would then release the destination, and a coroutine waiting for the
    write's completion signal would wait for a signal that could never be resolved, so
    the save never finished at all. Submission now goes through `run_in_executor`, which
    returns a plain Future that `asyncio.all_tasks()` does not include, and a done
    callback releases even if the executor drops the work.

    Deliberately not an async test: it has to cancel every task the way shutdown does.
    """
    from agent_framework._workflows import _checkpoint as checkpoint_module

    canonical = (tmp_path / "shared-id.json").resolve()
    outcome: dict[str, object] = {}

    async def main() -> None:
        storage = FileCheckpointStorage(str(tmp_path))
        asyncio.create_task(
            storage.save(
                WorkflowCheckpoint(workflow_name="victim", graph_signature_hash="test-hash", checkpoint_id="shared-id")
            )
        )
        # One tick, so the save coroutine actually runs and submits its write. Without
        # it the write has not been created yet and cancelling only the save takes the
        # clean cancelled-before-submission path, which was never the broken case.
        await asyncio.sleep(0)
        victims = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        outcome["task_count"] = len(victims)

        # Assert the structural property *before* cancelling anything. If the write is a
        # task, shutdown sweeps it and the save can end up waiting for a completion
        # signal nothing will ever resolve -- which hangs `asyncio.run`'s own shutdown,
        # outside any `wait_for` this test could wrap around it. Failing here keeps the
        # regression a clean assertion rather than a hung CI job.
        assert len(victims) == 1, (
            f"the write must not be a task, or loop shutdown cancels it: found {len(victims)} tasks"
        )

        for task in victims:
            task.cancel()
        await asyncio.wait_for(asyncio.gather(*victims, return_exceptions=True), timeout=10)

    asyncio.run(main())
    assert outcome["task_count"] == 1

    deadline = time.monotonic() + 10
    while canonical in checkpoint_module._destination_queues and time.monotonic() < deadline:  # pyright: ignore[reportPrivateUsage]
        time.sleep(0.05)
    assert canonical not in checkpoint_module._destination_queues, (  # pyright: ignore[reportPrivateUsage]
        "shutdown before the write started left the destination owned forever"
    )


async def test_file_checkpoint_storage_executor_shutdown_at_submission_releases():
    """If the write cannot be submitted at all, the coroutine must release the destination.

    `run_in_executor` raises synchronously against a shut-down executor, so no worker
    exists to release on our behalf. This is the one path where the coroutine, not the
    worker thread, owns the release.
    """
    from concurrent.futures import ThreadPoolExecutor

    from agent_framework._workflows import _checkpoint as checkpoint_module

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        dead_executor = ThreadPoolExecutor(max_workers=1)
        dead_executor.shutdown(wait=True)
        loop: Any = asyncio.get_running_loop()
        previous_executor = loop._default_executor
        loop.set_default_executor(dead_executor)
        try:
            with pytest.raises(RuntimeError):
                await storage.save(
                    WorkflowCheckpoint(
                        workflow_name="no-executor",
                        graph_signature_hash="test-hash",
                        checkpoint_id="shared-id",
                    )
                )
        finally:
            loop._default_executor = previous_executor

        registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]
        assert not registry, "a save that could not be submitted kept its destination"

        # The path is still usable once an executor is available again.
        await asyncio.wait_for(
            storage.save(
                WorkflowCheckpoint(workflow_name="after", graph_signature_hash="test-hash", checkpoint_id="shared-id")
            ),
            timeout=10,
        )
        assert (await storage.load("shared-id")).workflow_name == "after"


def test_wait_for_signal_survives_its_loop_being_closed():
    """Resolving a signal after its waiter's loop closed must not raise.

    The worker thread outlives the loop that submitted the write, so it can resolve a
    hand-off signal that a now-dead loop was waiting on. `call_soon_threadsafe` raises
    `RuntimeError` on a closed loop, and that runs inside a `concurrent.futures`
    done-callback -- where an exception would be swallowed into the callback machinery
    rather than surfacing usefully.
    """
    import threading
    from concurrent.futures import Future as ConcurrentFuture

    from agent_framework._workflows import _checkpoint as checkpoint_module

    source: ConcurrentFuture[None] = ConcurrentFuture()
    loop = asyncio.new_event_loop()
    try:

        async def register() -> None:
            checkpoint_module._wait_for_signal(source)  # pyright: ignore[reportPrivateUsage]

        loop.run_until_complete(register())
    finally:
        loop.close()

    # The worker thread resolves it after the loop is gone.
    errors: list[BaseException] = []

    def resolve() -> None:
        try:
            source.set_result(None)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    thread = threading.Thread(target=resolve)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert not errors, f"resolving after loop close raised: {errors!r}"
    assert source.done()


def test_await_signal_through_cancellation_survives_its_loop_being_closed():
    """Resolving the signal after the draining loop closed must not raise.

    The worker thread outlives the loop that submitted the write, so it can resolve a
    signal that a now-dead loop was draining on. `call_soon_threadsafe` raises
    `RuntimeError` against a closed loop, inside a `concurrent.futures` done-callback
    where it would be swallowed rather than surface.
    """
    import threading
    from concurrent.futures import Future as ConcurrentFuture

    from agent_framework._workflows import _checkpoint as checkpoint_module

    source: ConcurrentFuture[None] = ConcurrentFuture()
    loop = asyncio.new_event_loop()
    loop.set_exception_handler(lambda active_loop, context: None)
    try:
        # Start the drain, let it subscribe and suspend, then abandon the loop.
        drain = loop.create_task(
            checkpoint_module._await_signal_through_cancellation(source)  # pyright: ignore[reportPrivateUsage]
        )
        loop.run_until_complete(asyncio.sleep(0))
        assert not drain.done()
    finally:
        loop.close()

    errors: list[BaseException] = []

    def resolve() -> None:
        try:
            source.set_result(None)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    thread = threading.Thread(target=resolve)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert not errors, f"resolving after the draining loop closed raised: {errors!r}"
    assert source.done()


def test_release_write_does_not_recurse_per_deferred_link():
    """A long run of deferred releases must not nest one stack frame per link.

    A save cancelled while queued defers its hand-off onto its predecessor, so resolving
    the first ticket runs the second's callback, which resolves the third, and so on. Done
    naively that is synchronous recursion: a run longer than the recursion limit raised
    `RecursionError` on the worker thread partway through and left the destination owned
    for the life of the process. The chain is drained in a loop instead.

    Built from tickets directly so the depth can exceed the recursion limit without
    thousands of real saves.
    """
    from concurrent.futures import Future as ConcurrentFuture

    from agent_framework._workflows import _checkpoint as checkpoint_module

    depth = 2000
    assert depth > sys.getrecursionlimit(), "the run has to be longer than the recursion limit to prove anything"

    path = Path("/nonexistent/deferred-chain.json")
    tickets = [
        checkpoint_module._WriteTicket(  # pyright: ignore[reportPrivateUsage]
            path=path,
            predecessor=None,
            completion=ConcurrentFuture(),
        )
        for _ in range(depth)
    ]
    # Each link releases only once the one before it has.
    for earlier, later in zip(tickets, tickets[1:]):
        checkpoint_module._release_write_after(later, earlier.completion)  # pyright: ignore[reportPrivateUsage]

    # Releasing the head must unwind the whole run.
    checkpoint_module._release_write(tickets[0])  # pyright: ignore[reportPrivateUsage]

    unresolved = [index for index, ticket in enumerate(tickets) if not ticket.completion.done()]
    assert not unresolved, f"{len(unresolved)} links never released, first at index {unresolved[0]}"
    assert all(ticket.released for ticket in tickets)


def test_file_checkpoint_storage_abandoned_loop_while_queued_releases_the_destination(monkeypatch, tmp_path):
    """A save whose loop dies while it is still queued must not strand the destination.

    Reviewer follow-up on #7757: the submitted write is released by its worker thread, but
    a ticket still *waiting* for its predecessor has no worker. If that waiter's loop
    closes, `call_soon_threadsafe` raises and the coroutine never resumes, so nothing
    resolves its hand-off signal and every later save for the destination waits forever.
    The predecessor's callback now performs the release itself in that case.

    Deliberately not an async test: it needs two loops and has to close one of them.
    """
    import threading
    import time

    from agent_framework._workflows import _checkpoint as checkpoint_module

    real_replace = checkpoint_module.os.replace
    parked = threading.Event()
    release_parked = threading.Event()

    def gated_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
        parked.set()
        assert release_parked.wait(timeout=20)
        real_replace(src, dst)

    monkeypatch.setattr(checkpoint_module.os, "replace", gated_replace)

    def make(name: str) -> WorkflowCheckpoint:
        return WorkflowCheckpoint(workflow_name=name, graph_signature_hash="test-hash", checkpoint_id="shared-id")

    canonical = (tmp_path / "shared-id.json").resolve()
    registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]

    holder_loop = asyncio.new_event_loop()
    queued_loop = asyncio.new_event_loop()
    queued_loop.set_exception_handler(lambda loop, context: None)
    try:
        holder_storage = FileCheckpointStorage(str(tmp_path))

        async def start_holder() -> asyncio.Task[str]:
            task = holder_loop.create_task(holder_storage.save(make("holder")))
            await asyncio.to_thread(parked.wait, 20)
            return task

        holder = holder_loop.run_until_complete(start_holder())

        # A second save queues behind the parked holder on its own loop.
        queued_storage = FileCheckpointStorage(str(tmp_path))

        async def start_queued() -> None:
            queued_loop.create_task(queued_storage.save(make("queued")))
            for _ in range(400):
                entry = registry.get(canonical)
                if entry is not None and entry.pending == 2:
                    return
                await asyncio.sleep(0.005)
            raise AssertionError("the second save never queued behind the holder")

        queued_loop.run_until_complete(start_queued())
    finally:
        # Abandoned while its ticket is still queued and nothing has been submitted.
        queued_loop.close()

    release_parked.set()
    holder_loop.run_until_complete(asyncio.gather(holder, return_exceptions=True))
    holder_loop.close()

    deadline = time.monotonic() + 10
    while canonical in registry and time.monotonic() < deadline:
        time.sleep(0.05)
    assert canonical not in registry, "the abandoned queued save left the destination owned"

    # And the destination is usable again from a fresh loop.
    outcome: dict[str, bool] = {}

    def later_save() -> None:
        async def main() -> None:
            storage = FileCheckpointStorage(str(tmp_path))
            try:
                await asyncio.wait_for(storage.save(make("later")), timeout=10)
                outcome["saved"] = True
            except asyncio.TimeoutError:
                outcome["saved"] = False

        asyncio.run(main())

    thread = threading.Thread(target=later_save)
    thread.start()
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert outcome.get("saved") is True, "a later save to the abandoned destination hung"


def test_file_checkpoint_storage_graceful_shutdown_releases_a_queued_save(tmp_path, monkeypatch):
    """A queued save released through the normal shutdown path, which is the guarantee.

    `asyncio.run` cancels pending tasks before closing, so a save still waiting for its
    predecessor takes its cancellation path and defers the hand-off onto that
    predecessor. Pinning it because the `on_abandoned` hook only covers a loop that is
    already closed when the signal resolves -- this is the path that has to stay safe
    without it.
    """
    import threading
    import time

    from agent_framework._workflows import _checkpoint as checkpoint_module

    real_replace = checkpoint_module.os.replace
    parked = threading.Event()
    release_parked = threading.Event()

    def gated_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
        parked.set()
        assert release_parked.wait(timeout=20)
        real_replace(src, dst)

    monkeypatch.setattr(checkpoint_module.os, "replace", gated_replace)

    def make(name: str) -> WorkflowCheckpoint:
        return WorkflowCheckpoint(workflow_name=name, graph_signature_hash="test-hash", checkpoint_id="shared-id")

    canonical = (tmp_path / "shared-id.json").resolve()
    registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]

    holder_loop = asyncio.new_event_loop()
    try:
        holder_storage = FileCheckpointStorage(str(tmp_path))

        async def start_holder() -> asyncio.Task[str]:
            task = holder_loop.create_task(holder_storage.save(make("holder")))
            await asyncio.to_thread(parked.wait, 20)
            return task

        holder = holder_loop.run_until_complete(start_holder())

        # A second save queues behind it, on a loop that exits the normal way.
        def run_queued() -> None:
            async def main() -> None:
                storage = FileCheckpointStorage(str(tmp_path))
                asyncio.create_task(storage.save(make("queued")))
                for _ in range(400):
                    entry = registry.get(canonical)
                    if entry is not None and entry.pending == 2:
                        return
                    await asyncio.sleep(0.005)
                raise AssertionError("the second save never queued behind the holder")

            asyncio.run(main())

        thread = threading.Thread(target=run_queued)
        thread.start()
        thread.join(timeout=30)
        assert not thread.is_alive()

        release_parked.set()
        holder_loop.run_until_complete(asyncio.gather(holder, return_exceptions=True))
    finally:
        holder_loop.close()

    deadline = time.monotonic() + 10
    while canonical in registry and time.monotonic() < deadline:
        time.sleep(0.05)
    assert canonical not in registry, "a gracefully cancelled queued save left the destination owned"


def test_file_checkpoint_storage_abandonment_mid_chain_keeps_the_queue_ordered(tmp_path, monkeypatch):
    """Releasing an abandoned queued ticket must hand off to its successor, in order.

    The two-ticket case only shows the entry clearing. With a live save queued *behind*
    the abandoned one, the release has to propagate through that link and still serialize
    the writes -- if it handed off early, the successor's `os.replace` would run beside
    the holder's.
    """
    import threading
    import time

    from agent_framework._workflows import _checkpoint as checkpoint_module

    real_replace = checkpoint_module.os.replace
    parked = threading.Event()
    release_parked = threading.Event()
    inside_replace = 0
    peak_inside_replace = 0
    completed: list[str] = []
    guard = threading.Lock()

    def gated_replace(src, dst):  # noqa: ANN001, ANN202 - test shim
        nonlocal inside_replace, peak_inside_replace
        with guard:
            inside_replace += 1
            peak_inside_replace = max(peak_inside_replace, inside_replace)
            park = inside_replace == 1 and not parked.is_set()
        try:
            if park:
                parked.set()
                assert release_parked.wait(timeout=25)
            real_replace(src, dst)
            with guard:
                completed.append(os.path.basename(str(dst)))
        finally:
            with guard:
                inside_replace -= 1

    monkeypatch.setattr(checkpoint_module.os, "replace", gated_replace)

    def make(name: str) -> WorkflowCheckpoint:
        return WorkflowCheckpoint(workflow_name=name, graph_signature_hash="test-hash", checkpoint_id="shared-id")

    canonical = (tmp_path / "shared-id.json").resolve()
    registry = checkpoint_module._destination_queues  # pyright: ignore[reportPrivateUsage]

    def wait_for_pending(count: int, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            entry = registry.get(canonical)
            if entry is not None and entry.pending == count:
                return
            time.sleep(0.005)
        entry = registry.get(canonical)
        raise AssertionError(f"expected {count} queued, saw {entry.pending if entry else 0}")

    holder_loop = asyncio.new_event_loop()
    abandoned_loop = asyncio.new_event_loop()
    abandoned_loop.set_exception_handler(lambda loop, context: None)
    successor: dict[str, bool] = {}
    try:
        holder_storage = FileCheckpointStorage(str(tmp_path))

        async def start_holder() -> asyncio.Task[str]:
            task = holder_loop.create_task(holder_storage.save(make("holder")))
            await asyncio.to_thread(parked.wait, 25)
            return task

        holder = holder_loop.run_until_complete(start_holder())

        async def start_abandoned() -> None:
            storage = FileCheckpointStorage(str(tmp_path))
            abandoned_loop.create_task(storage.save(make("abandoned")))
            await asyncio.sleep(0)

        abandoned_loop.run_until_complete(start_abandoned())
        wait_for_pending(2)

        def run_successor() -> None:
            async def main() -> None:
                storage = FileCheckpointStorage(str(tmp_path))
                try:
                    await asyncio.wait_for(storage.save(make("successor")), timeout=25)
                    successor["saved"] = True
                except asyncio.TimeoutError:
                    successor["saved"] = False

            asyncio.run(main())

        thread = threading.Thread(target=run_successor)
        thread.start()
        wait_for_pending(3)

        abandoned_loop.close()

        release_parked.set()
        holder_loop.run_until_complete(asyncio.gather(holder, return_exceptions=True))
        thread.join(timeout=30)
        assert not thread.is_alive()
    finally:
        holder_loop.close()

    assert successor.get("saved") is True, "the save queued behind the abandoned one never ran"
    with guard:
        assert peak_inside_replace == 1, "writes overlapped across the abandoned link"
        assert len(completed) == 2, f"expected holder + successor, got {completed}"
    deadline = time.monotonic() + 10
    while canonical in registry and time.monotonic() < deadline:
        time.sleep(0.05)
    assert canonical not in registry
