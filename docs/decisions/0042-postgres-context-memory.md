---
status: accepted
contact: jaredmeade
date: 2026-09-14
deciders: jaredmeade
---

# PostgreSQL ContextMemory architecture

## Context and Problem Statement

[0041-postgres-memory-provider.md](0041-postgres-memory-provider.md) proposed a PostgreSQL-backed
Agent Framework provider, but its first implementation placed persistence, retrieval, extraction,
summarization, and profile maintenance inside the provider itself. This coupled the reusable memory
engine to one Agent Framework lifecycle adapter. The PostgreSQL integration should separate those
responsibilities so the memory engine is useful independently and the .NET and Python adapters share
the same behavioral contract.

## Decision Drivers

- Preserve the distinction between an Agent Framework context adapter and a reusable memory engine.
- Support turns, facts, procedural memories, episodic memories, thread summaries, and cross-thread
  user summaries.
- Support confidence filtering, hybrid retrieval, memory reconciliation, and background processing,
  not only fact extraction.
- Use provider-agnostic chat and embedding abstractions in both language implementations.
- Keep PostgreSQL as the only durable dependency; pgvector supplies semantic retrieval and native
  PostgreSQL full-text search supplies lexical retrieval.

## Decision Outcome

The package contains two public layers:

1. `PostgresMemoryClient` is the reusable PostgreSQL ContextMemory engine. It owns storage,
   retrieval, transformation, cadence-aware background processing, explicit processing, and
   background-work flushing.
2. `PostgresMemoryContextProvider` is a thin Agent Framework lifecycle adapter. Before a run it
   searches the client and retrieves the user summary; after a run it writes conversation turns.
   It does not implement extraction or summarization itself.

The .NET implementation is distributed in `Microsoft.Agents.AI.Postgres`. The Python implementation
is part of `agent-framework-postgres` and uses Psycopg 3.

### Memory model

The configured base table name produces four tables:

- `{base}_turns`: append-only raw conversation turns.
- `{base}_memories`: active and superseded fact, procedural, and episodic memories, with confidence,
  salience, tags, embeddings, full-text indexes, expiry, and reconciliation metadata.
- `{base}_summaries`: versioned thread summaries and cross-thread user summaries.
- `{base}_processing`: per-scope processing checkpoints and extraction cadence state.

### Lifecycle

- The provider's pre-run hook performs hybrid vector/full-text search over typed derived memories
  and independently retrieves the user summary. Both are injected as user-role, explicitly
  untrusted reference information.
- The provider's post-run hook writes supported input and output messages as turns. A turn write may
  schedule processing, but the provider does not wait for extraction.
- Both providers support configurable search/request/response message filters and independent
  storage and search scopes.
- `PostgresMemoryClient` extracts typed memories, incrementally updates thread/user summaries,
  applies episodic TTL, folds exact/vector-similar duplicates, and reconciles semantic
  contradictions while retaining supersession history.
- `FlushAsync`/`flush` drains in-flight processing before shutdown. `ProcessNowAsync`/`process_now`
  is available through the provider and client layers, giving tests, operators, and applications
  with automatic cadence disabled an explicit processing hook.

### Scope

`PostgresMemoryScope.UserId` is required for durable operations and follows a user across sessions.
`ThreadId` is required when storing or processing turns. The provider defaults its search scope to a
copy without `ThreadId`, enabling cross-thread recall for the same user. Optional application and
agent identifiers provide additional isolation and are matched exactly; null identifiers do not
act as wildcards across other applications or agents.

### Retrieval

Search defaults to fact, procedural, and episodic memories. It filters by minimum confidence and
combines pgvector cosine ranking with native `tsvector`/`ts_rank` using Reciprocal Rank Fusion.
Superseded and expired records are excluded. The initial implementation uses native PostgreSQL
full-text ranking; optional BM25 extensions remain a future enhancement.

## Consequences

- The memory engine is independently usable and testable instead of being coupled to Agent
  Framework lifecycle types.
- The provider API is named `PostgresMemoryContextProvider` to make its lifecycle role explicit.
- Model clients and Npgsql/Psycopg data sources are supplied and owned by the caller. A convenience
  provider constructor owns only the `PostgresMemoryClient` it creates, not those dependencies.
- Summary versions are serialized with PostgreSQL advisory transaction locks, and processing
  checkpoints are monotonic so concurrent workers cannot move completed work backward. Stale or
  equal summary coverage is rejected while holding the same lock.
- Extraction and reconciliation require a complete, schema-valid JSON array response. One malformed
  item invalidates the full response, and processing checkpoints do not advance.
- Direct and scheduled thread processing share per-scope locks, and user-summary turn cutoffs are
  captured before model execution so concurrent turn writes are not checkpointed prematurely.
- In-process background processing is appropriate for development and low-throughput deployments.
  A durable PostgreSQL processor (for example, an outbox plus worker) is deferred.
- PostgreSQL `vector` HNSW indexing supports up to 2,000 dimensions; callers using larger embedding
  outputs must request reduced dimensions or a future half-precision/index strategy.
