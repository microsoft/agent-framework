# Azure Cosmos DB Package Samples

This folder contains samples for `agent-framework-azure-cosmos`.

## History Provider Samples

Demonstrate conversation persistence using `CosmosHistoryProvider`.

| File | Description |
| --- | --- |
| [`history_provider/cosmos_history_basic.py`](history_provider/cosmos_history_basic.py) | Basic multi-turn conversation using `CosmosHistoryProvider` with `AzureOpenAIResponsesClient`, provider-configured container name, and `session_id` partitioning. |
| [`history_provider/cosmos_history_conversation_persistence.py`](history_provider/cosmos_history_conversation_persistence.py) | Persist and resume conversations across application restarts — serialize session state, create new provider/agent instances, and continue from Cosmos DB history. |
| [`history_provider/cosmos_history_messages.py`](history_provider/cosmos_history_messages.py) | Direct message history operations — retrieve stored messages as a transcript, clear session history, and verify data deletion. |
| [`history_provider/cosmos_history_sessions.py`](history_provider/cosmos_history_sessions.py) | Multi-session and multi-tenant management — per-tenant session isolation, `list_sessions()` to enumerate, switch between sessions, and resume specific conversations. |

## Checkpoint Storage Samples

Demonstrate workflow pause/resume using `CosmosCheckpointStorage`.

| File | Description |
| --- | --- |
| [`checkpoint_storage/cosmos_checkpoint_workflow.py`](checkpoint_storage/cosmos_checkpoint_workflow.py) | Workflow checkpoint storage with Cosmos DB — pause and resume workflows across restarts using `CosmosCheckpointStorage`, with support for key-based and managed identity auth. |
| [`checkpoint_storage/cosmos_checkpoint_foundry.py`](checkpoint_storage/cosmos_checkpoint_foundry.py) | End-to-end Azure AI Foundry + Cosmos DB checkpointing — multi-agent workflow using `AzureOpenAIResponsesClient` with `CosmosCheckpointStorage` for durable pause/resume. |

## Combined Sample

| File | Description |
| --- | --- |
| [`cosmos_e2e_foundry.py`](cosmos_e2e_foundry.py) | Both `CosmosHistoryProvider` and `CosmosCheckpointStorage` in a single Azure AI Foundry agent app — the recommended production pattern for fully durable agent workflows. |

## Prerequisites

- `AZURE_COSMOS_ENDPOINT`
- `AZURE_COSMOS_DATABASE_NAME`
- `AZURE_COSMOS_KEY` (or equivalent credential flow)

For Foundry samples, also set:
- `AZURE_AI_PROJECT_ENDPOINT`
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`

## Run

```bash
# History provider samples
uv run --directory packages/azure-cosmos python samples/history_provider/cosmos_history_basic.py
uv run --directory packages/azure-cosmos python samples/history_provider/cosmos_history_conversation_persistence.py
uv run --directory packages/azure-cosmos python samples/history_provider/cosmos_history_messages.py
uv run --directory packages/azure-cosmos python samples/history_provider/cosmos_history_sessions.py

# Checkpoint storage samples
uv run --directory packages/azure-cosmos python samples/checkpoint_storage/cosmos_checkpoint_workflow.py
uv run --directory packages/azure-cosmos python samples/checkpoint_storage/cosmos_checkpoint_foundry.py

# Combined sample
uv run --directory packages/azure-cosmos python samples/cosmos_e2e_foundry.py
```
