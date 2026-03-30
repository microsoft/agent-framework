# Azure Cosmos DB Package Samples

This folder contains samples for `agent-framework-azure-cosmos`.

| File | Description |
| --- | --- |
| [`cosmos_history_provider.py`](cosmos_history_provider.py) | Demonstrates an Agent using `CosmosHistoryProvider` with `AzureOpenAIResponsesClient` (project endpoint), provider-configured container name, and `session_id` partitioning. |

## Prerequisites

- `AZURE_COSMOS_ENDPOINT`
- `AZURE_COSMOS_DATABASE_NAME`
- `AZURE_COSMOS_CONTAINER_NAME`
- `AZURE_COSMOS_KEY` (or equivalent credential flow)

## Run

```bash
uv run --directory packages/azure-cosmos python samples/cosmos_history_provider.py
```
