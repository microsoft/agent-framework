# agent-framework-valkey

Valkey integration for the [Microsoft Agent Framework](https://aka.ms/agent-framework).

## Components

- **ValkeyStreamBuffer** — Resumable streaming buffer backed by Valkey Streams.
  Persists agent response chunks via `XADD` and supports cursor-based client
  reconnection via `XREAD`. Implements `AgentResponseCallbackProtocol` for
  direct use with durable agent workers.

## Installation

```bash
pip install agent-framework-valkey
```

For durable agent callback support:

```bash
pip install agent-framework-valkey[durabletask]
```

## Quick Start

```python
import asyncio

from glide import GlideClient, GlideClientConfiguration, NodeAddress
from agent_framework_valkey import ValkeyStreamBuffer


async def main():
    config = GlideClientConfiguration([NodeAddress("localhost", 6379)])
    client = await GlideClient.create(config)
    buffer = ValkeyStreamBuffer(client=client)

    # Write side
    await buffer.write_chunk("conv-1", "Hello, ", 0)
    await buffer.write_chunk("conv-1", "world!", 1)
    await buffer.write_completion("conv-1", 2)

    # Read side (supports cursor-based resumption)
    async for chunk in buffer.read_stream("conv-1"):
        if chunk.is_done:
            break
        print(chunk.text, end="")


asyncio.run(main())
```

## Requirements

- Python 3.10+
- Valkey server (any version supporting Streams)
- `valkey-glide` client library
