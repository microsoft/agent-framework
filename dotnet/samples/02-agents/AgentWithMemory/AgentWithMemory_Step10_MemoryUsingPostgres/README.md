# Agent with Memory Using PostgreSQL

This sample uses `PostgresMemoryClient` and `PostgresMemoryContextProvider` to derive and persist typed memories in PostgreSQL with pgvector, then recall them in a new agent session.

## Features Demonstrated

- Authenticating to Microsoft Foundry with `DefaultAzureCredential`
- Storing and inspecting raw conversation turns
- Extracting fact, procedural, and episodic memories
- Generating thread and cross-thread user summaries
- Using pgvector hybrid search to recall all three derived-memory types in new sessions
- Reconciling a changed preference while preserving supersession history
- Running the processing pipeline explicitly with `ProcessNowAsync`
- Using automatic background processing with `FlushAsync` in a smaller getting-started mode
- Using DiskANN and `azure_ai.rank()` on Azure Database for PostgreSQL flexible server

## Prerequisites

1. [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
2. A Microsoft Foundry project with:
   - A chat model deployment (the default is `gpt-5.4-mini`)
   - A `text-embedding-3-small` deployment with 1,536 dimensions
3. A PostgreSQL database with the [pgvector extension](https://github.com/pgvector/pgvector) available
4. A database role that can create the configured schema, tables, indexes, and the `vector` extension if it is not already installed
5. Azure CLI authentication (`az login`)

## Configuration

Set the following environment variables:

| Variable | Description | Default |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Microsoft Foundry project endpoint | *(required)* |
| `POSTGRES_MEMORY_CONNECTION_STRING` | Npgsql connection string for the memory database | *(required)* |
| `FOUNDRY_MODEL` | Chat model deployment name | `gpt-5.4-mini` |
| `FOUNDRY_EMBEDDING_MODEL` | Embedding model deployment name | `text-embedding-3-small` |
| `FOUNDRY_EMBEDDING_DIMENSIONS` | Number of dimensions produced by the embedding deployment | `1536` |
| `FOUNDRY_RERANKER_MODEL` | Foundry reranker deployment name used by the Azure demo | `cohere-rerank-v3.5` |

### Embedding Model Dimensions

The embedding model and vector dimensions are a pair:

| Model | Default dimensions | Supported by this sample |
|---|---:|---|
| `text-embedding-3-small` | 1,536 | Yes (the default) |
| `text-embedding-3-large` | 3,072 | Not at its default size; `PostgresMemoryClient` currently supports up to 2,000 dimensions |

`FOUNDRY_EMBEDDING_DIMENSIONS` defines the PostgreSQL vector column size; it does not change the
number of dimensions returned by the embedding deployment. Its value must match the actual embedding
output. The sample therefore defaults to `text-embedding-3-small` with `1536`. Using the native
3,072-dimensional output from `text-embedding-3-large` requires future support for larger vectors
(such as DiskANN product quantization) in `PostgresMemoryClient`.

## Run the Sample

Run the smaller background-processing walkthrough:

```bash
dotnet run
```

### Advanced Memory Pipeline Demo

Run the comprehensive memory-processing walkthrough:

```bash
dotnet run -- --advanced
```

The walkthrough deliberately exercises all four PostgreSQL tables:

1. The first session stores raw turns, seeds fact, procedural, and episodic information, and explicitly runs extraction, thread summarization, user summarization, and reconciliation.
2. The second session uses hybrid retrieval to recall those memories from a new thread.
3. The third session changes the user's favorite animal from elephants to giraffes, then runs extraction and reconciliation to supersede the conflicting preference.
4. The final session verifies that a new thread receives the updated preference.

The sample prints the stored turns, active typed memories, summaries, and reconciliation count. Memory extraction and reconciliation use model output, so the exact records and wording can vary between runs.

### Azure DiskANN and Semantic Reranking Demo

This mode requires Azure Database for PostgreSQL flexible server. Allowlist `vector`, `pg_diskann`,
and `azure_ai` in the server's `azure.extensions` parameter. Deploy the configured reranker model in
Microsoft Foundry by using the Serverless API option.

Before running the Azure demo, choose one of the following authentication options.

#### Option 1: Cohere with an endpoint key

This is the default because `FOUNDRY_RERANKER_MODEL` defaults to `cohere-rerank-v3.5`.

1. Open the reranker deployment in Foundry and copy its endpoint key and **Reranker API** route.
2. Connect to the sample database as a user that can manage `azure_ai` settings, and run:

   ```sql
   CREATE EXTENSION IF NOT EXISTS azure_ai;

      SELECT azure_ai.set_setting('azure_ml.serverless_ranking_endpoint', '<Reranker API Endpoint>');
      SELECT azure_ai.set_setting('azure_ml.serverless_ranking_endpoint_key', '<Reranker API Key>');

   SELECT azure_ai.get_setting('azure_ml.serverless_ranking_endpoint');
   ```

This option does not require a managed identity or Azure role assignment. The endpoint key is stored
in the database's `azure_ai` settings, so do not commit or print it.

#### Option 2: Azure OpenAI with managed identity

Set `FOUNDRY_RERANKER_MODEL` to the name of a deployed Azure OpenAI chat model supported by
`azure_ai.rank()`, and then:

1. In the Azure portal, open the Azure Database for PostgreSQL flexible server used by
   `POSTGRES_MEMORY_CONNECTION_STRING`. Under **Security** > **Identity**, turn the system-assigned
   managed identity **On**, and then save the change.
2. Open the Azure OpenAI resource that hosts the model deployment. Under **Access control (IAM)**,
   assign the **Cognitive Services OpenAI User** role to the managed identity of the PostgreSQL
   flexible server.
3. Restart the PostgreSQL flexible server so that the new identity is available to `azure_ai`.
4. Connect to the sample database as a user that can manage `azure_ai` settings, and run:

   ```sql
   CREATE EXTENSION IF NOT EXISTS azure_ai;

   SELECT azure_ai.set_setting('azure_openai.auth_type', 'managed-identity');
   SELECT azure_ai.set_setting('azure_openai.endpoint', 'https://<azure-openai-resource-name>.openai.azure.com');
   --OR
   SELECT azure_ai.set_setting('azure_openai.subscription_key', '<API_KEY>');

   SELECT azure_ai.get_setting('azure_openai.auth_type');
   SELECT azure_ai.get_setting('azure_openai.endpoint');

   SELECT azure_ai.set_setting('azure_ml.serverless_ranking_endpoint', '<Ranking Endpoint URL>');
   SELECT azure_ai.set_setting('azure_ml.serverless_ranking_endpoint_key', '<Ranking Endpoint Key>');

   ```

The PostgreSQL administrator is a member of `azure_pg_admin`, which can manage these settings. For
more detail, see the Microsoft Learn guides for [managed identity with `azure_ai`](https://learn.microsoft.com/azure/postgresql/azure-ai/generative-ai-enable-managed-identity-azure-ai)
and [`azure_ai.rank()` setup](https://learn.microsoft.com/azure/postgresql/azure-ai/generative-ai-azure-ai-functions#setup-for-rank-function).

Run the Azure-specific walkthrough:

```bash
dotnet run -- --azure
```

The walkthrough creates a DiskANN index, prints its PostgreSQL definition, and stores several
similar memories. It then prints the same search first in hybrid reciprocal-rank-fusion order and
again after `azure_ai.rank()` semantic reranking so the two scores and ordering can be compared.

Both `pg_diskann` and the `azure_ai.rank()` AI function are preview features. Availability depends
on the Azure region and PostgreSQL version.