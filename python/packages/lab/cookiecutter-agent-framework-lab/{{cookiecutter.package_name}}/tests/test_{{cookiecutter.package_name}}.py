# Copyright (c) Microsoft. All rights reserved.

"""Tests for {{ cookiecutter.package_name }} module."""

import pytest
from agent_framework_lab_{{cookiecutter.package_name}} import __version__


class Test{{cookiecutter.package_name | title}}:
    """Test the {{ cookiecutter.package_name }} module."""
    
    def test_version(self):
        """Test package version is defined."""
        assert __version__ is not None
        assert __version__ == "{{ cookiecutter.version }}"
