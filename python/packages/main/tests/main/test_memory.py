# Copyright (c) Microsoft. All rights reserved.

from collections.abc import MutableSequence, Sequence
from typing import Any
from unittest.mock import AsyncMock, Mock

from agent_framework import ChatMessage, Role, TextContent, ToolProtocol
from agent_framework._memory import AggregateContextProvider, Context, ContextProvider


class MockContextProvider(ContextProvider):
    """Mock ContextProvider for testing."""

    context_messages: list[ChatMessage] | None = None
    context_tools: list[ToolProtocol] | None = None
    context_instructions: str | None = None
    thread_created_called: bool = False
    messages_adding_called: bool = False
    model_invoking_called: bool = False
    thread_created_thread_id: str | None = None
    messages_adding_thread_id: str | None = None
    messages_adding_new_messages: ChatMessage | Sequence[ChatMessage] | None = None
    model_invoking_messages: ChatMessage | MutableSequence[ChatMessage] | None = None

    def __init__(self, messages: list[ChatMessage] | None = None) -> None:
        super().__init__()
        self.context_messages = messages
        self.thread_created_called = False
        self.messages_adding_called = False
        self.model_invoking_called = False
        self.thread_created_thread_id = None
        self.messages_adding_thread_id = None
        self.messages_adding_new_messages = None
        self.model_invoking_messages = None

    async def thread_created(self, thread_id: str | None) -> None:
        """Track thread_created calls."""
        self.thread_created_called = True
        self.thread_created_thread_id = thread_id

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Track messages_adding calls."""
        self.messages_adding_called = True
        self.messages_adding_thread_id = thread_id
        self.messages_adding_new_messages = new_messages

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        """Track invoking calls and return context."""
        self.model_invoking_called = True
        self.model_invoking_messages = messages
        context = Context()
        context.messages = self.context_messages
        return context


class TestAggregateContextProvider:
    """Tests for AggregateContextProvider class."""

    def test_init_with_no_providers(self) -> None:
        """Test initialization with no providers."""
        aggregate = AggregateContextProvider()
        assert aggregate.providers == []

    def test_init_with_none_providers(self) -> None:
        """Test initialization with None providers."""
        aggregate = AggregateContextProvider(None)
        assert aggregate.providers == []

    def test_init_with_providers(self) -> None:
        """Test initialization with providers."""
        provider1 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 1")])
        provider2 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 2")])
        provider3 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 3")])
        providers = [provider1, provider2, provider3]

        aggregate = AggregateContextProvider(providers)
        assert len(aggregate.providers) == 3
        assert aggregate.providers[0] is provider1
        assert aggregate.providers[1] is provider2
        assert aggregate.providers[2] is provider3

    def test_add_provider(self) -> None:
        """Test adding a provider."""
        aggregate = AggregateContextProvider()
        provider = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions")])

        aggregate.add(provider)
        assert len(aggregate.providers) == 1
        assert aggregate.providers[0] is provider

    def test_add_multiple_providers(self) -> None:
        """Test adding multiple providers."""
        aggregate = AggregateContextProvider()
        provider1 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 1")])
        provider2 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 2")])

        aggregate.add(provider1)
        aggregate.add(provider2)

        assert len(aggregate.providers) == 2
        assert aggregate.providers[0] is provider1
        assert aggregate.providers[1] is provider2

    async def test_thread_created_with_no_providers(self) -> None:
        """Test thread_created with no providers."""
        aggregate = AggregateContextProvider()

        # Should not raise an exception
        await aggregate.thread_created("thread-123")

    async def test_thread_created_with_providers(self) -> None:
        """Test thread_created calls all providers."""
        provider1 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 1")])
        provider2 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 2")])
        aggregate = AggregateContextProvider([provider1, provider2])

        thread_id = "thread-123"
        await aggregate.thread_created(thread_id)

        assert provider1.thread_created_called
        assert provider1.thread_created_thread_id == thread_id
        assert provider2.thread_created_called
        assert provider2.thread_created_thread_id == thread_id

    async def test_thread_created_with_none_thread_id(self) -> None:
        """Test thread_created with None thread_id."""
        provider = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions")])
        aggregate = AggregateContextProvider([provider])

        await aggregate.thread_created(None)

        assert provider.thread_created_called
        assert provider.thread_created_thread_id is None

    async def test_messages_adding_with_no_providers(self) -> None:
        """Test messages_adding with no providers."""
        aggregate = AggregateContextProvider()
        message = ChatMessage(text="Hello", role=Role.USER)

        # Should not raise an exception
        await aggregate.messages_adding("thread-123", message)

    async def test_messages_adding_with_single_message(self) -> None:
        """Test messages_adding with a single message."""
        provider1 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 1")])
        provider2 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 2")])
        aggregate = AggregateContextProvider([provider1, provider2])

        thread_id = "thread-123"
        message = ChatMessage(text="Hello", role=Role.USER)
        await aggregate.messages_adding(thread_id, message)

        assert provider1.messages_adding_called
        assert provider1.messages_adding_thread_id == thread_id
        assert provider1.messages_adding_new_messages == message
        assert provider2.messages_adding_called
        assert provider2.messages_adding_thread_id == thread_id
        assert provider2.messages_adding_new_messages == message

    async def test_messages_adding_with_message_sequence(self) -> None:
        """Test messages_adding with a sequence of messages."""
        provider = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions")])
        aggregate = AggregateContextProvider([provider])

        thread_id = "thread-123"
        messages = [
            ChatMessage(text="Hello", role=Role.USER),
            ChatMessage(text="Hi there", role=Role.ASSISTANT),
        ]
        await aggregate.messages_adding(thread_id, messages)

        assert provider.messages_adding_called
        assert provider.messages_adding_thread_id == thread_id
        assert provider.messages_adding_new_messages == messages

    async def test_model_invoking_with_no_providers(self) -> None:
        """Test invoking with no providers."""
        aggregate = AggregateContextProvider()
        message = ChatMessage(text="Hello", role=Role.USER)

        context = await aggregate.invoking(message)

        assert isinstance(context, Context)
        assert not context.messages

    async def test_model_invoking_with_single_provider(self) -> None:
        """Test invoking with a single provider."""
        provider = MockContextProvider(messages=[ChatMessage(role="user", text="Test instructions")])
        aggregate = AggregateContextProvider([provider])

        message = [ChatMessage(text="Hello", role=Role.USER)]
        context = await aggregate.invoking(message)

        assert provider.model_invoking_called
        assert provider.model_invoking_messages == message
        assert isinstance(context, Context)

        assert context.messages
        assert isinstance(context.messages[0].contents[0], TextContent)
        assert context.messages[0].text == "Test instructions"

    async def test_model_invoking_with_multiple_providers(self) -> None:
        """Test invoking combines contexts from multiple providers."""
        provider1 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 1")])
        provider2 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 2")])
        provider3 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 3")])
        aggregate = AggregateContextProvider([provider1, provider2, provider3])

        messages = [ChatMessage(text="Hello", role=Role.USER)]
        context = await aggregate.invoking(messages)

        assert provider1.model_invoking_called
        assert provider1.model_invoking_messages == messages
        assert provider2.model_invoking_called
        assert provider2.model_invoking_messages == messages
        assert provider3.model_invoking_called
        assert provider3.model_invoking_messages == messages

        assert isinstance(context, Context)

        assert context.messages
        assert isinstance(context.messages[0].contents[0], TextContent)
        assert isinstance(context.messages[1].contents[0], TextContent)
        assert isinstance(context.messages[2].contents[0], TextContent)
        assert context.messages[0].text == "Instructions 1"
        assert context.messages[1].text == "Instructions 2"
        assert context.messages[2].text == "Instructions 3"

    async def test_model_invoking_with_none_instructions(self) -> None:
        """Test invoking filters out None instructions."""
        provider1 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 1")])
        provider2 = MockContextProvider(messages=None)  # None instructions
        provider3 = MockContextProvider(messages=[ChatMessage(role="user", text="Instructions 3")])
        aggregate = AggregateContextProvider([provider1, provider2, provider3])

        message = ChatMessage(text="Hello", role=Role.USER)
        context = await aggregate.invoking(message)

        assert isinstance(context, Context)
        assert context.messages
        assert isinstance(context.messages[0].contents[0], TextContent)
        assert isinstance(context.messages[1].contents[0], TextContent)
        assert context.messages[0].text == "Instructions 1"
        assert context.messages[1].text == "Instructions 3"

    async def test_model_invoking_with_all_none_instructions(self) -> None:
        """Test invoking when all providers return None instructions."""
        provider1 = MockContextProvider(None)
        provider2 = MockContextProvider(None)
        aggregate = AggregateContextProvider([provider1, provider2])

        message = ChatMessage(text="Hello", role=Role.USER)
        context = await aggregate.invoking(message)

        assert isinstance(context, Context)
        assert not context.messages

    async def test_model_invoking_with_mutable_sequence(self) -> None:
        """Test invoking with MutableSequence of messages."""
        provider = MockContextProvider(messages=[ChatMessage(role="user", text="Test instructions")])
        aggregate = AggregateContextProvider([provider])

        messages = [ChatMessage(text="Hello", role=Role.USER)]
        context = await aggregate.invoking(messages)

        assert provider.model_invoking_called
        assert provider.model_invoking_messages == messages
        assert isinstance(context, Context)
        assert context.messages
        assert isinstance(context.messages[0].contents[0], TextContent)
        assert context.messages[0].text == "Test instructions"

    async def test_async_methods_concurrent_execution(self) -> None:
        """Test that async methods execute providers concurrently."""
        # Use AsyncMock to verify concurrent execution
        provider1 = Mock(spec=ContextProvider)
        provider1.thread_created = AsyncMock()
        provider1.messages_adding = AsyncMock()
        provider1.invoking = AsyncMock(return_value=Context(messages=[ChatMessage(role="user", text="Test 1")]))

        provider2 = Mock(spec=ContextProvider)
        provider2.thread_created = AsyncMock()
        provider2.messages_adding = AsyncMock()
        provider2.invoking = AsyncMock(return_value=Context(messages=[ChatMessage(role="user", text="Test 2")]))

        aggregate = AggregateContextProvider([provider1, provider2])

        # Test thread_created
        await aggregate.thread_created("thread-123")
        provider1.thread_created.assert_called_once_with("thread-123")
        provider2.thread_created.assert_called_once_with("thread-123")

        # Test messages_adding
        message = ChatMessage(text="Hello", role=Role.USER)
        await aggregate.messages_adding("thread-123", message)
        provider1.messages_adding.assert_called_once_with("thread-123", message)
        provider2.messages_adding.assert_called_once_with("thread-123", message)

        # Test invoking
        context = await aggregate.invoking(message)
        provider1.invoking.assert_called_once_with(message)
        provider2.invoking.assert_called_once_with(message)
        assert context.messages
        assert context.messages[0].text == "Test 1"
        assert context.messages[1].text == "Test 2"
