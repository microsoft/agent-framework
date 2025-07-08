# Copyright (c) Microsoft. All rights reserved.

from agent_framework.openai import __version__


def test_version():
    assert __version__ is not None
