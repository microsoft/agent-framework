# Azure Cosmos DB Package (agent-framework-azure-cosmos)

Azure Cosmos DB history, retrieval, and workflow checkpointing integration for Agent Framework.

## Main Classes

- **`CosmosHistoryProvider`** - Persistent conversation history storage backed by Azure Cosmos DB
- **`AzureCosmosContextProvider`** - Cosmos DB context provider for injecting relevant documents before a model run and writing request/response messages back into the same container after the run
- **`CosmosCheckpointStorage`** - Cosmos DB-backed workflow checkpoint storage for durable workflow execution

## Usage

```python
from agent_framework_azure_cosmos import (
    AzureCosmosContextProvider,
    CosmosCheckpointStorage,
    CosmosContextSearchMode,
    CosmosHistoryProvider,
)

history_provider = CosmosHistoryProvider(
    endpoint="https://<account>.documents.azure.com:443/",
    credential="<key-or-token-credential>",
    database_name="agent-framework",
    container_name="chat-history",
)

context_provider = AzureCosmosContextProvider(
    endpoint="https://<account>.documents.azure.com:443/",
    credential="<key-or-token-credential>",
    database_name="agent-framework",
    container_name="knowledge",
    default_search_mode=CosmosContextSearchMode.FULL_TEXT,
)

checkpoint_storage = CosmosCheckpointStorage(
    endpoint="https://<account>.documents.azure.com:443/",
    credential="<key-or-token-credential>",
    database_name="agent-framework",
    container_name="workflow-checkpoints",
)
```

Container name is configured on each provider. `CosmosHistoryProvider` uses `session_id` as the partition key for reads/writes. `AzureCosmosContextProvider` can optionally scope retrieval with `partition_key`.

`AzureCosmosContextProvider` joins the filtered `user` and `assistant` messages from the current run into one retrieval query string, and writes request/response messages back into the same Cosmos knowledge container after each run. Hybrid RRF weights are provided per run through `before_run(..., weights=[...])`.

When `AzureCosmosContextProvider` is attached to an agent through `context_providers=[...]`, normal agent runs use the provider defaults configured on the constructor. The explicit `before_run(..., search_mode=..., weights=[...], top_k=..., scan_limit=..., partition_key=...)` override is available for advanced callers and custom orchestration without mutating the provider instance.

The application owner is responsible for making sure the Cosmos account, database, container, partitioning strategy, and any required full-text/vector/hybrid indexing configuration already exist. The provider does not create or manage Cosmos resources or search policies.

`CosmosCheckpointStorage` creates the configured database and container on first use when needed, and stores workflow checkpoints using `/workflow_name` as the partition key.

## Import Path

```python
from agent_framework_azure_cosmos import (
    AzureCosmosContextProvider,
    CosmosCheckpointStorage,
    CosmosHistoryProvider,
)

# `CosmosHistoryProvider` is also available from the Azure namespace:
from agent_framework.azure import CosmosHistoryProvider
```
