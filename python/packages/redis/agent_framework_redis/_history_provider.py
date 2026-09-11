# Copyright (c) Microsoft. All rights reserved.

"""New-pattern Redis history provider using HistoryProvider.

This module provides ``RedisHistoryProvider``, built on the new
:class:`HistoryProvider` hooks pattern.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Awaitable, Sequence
from inspect import isawaitable
from typing import Any, ClassVar, Literal, TypeVar, cast

import redis.asyncio as redis
from agent_framework import Message
from agent_framework._filesystem import _storage_key_segment  # pyright: ignore[reportPrivateUsage]
from agent_framework._sessions import HistoryProvider, filter_new_messages
from agent_framework._telemetry import mark_feature_used
from redis.credentials import CredentialProvider

from ._feature_usage import FeatureIndex

_T = TypeVar("_T")


async def _redis_result(value: Awaitable[_T] | _T) -> _T:
    """Await a redis-py command result that is annotated as the sync/async union.

    Several redis-py commands are annotated as returning ``Awaitable[T] | T`` even on the asyncio
    client, so awaiting them directly does not type-check. Newer redis-py releases narrow those
    annotations to the awaitable alone, which makes a bare ``# type: ignore`` *required* on the
    older annotations and *unnecessary* on the newer ones: no single ignore comment satisfies the
    whole supported range. Normalising through this helper type-checks on every supported version
    without an ignore comment.
    """
    if isawaitable(value):
        return cast("_T", await value)
    return cast("_T", value)


class RedisHistoryProvider(HistoryProvider):
    """Redis-backed history provider using the new HistoryProvider hooks pattern.

    Stores conversation history in Redis Lists, with each session isolated by a
    key scoped to the application, optional tenant and agent, and provider source.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "redis_memory"
    _ENCODED_KEY_PREFIX: ClassVar[str] = "~redis-key-prefix-"
    _ENCODED_TENANT_PREFIX: ClassVar[str] = "~redis-tenant-"
    _ENCODED_APPLICATION_PREFIX: ClassVar[str] = "~redis-application-"
    _ENCODED_AGENT_PREFIX: ClassVar[str] = "~redis-agent-"
    _ENCODED_SOURCE_PREFIX: ClassVar[str] = "~redis-source-"
    _ENCODED_SESSION_PREFIX: ClassVar[str] = "~redis-session-"
    _ABSENT_SCOPE_SEGMENT: ClassVar[str] = "~none"

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
        tenant_id: str | None = None,
        application_id: str | None = None,
        agent_id: str | None = None,
        key_format: Literal["scoped", "legacy"] = "scoped",
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
            key_prefix: Base prefix for Redis keys. Scoped mode appends independently encoded
                tenant, application, agent, provider source, and session segments.
                Defaults to 'chat_messages'.
            tenant_id: Optional tenant identifier used as an independent key boundary.
            application_id: Application identifier used as a required key boundary in scoped mode.
            agent_id: Optional agent identifier used as an independent key boundary.
            key_format: Redis key format. ``"scoped"`` isolates history by tenant,
                application, agent, provider source, and session. ``"legacy"``
                preserves the historical ``{key_prefix}:{session_id}`` format for
                explicit migration compatibility. Scoped identifiers cannot be
                supplied in legacy mode. Defaults to ``"scoped"``.
            max_messages: Maximum number of messages to retain per session.
                When exceeded, oldest messages are automatically trimmed.
                None means unlimited storage; 0 retains nothing, and no message
                payload is written to Redis at all. Stored history is left as it
                is - use ``clear`` to remove it.
            load_messages: Whether to load messages before invocation.
            store_outputs: Whether to store response messages.
            store_inputs: Whether to store input messages.
            store_context_messages: Whether to store context from other providers.
            store_context_from: If set, only store context from these source_ids.

        Raises:
            ValueError: If neither redis_url nor credential_provider is provided.
            ValueError: If both redis_url and credential_provider are provided.
            ValueError: If credential_provider is used without host parameter.
            ValueError: If max_messages is negative.
            ValueError: If key_format or its scoped identifiers are invalid.
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
        if max_messages is not None and max_messages < 0:
            raise ValueError("max_messages must be None (unlimited) or a non-negative integer")
        if key_format not in ("scoped", "legacy"):
            raise ValueError("key_format must be 'scoped' or 'legacy'")
        if key_format == "scoped":
            if not application_id:
                raise ValueError("application_id must be a non-empty string when key_format='scoped'")
            if tenant_id == "":
                raise ValueError("tenant_id must be non-empty when supplied")
            if agent_id == "":
                raise ValueError("agent_id must be non-empty when supplied")
        elif any(scope is not None for scope in (tenant_id, application_id, agent_id)):
            raise ValueError("tenant_id, application_id, and agent_id cannot be used with key_format='legacy'")
        if key_format == "legacy":
            warnings.warn(
                "key_format='legacy' is deprecated and will be removed in a future version. "
                "Migrate persisted history to scoped keys and use key_format='scoped'.",
                DeprecationWarning,
                stacklevel=2,
            )

        self.key_prefix = key_prefix
        self.tenant_id = tenant_id
        self.application_id = application_id
        self.agent_id = agent_id
        self.key_format = key_format
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

    @classmethod
    def _optional_scope_segment(cls, value: str | None, *, encoded_prefix: str) -> str:
        """Encode an optional isolation boundary without conflating absence with a caller value."""
        if value is None:
            return cls._ABSENT_SCOPE_SEGMENT
        return _storage_key_segment(value, encoded_prefix=encoded_prefix)

    def _redis_key(self, session_id: str | None) -> str:
        """Get a pipe-delimited scoped key or the historical colon-delimited legacy key."""
        if self.key_format == "legacy":
            return f"{self.key_prefix}:{session_id or 'default'}"
        if not session_id:
            raise ValueError("session_id must be a non-empty string when key_format='scoped'")

        key_prefix_segment = _storage_key_segment(
            self.key_prefix,
            encoded_prefix=self._ENCODED_KEY_PREFIX,
        )
        tenant_segment = self._optional_scope_segment(
            self.tenant_id,
            encoded_prefix=self._ENCODED_TENANT_PREFIX,
        )
        agent_segment = self._optional_scope_segment(
            self.agent_id,
            encoded_prefix=self._ENCODED_AGENT_PREFIX,
        )
        application_segment = _storage_key_segment(
            cast("str", self.application_id),
            encoded_prefix=self._ENCODED_APPLICATION_PREFIX,
        )
        source_segment = _storage_key_segment(self.source_id, encoded_prefix=self._ENCODED_SOURCE_PREFIX)
        session_segment = _storage_key_segment(session_id, encoded_prefix=self._ENCODED_SESSION_PREFIX)
        return "|".join((
            key_prefix_segment,
            "v2",
            tenant_segment,
            application_segment,
            agent_segment,
            source_segment,
            session_segment,
        ))

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        """Retrieve stored messages for this session from Redis.

        Args:
            session_id: The session ID to retrieve messages for.
            state: Optional session state. Unused for Redis-backed history.
            **kwargs: Additional arguments (unused).

        Returns:
            List of stored Message objects in chronological order.
        """
        mark_feature_used(FeatureIndex.REDIS)
        key = self._redis_key(session_id)
        # ``lrange`` is annotated with a partially unknown return type across the supported redis
        # range, so neither keeping nor dropping an ignore comment here is correct for all of it.
        # Reaching the method through an explicitly ``Any``-typed client makes the call site
        # version-independent, and the outer cast pins the element type that
        # ``decode_responses=True`` guarantees.
        redis_messages = cast("list[str]", await _redis_result(cast("Any", self._redis_client).lrange(key, 0, -1)))
        messages: list[Message] = []
        for serialized in redis_messages:
            messages.append(Message.from_dict(self._deserialize_json(serialized)))
        return messages

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Persist messages for this session to Redis.

        Args:
            session_id: The session ID to store messages for.
            messages: The messages to persist.
            state: Optional session state. Unused for Redis-backed history.
            **kwargs: Additional arguments (unused).
        """
        mark_feature_used(FeatureIndex.REDIS)
        key = self._redis_key(session_id)
        if not messages:
            return

        if self.max_messages == 0:
            # Retention is disabled. Trimming cannot express this - LTRIM key 0 -1 keeps
            # the whole list - so return before serializing: no payload reaches Redis, an
            # AOF or a replica. Stored history is deliberately left alone; removing stored
            # history is what clear() is for.
            return

        existing_messages = await self.get_messages(session_id, state=state, **kwargs)
        new_messages = filter_new_messages(existing_messages, messages)

        if not new_messages:
            return

        serialized_messages = [self._serialize_json(msg) for msg in new_messages]

        async with self._redis_client.pipeline(transaction=True) as pipe:
            for serialized in serialized_messages:
                await _redis_result(pipe.rpush(key, serialized))
            await pipe.execute()

        if self.max_messages is not None:
            current_count: int = await _redis_result(self._redis_client.llen(key))
            if current_count > self.max_messages:
                await _redis_result(self._redis_client.ltrim(key, -self.max_messages, -1))

    @staticmethod
    def _serialize_json(message: Message) -> str:
        """Serialize a Message to a JSON string for Redis storage."""
        return json.dumps(message.to_dict())

    @staticmethod
    def _deserialize_json(data: str) -> dict[str, Any]:
        """Deserialize a JSON string from Redis to a dict."""
        return json.loads(data)

    async def clear(self, session_id: str | None) -> None:
        """Clear all messages for a session.

        Args:
            session_id: The session ID to clear messages for.
        """
        await self._redis_client.delete(self._redis_key(session_id))

    async def aclose(self) -> None:
        """Close the Redis connection."""
        await self._redis_client.aclose()


__all__ = ["RedisHistoryProvider"]
