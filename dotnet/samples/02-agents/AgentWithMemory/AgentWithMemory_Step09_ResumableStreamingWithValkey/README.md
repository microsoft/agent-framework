# Resumable Streaming with Valkey

This sample demonstrates using `ValkeyStreamBuffer` for resumable agent streaming backed by Valkey Streams.

## What it shows

1. **Stream + persist** — Streams an agent response while writing each chunk to a Valkey Stream via `XADD`
2. **Simulated disconnect** — Breaks the stream after 4 chunks, simulating a client disconnection
3. **Resume from last-seen** — Replays only the missed chunks using `ReadAsync(afterEntryId)`, demonstrating zero data loss
4. **Full replay** — Replays the entire stream from the beginning

## How it works

Each `AgentResponseUpdate` is serialized to JSON and appended to a Valkey Stream keyed by response ID. The `XADD` return value (the stream entry ID) serves as a continuation token. On reconnection, `ReadAsync` uses `XRANGE` starting after the last-seen entry ID to fetch only the missed chunks.

## Prerequisites

- Any Valkey or Redis OSS server (no modules required):

```bash
docker run -d --name valkey -p 6379:6379 valkey/valkey:latest
```

No LLM or cloud credentials needed — the sample simulates agent response chunks directly.

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `VALKEY_CONNECTION` | Valkey connection string | `localhost:6379` |

## Running

```bash
dotnet run
```

## Expected Output

```
=== Part 1: Streaming with simulated disconnect ===

Valkey Streams provide a powerful append-only log data structure.
  ⚡ CLIENT DISCONNECTED after 4 chunks!
  📦 11 total chunks persisted in Valkey Stream.
  🔖 Last seen entry ID: 1234567890-3

=== Part 2: Resuming from last-seen entry ===

  🔄 Replaying missed chunks from Valkey...

They support consumer groups for distributed processing, and each entry gets a unique auto-generated ID that serves as a natural continuation token. This makes them ideal for resumable streaming scenarios in AI agent frameworks.
  ✅ Resumed 7 missed chunks.

=== Part 3: Full replay from beginning ===

Valkey Streams provide a powerful append-only log data structure. They support consumer groups ...
  📊 Full replay: 11 total chunks.
  🗑️  Stream deleted.

Done!
```

The key takeaway: the server continued writing all 11 chunks to the stream even after the client disconnected at chunk 4. On resume, only the 7 missed chunks were returned — zero data loss.
