# Copyright (c) Microsoft. All rights reserved.

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent_framework import (
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
    WorkflowCheckpointException,
)


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
    workflow1_checkpoint_ids = await storage.list_ids("workflow-1")
    assert len(workflow1_checkpoint_ids) == 2
    assert checkpoint1.checkpoint_id in workflow1_checkpoint_ids
    assert checkpoint2.checkpoint_id in workflow1_checkpoint_ids

    # Test list for workflow-1 (returns objects)
    workflow1_checkpoints = await storage.list("workflow-1")
    assert len(workflow1_checkpoints) == 2
    assert all(isinstance(cp, WorkflowCheckpoint) for cp in workflow1_checkpoints)
    assert {cp.checkpoint_id for cp in workflow1_checkpoints} == {checkpoint1.checkpoint_id, checkpoint2.checkpoint_id}

    # Test list_ids for workflow-2
    workflow2_checkpoint_ids = await storage.list_ids("workflow-2")
    assert len(workflow2_checkpoint_ids) == 1
    assert checkpoint3.checkpoint_id in workflow2_checkpoint_ids

    # Test list for workflow-2 (returns objects)
    workflow2_checkpoints = await storage.list("workflow-2")
    assert len(workflow2_checkpoints) == 1
    assert workflow2_checkpoints[0].checkpoint_id == checkpoint3.checkpoint_id

    # Test list_ids for non-existent workflow
    empty_checkpoint_ids = await storage.list_ids("nonexistent-workflow")
    assert len(empty_checkpoint_ids) == 0

    # Test list for non-existent workflow
    empty_checkpoints = await storage.list("nonexistent-workflow")
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
        workflow1_checkpoint_ids = await storage.list_ids("workflow-1")
        assert len(workflow1_checkpoint_ids) == 2
        assert checkpoint1.checkpoint_id in workflow1_checkpoint_ids
        assert checkpoint2.checkpoint_id in workflow1_checkpoint_ids

        # Test list for workflow-1 (returns objects)
        workflow1_checkpoints = await storage.list("workflow-1")
        assert len(workflow1_checkpoints) == 2
        assert all(isinstance(cp, WorkflowCheckpoint) for cp in workflow1_checkpoints)
        checkpoint_ids = {cp.checkpoint_id for cp in workflow1_checkpoints}
        assert checkpoint_ids == {checkpoint1.checkpoint_id, checkpoint2.checkpoint_id}

        # Test list_ids for workflow-2
        workflow2_checkpoint_ids = await storage.list_ids("workflow-2")
        assert len(workflow2_checkpoint_ids) == 1
        assert checkpoint3.checkpoint_id in workflow2_checkpoint_ids

        # Test list for workflow-2 (returns objects)
        workflow2_checkpoints = await storage.list("workflow-2")
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
        checkpoints = await storage.list("any-workflow")
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
            assert hasattr(storage, "list")
            assert callable(storage.list)
            assert hasattr(storage, "delete")
            assert callable(storage.delete)
            assert hasattr(storage, "list_ids")
            assert callable(storage.list_ids)
