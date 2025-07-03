# Copyright (c) Microsoft. All rights reserved.


from agent_framework import __version__


def test_version():
    print(__version__)
    assert __version__ is not None
