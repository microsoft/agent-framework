# Copyright (c) Microsoft. All rights reserved.

"""New-pattern Redis history provider using BaseHistoryProvider.

This module provides ``RedisHistoryProvider``, built on the new
:class:`BaseHistoryProvider` hooks pattern.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

import redis.asyncio as redis
from agent_framework import Message
from agent_framework._sessions import BaseHistoryProvider
from redis.credentials import CredentialProvider


class RedisHistoryProvider(BaseHistoryProvider):
    """Redis-backed history provider using the new BaseHistoryProvider hooks pattern.

    Stores conversation history in Redis Lists, with each session isolated by a
    unique Redis key.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "redis_memory"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        redis_url: str | None = None,
        credential_provider: CredentialProvider | None = None,
        host: str | None = None,
        port: int = 6380,
        ssl: bool = True,
        username: str | None = None,
        *,
        key_prefix: str = "chat_messages",
        max_messages: int | None = None,
        load_messages: bool = True,
        store_outputs: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
    ) -> None:
        """Initialize the Redis history provider.

        Args:
            source_id: Unique identifier for this provider instance.
            redis_url: Redis connection URL (e.g., "redis://localhost:6379").
                Mutually exclusive with credential_provider.
            credential_provider: Redis credential provider for Azure AD authentication.
                Requires host parameter. Mutually exclusive with redis_url.
            host: Redis host name. Required when using credential_provider.
            port: Redis port number. Defaults to 6380 (Azure Redis SSL port).
            ssl: Enable SSL/TLS connection. Defaults to True.
            username: Redis username.
            key_prefix: Prefix for Redis keys. Defaults to 'chat_messages'.
            max_messages: Maximum number of messages to retain per session.
                When exceeded, oldest messages are automatically trimmed.
                None means unlimited storage.
            load_messages: Whether to load messages before invocation.
            store_outputs: Whether to store response messages.
            store_inputs: Whether to store input messages.
            store_context_messages: Whether to store context from other providers.
            store_context_from: If set, only store context from these source_ids.

        Raises:
            ValueError: If neither redis_url nor credential_provider is provided.
            ValueError: If both redis_url and credential_provider are provided.
            ValueError: If credential_provider is used without host parameter.
        """
        super().__init__(
            source_id,
            load_messages=load_messages,
            store_outputs=store_outputs,
            store_inputs=store_inputs,
            store_context_messages=store_context_messages,
            store_context_from=store_context_from,
        )

        if redis_url is None and credential_provider is None:
            raise ValueError("Either redis_url or credential_provider must be provided")
        if redis_url is not None and credential_provider is not None:
            raise ValueError("redis_url and credential_provider are mutually exclusive")
        if credential_provider is not None and host is None:
            raise ValueError("host is required when using credential_provider")

        self.key_prefix = key_prefix
        self.max_messages = max_messages
        self.redis_url = redis_url

        if credential_provider is not None and host is not None:
            self._redis_client = redis.Redis(
                host=host,
                port=port,
                ssl=ssl,
                username=username,
                credential_provider=credential_provider,
                decode_responses=True,
            )
        else:
            self._redis_client = redis.from_url(redis_url, decode_responses=True)  # type: ignore[no-untyped-call]

    def _redis_key(self, session_id: str | None) -> str:
        """Get the Redis key for a given session's messages."""
        return f"{self.key_prefix}:{session_id or 'default'}"

    async def get_messages(self, session_id: str | None, **kwargs: Any) -> list[Message]:
        """Retrieve stored messages for this session from Redis.

        Args:
            session_id: The session ID to retrieve messages for.
            **kwargs: Additional arguments (unused).

        Returns:
            List of stored Message objects in chronological order.
        """
        key = self._redis_key(session_id)
        redis_messages = await self._redis_client.lrange(key, 0, -1)  # type: ignore[misc]
        messages: list[Message] = []
        if redis_messages:
            for serialized in redis_messages:
                messages.append(Message.from_dict(self._deserialize_json(serialized)))
        return messages

    async def save_messages(self, session_id: str | None, messages: Sequence[Message], **kwargs: Any) -> None:
        """Persist messages for this session to Redis.

        Args:
            session_id: The session ID to store messages for.
            messages: The messages to persist.
            **kwargs: Additional arguments (unused).
        """
        if not messages:
            return

        key = self._redis_key(session_id)
        serialized_messages = [self._serialize_json(msg) for msg in messages]

        async with self._redis_client.pipeline(transaction=True) as pipe:
            for serialized in serialized_messages:
                await pipe.rpush(key, serialized)  # type: ignore[misc]
            await pipe.execute()

        if self.max_messages is not None:
            current_count = await self._redis_client.llen(key)  # type: ignore[misc]
            if current_count > self.max_messages:
                await self._redis_client.ltrim(key, -self.max_messages, -1)  # type: ignore[misc]

    @staticmethod
    def _serialize_json(message: Message) -> str:
        """Serialize a Message to a JSON string for Redis storage."""
        import json

        return json.dumps(message.to_dict())

    @staticmethod
    def _deserialize_json(data: str) -> dict[str, Any]:
        """Deserialize a JSON string from Redis to a dict."""
        import json

        return json.loads(data)  # type: ignore[no-any-return]

    async def clear(self, session_id: str | None) -> None:
        """Clear all messages for a session.

        Args:
            session_id: The session ID to clear messages for.
        """
        await self._redis_client.delete(self._redis_key(session_id))

    async def aclose(self) -> None:
        """Close the Redis connection."""
        await self._redis_client.aclose()  # type: ignore[misc]


__all__ = ["RedisHistoryProvider"]
