---
status: accepted
contact: rogerbarreto
date: 2026-03-06
deciders: rogerbarreto, alliscode
consulted: eavanvalkenburg
informed: ""
---

# Foundry agent type naming (.NET)

## Context

The Microsoft Foundry integration exposes two distinct usage patterns:

1. Direct Responses usage, where callers provide model, instructions, and tools at runtime.
2. Server-side versioned agents, where callers create and manage `AgentVersion` resources through `AIProjectClient.Agents`.

We briefly explored keeping the public surface centered on `ChatClientAgent` alone, with no Foundry-specific types. That approach avoided new public types but left a gap for Foundry-specific capabilities (server-side conversations, agent-scoped endpoints) that don't exist on `ChatClientAgent`.

The Python side introduced `FoundryAgent(Agent)` as a first-class public type in [ADR 0021 — Provider-Leading Client Design](0021-provider-leading-clients.md). This ADR records the aligned .NET decision and remaining port gaps.

## Decision (updated)

Introduce `FoundryAgent` as a public `DelegatingAIAgent` subclass in `Microsoft.Agents.AI.AzureAI`.

- Direct Responses scenarios use `AIProjectClient.AsAIAgent(model, instructions, ...)` → returns `FoundryAgent`.
- Server-side versioned scenarios use native `AIProjectClient.Agents` APIs, then wrap with `AIProjectClient.AsAIAgent(AgentRecord | AgentVersion | AgentReference)` → returns `FoundryAgent`.
- `FoundryAgent` adds Foundry-specific capabilities not present on `ChatClientAgent`: `CreateConversationSessionAsync()` for server-side conversation management.
- `CreateAIAgentAsync(...)` and `GetAIAgentAsync(...)` are marked `[Obsolete]` and will be removed in a future release. New code should use native `AIProjectClient.Agents` APIs and non-obsolete `AsAIAgent(...)` overloads.
- The internal `AzureAIProjectResponsesChatClient` handles Foundry Responses API plumbing; it is not part of the public surface.

## Why

- `FoundryAgent` provides a natural home for Foundry-specific features (server-side conversations) without polluting the generic `ChatClientAgent`.
- All `AsAIAgent(...)` overloads on `AIProjectClient` return `FoundryAgent`, giving users access to Foundry features without explicit casting.
- Aligns with Python's `FoundryAgent(Agent)` pattern from ADR 0021, keeping the cross-language API consistent.
- Removing `CreateAIAgentAsync`/`GetAIAgentAsync` simplifies the surface — lifecycle management belongs on the native `AIProjectClient.Agents` APIs, not on framework extensions.

## Consequences

### Direct Responses path

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

### Versioned agent path

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
    chatClient: projectResponsesClient.AsIChatClient(),
    name: "JokerAgent");
```

### Samples

- `AgentsWithFoundry/` samples cover both direct Responses and versioned agent paths with progressive complexity (Step00–Step23).
- `01-get-started/` samples use `AIProjectClient.AsAIAgent(model, ...)` as the default provider.

### Compatibility APIs

`CreateAIAgentAsync(...)` and `GetAIAgentAsync(...)` are `[Obsolete]`. New samples and guidance must not use them. Migration path:

- `CreateAIAgentAsync(...)` → use `AIProjectClient.Agents.CreateAgentVersionAsync(...)` + `AsAIAgent(version)`.
- `GetAIAgentAsync(...)` → use `AIProjectClient.Agents.GetAgentAsync(...)` + `AsAIAgent(agentRecord)`.

### .NET port gaps from ADR 0021

ADR 0021 introduced additional Python-side changes that need .NET equivalents:

- **Unified `model` parameter**: Python unified `model_id`, `deployment_name`, and `model_deployment_name` into a single `model` parameter. .NET already uses `model` in `AsAIAgent(...)` overloads — verify consistency across all entry points.
- **Deprecated Azure wrapper consolidation**: Python moved all deprecated `AzureOpenAI*` classes into a single file for clean future deletion. .NET should consolidate obsolete Foundry extensions similarly.
- **`FoundryAgent` constructor parity**: Python's `FoundryAgent` accepts `agent_name` for connecting to pre-configured agents. .NET's `FoundryAgent` supports this via the `AgentReference`-based constructor — verify feature parity.
- **`RawFoundryAgentChatClient` equivalent**: Python exposes `RawFoundryAgentChatClient` as a public extension point. .NET uses internal `AzureAIProjectResponsesChatClient` — evaluate whether a public extension point is needed.

## Rejected direction

Do not keep the surface centered on `ChatClientAgent` alone with no Foundry-specific public types. That approach was initially considered but rejected when `FoundryAgent` was introduced to support Foundry-specific capabilities (server-side conversations) and to align with ADR 0021's cross-language `FoundryAgent` pattern.
