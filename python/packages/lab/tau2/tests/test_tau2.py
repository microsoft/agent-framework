# Copyright (c) Microsoft. All rights reserved.

"""Tests for tau2 module."""

import pytest
from agent_framework_lab_tau2 import __version__


class TestTau2:
    """Test the tau2 module."""
    
    def test_version(self):
        """Test package version is defined."""
        assert __version__ is not None
        assert __version__ == "0.1.0b1"
