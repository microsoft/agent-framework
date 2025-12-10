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
│   ├── _shim.py        # DurableAIAgent implementation (will be ported from azurefunctions)
│   └── _utils.py       # Mixins and helpers
└── tests/
```

### 2. State Management (`_durable_agent_state.py`)

*   **Goal**: Maintain 100% schema compatibility with `agent-framework-azurefunctions`.
*   **Implementation**: Direct port of `packages/azurefunctions/agent_framework_azurefunctions/_durable_agent_state.py`.

### 3. The Agent Entity (`_entities.py`)

We will implement a class `AgentEntity` that inherits from `durabletask.entities.DurableEntity`.

**Important**: This will be ported from `azurefunctions` package too but with slight modifications, details TBD.

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

The `DurableAIAgent` implements `AgentProtocol` but delegates execution to the provider. This will be ported from `azurefunctions` package and updated accordingly.

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