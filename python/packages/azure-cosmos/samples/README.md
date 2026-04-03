# Azure Cosmos DB Package Samples

This folder contains samples for `agent-framework-azure-cosmos`.

| File | Description |
| --- | --- |
| [`cosmos_history_provider.py`](cosmos_history_provider.py) | Demonstrates an Agent using `CosmosHistoryProvider` with `AzureOpenAIResponsesClient` (project endpoint), provider-configured container name, and `session_id` partitioning. |
| [`cosmos_context_provider.py`](cosmos_context_provider.py) | Demonstrates an Agent using `AzureCosmosContextProvider` for context injection from an existing Cosmos knowledge container, with optional writeback support available through provider configuration. |

## Prerequisites

- `AZURE_COSMOS_ENDPOINT`
- `AZURE_COSMOS_DATABASE_NAME`
- `AZURE_COSMOS_CONTAINER_NAME`
- `AZURE_COSMOS_KEY` (or equivalent credential flow)

For `cosmos_context_provider.py`, the container should already contain documents with at least a `content` or `text` field.

## Run

```bash
uv run --directory packages/azure-cosmos python samples/cosmos_history_provider.py
uv run --directory packages/azure-cosmos python samples/cosmos_context_provider.py
```
