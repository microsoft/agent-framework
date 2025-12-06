---
status: proposed
contact: dmytrostruk
date: 2025-12-03
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
var agent1 = new AIProjectClient(...).GetAIAgent(agentSdkInstance); // Creates a local ChatClientAgent instance
var agent2 = new AIProjectClient(...).GetAIAgent(agentName); // Fetches agent data, creates a local ChatClientAgent instance
var agent3 = new AIProjectClient(...).CreateAIAgent(...); // Creates a remote agent, returns a local ChatClientAgent instance
```

Python:

```python
agent1 = AIProjectClient(...).get_agent(agent_sdk_instance) # Creates a local ChatAgent instance
agent2 = AIProjectClient(...).get_agent(agent_name) # Fetches agent data, creates a local ChatAgent instance
agent3 = AIProjectClient(...).create_agent(...) # Creates a remote agent, returns a local ChatAgent instance
```

### agent-framework-core (OpenAI Assistants)

- Add a `get_agent` method that accepts an underlying SDK agent instance and creates a local instance of `ChatAgent`.
- Add a `get_agent` method that accepts an agent name, performs an additional HTTP request to fetch agent data, and then creates a local instance of `ChatAgent`.
- Override the `create_agent` method from `BaseChatClient` to create a remote agent instance and wrap it into a local `ChatAgent`.

.NET:

```csharp
var agent1 = new AssistantClient(...).GetAIAgent(agentSdkInstance); // Creates a local ChatClientAgent instance
var agent2 = new AssistantClient(...).GetAIAgent(agentId); // Fetches agent data, creates a local ChatClientAgent instance
var agent3 = new AssistantClient(...).CreateAIAgent(...); // Creates a remote agent, returns a local ChatClientAgent instance
```

Python:

```python
agent1 = OpenAIAssistantsClient(...).get_agent(agent_sdk_instance) # Creates a local ChatAgent instance
agent2 = OpenAIAssistantsClient(...).get_agent(agent_name) # Fetches agent data, creates a local ChatAgent instance
agent3 = OpenAIAssistantsClient(...).create_agent(...) # Creates a remote agent, returns a local ChatAgent instance
```

## Decision Outcome

TBD
