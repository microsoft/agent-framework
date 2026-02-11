# Copyright (c) Microsoft. All rights reserved.

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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
    arguments: dict
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
    params: tuple


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
        messages={"executor1": [{"data": "test"}]},
        pending_request_info_events={"req123": {"data": "test"}},
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
        messages={"executor1": [{"data": "test"}]},
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
        messages={"executor1": [{"data": "hello"}]},
        pending_request_info_events={"req123": {"data": "test"}},
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
        async def finish(self, message: str, ctx: WorkflowContext[Never, str]) -> None:
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
        pending_request_info_events=pending_events,
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
            messages={"executor1": [{"data": "hello", "source_id": "test", "target_id": None}]},
            state={"key": "value"},
            pending_request_info_events={"req123": {"data": "test"}},
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
            messages={"executor1": [{"data": {"nested": {"value": 42}}, "source_id": "test", "target_id": None}]},
            state={"list": [1, 2, 3], "dict": {"a": "b", "c": {"d": "e"}}, "bool": True, "null": None},
            pending_request_info_events={"req123": {"data": "test"}},
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
        storage = FileCheckpointStorage(temp_dir)

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
        storage = FileCheckpointStorage(temp_dir)

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
            pending_request_info_events=pending_events,
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
        storage = FileCheckpointStorage(temp_dir)

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
