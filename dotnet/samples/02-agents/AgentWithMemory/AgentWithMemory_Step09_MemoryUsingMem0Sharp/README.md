# Agent with Memory Using Mem0Sharp

This sample uses the [`Mem0Sharp`](https://www.nuget.org/packages/Mem0Sharp) NuGet package as a local, in-memory store for an Agent Framework agent. It stores a user preference and recalls it from a new agent session without requiring a memory service or database.

## Prerequisites

1. [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
2. A Microsoft Foundry project with a chat model deployment
3. Azure CLI authentication (`az login`)

## Configuration

| Variable | Description | Default |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Microsoft Foundry project endpoint | *(required)* |
| `FOUNDRY_MODEL` | Chat model deployment name | `gpt-5.4-mini` |

## Run the Sample

```bash
dotnet run
```

## Storage Providers

This sample uses `MemoryService`'s default in-memory store, so memories do not survive application restarts. Mem0Sharp also supports:

- Qdrant through `QdrantMemoryStore`, included in the core `Mem0Sharp` package
- PostgreSQL with pgvector through the [`Mem0Sharp.PostgreSQL`](https://www.nuget.org/packages/Mem0Sharp.PostgreSQL) package
- SQLite through the [`Mem0Sharp.SQLite`](https://www.nuget.org/packages/Mem0Sharp.SQLite) package
- Custom providers by implementing `IMemoryStore` and, when needed, optional interfaces such as `IVectorMemoryStore` or `IMemoryHistoryStore`

Pass the configured store to `MemoryService` to replace the in-memory store. See the [Mem0Sharp providers and persistence guide](https://github.com/jihadkhawaja/mem0sharp/blob/main/docs/providers-and-persistence.md) for setup examples.