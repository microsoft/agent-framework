# Copyright (c) Microsoft. All rights reserved.

"""Regression test for https://github.com/microsoft/agent-framework/issues/5590.

agent-framework-azure-ai-search==0.0.0a1 shipped an empty agent_framework/__init__.py
that overwrote core's version on install, breaking every import that touches
observability.py (which does `from . import __version__`).
"""

import agent_framework


def test_version_is_importable() -> None:
    assert hasattr(agent_framework, "__version__"), (
        "agent_framework.__version__ is missing — another installed package likely "
        "overwrote agent_framework/__init__.py with an empty file"
    )


def test_version_is_a_non_empty_string() -> None:
    assert isinstance(agent_framework.__version__, str)
    assert agent_framework.__version__
