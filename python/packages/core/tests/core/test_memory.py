# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import MutableSequence
from typing import Any

from agent_framework import ChatMessage, Role
from agent_framework._memory import Context, ContextProvider


class MockContextProvider(ContextProvider):
    """Mock ContextProvider for testing."""

    def __init__(self, messages: list[ChatMessage] | None = None) -> None:
        self.context_messages = messages
        self.thread_created_called = False
        self.invoked_called = False
        self.invoking_called = False
        self.thread_created_thread_id = None
        self.new_messages = None
        self.model_invoking_messages = None

    async def thread_created(self, thread_id: str | None) -> None:
        """Track thread_created calls."""
        self.thread_created_called = True
        self.thread_created_thread_id = thread_id

    async def invoked(
        self,
        request_messages: Any,
        response_messages: Any | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Track invoked calls."""
        self.invoked_called = True
        self.new_messages = request_messages

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        """Track invoking calls and return context."""
        self.invoking_called = True
        self.model_invoking_messages = messages
        context = Context()
        context.messages = self.context_messages
        return context


class MinimalContextProvider(ContextProvider):
    """Minimal ContextProvider that only implements the required abstract method.

    Used to test the base class default implementations of thread_created,
    invoked, __aenter__, and __aexit__.
    """

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        """Return empty context."""
        return Context()


class TestContext:
    """Tests for Context class."""

    def test_context_default_values(self) -> None:
        """Test Context has correct default values."""
        context = Context()
        assert context.instructions is None
        assert context.messages == []
        assert context.tools == []

    def test_context_with_values(self) -> None:
        """Test Context can be initialized with values."""
        messages = [ChatMessage(role=Role.USER, text="Test message")]
        context = Context(instructions="Test instructions", messages=messages)
        assert context.instructions == "Test instructions"
        assert len(context.messages) == 1
        assert context.messages[0].text == "Test message"


class TestContextProvider:
    """Tests for ContextProvider class."""

    async def test_thread_created(self) -> None:
        """Test thread_created is called."""
        provider = MockContextProvider()
        await provider.thread_created("test-thread-id")
        assert provider.thread_created_called
        assert provider.thread_created_thread_id == "test-thread-id"

    async def test_invoked(self) -> None:
        """Test invoked is called."""
        provider = MockContextProvider()
        message = ChatMessage(role=Role.USER, text="Test message")
        await provider.invoked(message)
        assert provider.invoked_called
        assert provider.new_messages == message

    async def test_invoking(self) -> None:
        """Test invoking is called and returns context."""
        provider = MockContextProvider(messages=[ChatMessage(role=Role.USER, text="Context message")])
        message = ChatMessage(role=Role.USER, text="Test message")
        context = await provider.invoking(message)
        assert provider.invoking_called
        assert provider.model_invoking_messages == message
        assert context.messages is not None
        assert len(context.messages) == 1
        assert context.messages[0].text == "Context message"

    async def test_base_thread_created_does_nothing(self) -> None:
        """Test that base ContextProvider.thread_created does nothing by default."""
        provider = MinimalContextProvider()
        await provider.thread_created("some-thread-id")
        await provider.thread_created(None)

    async def test_base_invoked_does_nothing(self) -> None:
        """Test that base ContextProvider.invoked does nothing by default."""
        provider = MinimalContextProvider()
        message = ChatMessage(role=Role.USER, text="Test")
        await provider.invoked(message)
        await provider.invoked(message, response_messages=message)
        await provider.invoked(message, invoke_exception=Exception("test"))

    async def test_base_aenter_returns_self(self) -> None:
        """Test that base ContextProvider.__aenter__ returns self."""
        provider = MinimalContextProvider()
        async with provider as p:
            assert p is provider

    async def test_base_aexit_does_nothing(self) -> None:
        """Test that base ContextProvider.__aexit__ handles exceptions gracefully."""
        provider = MinimalContextProvider()
        await provider.__aexit__(None, None, None)
        try:
            raise ValueError("test error")
        except ValueError:
            exc_info = sys.exc_info()
            await provider.__aexit__(exc_info[0], exc_info[1], exc_info[2])
