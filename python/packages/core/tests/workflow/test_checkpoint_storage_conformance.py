# Copyright (c) Microsoft. All rights reserved.

"""Conformance tests for the CheckpointStorage ownership contract."""

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
    """Yield each in-tree checkpoint storage backend."""
    if request.param == "memory":
        return InMemoryCheckpointStorage()
    return FileCheckpointStorage(tmp_path / "conformance")


def _conformance_checkpoint(workflow_name: str = "conformance-workflow") -> WorkflowCheckpoint:
    return WorkflowCheckpoint(
        workflow_name=workflow_name,
        graph_signature_hash="conformance-hash",
        state={
            "shared": {"counter": 0, "history": ["initial"]},
            "_executor_state": {"executor1": {"visits": ["first"]}},
        },
        messages={
            "executor1": [
                WorkflowMessage(data={"text": "hello", "tags": ["initial"]}, source_id="src", target_id="tgt")
            ]
        },
        pending_request_info_events={
            "req1": WorkflowEvent.request_info(
                request_id="req1",
                source_executor_id="executor1",
                request_data={"payload": ["initial"]},
                response_type=str,
            )
        },
        metadata={"tags": ["initial"]},
    )


def _mutate(checkpoint: WorkflowCheckpoint) -> None:
    checkpoint.state["shared"]["counter"] = 999
    checkpoint.state["shared"]["history"].append("mutated")
    checkpoint.state["_executor_state"]["executor1"]["visits"].append("mutated")
    cast(dict[str, Any], checkpoint.messages["executor1"][0].data)["tags"].append("mutated")
    cast(dict[str, Any], checkpoint.pending_request_info_events["req1"].data)["payload"].append("mutated")
    checkpoint.metadata["tags"].append("mutated")


def _assert_pristine(checkpoint: WorkflowCheckpoint) -> None:
    assert checkpoint.state["shared"] == {"counter": 0, "history": ["initial"]}
    assert checkpoint.state["_executor_state"]["executor1"]["visits"] == ["first"]
    assert cast(dict[str, Any], checkpoint.messages["executor1"][0].data)["tags"] == ["initial"]
    assert cast(dict[str, Any], checkpoint.pending_request_info_events["req1"].data)["payload"] == ["initial"]
    assert checkpoint.metadata["tags"] == ["initial"]


async def test_load_returns_caller_owned_copy(conformance_storage: CheckpointStorage) -> None:
    checkpoint = _conformance_checkpoint()
    await conformance_storage.save(checkpoint)

    loaded = await conformance_storage.load(checkpoint.checkpoint_id)
    _mutate(loaded)

    _assert_pristine(await conformance_storage.load(checkpoint.checkpoint_id))


async def test_repeated_loads_are_independent(conformance_storage: CheckpointStorage) -> None:
    checkpoint = _conformance_checkpoint()
    await conformance_storage.save(checkpoint)

    first = await conformance_storage.load(checkpoint.checkpoint_id)
    second = await conformance_storage.load(checkpoint.checkpoint_id)
    assert first is not second

    _mutate(first)
    _assert_pristine(second)


async def test_get_latest_returns_caller_owned_copy(conformance_storage: CheckpointStorage) -> None:
    checkpoint = _conformance_checkpoint()
    await conformance_storage.save(checkpoint)

    latest = await conformance_storage.get_latest(workflow_name=checkpoint.workflow_name)
    assert latest is not None
    _mutate(latest)

    reloaded = await conformance_storage.get_latest(workflow_name=checkpoint.workflow_name)
    assert reloaded is not None
    _assert_pristine(reloaded)


async def test_list_checkpoints_returns_caller_owned_copies(conformance_storage: CheckpointStorage) -> None:
    checkpoint = _conformance_checkpoint()
    await conformance_storage.save(checkpoint)

    listed = await conformance_storage.list_checkpoints(workflow_name=checkpoint.workflow_name)
    assert len(listed) == 1
    _mutate(listed[0])

    relisted = await conformance_storage.list_checkpoints(workflow_name=checkpoint.workflow_name)
    assert len(relisted) == 1
    _assert_pristine(relisted[0])


async def test_save_snapshots_at_call_time(conformance_storage: CheckpointStorage) -> None:
    checkpoint = _conformance_checkpoint()
    await conformance_storage.save(checkpoint)

    _mutate(checkpoint)

    _assert_pristine(await conformance_storage.load(checkpoint.checkpoint_id))


async def test_list_checkpoints_filters_by_workflow_name(conformance_storage: CheckpointStorage) -> None:
    first = _conformance_checkpoint("workflow-a")
    second = _conformance_checkpoint("workflow-b")
    await conformance_storage.save(first)
    await conformance_storage.save(second)

    listed_a = await conformance_storage.list_checkpoints(workflow_name="workflow-a")
    listed_b = await conformance_storage.list_checkpoints(workflow_name="workflow-b")

    assert {checkpoint.checkpoint_id for checkpoint in listed_a} == {first.checkpoint_id}
    assert {checkpoint.checkpoint_id for checkpoint in listed_b} == {second.checkpoint_id}


async def test_get_latest_returns_none_when_empty(conformance_storage: CheckpointStorage) -> None:
    assert await conformance_storage.get_latest(workflow_name="missing-workflow") is None


async def test_load_missing_id_raises(conformance_storage: CheckpointStorage) -> None:
    with pytest.raises(WorkflowCheckpointException):
        await conformance_storage.load("does-not-exist")


async def test_save_returns_id(conformance_storage: CheckpointStorage) -> None:
    checkpoint = _conformance_checkpoint()
    assert await conformance_storage.save(checkpoint) == checkpoint.checkpoint_id


def _filesystem_is_case_insensitive(path: Path) -> bool:
    probe = path / "CkAsE.probe"
    probe.write_text("x")
    try:
        return (path / "ckase.probe").exists()
    finally:
        probe.unlink()


async def test_file_save_rejects_case_variant_checkpoint_id(tmp_path: Path) -> None:
    """A case-only variant ID must not silently replace the other checkpoint (#9444)."""
    # Probe inside the test on tmp_path: a module-level probe races under
    # pytest-xdist workers sharing the source directory, and tmp_path is the
    # volume that actually holds the checkpoints.
    if not _filesystem_is_case_insensitive(tmp_path):
        pytest.skip("case-variant collision only occurs on case-insensitive filesystems")
    storage = FileCheckpointStorage(tmp_path / "checkpoints")
    first = WorkflowCheckpoint(
        workflow_name="first-workflow",
        graph_signature_hash="topology-a",
        checkpoint_id="Round-A",
        state={"marker": "first"},
    )
    second = WorkflowCheckpoint(
        workflow_name="second-workflow",
        graph_signature_hash="topology-b",
        checkpoint_id="round-a",
        state={"marker": "second"},
    )

    first_id = await storage.save(first)
    with pytest.raises(WorkflowCheckpointException, match="collides"):
        await storage.save(second)

    # The first checkpoint survives untouched: its data and listing are intact.
    restored = await storage.load(first_id)
    assert restored.checkpoint_id == "Round-A"
    assert restored.workflow_name == "first-workflow"
    assert restored.state["marker"] == "first"
    listed = await storage.list_checkpoint_ids(workflow_name="first-workflow")
    assert listed == ["Round-A"]

    # Re-saving the exact same ID remains a normal update, not a collision.
    first.state["marker"] = "first-updated"
    assert await storage.save(first) == "Round-A"
    assert (await storage.load("Round-A")).state["marker"] == "first-updated"


def _filesystem_folds_unicode_normalization(path: Path) -> bool:
    """True when the volume treats NFC and NFD spellings of a name as one file."""
    import unicodedata

    nfc = unicodedata.normalize("NFC", "café-norm.probe")
    nfd = unicodedata.normalize("NFD", "café-norm.probe")
    probe = path / nfc
    probe.write_text("x")
    try:
        return (path / nfd).exists()
    finally:
        probe.unlink()


@pytest.mark.parametrize("mixed_case", [False, True], ids=["nfc-nfd", "case-nfc-nfd"])
async def test_file_save_rejects_normalization_variant_checkpoint_id(tmp_path: Path, mixed_case: bool) -> None:
    """An NFC/NFD spelling variant must not silently replace a checkpoint (#9466).

    APFS and HFS+ fold Unicode normalization forms, so two IDs that differ only
    in normalization name one file there; str.casefold() alone does not catch
    it. On volumes without that fold the two files coexist and there is nothing
    to reject.
    """
    import unicodedata

    if not _filesystem_folds_unicode_normalization(tmp_path):
        pytest.skip("normalization-variant collision only occurs on normalization-insensitive filesystems")
    first_spelling = unicodedata.normalize("NFC", "Café-1" if mixed_case else "café-1")
    second_spelling = unicodedata.normalize("NFD", "café-1")
    assert first_spelling != second_spelling  # the test would be vacuous otherwise

    storage = FileCheckpointStorage(tmp_path / "checkpoints")
    first = WorkflowCheckpoint(
        workflow_name="first-workflow",
        graph_signature_hash="topology-a",
        checkpoint_id=first_spelling,
        state={"marker": "first"},
    )
    second = WorkflowCheckpoint(
        workflow_name="second-workflow",
        graph_signature_hash="topology-b",
        checkpoint_id=second_spelling,
        state={"marker": "second"},
    )

    first_id = await storage.save(first)
    with pytest.raises(WorkflowCheckpointException, match="collides"):
        await storage.save(second)

    restored = await storage.load(first_id)
    assert restored.checkpoint_id == first_spelling
    assert restored.state["marker"] == "first"

    # Re-saving the exact same spelling remains a normal update.
    first.state["marker"] = "first-updated"
    assert await storage.save(first) == first_spelling
