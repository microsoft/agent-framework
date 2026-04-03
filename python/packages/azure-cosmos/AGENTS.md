# Azure Cosmos DB Package (agent-framework-azure-cosmos)

Azure Cosmos DB history and retrieval provider integration for Agent Framework.

## Main Classes

- **`CosmosHistoryProvider`** - Persistent conversation history storage backed by Azure Cosmos DB
- **`AzureCosmosContextProvider`** - Cosmos DB context provider for injecting relevant documents before a model run and writing request/response messages back into the same container after the run

## Usage

```python
from agent_framework_azure_cosmos import AzureCosmosContextProvider, CosmosContextSearchMode, CosmosHistoryProvider

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
```

Container name is configured on each provider. `CosmosHistoryProvider` uses `session_id` as the partition key for reads/writes. `AzureCosmosContextProvider` can optionally scope retrieval with `partition_key`.

`AzureCosmosContextProvider` writes request/response messages back into the same Cosmos knowledge container by default. Set `writeback_enabled=False` to disable it. Hybrid RRF weights are provided per run through `before_run(..., weights=[...])`.

## Import Path

```python
from agent_framework_azure_cosmos import AzureCosmosContextProvider, CosmosHistoryProvider
```
