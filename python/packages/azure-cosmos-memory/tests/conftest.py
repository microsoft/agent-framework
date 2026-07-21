# Copyright (c) Microsoft. All rights reserved.

"""Pytest configuration for azure-cosmos-memory tests."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers.

    Registered here (in addition to ``pyproject.toml``) so the markers are known even when
    pytest is not launched from the package root, avoiding unknown-marker warnings.
    """
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test requiring an external Cosmos DB backend "
        "(emulator-backed or live Azure); run without 'azure' for emulator-only.",
    )
    config.addinivalue_line(
        "markers",
        "azure: mark test as requiring a live Azure account (Cosmos DB + AI Foundry).",
    )
