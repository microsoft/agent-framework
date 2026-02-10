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
from durabletask.client import TaskHubGrpcClient
from durabletask.worker import TaskHubGrpcWorker
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_durabletask import DurableAIAgentClient, DurableAIAgentWorker

# Client side
dt_client = TaskHubGrpcClient(host_address="localhost:4001")
agent_client = DurableAIAgentClient(dt_client)
agent = agent_client.get_agent("assistant")
response = agent.run("Hello, how are you?")
print(response.text)

# Worker side
dt_worker = TaskHubGrpcWorker(host_address="localhost:4001")
agent_worker = DurableAIAgentWorker(dt_worker)

# Create a chat client for the agent
chat_client = AzureOpenAIChatClient()
my_agent = ChatAgent(chat_client=chat_client, name="assistant")
agent_worker.add_agent(my_agent)

dt_worker.start()
```

## Import Path

```python
from agent_framework_durabletask import DurableAIAgentClient, DurableAIAgentWorker
```
