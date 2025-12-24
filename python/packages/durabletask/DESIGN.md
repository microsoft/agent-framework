# Design: Durable Task Provider for Agent Framework

## Overview

This package, `agent-framework-durabletask`, provides a durability layer for the Microsoft Agent Framework using the `durabletask` Python SDK. It enables stateful, reliable, and distributed agent execution on any platform (Bring Your Own Platform), decoupling the agent's durability from the Azure Functions platform.

## Design Decision

**Selected Approach: Object-Oriented Wrappers with Symmetric Factory Pattern + Strategy Pattern for Execution**

We will use a symmetric Object-Oriented design where both the Client (external) and Orchestrator (internal) expose a consistent interface for retrieving and interacting with durable agents. Execution logic is delegated to dedicated provider strategies.

## Core Philosophy

*   **Native `DurableEntity` Support**: We will leverage the `DurableEntity` support introduced in `durabletask` v1.0.0.
*   **Symmetric Factories**: `DurableAIAgentClient` (for external use) and `DurableAIAgentOrchestrationContext` (for internal use) both provide a `get_agent` method.
*   **Unified Interface**: `DurableAIAgent` serves as the common interface for executing agents, regardless of the context (Client vs Orchestration).
*   **Strategy Pattern for Execution**: Execution logic is encapsulated in `DurableAgentExecutor` implementations, allowing flexible delegation while keeping the public API clean.
*   **Consistent Return Type**: `DurableAIAgent.run` returns context-appropriate objects (awaitable for Client, yieldable Task for Orchestrator), ensuring consistent usage patterns.

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
│   ├── _orchestration_context.py # DurableAIAgentOrchestrationContext
│   ├── _executors.py   # DurableAgentExecutor ABC and implementations
│   ├── _entities.py    # AgentEntity implementation
│   ├── _models.py      # Data models (RunRequest, AgentResponse, etc.)
│   ├── _durable_agent_state.py # State schema (Ported from azurefunctions)
│   └── _shim.py        # DurableAIAgent and DurableAgentProvider ABC
└── tests/
```

### 2. State Management (`_durable_agent_state.py`)

**Important**: This will be the state maintained in the durable entities for both `durabletask` and `azurefunctions` package. 

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

### 5. The Shim and Provider ABC (`_shim.py`)

The `_shim.py` module contains two key abstractions:

1. **`DurableAgentProvider` ABC**: Defines the contract for constructing durable agent proxies. Implemented by context-specific wrappers (client/orchestration) to provide a consistent `get_agent` entry point.

2. **`DurableAIAgent`**: The agent shim that delegates execution to an executor strategy.

```python
from abc import ABC, abstractmethod

class DurableAgentProvider(ABC):
    """Abstract provider for constructing durable agent proxies.
    
    Implemented by context-specific wrappers (client/orchestration) to return a
    DurableAIAgent shim backed by their respective DurableAgentExecutor
    implementation, ensuring a consistent get_agent entry point regardless of
    execution context.
    """
    
    @abstractmethod
    def get_agent(self, agent_name: str) -> DurableAIAgent:
        """Retrieve a DurableAIAgent shim for the specified agent."""
        raise NotImplementedError("Subclasses must implement get_agent()")


class DurableAIAgent(AgentProtocol):
    """A durable agent proxy that delegates execution to an executor.
    
    This class implements AgentProtocol but doesn't contain any agent logic itself.
    Instead, it serves as a consistent interface that delegates to the underlying
    executor, which can be either ClientAgentExecutor or OrchestrationAgentExecutor.
    """
    
    def __init__(self, executor: DurableAgentExecutor, name: str, *, agent_id: str | None = None):
        self._executor = executor
        self._name = name
        self._id = agent_id if agent_id is not None else name
    
    def run(self, messages: ..., **kwargs) -> Any:
        """Execute the agent via the injected executor."""
        message_str = self._normalize_messages(messages)
        return self._executor.run_durable_agent(
            agent_name=self._name,
            message=message_str,
            thread=kwargs.get('thread'),
            response_format=kwargs.get('response_format'),
            **kwargs
        )
```

### 6. The Executor Strategy (`_executors.py`)

We introduce dedicated "Executor" classes to handle execution logic using the Strategy Pattern. These are internal execution strategies that are injected into the `DurableAIAgent` shim. This ensures the public API of the Client and Orchestration Context remains clean, while allowing the Shim to be reused across different environments.

```python
from abc import ABC, abstractmethod
from typing import Any
from agent_framework import AgentThread
from pydantic import BaseModel

class DurableAgentExecutor(ABC):
    """Abstract base class for durable agent execution strategies."""

    @abstractmethod
    def run_durable_agent(
        self,
        agent_name: str,
        message: str,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute the durable agent.
        
        Returns:
            Any: Either an awaitable AgentRunResponse (Client) or a yieldable Task (Orchestrator).
        """
        raise NotImplementedError

    @abstractmethod
    def get_new_thread(self, agent_name: str, **kwargs: Any) -> AgentThread:
        """Create a new thread appropriate for the context."""
        raise NotImplementedError


class ClientAgentExecutor(DurableAgentExecutor):
    """Execution strategy for external clients (async)."""
    
    def __init__(self, client: 'TaskHubGrpcClient'):
        self._client = client

    async def run_durable_agent(
        self,
        agent_name: str,
        message: str,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> Any:
        # Implementation using self._client
        # Returns an awaitable AgentRunResponse
        raise NotImplementedError("ClientAgentExecutor.run_durable_agent is not yet implemented")

    def get_new_thread(self, agent_name: str, **kwargs: Any) -> AgentThread:
        # Implementation for client context
        return AgentThread(**kwargs)


class OrchestrationAgentExecutor(DurableAgentExecutor):
    """Execution strategy for orchestrations (sync/yield)."""
    
    def __init__(self, context: 'OrchestrationContext'):
        self._context = context

    def run_durable_agent(
        self,
        agent_name: str,
        message: str,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> Any:
        # Implementation using self._context
        # Returns a yieldable Task
        raise NotImplementedError("OrchestrationAgentExecutor.run_durable_agent is not yet implemented")

    def get_new_thread(self, agent_name: str, **kwargs: Any) -> AgentThread:
        # Implementation for orchestration context
        return AgentThread(**kwargs)
```

**Benefits of the Strategy Pattern:**

1.  **Strong Contract**: ABC enforces implementation of required methods.
2.  **Encapsulation**: Execution logic is hidden in provider classes.
3.  **Flexibility**: Easy to add new providers (e.g., for Azure Functions).
4.  **Separation of Concerns**: Client/Context wrappers focus on being factories/adapters.
5.  **Reusability**: The shim can be reused across different environments without modification.

### 7. The Client Wrapper (`_client.py`)

The `DurableAIAgentClient` is for external clients (e.g., FastAPI, CLI). It implements `DurableAgentProvider` to provide the `get_agent` factory method, and instantiates the `ClientAgentExecutor` to inject into the `DurableAIAgent`.

```python
from ._executors import ClientAgentExecutor
from ._shim import DurableAgentProvider, DurableAIAgent

class DurableAIAgentClient(DurableAgentProvider):
    def __init__(self, client: TaskHubGrpcClient):
        self._client = client

    def get_agent(self, agent_name: str) -> DurableAIAgent:
        """Retrieves a DurableAIAgent shim.
        
        Validates existence by attempting to fetch entity state/metadata.
        """
        # Validation logic using self._client.get_entity(...)
        # ...
        executor = ClientAgentExecutor(self._client)
        return DurableAIAgent(executor, agent_name)
```

### 8. The Orchestration Context Wrapper (`_orchestration_context.py`)

The `DurableAIAgentOrchestrationContext` is for use *inside* orchestrations to get access to agents that were registered in the workers. It implements `DurableAgentProvider` to provide the `get_agent` factory method, and instantiates the `OrchestrationAgentExecutor`.

```python
from ._executors import OrchestrationAgentExecutor
from ._shim import DurableAgentProvider, DurableAIAgent

class DurableAIAgentOrchestrationContext(DurableAgentProvider):
    def __init__(self, context: OrchestrationContext):
        self._context = context

    def get_agent(self, agent_name: str) -> DurableAIAgent:
        """Retrieves a DurableAIAgent shim.
        
        Validation is deferred or performed via call_entity if needed.
        """
        executor = OrchestrationAgentExecutor(self._context)
        return DurableAIAgent(executor, agent_name)
```

## Usage Experience

**Scenario A: Worker Side**
```python
# 1. Define your agent
# The agent can be any implementation of AgentProtocol.
# For example, a standard Agent with a model and instructions.
my_agent = Agent(
    name="my_agent", 
    instructions="You are a helpful assistant.",
    model=openai_model
)

# 2. Create the worker and the agent worker wrapper
with DurableTaskSchedulerWorker(...) as worker:
    
    agent_worker = DurableAIAgentWorker(worker)
    
    # 3. Register the agent
    agent_worker.add_agent(my_agent)
    
    # 4. Start the worker
    worker.start()
    
    # ... keep running ...
```

**Scenario B: Client Side**
```python
# 1. Configure the Durable Task client
client = DurableTaskSchedulerClient(...)

# 2. Create the Agent Client wrapper
agent_client = DurableAIAgentClient(client)

# 3. Get a reference to the agent
agent = await agent_client.get_agent("my_agent")

# 4. Run the agent
# The returned object is designed to be compatible with both `await` (Client) 
# and `yield` (Orchestrator). Implementation details on this unified return type will follow.
response = await agent.run("Hello")
```

**Scenario C: Orchestration Side**
```python
def orchestrator(context: OrchestrationContext):
    # 1. Create the Agent Orchestration Context
    agent_orch = DurableAIAgentOrchestrationContext(context)
    
    # 2. Get a reference to the agent
    agent = agent_orch.get_agent("my_agent")

    # 3. Run the agent (returns a Task, so we yield it)
    result = yield agent.run("Hello")
    
    return result
```

## Additional Styles Considered

### Inheritance Pattern for worker and client (like `DurableAIAgentWorker`, `DurableAIAgentClient`, etc)

We investigated inheriting `DurableAIAgentWorker` directly from `TaskHubGrpcWorker` (or `DurableTaskSchedulerWorker`) to provide a unified API where the agent worker *is* a durable task worker (and similarly the client).

**Why we chose Composition over Inheritance:**

1.  **Initialization Divergence:** The `durabletask` package has two distinct worker classes with incompatible `__init__` signatures:
    *   `TaskHubGrpcWorker`: Requires `host_address`, `metadata`, etc.
    *   `DurableTaskSchedulerWorker`: Requires `host_address`, `taskhub`, `token_credential`, etc.
    
    To support both via inheritance, we would need to maintain two separate classes (e.g., `DurableAIAgentGrpcWorker` and `DurableAIAgentSchedulerWorker`) or use a complex Mixin approach. This increases the API surface area and maintenance burden.

2.  **Encapsulation:** The logic for Azure Managed DTS (authentication, routing) is currently encapsulated in an internal interceptor class within `durabletask`. Without changes to the upstream package to expose this logic, we cannot create a single "Universal" worker class that inherits from the base worker but supports Azure features.

3.  **Flexibility:** The Composition pattern allows `DurableAIAgentWorker` to accept *any* instance of a worker that satisfies the required interface. This makes it forward-compatible with future worker implementations or custom subclasses without requiring code changes in our package.

4.  **Simplicity:** While Composition requires a two-step setup (instantiate worker, then wrap it), it keeps the `agent-framework-durabletask` package simple, focused, and loosely coupled from the implementation details of the underlying `durabletask` workers.

## Extension Point: Azure Functions Integration

The Strategy Pattern design allows for easy integration with Azure Functions. The `azurefunctions` package can define its own `AzureFunctionsAgentExecutor` in `packages/azurefunctions/agent_framework_azurefunctions/_executors.py`.

```python
from agent_framework_durabletask._executors import DurableAgentExecutor

class AzureFunctionsAgentExecutor(DurableAgentExecutor):
    """Execution strategy for Azure Functions orchestrations."""
    
    def __init__(self, context: DurableOrchestrationContext):
        self._context = context

    def run_durable_agent(
        self,
        agent_name: str,
        message: str,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> Any:
        # Implementation using Azure Functions context
        # Returns AgentTask
        ...

    def get_new_thread(self, agent_name: str, **kwargs: Any) -> AgentThread:
        # Implementation for Azure Functions context
        ...
```

Then `packages/azurefunctions/agent_framework_azurefunctions/_orchestration.py` implements `DurableAgentProvider` and uses this executor when creating the agent, ensuring consistent behavior across platforms while accommodating Azure Functions-specific features.