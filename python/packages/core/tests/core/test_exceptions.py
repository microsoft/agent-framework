# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentFrameworkException inner_exception handling."""

import pytest

from agent_framework import AgentFrameworkException


def test_exception_with_inner_exception():
    """When inner_exception is provided, it should be set as the second arg."""
    inner = ValueError("inner error")
    exc = AgentFrameworkException("test message", inner_exception=inner)
    assert exc.args[0] == "test message"
    assert exc.args[1] is inner


def test_exception_without_inner_exception():
    """When inner_exception is None, args should only contain the message."""
    exc = AgentFrameworkException("test message")
    assert exc.args == ("test message",)
    assert len(exc.args) == 1


def test_exception_inner_exception_none_explicit():
    """When inner_exception is explicitly None, args should only contain the message."""
    exc = AgentFrameworkException("test message", inner_exception=None)
    assert exc.args == ("test message",)
    assert len(exc.args) == 1
