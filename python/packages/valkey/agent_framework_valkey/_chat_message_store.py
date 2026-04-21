# Copyright (c) Microsoft. All rights reserved.

"""Valkey-backed chat message store using HistoryProvider.

This module provides ``ValkeyChatMessageStore``, a persistent conversation
history provider built on the :class:`HistoryProvider` hooks pattern, using
valkey-glide (the official Valkey Python client) for basic key-value operations.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any, ClassVar

from agent_framework import Message
from agent_framework._sessions import HistoryProvider

try:
    from glide import GlideClient, GlideClientConfiguration, NodeAddress
except ImportError:
    GlideClient = None  # type: ignore[assignment,misc]
    GlideClientConfiguration = None  # type: ignore[assignment,misc]
    NodeAddress = None  # type: ignore[assignment,misc]

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


def _check_glide_available() -> None:
    """Raise a clear error if valkey-glide is not installed."""
    if GlideClient is None:
        raise ImportError(
            "valkey-glide is required but not installed. "
            "It is not available on Windows. "
            "Install it with: pip install valkey-glide"
        )


class ValkeyChatMessageStore(HistoryProvider):
    """Valkey-backed history provider using the HistoryProvider hooks pattern.

    Stores conversation history in Valkey Lists, with each session isolated
    by a unique key. Uses valkey-glide for all operations.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "valkey_memory"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        valkey_url: str | None = None,
        host: str | None = None,
        port: int | None = None,
        *,
        use_tls: bool = False,
        key_prefix: str = "chat_messages",
        max_messages: int | None = None,
        load_messages: bool = True,
        store_outputs: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
        client: "GlideClient | None" = None,
    ) -> None:
        """Initialize the Valkey chat message store.

        Args:
            source_id: Unique identifier for this provider instance.
            valkey_url: Valkey connection URL (e.g., "valkey://localhost:6379").
                If provided, host and port are extracted from the URL.
                Mutually exclusive with explicit host/port.
            host: Valkey server hostname. Defaults to "localhost" when neither
                valkey_url nor client is provided.
            port: Valkey server port. Defaults to 6379 when neither valkey_url
                nor client is provided.
            use_tls: Enable TLS for the connection. Defaults to False.
            key_prefix: Prefix for Valkey keys. Defaults to "chat_messages".
            max_messages: Maximum number of messages to retain per session.
                When exceeded, oldest messages are automatically trimmed.
                None means unlimited storage.
            load_messages: Whether to load messages before invocation.
            store_outputs: Whether to store response messages.
            store_inputs: Whether to store input messages.
            store_context_messages: Whether to store context from other providers.
            store_context_from: If set, only store context from these source_ids.
            client: A pre-created GlideClient instance. If provided, host/port/url
                are ignored and the caller is responsible for the client lifecycle.
        """
        _check_glide_available()
        super().__init__(
            source_id,
            load_messages=load_messages,
            store_outputs=store_outputs,
            store_inputs=store_inputs,
            store_context_messages=store_context_messages,
            store_context_from=store_context_from,
        )

        # Validate mutually exclusive connection params
        if client is None and valkey_url is not None and (host is not None or port is not None):
            raise ValueError("valkey_url and explicit host/port are mutually exclusive.")

        self.key_prefix = key_prefix
        self.max_messages = max_messages
        self.valkey_url = valkey_url
        self.host = host or "localhost"
        self.port = port or 6379
        self.use_tls = use_tls
        self._client: GlideClient | None = client  # type: ignore[assignment]
        self._owns_client = client is None

    async def _get_client(self) -> GlideClient:  # type: ignore[return]
        """Get or create the Valkey client."""
        if self._client is None:
            if self.valkey_url is not None:
                host, port = self._parse_url(self.valkey_url)
            else:
                host, port = self.host, self.port
            config = GlideClientConfiguration(
                addresses=[NodeAddress(host=host, port=port)],
                use_tls=self.use_tls,
            )
            self._client = await GlideClient.create(config)
        return self._client

    @staticmethod
    def _parse_url(url: str) -> tuple[str, int]:
        """Parse a Valkey URL into host and port components.

        Args:
            url: A URL like "valkey://host:port" or "redis://host:port".

        Returns:
            A tuple of (host, port).
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        return host, port

    def _valkey_key(self, session_id: str | None) -> str:
        """Get the Valkey key for a given session's messages."""
        return f"{self.key_prefix}:{session_id or 'default'}"

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        """Retrieve stored messages for this session from Valkey.

        Args:
            session_id: The session ID to retrieve messages for.
            state: Optional session state. Unused for Valkey-backed history.
            **kwargs: Additional arguments (unused).

        Returns:
            List of stored Message objects in chronological order.
        """
        client = await self._get_client()
        key = self._valkey_key(session_id)
        raw_messages = await client.lrange(key, 0, -1)
        messages: list[Message] = []
        if raw_messages:
            for raw in raw_messages:
                decoded = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                messages.append(Message.from_dict(json.loads(decoded)))
        return messages

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Persist messages for this session to Valkey.

        Args:
            session_id: The session ID to store messages for.
            messages: The messages to persist.
            state: Optional session state. Unused for Valkey-backed history.
            **kwargs: Additional arguments (unused).
        """
        if not messages:
            return

        client = await self._get_client()
        key = self._valkey_key(session_id)
        serialized_messages = [json.dumps(msg.to_dict()) for msg in messages]

        await client.rpush(key, serialized_messages)  # pyright: ignore[reportArgumentType]

        if self.max_messages is not None:
            await client.ltrim(key, -self.max_messages, -1)

    async def clear(self, session_id: str | None) -> None:
        """Clear all messages for a session.

        Args:
            session_id: The session ID to clear messages for.
        """
        client = await self._get_client()
        await client.delete([self._valkey_key(session_id)])

    async def aclose(self) -> None:
        """Close the Valkey connection if owned by this instance."""
        if self._owns_client and self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.aclose()


__all__ = ["ValkeyChatMessageStore"]
