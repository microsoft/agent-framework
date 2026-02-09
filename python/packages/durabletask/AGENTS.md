# Durable Task Package (agent-framework-durabletask)

Durable execution support for long-running agent workflows using Azure Durable Functions.

## Main Classes

### Client Side

- **`DurableAIAgentClient`** - Client for invoking durable agents
- **`DurableAIAgent`** - Shim for creating durable agents

### Worker Side

- **`DurableAIAgentWorker`** - Worker that executes durable agent tasks
- **`DurableAgentExecutor`** - Executes agent logic within durable context
- **`AgentEntity`** - Durable entity for agent state management

### State Management

- **`DurableAgentState`** - State container for durable agents
- **`DurableAgentThread`** - Thread management for durable agents
- **`DurableAIAgentOrchestrationContext`** - Orchestration context

### Callbacks

- **`AgentCallbackContext`** - Context for agent callbacks
- **`AgentResponseCallbackProtocol`** - Protocol for response callbacks

## Usage

```python
from agent_framework_durabletask import DurableAIAgentClient, DurableAIAgentWorker

# Client side
client = DurableAIAgentClient(endpoint="https://your-functions.azurewebsites.net")
response = await client.run("Hello")

# Worker side
worker = DurableAIAgentWorker(agent=my_agent)
```

## Import Path

```python
from agent_framework_durabletask import DurableAIAgentClient, DurableAIAgentWorker
```
