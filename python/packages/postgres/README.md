# Agent Framework PostgreSQL

Store vector records, durable agent memory, and workflow checkpoints in PostgreSQL with this alpha integration for
[Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/).
The package uses Psycopg 3 and the official pgvector Python adapter.

- **`PostgresCollection`** provides batch upsert, retrieval, deletion, and vector similarity search.
- **`PostgresStore`** creates collection clients that share a connection pool.
- **`PostgresMemoryClient`** stores turns, extracts typed memories, maintains summaries, and performs hybrid retrieval.
- **`PostgresMemoryContextProvider`** injects relevant memory before agent runs and stores new turns afterward.
- **`PostgresCheckpointStorage`** persists workflow state for scoped checkpoint recovery.
- **`PostgresSettings`** describes connection settings resolved by Agent Framework.

## Installation

```bash
pip install agent-framework-postgres --pre
```

Requires Python 3.10+ and PostgreSQL 13+. Vector storage and memory additionally require pgvector 0.8.0+;
checkpoint storage does not require a database extension or a model client.
Import the connector directly from `agent_framework_postgres`.
Python 3.10 through 3.14 install Psycopg's binary distribution. Python 3.15+
uses the pure-Python implementation because binary wheels are not yet
published, so a system `libpq` installation is required.

## Connection setup

For vector storage and memory, have your database administrator install and enable the `vector` extension and
provide an existing schema. The extension must be visible through the connection's
`search_path`. The connector never creates schemas, enables extensions, or changes
server-wide configuration. `ensure_collection_exists()` creates a vector collection's
table and requested indexes. `PostgresMemoryClient.ensure_schema()` creates the four
memory tables and their indexes. Both operations require the corresponding permissions
and do not migrate incompatible existing tables.

Set `POSTGRES_CONNECTION_STRING` to a PostgreSQL URI or Psycopg conninfo string,
or pass `connection_string` to either constructor. Both accept a string or AF
`SecretString`. Settings precedence is **explicit argument > selected `.env`
file > environment**. Select a file with `env_file_path` and optional
`env_file_encoding`; missing or empty connection strings are rejected.
The `schema` argument defaults to `public`.

A connector-created pool is closed by `close()` or an async context manager.
Alternatively, inject an open Psycopg `AsyncConnection` or `AsyncConnectionPool`
using `client`; it remains caller-owned and bypasses settings loading.
Injected clients cannot be combined with connection-string or `.env` options.
Collections created by a store borrow its pool, so keep the store open while
using them.

## Workflow checkpoints

`PostgresCheckpointStorage` implements the framework's `CheckpointStorage` protocol.
It stores the complete framework-encoded snapshot in JSONB, including executor state,
queued messages, and pending human requests. Memory extraction and retrieval are not involved.

```python
from agent_framework_postgres import PostgresCheckpointStorage

storage = PostgresCheckpointStorage(
    application_id="purchasing",
    tenant_id="authorized-tenant",
    run_id="purchase-1042",
)
```

Use it as an async context manager, call `await storage.ensure_table()` once during setup,
and pass it as `checkpoint_storage` to `WorkflowBuilder`. It resolves connection settings
and borrows connections or pools using the same rules as the other package clients.
`ensure_table()` requires an existing schema and table/index creation permissions; it
does not create schemas, install extensions, or migrate incompatible tables.

The default table is `agent_framework_checkpoints`, shared with the .NET provider.
Both use the same relational schema. Every operation is scoped to application, tenant,
run, and `payload_format`; the Python format is `agent-framework.python.checkpoint.v1`.
Use trusted, authorized scope values, not unvalidated IDs from a request. A workflow name
identifies a definition, not a tenant or run. Recreate the same storage scope and workflow
graph, with stable executor identities, to resume.

Sharing the table does **not** enable cross-language workflow resumption. Python's
framework codec may embed pickled Python objects; .NET uses its own checkpoint structure.
Each provider reads only its own format. See the [shared storage decision](../../../docs/decisions/0043-postgres-workflow-checkpoints.md)
for the table contract.

Checkpoints are immutable: saving the same ID and payload again is idempotent; saving
different state under an existing ID raises `WorkflowCheckpointException`. History and
`get_latest()` use database save order, not iteration counts or client timestamps.
Saves are transactionally serialized within a run. A borrowed connection's outer
transaction remains caller-owned: commit it before treating its checkpoints as durable,
and use a pool for concurrent saves. `delete()` removes only the selected checkpoint,
without cascading to children or other formats. Retention is application-managed.

Only read checkpoints from trusted, access-controlled storage. For application-defined
Python types, supply `allowed_checkpoint_types` or use `register_checkpoint_type`.
The decoder's allowlist is defense in depth, not a security boundary. Checkpoint storage
does not supply worker scheduling, leases, or exactly-once external side effects;
operations after a checkpoint can repeat and should use idempotency keys.

The [approval sample](samples/postgres_checkpointing.py) exits while waiting, then resumes
in a separate process. With `POSTGRES_CONNECTION_STRING` configured, run from this package:

```sh
python samples/postgres_checkpointing.py start --tenant-id demo --run-id purchase-1042
python samples/postgres_checkpointing.py resume --tenant-id demo --run-id purchase-1042 --decision approve
```

On Windows, Psycopg requires a selector event loop. The sample configures one at its
entry point; library code does not change the application's event-loop policy.
Run checkpoint tests with `POSTGRES_TEST_CONNECTION_STRING` pointing at an explicitly
designated test database. Those tests create and remove temporary schemas and do not
require pgvector.

## Durable memory

The provider can construct and own its `PostgresMemoryClient`, so a single call wires
PostgreSQL, embeddings, memory processing, and Agent Framework lifecycle hooks:

```python
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient, OpenAIEmbeddingClient
from agent_framework_postgres import (
    PostgresMemoryClientOptions,
    PostgresMemoryContextProvider,
)

chat_client = OpenAIChatClient()
provider = PostgresMemoryContextProvider(
    connection_string="postgresql://user:password@localhost/agents",
    embedding_generator=OpenAIEmbeddingClient(model="text-embedding-3-small"),
    chat_client=chat_client,
    application_id="support-app",
    agent_id="support-agent",
    auto_extract=True,
    client_options=PostgresMemoryClientOptions(embedding_dimensions=1536),
)
agent = Agent(
    client=chat_client,
    instructions="Answer clearly and use relevant prior context.",
    context_providers=[provider],
)

session = agent.create_session()
session.state.setdefault(provider.source_id, {})["user_id"] = "stable-user-id"

async with provider:
    response = await agent.run("Remember that I prefer concise Python examples.", session=session)
    await provider.flush()
```

A stable `user_id` is required by default and must be authenticated and authorized by
the application before it is placed in provider state. Set
`fallback_to_session_id=True` only when session-scoped recall is sufficient; this uses
the session ID as both the user and default thread boundary. `thread_id` otherwise
defaults to the Agent Framework session ID and can be overridden with
`state["thread_id"]`. Searches span all threads for the user by default. Optional
application and agent identifiers are exact isolation dimensions; omitted identifiers
match only rows where those identifiers are also null.

The convenience provider owns only the `PostgresMemoryClient` it creates. Supplied
Psycopg connections or pools and model clients remain caller-owned. Construct
`PostgresMemoryClient` explicitly when it must be shared, queried directly, or driven
by a separate processing worker.

The memory client uses four typed tables:

- `{base}_turns` stores append-only conversation turns.
- `{base}_memories` stores fact, procedural, and episodic memories with confidence,
  salience, tags, embeddings, expiry, and supersession history.
- `{base}_summaries` stores versioned thread and cross-thread user summaries.
- `{base}_processing` stores monotonic processing checkpoints.

Retrieval fuses pgvector cosine ranking with PostgreSQL `tsvector`/`ts_rank` using
Reciprocal Rank Fusion. Expired and superseded memories are excluded. Turn writes can
schedule cadence-aware extraction, summaries, and reconciliation in the current
process. Pass `auto_extract=False` to the convenience provider, or set
`auto_process=False` in `PostgresMemoryClientOptions`, when processing must be explicit.
Call `provider.process_now(session=session, state=provider_state)` to run all processing
steps for the resolved scope. `flush()` waits up to 30 seconds by default; pass
`timeout=None` to wait without a limit.

Processing cadence, reconciliation pool size, deduplication thresholds, episodic
retention, and all extraction and summarization prompts are configurable through
`PostgresMemoryClientOptions` and `PostgresMemoryPromptOptions`. A borrowed single
`AsyncConnection` requires automatic processing to be disabled; use a connection string
or `AsyncConnectionPool` for background processing.

### Azure DiskANN and semantic reranking

On Azure Database for PostgreSQL flexible server, memory retrieval can use the
`pg_diskann` index and rerank the hybrid candidate set with one batched
`azure_ai.rank()` call:

```python
from agent_framework_postgres import PostgresMemoryClientOptions, PostgresMemoryVectorIndexKind

options = PostgresMemoryClientOptions(
    embedding_dimensions=1536,
    vector_index_kind=PostgresMemoryVectorIndexKind.DISK_ANN,
    enable_azure_ai_reranking=True,
    azure_ai_reranker_model="cohere-rerank-v3.5",
    reranking_candidate_count=25,
)
```

The database administrator must allowlist and enable `vector`, `pg_diskann`, and
`azure_ai`; this connector does not install extensions. When reranking is enabled,
hybrid retrieval expands to `reranking_candidate_count`, and `azure_ai.rank()` orders
those candidates semantically. `PostgresMemoryRecord.score` retains the RRF score and
`reranker_score` contains the semantic relevance score. If the database reranking call
fails, retrieval returns the original hybrid order.

The default HNSW index supports at most 2,000 dimensions. DiskANN supports higher
dimensions only with product quantization in `pg_diskann` 0.6 or later; this client does
not yet configure product quantization, so memory embeddings currently retain the
2,000-dimension limit. Run `samples/postgres_memory.py --azure` to exercise DiskANN and
semantic reranking with a 1,536-dimensional `text-embedding-3-small` deployment.

For advanced provider integration, configure `search_input_message_filter`,
`storage_input_request_message_filter`, and `storage_input_response_message_filter` to
control which messages participate in retrieval and persistence. A `scope_resolver`
can return `PostgresMemoryContextProviderState` with independent storage and search
scopes when the built-in user-wide or thread-local retrieval modes are insufficient.

## Vector store example

With `POSTGRES_CONNECTION_STRING` configured, create a typed collection and
search using precomputed embeddings:

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import Filter, VectorStoreField, vectorstoremodel
from agent_framework_postgres import PostgresStore


@vectorstoremodel(collection_name="articles")
@dataclass
class Article:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main() -> None:
    async with PostgresStore() as store:
        collection = store.get_collection(Article)
        await collection.ensure_collection_exists()
        await collection.upsert(
            [
                Article("1", "PostgreSQL supports vectors", [1, 0, 0]),
                Article("2", "A travel journal", [0, 1, 0]),
            ],
            generate_vectors=False,
        )
        results = await collection.search(
            vector=[1, 0, 0],
            filter=Filter("text", "contains_text", "PostgreSQL"),
            score_threshold=0.25,
            top=3,
        )
        async for result in results:
            print(result["record"].text, result["score"])


if __name__ == "__main__":
    asyncio.run(main())
```

Pass `generate_vectors=False` to preserve supplied embeddings. To generate them
locally, configure an `embedding_generator`. Retrieval excludes embeddings by
default; use `include_vectors=True` to return them.

## Capabilities and limits

The connector supports typed models, string/integer/UUID keys (including generated
keys), multiple nullable vector columns, storage aliases, and database-side
filters and paging. Batch writes are transactional; an existing transaction on
an injected connection remains under the caller's commit control.

Vector fields support `float`, `float32`, and `float16` declarations. PostgreSQL
`vector` storage uses 32-bit floats; `float16` defaults to 16-bit `halfvec`.
The `postgres.vector_type` provider annotation explicitly selects either storage
type. Ordinary Python floats and integer-valued elements are accepted and rounded
to the selected precision; declared `int` and `float64` vector fields are rejected.

Storage precision does not determine the model's Python scalar type. The default
decoder returns ordinary Python floats: use `list[float]` annotations even with
explicit `float16` or `float32` field metadata. Models annotated with
`list[numpy.float16]` or `list[numpy.float32]` require a custom `decoder` passed to
`vectorstoremodel` or `register_vectorstoremodel`. That decoder must reconstruct
each component with the declared NumPy scalar type and handle omitted vector
fields when `include_vectors=False`. NumPy is not a connector runtime dependency.

Exact search is the default. HNSW and IVFFlat are optional approximate indexes;
selective filters can reduce their recall. Use
`operation_options={"exact": True}` when complete recall is required.
`exact=False` requires an HNSW or IVFFlat field. Result metadata's `approximate`
flag identifies ANN-permitted query mode, not proof that PostgreSQL used an ANN
index.
IVFFlat needs data before index creation: first call
`ensure_collection_exists(operation_options={"create_indexes": False})`, load
records, then call `ensure_collection_exists()` again.
Storage supports up to 16,000 dimensions; ANN indexes support up to 2,000 for
`vector` and 4,000 for `halfvec`.

Scores use the selected metric's units, not probabilities. The default is cosine
distance, where lower is better and `score_threshold` is a maximum. Cosine
similarity and dot product use minimum thresholds; negative dot product, L2, and
L1 distances use maximum thresholds. IVFFlat does not support L1.

`PostgresCollection` does not support keyword/hybrid/full-text search, sparse/binary
vectors, nested filter paths, schema migration, or server-side embedding generation.
Hybrid full-text/vector retrieval is provided by `PostgresMemoryClient` for its managed
memory schema.

## Documentation

- [Microsoft Agent Framework documentation](https://learn.microsoft.com/agent-framework/)
- [PostgreSQL documentation](https://www.postgresql.org/docs/current/)
- [pgvector setup, indexes, and distance functions](https://github.com/pgvector/pgvector)
- [Psycopg connection pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)
