# Redis Context Provider Examples

The Redis context provider enables persistent, searchable memory for your agents using Redis (RediSearch). It supports full‑text search and optional hybrid search with vector embeddings, letting agents remember and retrieve user context across sessions and threads.

This folder contains an example demonstrating how to use the Redis context provider with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`redis_basics.py`](redis_basics.py) | Shows standalone provider usage and agent integration. Demonstrates writing messages to Redis, retrieving context via full‑text or hybrid vector search, and persisting preferences across threads. Also includes a simple tool example whose outputs are remembered. |
| [`redis_threads.py`](redis_threads.py) | Demonstrates thread scoping. Includes: (1) global thread scope with a fixed `thread_id` shared across operations; (2) per‑operation thread scope where `scope_to_per_operation_thread_id=True` binds memory to a single thread for the provider’s lifetime; and (3) multiple agents with isolated memory via different `agent_id` values. |

## Prerequisites

### Required resources

1. A running Redis with RediSearch (Redis Stack or a managed service)
2. Python environment with Agent Framework Redis extra installed
3. Optional: OpenAI API key if using vector embeddings

### Install the package

```bash
pip install "agent-framework[redis]"
```

## Running Redis

Pick one option:

### Option A: Docker (local Redis Stack)

```bash
docker run --name redis -p 6379:6379 -d redis:8.0.3
```

### Option B: Redis Cloud

Create a free database and get the connection URL at `https://redis.io/cloud/`.

### Option C: Azure Managed Redis

See quickstart: `https://learn.microsoft.com/azure/redis/quickstart-create-managed-redis`

## Configuration

### Environment variables

- `OPENAI_API_KEY` (optional): Required only if you set `vectorizer_choice="openai"` to enable hybrid search.

### Provider configuration highlights

The provider supports both full‑text only and hybrid vector search:

- Set `vectorizer_choice` to `"openai"` or `"hf"` to enable embeddings and hybrid search.
- When using a vectorizer, also set `vector_field_name` (e.g., `"vector"`).
- Partition fields for scoping memory: `application_id`, `agent_id`, `user_id`, `thread_id`.
- Thread scoping: `scope_to_per_operation_thread_id=True` isolates memory per operation thread.
- Index management: `index_name`, `overwrite_redis_index`, `drop_redis_index`.

## What the example does

`redis_basics.py` walks through three scenarios:

1. Standalone provider usage: adds messages and retrieves context via `model_invoking`.
2. Agent integration: teaches the agent a preference and verifies it is remembered across turns.
3. Agent + tool: calls a sample tool (flight search) and then asks the agent to recall details remembered from the tool output.

It uses OpenAI for both chat (via `OpenAIChatClient`) and, in some steps, optional embeddings for hybrid search.

## How to run

1) Start Redis (see options above). For local default, ensure it's reachable at `redis://localhost:6379`.

2) Set your OpenAI key if using embeddings and for the chat client used in the sample:

```bash
export OPENAI_API_KEY="<your key>"
```

3) Run the example:

```bash
python redis_basics.py
```

You should see the agent responses and, when using embeddings, context retrieved from Redis. The example includes commented debug helpers you can print, such as index info or all stored docs.

## Key concepts

### Memory scoping

- Global scope: set `application_id`, `agent_id`, `user_id`, or `thread_id` on the provider to filter memory.
- Per‑operation thread scope: set `scope_to_per_operation_thread_id=True` to isolate memory to the current thread created by the framework.

### Hybrid vector search (optional)

- Enable by setting `vectorizer_choice` to `"openai"` (requires `OPENAI_API_KEY`) or `"hf"` (offline model).
- Provide `vector_field_name` (e.g., `"vector"`); other vector settings have sensible defaults.

### Index lifecycle controls

- `overwrite_redis_index` and `drop_redis_index` help recreate indexes during iteration.

## Troubleshooting

- Ensure at least one of `application_id`, `agent_id`, `user_id`, or `thread_id` is set; the provider requires a scope.
- If using embeddings, verify `OPENAI_API_KEY` is set and reachable.
- Make sure Redis exposes RediSearch (Redis Stack image or managed service with search enabled).


