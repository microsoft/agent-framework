# Copyright (c) Microsoft. All rights reserved.

"""Tests for lighting module."""

import pytest
from agent_framework_lab_lighting import __version__


class TestLighting:
    """Test the lighting module."""
    
    def test_version(self):
        """Test package version is defined."""
        assert __version__ is not None
        assert __version__ == "0.1.0b1"
