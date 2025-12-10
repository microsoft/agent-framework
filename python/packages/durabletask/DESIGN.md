# Design: Durable Task Provider for Agent Framework

## Overview

This package, `agent-framework-durabletask`, provides a durability layer for the Microsoft Agent Framework using the `durabletask` Python SDK. It enables stateful, reliable, and distributed agent execution on any platform (Bring Your Own Platform), decoupling the agent's durability from the Azure Functions platform.

## Design Decision

**Selected Approach: Object-Oriented Wrappers with Symmetric Factory Pattern**

We will use a symmetric Object-Oriented design where both the Client (external) and Orchestrator (internal) expose a consistent interface for retrieving and interacting with durable agents.

## Core Philosophy

*   **Native `DurableEntity` Support**: We will leverage the `DurableEntity` support introduced in `durabletask` v1.0.0.
*   **Symmetric Factories**: `DurableAIAgentClient` (for external use) and `DurableAIAgentOrchestrator` (for internal use) both provide a `get_agent` method.
*   **Unified Interface**: `DurableAIAgent` serves as the common interface for executing agents, regardless of the context (Client vs Orchestration).
*   **Consistent Return Type**: `DurableAIAgent.run` always returns a `Task` (or compatible awaitable), ensuring consistent usage patterns.

## Architecture

### 1. Package Structure

```text
packages/durabletask/
├── pyproject.toml
├── README.md
├── agent_framework_durabletask/
│   ├── __init__.py
│   ├── _worker.py      # DurableAIAgentWorker
│   ├── _client.py      # DurableAIAgentClient
│   ├── _orchestrator.py # DurableAIAgentOrchestrator
│   ├── _entities.py    # AgentEntity implementation
│   ├── _models.py      # Data models (RunRequest, AgentResponse, etc.)
│   ├── _durable_agent_state.py # State schema (Ported from azurefunctions)
│   ├── _shim.py        # DurableAIAgent implementation
│   └── _utils.py       # Mixins and helpers
└── tests/
```

### 2. State Management (`_durable_agent_state.py`)

*   **Goal**: Maintain 100% schema compatibility with `agent-framework-azurefunctions`.
*   **Implementation**: Direct port of `packages/azurefunctions/agent_framework_azurefunctions/_durable_agent_state.py`.

### 3. The Agent Entity (`_entities.py`)

We will implement a class `AgentEntity` that inherits from `durabletask.entities.DurableEntity`.

**Important**: Due to the nature of the `durabletask` SDK, `DurableEntity` subclasses cannot have custom constructors. The SDK instantiates entities using a parameterless constructor. Therefore, we must use a **factory pattern** to inject the agent instance, similar to the approach used in `agent-framework-azurefunctions`.

```python
class AgentEntity(durabletask.entities.DurableEntity):
    """Durable entity that wraps an agent and maintains conversation state.
    
    Note: This class cannot have a custom __init__ due to durabletask SDK constraints.
    Use create_agent_entity() factory function to create instances with injected agents.
    """
    
    agent: AgentProtocol
    state: DurableAgentState

    async def run_agent(self, input_data: dict[str, Any]) -> dict[str, Any]:
        # 1. Deserialize Input
        request = RunRequest.from_dict(input_data)
        
        # 2. Update State (User Message)
        state_request = DurableAgentStateRequest.from_run_request(request)
        self.state.data.conversation_history.append(state_request)
        
        # 3. Rehydrate Chat History
        chat_messages = [
            m.to_chat_message()
            for entry in self.state.data.conversation_history
            for m in entry.messages
        ]
        
        # 4. Execute Agent
        response = await self.agent.run(messages=chat_messages, ...)
        
        # 5. Update State (Agent Response)
        state_response = DurableAgentStateResponse.from_run_response(
            request.correlation_id, response
        )
        self.state.data.conversation_history.append(state_response)
        
        # 6. Return Result (Serialized AgentRunResponse)
        return response.to_dict()

    def reset(self) -> None:
        self.state = DurableAgentState()


def create_agent_entity(agent: AgentProtocol) -> type[AgentEntity]:
    """Factory function to create an AgentEntity class with an injected agent.
    
    This factory pattern is required because DurableEntity subclasses cannot
    have custom constructors due to durabletask SDK constraints.
    
    Args:
        agent: The agent instance to inject into the entity
        
    Returns:
        A new AgentEntity class with the agent pre-configured
    """
    class ConfiguredAgentEntity(AgentEntity):
        def __init__(self):
            self.agent = agent
            self.state = DurableAgentState()
    
    return ConfiguredAgentEntity
```

### 4. The Worker Wrapper (`_worker.py`)

The `DurableAIAgentWorker` wraps an existing `durabletask` worker instance.

```python
class DurableAIAgentWorker:
    def __init__(self, worker: TaskHubGrpcWorker):
        self._worker = worker
        self._registered_agents: dict[str, AgentProtocol] = {}

    def add_agent(self, agent: AgentProtocol) -> None:
        """Registers an agent with the worker.
        
        Uses the factory pattern to create an AgentEntity class with the agent
        instance injected, then registers it with the durabletask worker.
        """
        # Store the agent reference
        self._registered_agents[agent.name] = agent
        
        # Create a configured entity class using the factory
        entity_class = create_agent_entity(agent)
        
        # Register the entity class with the worker
        # The worker.add_entity method takes a class or function
        self._worker.add_entity(entity_class)

    def start(self):
        """Start the worker to begin processing tasks."""
        self._worker.start()

    def stop(self):
        """Stop the worker gracefully."""
        self._worker.stop()
```

### 5. The Mixin (`_utils.py`)

```python
class GetDurableAgentMixin:
    """Mixin to provide get_agent interface."""
    
    def get_agent(self, agent_name: str) -> 'DurableAIAgent':
        raise NotImplementedError
```

### 6. The Client Wrapper (`_client.py`)

The `DurableAIAgentClient` is for external clients (e.g., FastAPI, CLI).

```python
class DurableAIAgentClient(GetDurableAgentMixin):
    def __init__(self, client: TaskHubGrpcClient):
        self._client = client

    async def get_agent(self, agent_name: str) -> 'DurableAIAgent':
        """Retrieves a DurableAIAgent shim.
        
        Validates existence by attempting to fetch entity state/metadata.
        """
        # Validation logic using self._client.get_entity(...)
        # ...
        return DurableAIAgent(self, agent_name)

    def run_agent(self, agent_name: str, message: str, **kwargs) -> 'Task':
        """Runs agent via signal + poll and returns a Task wrapper."""
        # Returns a ClientTask (wrapper around asyncio.Task)
        pass
```

### 7. The Orchestrator Wrapper (`_orchestrator.py`)

The `DurableAIAgentOrchestrator` is for use *inside* orchestrations.

```python
class DurableAIAgentOrchestrator(GetDurableAgentMixin):
    def __init__(self, context: OrchestrationContext):
        self._context = context

    def get_agent(self, agent_name: str) -> 'DurableAIAgent':
        """Retrieves a DurableAIAgent shim.
        
        Validation is deferred or performed via call_entity if needed.
        """
        return DurableAIAgent(self, agent_name)

    def run_agent(self, agent_name: str, message: str, **kwargs) -> 'Task':
        """Runs agent via call_entity and returns the Task."""
        # Returns the native durabletask.Task
        pass
```

### 8. The Durable Agent Shim (`_shim.py`)

The `DurableAIAgent` implements `AgentProtocol` but delegates execution to the provider.

```python
class DurableAIAgent(AgentProtocol):
    """A shim that delegates execution to the provider (Client or Orchestrator)."""
    
    def __init__(self, provider: GetDurableAgentMixin, name: str):
        self._provider = provider
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def run(self, message: str, **kwargs) -> 'Task':
        """Executes the agent.
        
        Returns:
            Task: A yieldable/awaitable task object.
        """
        return self._provider.run_agent(
            agent_name=self.name,
            message=message,
            **kwargs
        )
```

## Usage Experience

**Scenario A: Client Side**
```python
client = TaskHubGrpcClient(...)
agent_client = DurableAIAgentClient(client)
agent = await agent_client.get_agent("my_agent")

# Returns a Task-like object, so we await it
response = await agent.run("Hello")
```

**Scenario B: Orchestration Side**
```python
def orchestrator(context):
    agent_orch = DurableAIAgentOrchestrator(context)
    agent = agent_orch.get_agent("my_agent")

    # Returns a Task, so we yield it
    result = yield agent.run("Hello")
```

## Implementation Steps

1.  **Scaffold Package**: Create directory structure and `pyproject.toml`.
2.  **Port State Models**: Copy `_durable_agent_state.py` and `_models.py` (adapting imports).
3.  **Implement `AgentEntity`**: Create `_entities.py`.
4.  **Implement `DurableAIAgentWorker`**: Create `_worker.py`.
5.  **Implement `GetDurableAgentMixin`**: Create `_utils.py` (or `_mixins.py`).
6.  **Implement `DurableAIAgent`**: Create `_shim.py`.
7.  **Implement `DurableAIAgentClient`**: Create `_client.py`.
8.  **Implement `DurableAIAgentOrchestrator`**: Create `_orchestrator.py`.
9.  **Tests**: Add unit tests and integration tests.
