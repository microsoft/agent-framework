# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for ValkeyStreamBuffer with a mocked valkey-glide client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework_valkey import StreamChunk, ValkeyStreamBuffer

# ---------------------------------------------------------------------------
# Protocol-aligned fakes — mirror the real protocol shapes so tests catch
# interface drift without importing the actual durabletask package.
# ---------------------------------------------------------------------------


class HasText(Protocol):
    """Minimal shape of AgentResponseUpdate used by ValkeyStreamBuffer."""

    @property
    def text(self) -> str: ...


class HasThreadId(Protocol):
    """Minimal shape of AgentCallbackContext used by ValkeyStreamBuffer."""

    @property
    def thread_id(self) -> str | None: ...

    @property
    def agent_name(self) -> str: ...

    @property
    def correlation_id(self) -> str: ...


@dataclass(frozen=True)
class FakeCallbackContext:
    """Fake satisfying the AgentCallbackContext shape."""

    agent_name: str = "test-agent"
    correlation_id: str = "corr-1"
    thread_id: str | None = "thread-1"
    request_message: str | None = None


@dataclass
class FakeUpdate:
    """Fake satisfying the AgentResponseUpdate.text shape."""

    text: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> AsyncMock:
    """Create a mock GlideClient with async stream methods."""
    client = AsyncMock()
    client.xadd = AsyncMock(return_value=b"1234567890-0")
    client.expire = AsyncMock(return_value=True)
    client.xread = AsyncMock(return_value=None)
    return client


def _xread_entries(
    stream_key: str,
    entries: dict[str, list[list[bytes]]],
) -> dict[bytes, dict[bytes, list[list[bytes]]]]:
    """Build a valkey-glide-style xread return value."""
    return {
        stream_key.encode(): {eid.encode(): fields for eid, fields in entries.items()}
    }


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_rejects_none_client(self) -> None:
        with pytest.raises(ValueError, match="client must not be None"):
            ValkeyStreamBuffer(client=None)  # type: ignore[arg-type]

    def test_default_parameters(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)
        assert buf._stream_ttl_seconds == 600
        assert buf._key_prefix == "agent-stream"
        assert buf._max_empty_reads == 300

    def test_custom_parameters(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(
            client=client,
            stream_ttl=timedelta(minutes=5),
            key_prefix="custom-prefix",
            max_empty_reads=10,
            poll_interval_seconds=0.5,
        )
        assert buf._stream_ttl_seconds == 300
        assert buf._key_prefix == "custom-prefix"
        assert buf._max_empty_reads == 10
        assert buf._poll_interval_seconds == 0.5


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


class TestWriteChunk:
    @pytest.mark.asyncio
    async def test_write_chunk_calls_xadd_and_expire(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)

        await buf.write_chunk("conv-1", "hello", 0)

        client.xadd.assert_awaited_once()
        args = client.xadd.call_args
        assert args[0][0] == "agent-stream:conv-1"
        fields = args[0][1]
        field_dict = {k: v for k, v in fields}
        assert field_dict["text"] == "hello"
        assert field_dict["sequence"] == "0"
        assert "timestamp" in field_dict

        client.expire.assert_awaited_once_with("agent-stream:conv-1", 600)

    @pytest.mark.asyncio
    async def test_write_completion_includes_done_marker(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)

        await buf.write_completion("conv-1", 5)

        args = client.xadd.call_args
        fields = args[0][1]
        field_dict = {k: v for k, v in fields}
        assert field_dict["done"] == "true"
        assert field_dict["text"] == ""
        assert field_dict["sequence"] == "5"

    @pytest.mark.asyncio
    async def test_write_error_includes_error_field(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)

        await buf.write_error("conv-1", "something broke", 3)

        args = client.xadd.call_args
        fields = args[0][1]
        field_dict = {k: v for k, v in fields}
        assert field_dict["error"] == "something broke"
        assert field_dict["sequence"] == "3"

    @pytest.mark.asyncio
    async def test_write_chunk_rejects_empty_conversation_id(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)

        with pytest.raises(ValueError, match="conversation_id must not be empty"):
            await buf.write_chunk("", "text", 0)

    @pytest.mark.asyncio
    async def test_write_completion_rejects_empty_conversation_id(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)

        with pytest.raises(ValueError, match="conversation_id must not be empty"):
            await buf.write_completion("", 0)

    @pytest.mark.asyncio
    async def test_write_error_rejects_empty_conversation_id(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)

        with pytest.raises(ValueError, match="conversation_id must not be empty"):
            await buf.write_error("", "err", 0)


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


class TestReadStream:
    @pytest.mark.asyncio
    async def test_read_text_chunks(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client, poll_interval_seconds=0)

        client.xread = AsyncMock(
            side_effect=[
                _xread_entries(
                    "agent-stream:conv-1",
                    {
                        "100-0": [[b"text", b"Hello "], [b"sequence", b"0"]],
                        "100-1": [[b"text", b"world!"], [b"sequence", b"1"]],
                        "100-2": [[b"text", b""], [b"done", b"true"], [b"sequence", b"2"]],
                    },
                ),
            ]
        )

        chunks: list[StreamChunk] = []
        async for chunk in buf.read_stream("conv-1"):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0].text == "Hello "
        assert chunks[0].entry_id == "100-0"
        assert chunks[1].text == "world!"
        assert chunks[2].is_done is True
        assert chunks[2].entry_id == "100-2"

    @pytest.mark.asyncio
    async def test_read_with_cursor_resumes(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client, poll_interval_seconds=0)

        client.xread = AsyncMock(
            side_effect=[
                _xread_entries(
                    "agent-stream:conv-1",
                    {
                        "200-0": [[b"text", b"resumed chunk"], [b"sequence", b"1"]],
                        "200-1": [[b"text", b""], [b"done", b"true"], [b"sequence", b"2"]],
                    },
                ),
            ]
        )

        chunks: list[StreamChunk] = []
        async for chunk in buf.read_stream("conv-1", cursor="100-1"):
            chunks.append(chunk)

        # Verify xread was called with the cursor as start ID.
        call_args = client.xread.call_args
        keys_and_ids = call_args[0][0]
        assert keys_and_ids["agent-stream:conv-1"] == "100-1"

        assert len(chunks) == 2
        assert chunks[0].text == "resumed chunk"

    @pytest.mark.asyncio
    async def test_read_error_entry_stops_stream(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client, poll_interval_seconds=0)

        client.xread = AsyncMock(
            side_effect=[
                _xread_entries(
                    "agent-stream:conv-1",
                    {
                        "300-0": [[b"error", b"upstream failure"], [b"sequence", b"0"]],
                    },
                ),
            ]
        )

        chunks: list[StreamChunk] = []
        async for chunk in buf.read_stream("conv-1"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0].error == "upstream failure"

    @pytest.mark.asyncio
    async def test_read_timeout_on_empty_stream(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(
            client=client,
            max_empty_reads=3,
            poll_interval_seconds=0,
        )

        # xread always returns None (empty).
        client.xread = AsyncMock(return_value=None)

        chunks: list[StreamChunk] = []
        async for chunk in buf.read_stream("conv-1"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0].error is not None
        assert "timed out" in chunks[0].error

    @pytest.mark.asyncio
    async def test_read_timeout_after_data_seen(self) -> None:
        """Reader times out even after receiving earlier data (producer crash)."""
        client = _make_client()
        buf = ValkeyStreamBuffer(
            client=client,
            max_empty_reads=2,
            poll_interval_seconds=0,
        )

        # First call returns data, then producer goes silent.
        client.xread = AsyncMock(
            side_effect=[
                _xread_entries(
                    "agent-stream:conv-1",
                    {"500-0": [[b"text", b"partial"], [b"sequence", b"0"]]},
                ),
                None,
                None,  # hits max_empty_reads
            ]
        )

        chunks: list[StreamChunk] = []
        async for chunk in buf.read_stream("conv-1"):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0].text == "partial"
        assert chunks[1].error is not None
        assert "timed out" in chunks[1].error

    @pytest.mark.asyncio
    async def test_read_resets_empty_count_on_data(self) -> None:
        """Empty-read counter resets when data arrives, preventing false timeouts."""
        client = _make_client()
        buf = ValkeyStreamBuffer(
            client=client,
            max_empty_reads=3,
            poll_interval_seconds=0,
        )

        # Two empties, then data, then two more empties, then done.
        client.xread = AsyncMock(
            side_effect=[
                None,
                None,
                _xread_entries(
                    "agent-stream:conv-1",
                    {"600-0": [[b"text", b"ok"], [b"sequence", b"0"]]},
                ),
                None,
                None,
                _xread_entries(
                    "agent-stream:conv-1",
                    {"600-1": [[b"text", b""], [b"done", b"true"], [b"sequence", b"1"]]},
                ),
            ]
        )

        chunks: list[StreamChunk] = []
        async for chunk in buf.read_stream("conv-1"):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0].text == "ok"
        assert chunks[1].is_done is True

    @pytest.mark.asyncio
    async def test_read_exception_yields_error_chunk(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client, poll_interval_seconds=0)

        client.xread = AsyncMock(side_effect=ConnectionError("connection lost"))

        chunks: list[StreamChunk] = []
        async for chunk in buf.read_stream("conv-1"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0].error == "connection lost"

    @pytest.mark.asyncio
    async def test_read_polls_until_data_arrives(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client, poll_interval_seconds=0)

        # First two reads return nothing, third returns data.
        client.xread = AsyncMock(
            side_effect=[
                None,
                None,
                _xread_entries(
                    "agent-stream:conv-1",
                    {
                        "400-0": [[b"text", b"delayed"], [b"sequence", b"0"]],
                        "400-1": [[b"text", b""], [b"done", b"true"], [b"sequence", b"1"]],
                    },
                ),
            ]
        )

        chunks: list[StreamChunk] = []
        async for chunk in buf.read_stream("conv-1"):
            chunks.append(chunk)

        assert client.xread.await_count == 3
        assert len(chunks) == 2
        assert chunks[0].text == "delayed"
        assert chunks[1].is_done is True

    @pytest.mark.asyncio
    async def test_read_rejects_empty_conversation_id(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)

        with pytest.raises(ValueError, match="conversation_id must not be empty"):
            async for _ in buf.read_stream(""):
                pass  # pragma: no cover


# ---------------------------------------------------------------------------
# Callback protocol
# ---------------------------------------------------------------------------


class TestCallbackProtocol:
    @pytest.mark.asyncio
    async def test_on_streaming_response_update_writes_chunk(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)
        ctx = FakeCallbackContext(thread_id="t-1")
        update = FakeUpdate(text="chunk text")

        await buf.on_streaming_response_update(update, ctx)  # type: ignore[arg-type]

        client.xadd.assert_awaited_once()
        args = client.xadd.call_args
        assert args[0][0] == "agent-stream:t-1"
        field_dict = {k: v for k, v in args[0][1]}
        assert field_dict["text"] == "chunk text"
        assert field_dict["sequence"] == "0"

    @pytest.mark.asyncio
    async def test_on_streaming_response_update_increments_sequence(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)
        ctx = FakeCallbackContext(thread_id="t-1")

        await buf.on_streaming_response_update(FakeUpdate(text="a"), ctx)  # type: ignore[arg-type]
        await buf.on_streaming_response_update(FakeUpdate(text="b"), ctx)  # type: ignore[arg-type]

        assert client.xadd.await_count == 2
        second_call_fields = {k: v for k, v in client.xadd.call_args_list[1][0][1]}
        assert second_call_fields["sequence"] == "1"

    @pytest.mark.asyncio
    async def test_on_streaming_response_update_skips_empty_text(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)
        ctx = FakeCallbackContext(thread_id="t-1")

        await buf.on_streaming_response_update(FakeUpdate(text=""), ctx)  # type: ignore[arg-type]
        await buf.on_streaming_response_update(FakeUpdate(text=None), ctx)  # type: ignore[arg-type]

        client.xadd.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_streaming_response_update_skips_no_thread_id(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)
        ctx = FakeCallbackContext(thread_id=None)

        await buf.on_streaming_response_update(FakeUpdate(text="data"), ctx)  # type: ignore[arg-type]

        client.xadd.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_agent_response_writes_completion(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)
        ctx = FakeCallbackContext(thread_id="t-1")

        # Simulate one chunk first to set sequence.
        await buf.on_streaming_response_update(FakeUpdate(text="x"), ctx)  # type: ignore[arg-type]
        client.xadd.reset_mock()

        await buf.on_agent_response(MagicMock(), ctx)  # type: ignore[arg-type]

        client.xadd.assert_awaited_once()
        field_dict = {k: v for k, v in client.xadd.call_args[0][1]}
        assert field_dict["done"] == "true"
        assert field_dict["sequence"] == "1"

    @pytest.mark.asyncio
    async def test_on_agent_response_cleans_up_sequence(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)
        ctx = FakeCallbackContext(thread_id="t-1")

        await buf.on_streaming_response_update(FakeUpdate(text="x"), ctx)  # type: ignore[arg-type]
        assert "t-1" in buf._sequence_numbers

        await buf.on_agent_response(MagicMock(), ctx)  # type: ignore[arg-type]
        assert "t-1" not in buf._sequence_numbers

    @pytest.mark.asyncio
    async def test_on_agent_response_skips_no_thread_id(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)
        ctx = FakeCallbackContext(thread_id=None)

        await buf.on_agent_response(MagicMock(), ctx)  # type: ignore[arg-type]

        client.xadd.assert_not_awaited()


# ---------------------------------------------------------------------------
# Stream key generation & validation
# ---------------------------------------------------------------------------


class TestStreamKey:
    def test_default_prefix(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)
        assert buf._stream_key("abc") == "agent-stream:abc"

    def test_custom_prefix(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client, key_prefix="my-streams")
        assert buf._stream_key("abc") == "my-streams:abc"

    def test_rejects_empty_conversation_id(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)
        with pytest.raises(ValueError, match="conversation_id must not be empty"):
            buf._stream_key("")


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------


class TestSessionIsolation:
    @pytest.mark.asyncio
    async def test_separate_sequences_per_thread(self) -> None:
        client = _make_client()
        buf = ValkeyStreamBuffer(client=client)

        ctx_a = FakeCallbackContext(thread_id="thread-a")
        ctx_b = FakeCallbackContext(thread_id="thread-b")

        await buf.on_streaming_response_update(FakeUpdate(text="a1"), ctx_a)  # type: ignore[arg-type]
        await buf.on_streaming_response_update(FakeUpdate(text="b1"), ctx_b)  # type: ignore[arg-type]
        await buf.on_streaming_response_update(FakeUpdate(text="a2"), ctx_a)  # type: ignore[arg-type]

        # thread-a should be at sequence 2, thread-b at sequence 1.
        assert buf._sequence_numbers["thread-a"] == 2
        assert buf._sequence_numbers["thread-b"] == 1


# ---------------------------------------------------------------------------
# Malformed stream data logging
# ---------------------------------------------------------------------------


class TestMalformedFields:
    def test_malformed_pair_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        from agent_framework_valkey._stream_buffer import _fields_list_to_dict

        with caplog.at_level(logging.WARNING):
            result = _fields_list_to_dict([[b"only_key"], [b"good_key", b"good_val"]])

        assert result == {b"good_key": b"good_val"}
        assert "malformed stream entry field" in caplog.text.lower()

    def test_empty_pair_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        from agent_framework_valkey._stream_buffer import _fields_list_to_dict

        with caplog.at_level(logging.WARNING):
            result = _fields_list_to_dict([[], [b"k", b"v"]])

        assert result == {b"k": b"v"}
        assert "malformed" in caplog.text.lower()
