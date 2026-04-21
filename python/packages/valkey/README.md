# Get Started with Microsoft Agent Framework Valkey

Please install this package via pip:

```bash
pip install agent-framework-valkey --pre
```

## Server Requirements

The `ValkeyChatMessageStore` works with any Valkey (or Redis OSS) server — it only uses basic key-value operations.

The `ValkeyContextProvider` requires the **valkey-search** module (>= 1.2) for its `FT.CREATE` / `FT.SEARCH` commands. This module ships with **valkey-bundle >= 9.1.0** and is also available in managed cloud offerings (AWS ElastiCache for Valkey, GCP Memorystore for Valkey).

For local development and testing, use `valkey-bundle 9.1.0-rc1`:

```bash
docker run -d --name valkey -p 6379:6379 valkey/valkey-bundle:9.1.0-rc1
```

## Components

### Valkey Context Provider

The `ValkeyContextProvider` enables persistent context and memory capabilities for your agents,
allowing them to remember user preferences and conversation context across sessions and threads.
It uses Valkey's native vector search capabilities (`FT.CREATE` / `FT.SEARCH`) for semantic
retrieval of past conversation context.

#### Basic Usage

```python
from agent_framework_valkey import ValkeyContextProvider

# Text-only search (no embeddings required)
context_provider = ValkeyContextProvider(
    host="localhost",
    port=6379,
    user_id="user-123",
)

# With vector search (requires an embedding function)
async def my_embed_fn(text: str) -> list[float]:
    # Your embedding logic here
    ...

context_provider = ValkeyContextProvider(
    host="localhost",
    port=6379,
    user_id="user-123",
    embed_fn=my_embed_fn,
    vector_field_name="embedding",
    vector_dims=1536,
)
```

### Valkey Chat Message Store

The `ValkeyChatMessageStore` provides persistent conversation storage using Valkey Lists,
enabling chat history to survive application restarts and support distributed applications.

#### Key Features

- **Persistent Storage**: Messages survive application restarts
- **Session Isolation**: Each conversation session has its own Valkey key
- **Message Limits**: Configurable automatic trimming of old messages
- **Lightweight**: Uses only basic Valkey key-value operations (no search module required)
- **valkey-glide**: Built on the official Valkey Python client

#### Basic Usage

```python
from agent_framework_valkey import ValkeyChatMessageStore

store = ValkeyChatMessageStore(
    host="localhost",
    port=6379,
    max_messages=100,
)
```

## Installing and Running Valkey

### Option A: Local Valkey with Docker

For basic chat history storage (no search needed):

```bash
docker run --name valkey -p 6379:6379 -d valkey/valkey:8.1
```

For full functionality including the `ValkeyContextProvider` (requires valkey-search):

```bash
docker run --name valkey -p 6379:6379 -d valkey/valkey-bundle:9.1.0-rc1
```

### Option B: AWS ElastiCache for Valkey

Create a serverless or node-based [ElastiCache for Valkey](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.html) cluster.

### Option C: Google Cloud Memorystore for Valkey

Create a [Memorystore for Valkey](https://cloud.google.com/memorystore/docs/valkey) instance.

## Why Valkey?

Valkey is an open-source, Linux Foundation project that is protocol-compatible with Redis
for core operations. It provides:

- **Open governance**: Community-driven development under the Linux Foundation
- **Performance**: Single-digit millisecond latency with high recall for vector search
- **Scaling**: Linear scaling with cluster mode support
- **Cloud support**: Managed services from AWS, GCP, and other providers
- **Migration path**: Drop-in replacement for Redis deployments
