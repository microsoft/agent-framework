# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Collection, Iterable, Sequence
from typing import Any, Protocol

from ._pydantic import AFBaseModel
from ._types import ChatMessage

__all__ = ["AgentThread", "ChatMessageStore", "InMemoryChatMessageStore"]


class ChatMessageStore(Protocol):
    """Defines methods for storing and retrieving chat messages associated with a specific thread.

    Implementations of this protocol are responsible for managing the storage of chat messages,
    including handling large volumes of data by truncating or summarizing messages as necessary.
    """

    async def get_messages(self) -> Iterable[ChatMessage]:
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

    _conversation_id: str | None = None
    _message_store: ChatMessageStore | None = None

    def __init__(self, conversation_id: str | None = None, message_store: ChatMessageStore | None = None) -> None:
        super().__init__()

        self.conversation_id = conversation_id
        self.message_store = message_store

    @property
    def conversation_id(self) -> str | None:
        return self._conversation_id

    @conversation_id.setter
    def conversation_id(self, conversation_id: str | None) -> None:
        if not self._conversation_id and not conversation_id:
            return

        if self._message_store is not None:
            raise ValueError(
                "Only the conversation_id or message_store may be set, "
                "but not both and switching from one to another is not supported."
            )

        self._conversation_id = conversation_id

    @property
    def message_store(self) -> ChatMessageStore | None:
        return self._message_store

    @message_store.setter
    def message_store(self, message_store: ChatMessageStore | None) -> None:
        if self._message_store is None and message_store is None:
            return

        if self._conversation_id:
            raise ValueError(
                "Only the conversation_id or message_store may be set, "
                "but not both and switching from one to another is not supported."
            )

        self._message_store = message_store

    async def get_messages(self) -> AsyncIterable[ChatMessage]:
        if self._message_store is not None:
            messages = await self._message_store.get_messages()
            for message in messages:
                yield message

    async def _on_new_messages(
        self,
        new_messages: ChatMessage | Sequence[ChatMessage],
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        if self._conversation_id is not None:
            # If the thread messages are stored in the service there is nothing to do here,
            # since invoking the service should already update the thread.
            return

        if self._message_store is None:
            # If there is no conversation id, and no store we can
            # create a default in memory store.
            self._message_store = InMemoryChatMessageStore()

        # If a store has been provided, we need to add the messages to the store.
        if isinstance(new_messages, ChatMessage):
            new_messages = [new_messages]
        await self._message_store.add_messages(new_messages)

    async def _deserialize(self, serialized_thread: Any, **kwargs: Any) -> None:
        """Deserializes the state from a dictionary into the thread properties."""
        state = ThreadState(**serialized_thread)

        if state.conversation_id:
            self._conversation_id = state.conversation_id
            # Since we have an ID, we should not have a chat message store and we can return here.
            return

        # If we don't have any ChatMessageStore state return here.
        if state.store_state is None:
            return

        if self._message_store is None:
            # If we don't have a chat message store yet, create an in-memory one.
            self._message_store = InMemoryChatMessageStore()

        await self._message_store.deserialize_state(state.store_state, **kwargs)

    async def serialize(self, **kwargs: Any) -> Any:
        store_state = None
        if self._message_store is not None:
            store_state = await self._message_store.serialize_state(**kwargs)

        state = ThreadState(conversation_id=self._conversation_id, store_state=store_state)

        return state.__dict__


class ThreadState(AFBaseModel):
    conversation_id: str | None = None
    store_state: Any | None = None


class StoreState(AFBaseModel):
    messages: list[ChatMessage]


class InMemoryChatMessageStore(ChatMessageStore):
    def __init__(self, messages: Collection[ChatMessage] | None = None) -> None:
        self._messages: list[ChatMessage] = []
        if messages:
            self._messages.extend(messages)

    async def add_messages(self, messages: Collection[ChatMessage]) -> None:
        self._messages.extend(messages)

    async def get_messages(self) -> list[ChatMessage]:
        return self._messages

    async def deserialize_state(self, serialized_store_state: Any, **kwargs: Any) -> None:
        if serialized_store_state:
            state = StoreState(**serialized_store_state)
            if state.messages:
                self._messages.extend(state.messages)

    async def serialize_state(self, **kwargs: Any) -> Any:
        state = StoreState(messages=self._messages)
        return state.__dict__

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
