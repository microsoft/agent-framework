---
status: superseded by [ADR-0042](0042-postgres-context-memory.md)
contact: jaredmeade
date: 2026-09-14
deciders: jaredmeade
---

# PostgreSQL-backed memory context provider

> **Superseded by [ADR-0042](0042-postgres-context-memory.md).** The final design retains the
> PostgreSQL package and native .NET implementation but replaces the provider-owned, message-level
> pipeline with a reusable `PostgresMemoryClient` and thin `PostgresMemoryContextProvider`.

## Context and Problem Statement

Many customers run PostgreSQL as their primary database and want durable, cross-session agent
memory backed by it, using pgvector for semantic recall and a full-text ranking mechanism for
lexical recall, without introducing another datastore. How should a PostgreSQL memory provider be
designed and shipped, and should it be available for both .NET and Python?

## Decision Drivers

- Integrate through Agent Framework's existing context-provider extension points.
- Avoid requiring a separate always-on service; the provider should work with a plain PostgreSQL database plus optional extensions.
- Support both .NET and Python with parity, since both are first-class Agent Framework languages.
- Ship an initial, reviewable increment rather than the full memory pipeline (raw turns → facts → summaries → profile) in one PR.

## Considered Options

- Native per-language packages (`Microsoft.Agents.AI.Postgres` for .NET, with a matching Python package), each talking to PostgreSQL directly.
- A single shared backend service (one implementation, both SDKs as thin HTTP/gRPC clients) — avoids duplicating retrieval/extraction logic across languages at the cost of an extra deployable component.
- Reuse the existing `agent-framework-postgres` (Python) pgvector connector directly as the context provider, without a dedicated memory-shaped package.

## Decision Outcome

Chosen option: "Native per-language packages", because it keeps the integration in-process without
an additional service to deploy. Behavioral parity between the two languages is enforced through
documentation and shared expectations in this ADR rather than shared code.

### v1 scope

- Store conversation turns and derived memories with embeddings.
- Retrieve relevant memories via hybrid search: pgvector cosine similarity fused with PostgreSQL full-text ranking (native `tsvector`/`ts_rank`; BM25 extensions such as `pg_textsearch`/ParadeDB `pg_search` are a documented future upgrade, not a v1 requirement).
- Scope memories by application, agent, thread, and user identifiers.

### Deferred to a later iteration

- The reusable client and context-provider separation described in
  [0042-postgres-context-memory.md](0042-postgres-context-memory.md), which supersedes the initial
  provider-owned design.
- BM25 ranking via `pg_textsearch`/ParadeDB `pg_search` (native `tsvector`/`ts_rank` is the v1 fallback and default).
- The Python package (`agent-framework-postgres-memory` or similar); this ADR covers the .NET package (`Microsoft.Agents.AI.Postgres`) first.
