# Copyright (c) Microsoft. All rights reserved.


def test_self_through_main() -> None:
    try:
        from agent_framework.redis import __version__
    except ImportError:
        __version__ = None

    assert __version__ is not None


def test_self() -> None:
    try:
        from agent_framework_redis import __version__
    except ImportError:
        __version__ = None

    assert __version__ is not None


def test_agent_framework() -> None:
    try:
        from agent_framework import __version__
    except ImportError:
        __version__ = None

    assert __version__ is not None
