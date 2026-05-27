# Get Started with Microsoft Agent Framework Azure Cosmos DB

Please install this package via pip:

```bash
pip install agent-framework-azure-cosmos --pre
```

## Azure Cosmos DB History Provider

The Azure Cosmos DB integration provides `CosmosHistoryProvider` for persistent conversation history storage.

### Basic Usage Example

```python
from azure.identity.aio import DefaultAzureCredential
from agent_framework_azure_cosmos import CosmosHistoryProvider

provider = CosmosHistoryProvider(
    endpoint="https://<account>.documents.azure.com:443/",
    credential=DefaultAzureCredential(),
    database_name="agent-framework",
    container_name="chat-history",
)
```

Credentials follow the same pattern used by other Azure connectors in the repository:

- Pass a credential object (for example `DefaultAzureCredential`)
- Or pass a key string directly
- Or set `AZURE_COSMOS_KEY` in the environment

Container naming behavior:

- Container name is configured on the provider (`container_name` or `AZURE_COSMOS_CONTAINER_NAME`)
- `session_id` is used as the Cosmos partition key for reads/writes

See `samples/02-agents/conversations/cosmos_history_provider.py` for a runnable example.

## Cosmos DB Workflow Checkpoint Storage

`CosmosCheckpointStorage` implements the `CheckpointStorage` protocol, enabling
durable workflow checkpointing backed by Azure Cosmos DB NoSQL. Workflows can be
paused and resumed across process restarts by persisting checkpoint state in Cosmos DB.

### Basic Usage

#### Managed Identity / RBAC (recommended for production)

```python
from azure.identity.aio import DefaultAzureCredential
from agent_framework import WorkflowBuilder
from agent_framework_azure_cosmos import CosmosCheckpointStorage

checkpoint_storage = CosmosCheckpointStorage(
    endpoint="https://<account>.documents.azure.com:443/",
    credential=DefaultAzureCredential(),
    database_name="agent-framework",
    container_name="workflow-checkpoints",
)
```

#### Account Key

```python
from agent_framework_azure_cosmos import CosmosCheckpointStorage

checkpoint_storage = CosmosCheckpointStorage(
    endpoint="https://<account>.documents.azure.com:443/",
    credential="<your-account-key>",
    database_name="agent-framework",
    container_name="workflow-checkpoints",
)
```

#### Then use with a workflow

```python
from agent_framework import WorkflowBuilder

# Build a workflow with checkpointing enabled
workflow = WorkflowBuilder(
    start_executor=start,
    checkpoint_storage=checkpoint_storage,
).build()

# Run the workflow — checkpoints are automatically saved after each superstep
result = await workflow.run(message="input data")

# Resume from a checkpoint
latest = await checkpoint_storage.get_latest(workflow_name=workflow.name)
if latest:
    resumed = await workflow.run(checkpoint_id=latest.checkpoint_id)
```

### Authentication Options

`CosmosCheckpointStorage` supports the same authentication modes as `CosmosHistoryProvider`:

- **Managed identity / RBAC** (recommended): Pass `DefaultAzureCredential()`,
  `ManagedIdentityCredential()`, or any Azure `TokenCredential`
- **Account key**: Pass a key string via `credential` parameter
- **Environment variables**: Set `AZURE_COSMOS_ENDPOINT`, `AZURE_COSMOS_DATABASE_NAME`,
  `AZURE_COSMOS_CONTAINER_NAME`, and `AZURE_COSMOS_KEY` (key not required when using
  Azure credentials)
- **Pre-created client**: Pass an existing `CosmosClient` or `ContainerProxy`

### Database and Container Setup

The database and container are created automatically on first use (via
`create_database_if_not_exists` and `create_container_if_not_exists`). The container
uses `/workflow_name` as the partition key. You can also pre-create them in the Azure
portal with this partition key configuration.

### Environment Variables

| Variable | Description |
|---|---|
| `AZURE_COSMOS_ENDPOINT` | Cosmos DB account endpoint |
| `AZURE_COSMOS_DATABASE_NAME` | Database name |
| `AZURE_COSMOS_CONTAINER_NAME` | Container name |
| `AZURE_COSMOS_KEY` | Account key (optional if using Azure credentials) |

See `samples/03-workflows/checkpoint/cosmos_workflow_checkpointing.py` for a standalone example,
or `samples/03-workflows/checkpoint/cosmos_workflow_checkpointing_foundry.py` for an end-to-end
example with Azure AI Foundry agents.
