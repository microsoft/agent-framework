# Copyright (c) Microsoft. All rights reserved.

"""Conformance tests for the CheckpointStorage ownership contract.

A checkpoint handed to the caller is owned by the caller, and a checkpoint
handed to ``save()`` is snapshotted at call time. Backends that serialize
(file, Cosmos) get this for free because decoding allocates a fresh object
graph; backends that hold live objects must copy explicitly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from agent_framework import (
    CheckpointStorage,
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
    WorkflowCheckpointException,
    WorkflowEvent,
)
from agent_framework._workflows._runner_context import WorkflowMessage


@pytest.fixture(params=["memory", "file"])
def conformance_storage(request: pytest.FixtureRequest, tmp_path: Path) -> CheckpointStorage:
    """Yield each in-tree checkpoint storage backend for the shared contract tests."""
    if request.param == "memory":
        return InMemoryCheckpointStorage()
    return FileCheckpointStorage(tmp_path / "conformance")


def _conformance_checkpoint(workflow_name: str = "conformance-workflow") -> WorkflowCheckpoint:
    """Build a checkpoint whose object graph holds nested mutable containers."""
    return WorkflowCheckpoint(
        workflow_name=workflow_name,
        graph_signature_hash="conformance-hash",
        state={
            "shared": {"counter": 0, "history": ["initial"]},
            "_executor_state": {"executor1": {"visits": ["first"]}},
        },
        messages={
            "executor1": [
                WorkflowMessage(
                    data={"text": "hello", "tags": ["initial"]},
                    source_id="src",
                    target_id="tgt",
                )
            ]
        },
        pending_request_info_events={
            "req1": WorkflowEvent.request_info(
                request_id="req1",
                source_executor_id="executor1",
                request_data={"payload": ["initial"]},
                response_type=str,
            ),
        },
        metadata={"tags": ["initial"]},
    )


def _mutate(checkpoint: WorkflowCheckpoint) -> None:
    """Mutate every nested container the ownership contract covers."""
    checkpoint.state["shared"]["counter"] = 999
    checkpoint.state["shared"]["history"].append("mutated")
    checkpoint.state["_executor_state"]["executor1"]["visits"].append("mutated")
    cast(dict[str, Any], checkpoint.messages["executor1"][0].data)["tags"].append("mutated")
    cast(dict[str, Any], checkpoint.pending_request_info_events["req1"].data)["payload"].append("mutated")
    checkpoint.metadata["tags"].append("mutated")


def _assert_pristine(checkpoint: WorkflowCheckpoint) -> None:
    """Assert nested containers still hold their original values."""
    assert checkpoint.state["shared"]["counter"] == 0
    assert checkpoint.state["shared"]["history"] == ["initial"]
    assert checkpoint.state["_executor_state"]["executor1"]["visits"] == ["first"]
    assert cast(dict[str, Any], checkpoint.messages["executor1"][0].data)["tags"] == ["initial"]
    assert cast(dict[str, Any], checkpoint.pending_request_info_events["req1"].data)["payload"] == ["initial"]
    assert checkpoint.metadata["tags"] == ["initial"]


async def test_conformance_load_returns_caller_owned_copy(conformance_storage: CheckpointStorage) -> None:
    """Mutating a loaded checkpoint must not alter what the backend has stored."""
    checkpoint = _conformance_checkpoint()
    await conformance_storage.save(checkpoint)

    loaded = await conformance_storage.load(checkpoint.checkpoint_id)
    _mutate(loaded)

    reloaded = await conformance_storage.load(checkpoint.checkpoint_id)
    _assert_pristine(reloaded)


async def test_conformance_repeated_loads_are_independent(conformance_storage: CheckpointStorage) -> None:
    """Two loads of one checkpoint must not share mutable state."""
    checkpoint = _conformance_checkpoint()
    await conformance_storage.save(checkpoint)

    first = await conformance_storage.load(checkpoint.checkpoint_id)
    second = await conformance_storage.load(checkpoint.checkpoint_id)
    assert first is not second

    _mutate(first)
    _assert_pristine(second)


async def test_conformance_get_latest_returns_caller_owned_copy(conformance_storage: CheckpointStorage) -> None:
    """Mutating the result of get_latest must not alter stored state."""
    checkpoint = _conformance_checkpoint()
    await conformance_storage.save(checkpoint)

    latest = await conformance_storage.get_latest(workflow_name=checkpoint.workflow_name)
    assert latest is not None
    _mutate(latest)

    reloaded = await conformance_storage.get_latest(workflow_name=checkpoint.workflow_name)
    assert reloaded is not None
    _assert_pristine(reloaded)


async def test_conformance_list_checkpoints_returns_caller_owned_copies(
    conformance_storage: CheckpointStorage,
) -> None:
    """Mutating a checkpoint from list_checkpoints must not alter stored state."""
    checkpoint = _conformance_checkpoint()
    await conformance_storage.save(checkpoint)

    listed = await conformance_storage.list_checkpoints(workflow_name=checkpoint.workflow_name)
    assert len(listed) == 1
    _mutate(listed[0])

    relisted = await conformance_storage.list_checkpoints(workflow_name=checkpoint.workflow_name)
    assert len(relisted) == 1
    _assert_pristine(relisted[0])


async def test_conformance_save_snapshots_state_at_call_time(conformance_storage: CheckpointStorage) -> None:
    """Mutating the caller's object after save must not alter the stored checkpoint."""
    checkpoint = _conformance_checkpoint()
    await conformance_storage.save(checkpoint)

    _mutate(checkpoint)

    loaded = await conformance_storage.load(checkpoint.checkpoint_id)
    _assert_pristine(loaded)


async def test_conformance_list_checkpoints_filters_by_workflow_name(
    conformance_storage: CheckpointStorage,
) -> None:
    """list_checkpoints must continue to filter by workflow_name after isolation."""
    first = _conformance_checkpoint(workflow_name="workflow-a")
    second = _conformance_checkpoint(workflow_name="workflow-b")
    await conformance_storage.save(first)
    await conformance_storage.save(second)

    listed_a = await conformance_storage.list_checkpoints(workflow_name="workflow-a")
    listed_b = await conformance_storage.list_checkpoints(workflow_name="workflow-b")

    assert {cp.checkpoint_id for cp in listed_a} == {first.checkpoint_id}
    assert {cp.checkpoint_id for cp in listed_b} == {second.checkpoint_id}


async def test_conformance_get_latest_returns_none_when_empty(conformance_storage: CheckpointStorage) -> None:
    """get_latest must return None for an unknown workflow, not raise."""
    result = await conformance_storage.get_latest(workflow_name="missing-workflow")
    assert result is None


async def test_conformance_load_missing_id_raises(conformance_storage: CheckpointStorage) -> None:
    """load must raise WorkflowCheckpointException for an unknown checkpoint id."""
    with pytest.raises(WorkflowCheckpointException):
        await conformance_storage.load("does-not-exist")


async def test_conformance_save_returns_id(conformance_storage: CheckpointStorage) -> None:
    """save must return the checkpoint_id."""
    checkpoint = _conformance_checkpoint()
    result = await conformance_storage.save(checkpoint)
    assert result == checkpoint.checkpoint_id
