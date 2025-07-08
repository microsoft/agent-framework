# Copyright (c) Microsoft. All rights reserved.

from agent_framework.ext.openai import __version__


def test_version():
    assert __version__ is not None
