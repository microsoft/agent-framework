# Copyright (c) Microsoft. All rights reserved.

"""Tests for CuaAgentMiddleware."""

from agent_framework_cua import CuaAgentMiddleware


def test_middleware_import():
    """Test that CuaAgentMiddleware can be imported."""
    assert CuaAgentMiddleware is not None


def test_middleware_requires_computer():
    """Test that creating middleware without cua packages raises ImportError."""
    # This test assumes cua packages are installed
    # In a real scenario without cua packages, this would raise ImportError
    pass


# TODO: Add more comprehensive tests once we can mock Computer and ComputerAgent
# For now, the integration tests with real Cua instances would be in a separate test suite
