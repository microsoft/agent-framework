# Neo4j Memory Context Provider Examples

[Neo4j Agent Memory](https://github.com/neo4j-labs/agent-memory) is a graph-native memory system for AI agents that stores conversations, builds knowledge graphs from interactions, and lets agents learn from their own reasoning — all backed by Neo4j.

This is a **read-write memory provider** — it grows over time as the agent interacts with users. For read-only retrieval from an existing knowledge base, see the [Neo4j GraphRAG Provider](../neo4j_graphrag/README.md). For help choosing between the two, see the [Neo4j Context Providers overview](../neo4j/README.md).

## Examples

- **Basic memory**: Store conversations and recall context across sessions
- **Memory with tools**: Give the agent tools to search memory, remember preferences, and find entity connections in the knowledge graph

For a full runnable example, see the [retail assistant sample](https://github.com/neo4j-labs/agent-memory/tree/main/examples/microsoft_agent_retail_assistant).

## Installation

```bash
pip install neo4j-agent-memory[microsoft-agent]
```

## Prerequisites

### Required Resources

1. **Neo4j database** (empty — the memory provider creates its own schema)
   - [Neo4j AuraDB](https://neo4j.com/cloud/auradb/) (managed) or self-hosted
   - No pre-existing indexes or data required
2. **Azure AI Foundry project** with a model deployment (for the agent's chat model)
3. **Embedding model** — supports OpenAI, Azure AI, or other providers for semantic search over memories

### Authentication

- Neo4j: Username/password authentication
- Azure AI: Uses `DefaultAzureCredential`

Run `az login` for Azure authentication.

## Configuration

### Environment Variables

**Neo4j:**
- `NEO4J_URI`: Neo4j connection URI (e.g., `neo4j+s://your-instance.databases.neo4j.io`)
- `NEO4J_USERNAME`: Database username
- `NEO4J_PASSWORD`: Database password

**Azure AI:**
- `AZURE_AI_PROJECT_ENDPOINT`: Azure AI Foundry project endpoint
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: Chat model deployment name (e.g., `gpt-4o`)

**Embeddings (pick one):**
- `OPENAI_API_KEY`: For OpenAI embeddings
- Or configure Azure AI embeddings via `AZURE_AI_PROJECT_ENDPOINT`

## Code Example

```python
import os

from agent_framework import Agent
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential
from neo4j_agent_memory import MemoryClient, MemorySettings
from neo4j_agent_memory.integrations.microsoft_agent import (
    Neo4jMicrosoftMemory,
    create_memory_tools,
)

settings = MemorySettings(...)
memory_client = MemoryClient(settings)

async with memory_client:
    memory = Neo4jMicrosoftMemory.from_memory_client(
        memory_client=memory_client,
        session_id="user-123",
    )
    tools = create_memory_tools(memory)

    async with (
        AzureAIClient(
            credential=AzureCliCredential(),
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        ) as client,
        Agent(
            client=client,
            name="MemoryAssistant",
            instructions="You are a helpful assistant with persistent memory.",
            tools=tools,
            context_providers=[memory.context_provider],
        ) as agent,
    ):
        session = agent.create_session()
        response = await agent.run(
            "Remember that I prefer window seats on flights.", session=session
        )
        print(response.text)
```

`create_memory_tools()` returns callable `FunctionTool` instances that the framework auto-invokes during streaming — no manual tool dispatch is needed. The core tools are: `search_memory`, `remember_preference`, `recall_preferences`, `search_knowledge`, `remember_fact`, and `find_similar_tasks`. Optional GDS graph algorithm tools (`find_connection_path`, `find_similar_items`, `find_important_entities`) are included when a `GDSConfig` is provided.

## Additional Resources

- [Neo4j Agent Memory Repository](https://github.com/neo4j-labs/agent-memory)
- [Neo4j AuraDB](https://neo4j.com/cloud/auradb/)
