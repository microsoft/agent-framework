# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for https://github.com/microsoft/agent-framework/issues/7683.

The InMemoryCheckpointStorage must return deep copies from
``load()``, ``list_checkpoints()``, and ``get_latest()`` so that callers
cannot mutate the storage backend's internal checkpoint objects. This
matches the defensive copy already applied in ``save()``.

These tests import directly from ``_workflows._checkpoint`` and
``agent_framework.exceptions`` to avoid pulling the top-level
``agent_framework`` package, which has heavy runtime dependencies
(opentelemetry, etc.) that are not relevant to the isolation contract
under test.

The tests are written as synchronous functions that drive an asyncio
event loop internally. This keeps the test file runnable both locally
(without ``pytest-asyncio``) and in CI (where the project's standard
``asyncio_mode = "auto"`` setting would also be honoured).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from agent_framework._workflows._checkpoint import (
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
)
from agent_framework.exceptions import WorkflowCheckpointException


def _make_checkpoint(
    *,
    checkpoint_id: str,
    workflow_name: str = "demo",
    state: dict | None = None,
    messages: dict | None = None,
    timestamp: str | None = None,
) -> WorkflowCheckpoint:
    return WorkflowCheckpoint(
        workflow_name=workflow_name,
        graph_signature_hash="hash-1",
        checkpoint_id=checkpoint_id,
        previous_checkpoint_id=None,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        messages=messages if messages is not None else {},
        state=state if state is not None else {"history": ["step-1"]},
        pending_request_info_events={},
        iteration_count=1,
    )


def test_load_returns_isolated_checkpoint() -> None:
    """Mutating a loaded checkpoint must not affect the storage backend."""

    async def _run() -> None:
        storage = InMemoryCheckpointStorage()
        await storage.save(_make_checkpoint(checkpoint_id="cp-1"))

        loaded = await storage.load("cp-1")
        loaded.state["history"].append("step-2")  # mutate the returned snapshot

        reloaded = await storage.load("cp-1")
        assert reloaded.state == {"history": ["step-1"]}

    asyncio.run(_run())


def test_load_returns_isolated_messages() -> None:
    """The ``messages`` field is also nested mutable state and must be isolated."""

    async def _run() -> None:
        storage = InMemoryCheckpointStorage()
        checkpoint = _make_checkpoint(
            checkpoint_id="cp-1",
            state={"history": ["step-1"]},
            messages={"src": ["msg-1"]},
        )
        await storage.save(checkpoint)

        loaded = await storage.load("cp-1")
        loaded.messages["src"].append("msg-2")

        reloaded = await storage.load("cp-1")
        assert reloaded.messages == {"src": ["msg-1"]}

    asyncio.run(_run())


def test_list_checkpoints_returns_isolated_snapshots() -> None:
    """Mutating checkpoints returned from list_checkpoints must not affect the backend."""

    async def _run() -> None:
        storage = InMemoryCheckpointStorage()
        await storage.save(_make_checkpoint(checkpoint_id="cp-1"))
        await storage.save(_make_checkpoint(checkpoint_id="cp-2"))

        listed = await storage.list_checkpoints(workflow_name="demo")
        assert len(listed) == 2

        for cp in listed:
            cp.state["history"].append("step-2")  # mutate each returned snapshot

        # Reload: storage must be untouched.
        cp1 = await storage.load("cp-1")
        cp2 = await storage.load("cp-2")
        assert cp1.state == {"history": ["step-1"]}
        assert cp2.state == {"history": ["step-1"]}

    asyncio.run(_run())


def test_list_checkpoints_filters_by_workflow_name() -> None:
    """list_checkpoints must continue to filter by workflow_name after isolation."""

    async def _run() -> None:
        storage = InMemoryCheckpointStorage()
        await storage.save(_make_checkpoint(checkpoint_id="cp-1", workflow_name="a"))
        await storage.save(_make_checkpoint(checkpoint_id="cp-2", workflow_name="b"))

        listed_a = await storage.list_checkpoints(workflow_name="a")
        listed_b = await storage.list_checkpoints(workflow_name="b")

        assert {cp.checkpoint_id for cp in listed_a} == {"cp-1"}
        assert {cp.checkpoint_id for cp in listed_b} == {"cp-2"}

    asyncio.run(_run())


def test_get_latest_returns_isolated_snapshot() -> None:
    """Mutating the result of get_latest must not affect any stored checkpoint."""

    async def _run() -> None:
        storage = InMemoryCheckpointStorage()
        cp1 = _make_checkpoint(
            checkpoint_id="cp-1",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        cp2 = _make_checkpoint(
            checkpoint_id="cp-2",
            timestamp="2026-02-01T00:00:00+00:00",
        )
        await storage.save(cp1)
        await storage.save(cp2)

        latest = await storage.get_latest(workflow_name="demo")
        assert latest is not None
        assert latest.checkpoint_id == "cp-2"

        latest.state["history"].append("step-2")  # mutate the latest snapshot

        # Both stored checkpoints must be unchanged.
        reloaded_latest = await storage.get_latest(workflow_name="demo")
        assert reloaded_latest is not None
        assert reloaded_latest.state == {"history": ["step-1"]}
        # And the older one wasn't touched either.
        reloaded_cp1 = await storage.load("cp-1")
        assert reloaded_cp1.state == {"history": ["step-1"]}

    asyncio.run(_run())


def test_get_latest_returns_none_when_empty() -> None:
    """get_latest must return None for an unknown workflow, not raise."""

    async def _run() -> None:
        storage = InMemoryCheckpointStorage()
        result = await storage.get_latest(workflow_name="demo")
        assert result is None

    asyncio.run(_run())


def test_load_missing_id_raises() -> None:
    """load must raise WorkflowCheckpointException for an unknown checkpoint id."""

    async def _run() -> None:
        storage = InMemoryCheckpointStorage()
        try:
            await storage.load("does-not-exist")
        except WorkflowCheckpointException:
            return
        raise AssertionError("Expected WorkflowCheckpointException for missing checkpoint id")

    asyncio.run(_run())


def test_save_returns_id() -> None:
    """save must return the checkpoint_id (and the contract must hold post-isolation)."""

    async def _run() -> None:
        storage = InMemoryCheckpointStorage()
        result = await storage.save(_make_checkpoint(checkpoint_id="cp-1"))
        assert result == "cp-1"

    asyncio.run(_run())
