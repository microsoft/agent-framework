# Copyright (c) Microsoft. All rights reserved.

"""Tests for GAIA benchmark implementation."""

from agent_framework_lab_gaia import gaia_scorer


class TestGAIAScorer:
    """Test the GAIA scoring function."""

    def test_numeric_exact_match(self):
        """Test numeric exact matching."""
        assert gaia_scorer("42", "42") is True
        assert gaia_scorer("42.0", "42") is True
        assert gaia_scorer("42", "42.0") is True
        assert gaia_scorer("42", "43") is False

    def test_string_normalization(self):
        """Test string normalization and matching."""
        assert gaia_scorer("Hello World", "hello world") is True
        assert gaia_scorer("Hello, World!", "helloworld") is True
        assert gaia_scorer("test", "TEST") is True
        assert gaia_scorer("test", "different") is False

    def test_list_matching(self):
        """Test list matching with comma/semicolon separation."""
        assert gaia_scorer("1,2,3", "1,2,3") is True
        assert gaia_scorer("1; 2; 3", "1,2,3") is True
        assert gaia_scorer("apple,banana", "apple,banana") is True
        assert gaia_scorer("1,2,3", "1,2,4") is False
        assert gaia_scorer("1,2", "1,2,3") is False

    def test_none_handling(self):
        """Test handling of None values."""
        assert gaia_scorer("None", "test") is False
        assert gaia_scorer("", "test") is False
