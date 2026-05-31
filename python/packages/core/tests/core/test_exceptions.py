# Copyright (c) Microsoft. All rights reserved.

"""Tests for the AgentFrameworkException hierarchy."""

import pytest

from agent_framework.exceptions import AgentFrameworkException


def test_exception_without_inner_exception() -> None:
    exc = AgentFrameworkException("something went wrong", log_level=None)
    assert exc.args == ("something went wrong",)


def test_exception_with_inner_exception_preserves_it() -> None:
    inner = ValueError("root cause")
    exc = AgentFrameworkException("outer message", inner_exception=inner, log_level=None)
    assert exc.args == ("outer message", inner)
    assert exc.args[1] is inner


def test_exception_without_inner_exception_does_not_include_none() -> None:
    exc = AgentFrameworkException("msg", inner_exception=None, log_level=None)
    assert None not in exc.args
