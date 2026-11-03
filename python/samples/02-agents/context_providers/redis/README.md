# Redis Context Provider Examples

The Redis context provider enables persistent, searchable memory for your agents using Redis (RediSearch). It supports full‑text search and optional hybrid search with vector embeddings, letting agents remember and retrieve user context across sessions and threads.

This folder contains an example demonstrating how to use the Redis context provider with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`azure_redis_conversation.py`](azure_redis_conversation.py) | Demonstrates conversation persistence with RedisHistoryProvider and Azure Redis with Azure AD (Entra ID) authentication using credential provider. |
| [`redis_basics.py`](redis_basics.py) | Shows standalone provider usage and agent integration. Demonstrates writing messages to Redis, retrieving context via full‑text or hybrid vector search, and persisting preferences across threads. Also includes a simple tool example whose outputs are remembered. |
| [`redis_conversation.py`](redis_conversation.py) | Shows context retrieval across conversation turns with RedisContextProvider using a Redis connection URL and OpenAI embeddings. For complete conversation history persistence, use RedisHistoryProvider. |
| [`redis_sessions.py`](redis_sessions.py) | Demonstrates memory scoping strategies. Includes: (1) global memory scope with `application_id`, `agent_id`, and `user_id` shared across operations; (2) hybrid vector search using a custom OpenAI vectorizer for richer context retrieval; and (3) multiple agents with isolated memory via different `agent_id` values. |


## Prerequisites

### Required resources

1. A running Redis with RediSearch (Redis Stack or a managed service)
2. Python environment with Agent Framework Redis extra installed
3. Microsoft Foundry project endpoint and Azure OpenAI Responses deployment
4. OpenAI API key for the OpenAI-vectorizer examples (`redis_basics.py`, `redis_conversation.py`, and the hybrid-search and multiple-agents scenarios in `redis_sessions.py`)

### Install the package

```bash
pip install "agent-framework-redis" "agent-framework-foundry"
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

- `FOUNDRY_PROJECT_ENDPOINT` (required): Microsoft Foundry project endpoint for `FoundryChatClient`
- `FOUNDRY_MODEL` (required): Foundry model deployment name
- `OPENAI_API_KEY`: Required by the examples that instantiate `OpenAITextVectorizer` for hybrid search.

### Provider configuration highlights

The provider supports both full‑text only and hybrid vector search:

- Pass a RedisVL vectorizer instance, such as `OpenAITextVectorizer`, through `redis_vectorizer` and set `vector_field_name` (e.g., `"vector"`) to enable hybrid search.
- Omit `redis_vectorizer` and `vector_field_name` for full-text-only retrieval, as in the global-scope scenario in `redis_sessions.py`.
- Partition fields for scoping memory: `application_id`, `agent_id`, `user_id`.
- Index configuration: `index_name`, `prefix`, and `overwrite_index`.

## What the example does

`redis_basics.py` walks through three scenarios:

1. Standalone provider usage: stores messages via `after_run` and retrieves context via `before_run`.
2. Agent integration: teaches the agent a preference and verifies it is remembered across turns.
3. Agent + tool: calls a sample tool (flight search) and then asks the agent to recall details remembered from the tool output.

It uses `FoundryChatClient` for chat and, in some steps, optional OpenAI embeddings for hybrid search.

## How to run

1) Start Redis (see options above). For local default, ensure it's reachable at `redis://localhost:6379`.

2) Set Azure Foundry/OpenAI responses environment variables:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
export FOUNDRY_MODEL="<deployment-name>"
```

3) Set your OpenAI key for `redis_basics.py` and the other OpenAI-vectorizer examples:

```bash
export OPENAI_API_KEY="<your key>"
```

4) Run the example:

```bash
python redis_basics.py
```

You should see the agent responses and, when using embeddings, context retrieved from Redis. The example includes commented debug helpers you can print, such as index info or all stored docs.

## Key concepts

### Memory scoping

- Global scope: set `application_id`, `agent_id`, or `user_id` on the provider to filter memory.
- Agent isolation: use different `agent_id` values to keep memories separated for different agent personas.

### Hybrid vector search (optional)

- Pass a vectorizer as `redis_vectorizer` and provide `vector_field_name` (e.g., `"vector"`). The examples use `OpenAITextVectorizer`, which requires `OPENAI_API_KEY`.
- `vector_algorithm` and `vector_distance_metric` configure the vector index; the examples use `"hnsw"` and `"cosine"`.

### Index lifecycle controls

- Set `overwrite_index=True` to recreate an existing index during initialization. The examples clean up their indexes with `await provider.redis_index.delete()`.

## Troubleshooting

- Ensure at least one of `application_id`, `agent_id`, or `user_id` is set; the provider requires a scope.
- Verify `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL` are set for the chat client.
- If using embeddings, verify `OPENAI_API_KEY` is set and reachable.
- Make sure Redis exposes RediSearch (Redis Stack image or managed service with search enabled).
