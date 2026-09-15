# Azure Cosmos DB Package (agent-framework-azure-cosmos)

Azure Cosmos DB for NoSQL integrations for Agent Framework.

## Main Classes

- **`CosmosHistoryProvider`** - Persistent conversation history storage backed by Azure Cosmos DB
- **`CosmosCheckpointStorage`** - Workflow checkpoint storage backed by Azure Cosmos DB
- **`CosmosCollection`** - Vector collection using NoSQL `VectorDistance` queries
- **`CosmosStore`** - Factory and database administration for vector collections
- **`AzureCosmosSettings`** - Shared vector connector settings shape

## Usage

```python
from agent_framework.azure import CosmosHistoryProvider

provider = CosmosHistoryProvider(
    endpoint="https://<account>.documents.azure.com:443/",
    credential="<key-or-token-credential>",
    database_name="agent-framework",
    container_name="chat-history",
)
```

Container name is configured on the provider. `session_id` is used as the partition key.

Vector collections require an application-provided string key stored as `id` and a
container partition key of `/id`. Container vector and indexing policies are created
only by `ensure_collection_exists()` and validated before use. Existing incompatible
containers are never updated or recreated.
Supported vector element types are float32, int8, and uint8. Euclidean search is supported,
but Euclidean score thresholds fail before service I/O.

## Import Path

```python
from agent_framework.azure import CosmosCollection, CosmosHistoryProvider, CosmosStore
# or directly:
from agent_framework_azure_cosmos import CosmosCollection, CosmosHistoryProvider, CosmosStore
```
