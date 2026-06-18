---
status: proposed
contact: dmytrostruk
date: 2025-12-12
deciders: dmytrostruk, markwallace-microsoft, eavanvalkenburg, giles17
---

# Create/Get Agent API

## Context and Problem Statement

There is a misalignment between the create/get agent API in the .NET and Python implementations.

In .NET, the `CreateAIAgent` method can create either a local instance of an agent or a remote instance if the backend provider supports it. For remote agents, once the agent is created, you can retrieve an existing remote agent by using the `GetAIAgent` method. If a backend provider doesn't support remote agents, `CreateAIAgent` just initializes a new local agent instance and `GetAIAgent` is not available. There is also a `BuildAIAgent` method, which is an extension for the `ChatClientBuilder` class from `Microsoft.Extensions.AI`. It builds pipelines of `IChatClient` instances with an `IServiceProvider`. This functionality does not exist in Python, so `BuildAIAgent` is out of scope.

In Python, there is only one `create_agent` method, which always creates a local instance of the agent. If the backend provider supports remote agents, the remote agent is created only on the first `agent.run()` invocation.

Below is a short summary of different providers and their APIs in .NET:

| Package | Method | Behavior | Python support |
|---|---|---|---|
| Microsoft.Agents.AI | `CreateAIAgent` (based on `IChatClient`) | Creates a local instance of `ChatClientAgent`. | Yes (`create_agent` in `BaseChatClient`). |
| Microsoft.Agents.AI.Anthropic | `CreateAIAgent` (based on `IBetaService` and `IAnthropicClient`) | Creates a local instance of `ChatClientAgent`. | Yes (`AnthropicClient` inherits `BaseChatClient`, which exposes `create_agent`). |
| Microsoft.Agents.AI.AzureAI (V2) | `GetAIAgent` (based on `AIProjectClient` with `AgentReference`) | Creates a local instance of `ChatClientAgent`. | Partial (Python uses `create_agent` from `BaseChatClient`). |
| Microsoft.Agents.AI.AzureAI (V2) | `GetAIAgent`/`GetAIAgentAsync` (with `Name`/`ChatClientAgentOptions`) | Fetches `AgentRecord` via HTTP, then creates a local `ChatClientAgent` instance. | No |
| Microsoft.Agents.AI.AzureAI (V2) | `CreateAIAgent`/`CreateAIAgentAsync` (based on `AIProjectClient`) | Creates a remote agent first, then wraps it into a local `ChatClientAgent` instance. | No |
| Microsoft.Agents.AI.AzureAI.Persistent (V1) | `GetAIAgent` (based on `PersistentAgentsClient` with `PersistentAgent`) | Creates a local instance of `ChatClientAgent`. | Partial (Python uses `create_agent` from `BaseChatClient`). |
| Microsoft.Agents.AI.AzureAI.Persistent (V1) | `GetAIAgent`/`GetAIAgentAsync` (with `AgentId`) | Fetches `PersistentAgent` via HTTP, then creates a local `ChatClientAgent` instance. | No |
| Microsoft.Agents.AI.AzureAI.Persistent (V1) | `CreateAIAgent`/`CreateAIAgentAsync` | Creates a remote agent first, then wraps it into a local `ChatClientAgent` instance. | No |
| Microsoft.Agents.AI.OpenAI | `GetAIAgent` (based on `AssistantClient` with `Assistant`) | Creates a local instance of `ChatClientAgent`. | Partial (Python uses `create_agent` from `BaseChatClient`). |
| Microsoft.Agents.AI.OpenAI | `GetAIAgent`/`GetAIAgentAsync` (with `AgentId`) | Fetches `Assistant` via HTTP, then creates a local `ChatClientAgent` instance. | No |
| Microsoft.Agents.AI.OpenAI | `CreateAIAgent`/`CreateAIAgentAsync` (based on `AssistantClient`) | Creates a remote agent first, then wraps it into a local `ChatClientAgent` instance. | No |
| Microsoft.Agents.AI.OpenAI | `CreateAIAgent` (based on `ChatClient`) | Creates a local instance of `ChatClientAgent`. | Yes (`create_agent` in `BaseChatClient`). |
| Microsoft.Agents.AI.OpenAI | `CreateAIAgent` (based on `OpenAIResponseClient`) | Creates a local instance of `ChatClientAgent`. | Yes (`create_agent` in `BaseChatClient`). |

Another difference between Python and .NET implementation is that in .NET `CreateAIAgent`/`GetAIAgent` methods are implemented as extension methods based on underlying SDK client, like `AIProjectClient` from Azure AI or `AssistantClient` from OpenAI:

```csharp
// Definition
public static ChatClientAgent CreateAIAgent(
    this AIProjectClient aiProjectClient,
    string name,
    string model,
    string instructions,
    string? description = null,
    IList<AITool>? tools = null,
    Func<IChatClient, IChatClient>? clientFactory = null,
    IServiceProvider? services = null,
    CancellationToken cancellationToken = default)
{ }

// Usage
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential()); // Initialization of underlying SDK client

var newAgent = await aiProjectClient.CreateAIAgentAsync(name: AgentName, model: deploymentName, instructions: AgentInstructions, tools: [tool]); // ChatClientAgent creation from underlying SDK client

// Alternative usage (same as extension method, just explicit syntax)
var newAgent = await AzureAIProjectChatClientExtensions.CreateAIAgentAsync(
    aiProjectClient,
    name: AgentName,
    model: deploymentName,
    instructions: AgentInstructions,
    tools: [tool]);
```

Python doesn't support extension methods. Currently `create_agent` method is defined on `BaseChatClient`, but this method only creates a local instance of `ChatAgent` and it can't create remote agents for providers that support it for a couple of reasons:

- It's defined as non-async.
- `BaseChatClient` implementation is stateful for providers like Azure AI or OpenAI Assistants. The implementation stores agent/assistant metadata like `AgentId` and `AgentName`, so currently it's not possible to create different instances of `ChatAgent` from a single `BaseChatClient` in case if the implementation is stateful.

## Decision Drivers

- API should be aligned between .NET and Python.
- API should be intuitive and consistent between backend providers in .NET and Python.

## Considered Options

Add missing implementations on the Python side. This should include the following:

### agent-framework-azure-ai (both V1 and V2)

- Add a `get_agent` method that accepts an underlying SDK agent instance and creates a local instance of `ChatAgent`.
- Add a `get_agent` method that accepts an agent identifier, performs an additional HTTP request to fetch agent data, and then creates a local instance of `ChatAgent`.
- Override the `create_agent` method from `BaseChatClient` to create a remote agent instance and wrap it into a local `ChatAgent`.

.NET:

```csharp
var agent1 = new AIProjectClient(...).GetAIAgent(agentInstanceFromSdkType); // Creates a local ChatClientAgent instance from Azure.AI.Projects.OpenAI.AgentReference 
var agent2 = new AIProjectClient(...).GetAIAgent(agentName); // Fetches agent data, creates a local ChatClientAgent instance
var agent3 = new AIProjectClient(...).CreateAIAgent(...); // Creates a remote agent, returns a local ChatClientAgent instance
```

### agent-framework-core (OpenAI Assistants)

- Add a `get_agent` method that accepts an underlying SDK agent instance and creates a local instance of `ChatAgent`.
- Add a `get_agent` method that accepts an agent name, performs an additional HTTP request to fetch agent data, and then creates a local instance of `ChatAgent`.
- Override the `create_agent` method from `BaseChatClient` to create a remote agent instance and wrap it into a local `ChatAgent`.

.NET:

```csharp
var agent1 = new AssistantClient(...).GetAIAgent(agentInstanceFromSdkType); // Creates a local ChatClientAgent instance from OpenAI.Assistants.Assistant
var agent2 = new AssistantClient(...).GetAIAgent(agentId); // Fetches agent data, creates a local ChatClientAgent instance
var agent3 = new AssistantClient(...).CreateAIAgent(...); // Creates a remote agent, returns a local ChatClientAgent instance
```

### Possible Python implementations

Methods like `create_agent` and `get_agent` should be implemented separately or defined on some stateless component that will allow to create multiple agents from the same instance/place.

Possible options:

#### Option 1: Module-level functions

Implement free functions in the provider package that accept the underlying SDK client as the first argument (similar to .NET extension methods, but expressed in Python).

Example:

```python
from agent_framework.azure import create_agent, get_agent

ai_project_client = AIProjectClient(...)

# Creates a remote agent first, then returns a local ChatAgent wrapper
created_agent = await create_agent(
    ai_project_client,
    name="",
    instructions="",
    tools=[tool],
)

# Gets an existing remote agent and returns a local ChatAgent wrapper
first_agent = await get_agent(ai_project_client, agent_id=agent_id)

# Wraps an SDK agent instance (no extra HTTP call)
second_agent = get_agent(ai_project_client, agent_reference)
```

Pros:

- Naturally supports async `create_agent` / `get_agent`.
- Supports multiple agents per SDK client.
- Closest conceptual match to .NET extension methods while staying Pythonic.

Cons:

- Discoverability is lower (users need to know where the functions live).
- Verbose when creating multiple agents (client must be passed every time):

  ```python
  agent1 = await azure_agents.create_agent(client, name="Agent1", ...)
  agent2 = await azure_agents.create_agent(client, name="Agent2", ...)
  ```

#### Option 2: Provider object

Introduce a dedicated provider type that is constructed from the underlying SDK client, and exposes async `create_agent` / `get_agent` methods.

Example:

```python
from agent_framework.azure import AzureAIAgentProvider

ai_project_client = AIProjectClient(...)
provider = AzureAIAgentProvider(ai_project_client)

agent = await provider.create_agent(
    name="",
    instructions="",
    tools=[tool],
)

agent = await provider.get_agent(agent_id=agent_id)
agent = provider.get_agent(agent_reference=agent_reference)
```

Pros:

- High discoverability and clear grouping of related behavior.
- Keeps SDK clients unchanged and supports multiple agents per SDK client.
- Concise when creating multiple agents (client passed once):

  ```python
  provider = AzureAIAgentProvider(ai_project_client)
  agent1 = await provider.create_agent(name="Agent1", ...)
  agent2 = await provider.create_agent(name="Agent2", ...)
  ```

Cons:

- Adds a new public concept/type for users to learn.

#### Option 3: Inheritance (SDK client subclass)

Create a subclass of the underlying SDK client and add `create_agent` / `get_agent` methods.

Example:

```python
class ExtendedAIProjectClient(AIProjectClient):
    async def create_agent(self, *, name: str, model: str, instructions: str, **kwargs) -> ChatAgent:
        ...

    async def get_agent(self, *, agent_id: str | None = None, sdk_agent=None, **kwargs) -> ChatAgent:
        ...

client = ExtendedAIProjectClient(...)
agent = await client.create_agent(name="", instructions="")
```

Pros:

- Discoverable and ergonomic call sites.
- Mirrors the .NET “methods on the client” feeling.

Cons:

- Many SDK clients are not designed for inheritance; SDK upgrades can break subclasses.
- Users must opt into subclass everywhere.
- Typing/initialization can be tricky if the SDK client has non-trivial constructors.

#### Option 4: Monkey patching

Attach `create_agent` / `get_agent` methods to an SDK client class (or instance) at runtime.

Example:

```python
def _create_agent(self, *, name: str, model: str, instructions: str, **kwargs) -> ChatAgent:
    ...

AIProjectClient.create_agent = _create_agent  # monkey patch
```

Pros:

- Produces “extension method-like” call sites without wrappers or subclasses.

Cons:

- Fragile across SDK updates and difficult to type-check.
- Surprising behavior (global side effects), potential conflicts across packages.
- Harder to support/debug, especially in larger apps and test suites.

## Decision Outcome

Implement `create_agent`/`get_agent`/`as_agent` API via **Option 2: Provider object**.

### Rationale

| Aspect | Option 1 (Functions) | Option 2 (Provider) |
|--------|----------------------|---------------------|
| Multiple implementations | One package may contain V1, V2, and other agent types. Function names like `create_agent` become ambiguous - which agent type does it create? | Each provider class is explicit: `AzureAIAgentsProvider` vs `AzureAIProjectAgentProvider` |
| Discoverability | Users must know to import specific functions from the package | IDE autocomplete on provider instance shows all available methods |
| Client reuse | SDK client must be passed to every function call: `create_agent(client, ...)`, `get_agent(client, ...)` | SDK client passed once at construction: `provider = Provider(client)` |

**Option 1 example:**
```python
from agent_framework.azure import create_agent, get_agent
agent1 = await create_agent(client, name="Agent1", ...)  # Which agent type, V1 or V2?
agent2 = await create_agent(client, name="Agent2", ...)  # Repetitive client passing
```

**Option 2 example:**
```python
from agent_framework.azure import AzureAIProjectAgentProvider
provider = AzureAIProjectAgentProvider(client)  # Clear which service, client passed once
agent1 = await provider.create_agent(name="Agent1", ...)
agent2 = await provider.create_agent(name="Agent2", ...)
```

### Method Naming

| Operation | Python | .NET | Async |
|-----------|--------|------|-------|
| Create on service | `create_agent()` | `CreateAIAgent()` | Yes |
| Get from service | `get_agent(id=...)` | `GetAIAgent(agentId)` | Yes |
| Wrap SDK object | `as_agent(reference)` | `AsAIAgent(agentInstance)` | No |

The method names (`create_agent`, `get_agent`) do not explicitly mention "service" or "remote" because:
- In Python, the provider class name explicitly identifies the service (`AzureAIAgentsProvider`, `OpenAIAssistantProvider`), making additional qualifiers in method names redundant.
- In .NET, these are extension methods on `AIProjectClient` or `AssistantClient`, which already imply service operations.

### Provider Class Naming

| Package | Provider Class | SDK Client | Service |
|---------|---------------|------------|---------|
| `agent_framework.azure` | `AzureAIProjectAgentProvider` | `AIProjectClient` | Azure AI Agent Service, based on Responses API (V2) |
| `agent_framework.azure` | `AzureAIAgentsProvider` | `AgentsClient` | Azure AI Agent Service (V1) |
| `agent_framework.openai` | `OpenAIAssistantProvider` | `AsyncOpenAI` | OpenAI Assistants API |

> **Note:** Azure AI naming is temporary. Final naming will be updated according to Azure AI / Microsoft Foundry renaming decisions.

### Usage Examples

#### Azure AI Agent Service V2 (based on Responses API)

```python
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.ai.projects import AIProjectClient

client = AIProjectClient(endpoint, credential)
provider = AzureAIProjectAgentProvider(client)

# Create new agent on service
agent = await provider.create_agent(name="MyAgent", model="gpt-4", instructions="...")

# Get existing agent by name
agent = await provider.get_agent(agent_name="MyAgent")

# Wrap already-fetched SDK object (no HTTP calls)
agent_ref = await client.agents.get("MyAgent")
agent = provider.as_agent(agent_ref)
```

#### Azure AI Persistent Agents V1

```python
from agent_framework.azure import AzureAIAgentsProvider
from azure.ai.agents import AgentsClient

client = AgentsClient(endpoint, credential)
provider = AzureAIAgentsProvider(client)

agent = await provider.create_agent(name="MyAgent", model="gpt-4", instructions="...")
agent = await provider.get_agent(agent_id="persistent-agent-456")
agent = provider.as_agent(persistent_agent)
```

#### OpenAI Assistants

```python
from agent_framework.openai import OpenAIAssistantProvider
from openai import OpenAI

client = OpenAI()
provider = OpenAIAssistantProvider(client)

agent = await provider.create_agent(name="MyAssistant", model="gpt-4", instructions="...")
agent = await provider.get_agent(assistant_id="asst_123")
agent = provider.as_agent(assistant)
```

#### Local-Only Agents (No Provider)

Current method `create_agent` (python) / `CreateAIAgent` (.NET) can be renamed to `as_agent` (python) / `AsAIAgent` (.NET) to emphasize the conversion logic rather than creation/initialization logic and to avoid collision with `create_agent` method for remote calls.

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

# Convert chat client to ChatAgent (no remote service involved)
client = OpenAIChatClient(model="gpt-4")
agent = client.as_agent(name="LocalAgent", instructions="...") # instead of create_agent
```

### Adding New Agent Types

Python:

1. Create provider class in appropriate package.
2. Implement `create_agent`, `get_agent`, `as_agent` as applicable.

.NET:

1. Create static class for extension methods.
2. Implement `CreateAIAgentAsync`, `GetAIAgentAsync`, `AsAIAgent` as applicable.
