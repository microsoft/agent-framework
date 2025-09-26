# Copyright (c) Microsoft. All rights reserved.

"""Tests for lightning module."""

from agent_framework_lab_lightning import __version__


class TestLightning:
    """Test the lightning module."""

    def test_version(self):
        """Test package version is defined."""
        assert __version__ is not None
        # In development mode, version falls back to "0.0.0"
        # In installed mode, it would be the actual package version
        assert isinstance(__version__, str)
        assert len(__version__) > 0
