# Copyright (c) Microsoft. All rights reserved.

"""Redis-based streaming response handler for durable agents.

This module provides reliable, resumable streaming of agent responses using Redis Streams
as a message broker. It enables clients to disconnect and reconnect without losing messages.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import timedelta
from collections.abc import AsyncIterator

import redis.asyncio as aioredis


@dataclass
class StreamChunk:
    """Represents a chunk of streamed data from Redis.

    Attributes:
        entry_id: The Redis stream entry ID (used as cursor for resumption).
        text: The text content of the chunk, if any.
        is_done: Whether this is the final chunk in the stream.
        error: Error message if an error occurred, otherwise None.
    """
    entry_id: str
    text: str | None = None
    is_done: bool = False
    error: str | None = None


class RedisStreamResponseHandler:
    """Handles agent responses by persisting them to Redis Streams.

    This handler writes agent response updates to Redis Streams, enabling reliable,
    resumable streaming delivery to clients. Clients can disconnect and reconnect
    at any point using cursor-based pagination.

    Attributes:
        MAX_EMPTY_READS: Maximum number of empty reads before timing out.
        POLL_INTERVAL_MS: Interval in milliseconds between polling attempts.
    """

    MAX_EMPTY_READS = 300
    POLL_INTERVAL_MS = 1000

    def __init__(self, redis_client: aioredis.Redis, stream_ttl: timedelta):
        """Initialize the Redis stream response handler.

        Args:
            redis_client: The async Redis client instance.
            stream_ttl: Time-to-live for stream entries in Redis.
        """
        self._redis = redis_client
        self._stream_ttl = stream_ttl

    async def __aenter__(self):
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Exit async context manager and close Redis connection."""
        await self._redis.aclose()

    async def write_chunk(
        self,
        conversation_id: str,
        text: str,
        sequence: int,
    ) -> None:
        """Write a single text chunk to the Redis Stream.

        Args:
            conversation_id: The conversation ID for this agent run.
            text: The text content to write.
            sequence: The sequence number for ordering.
        """
        stream_key = self._get_stream_key(conversation_id)
        await self._redis.xadd(
            stream_key,
            {
                "text": text,
                "sequence": str(sequence),
                "timestamp": str(int(time.time() * 1000)),
            }
        )
        await self._redis.expire(stream_key, self._stream_ttl)

    async def write_completion(
        self,
        conversation_id: str,
        sequence: int,
    ) -> None:
        """Write an end-of-stream marker to the Redis Stream.

        Args:
            conversation_id: The conversation ID for this agent run.
            sequence: The final sequence number.
        """
        stream_key = self._get_stream_key(conversation_id)
        await self._redis.xadd(
            stream_key,
            {
                "text": "",
                "sequence": str(sequence),
                "timestamp": str(int(time.time() * 1000)),
                "done": "true",
            }
        )
        await self._redis.expire(stream_key, self._stream_ttl)

    async def read_stream(
        self,
        conversation_id: str,
        cursor: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Read entries from a Redis Stream with cursor-based pagination.

        This method polls the Redis Stream for new entries, yielding chunks as they
        become available. Clients can resume from any point using the entry_id from
        a previous chunk.

        Args:
            conversation_id: The conversation ID to read from.
            cursor: Optional cursor to resume from. If None, starts from beginning.

        Yields:
            StreamChunk instances containing text content or status markers.
        """
        stream_key = self._get_stream_key(conversation_id)
        start_id = cursor if cursor else "0-0"

        empty_read_count = 0
        has_seen_data = False

        while True:
            try:
                # Read up to 100 entries from the stream
                entries = await self._redis.xread(
                    {stream_key: start_id},
                    count=100,
                    block=None,
                )

                if not entries:
                    # No entries found
                    if not has_seen_data:
                        empty_read_count += 1
                        if empty_read_count >= self.MAX_EMPTY_READS:
                            timeout_seconds = self.MAX_EMPTY_READS * self.POLL_INTERVAL_MS / 1000
                            yield StreamChunk(
                                entry_id=start_id,
                                error=f"Stream not found or timed out after {timeout_seconds} seconds"
                            )
                            return

                    # Wait before polling again
                    await asyncio.sleep(self.POLL_INTERVAL_MS / 1000)
                    continue

                has_seen_data = True

                # Process entries from the stream
                for _stream_name, stream_entries in entries:
                    for entry_id, entry_data in stream_entries:
                        start_id = entry_id.decode() if isinstance(entry_id, bytes) else entry_id

                        # Decode entry data
                        text = entry_data.get(b"text", b"").decode() if b"text" in entry_data else None
                        done = entry_data.get(b"done", b"").decode() if b"done" in entry_data else None
                        error = entry_data.get(b"error", b"").decode() if b"error" in entry_data else None

                        if error:
                            yield StreamChunk(entry_id=start_id, error=error)
                            return

                        if done == "true":
                            yield StreamChunk(entry_id=start_id, is_done=True)
                            return

                        if text:
                            yield StreamChunk(entry_id=start_id, text=text)

            except Exception as ex:
                yield StreamChunk(entry_id=start_id, error=str(ex))
                return

    @staticmethod
    def _get_stream_key(conversation_id: str) -> str:
        """Generate the Redis key for a conversation's stream.

        Args:
            conversation_id: The conversation ID.

        Returns:
            The Redis stream key.
        """
        return f"agent-stream:{conversation_id}"
