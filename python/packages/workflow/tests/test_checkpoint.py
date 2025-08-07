# Copyright (c) Microsoft. All rights reserved.

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agent_framework_workflow._checkpoint import (
    FileCheckpointStorage,
    MemoryCheckpointStorage,
    WorkflowCheckpoint,
)


def test_workflow_checkpoint_default_values():
    checkpoint = WorkflowCheckpoint()

    # Check that default values are set
    assert checkpoint.checkpoint_id != ""  # uuid should be generated
    assert checkpoint.workflow_id == ""
    assert checkpoint.timestamp != ""  # timestamp should be generated
    assert checkpoint.messages == {}
    assert checkpoint.events == []
    assert checkpoint.shared_state == {}
    assert checkpoint.executor_states == {}
    assert checkpoint.iteration_count == 0
    assert checkpoint.max_iterations == 100
    assert checkpoint.metadata == {}
    assert checkpoint.version == "1.0"


def test_workflow_checkpoint_custom_values():
    custom_timestamp = datetime.now(timezone.utc).isoformat()
    checkpoint = WorkflowCheckpoint(
        checkpoint_id="test-checkpoint-123",
        workflow_id="test-workflow-456",
        timestamp=custom_timestamp,
        messages={"executor1": [{"data": "test"}]},
        events=[{"type": "test_event"}],
        shared_state={"key": "value"},
        executor_states={"executor1": {"state": "active"}},
        iteration_count=5,
        max_iterations=50,
        metadata={"test": True},
        version="2.0",
    )

    assert checkpoint.checkpoint_id == "test-checkpoint-123"
    assert checkpoint.workflow_id == "test-workflow-456"
    assert checkpoint.timestamp == custom_timestamp
    assert checkpoint.messages == {"executor1": [{"data": "test"}]}
    assert checkpoint.events == [{"type": "test_event"}]
    assert checkpoint.shared_state == {"key": "value"}
    assert checkpoint.executor_states == {"executor1": {"state": "active"}}
    assert checkpoint.iteration_count == 5
    assert checkpoint.max_iterations == 50
    assert checkpoint.metadata == {"test": True}
    assert checkpoint.version == "2.0"


def test_memory_checkpoint_storage_save_and_load():
    storage = MemoryCheckpointStorage()
    checkpoint = WorkflowCheckpoint(workflow_id="test-workflow", messages={"executor1": [{"data": "hello"}]})

    # Save checkpoint
    saved_id = storage.save_checkpoint(checkpoint)
    assert saved_id == checkpoint.checkpoint_id

    # Load checkpoint
    loaded_checkpoint = storage.load_checkpoint(checkpoint.checkpoint_id)
    assert loaded_checkpoint is not None
    assert loaded_checkpoint.checkpoint_id == checkpoint.checkpoint_id
    assert loaded_checkpoint.workflow_id == checkpoint.workflow_id
    assert loaded_checkpoint.messages == checkpoint.messages


def test_memory_checkpoint_storage_load_nonexistent():
    storage = MemoryCheckpointStorage()

    result = storage.load_checkpoint("nonexistent-id")
    assert result is None


def test_memory_checkpoint_storage_list_checkpoints():
    storage = MemoryCheckpointStorage()

    # Create checkpoints for different workflows
    checkpoint1 = WorkflowCheckpoint(workflow_id="workflow-1")
    checkpoint2 = WorkflowCheckpoint(workflow_id="workflow-1")
    checkpoint3 = WorkflowCheckpoint(workflow_id="workflow-2")

    storage.save_checkpoint(checkpoint1)
    storage.save_checkpoint(checkpoint2)
    storage.save_checkpoint(checkpoint3)

    # List checkpoints for workflow-1
    workflow1_checkpoints = storage.list_checkpoints("workflow-1")
    assert len(workflow1_checkpoints) == 2
    assert checkpoint1.checkpoint_id in workflow1_checkpoints
    assert checkpoint2.checkpoint_id in workflow1_checkpoints

    # List checkpoints for workflow-2
    workflow2_checkpoints = storage.list_checkpoints("workflow-2")
    assert len(workflow2_checkpoints) == 1
    assert checkpoint3.checkpoint_id in workflow2_checkpoints

    # List checkpoints for non-existent workflow
    empty_checkpoints = storage.list_checkpoints("nonexistent-workflow")
    assert len(empty_checkpoints) == 0


def test_memory_checkpoint_storage_delete():
    storage = MemoryCheckpointStorage()
    checkpoint = WorkflowCheckpoint(workflow_id="test-workflow")

    # Save checkpoint
    storage.save_checkpoint(checkpoint)
    assert storage.load_checkpoint(checkpoint.checkpoint_id) is not None

    # Delete checkpoint
    result = storage.delete_checkpoint(checkpoint.checkpoint_id)
    assert result is True

    # Verify deletion
    assert storage.load_checkpoint(checkpoint.checkpoint_id) is None

    # Try to delete again
    result = storage.delete_checkpoint(checkpoint.checkpoint_id)
    assert result is False


def test_file_checkpoint_storage_save_and_load():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)
        checkpoint = WorkflowCheckpoint(
            workflow_id="test-workflow",
            messages={"executor1": [{"data": "hello", "source_id": "test", "target_id": None}]},
            shared_state={"key": "value"},
        )

        # Save checkpoint
        saved_id = storage.save_checkpoint(checkpoint)
        assert saved_id == checkpoint.checkpoint_id

        # Verify file was created
        file_path = Path(temp_dir) / f"{checkpoint.checkpoint_id}.json"
        assert file_path.exists()

        # Load checkpoint
        loaded_checkpoint = storage.load_checkpoint(checkpoint.checkpoint_id)
        assert loaded_checkpoint is not None
        assert loaded_checkpoint.checkpoint_id == checkpoint.checkpoint_id
        assert loaded_checkpoint.workflow_id == checkpoint.workflow_id
        assert loaded_checkpoint.messages == checkpoint.messages
        assert loaded_checkpoint.shared_state == checkpoint.shared_state


def test_file_checkpoint_storage_load_nonexistent():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        result = storage.load_checkpoint("nonexistent-id")
        assert result is None


def test_file_checkpoint_storage_list_checkpoints():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create checkpoints for different workflows
        checkpoint1 = WorkflowCheckpoint(workflow_id="workflow-1")
        checkpoint2 = WorkflowCheckpoint(workflow_id="workflow-1")
        checkpoint3 = WorkflowCheckpoint(workflow_id="workflow-2")

        storage.save_checkpoint(checkpoint1)
        storage.save_checkpoint(checkpoint2)
        storage.save_checkpoint(checkpoint3)

        # List checkpoints for workflow-1
        workflow1_checkpoints = storage.list_checkpoints("workflow-1")
        assert len(workflow1_checkpoints) == 2
        assert checkpoint1.checkpoint_id in workflow1_checkpoints
        assert checkpoint2.checkpoint_id in workflow1_checkpoints

        # List checkpoints for workflow-2
        workflow2_checkpoints = storage.list_checkpoints("workflow-2")
        assert len(workflow2_checkpoints) == 1
        assert checkpoint3.checkpoint_id in workflow2_checkpoints


def test_file_checkpoint_storage_delete():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)
        checkpoint = WorkflowCheckpoint(workflow_id="test-workflow")

        # Save checkpoint
        storage.save_checkpoint(checkpoint)
        file_path = Path(temp_dir) / f"{checkpoint.checkpoint_id}.json"
        assert file_path.exists()

        # Delete checkpoint
        result = storage.delete_checkpoint(checkpoint.checkpoint_id)
        assert result is True
        assert not file_path.exists()

        # Try to delete again
        result = storage.delete_checkpoint(checkpoint.checkpoint_id)
        assert result is False


def test_file_checkpoint_storage_directory_creation():
    with tempfile.TemporaryDirectory() as temp_dir:
        nested_path = Path(temp_dir) / "nested" / "checkpoint" / "storage"
        storage = FileCheckpointStorage(nested_path)

        # Directory should be created
        assert nested_path.exists()
        assert nested_path.is_dir()

        # Should be able to save checkpoints
        checkpoint = WorkflowCheckpoint(workflow_id="test")
        storage.save_checkpoint(checkpoint)

        file_path = nested_path / f"{checkpoint.checkpoint_id}.json"
        assert file_path.exists()


def test_file_checkpoint_storage_corrupted_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create a corrupted JSON file
        corrupted_file = Path(temp_dir) / "corrupted.json"
        with open(corrupted_file, "w") as f:
            f.write("{ invalid json }")

        # list_checkpoints should handle the corrupted file gracefully
        checkpoints = storage.list_checkpoints("any-workflow")
        assert checkpoints == []


def test_file_checkpoint_storage_json_serialization():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create checkpoint with complex nested data
        checkpoint = WorkflowCheckpoint(
            workflow_id="complex-workflow",
            messages={"executor1": [{"data": {"nested": {"value": 42}}, "source_id": "test", "target_id": None}]},
            shared_state={"list": [1, 2, 3], "dict": {"a": "b", "c": {"d": "e"}}, "bool": True, "null": None},
            executor_states={"executor1": {"state": "active", "config": {"timeout": 30, "retries": 3}}},
        )

        # Save and load
        storage.save_checkpoint(checkpoint)
        loaded = storage.load_checkpoint(checkpoint.checkpoint_id)

        assert loaded is not None
        assert loaded.messages == checkpoint.messages
        assert loaded.shared_state == checkpoint.shared_state
        assert loaded.executor_states == checkpoint.executor_states

        # Verify the JSON file is properly formatted
        file_path = Path(temp_dir) / f"{checkpoint.checkpoint_id}.json"
        with open(file_path) as f:
            data = json.load(f)

        assert data["messages"]["executor1"][0]["data"]["nested"]["value"] == 42
        assert data["shared_state"]["list"] == [1, 2, 3]
        assert data["shared_state"]["bool"] is True
        assert data["shared_state"]["null"] is None


def test_checkpoint_storage_protocol_compliance():
    # This test ensures both implementations have all required methods
    memory_storage = MemoryCheckpointStorage()

    with tempfile.TemporaryDirectory() as temp_dir:
        file_storage = FileCheckpointStorage(temp_dir)

        for storage in [memory_storage, file_storage]:
            # Test that all protocol methods exist and are callable
            assert hasattr(storage, "save_checkpoint")
            assert callable(storage.save_checkpoint)
            assert hasattr(storage, "load_checkpoint")
            assert callable(storage.load_checkpoint)
            assert hasattr(storage, "list_checkpoints")
            assert callable(storage.list_checkpoints)
            assert hasattr(storage, "delete_checkpoint")
            assert callable(storage.delete_checkpoint)
