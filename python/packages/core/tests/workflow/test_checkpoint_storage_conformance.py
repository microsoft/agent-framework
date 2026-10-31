# Copyright (c) Microsoft. All rights reserved.

"""Conformance tests for the CheckpointStorage ownership contract."""

from __future__ import annotations

import asyncio
import threading
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


async def test_file_save_rejects_path_bearing_alias_checkpoint_id(tmp_path: Path) -> None:
    """A path-bearing ID that resolves to another checkpoint's file must not replace it.

    ``./Round-A`` and ``Round-A`` resolve to the same ``Round-A.json`` but are
    different IDs. The collision guard compared full IDs against basenames, so a
    prefixed ID found no variant and skipped the persisted-identity check,
    silently overwriting the first checkpoint on a folding filesystem (#9466).
    """
    storage = FileCheckpointStorage(tmp_path / "checkpoints")
    first = WorkflowCheckpoint(
        workflow_name="first-workflow",
        graph_signature_hash="topology-a",
        checkpoint_id="Round-A",
        state={"marker": "first"},
    )
    alias = WorkflowCheckpoint(
        workflow_name="second-workflow",
        graph_signature_hash="topology-b",
        checkpoint_id="./Round-A",
        state={"marker": "second"},
    )

    first_id = await storage.save(first)
    with pytest.raises(WorkflowCheckpointException, match="collides"):
        await storage.save(alias)

    # The first checkpoint survives untouched.
    restored = await storage.load(first_id)
    assert restored.checkpoint_id == "Round-A"
    assert restored.state["marker"] == "first"
    assert await storage.list_checkpoint_ids(workflow_name="first-workflow") == ["Round-A"]


async def test_file_load_rejects_case_variant_checkpoint_id(tmp_path: Path) -> None:
    """A variant ID must not read another checkpoint's data (#9466 review).

    On a folding filesystem ``load("round-a")`` resolves to the stored
    ``Round-A.json``; under fail-closed it names no checkpoint at all.
    """
    if not _filesystem_is_case_insensitive(tmp_path):
        pytest.skip("case-variant collision only occurs on case-insensitive filesystems")
    storage = FileCheckpointStorage(tmp_path / "checkpoints")
    first = WorkflowCheckpoint(
        workflow_name="first-workflow",
        graph_signature_hash="topology-a",
        checkpoint_id="Round-A",
        state={"marker": "first"},
    )
    await storage.save(first)

    with pytest.raises(WorkflowCheckpointException, match="spelled 'Round-A'"):
        await storage.load("round-a")

    # The stored checkpoint is untouched and still reachable under its own ID.
    restored = await storage.load("Round-A")
    assert restored.state["marker"] == "first"


async def test_file_delete_rejects_case_variant_checkpoint_id(tmp_path: Path) -> None:
    """A variant ID must not delete another checkpoint (#9466 review)."""
    if not _filesystem_is_case_insensitive(tmp_path):
        pytest.skip("case-variant collision only occurs on case-insensitive filesystems")
    storage = FileCheckpointStorage(tmp_path / "checkpoints")
    first = WorkflowCheckpoint(
        workflow_name="first-workflow",
        graph_signature_hash="topology-a",
        checkpoint_id="Round-A",
        state={"marker": "first"},
    )
    await storage.save(first)

    with pytest.raises(WorkflowCheckpointException, match="spelled 'Round-A'"):
        await storage.delete("round-a")

    assert (await storage.load("Round-A")).state["marker"] == "first"
    assert await storage.list_checkpoint_ids(workflow_name="first-workflow") == ["Round-A"]


async def test_concurrent_variant_saves_do_not_overwrite(tmp_path: Path) -> None:
    """Two first-time variant saves must not both pass the guard (#9466 review).

    The collision check used to run before the write was queued, so both saves
    observed "no destination" and the second atomic replace silently won.
    """
    if not _filesystem_is_case_insensitive(tmp_path):
        pytest.skip("case-variant collision only occurs on case-insensitive filesystems")
    storage = FileCheckpointStorage(tmp_path / "checkpoints")
    upper = WorkflowCheckpoint(
        workflow_name="upper-workflow",
        graph_signature_hash="topology-a",
        checkpoint_id="Round-B",
        state={"marker": "upper"},
    )
    lower = WorkflowCheckpoint(
        workflow_name="lower-workflow",
        graph_signature_hash="topology-b",
        checkpoint_id="round-b",
        state={"marker": "lower"},
    )

    results = await asyncio.gather(storage.save(upper), storage.save(lower), return_exceptions=True)
    errors = [r for r in results if isinstance(r, WorkflowCheckpointException)]
    saved_ids = [r for r in results if isinstance(r, str)]
    assert len(errors) == 1, f"expected exactly one save to be rejected, got {results!r}"
    assert "collides" in str(errors[0])
    assert len(saved_ids) == 1

    # Whichever spelling won keeps its own data; nothing is silently replaced.
    workflow_name = f"{'upper' if saved_ids[0] == 'Round-B' else 'lower'}-workflow"
    stored = await storage.list_checkpoint_ids(workflow_name=workflow_name)
    assert stored == [saved_ids[0]]
    assert (await storage.load(saved_ids[0])).state["marker"] == ("upper" if saved_ids[0] == "Round-B" else "lower")


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


async def test_decomposed_listing_uses_persisted_checkpoint_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HFS+ spelling changes must not hide or conflate checkpoint identities."""
    import unicodedata

    nfc = unicodedata.normalize("NFC", "café-identity")
    nfd = unicodedata.normalize("NFD", nfc)
    storage = FileCheckpointStorage(tmp_path / "checkpoints")
    first = WorkflowCheckpoint(
        workflow_name="first-workflow",
        graph_signature_hash="topology-a",
        checkpoint_id=nfc,
        state={"marker": "first"},
    )
    await storage.save(first)

    original_iterdir = Path.iterdir
    original_validate = storage._validate_file_path

    def decomposed_iterdir(path: Path):
        if path == storage.storage_path:
            return iter([Path(f"{nfd}.json")])
        return original_iterdir(path)

    def folded_validate(checkpoint_id: str) -> Path:
        if checkpoint_id == nfd:
            return storage.storage_path / f"{nfc}.json"
        return original_validate(checkpoint_id)

    monkeypatch.setattr(Path, "iterdir", decomposed_iterdir)
    monkeypatch.setattr(storage, "_validate_file_path", folded_validate)

    second = WorkflowCheckpoint(
        workflow_name="second-workflow",
        graph_signature_hash="topology-b",
        checkpoint_id=nfd,
        state={"marker": "second"},
    )
    with pytest.raises(WorkflowCheckpointException, match="collides"):
        await storage.save(second)

    first.state["marker"] = "first-updated"
    assert await storage.save(first) == nfc
    restored = await storage.load(nfc)
    assert restored.checkpoint_id == nfc
    assert restored.state["marker"] == "first-updated"
    assert await storage.delete(nfc) is True


async def test_file_delete_absent_variant_returns_false_on_case_sensitive_filesystem(tmp_path: Path) -> None:
    """An absent independent ID returns False even when a folded sibling exists."""
    if _filesystem_is_case_insensitive(tmp_path):
        pytest.skip("missing-variant delete contract requires a case-sensitive filesystem")
    storage = FileCheckpointStorage(tmp_path / "checkpoints")
    checkpoint = WorkflowCheckpoint(
        workflow_name="first-workflow",
        graph_signature_hash="topology-a",
        checkpoint_id="Round-A",
        state={"marker": "first"},
    )
    await storage.save(checkpoint)

    assert await storage.delete("round-a") is False
    assert (await storage.load("Round-A")).state["marker"] == "first"


@pytest.mark.parametrize("operation", ["save", "load", "delete"])
async def test_file_directory_verification_stays_off_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """A slow directory scan must not stall unrelated event-loop work."""
    storage = FileCheckpointStorage(tmp_path / "checkpoints")
    checkpoint = WorkflowCheckpoint(
        workflow_name="workflow",
        graph_signature_hash="topology",
        checkpoint_id="Round-C",
        state={"marker": "value"},
    )
    await storage.save(checkpoint)

    original_iterdir = Path.iterdir
    release_scan = threading.Event()

    def slow_iterdir(path: Path):
        if path != storage.storage_path:
            return original_iterdir(path)

        def entries():
            release_scan.wait(timeout=5)
            for index in range(2000):
                yield Path(f"other-{index}.json")
            yield from original_iterdir(path)

        return entries()

    monkeypatch.setattr(Path, "iterdir", slow_iterdir)
    beats = 0
    stop_heartbeat = False

    async def heartbeat() -> None:
        nonlocal beats
        while not stop_heartbeat:
            beats += 1
            await asyncio.sleep(0.005)

    heartbeat_task = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)
    timer = threading.Timer(0.1, release_scan.set)
    timer.start()
    try:
        if operation == "save":
            await storage.save(checkpoint)
        elif operation == "load":
            await storage.load(checkpoint.checkpoint_id)
        else:
            await storage.delete(checkpoint.checkpoint_id)
    finally:
        release_scan.set()
        stop_heartbeat = True
        timer.join()
        await heartbeat_task

    assert beats >= 3, f"{operation} blocked the event loop during directory verification"
