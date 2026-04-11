# Azure Cosmos DB Package Samples

This package keeps a local sample for the Cosmos context provider.

## Package-local sample

| File | Description |
| --- | --- |
| [`cosmos_context_provider.py`](cosmos_context_provider.py) | Demonstrates an Agent using `AzureCosmosContextProvider` for context injection from an existing Cosmos knowledge container, using `default_search_mode=CosmosContextSearchMode.FULL_TEXT` for the normal agent flow and writing request/response messages back into that same container. |

## Other Azure Cosmos samples

- History provider samples live under `python/samples/02-agents/conversations/`
- Workflow checkpoint storage samples live under `python/samples/03-workflows/checkpoint/`

## Prerequisites

- `AZURE_COSMOS_ENDPOINT`
- `AZURE_COSMOS_DATABASE_NAME`
- `AZURE_COSMOS_CONTAINER_NAME`
- `AZURE_COSMOS_KEY` (or equivalent credential flow)

For `cosmos_context_provider.py`, the Cosmos account, database, and container must already exist and the container should already contain documents with at least a `content` or `text` field. If you want to switch the provider to vector or hybrid retrieval, the application owner is responsible for making sure the container has the required Cosmos vector/full-text/hybrid indexing policies in place. Normal agent runs use the provider defaults configured on the constructor, while advanced callers can override those defaults for a single run through `before_run(..., search_mode=..., weights=..., top_k=..., scan_limit=..., partition_key=...)`.

## Run

```bash
uv run --directory packages/azure-cosmos python samples/cosmos_context_provider.py
```
