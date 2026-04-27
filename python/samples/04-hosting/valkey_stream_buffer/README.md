# Valkey Stream Buffer — Resumable Streaming

This sample demonstrates the `ValkeyStreamBuffer` component from `agent-framework-valkey`, which provides reliable, resumable streaming using Valkey Streams.

See also the Redis-based equivalent: [`../azure_functions/03_reliable_streaming/`](../azure_functions/03_reliable_streaming/)

## Prerequisites

- A running Valkey server (default: `localhost:6379`)

Start Valkey locally with Docker:

```bash
docker run -d --name valkey -p 6379:6379 valkey/valkey:latest
```

## Scenarios Demonstrated

| # | Scenario | Description |
|---|----------|-------------|
| 1 | Basic write and read | Write chunks to a Valkey Stream and read them back |
| 2 | Cursor-based resumption | Simulate a client disconnect and reconnect mid-stream |
| 3 | Error propagation | Write an error entry and observe reader behavior |

## Running

```bash
# From the python/ directory
uv run python samples/04-hosting/valkey_stream_buffer/valkey_stream_buffer.py
```
