# Microsoft Agent Framework Redis

Redis-backed conversation history, memory retrieval, and vector storage for
[Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/).

## Choose the right component

| Your goal | Component |
| --- | --- |
| Persist ordered conversation messages across runs and application restarts | `RedisHistoryProvider` |
| Retrieve relevant memories and add them to an agent's context | `RedisContextProvider` |
| Store and search your own documents or embeddings | `RedisCollection` (experimental) |
| Manage vector collections with a shared connection and namespace | `RedisStore` (experimental) |
| Resolve vector-store connection configuration from arguments, `.env`, or environment variables | `RedisSettings` |

These components can be used together, but do not automatically share stored
records. Import them from `agent_framework.redis` or `agent_framework_redis`.

## Install

Requires Python 3.10 or later:

```bash
pip install agent-framework-redis --pre
```

## Run Redis

Choose a managed service or run Redis locally:

- **Azure Managed Redis**: Run Redis as a managed Azure service. Follow the
  [Azure Managed Redis quickstart](https://learn.microsoft.com/en-us/azure/redis/quickstart-create-managed-redis)
  to create an instance.
- **Redis Cloud**: Use [Redis Cloud](https://redis.io/cloud/) for a fully managed
  Redis database.
- **Local Docker**: Start Redis on your machine with:

  ```bash
  docker run --rm --name agent-framework-redis -p 127.0.0.1:6379:6379 redis:8.0.3
  ```

For managed services, choose a configuration with the Search/JSON capabilities
required by your component below, and use the service's connection endpoint
and authentication settings.

## Requirements and configuration

Conversation history uses Redis Lists and does not require Search or RedisJSON.
Context retrieval requires Redis Search. Vector collections require Redis
8.0.3 or later with Search, including `INDEXMISSING` and `INDEXEMPTY` support;
JSON collections additionally require RedisJSON.
Redis Search indexes require logical database 0, so vector-store URLs and clients
must select database 0 (the default).

Choose `storage_type="hash"` for non-null records with binary vector storage,
or `"json"` for nullable fields/vectors and native JSON data. HASH rejects
`None`, including `vector=None`; JSON preserves explicit null. Both support
multiple vector fields and FLAT/HNSW indexes.

`RedisCollection` and `RedisStore` use `RedisSettings` with the Agent Framework
settings loader. Connection precedence is an explicit `redis_url`, then
`REDIS_URL` in a supplied `env_file_path`, then the process environment, with
`redis://localhost:6379` as the default. Settings mask credential-bearing URLs
with `SecretString`; use `rediss://` when your server requires TLS.

You may supply a standalone `redis.asyncio.Redis` client using
`decode_responses=False` and RESP2. Both URL-created and supplied clients must use
strict UTF-8 encoding (`encoding="utf-8"`, `encoding_errors="strict"`, the defaults)
so Unicode keys and string fields round-trip without lossy conversions.
Incompatible encoding or database settings are rejected before connecting.
Supplied clients take precedence over URL settings and remain caller-owned.
Closing a store closes its owned connection, not its stored data. Redis Cluster
clients are not supported.

Vector collections support dense search and a subset of portable filters,
not hybrid/full-text search or literal substring/prefix/suffix filters.
JSON null checks are supported on numeric and boolean fields, not strings or
arrays. Indexed strings cannot contain surrounding whitespace, NUL, or U+001F,
and must fit Redis's 4096-byte TAG limit; these restrictions do not apply to
unindexed payloads. Unsupported operations raise an error.

## Store and search documents

This example uses precomputed vectors, so no embedding service is needed.
It connects using `REDIS_URL` or the localhost default:

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import VectorStoreField, vectorstoremodel
from agent_framework.redis import RedisStore


@vectorstoremodel
@dataclass
class Document:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data")]
    vector: Annotated[
        list[float] | None,
        VectorStoreField("vector", dimensions=2, index_kind="flat"),
    ] = None


async def main() -> None:
    async with RedisStore(storage_type="json", namespace="my-app") as store:
        collection = store.get_collection(Document, collection_name="documents")
        await collection.ensure_collection_exists()
        await collection.upsert(
            [Document("one", "A guide to Redis", [1.0, 0.0])],
            generate_vectors=False,
        )
        results = await collection.search(vector=[1.0, 0.0], top=3)
        async for result in results:
            print(result["record"].text, result["score"])


asyncio.run(main())
```

CRUD operations accept batches. Provide an embedding generator to generate
vectors automatically, or use `generate_vectors=False` to keep supplied vectors.
Retrieval excludes vectors by default; use `include_vectors=True` to return them.
Search scores are native distances (cosine distance by default), where lower is
better; a nonnegative `score_threshold` sets a maximum distance before paging.

## Documentation and examples

- [Agent Framework documentation](https://learn.microsoft.com/agent-framework/)
- [Redis documentation](https://redis.io/docs/latest/)
- [Redis vector search](https://redis.io/docs/latest/develop/ai/search-and-query/vectors/)
- [Redis conversation-history example](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/conversations/redis_history_provider.py)
- [Redis context-provider examples](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/context_providers/redis)
- [HASH and JSON vector-store example](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/vector_stores/redis_store.py)
