# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for ValkeyStreamBuffer against a real Valkey server.

These tests require a running Valkey instance (default: localhost:6379).
Run with:  uv run pytest packages/valkey/tests/ -v -m integration

They are skipped by default in the unit test suite.
"""

from __future__ import annotations

import uuid

import pytest

from agent_framework_valkey import StreamChunk, ValkeyStreamBuffer

# Guard the glide import so the module can be collected on Windows (where
# valkey-glide is not installed) without failing at import time.
glide = pytest.importorskip("glide", reason="valkey-glide is not installed (not available on Windows)")


@pytest.fixture
async def valkey_client():
    """Create a GlideClient connected to localhost:6379."""
    config = glide.GlideClientConfiguration([glide.NodeAddress("localhost", 6379)])
    client = await glide.GlideClient.create(config)
    yield client
    await client.close()


@pytest.fixture
def conversation_id() -> str:
    """Generate a unique conversation ID to avoid test interference."""
    return f"test-{uuid.uuid4().hex[:12]}"


@pytest.mark.integration
class TestStreamBufferIntegration:
    """Round-trip integration tests validating the valkey-glide wire format."""

    @pytest.mark.asyncio
    async def test_write_and_read_round_trip(
        self,
        valkey_client: glide.GlideClient,
        conversation_id: str,
    ) -> None:
        """Write chunks and read them back, verifying the full round trip."""
        buf = ValkeyStreamBuffer(client=valkey_client, key_prefix="test-stream")

        await buf.write_chunk(conversation_id, "Hello, ", 0)
        await buf.write_chunk(conversation_id, "world!", 1)
        await buf.write_completion(conversation_id, 2)

        chunks: list[StreamChunk] = []
        async for chunk in buf.read_stream(conversation_id):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0].text == "Hello, "
        assert chunks[1].text == "world!"
        assert chunks[2].is_done is True

        # Clean up
        await valkey_client.delete([f"test-stream:{conversation_id}"])

    @pytest.mark.asyncio
    async def test_cursor_resumption(
        self,
        valkey_client: glide.GlideClient,
        conversation_id: str,
    ) -> None:
        """Resume reading from a cursor mid-stream."""
        buf = ValkeyStreamBuffer(client=valkey_client, key_prefix="test-stream")

        await buf.write_chunk(conversation_id, "first", 0)
        await buf.write_chunk(conversation_id, "second", 1)
        await buf.write_completion(conversation_id, 2)

        # Read first chunk and capture cursor.
        first_chunk: StreamChunk | None = None
        async for chunk in buf.read_stream(conversation_id):
            first_chunk = chunk
            break

        assert first_chunk is not None
        assert first_chunk.text == "first"

        # Resume from cursor — should get "second" and done.
        remaining: list[StreamChunk] = []
        async for chunk in buf.read_stream(conversation_id, cursor=first_chunk.entry_id):
            remaining.append(chunk)

        assert len(remaining) == 2
        assert remaining[0].text == "second"
        assert remaining[1].is_done is True

        # Clean up
        await valkey_client.delete([f"test-stream:{conversation_id}"])
