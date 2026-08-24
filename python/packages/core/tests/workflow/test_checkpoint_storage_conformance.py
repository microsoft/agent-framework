# Copyright (c) Microsoft. All rights reserved.
"""Conformance tests for checkpoint storage backends.

These tests verify that all checkpoint storage implementations satisfy the
ownership contract defined in the CheckpointStorage Protocol.
"""
import copy
import pickle
from dataclasses import dataclass

import pytest

from agent_framework import (
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
    WorkflowCheckpointException,
    WorkflowEvent,
    register_checkpoint_type,
)
from agent_framework._workflows._runner_context import WorkflowMessage


# Test dataclass for pickle-serializable but not deepcopyable regression test
@dataclass
class _PickleableNotDeepcopyable:
    """A class that is pickle-serializable but explicitly rejects deepcopy."""

    value: str

    def __deepcopy__(self, memo):
        raise TypeError("This class explicitly rejects deepcopy for testing purposes")

    def __reduce__(self):
        # Custom pickle support that doesn't require deepcopy
        return (_PickleableNotDeepcopyable, (self.value,))


# Register the test type for restricted checkpoint deserialization
register_checkpoint_type(_PickleableNotDeepcopyable)


@pytest.fixture(params=["memory", "file"])
def conformance_storage(request, tmp_path):
    """Parametrized fixture returning both in-tree storage backends."""
    if request.param == "memory":
        return InMemoryCheckpointStorage()
    return FileCheckpointStorage(tmp_path / "conformance")


class TestCheckpointStorageOwnership:
    """Tests for checkpoint ownership contract compliance."""

    async def test_load_returns_caller_owned_copy(self, conformance_storage):
        """Mutating a loaded checkpoint must not affect the stored checkpoint."""
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={"key": "original"},
        )
        saved_id = await conformance_storage.save(checkpoint)
        loaded = await conformance_storage.load(saved_id)
        loaded.state["key"] = "mutated"

        # Reload to verify the stored checkpoint is unchanged
        reloaded = await conformance_storage.load(saved_id)
        assert reloaded.state["key"] == "original"

    async def test_repeated_load_returns_independent_objects(self, conformance_storage):
        """Repeated load calls must return independent objects from each other."""
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={"key": "original"},
        )
        saved_id = await conformance_storage.save(checkpoint)
        loaded1 = await conformance_storage.load(saved_id)
        loaded2 = await conformance_storage.load(saved_id)

        # Mutate the first loaded checkpoint
        loaded1.state["key"] = "mutated"

        # The second loaded checkpoint should be unaffected
        assert loaded2.state["key"] == "original"

    async def test_get_latest_returns_caller_owned_copy(self, conformance_storage):
        """Mutating get_latest result must not affect the stored checkpoint."""
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={"key": "original"},
        )
        await conformance_storage.save(checkpoint)
        latest = await conformance_storage.get_latest(workflow_name="test-workflow")
        assert latest is not None
        latest.state["key"] = "mutated"

        # Reload to verify the stored checkpoint is unchanged
        reloaded = await conformance_storage.get_latest(workflow_name="test-workflow")
        assert reloaded is not None
        assert reloaded.state["key"] == "original"

    async def test_list_checkpoints_returns_caller_owned_copies(self, conformance_storage):
        """Mutating list_checkpoints results must not affect stored checkpoints."""
        checkpoint1 = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={"key": "checkpoint1"},
        )
        checkpoint2 = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={"key": "checkpoint2"},
        )
        await conformance_storage.save(checkpoint1)
        await conformance_storage.save(checkpoint2)
        checkpoints = await conformance_storage.list_checkpoints(workflow_name="test-workflow")
        checkpoints[0].state["key"] = "mutated"

        # Reload to verify stored checkpoints are unchanged
        reloaded = await conformance_storage.list_checkpoints(workflow_name="test-workflow")
        assert all(cp.state["key"] != "mutated" for cp in reloaded)

    async def test_save_snapshots_at_call_time(self, conformance_storage):
        """Mutating caller's object after save must not affect what was stored."""
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={"key": "original"},
        )
        saved_id = await conformance_storage.save(checkpoint)

        # Mutate the original checkpoint object after save
        checkpoint.state["key"] = "mutated"

        # Reload to verify the stored checkpoint has the original value
        reloaded = await conformance_storage.load(saved_id)
        assert reloaded.state["key"] == "original"

    async def test_save_snapshots_nested_mutation(self, conformance_storage):
        """Mutating nested structures after save must not affect what was stored."""
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={"nested": {"deep": {"value": "original"}}},
        )
        saved_id = await conformance_storage.save(checkpoint)

        # Mutate nested structure after save
        checkpoint.state["nested"]["deep"]["value"] = "mutated"

        # Reload to verify the stored checkpoint has the original value
        reloaded = await conformance_storage.load(saved_id)
        assert reloaded.state["nested"]["deep"]["value"] == "original"

    async def test_list_checkpoints_filters_by_workflow_name(self, conformance_storage):
        """list_checkpoints must correctly filter by workflow_name."""
        checkpoint1 = WorkflowCheckpoint(
            workflow_name="workflow-1",
            graph_signature_hash="hash-1",
        )
        checkpoint2 = WorkflowCheckpoint(
            workflow_name="workflow-2",
            graph_signature_hash="hash-2",
        )
        checkpoint3 = WorkflowCheckpoint(
            workflow_name="workflow-1",
            graph_signature_hash="hash-3",
        )
        await conformance_storage.save(checkpoint1)
        await conformance_storage.save(checkpoint2)
        await conformance_storage.save(checkpoint3)

        workflow1_checkpoints = await conformance_storage.list_checkpoints(workflow_name="workflow-1")
        assert len(workflow1_checkpoints) == 2
        assert all(cp.workflow_name == "workflow-1" for cp in workflow1_checkpoints)

        workflow2_checkpoints = await conformance_storage.list_checkpoints(workflow_name="workflow-2")
        assert len(workflow2_checkpoints) == 1
        assert workflow2_checkpoints[0].workflow_name == "workflow-2"

    async def test_get_latest_returns_none_for_unknown_workflow(self, conformance_storage):
        """get_latest must return None for an unknown workflow, not raise."""
        latest = await conformance_storage.get_latest(workflow_name="unknown-workflow")
        assert latest is None

    async def test_load_with_missing_id_raises_exception(self, conformance_storage):
        """load with a missing checkpoint_id must raise WorkflowCheckpointException."""
        with pytest.raises(WorkflowCheckpointException):
            await conformance_storage.load("nonexistent-id")

    async def test_save_returns_checkpoint_id(self, conformance_storage):
        """save must return the checkpoint_id."""
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
        )
        saved_id = await conformance_storage.save(checkpoint)
        assert saved_id == checkpoint.checkpoint_id


class TestCheckpointStorageNestedMutation:
    """Tests for isolation of nested mutable structures."""

    async def test_nested_state_mutation_isolated(self, conformance_storage):
        """Mutating nested state structures must not affect stored checkpoint."""
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={"nested": {"deep": {"value": "original"}}},
        )
        saved_id = await conformance_storage.save(checkpoint)
        loaded = await conformance_storage.load(saved_id)
        loaded.state["nested"]["deep"]["value"] = "mutated"
        reloaded = await conformance_storage.load(saved_id)
        assert reloaded.state["nested"]["deep"]["value"] == "original"

    async def test_messages_data_mutation_isolated(self, conformance_storage):
        """Mutating WorkflowMessage.data must not affect stored checkpoint."""
        message = WorkflowMessage(source_id="test", target_id="test", data="original")
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            messages={"executor1": [message]},
        )
        saved_id = await conformance_storage.save(checkpoint)
        loaded = await conformance_storage.load(saved_id)
        loaded.messages["executor1"][0].data = "mutated"
        reloaded = await conformance_storage.load(saved_id)
        assert reloaded.messages["executor1"][0].data == "original"

    async def test_pending_request_info_events_data_mutation_isolated(self, conformance_storage):
        """Mutating pending_request_info_events.data must not affect stored checkpoint."""
        event = WorkflowEvent(type="test", data="original")
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            pending_request_info_events={"req1": event},
        )
        saved_id = await conformance_storage.save(checkpoint)
        loaded = await conformance_storage.load(saved_id)
        loaded.pending_request_info_events["req1"].data = "mutated"
        reloaded = await conformance_storage.load(saved_id)
        assert reloaded.pending_request_info_events["req1"].data == "original"

    async def test_metadata_mutation_isolated(self, conformance_storage):
        """Mutating metadata must not affect stored checkpoint."""
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            metadata={"nested": {"value": "original"}},
        )
        saved_id = await conformance_storage.save(checkpoint)
        loaded = await conformance_storage.load(saved_id)
        loaded.metadata["nested"]["value"] = "mutated"
        reloaded = await conformance_storage.load(saved_id)
        assert reloaded.metadata["nested"]["value"] == "original"


class TestPickleRoundtripRegression:
    """Regression test for pickle-serializable but not deepcopyable values.

    This test MUST FAIL against a deepcopy-based implementation and MUST PASS
    against the pickle round-trip implementation, proving the regression is closed.
    """

    async def test_pickleable_not_deepcopyable_roundtrips(self, conformance_storage):
        """Values that are pickle-serializable but not deepcopyable must roundtrip correctly.

        This test is skipped for InMemoryCheckpointStorage since it uses copy.deepcopy()
        instead of pickle round-trip for isolation.
        """
        # Skip for memory backend - it uses deepcopy, not pickle
        if isinstance(conformance_storage, InMemoryCheckpointStorage):
            pytest.skip("InMemoryCheckpointStorage uses copy.deepcopy(), not pickle round-trip")

        # This value would fail with copy.deepcopy but works with pickle round-trip
        test_value = _PickleableNotDeepcopyable(value="test")

        # Verify it's not deepcopyable (this should raise)
        with pytest.raises(TypeError, match="explicitly rejects deepcopy"):
            copy.deepcopy(test_value)

        # But it should be pickle-serializable
        pickled = pickle.dumps(test_value)
        unpickled = pickle.loads(pickled)
        assert unpickled.value == "test"

        # Now test that it roundtrips through checkpoint storage
        checkpoint = WorkflowCheckpoint(
            workflow_name="test-workflow",
            graph_signature_hash="test-hash",
            state={"custom": test_value},
        )
        saved_id = await conformance_storage.save(checkpoint)
        loaded = await conformance_storage.load(saved_id)
        assert isinstance(loaded.state["custom"], _PickleableNotDeepcopyable)
        assert loaded.state["custom"].value == "test"

        # Verify it's truly isolated
        loaded.state["custom"].value = "mutated"
        reloaded = await conformance_storage.load(saved_id)
        assert reloaded.state["custom"].value == "test"
