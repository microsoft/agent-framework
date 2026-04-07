# Azure Cosmos DB Package Samples

This folder contains samples for `agent-framework-azure-cosmos`.

| File | Description |
| --- | --- |
| [`cosmos_history_provider.py`](cosmos_history_provider.py) | Demonstrates an Agent using `CosmosHistoryProvider` with `AzureOpenAIResponsesClient` (project endpoint), provider-configured container name, and `session_id` partitioning. |
| [`cosmos_context_provider.py`](cosmos_context_provider.py) | Demonstrates an Agent using `AzureCosmosContextProvider` for context injection from an existing Cosmos knowledge container, using `default_search_mode=CosmosContextSearchMode.FULL_TEXT` for the normal agent flow and always writing request/response messages back into that same container. |

## Prerequisites

- `AZURE_COSMOS_ENDPOINT`
- `AZURE_COSMOS_DATABASE_NAME`
- `AZURE_COSMOS_CONTAINER_NAME`
- `AZURE_COSMOS_KEY` (or equivalent credential flow)

For `cosmos_context_provider.py`, the Cosmos account, database, and container must already exist and the container should already contain documents with at least a `content` or `text` field. If you want to switch the provider to vector or hybrid retrieval, the application owner is responsible for making sure the container has the required Cosmos vector/full-text/hybrid indexing policies in place. Normal agent runs use the provider defaults configured on the constructor, while advanced callers can override those defaults for a single run through `before_run(..., search_mode=..., weights=..., top_k=..., scan_limit=..., partition_key=...)`.

## Run

```bash
uv run --directory packages/azure-cosmos python samples/cosmos_history_provider.py
uv run --directory packages/azure-cosmos python samples/cosmos_context_provider.py
```
