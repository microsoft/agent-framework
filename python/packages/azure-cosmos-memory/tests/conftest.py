# Copyright (c) Microsoft. All rights reserved.

"""Pytest configuration for azure-cosmos-memory tests."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test requiring live Azure accounts")
