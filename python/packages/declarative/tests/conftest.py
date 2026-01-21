# Copyright (c) Microsoft. All rights reserved.

"""Pytest configuration for declarative tests."""

import sys

import pytest

# Skip all tests in this directory on Python 3.14+ because powerfx doesn't support it yet
if sys.version_info >= (3, 14):
    collect_ignore_glob = ["test_*.py"]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip all declarative tests on Python 3.14+ due to powerfx incompatibility."""
    if sys.version_info >= (3, 14):
        skip_marker = pytest.mark.skip(reason="powerfx does not support Python 3.14+")
        for item in items:
            if "declarative" in str(item.fspath):
                item.add_marker(skip_marker)
