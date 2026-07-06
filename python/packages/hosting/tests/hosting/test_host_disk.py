# Copyright (c) Microsoft. All rights reserved.

"""Tests for narrowed ``state_dir`` support in :class:`AgentFrameworkHost`."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, cast

import pytest
from agent_framework import AgentSession, ServiceSessionId

from agent_framework_hosting import AgentFrameworkHost, ChannelContext, ChannelContribution

pytest.importorskip("diskcache")


class _AgentStub:
    """Bare-minimum SupportsAgentRun stub for host construction."""

    id = "agent-stub"
    name: str | None = "Agent Stub"
    description: str | None = "Test agent stub"

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(service_session_id=service_session_id, session_id=session_id)

    def run(self, *_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover - unused
        raise RuntimeError("not invoked")


class _ChannelStub:
    name = "stub"
    path = "/stub"

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        del context
        return ChannelContribution()


def _close_host_disk(host: AgentFrameworkHost) -> None:
    """Release any session-alias store held by ``host``."""
    if host._sessions_store is not None:
        host._sessions_store.close()


def test_state_dir_none_keeps_plain_alias_dict(tmp_path: Path) -> None:
    """No store, no alias persistence, no files written."""
    host = AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()])
    assert host._sessions_store is None
    assert isinstance(host._session_aliases, dict)
    assert list(tmp_path.iterdir()) == []


def test_string_state_dir_creates_sessions_subfolder_only(tmp_path: Path) -> None:
    """Passing a single path expands to ``sessions/`` plus lazy checkpoint path."""
    host = AgentFrameworkHost(
        target=_AgentStub(),
        channels=[_ChannelStub()],
        state_dir=tmp_path,
    )
    try:
        assert host._sessions_store is not None
        assert (tmp_path / "sessions").is_dir()
        assert not (tmp_path / "runner").exists()
        assert not (tmp_path / "links").exists()
        # Checkpoint path is derived but not created for agent targets.
        assert not (tmp_path / "checkpoints").exists()
    finally:
        _close_host_disk(host)


def test_per_component_session_path(tmp_path: Path) -> None:
    """Dict form lets callers route session aliases to a specific root."""
    sessions_dir = tmp_path / "state"
    host = AgentFrameworkHost(
        target=_AgentStub(),
        channels=[_ChannelStub()],
        state_dir={"sessions": sessions_dir},
    )
    try:
        assert sessions_dir.is_dir()
        assert host._sessions_store is not None
        assert host._checkpoint_location is None
    finally:
        _close_host_disk(host)


@pytest.mark.parametrize("key", ["runner", "links", "active", "identities"])
def test_removed_state_dir_component_keys_raise(tmp_path: Path, key: str) -> None:
    """Obsolete follow-up components should fail loudly instead of becoming no-ops."""
    with pytest.raises(ValueError, match="unknown"):
        AgentFrameworkHost(
            target=_AgentStub(),
            channels=[_ChannelStub()],
            state_dir=cast(Any, {key: tmp_path / key}),
        )


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


def _build_simple_workflow() -> Any:
    """Build a no-op workflow for checkpoint-wiring tests."""
    build_upper_workflow = importlib.import_module("hosting_workflow_fixtures").build_upper_workflow

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
        assert host._sessions_store is None
    finally:
        _close_host_disk(host)


def test_mapping_state_dir_omits_checkpoints_for_workflow(tmp_path: Path) -> None:
    """Mapping form lets workflow callers opt out of checkpoint persistence."""
    workflow = _build_simple_workflow()
    host = AgentFrameworkHost(
        target=workflow,
        channels=[_ChannelStub()],
        state_dir={"sessions": tmp_path / "s"},
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
        assert not (tmp_path / "checkpoints").exists()
    finally:
        _close_host_disk(host)


def test_state_dir_checkpoints_for_agent_target_warns_when_explicit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Mapping form with ``checkpoints`` + agent target → warn."""
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

    _UpperExecutor = importlib.import_module("hosting_workflow_fixtures")._UpperExecutor
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
