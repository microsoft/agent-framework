# Redis Package (agent-framework-redis)

Redis-based storage for agent threads and context.

## Main Classes

- **`RedisHistoryProvider`** - Persistent chat history provider using Redis
- **`RedisContextProvider`** - Context provider with Redis-backed retrieval
- **`RedisSettings`** - TypedDict connection settings for vector stores, resolved with core `load_settings` from
  explicit URL overrides, an optional .env file, or `REDIS_URL`. URLs use `SecretString` to mask credentials.
- **`RedisCollection` / `RedisStore`** - Experimental generic vector storage and search over native HASH and JSON
  documents. `_vector_store.py` contains settings, connection/codec/schema/filter helpers, the collection, and
  the store, separate from the preexisting history/context providers. `_create_client` shares AF settings resolution;
  `RedisCollection._prepare_filter` validates support and translates portable filters to native Redis queries.
  Requires Redis Search with INDEXMISSING/INDEXEMPTY support.
  See README for the per-type native filter restrictions, HASH null rejection, and distance units.

## Vector connector tests

From `python/`, run the connector's deterministic unit tests with:

```bash
uv run --no-sync pytest packages/redis/tests/test_vector_store.py packages/redis/tests/test_vector_settings.py -m "not integration"
```

Set `REDIS_VECTOR_TEST_URL` to an explicitly disposable Search/JSON instance
and select `-m integration` to run integration tests in `tests/test_vector_store.py`.
Live tests cover Redis 8.0.3 and 8.8. A configured but insufficient server fails;
only an unset URL skips them. Tests create unique namespaces and clean only
their own indexes/keys, never `FLUSHALL`. Coverage includes both formats and
1000-record batches with two 1536-dimensional vectors without embedding API calls.

## Usage

```python
from agent_framework.redis import RedisContextProvider, RedisHistoryProvider

context_provider = RedisContextProvider(redis_url="redis://localhost:6379")
history_provider = RedisHistoryProvider(redis_url="redis://localhost:6379")
```

## Import Path

```python
from agent_framework.redis import RedisContextProvider, RedisHistoryProvider
# or directly:
from agent_framework_redis import RedisContextProvider, RedisHistoryProvider
```
