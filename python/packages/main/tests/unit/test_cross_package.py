# Copyright (c) Microsoft. All rights reserved.


def test_azure():
    try:
        from agent_framework.azure import __version__
    except ImportError:
        __version__ = None
    assert __version__ is not None
