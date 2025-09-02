# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Sequence
from typing import Any

import pytest

from agent_framework import AgentThread, ChatMessage, ChatMessageList, ChatRole
from agent_framework._threads import StoreState, ThreadState, deserialize_thread_state, thread_on_new_messages


class MockChatMessageStore:
    """Mock implementation of ChatMessageStore for testing."""

    def __init__(self, messages: list[ChatMessage] | None = None) -> None:
        self._messages = messages or []
        self._serialize_calls = 0
        self._deserialize_calls = 0

    async def list_messages(self) -> list[ChatMessage]:
        return self._messages

    async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
        self._messages.extend(messages)

    async def serialize_state(self, **kwargs: Any) -> Any:
        self._serialize_calls += 1
        return {"messages": [msg.__dict__ for msg in self._messages], "kwargs": kwargs}

    async def deserialize_state(self, serialized_store_state: Any, **kwargs: Any) -> None:
        self._deserialize_calls += 1
        if serialized_store_state and "messages" in serialized_store_state:
            self._messages = serialized_store_state["messages"]


@pytest.fixture
def sample_messages() -> list[ChatMessage]:
    """Fixture providing sample chat messages for testing."""
    return [
        ChatMessage(role=ChatRole.USER, text="Hello", message_id="msg1"),
        ChatMessage(role=ChatRole.ASSISTANT, text="Hi there!", message_id="msg2"),
        ChatMessage(role=ChatRole.USER, text="How are you?", message_id="msg3"),
    ]


@pytest.fixture
def sample_message() -> ChatMessage:
    """Fixture providing a single sample chat message for testing."""
    return ChatMessage(role=ChatRole.USER, text="Test message", message_id="test1")


class TestAgentThread:
    """Test cases for AgentThread class."""

    def test_init_with_no_parameters(self) -> None:
        """Test AgentThread initialization with no parameters."""
        thread = AgentThread()
        assert thread.service_thread_id is None
        assert thread.message_store is None

    def test_init_with_service_thread_id(self) -> None:
        """Test AgentThread initialization with service_thread_id."""
        service_thread_id = "test-conversation-123"
        thread = AgentThread(service_thread_id=service_thread_id)
        assert thread.service_thread_id == service_thread_id
        assert thread.message_store is None

    def test_init_with_message_store(self) -> None:
        """Test AgentThread initialization with message_store."""
        store = ChatMessageList()
        thread = AgentThread(message_store=store)
        assert thread.service_thread_id is None
        assert thread.message_store is store

    def test_service_thread_id_property_setter(self) -> None:
        """Test service_thread_id property setter."""
        thread = AgentThread()
        service_thread_id = "test-conversation-456"

        thread.service_thread_id = service_thread_id
        assert thread.service_thread_id == service_thread_id

    def test_service_thread_id_setter_with_existing_message_store_raises_error(self) -> None:
        """Test that setting service_thread_id when message_store exists raises ValueError."""
        store = ChatMessageList()
        thread = AgentThread(message_store=store)

        with pytest.raises(ValueError, match="Only the service_thread_id or message_store may be set"):
            thread.service_thread_id = "test-conversation-789"

    def test_service_thread_id_setter_with_none_values(self) -> None:
        """Test service_thread_id setter with None values does nothing."""
        thread = AgentThread()
        thread.service_thread_id = None  # Should not raise error
        assert thread.service_thread_id is None

    def test_message_store_property_setter(self) -> None:
        """Test message_store property setter."""
        thread = AgentThread()
        store = ChatMessageList()

        thread.message_store = store
        assert thread.message_store is store

    def test_message_store_setter_with_existing_service_thread_id_raises_error(self) -> None:
        """Test that setting message_store when service_thread_id exists raises ValueError."""
        service_thread_id = "test-conversation-999"
        thread = AgentThread(service_thread_id=service_thread_id)
        store = ChatMessageList()

        with pytest.raises(ValueError, match="Only the service_thread_id or message_store may be set"):
            thread.message_store = store

    def test_message_store_setter_with_none_values(self) -> None:
        """Test message_store setter with None values does nothing."""
        thread = AgentThread()
        thread.message_store = None  # Should not raise error
        assert thread.message_store is None

    async def test_get_messages_with_message_store(self, sample_messages: list[ChatMessage]) -> None:
        """Test get_messages when message_store is set."""
        store = ChatMessageList(sample_messages)
        thread = AgentThread(message_store=store)

        assert thread.message_store is not None

        messages: list[ChatMessage] = await thread.message_store.list_messages()

        assert messages is not None
        assert len(messages) == 3
        assert messages[0].text == "Hello"
        assert messages[1].text == "Hi there!"
        assert messages[2].text == "How are you?"

    async def test_get_messages_with_no_message_store(self) -> None:
        """Test get_messages when no message_store is set."""
        thread = AgentThread()

        assert thread.message_store is None

    async def test_on_new_messages_with_service_thread_id(self, sample_message: ChatMessage) -> None:
        """Test _on_new_messages when service_thread_id is set (should do nothing)."""
        thread = AgentThread(service_thread_id="test-conv")

        await thread_on_new_messages(thread, sample_message)

        # Should not create a message store
        assert thread.message_store is None

    async def test_on_new_messages_single_message_creates_store(self, sample_message: ChatMessage) -> None:
        """Test _on_new_messages with single message creates ChatMessageList."""
        thread = AgentThread()

        await thread_on_new_messages(thread, sample_message)

        assert thread.message_store is not None
        assert isinstance(thread.message_store, ChatMessageList)
        messages = await thread.message_store.list_messages()
        assert len(messages) == 1
        assert messages[0].text == "Test message"

    async def test_on_new_messages_multiple_messages(self, sample_messages: list[ChatMessage]) -> None:
        """Test _on_new_messages with multiple messages."""
        thread = AgentThread()

        await thread_on_new_messages(thread, sample_messages)

        assert thread.message_store is not None
        messages = await thread.message_store.list_messages()
        assert len(messages) == 3

    async def test_on_new_messages_with_existing_store(self, sample_message: ChatMessage) -> None:
        """Test _on_new_messages adds to existing message store."""
        initial_messages = [ChatMessage(role=ChatRole.USER, text="Initial", message_id="init1")]
        store = ChatMessageList(initial_messages)
        thread = AgentThread(message_store=store)

        await thread_on_new_messages(thread, sample_message)

        assert thread.message_store is not None
        messages = await thread.message_store.list_messages()
        assert len(messages) == 2
        assert messages[0].text == "Initial"
        assert messages[1].text == "Test message"

    async def test_deserialize_with_service_thread_id(self) -> None:
        """Test _deserialize with service_thread_id."""
        thread = AgentThread()
        serialized_data = {"service_thread_id": "test-conv-123", "chat_message_store_state": None}

        await deserialize_thread_state(thread, serialized_data)

        assert thread.service_thread_id == "test-conv-123"
        assert thread.message_store is None

    async def test_deserialize_with_store_state(self, sample_messages: list[ChatMessage]) -> None:
        """Test _deserialize with chat_message_store_state."""
        thread = AgentThread()
        store_state = {"messages": sample_messages}
        serialized_data = {"service_thread_id": None, "chat_message_store_state": store_state}

        await deserialize_thread_state(thread, serialized_data)

        assert thread.service_thread_id is None
        assert thread.message_store is not None
        assert isinstance(thread.message_store, ChatMessageList)

    async def test_deserialize_with_no_state(self) -> None:
        """Test _deserialize with no state."""
        thread = AgentThread()
        serialized_data = {"service_thread_id": None, "chat_message_store_state": None}

        await deserialize_thread_state(thread, serialized_data)

        assert thread.service_thread_id is None
        assert thread.message_store is None

    async def test_deserialize_with_existing_store(self) -> None:
        """Test _deserialize with existing message store."""
        store = MockChatMessageStore()
        thread = AgentThread(message_store=store)
        serialized_data: dict[str, Any] = {"service_thread_id": None, "chat_message_store_state": {"messages": []}}

        await deserialize_thread_state(thread, serialized_data)

        assert store._deserialize_calls == 1  # pyright: ignore[reportPrivateUsage]

    async def test_serialize_with_service_thread_id(self) -> None:
        """Test serialize with service_thread_id."""
        thread = AgentThread(service_thread_id="test-conv-456")

        result = await thread.serialize()

        assert result["service_thread_id"] == "test-conv-456"
        assert result["chat_message_store_state"] is None

    async def test_serialize_with_message_store(self) -> None:
        """Test serialize with message_store."""
        store = MockChatMessageStore()
        thread = AgentThread(message_store=store)

        result = await thread.serialize()

        assert result["service_thread_id"] is None
        assert result["chat_message_store_state"] is not None
        assert store._serialize_calls == 1  # pyright: ignore[reportPrivateUsage]

    async def test_serialize_with_no_state(self) -> None:
        """Test serialize with no state."""
        thread = AgentThread()

        result = await thread.serialize()

        assert result["service_thread_id"] is None
        assert result["chat_message_store_state"] is None

    async def test_serialize_with_kwargs(self) -> None:
        """Test serialize passes kwargs to message store."""
        store = MockChatMessageStore()
        thread = AgentThread(message_store=store)

        await thread.serialize(custom_param="test_value")

        assert store._serialize_calls == 1  # pyright: ignore[reportPrivateUsage]


class TestChatMessageList:
    """Test cases for ChatMessageList class."""

    def test_init_empty(self) -> None:
        """Test ChatMessageList initialization with no messages."""
        store = ChatMessageList()
        assert len(store) == 0

    def test_init_with_messages(self, sample_messages: list[ChatMessage]) -> None:
        """Test ChatMessageList initialization with messages."""
        store = ChatMessageList(sample_messages)
        assert len(store) == 3

    async def test_add_messages(self, sample_messages: list[ChatMessage]) -> None:
        """Test adding messages to the store."""
        store = ChatMessageList()

        await store.add_messages(sample_messages)

        assert len(store) == 3
        messages = await store.list_messages()
        assert messages[0].text == "Hello"

    async def test_get_messages(self, sample_messages: list[ChatMessage]) -> None:
        """Test getting messages from the store."""
        store = ChatMessageList(sample_messages)

        messages = await store.list_messages()

        assert len(messages) == 3
        assert messages[0].message_id == "msg1"

    async def test_serialize_state(self, sample_messages: list[ChatMessage]) -> None:
        """Test serializing store state."""
        store = ChatMessageList(sample_messages)

        result = await store.serialize_state()

        assert "messages" in result
        assert len(result["messages"]) == 3

    async def test_serialize_state_empty(self) -> None:
        """Test serializing empty store state."""
        store = ChatMessageList()

        result = await store.serialize_state()

        assert "messages" in result
        assert len(result["messages"]) == 0

    async def test_deserialize_state(self, sample_messages: list[ChatMessage]) -> None:
        """Test deserializing store state."""
        store = ChatMessageList()
        state_data = {"messages": sample_messages}

        await store.deserialize_state(state_data)

        messages = await store.list_messages()
        assert len(messages) == 3
        assert messages[0].text == "Hello"

    async def test_deserialize_state_none(self) -> None:
        """Test deserializing None state."""
        store = ChatMessageList()

        await store.deserialize_state(None)

        assert len(store) == 0

    async def test_deserialize_state_empty(self) -> None:
        """Test deserializing empty state."""
        store = ChatMessageList()

        await store.deserialize_state({})

        assert len(store) == 0

    def test_len(self, sample_messages: list[ChatMessage]) -> None:
        """Test __len__ method."""
        store = ChatMessageList(sample_messages)
        assert len(store) == 3

        empty_store = ChatMessageList()
        assert len(empty_store) == 0

    def test_getitem(self, sample_messages: list[ChatMessage]) -> None:
        """Test __getitem__ method."""
        store = ChatMessageList(sample_messages)

        assert store[0].text == "Hello"
        assert store[1].text == "Hi there!"
        assert store[2].text == "How are you?"

    def test_setitem(self, sample_messages: list[ChatMessage], sample_message: ChatMessage) -> None:
        """Test __setitem__ method."""
        store = ChatMessageList(sample_messages)

        store[1] = sample_message
        assert store[1].text == "Test message"
        assert store[1].message_id == "test1"

    def test_append(self, sample_message: ChatMessage) -> None:
        """Test append method."""
        store = ChatMessageList()

        store.append(sample_message)

        assert len(store) == 1
        assert store[0].text == "Test message"

    def test_clear(self, sample_messages: list[ChatMessage]) -> None:
        """Test clear method."""
        store = ChatMessageList(sample_messages)
        assert len(store) == 3

        store.clear()
        assert len(store) == 0

    def test_index(self, sample_messages: list[ChatMessage]) -> None:
        """Test index method."""
        store = ChatMessageList(sample_messages)

        index = store.index(sample_messages[1])
        assert index == 1

    def test_insert(self, sample_messages: list[ChatMessage], sample_message: ChatMessage) -> None:
        """Test insert method."""
        store = ChatMessageList(sample_messages)

        store.insert(1, sample_message)

        assert len(store) == 4
        assert store[1].text == "Test message"
        assert store[2].text == "Hi there!"  # Original message at index 1 is now at index 2

    def test_remove(self, sample_messages: list[ChatMessage]) -> None:
        """Test remove method."""
        store = ChatMessageList(sample_messages)
        message_to_remove = sample_messages[1]

        store.remove(message_to_remove)

        assert len(store) == 2
        assert store[0].text == "Hello"
        assert store[1].text == "How are you?"

    def test_pop_default(self, sample_messages: list[ChatMessage]) -> None:
        """Test pop method with default index."""
        store = ChatMessageList(sample_messages)

        popped_message = store.pop()

        assert len(store) == 2
        assert popped_message.text == "How are you?"  # Last message

    def test_pop_with_index(self, sample_messages: list[ChatMessage]) -> None:
        """Test pop method with specific index."""
        store = ChatMessageList(sample_messages)

        popped_message = store.pop(1)

        assert len(store) == 2
        assert popped_message.text == "Hi there!"
        assert store[0].text == "Hello"
        assert store[1].text == "How are you?"


class TestStoreState:
    """Test cases for StoreState class."""

    def test_init(self, sample_messages: list[ChatMessage]) -> None:
        """Test StoreState initialization."""
        state = StoreState(messages=sample_messages)

        assert len(state.messages) == 3
        assert state.messages[0].text == "Hello"

    def test_init_empty(self) -> None:
        """Test StoreState initialization with empty messages."""
        state = StoreState(messages=[])

        assert len(state.messages) == 0


class TestThreadState:
    """Test cases for ThreadState class."""

    def test_init_with_service_thread_id(self) -> None:
        """Test ThreadState initialization with service_thread_id."""
        state = ThreadState(service_thread_id="test-conv-123")

        assert state.service_thread_id == "test-conv-123"
        assert state.chat_message_store_state is None

    def test_init_with_chat_message_store_state(self) -> None:
        """Test ThreadState initialization with chat_message_store_state."""
        store_data: dict[str, Any] = {"messages": []}
        state = ThreadState(chat_message_store_state=store_data)

        assert state.service_thread_id is None
        assert state.chat_message_store_state == store_data

    def test_init_with_both(self) -> None:
        """Test ThreadState initialization with both parameters."""
        store_data: dict[str, Any] = {"messages": []}
        state = ThreadState(service_thread_id="test-conv-456", chat_message_store_state=store_data)

        assert state.service_thread_id == "test-conv-456"
        assert state.chat_message_store_state == store_data

    def test_init_defaults(self) -> None:
        """Test ThreadState initialization with defaults."""
        state = ThreadState()

        assert state.service_thread_id is None
        assert state.chat_message_store_state is None
