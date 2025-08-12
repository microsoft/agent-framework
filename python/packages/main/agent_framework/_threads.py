# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Collection, Sequence
from typing import Any, Protocol

from ._pydantic import AFBaseModel
from ._types import ChatMessage

__all__ = ["AgentThread", "ChatMessageStore", "ListChatMessageStore"]


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

    async def add_messages(self, messages: Collection[ChatMessage]) -> None:
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

    def __init__(self, service_thread_id: str | None = None, message_store: ChatMessageStore | None = None) -> None:
        super().__init__()

        self._service_thread_id = service_thread_id
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
        return await self._message_store.list_messages() if self._message_store is not None else None

    async def serialize(self, **kwargs: Any) -> Any:
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
        thread.message_store = ListChatMessageStore()

    # If a store has been provided, we need to add the messages to the store.
    if isinstance(new_messages, ChatMessage):
        new_messages = [new_messages]

    await thread.message_store.add_messages(new_messages)


async def deserialize_thread_state(thread: AgentThread, serialized_thread: Any, **kwargs: Any) -> None:
    """Deserializes the state from a dictionary into the thread properties."""
    state = ThreadState(**serialized_thread)

    if state.service_thread_id:
        thread.service_thread_id = state.service_thread_id
        # Since we have an ID, we should not have a chat message store and we can return here.
        return

    # If we don't have any ChatMessageStore state return here.
    if state.chat_message_store_state is None:
        return

    if thread.message_store is None:
        # If we don't have a chat message store yet, create an in-memory one.
        thread.message_store = ListChatMessageStore()

    await thread.message_store.deserialize_state(state.chat_message_store_state, **kwargs)


class ThreadState(AFBaseModel):
    service_thread_id: str | None = None
    chat_message_store_state: Any | None = None


class StoreState(AFBaseModel):
    messages: list[ChatMessage]


class ListChatMessageStore:
    def __init__(self, messages: Collection[ChatMessage] | None = None) -> None:
        self._messages: list[ChatMessage] = []
        if messages:
            self._messages.extend(messages)

    async def add_messages(self, messages: Collection[ChatMessage]) -> None:
        self._messages.extend(messages)

    async def list_messages(self) -> list[ChatMessage]:
        return self._messages

    async def deserialize_state(self, serialized_store_state: Any, **kwargs: Any) -> None:
        if serialized_store_state:
            state = StoreState(**serialized_store_state)
            if state.messages:
                self._messages.extend(state.messages)

    async def serialize_state(self, **kwargs: Any) -> Any:
        state = StoreState(messages=self._messages)
        return state.model_dump()

    def __len__(self) -> int:
        return len(self._messages)

    def __getitem__(self, index: int) -> ChatMessage:
        return self._messages[index]

    def __setitem__(self, index: int, item: ChatMessage) -> None:
        self._messages[index] = item

    def append(self, item: ChatMessage) -> None:
        self._messages.append(item)

    def clear(self) -> None:
        self._messages.clear()

    def index(self, item: ChatMessage) -> int:
        return self._messages.index(item)

    def insert(self, index: int, item: ChatMessage) -> None:
        self._messages.insert(index, item)

    def remove(self, item: ChatMessage) -> None:
        self._messages.remove(item)

    def pop(self, index: int = -1) -> ChatMessage:
        return self._messages.pop(index)
