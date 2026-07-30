# Copyright (c) Microsoft. All rights reserved.

"""Pytest configuration for hosting tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def pytest_configure() -> None:
    """Make workflow fixtures importable in package-local and aggregate test modes."""
    module_name = "hosting_workflow_fixtures"
    if module_name in sys.modules:
        return

    fixture_path = Path(__file__).with_name("_workflow_fixtures.py")
    spec = importlib.util.spec_from_file_location(module_name, fixture_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load workflow fixtures from {fixture_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
