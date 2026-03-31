---
status: accepted
contact: rogerbarreto
date: 2026-03-06
deciders: rogerbarreto, alliscode
consulted: eavanvalkenburg, sphenry, chetantoshnival
informed: ""
---

# Foundry Agents usage pattern and samples updates (.NET)

## Context and Problem Statement

The Microsoft Foundry integration exposes two distinct usage patterns:

1. Direct Responses API usage, where callers provide model, instructions, and tools at runtime without creating a server-side agent.
2. Server-side versioned agents, where agents are created separately via `AIProjectClient.Agents` APIs and consumed as pre-existing immutable agent versions via `AgentVersion`, `AgentReference` or `AgentRecord` resources.

Agent Framework APIs are focused on runtime consumption of Foundry agents, not their lifecycle management. Server-side lifecycle operations (creating, updating, deleting agents) are the responsibility of `AIProjectClient.Agents` and are not part of the framework's consumption design. APIs and samples that previously encouraged usage of `CreateAIAgentAsync` and `GetAIAgentAsync` needed to be deprecated in favor of `AIProjectClient.AsAIAgent` targeting already existing versions.

## Decision Outcome

Introduce a specialized `FoundryAgent` type in `Microsoft.Agents.AI.AzureAI` for consuming server-side versioned agents, and deprecate the lifecycle-oriented `CreateAIAgentAsync`/`GetAIAgentAsync` APIs. This aligns with Python's `FoundryAgent` introduced in [ADR 0021 — Provider-Leading Client Design](0021-provider-leading-clients.md).

- Direct Responses scenarios use `AIProjectClient.AsAIAgent(model, instructions, ...)` → returns `ChatClientAgent`.
- Server-side versioned scenarios use native `AIProjectClient.Agents` APIs, then wrap with `AIProjectClient.AsAIAgent(AgentRecord | AgentVersion | AgentReference)` → returns `FoundryAgent`.
- `FoundryAgent` adds Foundry-specific capabilities not present on `ChatClientAgent`: `CreateConversationSessionAsync()` for server-side conversation management.
- `CreateAIAgentAsync(...)` and `GetAIAgentAsync(...)` are marked `[Obsolete]` and will be removed in a future release. New code should use native `AIProjectClient.Agents` APIs and non-obsolete `AsAIAgent(...)` overloads.

### Consequences

#### Direct Responses path

Use the convenience overloads on `AIProjectClient`:

```csharp
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

FoundryAgent agent = aiProjectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");
```

Or use composed `ChatClientAgent` for provider-agnostic code:

```csharp
ProjectResponsesClient projectResponsesClient = new(new Uri(endpoint), new DefaultAzureCredential(), new AgentReference($"model:{deploymentName}"));

ChatClientAgent agent = new(
    chatClient: projectResponsesClient.AsIChatClient(),
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");
```

This path is code-first and does not create a persistent server-side agent.

#### Versioned / Foundry Agent path

Use the convenience overloads on `AIProjectClient`:

```csharp
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

AgentVersion version = await aiProjectClient.Agents.CreateAgentVersionAsync(
    "JokerAgent",
    new AgentVersionCreationOptions(
        new PromptAgentDefinition(deploymentName)
        {
            Instructions = "You are good at telling jokes."
        }));

FoundryAgent agent = aiProjectClient.AsAIAgent(version);
```

Or use composed `ChatClientAgent`:

```csharp
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

AgentVersion version = await aiProjectClient.Agents.CreateAgentVersionAsync(
    "JokerAgent",
    new AgentVersionCreationOptions(
        new PromptAgentDefinition(deploymentName)
        {
            Instructions = "You are good at telling jokes."
        }));

ProjectResponsesClient projectResponsesClient = aiProjectClient
    .GetProjectOpenAIClient()
    .GetProjectResponsesClientForAgent(new AgentReference(version.Name, version.Version));

ChatClientAgent agent = new(
    chatClient: projectResponsesClient.AsIChatClient(deploymentName),
    name: "JokerAgent");
```

#### Samples

- `AgentsWithFoundry/` samples cover both direct Responses and versioned agent paths with progressive complexity (Step00–Step23).
- `01-get-started/` samples use `AIProjectClient.AsAIAgent(model, ...)` as the default provider.

#### Compatibility APIs

`CreateAIAgentAsync(...)` and `GetAIAgentAsync(...)` are `[Obsolete]`. New samples and guidance must not use them. Migration path:

- `CreateAIAgentAsync(...)` → use `AIProjectClient.Agents.CreateAgentVersionAsync(...)` + `AsAIAgent(version)`.
- `GetAIAgentAsync(...)` → use `AIProjectClient.Agents.GetAgentAsync(...)` + `AsAIAgent(agentRecord)`.
