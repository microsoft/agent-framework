# Copyright (c) Microsoft. All rights reserved.

"""Pytest configuration for declarative tests."""

import sys

import pytest
from agent_framework import _feature_stage

# Skip all tests in this directory on Python 3.14+ because powerfx doesn't support it yet
if sys.version_info >= (3, 14):
    collect_ignore_glob = ["test_*.py"]


@pytest.fixture
def fresh_feature_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate once-per-feature warnings from other tests."""
    monkeypatch.setattr(_feature_stage, "_WARNED_FEATURES", set())


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip all declarative tests on Python 3.14+ due to powerfx incompatibility."""
    if sys.version_info >= (3, 14):
        skip_marker = pytest.mark.skip(reason="powerfx does not support Python 3.14+")
        for item in items:
            if "declarative" in str(item.fspath):
                item.add_marker(skip_marker)
