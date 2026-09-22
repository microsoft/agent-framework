# Microsoft Agent Framework PostgreSQL

`Microsoft.Agents.AI.Postgres` provides durable, cross-session agent memory backed by PostgreSQL
and pgvector, plus workflow checkpoint storage that does not require pgvector.
The package separates memory processing from Agent Framework lifecycle integration:

- `PostgresMemoryClient` owns the memory model, hybrid retrieval, processing pipeline, and
  background tasks.
- `PostgresMemoryContextProvider` adapts the client to Agent Framework's before/after invocation
  lifecycle.
- `PostgresCheckpointStore` implements `JsonCheckpointStore` for durable workflow recovery.

## Workflow checkpoints

```csharp
using Microsoft.Agents.AI.Postgres;
using Microsoft.Agents.AI.Workflows;
using Npgsql;

await using var checkpointDataSource = NpgsqlDataSource.Create(connectionString);
var checkpointStore = new PostgresCheckpointStore(
        checkpointDataSource, applicationId: "purchasing", tenantId: authenticatedTenantId);
await checkpointStore.EnsureTableAsync();
var checkpointManager = checkpointStore.CreateCheckpointManager();
```

Pass the manager to `InProcessExecution.RunStreamingAsync` and supply a stable `sessionId`
for the workflow run. Later, reconstruct the same graph and executor identities, obtain
the latest checkpoint with `checkpointManager.GetLatestCheckpointAsync(sessionId)`, and
pass it to `InProcessExecution.ResumeStreamingAsync` with the manager.

Use `CreateCheckpointManager()` to enable out-of-order JSON metadata, since JSONB
does not preserve property order. Application-specific serializer options can be passed
to this factory; they are copied without mutation. When constructing a manager directly
with `CheckpointManager.CreateJson`, supply `JsonSerializerOptions` with
`AllowOutOfOrderMetadataProperties = true` or polymorphic workflow state may fail to resume.

The supplied `NpgsqlDataSource` remains caller-owned. `EnsureTableAsync` creates a table
and index in an existing schema, with the corresponding database permissions. It does
not create schemas, install extensions, or migrate existing tables. PostgreSQL 13 or
later is sufficient; neither `UseVector()` nor an embedding or chat client is required.

Both Python and .NET use the default `agent_framework_checkpoints` table and the same
relational schema. The .NET `sessionId` maps to `run_id`. Queries always filter application,
tenant, run, and `payload_format` (`agent-framework.dotnet.checkpoint.v1`). Scope values
must come from trusted, authenticated application code. An index returns checkpoints
oldest first in committed save order, with optional parent filtering.

The table is shared, but execution payloads are SDK-specific. A .NET workflow cannot
resume a Python checkpoint or vice versa. See the
[shared storage decision](../../../docs/decisions/0043-postgres-workflow-checkpoints.md).
Use database permissions to keep checkpoints private and untampered; storage scoping
does not replace authorization. Retention is application-managed. This provider is not
a worker scheduler or an exactly-once execution engine: external actions after the last
checkpoint can repeat, so use idempotency keys where needed.

The [approval sample](../../samples/03-workflows/Checkpoint/PostgresCheckpointing) runs
the start and resume phases in separate processes. Set
`POSTGRES_CHECKPOINT_CONNECTION_STRING` to an explicitly designated database to run
`PostgresCheckpointStoreIntegrationTests`; these tests create and remove isolated schemas.

## Durable memory

The client stores raw turns and derives facts, procedural memories, episodic memories, thread
summaries, and cross-thread user summaries. Derived memories include confidence metadata and can be
reconciled when newer information contradicts older records.

```csharp
await using var dataSource = new NpgsqlDataSourceBuilder(connectionString)
    .UseVector()
    .Build();

await using var memoryProvider = new PostgresMemoryContextProvider(
    dataSource,
    embeddingGenerator,
    chatClient,
    _ => new PostgresMemoryContextProvider.State(
        new PostgresMemoryScope
        {
            UserId = authenticatedUserId,
            ThreadId = conversationId,
        }),
    clientOptions: new PostgresMemoryClientOptions
    {
        EmbeddingDimensions = 1536,
    },
    providerOptions: new PostgresMemoryContextProviderOptions
    {
        TopK = 5,
    });

var agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [memoryProvider],
});
```

This constructor creates, flushes, and disposes the internal `PostgresMemoryClient`. The supplied
`NpgsqlDataSource`, embedding generator, and chat client remain owned by the caller or dependency
injection container. Create a `PostgresMemoryClient` separately and pass it to the provider when it
must be shared, queried directly, or used by an external processing worker.

Use a stable, authorized `UserId` for cross-session recall. The default search scope omits the
thread id, so relevant memories can be recalled from the user's other conversations.
`ApplicationId` and `AgentId` are exact isolation dimensions: a null value matches only records
stored with a null value and does not search other applications or agents.

Turn writes schedule extraction and summary processing in the background by default. Drain pending
work before shutdown:

```csharp
await memoryProvider.FlushAsync();
```

Set `PostgresMemoryClientOptions.AutoProcess` to `false` and call
`PostgresMemoryContextProvider.ProcessNowAsync` with the current agent session, or call
`PostgresMemoryClient.ProcessNowAsync` with a scope when the application owns processing cadence
explicitly.

The database role must be able to create the configured schema and tables when
`EnsureSchemaOnFirstUse` is enabled. Install the PostgreSQL `vector` extension before deployment,
or grant the development role permission to create it on first use.

## Azure PostgreSQL DiskANN

Azure Database for PostgreSQL flexible server can use the `pg_diskann` extension instead of HNSW
for approximate vector search. Allowlist both `vector` and `pg_diskann` in the server's
`azure.extensions` parameter, then select DiskANN in the client options:

```csharp
clientOptions: new PostgresMemoryClientOptions
{
    EmbeddingDimensions = 1536,
    VectorIndexKind = PostgresMemoryVectorIndexKind.DiskAnn,
}
```

When `EnsureSchemaOnFirstUse` is enabled, the client creates the allowlisted extensions and the
selected indexes. Changing `VectorIndexKind` replaces indexes managed by this package; it does not
modify other indexes. DiskANN availability and supported versions depend on the Azure region and
PostgreSQL version. HNSW remains the default and works with PostgreSQL installations that support
pgvector.

## Azure AI semantic reranking

Azure Database for PostgreSQL flexible server can rerank the hybrid search candidate set by using
the preview `azure_ai.rank()` function. Allowlist `azure_ai`, deploy a supported reranker in
Microsoft Foundry, and configure the extension's endpoint and authentication. Managed identity is
recommended.

Enable reranking in the client options:

```csharp
clientOptions: new PostgresMemoryClientOptions
{
    EnableAzureAiReranking = true,
    AzureAiRerankerModel = "cohere-rerank-v3.5",
    RerankingCandidateCount = 25,
}
```

The client retrieves candidates with vector and full-text search, combines them with reciprocal
rank fusion, and sends at most `RerankingCandidateCount` records to `azure_ai.rank()`. It returns
the requested `TopK` in semantic rank order. `PostgresMemoryRecord.Score` retains the reciprocal
rank fusion score, and `PostgresMemoryRecord.RerankerScore` contains the semantic relevance score.
If the ranking call fails with a PostgreSQL error, the client logs a warning and returns the
original hybrid order.

To run the live storage tests, set `POSTGRES_MEMORY_CONNECTION_STRING` to a PostgreSQL database with
pgvector available, then run the `Category=Postgres` tests.

### Azure reranking integration tests

`AzureRankLiveIntegrationTests` provides opt-in live coverage separate from the general storage tests.
Supply an Npgsql-format connection string through the environment; never commit credentials.

| Environment variable | Purpose |
| --- | --- |
| `POSTGRES_AZURE_AI_CONNECTION_STRING` | An explicitly designated Azure PostgreSQL test database with `vector` and `azure_ai` already enabled. Enables the disabled-reranking and single-candidate tests. |
| `POSTGRES_AZURE_AI_RERANKER_MODEL` | A working reranker deployment for the success test. This test requires semantic scores and fails if retrieval falls back to hybrid results. |
| `POSTGRES_AZURE_AI_FAILURE_MODEL` | A model name configured to fail, such as a nonexistent deployment, for the fallback test. This test requires a logged database error, unchanged hybrid results, and successful subsequent reads and writes. |

Missing connection or model settings skip the corresponding tests. Providing settings opts into
real database calls; the model-dependent tests can invoke external inference and incur charges.
Chat and embedding clients are deterministic test doubles, and all memory content is synthetic.
No particular SQL error or extension version is required by the fallback test.

The database role needs permission to create and drop schemas, tables, and indexes. Tests create
unique `af_azure_rank_*` schemas and remove them during teardown. They do not configure model
endpoints, modify server settings, or replace the installed reranking function.

From `dotnet`, after setting the environment variables, run:

```shell
dotnet test --project tests/Microsoft.Agents.AI.Postgres.UnitTests --framework net10.0 --filter-class "*AzureRankLiveIntegrationTests"
```
