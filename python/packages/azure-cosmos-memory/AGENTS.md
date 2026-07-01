# Azure Cosmos DB Memory Package (agent-framework-azure-cosmos-memory)

Long-term semantic memory for agents, backed by Azure Cosmos DB via the
[Azure Cosmos DB Agent Memory Toolkit](https://github.com/AzureCosmosDB/AgentMemoryToolkit).

## Main Classes

- **`CosmosMemoryContextProvider`** - Context provider that integrates Cosmos DB-backed
  semantic memory (facts, procedural/episodic memories, and user/thread summaries) into agents.

## Usage

```python
from azure.identity.aio import DefaultAzureCredential
from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider

provider = CosmosMemoryContextProvider(
    cosmos_endpoint="https://<account>.documents.azure.com:443/",
    cosmos_database="ai_memory",
    foundry_endpoint="https://<project>.services.ai.azure.com",
    credential=DefaultAzureCredential(),
)
```

## Import Path

```python
from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider
```

## Notes

- Requires the `azure-cosmos-agent-memory` toolkit and an AI Foundry endpoint (used for both
  embeddings and fact extraction).
- Set a stable `user_id` in `state["user_id"]` or `session.state["user_id"]` for long-term,
  cross-session memory. Without it, memory scopes to the ephemeral session id and the provider
  logs a one-time warning.
- Background fact extraction runs out-of-band after each turn. Call `provider.flush()` before
  shutdown so in-flight extraction completes before the client closes.
- See `README.md` for full configuration, authentication, and processor-tuning options.
