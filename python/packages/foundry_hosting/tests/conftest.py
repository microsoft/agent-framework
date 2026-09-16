# Copyright (c) Microsoft. All rights reserved.

"""Fixtures for Foundry Hosting tests."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_local_agentserver_state_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Give each test an independent local AgentServer state root."""
    monkeypatch.setenv("AGENTSERVER_STATE_ROOT", str(tmp_path / "agentserver-state"))
