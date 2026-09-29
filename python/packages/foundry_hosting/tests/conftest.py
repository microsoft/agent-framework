# Copyright (c) Microsoft. All rights reserved.

"""Fixtures for Foundry Hosting tests."""

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture(autouse=True)
def isolate_local_agentserver_state_root(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give each test attempt an independent local AgentServer state root."""
    # pytest-retry bypasses the report hooks needed by tmp_path's teardown bookkeeping.
    with TemporaryDirectory(prefix="agentserver-test-") as directory:
        monkeypatch.setenv("AGENTSERVER_STATE_ROOT", str(Path(directory) / "agentserver-state"))
        yield
