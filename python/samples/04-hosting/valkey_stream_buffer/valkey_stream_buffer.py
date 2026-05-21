# Copyright (c) Microsoft. All rights reserved.

"""ValkeyStreamBuffer: Resumable streaming with Valkey Streams

This sample demonstrates the ValkeyStreamBuffer component from the
agent-framework-valkey package.  It shows three scenarios:

1) Basic write and read — write chunks to a Valkey Stream and read them back.
2) Cursor-based resumption — simulate a client disconnect and reconnect
   mid-stream, resuming from the last-seen entry ID.
3) Error propagation — write an error entry and observe how the reader
   surfaces it.

The ValkeyStreamBuffer uses Valkey Streams (XADD/XREAD) under the hood.
Each conversation gets its own stream key with a configurable TTL that
auto-refreshes on every write.

Requirements:
  - A running Valkey server (default: localhost:6379)
  - agent-framework-valkey installed (included in the workspace dev environment)

  Start Valkey locally with Docker:
    docker run -d --name valkey -p 6379:6379 valkey/valkey:latest

Run (from the python/ directory):
    uv run python samples/04-hosting/valkey_stream_buffer/valkey_stream_buffer.py
"""

import asyncio

from agent_framework_valkey import ValkeyStreamBuffer
from glide import GlideClient, GlideClientConfiguration, NodeAddress

# Connection settings — adjust for your environment.
VALKEY_HOST = "localhost"
VALKEY_PORT = 6379


async def create_client() -> GlideClient:
    """Create and return a connected GlideClient."""
    config = GlideClientConfiguration([NodeAddress(VALKEY_HOST, VALKEY_PORT)])
    return await GlideClient.create(config)


# ---------------------------------------------------------------------------
# Scenario 1: Basic write and read
# ---------------------------------------------------------------------------


async def basic_write_and_read(client: GlideClient) -> None:
    """Write chunks to a Valkey Stream and read them back in order."""
    print("=== Scenario 1: Basic Write and Read ===\n")

    buf = ValkeyStreamBuffer(client=client, key_prefix="sample-stream")
    conv_id = "demo-basic"

    # 1. Write several chunks and a completion marker.
    await buf.write_chunk(conv_id, "Hello, ", 0)
    await buf.write_chunk(conv_id, "world! ", 1)
    await buf.write_chunk(conv_id, "This is streamed from Valkey.", 2)
    await buf.write_completion(conv_id, 3)
    print("Wrote 3 text chunks + completion sentinel.\n")

    # 2. Read them back.
    print("Reading stream:")
    async for chunk in buf.read_stream(conv_id):
        if chunk.is_done:
            print("\n[Stream complete]")
            break
        print(f"  chunk({chunk.entry_id}): {chunk.text!r}")

    # Clean up the stream key.
    await client.delete([f"sample-stream:{conv_id}"])


# ---------------------------------------------------------------------------
# Scenario 2: Cursor-based resumption
# ---------------------------------------------------------------------------


async def cursor_resumption(client: GlideClient) -> None:
    """Simulate a client disconnect and resume from the last-seen cursor."""
    print("\n=== Scenario 2: Cursor-Based Resumption ===\n")

    buf = ValkeyStreamBuffer(client=client, key_prefix="sample-stream")
    conv_id = "demo-resume"

    # 1. Write a multi-chunk response.
    chunks_text = [
        "Planning your trip: ",
        "Day 1 — Arrive in Tokyo. ",
        "Day 2 — Visit Shibuya and Harajuku. ",
        "Day 3 — Explore Asakusa and Akihabara. ",
        "Have a great trip!",
    ]
    for i, text in enumerate(chunks_text):
        await buf.write_chunk(conv_id, text, i)
    await buf.write_completion(conv_id, len(chunks_text))
    print(f"Wrote {len(chunks_text)} chunks + completion.\n")

    # 2. Read only the first 2 chunks, simulating a client disconnect.
    print("First read (simulating disconnect after 2 chunks):")
    last_cursor: str | None = None
    count = 0
    async for chunk in buf.read_stream(conv_id):
        if chunk.is_done:
            break
        print(f"  chunk({chunk.entry_id}): {chunk.text!r}")
        last_cursor = chunk.entry_id
        count += 1
        if count >= 2:
            print("  [Client disconnected]\n")
            break

    # 3. Resume from the last-seen cursor.
    print(f"Resuming from cursor: {last_cursor}")
    async for chunk in buf.read_stream(conv_id, cursor=last_cursor):
        if chunk.is_done:
            print("\n[Stream complete]")
            break
        print(f"  chunk({chunk.entry_id}): {chunk.text!r}")

    # Clean up.
    await client.delete([f"sample-stream:{conv_id}"])


# ---------------------------------------------------------------------------
# Scenario 3: Error propagation
# ---------------------------------------------------------------------------


async def error_propagation(client: GlideClient) -> None:
    """Write an error entry and observe how the reader surfaces it."""
    print("\n=== Scenario 3: Error Propagation ===\n")

    buf = ValkeyStreamBuffer(client=client, key_prefix="sample-stream")
    conv_id = "demo-error"

    # 1. Write a partial response followed by an error.
    await buf.write_chunk(conv_id, "Starting response... ", 0)
    await buf.write_error(conv_id, "upstream model timeout", 1)
    print("Wrote 1 chunk + error entry.\n")

    # 2. Read — the reader yields the text chunk, then the error, and stops.
    print("Reading stream:")
    async for chunk in buf.read_stream(conv_id):
        if chunk.error:
            print(f"  [Error] {chunk.error}")
            break
        print(f"  chunk({chunk.entry_id}): {chunk.text!r}")

    # Clean up.
    await client.delete([f"sample-stream:{conv_id}"])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run all three scenarios."""
    client = await create_client()
    try:
        await basic_write_and_read(client)
        await cursor_resumption(client)
        await error_propagation(client)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

=== Scenario 1: Basic Write and Read ===

Wrote 3 text chunks + completion sentinel.

Reading stream:
  chunk(1745862000000-0): 'Hello, '
  chunk(1745862000001-0): 'world! '
  chunk(1745862000002-0): 'This is streamed from Valkey.'

[Stream complete]

=== Scenario 2: Cursor-Based Resumption ===

Wrote 5 chunks + completion.

First read (simulating disconnect after 2 chunks):
  chunk(1745862000010-0): 'Planning your trip: '
  chunk(1745862000011-0): 'Day 1 — Arrive in Tokyo. '
  [Client disconnected]

Resuming from cursor: 1745862000011-0
  chunk(1745862000012-0): 'Day 2 — Visit Shibuya and Harajuku. '
  chunk(1745862000013-0): 'Day 3 — Explore Asakusa and Akihabara. '
  chunk(1745862000014-0): 'Have a great trip!'

[Stream complete]

=== Scenario 3: Error Propagation ===

Wrote 1 chunk + error entry.

Reading stream:
  chunk(1745862000020-0): 'Starting response... '
  [Error] upstream model timeout
"""
