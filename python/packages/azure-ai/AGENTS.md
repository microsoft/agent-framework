# Azure AI Package (agent-framework-azure-ai)

Integration with Azure AI Foundry for persistent agents and project-based agent management.

## Main Classes

- **`AzureAIAgentClient`** - Chat client for Azure AI Agents (persistent agents with threads)
- **`AzureAIClient`** - Client for Azure AI Foundry project-based agents
- **`AzureAIAgentsProvider`** - Provider for listing/managing Azure AI agents
- **`AzureAIProjectAgentProvider`** - Provider for project-scoped agent management
- **`AzureAISettings`** - Pydantic settings for Azure AI configuration
- **`AzureAIAgentOptions`** / **`AzureAIProjectAgentOptions`** - Options TypedDicts

## Usage

```python
from agent_framework.azure import AzureAIAgentClient

client = AzureAIAgentClient(
    endpoint="https://your-project.services.ai.azure.com",
    agent_id="your-agent-id",
)
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework.azure import AzureAIAgentClient, AzureAIClient
# or directly:
from agent_framework_azure_ai import AzureAIAgentClient
```
