# Copyright (c) Microsoft. All rights reserved.


def test_self_through_main():
    try:
        from agent_framework.foundry import __version__
    except ImportError:
        __version__ = None

    assert __version__ is not None


def test_self():
    try:
        from agent_framework_foundry import __version__
    except ImportError:
        __version__ = None

    assert __version__ is not None


def test_agent_framework():
    try:
        from agent_framework import __version__
    except ImportError:
        __version__ = None

    assert __version__ is not None
