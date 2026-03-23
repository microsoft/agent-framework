# Copyright (c) Microsoft. All rights reserved.

"""Conftest for golden tests — ensures parent test dir is importable."""

import sys
from pathlib import Path


def pytest_configure() -> None:
    """Ensure parent test directory is on sys.path for helper module imports."""
    parent_test_dir = str(Path(__file__).resolve().parent.parent)
    if parent_test_dir not in sys.path:
        sys.path.insert(0, parent_test_dir)
