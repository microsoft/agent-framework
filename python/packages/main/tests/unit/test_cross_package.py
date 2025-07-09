# Copyright (c) Microsoft. All rights reserved.

from pytest import mark


@mark.xfail(reason="Not solved")
def test_openai():
    try:
        from agent_framework.openai import __version__
    except ImportError:
        __version__ = None
    assert __version__ is not None


@mark.xfail(reason="Not solved")
def test_azure():
    try:
        from agent_framework.azure import __version__
    except ImportError:
        __version__ = None
    assert __version__ is not None
