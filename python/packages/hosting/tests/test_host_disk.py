# Copyright (c) Microsoft. All rights reserved.

"""Tests for ``state_dir`` wired through :class:`AgentFrameworkHost`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agent_framework_hosting import (
    AgentFrameworkHost,
    ChannelContext,
    ChannelContribution,
    ChannelIdentity,
)

# Skip the whole module when the optional disk extra isn't installed.
pytest.importorskip("diskcache")


# --------------------------------------------------------------------------- #
# Test helpers                                                                  #
# --------------------------------------------------------------------------- #


class _AgentStub:
    """Bare-minimum SupportsAgentRun stub for host construction."""

    async def run(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - unused
        return None


class _ChannelStub:
    name = "stub"
    path = "/stub"

    def contribute(self, _context: ChannelContext) -> ChannelContribution:
        return ChannelContribution()


def _close_host_disk(host: AgentFrameworkHost) -> None:
    """Mirror the lifespan shutdown ordering for tests that simulate restart.

    The real shutdown order is ``runner.shutdown()`` → ``sessions_store.close()``;
    both release their advisory file locks so a second host can take ownership.
    """
    runner = host._durable_task_runner
    try:
        asyncio.get_event_loop().run_until_complete(runner.shutdown(timeout=1.0))
    except RuntimeError:
        # No running loop; spin up a throw-away one.
        asyncio.run(runner.shutdown(timeout=1.0))
    if host._sessions_store is not None:
        host._sessions_store.close()


# --------------------------------------------------------------------------- #
# state_dir=None preserves the in-memory contract                             #
# --------------------------------------------------------------------------- #


def test_state_dir_none_keeps_plain_dicts(tmp_path: Path) -> None:
    """No store, no sessions persistence, no files written."""
    host = AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()])
    try:
        assert host._sessions_store is None
        assert isinstance(host._session_aliases, dict)
        assert isinstance(host._active, dict)
        assert isinstance(host._identities, dict)
        # No accidental disk writes anywhere under tmp_path.
        assert list(tmp_path.iterdir()) == []
    finally:
        # Nothing to close.
        pass


# --------------------------------------------------------------------------- #
# Single string state_dir creates default subfolders                          #
# --------------------------------------------------------------------------- #


def test_string_state_dir_creates_subfolders(tmp_path: Path) -> None:
    """Passing a single path expands to ``runner/`` and ``sessions/``."""
    host = AgentFrameworkHost(
        target=_AgentStub(),
        channels=[_ChannelStub()],
        state_dir=tmp_path,
    )
    try:
        assert host._sessions_store is not None
        assert (tmp_path / "runner").is_dir()
        assert (tmp_path / "sessions").is_dir()
    finally:
        _close_host_disk(host)


# --------------------------------------------------------------------------- #
# Per-component override via HostStatePaths-shaped dict                       #
# --------------------------------------------------------------------------- #


def test_per_component_paths(tmp_path: Path) -> None:
    """Dict form lets the caller route components to different roots."""
    runner_dir = tmp_path / "tasks"
    sessions_dir = tmp_path / "state"
    host = AgentFrameworkHost(
        target=_AgentStub(),
        channels=[_ChannelStub()],
        state_dir={"runner": runner_dir, "sessions": sessions_dir},
    )
    try:
        assert runner_dir.is_dir()
        assert sessions_dir.is_dir()
        # Default subfolders should NOT exist when the caller provides
        # explicit overrides.
        assert not (tmp_path / "runner").is_dir() or runner_dir == (tmp_path / "runner")
        assert not (tmp_path / "sessions").is_dir() or sessions_dir == (tmp_path / "sessions")
    finally:
        _close_host_disk(host)


def test_unknown_component_key_raises(tmp_path: Path) -> None:
    """Misspelled keys should fail loudly so the user catches typos."""
    with pytest.raises(ValueError, match="unknown"):
        AgentFrameworkHost(
            target=_AgentStub(),
            channels=[_ChannelStub()],
            state_dir={"runnerr": tmp_path / "x"},  # type: ignore[dict-item]
        )


# --------------------------------------------------------------------------- #
# Session bookkeeping survives a host restart                                  #
# --------------------------------------------------------------------------- #


def test_session_aliases_survive_restart(tmp_path: Path) -> None:
    """Aliases written on host #1 must be visible to host #2."""
    state_dir = tmp_path / "state"

    host1 = AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()], state_dir=state_dir)
    host1._session_aliases["user-1"] = "sess-abc"
    host1._session_aliases["user-2"] = "sess-def"
    _close_host_disk(host1)

    host2 = AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()], state_dir=state_dir)
    try:
        assert host2._session_aliases["user-1"] == "sess-abc"
        assert host2._session_aliases["user-2"] == "sess-def"
    finally:
        _close_host_disk(host2)


def test_active_channel_survives_restart(tmp_path: Path) -> None:
    """``_active`` must round-trip through the store."""
    state_dir = tmp_path / "state"

    host1 = AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()], state_dir=state_dir)
    host1._active["user-1"] = "telegram"
    host1._active["user-2"] = "responses"
    _close_host_disk(host1)

    host2 = AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()], state_dir=state_dir)
    try:
        assert host2._active["user-1"] == "telegram"
        assert host2._active["user-2"] == "responses"
    finally:
        _close_host_disk(host2)


def test_identities_nested_mutation_survives_restart(tmp_path: Path) -> None:
    """Setting ``self._identities[ik][channel] = identity`` must persist.

    This exercises the proxy-inner-dict ``__setitem__`` write-through path,
    not just the outer-key replacement path.
    """
    state_dir = tmp_path / "state"

    host1 = AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()], state_dir=state_dir)
    ident_tg = ChannelIdentity("telegram", "tg-123", {"username": "alice"})
    ident_rsp = ChannelIdentity("responses", "rsp-456")
    # Mirrors the host-internal path in ``_register_identity``.
    host1._identities.setdefault("user-1", {})["telegram"] = ident_tg
    host1._identities.setdefault("user-1", {})["responses"] = ident_rsp
    host1._identities.setdefault("user-2", {})["telegram"] = ChannelIdentity("telegram", "tg-789")
    _close_host_disk(host1)

    host2 = AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()], state_dir=state_dir)
    try:
        u1 = host2._identities["user-1"]
        assert set(u1.keys()) == {"telegram", "responses"}
        assert u1["telegram"].native_id == "tg-123"
        assert u1["telegram"].attributes["username"] == "alice"
        assert u1["responses"].native_id == "rsp-456"
        assert host2._identities["user-2"]["telegram"].native_id == "tg-789"
    finally:
        _close_host_disk(host2)


# --------------------------------------------------------------------------- #
# Explicit durable_task_runner + state_dir['runner'] warns                    #
# --------------------------------------------------------------------------- #


def test_explicit_runner_with_runner_state_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Caller-owned runner + state_dir['runner'] → ignore + warn."""
    from agent_framework_hosting import InProcessTaskRunner

    user_runner = InProcessTaskRunner()
    try:
        with caplog.at_level("WARNING"):
            host = AgentFrameworkHost(
                target=_AgentStub(),
                channels=[_ChannelStub()],
                durable_task_runner=user_runner,
                allow_in_process_runner=True,
                state_dir={"runner": tmp_path / "runner"},
            )
        assert any("state_dir['runner']" in rec.message for rec in caplog.records)
        # Sessions store wasn't requested, so still None.
        assert host._sessions_store is None
    finally:
        # user_runner has no disk state, so nothing else to clean up.
        pass


# --------------------------------------------------------------------------- #
# Workflow checkpoint integration                                              #
# --------------------------------------------------------------------------- #


def _build_simple_workflow() -> Any:
    """Build a no-op workflow for checkpoint-wiring tests."""
    from tests._workflow_fixtures import build_upper_workflow

    return build_upper_workflow()


def test_single_path_state_dir_wires_workflow_checkpoints(tmp_path: Path) -> None:
    """``state_dir="/foo"`` + workflow target → ``/foo/checkpoints/`` is used."""
    workflow = _build_simple_workflow()
    host = AgentFrameworkHost(
        target=workflow,
        channels=[_ChannelStub()],
        state_dir=tmp_path,
    )
    try:
        # Checkpoint location is derived from the single state_dir.
        assert host._checkpoint_location == tmp_path / "checkpoints"
    finally:
        _close_host_disk(host)


def test_mapping_state_dir_checkpoints_key_wires_workflow_checkpoints(tmp_path: Path) -> None:
    """``state_dir={"checkpoints": ...}`` + workflow target → that path is used."""
    workflow = _build_simple_workflow()
    ckpt_dir = tmp_path / "ck"
    host = AgentFrameworkHost(
        target=workflow,
        channels=[_ChannelStub()],
        state_dir={"checkpoints": ckpt_dir},
    )
    try:
        assert host._checkpoint_location == ckpt_dir
        # No diskcache components were requested.
        assert host._sessions_store is None
    finally:
        _close_host_disk(host)


def test_mapping_state_dir_omits_checkpoints_for_workflow(tmp_path: Path) -> None:
    """Mapping form lets workflow callers opt out of checkpoint persistence."""
    workflow = _build_simple_workflow()
    host = AgentFrameworkHost(
        target=workflow,
        channels=[_ChannelStub()],
        # No 'checkpoints' key → no checkpoint persistence even though
        # other components are persisted.
        state_dir={"runner": tmp_path / "r", "sessions": tmp_path / "s"},
    )
    try:
        assert host._checkpoint_location is None
    finally:
        _close_host_disk(host)


def test_explicit_checkpoint_location_wins_over_state_dir(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """``checkpoint_location`` + ``state_dir`` → explicit param wins + warn."""
    workflow = _build_simple_workflow()
    explicit = tmp_path / "explicit-ck"
    with caplog.at_level("WARNING", logger="agent_framework.hosting"):
        host = AgentFrameworkHost(
            target=workflow,
            channels=[_ChannelStub()],
            checkpoint_location=explicit,
            state_dir=tmp_path,
        )
    try:
        assert host._checkpoint_location == explicit
        assert any(
            "state_dir['checkpoints']" in rec.message and "checkpoint_location" in rec.message for rec in caplog.records
        )
    finally:
        _close_host_disk(host)


def test_state_dir_checkpoints_for_agent_target_silent_for_single_path(tmp_path: Path) -> None:
    """Single-path state_dir + agent target → no checkpoint, no warning."""
    host = AgentFrameworkHost(
        target=_AgentStub(),
        channels=[_ChannelStub()],
        state_dir=tmp_path,
    )
    try:
        assert host._checkpoint_location is None
        # ``checkpoints/`` subfolder is not eagerly created (no consumer).
        assert not (tmp_path / "checkpoints").exists()
    finally:
        _close_host_disk(host)


def test_state_dir_checkpoints_for_agent_target_warns_when_explicit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Mapping form with ``checkpoints`` + agent target → warn (dead config)."""
    with caplog.at_level("WARNING", logger="agent_framework.hosting"):
        host = AgentFrameworkHost(
            target=_AgentStub(),
            channels=[_ChannelStub()],
            state_dir={"checkpoints": tmp_path / "ck"},
        )
    try:
        assert host._checkpoint_location is None
        assert any(
            "state_dir['checkpoints']" in rec.message and "not a Workflow" in rec.message for rec in caplog.records
        )
    finally:
        _close_host_disk(host)


def test_state_dir_checkpoints_conflicts_with_workflow_own_storage(tmp_path: Path) -> None:
    """Derived checkpoint path triggers the same conflict guard as explicit."""
    from agent_framework import InMemoryCheckpointStorage, WorkflowBuilder

    from tests._workflow_fixtures import _UpperExecutor

    workflow = WorkflowBuilder(
        start_executor=_UpperExecutor(id="upper"),
        checkpoint_storage=InMemoryCheckpointStorage(),
    ).build()
    with pytest.raises(RuntimeError, match="already has checkpoint storage"):
        AgentFrameworkHost(
            target=workflow,
            channels=[_ChannelStub()],
            state_dir=tmp_path,
        )
