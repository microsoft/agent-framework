# Copyright (c) Microsoft. All rights reserved.

"""Make helper modules in this directory importable by name under any pytest import mode."""

import sys
from pathlib import Path


def pytest_configure() -> None:
    """Put this directory on sys.path; the workspace test sweep uses --import-mode=importlib."""
    test_dir = str(Path(__file__).resolve().parent)
    if test_dir not in sys.path:
        sys.path.insert(0, test_dir)
