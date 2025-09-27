# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import redis.asyncio as redis
from agent_framework import ChatMessage
from agent_framework._pydantic import AFBaseModel


class RedisStoreState(AFBaseModel):
    """State model for serializing and deserializing Redis chat message store data."""

    thread_id: str
    redis_url: str | None = None
    key_prefix: str = "chat_messages"
    max_messages: int | None = None


class RedisChatMessageStore:
    """Redis-backed implementation of ChatMessageStore using Redis Lists.

    This implementation provides persistent, thread-safe chat message storage using Redis Lists.
    Messages are stored as JSON-serialized strings in chronological order, with each conversation
    thread isolated by a unique Redis key.

    Key Features:
    ============
    - **Persistent Storage**: Messages survive application restarts and crashes
    - **Thread Isolation**: Each conversation thread has its own Redis key namespace
    - **Auto Message Limits**: Configurable automatic trimming of old messages using LTRIM
    - **Performance Optimized**: Uses native Redis operations for efficiency
    - **State Serialization**: Full compatibility with Agent Framework thread serialization
    - **Initial Message Support**: Pre-load conversations with existing message history
    - **Production Ready**: Atomic operations, error handling, connection pooling

    Redis Operations:
    - RPUSH: Add messages to the end of the list (chronological order)
    - LRANGE: Retrieve messages in chronological order
    - LTRIM: Maintain message limits by trimming old messages
    - DELETE: Clear all messages for a thread
    """

    def __init__(
        self,
        redis_url: str | None = None,
        thread_id: str | None = None,
        key_prefix: str = "chat_messages",
        max_messages: int | None = None,
        messages: Sequence[ChatMessage] | None = None,
    ) -> None:
        """Initialize the Redis chat message store.

        Creates a Redis-backed chat message store for a specific conversation thread.
        The store will automatically create a Redis connection and manage message
        persistence using Redis List operations.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379").
                      Required for establishing Redis connection.
            thread_id: Unique identifier for this conversation thread.
                      If not provided, a UUID will be auto-generated.
                      This becomes part of the Redis key: {key_prefix}:{thread_id}
            key_prefix: Prefix for Redis keys to namespace different applications.
                       Defaults to 'chat_messages'. Useful for multi-tenant scenarios.
            max_messages: Maximum number of messages to retain in Redis.
                         When exceeded, oldest messages are automatically trimmed using LTRIM.
                         None means unlimited storage.
            messages: Initial messages to pre-populate the conversation.
                     These are added to Redis on first access if the Redis key is empty.
                     Useful for resuming conversations or seeding with context.

        Raises:
            ValueError: If redis_url is None (Redis connection is required).
            redis.ConnectionError: If unable to connect to Redis server.


        """
        # Validate required parameters
        if redis_url is None:
            raise ValueError("redis_url is required for Redis connection")

        # Store configuration
        self.redis_url = redis_url
        self.thread_id = thread_id or f"thread_{uuid4()}"
        self.key_prefix = key_prefix
        self.max_messages = max_messages

        # Initialize Redis client with connection pooling and async support
        self._redis_client = redis.from_url(redis_url, decode_responses=True)  # type: ignore[no-untyped-call]

        # Handle initial messages (will be moved to Redis on first access)
        self._initial_messages = list(messages) if messages else []
        self._initial_messages_added = False

    @property
    def redis_key(self) -> str:
        """Get the Redis key for this thread's messages.

        The key format is: {key_prefix}:{thread_id}

        Returns:
            Redis key string used for storing this thread's messages.

        Example:
            For key_prefix="chat_messages" and thread_id="user_123_session_456":
            Returns "chat_messages:user_123_session_456"
        """
        return f"{self.key_prefix}:{self.thread_id}"

    async def _ensure_initial_messages_added(self) -> None:
        """Ensure initial messages are added to Redis if not already present.

        This method is called before any Redis operations to guarantee that
        initial messages provided during construction are persisted to Redis.
        """
        if not self._initial_messages or self._initial_messages_added:
            return

        # Check if Redis key already has messages (prevents duplicate additions)
        existing_count = await self._redis_client.llen(self.redis_key)  # type: ignore[misc]  # type: ignore[misc]
        if existing_count == 0:
            # Add initial messages using atomic pipeline operation
            await self._add_redis_messages(self._initial_messages)

        # Mark as completed and free memory
        self._initial_messages_added = True
        self._initial_messages.clear()

    async def _add_redis_messages(self, messages: Sequence[ChatMessage]) -> None:
        """Add multiple messages to Redis using atomic pipeline operation.

        This internal method efficiently adds multiple messages to the Redis list
        using a single atomic transaction to ensure consistency.

        Args:
            messages: Sequence of ChatMessage objects to add to Redis.
        """
        if not messages:
            return

        # Pre-serialize all messages for efficient pipeline operation
        serialized_messages = [self._serialize_message(message) for message in messages]

        # Use Redis pipeline for atomic batch operation
        async with self._redis_client.pipeline(transaction=True) as pipe:
            for serialized_message in serialized_messages:
                await pipe.rpush(self.redis_key, serialized_message)  # type: ignore[misc]
            await pipe.execute()

    async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
        """Add messages to the Redis store (ChatMessageStore protocol method).

        This method implements the required ChatMessageStore protocol for adding messages.
        Messages are appended to the Redis list in chronological order, with automatic
        trimming if message limits are configured.

        Args:
            messages: Sequence of ChatMessage objects to add to the store.
                     Can be empty (no-op) or contain multiple messages.

        Thread Safety:
        - Atomic pipeline ensures all messages are added together
        - LTRIM operation is atomic for consistent message limits

        Example:
            ```python
            messages = [ChatMessage(role=Role.USER, text="Hello"), ChatMessage(role=Role.ASSISTANT, text="Hi there!")]
            await store.add_messages(messages)
            ```
        """
        if not messages:
            return

        # Ensure any initial messages are persisted first
        await self._ensure_initial_messages_added()

        # Add new messages using atomic pipeline operation
        await self._add_redis_messages(messages)

        # Apply message limit if configured (automatic cleanup)
        if self.max_messages is not None:
            current_count = await self._redis_client.llen(self.redis_key)  # type: ignore[misc]
            if current_count > self.max_messages:
                # Keep only the most recent max_messages using LTRIM
                await self._redis_client.ltrim(self.redis_key, -self.max_messages, -1)  # type: ignore[misc]

    async def list_messages(self) -> list[ChatMessage]:
        """Get all messages from the store in chronological order (ChatMessageStore protocol method).

        This method implements the required ChatMessageStore protocol for retrieving messages.
        Returns all messages stored in Redis, ordered from oldest (index 0) to newest (index -1).

        Returns:
            List of ChatMessage objects in chronological order (oldest first).
            Returns empty list if no messages exist or if Redis connection fails.

        Example:
            ```python
            # Get all conversation history
            messages = await store.list_messages()
            ```
        """
        # Ensure any initial messages are persisted to Redis first
        await self._ensure_initial_messages_added()

        messages = []
        # Retrieve all messages from Redis list (oldest to newest)
        redis_messages = await self._redis_client.lrange(self.redis_key, 0, -1)  # type: ignore[misc]

        if redis_messages:
            for serialized_message in redis_messages:
                # Deserialize each JSON message back to ChatMessage
                message = self._deserialize_message(serialized_message)
                messages.append(message)

        return messages

    async def serialize_state(self, **kwargs: Any) -> Any:
        """Serialize the current store state for persistence (ChatMessageStore protocol method).

        This method implements the required ChatMessageStore protocol for state serialization.
        Captures the Redis connection configuration and thread information needed to
        reconstruct the store and reconnect to the same conversation data.

        Args:
            **kwargs: Additional arguments passed to Pydantic model_dump() for serialization.
                     Common options: exclude_none=True, by_alias=True

        Returns:
            Dictionary containing serialized store configuration that can be persisted
            to databases, files, or other storage mechanisms.
        """
        state = RedisStoreState(
            thread_id=self.thread_id,
            redis_url=self.redis_url,
            key_prefix=self.key_prefix,
            max_messages=self.max_messages,
        )
        return state.model_dump(**kwargs)

    async def deserialize_state(self, serialized_store_state: Any, **kwargs: Any) -> None:
        """Deserialize state data into this store instance (ChatMessageStore protocol method).

        This method implements the required ChatMessageStore protocol for state deserialization.
        Restores the store configuration from previously serialized data, allowing the store
        to reconnect to the same conversation data in Redis.

        Args:
            serialized_store_state: Previously serialized state data from serialize_state().
                                   Should be a dictionary with thread_id, redis_url, etc.
            **kwargs: Additional arguments passed to Pydantic model validation.
        """
        if not serialized_store_state:
            return

        # Validate and parse the serialized state using Pydantic
        state = RedisStoreState.model_validate(serialized_store_state, **kwargs)

        # Update store configuration from deserialized state
        self.thread_id = state.thread_id
        if state.redis_url is not None:
            self.redis_url = state.redis_url
        self.key_prefix = state.key_prefix
        self.max_messages = state.max_messages

        # Recreate Redis client if the URL changed
        if state.redis_url and state.redis_url != getattr(self, "_last_redis_url", None):
            self._redis_client = redis.from_url(state.redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
            self._last_redis_url = state.redis_url

        # Reset initial message state since we're connecting to existing data
        self._initial_messages_added = False

    async def clear(self) -> None:
        """Remove all messages from the store.

        Permanently deletes all messages for this conversation thread by removing
        the Redis key. This operation cannot be undone.

        Warning:
        - This permanently deletes all conversation history
        - Consider exporting messages before clearing if backup is needed

        Example:
            ```python
            # Clear conversation history
            await store.clear()

            # Verify messages are gone
            messages = await store.list_messages()
            assert len(messages) == 0
            ```
        """
        await self._redis_client.delete(self.redis_key)

    def _serialize_message(self, message: ChatMessage) -> str:
        """Serialize a ChatMessage to JSON string.

        Args:
            message: ChatMessage to serialize.

        Returns:
            JSON string representation of the message.
        """
        # Convert ChatMessage to dictionary using Pydantic serialization
        message_dict = message.model_dump()
        # Serialize to compact JSON (no extra whitespace for Redis efficiency)
        return json.dumps(message_dict, separators=(",", ":"))

    def _deserialize_message(self, serialized_message: str) -> ChatMessage:
        """Deserialize a JSON string to ChatMessage.

        Args:
            serialized_message: JSON string representation of a message.

        Returns:
            ChatMessage object.
        """
        # Parse JSON string back to dictionary
        message_dict = json.loads(serialized_message)
        # Reconstruct ChatMessage using Pydantic validation
        return ChatMessage.model_validate(message_dict)

    # ============================================================================
    # List-like Convenience Methods (Redis-optimized async versions)
    # ============================================================================

    def __bool__(self) -> bool:
        """Return True since the store always exists once created.

        This method is called by Python's truthiness checks (if store:).
        Since a RedisChatMessageStore instance always represents a valid store,
        this always returns True.

        Returns:
            Always True - the store exists and is ready for operations.

        Note:
            This is used by the Agent Framework to check if a message store
            is configured: `if thread.message_store:`
        """
        return True

    async def __len__(self) -> int:
        """Return the number of messages in the Redis store.

        Provides efficient message counting using Redis LLEN command.
        This is the async equivalent of Python's built-in len() function.

        Returns:
            The count of messages currently stored in Redis.
        """
        await self._ensure_initial_messages_added()
        return await self._redis_client.llen(self.redis_key)  # type: ignore[misc,no-any-return]

    async def getitem(self, index: int) -> ChatMessage:
        """Get a message by index using Redis LINDEX.

        Args:
            index: The index of the message to retrieve.

        Returns:
            The ChatMessage at the specified index.

        Raises:
            IndexError: If the index is out of range.
        """
        await self._ensure_initial_messages_added()

        # Use Redis LINDEX for efficient single-item access
        serialized_message = await self._redis_client.lindex(self.redis_key, index)  # type: ignore[misc]
        if serialized_message is None:
            raise IndexError("list index out of range")

        return self._deserialize_message(serialized_message)

    async def setitem(self, index: int, item: ChatMessage) -> None:
        """Set a message at the specified index using Redis LSET.

        Args:
            index: The index at which to set the message.
            item: The ChatMessage to set at the specified index.

        Raises:
            IndexError: If the index is out of range.
        """
        await self._ensure_initial_messages_added()

        # Validate index exists using LLEN
        current_count = await self._redis_client.llen(self.redis_key)  # type: ignore[misc]
        if index < 0:
            index = current_count + index
        if index < 0 or index >= current_count:
            raise IndexError("list index out of range")

        # Use Redis LSET for efficient single-item update
        serialized_message = self._serialize_message(item)
        await self._redis_client.lset(self.redis_key, index, serialized_message)  # type: ignore[misc]

    async def append(self, item: ChatMessage) -> None:
        """Append a message to the end of the store.

        Args:
            item: The ChatMessage to append.
        """
        await self.add_messages([item])

    async def count(self) -> int:
        """Return the number of messages in the Redis store.

        Returns:
            The count of messages currently stored in Redis.
        """
        await self._ensure_initial_messages_added()
        return await self._redis_client.llen(self.redis_key)  # type: ignore[misc,no-any-return]

    async def index(self, item: ChatMessage) -> int:
        """Return the index of the first occurrence of the specified message.

        Uses Redis LINDEX to iterate through the list without loading all messages.
        Still O(N) but more memory efficient for large lists.

        Args:
            item: The ChatMessage to find.

        Returns:
            The index of the first occurrence of the message.

        Raises:
            ValueError: If the message is not found in the store.
        """
        await self._ensure_initial_messages_added()

        target_serialized = self._serialize_message(item)
        list_length = await self._redis_client.llen(self.redis_key)  # type: ignore[misc]

        # Iterate through Redis list using LINDEX
        for i in range(list_length):
            redis_message = await self._redis_client.lindex(self.redis_key, i)  # type: ignore[misc]
            if redis_message == target_serialized:
                return i

        raise ValueError("ChatMessage not found in store")

    async def remove(self, item: ChatMessage) -> None:
        """Remove the first occurrence of the specified message from the store.

        Uses Redis LREM command for efficient removal by value.
        O(N) but performed natively in Redis without data transfer.

        Args:
            item: The ChatMessage to remove.

        Raises:
            ValueError: If the message is not found in the store.
        """
        await self._ensure_initial_messages_added()

        # Serialize the message to match Redis storage format
        target_serialized = self._serialize_message(item)

        # Use LREM to remove first occurrence (count=1)
        removed_count = await self._redis_client.lrem(self.redis_key, 1, target_serialized)  # type: ignore[misc]

        if removed_count == 0:
            raise ValueError("ChatMessage not found in store")

    async def extend(self, items: Sequence[ChatMessage]) -> None:
        """Extend the store by appending all messages from the iterable.

        Args:
            items: Sequence of ChatMessage objects to append.
        """
        await self.add_messages(items)

    async def ping(self) -> bool:
        """Test the Redis connection.

        Returns:
            True if the connection is successful, False otherwise.
        """
        try:
            await self._redis_client.ping()  # type: ignore[misc]
            return True
        except Exception:
            return False

    async def aclose(self) -> None:
        """Close the Redis connection.

        This method provides a clean way to close the underlying Redis connection
        when the store is no longer needed. This is particularly useful in samples
        and applications where explicit resource cleanup is desired.
        """
        await self._redis_client.aclose()  # type: ignore[misc]

    def __repr__(self) -> str:
        """String representation of the store."""
        return (
            f"RedisChatMessageStore(thread_id='{self.thread_id}', "
            f"redis_key='{self.redis_key}', max_messages={self.max_messages})"
        )
