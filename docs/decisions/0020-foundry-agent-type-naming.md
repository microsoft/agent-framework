---
status: accepted
contact: rogerbarreto
date: 2026-03-06
deciders: rogerbarreto, alliscode
consulted: ""
informed: ""
---

# Foundry agent surface stays centered on `ChatClientAgent`

## Context

The Microsoft Foundry integration exposes two distinct usage patterns:

1. Direct Responses usage, where callers provide model, instructions, and tools at runtime.
2. Server-side versioned agents, where callers create and manage `AgentVersion` resources through `AIProjectClient.Agents`.

We briefly explored adding public wrapper types such as `FoundryAgent`, `FoundryVersionedAgent`, and `FoundryResponsesChatClient` to make those paths feel more specialized. That direction created extra public types, duplicated existing `ChatClientAgent` behavior, and pushed samples toward compatibility helpers instead of the native Azure SDK flow.

## Decision

Keep the public surface centered on `ChatClientAgent`.

- Direct Responses scenarios use `AIProjectClient.AsAIAgent(...)`.
- Server-side versioned scenarios use native `AIProjectClient.Agents` APIs to create or retrieve agent resources, then wrap `AgentRecord` or `AgentVersion` with `AIProjectClient.AsAIAgent(...)`.
- Compatibility helpers such as `AIProjectClient.CreateAIAgentAsync(...)` and `AIProjectClient.GetAIAgentAsync(...)` remain only as obsolete migration shims.
- Public wrapper types `FoundryAgent`, `FoundryVersionedAgent`, `FoundryResponsesChatClient`, and `FoundryResponsesChatClientAgent` are not part of the chosen direction.

## Why

- `ChatClientAgent` is already the framework abstraction used everywhere else.
- `AIProjectClient` is the native Azure SDK entry point for versioned agent lifecycle operations.
- A single agent abstraction avoids parallel type hierarchies for the same backend.
- Samples become clearer when they show either:
  - direct Responses construction via `AIProjectClient.AsAIAgent(...)`, or
  - native Foundry resource management via `AIProjectClient.Agents`.

## Consequences

### Direct Responses path

Use the convenience overloads on `AIProjectClient`:

```csharp
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

ChatClientAgent agent = aiProjectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");
```

Or use composed `ChatClientAgent`

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

ChatClientAgent agent = aiProjectClient.AsAIAgent(version);
```

Or use composed `ChatClientAgent`

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

- `FoundryAgents/` samples show the direct Responses path with `AIProjectClient.AsAIAgent(...)`.
- `FoundryVersionedAgents/` samples should show native `AIProjectClient.Agents` create/get/delete flows plus `AsAIAgent(...)`.

### Compatibility APIs

Obsolete helper extensions remain only to ease migration of existing code. New samples and new guidance should not be written against them.

## Rejected direction

Do not introduce or preserve separate public wrapper types whose main purpose is to forward to `ChatClientAgent` while carrying Foundry-specific naming.

That approach:

- duplicates lifecycle concepts already present on `AIProjectClient`,
- fragments the public API,
- complicates samples and docs,
- and makes migration harder by encouraging wrapper-specific affordances.
