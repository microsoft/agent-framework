# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentFrameworkException inner_exception handling."""

from agent_framework import AgentFrameworkException, FunctionCallInvalidatedException
from agent_framework.exceptions import ChatClientException


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


def test_function_call_invalidated_exception_is_public_and_picklable() -> None:
    """The provider invalidation signal is a public chat-client exception."""
    import pickle

    inner = RuntimeError("provider stream failed")
    exc = FunctionCallInvalidatedException("local function calls were invalidated", inner_exception=inner)
    restored = pickle.loads(pickle.dumps(exc))

    assert isinstance(exc, ChatClientException)
    assert isinstance(restored, FunctionCallInvalidatedException)
    assert restored.args[0] == "local function calls were invalidated"
    assert isinstance(restored.args[1], RuntimeError)
    assert str(restored.args[1]) == "provider stream failed"
