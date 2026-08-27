# Agent with Memory Using Azure Cosmos DB for NoSQL

This sample uses `ChatHistoryMemoryProvider` with `CosmosVectorStore` to persist chat history in Azure Cosmos DB for NoSQL and recall relevant messages in a new agent session.

## Features Demonstrated

- Authenticating to Microsoft Foundry and Azure Cosmos DB with `DefaultAzureCredential`
- Storing chat messages in an Azure Cosmos DB vector store
- Creating the configured database and chat-history container when they do not exist
- Recalling relevant chat history across agent sessions

## Prerequisites

1. [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
2. A Microsoft Foundry project with:
   - A chat model deployment (the default is `gpt-5.4-mini`)
   - A `text-embedding-3-large` deployment with 3,072 dimensions
3. An Azure Cosmos DB for NoSQL account with [vector search enabled](https://learn.microsoft.com/azure/cosmos-db/nosql/vector-search)
4. An Azure identity that can create the configured database and container and read and write items
5. Azure CLI authentication (`az login`)

## Configuration

Set the following environment variables:

| Variable | Description | Default |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Microsoft Foundry project endpoint | *(required)* |
| `COSMOS_ENDPOINT` | Azure Cosmos DB account endpoint | *(required)* |
| `FOUNDRY_MODEL` | Chat model deployment name | `gpt-5.4-mini` |
| `FOUNDRY_EMBEDDING_MODEL` | Embedding model deployment name | `text-embedding-3-large` |
| `FOUNDRY_EMBEDDING_DIMENSIONS` | Number of dimensions produced by the embedding deployment | `3072` |
| `COSMOS_DATABASE_NAME` | Database used to store agent memory | `agent-memory` |

## Run the Sample

```bash
dotnet run
```

The first session stores the user's preference for pirate jokes. The second session uses a different `AgentSession` but the same per-run user search scope, allowing the agent to retrieve that preference from Azure Cosmos DB without recalling data from earlier sample runs.