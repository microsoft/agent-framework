# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Sequence
from typing import Any, Protocol, overload

from ._pydantic import AFBaseModel
from ._types import ChatMessage

__all__ = ["AgentThread", "ChatMessageList", "ChatMessageStore"]


class ChatMessageStore(Protocol):
    """Defines methods for storing and retrieving chat messages associated with a specific thread.

    Implementations of this protocol are responsible for managing the storage of chat messages,
    including handling large volumes of data by truncating or summarizing messages as necessary.
    """

    async def list_messages(self) -> list[ChatMessage]:
        """Gets all the messages from the store that should be used for the next agent invocation.

        Messages are returned in ascending chronological order, with the oldest message first.

        If the messages stored in the store become very large, it is up to the store to
        truncate, summarize or otherwise limit the number of messages returned.

        When using implementations of ChatMessageStore, a new one should be created for each thread
        since they may contain state that is specific to a thread.
        """
        ...

    async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
        """Adds messages to the store."""
        ...

    async def deserialize_state(self, serialized_store_state: Any, **kwargs: Any) -> None:
        """Deserializes the state into the properties on this store.

        This method, together with serialize_state can be used to save and load messages from a persistent store
        if this store only has messages in memory.
        """
        ...

    async def serialize_state(self, **kwargs: Any) -> Any:
        """Serializes the current object's state.

        This method, together with deserialize_state can be used to save and load messages from a persistent store
        if this store only has messages in memory.
        """
        ...


class AgentThread(AFBaseModel):
    """Base class for agent threads."""

    _service_thread_id: str | None = None
    _message_store: ChatMessageStore | None = None

    @overload
    def __init__(self) -> None:
        """Initialize an empty AgentThread with no service thread ID or message store."""
        ...

    @overload
    def __init__(self, service_thread_id: str) -> None:
        """Initialize an AgentThread with a service thread ID.

        Args:
            service_thread_id: The ID of the thread managed by the agent service.
        """
        ...

    @overload
    def __init__(self, *, message_store: ChatMessageStore) -> None:
        """Initialize an AgentThread with a custom message store.

        Args:
            message_store: The ChatMessageStore implementation for managing chat messages.
        """
        ...

    def __init__(self, service_thread_id: str | None = None, *, message_store: ChatMessageStore | None = None) -> None:
        """Initialize an AgentThread.

        Args:
            service_thread_id: Optional ID of the thread managed by the agent service.
            message_store: Optional ChatMessageStore implementation for managing chat messages.

        Note:
            Either service_thread_id or message_store may be set, but not both.
        """
        super().__init__()

        self.service_thread_id = service_thread_id
        self.message_store = message_store

    @property
    def service_thread_id(self) -> str | None:
        """Gets the ID of the current thread to support cases where the thread is owned by the agent service."""
        return self._service_thread_id

    @service_thread_id.setter
    def service_thread_id(self, service_thread_id: str | None) -> None:
        """Sets the ID of the current thread to support cases where the thread is owned by the agent service.

        Note that either service_thread_id or message_store may be set, but not both.
        """
        if not self._service_thread_id and not service_thread_id:
            return

        if self._message_store is not None:
            raise ValueError(
                "Only the service_thread_id or message_store may be set, "
                "but not both and switching from one to another is not supported."
            )

        self._service_thread_id = service_thread_id

    @property
    def message_store(self) -> ChatMessageStore | None:
        """Gets the ChatMessageStore used by this thread, when messages should be stored in a custom location."""
        return self._message_store

    @message_store.setter
    def message_store(self, message_store: ChatMessageStore | None) -> None:
        """Sets the ChatMessageStore used by this thread, when messages should be stored in a custom location.

        Note that either service_thread_id or message_store may be set, but not both.
        """
        if self._message_store is None and message_store is None:
            return

        if self._service_thread_id:
            raise ValueError(
                "Only the service_thread_id or message_store may be set, "
                "but not both and switching from one to another is not supported."
            )

        self._message_store = message_store

    async def list_messages(self) -> list[ChatMessage] | None:
        """Retrieves any messages stored in ChatMessageStore of the thread, otherwise returns an empty collection."""
        return await self._message_store.list_messages() if self._message_store is not None else None

    async def serialize(self, **kwargs: Any) -> dict[str, Any]:
        """Serializes the current object's state.

        Args:
            **kwargs: Arguments for serialization.
        """
        chat_message_store_state = None
        if self._message_store is not None:
            chat_message_store_state = await self._message_store.serialize_state(**kwargs)

        state = ThreadState(
            service_thread_id=self._service_thread_id, chat_message_store_state=chat_message_store_state
        )

        return state.model_dump()


async def thread_on_new_messages(thread: AgentThread, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
    """Invoked when a new message has been contributed to the chat by any participant."""
    if thread.service_thread_id is not None:
        # If the thread messages are stored in the service there is nothing to do here,
        # since invoking the service should already update the thread.
        return

    if thread.message_store is None:
        # If there is no conversation id, and no store we can
        # create a default in memory store.
        thread.message_store = ChatMessageList()

    # If a store has been provided, we need to add the messages to the store.
    if isinstance(new_messages, ChatMessage):
        new_messages = [new_messages]

    await thread.message_store.add_messages(new_messages)


async def deserialize_thread_state(
    thread: AgentThread,
    serialized_thread: dict[str, Any],
    **kwargs: Any,
) -> None:
    """Deserializes the state from a dictionary into the thread properties."""
    state = ThreadState.model_validate(serialized_thread)

    if state.service_thread_id:
        thread.service_thread_id = state.service_thread_id
        # Since we have an ID, we should not have a chat message store and we can return here.
        return

    # If we don't have any ChatMessageStore state return here.
    if state.chat_message_store_state is None:
        return

    if thread.message_store is None:
        # If we don't have a chat message store yet, create an in-memory one.
        thread.message_store = ChatMessageList()

    await thread.message_store.deserialize_state(state.chat_message_store_state, **kwargs)


class ThreadState(AFBaseModel):
    """State model for serializing and deserializing thread information.

    Attributes:
        service_thread_id: Optional ID of the thread managed by the agent service.
        chat_message_store_state: Optional serialized state of the chat message store.
    """

    service_thread_id: str | None = None
    chat_message_store_state: Any | None = None


class StoreState(AFBaseModel):
    """State model for serializing and deserializing chat message store data.

    Attributes:
        messages: List of chat messages stored in the message store.
    """

    messages: list[ChatMessage]


class ChatMessageList:
    """An in-memory implementation of ChatMessageStore that stores messages in a list.

    This implementation provides a simple, list-based storage for chat messages
    with support for serialization and deserialization. It implements all the
    required methods of the ChatMessageStore protocol and provides additional
    list-like operations for direct message manipulation.

    The store maintains messages in memory and provides methods to serialize
    and deserialize the state for persistence purposes.
    """

    def __init__(self, messages: Sequence[ChatMessage] | None = None) -> None:
        """Initialize the message store with optional initial messages.

        Args:
            messages: Optional collection of initial ChatMessage objects to store.
        """
        self._messages: list[ChatMessage] = []
        if messages:
            self._messages.extend(messages)

    async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
        """Add messages to the store.

        Args:
            messages: Sequence of ChatMessage objects to add to the store.
        """
        self._messages.extend(messages)

    async def list_messages(self) -> list[ChatMessage]:
        """Get all messages from the store in chronological order.

        Returns:
            List of ChatMessage objects, ordered from oldest to newest.
        """
        return self._messages

    async def deserialize_state(self, serialized_store_state: Any, **kwargs: Any) -> None:
        """Deserialize state data into this store instance.

        Args:
            serialized_store_state: Previously serialized state data containing messages.
            **kwargs: Additional arguments for deserialization.
        """
        if serialized_store_state:
            state = StoreState.model_validate(obj=serialized_store_state, **kwargs)
            if state.messages:
                self._messages.extend(state.messages)

    async def serialize_state(self, **kwargs: Any) -> Any:
        """Serialize the current store state for persistence.

        Args:
            **kwargs: Additional arguments for serialization.

        Returns:
            Serialized state data that can be used with deserialize_state.
        """
        state = StoreState(messages=self._messages)
        return state.model_dump(**kwargs)

    def __len__(self) -> int:
        """Return the number of messages in the store.

        Returns:
            The count of messages currently stored.
        """
        return len(self._messages)

    def __getitem__(self, index: int) -> ChatMessage:
        """Get a message by index.

        Args:
            index: The index of the message to retrieve.

        Returns:
            The ChatMessage at the specified index.
        """
        return self._messages[index]

    def __setitem__(self, index: int, item: ChatMessage) -> None:
        """Set a message at the specified index.

        Args:
            index: The index at which to set the message.
            item: The ChatMessage to set at the specified index.
        """
        self._messages[index] = item

    def append(self, item: ChatMessage) -> None:
        """Append a message to the end of the store.

        Args:
            item: The ChatMessage to append.
        """
        self._messages.append(item)

    def clear(self) -> None:
        """Remove all messages from the store."""
        self._messages.clear()

    def index(self, item: ChatMessage) -> int:
        """Return the index of the first occurrence of the specified message.

        Args:
            item: The ChatMessage to find.

        Returns:
            The index of the first occurrence of the message.

        Raises:
            ValueError: If the message is not found in the store.
        """
        return self._messages.index(item)

    def insert(self, index: int, item: ChatMessage) -> None:
        """Insert a message at the specified index.

        Args:
            index: The index at which to insert the message.
            item: The ChatMessage to insert.
        """
        self._messages.insert(index, item)

    def remove(self, item: ChatMessage) -> None:
        """Remove the first occurrence of the specified message from the store.

        Args:
            item: The ChatMessage to remove.

        Raises:
            ValueError: If the message is not found in the store.
        """
        self._messages.remove(item)

    def pop(self, index: int = -1) -> ChatMessage:
        """Remove and return a message at the specified index.

        Args:
            index: The index of the message to remove and return. Defaults to -1 (last item).

        Returns:
            The ChatMessage that was removed.

        Raises:
            IndexError: If the index is out of range.
        """
        return self._messages.pop(index)
