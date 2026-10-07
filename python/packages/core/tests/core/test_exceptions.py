# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentFrameworkException inner_exception handling."""

from agent_framework import AgentFrameworkException, ResponseInvalidatedException
from agent_framework.exceptions import ChatClientException, ChatClientInvalidResponseException


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


def test_response_invalidated_exception_is_public_and_picklable() -> None:
    """The partial-response invalidation signal is a public chat-client exception."""
    import pickle

    inner = RuntimeError("provider stream failed")
    exc = ResponseInvalidatedException("partial response output was invalidated", inner_exception=inner)
    restored = pickle.loads(pickle.dumps(exc))

    assert isinstance(exc, ChatClientException)
    assert not isinstance(exc, ChatClientInvalidResponseException)
    assert isinstance(restored, ResponseInvalidatedException)
    assert restored.args[0] == "partial response output was invalidated"
    assert isinstance(restored.args[1], RuntimeError)
    assert str(restored.args[1]) == "provider stream failed"
