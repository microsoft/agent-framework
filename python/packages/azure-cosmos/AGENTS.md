# Azure Cosmos DB Package (agent-framework-azure-cosmos)

Azure Cosmos DB history provider integration for Agent Framework.

## Main Classes

- **`CosmosHistoryProvider`** - Persistent conversation history storage backed by Azure Cosmos DB

## Usage

```python
from agent_framework_azure_cosmos import CosmosHistoryProvider

provider = CosmosHistoryProvider(
    endpoint="https://<account>.documents.azure.com:443/",
    credential="<key-or-token-credential>",
    database_name="agent-framework",
    container_name="chat-history",
)
```

Container name is configured on the provider. `session_id` is used as the partition key.

## Import Path

```python
from agent_framework_azure_cosmos import CosmosHistoryProvider
```
