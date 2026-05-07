# Copyright (c) Microsoft. All rights reserved.

"""Valkey-backed resumable stream buffer for durable agent responses.

This module provides :class:`ValkeyStreamBuffer`, a reliable streaming buffer
that persists agent response chunks to Valkey Streams (``XADD``/``XREAD``)
using the ``valkey-glide`` client.  Clients can disconnect and reconnect
mid-stream without data loss by supplying the last-seen entry ID as a cursor.

The class implements :class:`AgentResponseCallbackProtocol` so it can be
registered directly as a callback with durable agent workers, and also
exposes lower-level ``write_chunk`` / ``read_stream`` methods for custom
integration.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from agent_framework import AgentResponse, AgentResponseUpdate
    from agent_framework_durabletask import AgentCallbackContext
    from glide import GlideClient, GlideClusterClient

# Union accepted by all public methods so callers can pass either client type.
TGlideClient = Union["GlideClient", "GlideClusterClient"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------
_DEFAULT_STREAM_TTL = timedelta(minutes=10)
_DEFAULT_KEY_PREFIX = "agent-stream"
_MAX_EMPTY_READS = 300
_POLL_INTERVAL_SECONDS = 1.0
# Number of entries to fetch per XREAD call.  Kept as a module constant
# rather than a constructor parameter because tuning it has negligible
# impact on correctness — it only affects per-poll batch size.
_READ_COUNT = 100


@dataclass
class StreamChunk:
    """A single chunk read from a Valkey Stream.

    Attributes:
        entry_id: The Valkey stream entry ID (use as cursor for resumption).
        text: The text content of the chunk, if any.
        is_done: Whether this chunk marks the end of the stream.
        error: Error message if something went wrong, otherwise ``None``.
    """

    entry_id: str
    text: str | None = None
    is_done: bool = False
    error: str | None = None


class ValkeyStreamBuffer:
    """Resumable stream buffer backed by Valkey Streams.

    Writes agent response chunks via ``XADD`` and reads them back via
    ``XREAD``, supporting cursor-based resumption.  Each conversation gets
    its own Valkey Stream keyed by ``{key_prefix}:{conversation_id}``.

    The class also satisfies the ``AgentResponseCallbackProtocol`` from
    ``agent-framework-durabletask`` so it can be passed directly as a
    ``callback`` when registering agents with a durable worker.

    Args:
        client: A connected ``GlideClient`` or ``GlideClusterClient``.
        stream_ttl: Time-to-live for stream keys.  Refreshed on every write.
        key_prefix: Prefix for Valkey stream keys.
        max_empty_reads: Maximum consecutive empty reads before timing out
            on the read side.
        poll_interval_seconds: Seconds to sleep between read polls.

    Example:
        .. code-block:: python

            from glide import GlideClient, GlideClientConfiguration, NodeAddress
            from agent_framework_valkey import ValkeyStreamBuffer

            config = GlideClientConfiguration([NodeAddress("localhost", 6379)])
            client = await GlideClient.create(config)
            buffer = ValkeyStreamBuffer(client=client)

            # Write side
            await buffer.write_chunk("conv-1", "Hello, ", 0)
            await buffer.write_chunk("conv-1", "world!", 1)
            await buffer.write_completion("conv-1", 2)

            # Read side
            async for chunk in buffer.read_stream("conv-1"):
                if chunk.is_done:
                    break
                print(chunk.text, end="")
    """

    def __init__(
        self,
        client: TGlideClient,
        *,
        stream_ttl: timedelta = _DEFAULT_STREAM_TTL,
        key_prefix: str = _DEFAULT_KEY_PREFIX,
        max_empty_reads: int = _MAX_EMPTY_READS,
        poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
    ) -> None:
        if client is None:
            raise ValueError("client must not be None")
        self._client: TGlideClient = client
        self._stream_ttl_seconds = int(stream_ttl.total_seconds())
        self._key_prefix = key_prefix
        self._max_empty_reads = max_empty_reads
        self._poll_interval_seconds = poll_interval_seconds
        # Track per-conversation sequence numbers for callback usage.
        self._sequence_numbers: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    async def write_chunk(
        self,
        conversation_id: str,
        text: str,
        sequence: int,
    ) -> None:
        """Write a single text chunk to the Valkey Stream.

        Args:
            conversation_id: Conversation / session identifier.
            text: The text content to persist.
            sequence: Monotonically increasing sequence number.

        Raises:
            ValueError: If *conversation_id* is empty.
        """
        stream_key = self._stream_key(conversation_id)
        await self._xadd_and_expire(
            stream_key,
            [
                ("text", text),
                ("sequence", str(sequence)),
                ("timestamp", str(int(time.time() * 1000))),
            ],
        )

    async def write_completion(
        self,
        conversation_id: str,
        sequence: int,
    ) -> None:
        """Write an end-of-stream sentinel to the Valkey Stream.

        Args:
            conversation_id: Conversation / session identifier.
            sequence: Final sequence number.

        Raises:
            ValueError: If *conversation_id* is empty.
        """
        stream_key = self._stream_key(conversation_id)
        await self._xadd_and_expire(
            stream_key,
            [
                ("text", ""),
                ("sequence", str(sequence)),
                ("timestamp", str(int(time.time() * 1000))),
                ("done", "true"),
            ],
        )

    async def write_error(
        self,
        conversation_id: str,
        error: str,
        sequence: int,
    ) -> None:
        """Write an error entry to the Valkey Stream.

        Args:
            conversation_id: Conversation / session identifier.
            error: The error message.
            sequence: Sequence number.

        Raises:
            ValueError: If *conversation_id* is empty.
        """
        stream_key = self._stream_key(conversation_id)
        await self._xadd_and_expire(
            stream_key,
            [
                ("error", error),
                ("sequence", str(sequence)),
                ("timestamp", str(int(time.time() * 1000))),
            ],
        )

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    async def read_stream(
        self,
        conversation_id: str,
        cursor: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Read chunks from a Valkey Stream with cursor-based resumption.

        Polls the stream for new entries, yielding :class:`StreamChunk`
        instances as they arrive.  Pass the ``entry_id`` of the last
        received chunk as ``cursor`` to resume after a disconnect.

        The reader times out after ``max_empty_reads`` consecutive empty
        polls — both before *and* after data has been seen.  This prevents
        the reader from polling forever if the producer crashes mid-stream.

        Args:
            conversation_id: Conversation / session identifier.
            cursor: Entry ID to resume from (exclusive).  ``None`` reads
                from the beginning.

        Yields:
            :class:`StreamChunk` instances.

        Raises:
            ValueError: If *conversation_id* is empty.
        """
        stream_key = self._stream_key(conversation_id)
        start_id = cursor if cursor else "0-0"

        # Build read options if valkey-glide is installed.  On Windows the
        # package is unavailable, but unit tests still exercise this path
        # with a mocked client that accepts any arguments.
        read_options = None
        try:
            from glide import StreamReadOptions

            read_options = StreamReadOptions(count=_READ_COUNT)
        except ImportError:
            pass

        empty_read_count = 0

        while True:
            try:
                if read_options is not None:
                    result = await self._client.xread(  # type: ignore[union-attr]
                        {stream_key: start_id},
                        read_options,
                    )
                else:
                    result = await self._client.xread(  # type: ignore[union-attr]
                        {stream_key: start_id},
                    )

                if not result:
                    empty_read_count += 1
                    if empty_read_count >= self._max_empty_reads:
                        timeout_secs = self._max_empty_reads * self._poll_interval_seconds
                        yield StreamChunk(
                            entry_id=start_id,
                            error=f"Stream not found or timed out after {timeout_secs} seconds",
                        )
                        return

                    await asyncio.sleep(self._poll_interval_seconds)
                    continue

                # Reset counter whenever we receive data so a stalled
                # producer is detected even after earlier successful reads.
                empty_read_count = 0

                for _stream_name, entries in result.items():
                    for entry_id_bytes, fields_list in entries.items():
                        entry_id = _decode_value(entry_id_bytes)
                        start_id = entry_id

                        # Convert [[field, value], ...] list to a dict.
                        fields = _fields_list_to_dict(fields_list)

                        error_val = fields.get(b"error")
                        if error_val:
                            yield StreamChunk(entry_id=entry_id, error=_decode_value(error_val))
                            return

                        done_val = fields.get(b"done")
                        if done_val and _decode_value(done_val) == "true":
                            yield StreamChunk(entry_id=entry_id, is_done=True)
                            return

                        if b"text" in fields:
                            text_str = _decode_value(fields[b"text"])
                            yield StreamChunk(entry_id=entry_id, text=text_str)

            except Exception as exc:
                yield StreamChunk(entry_id=start_id, error=str(exc))
                return

    # ------------------------------------------------------------------
    # AgentResponseCallbackProtocol implementation
    # ------------------------------------------------------------------

    async def on_streaming_response_update(
        self,
        update: AgentResponseUpdate,
        context: AgentCallbackContext,
    ) -> None:
        """Handle a streaming response update from a durable agent.

        Satisfies ``AgentResponseCallbackProtocol.on_streaming_response_update``.
        """
        thread_id: str | None = context.thread_id
        if not thread_id:
            return

        text: str | None = update.text if update.text else None
        if not text:
            return

        seq = self._sequence_numbers.get(thread_id, 0)
        self._sequence_numbers[thread_id] = seq + 1
        await self.write_chunk(thread_id, text, seq)

    async def on_agent_response(
        self,
        response: AgentResponse,
        context: AgentCallbackContext,
    ) -> None:
        """Handle the final agent response from a durable agent.

        Satisfies ``AgentResponseCallbackProtocol.on_agent_response``.
        """
        thread_id: str | None = context.thread_id
        if not thread_id:
            return

        seq = self._sequence_numbers.pop(thread_id, 0)
        await self.write_completion(thread_id, seq)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _stream_key(self, conversation_id: str) -> str:
        """Build the Valkey key for a conversation stream.

        Raises:
            ValueError: If *conversation_id* is empty.
        """
        if not conversation_id:
            raise ValueError("conversation_id must not be empty")
        return f"{self._key_prefix}:{conversation_id}"

    async def _xadd_and_expire(
        self,
        stream_key: str,
        fields: list[tuple[str, str]],
    ) -> None:
        """Append an entry to a stream and refresh its TTL.

        Note: ``XADD`` and ``EXPIRE`` are issued as two separate commands, so
        a crash between them could leave a key without a TTL.  In practice
        this is self-healing — the TTL is refreshed on every subsequent write,
        and Valkey's memory-eviction policy covers the final-write edge case.
        """
        await self._client.xadd(stream_key, fields)  # type: ignore[union-attr]
        await self._client.expire(stream_key, self._stream_ttl_seconds)  # type: ignore[union-attr]


def _decode_value(val: bytes | str) -> str:
    """Decode a bytes or str value to str."""
    return val.decode() if isinstance(val, bytes) else str(val)


def _fields_list_to_dict(fields_list: list[list[bytes]]) -> dict[bytes, bytes]:
    """Convert ``[[field, value], ...]`` to ``{field: value}``.

    Pairs with fewer than 2 elements are skipped with a warning, as they
    indicate corrupt or unexpected stream data.
    """
    result: dict[bytes, bytes] = {}
    for pair in fields_list:
        if len(pair) >= 2:
            result[pair[0]] = pair[1]
        else:
            logger.warning("Skipping malformed stream entry field (expected [key, value], got %d elements)", len(pair))
    return result
