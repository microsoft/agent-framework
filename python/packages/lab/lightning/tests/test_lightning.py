# Copyright (c) Microsoft. All rights reserved.

"""Tests for lightning module."""

import pytest
from agent_framework_lab_lightning import __version__


class TestLightning:
    """Test the lightning module."""
    
    def test_version(self):
        """Test package version is defined."""
        assert __version__ is not None
        assert __version__ == "0.1.0b1"
