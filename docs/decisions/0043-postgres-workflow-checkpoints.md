---
status: proposed
contact: jaredmeade
date: 2026-09-17
deciders: jaredmeade
---

# PostgreSQL workflow checkpoints with a shared storage schema

## Context and Problem Statement

The PostgreSQL integration already persists agent memory. Workflows also need exact
execution snapshots to survive a process restart or wait for human approval. These are
not derived memories and must not pass through extraction, summarization, or vector search.
Python and .NET should share a storage contract without implying that their different
execution-state formats can resume across runtimes.

## Decision Drivers

- Reuse the existing checkpoint extension points without modifying the workflow engine.
- Support plain PostgreSQL, including deployments without pgvector or a model client.
- Share one relational schema and default table across both SDKs.
- Preserve scoped access, immutable snapshots, parent history, and committed save order.

## Considered Options

- **Separate language-specific tables:** simple payload separation, but duplicates database
  administration and creates unnecessary schema divergence.
- **Shared table with an explicit payload format:** common storage and operations, with
  independent SDK codecs. Does not provide cross-language execution recovery.
- **Universal checkpoint codec:** could enable portable recovery, but requires a framework-wide
  contract for graphs, executor identities, messages, types, and state restoration. A storage
  adapter cannot supply that guarantee by converting JSON field names.

## Decision Outcome

Implement `PostgresCheckpointStorage` in Python and `PostgresCheckpointStore` in .NET.
Both default to the same `agent_framework_checkpoints` table, in an existing configured
schema, with this common envelope:

| Column | Meaning |
| --- | --- |
| `application_id`, `tenant_id` | Required trusted application and authorization scope |
| `run_id` | Required execution identity; .NET's workflow session ID |
| `payload_format` | SDK-specific codec identifier |
| `checkpoint_id` | Identity within the scope and format |
| `workflow_name` | Optional definition metadata; used by Python filtering |
| `parent_checkpoint_id` | Previous checkpoint identity, when present |
| `version` | Storage-envelope version, initially integer 1 |
| `sequence` | Database-generated identity used for save ordering |
| `created_at` | Database timestamp for operational inspection |
| `payload` | Framework-serialized JSONB snapshot |

The composite primary key is `(application_id, tenant_id, run_id, payload_format, checkpoint_id)`.
A common B-tree index covers `(application_id, tenant_id, run_id, payload_format, sequence)`.
Each adapter filters every retrieval and deletion by its complete scope and format:

- Python: `agent-framework.python.checkpoint.v1`.
- .NET: `agent-framework.dotnet.checkpoint.v1`.

The discriminator versions the codec contract, not the installed package. Python retains
the checkpoint's own format version inside its payload. The .NET provider treats the
framework's `JsonElement` as opaque. A format change requires a new discriminator or an
explicit compatibility strategy; changing the envelope requires a schema migration.

Both providers serialize saves within a run and format using transaction-scoped PostgreSQL
advisory locks. The database identity is assigned after obtaining the lock, so commit order
does not depend on worker clocks or iteration counts. Python re-saving an identical
checkpoint ID is idempotent and does not change history order; conflicting content is
rejected. The .NET contract generates a new checkpoint ID for each creation.

## Consequences

- The same physical table can contain both runtimes' checkpoints, even for identical
  application, tenant, run, and checkpoint IDs. Neither runtime decodes the other's rows.
- SDK-specific payloads are **not** cross-runtime resumable. Python uses the framework's
  restricted pickle/JSON codec; .NET uses its JSON checkpoint marshaller.
- Scope values must be authorized by the host. They are query isolation, not a replacement
  for database access controls. Checkpoints must remain trusted, private, untampered state.
- Callers own injected connections and pools. A borrowed Python connection's outer
  transaction must commit before its checkpoint is durable; use pools for parallel writes.
- Table initialization creates no schema or extension and does not migrate incompatible
  existing tables. Provision the table before concurrent workers start. Retention and
  cleanup remain application responsibilities.
- Checkpoint persistence does not add scheduling, worker leases, distributed workflow
  ownership, or exactly-once external side effects. Hosts must avoid concurrent execution
  of the same run and use idempotency or an outbox for repeatable side effects.

## Verification

Focused tests cover round trips, scope and payload-format isolation, history ordering,
duplicate-save behavior, parent lookup, rollback, and concurrent writes. Model-free approval
samples demonstrate preserving a human wait across separate processes. Validation uses
an isolated PostgreSQL database without the vector extension.

## References

- [PostgreSQL ContextMemory architecture](0042-postgres-context-memory.md)
- [Workflow checkpoint documentation](https://learn.microsoft.com/agent-framework/workflows/checkpoints)
- [Durable execution extension](https://learn.microsoft.com/agent-framework/hosting/azure-functions)
