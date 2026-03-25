# Azure Cosmos DB Package Samples

This folder contains samples for `agent-framework-azure-cosmos`.

| File | Description |
| --- | --- |
| [`cosmos_history_provider.py`](cosmos_history_provider.py) | Demonstrates an Agent using `CosmosHistoryProvider` with `AzureOpenAIResponsesClient` (project endpoint), provider-configured container name, and `session_id` partitioning. |
| [`cosmos_workflow_checkpointing.py`](cosmos_workflow_checkpointing.py) | Workflow checkpoint storage with Cosmos DB — pause and resume workflows across restarts using `CosmosCheckpointStorage`, with support for key-based and managed identity auth. |
| [`cosmos_workflow_checkpointing_foundry.py`](cosmos_workflow_checkpointing_foundry.py) | End-to-end Azure AI Foundry + Cosmos DB checkpointing — multi-agent workflow using `AzureOpenAIResponsesClient` with `CosmosCheckpointStorage` for durable pause/resume. |

## Prerequisites

- `AZURE_COSMOS_ENDPOINT`
- `AZURE_COSMOS_DATABASE_NAME`
- `AZURE_COSMOS_CONTAINER_NAME`
- `AZURE_COSMOS_KEY` (or equivalent credential flow)

## Run

```bash
uv run --directory packages/azure-cosmos python samples/cosmos_history_provider.py
uv run --directory packages/azure-cosmos python samples/cosmos_workflow_checkpointing.py
uv run --directory packages/azure-cosmos python samples/cosmos_workflow_checkpointing_foundry.py
```
