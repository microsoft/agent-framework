# Azure Cosmos DB Context Provider Examples

The Azure Cosmos DB context provider enables persistent conversation history for your agents using Azure Cosmos DB. It uses `session_id` as the partition key for efficient multi-session support.

## Examples

| File | Description |
|------|-------------|
| [`cosmos_history_provider.py`](cosmos_history_provider.py) | Demonstrates an Agent using `CosmosHistoryProvider` with `FoundryChatClient` (configured against an Azure AI Foundry project endpoint), provider-configured container name, and `session_id` partitioning. |

## Prerequisites

### Required resources

1. An Azure Cosmos DB account with a database and container
2. Python environment with Agent Framework Azure Cosmos extra installed
3. Azure AI Foundry project endpoint and model deployment

### Install the package

```bash
pip install "agent-framework-azure-cosmos"
```

### Environment variables

- `FOUNDRY_PROJECT_ENDPOINT` (required): Azure AI Foundry project endpoint
- `FOUNDRY_MODEL` (required): Foundry model deployment name
- `AZURE_COSMOS_ENDPOINT` (required): Azure Cosmos DB endpoint
- `AZURE_COSMOS_DATABASE_NAME` (required): Cosmos DB database name
- `AZURE_COSMOS_CONTAINER_NAME` (required): Cosmos DB container name
- `AZURE_COSMOS_KEY` (optional): Cosmos DB key (falls back to Azure CLI credential)

## How to run

1. Set the required environment variables:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
export FOUNDRY_MODEL="<deployment-name>"
export AZURE_COSMOS_ENDPOINT="https://<account>.documents.azure.com:443/"
export AZURE_COSMOS_DATABASE_NAME="<database>"
export AZURE_COSMOS_CONTAINER_NAME="<container>"
```

2. Run the example:

```bash
uv run python samples/02-agents/context_providers/azure_cosmos/cosmos_history_provider.py
```
