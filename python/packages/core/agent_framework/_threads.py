# Copyright (c) Microsoft. All rights reserved.

from collections.abc import MutableMapping, Sequence
from typing import Any, Protocol, TypeVar

from ._memory import AggregateContextProvider
from ._serialization import SerializationMixin
from ._types import ChatMessage
from .exceptions import AgentThreadException

__all__ = ["AgentThread", "ChatMessageStore", "ChatMessageStoreProtocol"]


class ChatMessageStoreProtocol(Protocol):
    """Defines methods for storing and retrieving chat messages associated with a specific thread.

    Implementations of this protocol are responsible for managing the storage of chat messages,
    including handling large volumes of data by truncating or summarizing messages as necessary.

    Examples:
        .. code-block:: python

            from agent_framework import ChatMessage


            class MyMessageStore:
                def __init__(self):
                    self._messages = []

                async def list_messages(self) -> list[ChatMessage]:
                    return self._messages

                async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
                    self._messages.extend(messages)

                @classmethod
                async def deserialize(cls, serialized_store_state, **kwargs):
                    store = cls()
                    store._messages = serialized_store_state.get("messages", [])
                    return store

                async def update_from_state(self, serialized_store_state, **kwargs) -> None:
                    self._messages = serialized_store_state.get("messages", [])

                async def serialize(self, **kwargs):
                    return {"messages": self._messages}


            # Use the custom store
            store = MyMessageStore()
    """

    async def list_messages(self) -> list[ChatMessage]:
        """Gets all the messages from the store that should be used for the next agent invocation.

        Messages are returned in ascending chronological order, with the oldest message first.

        If the messages stored in the store become very large, it is up to the store to
        truncate, summarize or otherwise limit the number of messages returned.

        When using implementations of ``ChatMessageStoreProtocol``, a new one should be created for each thread
        since they may contain state that is specific to a thread.
        """
        ...

    async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
        """Adds messages to the store.

        Args:
            messages: The sequence of ChatMessage objects to add to the store.
        """
        ...

    @classmethod
    async def deserialize(
        cls, serialized_store_state: MutableMapping[str, Any], **kwargs: Any
    ) -> "ChatMessageStoreProtocol":
        """Creates a new instance of the store from previously serialized state.

        This method, together with ``serialize()`` can be used to save and load messages from a persistent store
        if this store only has messages in memory.

        Args:
            serialized_store_state: The previously serialized state data containing messages.

        Keyword Args:
            **kwargs: Additional arguments for deserialization.

        Returns:
            A new instance of the store populated with messages from the serialized state.
        """
        ...

    async def update_from_state(self, serialized_store_state: MutableMapping[str, Any], **kwargs: Any) -> None:
        """Update the current ChatMessageStore instance from serialized state data.

        Args:
            serialized_store_state: Previously serialized state data containing messages.

        Keyword Args:
            kwargs: Additional arguments for deserialization.
        """
        ...

    async def serialize(self, **kwargs: Any) -> dict[str, Any]:
        """Serializes the current object's state.

        This method, together with ``deserialize()`` can be used to save and load messages from a persistent store
        if this store only has messages in memory.

        Keyword Args:
            kwargs: Additional arguments for serialization.

        Returns:
            The serialized state data that can be used with ``deserialize()``.
        """
        ...


class ChatMessageStoreState(SerializationMixin):
    """State model for serializing and deserializing chat message store data.

    Attributes:
        messages: List of chat messages stored in the message store.
    """

    def __init__(
        self,
        messages: Sequence[ChatMessage] | Sequence[MutableMapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create the store state.

        Args:
            messages: a list of messages or a list of the dict representation of messages.

        Keyword Args:
            **kwargs: not used for this, but might be used by subclasses.

        """
        if not messages:
            self.messages: list[ChatMessage] = []
            return
        if not isinstance(messages, list):
            raise TypeError("Messages should be a list")
        new_messages: list[ChatMessage] = []
        for msg in messages:
            if isinstance(msg, ChatMessage):
                new_messages.append(msg)
            else:
                new_messages.append(ChatMessage.from_dict(msg))
        self.messages = new_messages


class AgentThreadState(SerializationMixin):
    """State model for serializing and deserializing thread information."""

    def __init__(
        self,
        *,
        service_thread_id: str | None = None,
        chat_message_store_state: ChatMessageStoreState | MutableMapping[str, Any] | None = None,
    ) -> None:
        """Create a AgentThread state.

        Keyword Args:
            service_thread_id: Optional ID of the thread managed by the agent service.
            chat_message_store_state: Optional serialized state of the chat message store.
        """
        if service_thread_id is not None and chat_message_store_state is not None:
            raise AgentThreadException("A thread cannot have both a service_thread_id and a chat_message_store.")
        self.service_thread_id = service_thread_id
        self.chat_message_store_state: ChatMessageStoreState | None = None
        if chat_message_store_state is not None:
            if isinstance(chat_message_store_state, dict):
                self.chat_message_store_state = ChatMessageStoreState.from_dict(chat_message_store_state)
            elif isinstance(chat_message_store_state, ChatMessageStoreState):
                self.chat_message_store_state = chat_message_store_state
            else:
                raise TypeError("Could not parse ChatMessageStoreState.")


TChatMessageStore = TypeVar("TChatMessageStore", bound="ChatMessageStore")


class ChatMessageStore:
    """An in-memory implementation of ChatMessageStoreProtocol that stores messages in a list.

    This implementation provides a simple, list-based storage for chat messages
    with support for serialization and deserialization. It implements all the
    required methods of the ``ChatMessageStoreProtocol`` protocol.

    The store maintains messages in memory and provides methods to serialize
    and deserialize the state for persistence purposes.

    Examples:
        .. code-block:: python

            from agent_framework import ChatMessageStore, ChatMessage

            # Create an empty store
            store = ChatMessageStore()

            # Add messages
            message = ChatMessage(role="user", content="Hello")
            await store.add_messages([message])

            # Retrieve messages
            messages = await store.list_messages()

            # Serialize for persistence
            state = await store.serialize()

            # Deserialize from saved state
            restored_store = await ChatMessageStore.deserialize(state)
    """

    def __init__(self, messages: Sequence[ChatMessage] | None = None):
        """Create a ChatMessageStore for use in a thread.

        Args:
            messages: The messages to store.
        """
        self.messages = list(messages) if messages else []

    async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
        """Add messages to the store.

        Args:
            messages: Sequence of ChatMessage objects to add to the store.
        """
        self.messages.extend(messages)

    async def list_messages(self) -> list[ChatMessage]:
        """Get all messages from the store in chronological order.

        Returns:
            List of ChatMessage objects, ordered from oldest to newest.
        """
        return self.messages

    @classmethod
    async def deserialize(
        cls: type[TChatMessageStore], serialized_store_state: MutableMapping[str, Any], **kwargs: Any
    ) -> TChatMessageStore:
        """Create a new ChatMessageStore instance from serialized state data.

        Args:
            serialized_store_state: Previously serialized state data containing messages.

        Keyword Args:
            **kwargs: Additional arguments for deserialization.

        Returns:
            A new ChatMessageStore instance populated with messages from the serialized state.
        """
        state = ChatMessageStoreState.from_dict(serialized_store_state, **kwargs)
        if state.messages:
            return cls(messages=state.messages)
        return cls()

    async def update_from_state(self, serialized_store_state: MutableMapping[str, Any], **kwargs: Any) -> None:
        """Update the current ChatMessageStore instance from serialized state data.

        Args:
            serialized_store_state: Previously serialized state data containing messages.

        Keyword Args:
            **kwargs: Additional arguments for deserialization.
        """
        if not serialized_store_state:
            return
        state = ChatMessageStoreState.from_dict(serialized_store_state, **kwargs)
        if state.messages:
            self.messages = state.messages

    async def serialize(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize the current store state for persistence.

        Keyword Args:
            **kwargs: Additional arguments for serialization.

        Returns:
            Serialized state data that can be used with deserialize_state.
        """
        state = ChatMessageStoreState(messages=self.messages)
        return state.to_dict()


TAgentThread = TypeVar("TAgentThread", bound="AgentThread")


class AgentThread:
    """The Agent thread class, this can represent both a locally managed thread or a thread managed by the service.

    An ``AgentThread`` maintains the conversation state and message history for an agent interaction.
    It can either use a service-managed thread (via ``service_thread_id``) or a local message store
    (via ``message_store``), but not both.

    Examples:
        .. code-block:: python

            from agent_framework import ChatAgent, ChatMessageStore
            from agent_framework.openai import OpenAIChatClient

            client = OpenAIChatClient(model="gpt-4o")

            # Create agent with service-managed threads using a service_thread_id
            service_agent = ChatAgent(name="assistant", client=client)
            service_thread = await service_agent.get_new_thread(service_thread_id="thread_abc123")

            # Create agent with service-managed threads using conversation_id
            conversation_agent = ChatAgent(name="assistant", client=client, conversation_id="thread_abc123")
            conversation_thread = await conversation_agent.get_new_thread()

            # Create agent with custom message store factory
            local_agent = ChatAgent(name="assistant", client=client, chat_message_store_factory=ChatMessageStore)
            local_thread = await local_agent.get_new_thread()

            # Serialize and restore thread state
            state = await local_thread.serialize()
            restored_thread = await local_agent.deserialize_thread(state)
    """

    def __init__(
        self,
        *,
        service_thread_id: str | None = None,
        message_store: ChatMessageStoreProtocol | None = None,
        context_provider: AggregateContextProvider | None = None,
    ) -> None:
        """Initialize an AgentThread, do not use this method manually, always use: ``agent.get_new_thread()``.

        Args:
            service_thread_id: The optional ID of the thread managed by the agent service.
            message_store: The optional ChatMessageStore implementation for managing chat messages.
            context_provider: The optional ContextProvider for the thread.

        Note:
            Either ``service_thread_id`` or ``message_store`` may be set, but not both.
        """
        if service_thread_id is not None and message_store is not None:
            raise AgentThreadException("Only the service_thread_id or message_store may be set, but not both.")

        self._service_thread_id = service_thread_id
        self._message_store = message_store
        self.context_provider = context_provider

    @property
    def is_initialized(self) -> bool:
        """Indicates if the thread is initialized.

        This means either the ``service_thread_id`` or the ``message_store`` is set.
        """
        return self._service_thread_id is not None or self._message_store is not None

    @property
    def service_thread_id(self) -> str | None:
        """Gets the ID of the current thread to support cases where the thread is owned by the agent service."""
        return self._service_thread_id

    @service_thread_id.setter
    def service_thread_id(self, service_thread_id: str | None) -> None:
        """Sets the ID of the current thread to support cases where the thread is owned by the agent service.

        Note:
            Either ``service_thread_id`` or ``message_store`` may be set, but not both.
        """
        if service_thread_id is None:
            return

        if self._message_store is not None:
            raise AgentThreadException(
                "Only the service_thread_id or message_store may be set, "
                "but not both and switching from one to another is not supported."
            )
        self._service_thread_id = service_thread_id

    @property
    def message_store(self) -> ChatMessageStoreProtocol | None:
        """Gets the ``ChatMessageStoreProtocol`` used by this thread."""
        return self._message_store

    @message_store.setter
    def message_store(self, message_store: ChatMessageStoreProtocol | None) -> None:
        """Sets the ``ChatMessageStoreProtocol`` used by this thread.

        Note:
            Either ``service_thread_id`` or ``message_store`` may be set, but not both.
        """
        if message_store is None:
            return

        if self._service_thread_id is not None:
            raise AgentThreadException(
                "Only the service_thread_id or message_store may be set, "
                "but not both and switching from one to another is not supported."
            )

        self._message_store = message_store

    async def on_new_messages(self, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Invoked when a new message has been contributed to the chat by any participant.

        Args:
            new_messages: The new ChatMessage or sequence of ChatMessage objects to add to the thread.
        """
        if self._service_thread_id is not None:
            # If the thread messages are stored in the service there is nothing to do here,
            # since invoking the service should already update the thread.
            return
        if self._message_store is None:
            # If there is no conversation id, and no store we can
            # create a default in memory store.
            self._message_store = ChatMessageStore()
        # If a store has been provided, we need to add the messages to the store.
        if isinstance(new_messages, ChatMessage):
            new_messages = [new_messages]
        await self._message_store.add_messages(new_messages)

    async def serialize(self, **kwargs: Any) -> dict[str, Any]:
        """Serializes the current object's state.

        Keyword Args:
            **kwargs: Arguments for serialization.
        """
        chat_message_store_state = None
        if self._message_store is not None:
            chat_message_store_state = await self._message_store.serialize(**kwargs)

        state = AgentThreadState(
            service_thread_id=self._service_thread_id, chat_message_store_state=chat_message_store_state
        )
        return state.to_dict(exclude_none=False)

    @classmethod
    async def deserialize(
        cls: type[TAgentThread],
        serialized_thread_state: MutableMapping[str, Any],
        *,
        message_store: ChatMessageStoreProtocol | None = None,
        **kwargs: Any,
    ) -> TAgentThread:
        """Deserializes the state from a dictionary into a new AgentThread instance.

        Args:
            serialized_thread_state: The serialized thread state as a dictionary.

        Keyword Args:
            message_store: Optional ChatMessageStoreProtocol to use for managing messages.
                If not provided, a new ChatMessageStore will be created if needed.
            **kwargs: Additional arguments for deserialization.

        Returns:
            A new AgentThread instance with properties set from the serialized state.
        """
        state = AgentThreadState.from_dict(serialized_thread_state)

        if state.service_thread_id is not None:
            return cls(service_thread_id=state.service_thread_id)

        # If we don't have any ChatMessageStoreProtocol state return here.
        if state.chat_message_store_state is None:
            return cls()

        if message_store is not None:
            try:
                await message_store.add_messages(state.chat_message_store_state.messages, **kwargs)
            except Exception as ex:
                raise AgentThreadException("Failed to deserialize the provided message store.") from ex
            return cls(message_store=message_store)
        try:
            message_store = ChatMessageStore(messages=state.chat_message_store_state.messages, **kwargs)
        except Exception as ex:
            raise AgentThreadException("Failed to deserialize the message store.") from ex
        return cls(message_store=message_store)

    async def update_from_thread_state(
        self,
        serialized_thread_state: MutableMapping[str, Any],
        **kwargs: Any,
    ) -> None:
        """Deserializes the state from a dictionary into the thread properties.

        Args:
            serialized_thread_state: The serialized thread state as a dictionary.

        Keyword Args:
            **kwargs: Additional arguments for deserialization.
        """
        state = AgentThreadState.from_dict(serialized_thread_state)

        if state.service_thread_id is not None:
            self.service_thread_id = state.service_thread_id
            # Since we have an ID, we should not have a chat message store and we can return here.
            return
        # If we don't have any ChatMessageStoreProtocol state return here.
        if state.chat_message_store_state is None:
            return
        if self.message_store is not None:
            await self.message_store.add_messages(state.chat_message_store_state.messages, **kwargs)
            # If we don't have a chat message store yet, create an in-memory one.
            return
        # Create the message store from the default.
        self.message_store = ChatMessageStore(messages=state.chat_message_store_state.messages, **kwargs)
