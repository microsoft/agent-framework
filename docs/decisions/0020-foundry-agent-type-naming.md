---
status: proposed
contact: rogerbarreto
date: 2026-03-06
deciders: rogerbarreto, alliscode
consulted: ""
informed: ""
---

# Naming Convention for Microsoft Foundry Agent Types in MAF

## Context and Problem Statement

The Microsoft Agent Framework (MAF) needs to provide wrapper types around the Azure SDK's Microsoft Foundry agent service. The Foundry service exposes two distinct interaction models:

1. **Responses API (RAPI)** — Stateless, model-level calls where the caller provides instructions, model, and tools at each request. No server-side agent definition is created or managed.
2. **Versioned Agents** — Server-side agent definitions (managed by the Foundry service) that are created, versioned, and persisted. These come in four `AgentKind` variants: `Prompt`, `ContainerApp`, `Hosted`, and `Workflow`.

We currently have `FoundryResponsesAgent` (wrapping the Responses API path). We need a clear, consistent naming scheme that:
- Distinguishes between the two interaction models
- Is intuitive for developers new to the framework
- Leaves room for future agent kinds without naming conflicts
- Aligns with the broader MAF naming conventions (`ChatClientAgent`, `AzureAIProjectChatClient`, etc.)

## Decision Drivers

- **Clarity** — A developer should understand what each type does from its name alone
- **Consistency** — Names should follow existing MAF patterns (`XxxAgent` suffix)
- **Extensibility** — The naming should not need to change as new Foundry agent kinds emerge
- **Discoverability** — IntelliSense/autocomplete should group related types together (shared prefix)
- **Accuracy** — Names should reflect the Azure SDK terminology (`AgentVersion`, `AgentDefinition`, `PromptAgentDefinition`, etc.)

## Background: Foundry Agent Definition Types

The Azure SDK (`Azure.AI.Projects.OpenAI`) defines the following hierarchy:

```
AgentDefinition (abstract)
├── PromptAgentDefinition       (kind: "prompt")       — GA
├── ContainerApplicationAgentDefinition  (kind: "container_app")  — Experimental
├── HostedAgentDefinition       (kind: "hosted")       — Experimental
├── WorkflowAgentDefinition     (kind: "workflow")     — Experimental
```

All four kinds use the same versioning API (`CreateAgentVersion` / `GetAgentVersions`). Agents are immutable — every update creates a new `AgentVersion`.

The key operational difference from the Responses API path is:
- **Responses API**: No persistent agent definition. Model + instructions + tools are sent per-request.
- **Versioned Agents**: A persistent `AgentDefinition` is created server-side. Requests reference the agent by name/version.

## Considered Options

### Option 1: `FoundryResponsesAgent` + `FoundryAgent`

| Type | Wraps | Description |
|------|-------|-------------|
| `FoundryResponsesAgent` | Responses API directly | No server-side agent. Uses `GetProjectResponsesClientForModel()`. |
| `FoundryAgent` | Versioned agent (any kind) | Creates/manages an `AgentVersion` via `CreateAgentVersionAsync()`. Uses `GetProjectResponsesClientForAgent()`. |

- Good, because `FoundryAgent` is the simplest, most intuitive name for the server-side agent path
- Good, because it mirrors the distinction: "Responses" (API-level) vs. "Agent" (managed entity)
- Neutral, because `FoundryAgent` is generic — it would need to support all four definition kinds via configuration
- Bad, because the word "Agent" is overloaded in the framework context (everything is an agent)

### Option 2: `FoundryResponsesAgent` + `FoundryVersionedAgent`

| Type | Wraps | Description |
|------|-------|-------------|
| `FoundryResponsesAgent` | Responses API directly | No server-side agent. Uses `GetProjectResponsesClientForModel()`. |
| `FoundryVersionedAgent` | Versioned agent (any kind) | Creates/manages an `AgentVersion`. The "versioned" qualifier highlights the immutable versioning model. |

- Good, because "Versioned" explicitly calls out the key differentiator (immutable server-side versions)
- Good, because it makes the contrast with `FoundryResponsesAgent` immediately clear
- Good, because it aligns with the Azure SDK terminology (`AgentVersion`, `CreateAgentVersion`)
- Neutral, because "Versioned" is an implementation detail that may not be meaningful to users unfamiliar with the service
- Bad, because the name could become confusing if the Responses API path later gains version-like features

### Option 3: `FoundryResponsesAgent` + `FoundryManagedAgent`

| Type | Wraps | Description |
|------|-------|-------------|
| `FoundryResponsesAgent` | Responses API directly | No server-side agent. |
| `FoundryManagedAgent` | Versioned agent (any kind) | Emphasizes that Foundry manages the agent definition server-side. |

- Good, because "Managed" communicates that the service owns the agent lifecycle
- Good, because it's intuitive even without understanding versioning details
- Neutral, because "Managed" is a common qualifier in Azure (ManagedIdentity, etc.) and may feel generic
- Bad, because it doesn't hint at the versioning model which is a core characteristic

### Option 4: `FoundryResponsesAgent` + `FoundryProjectAgent`

| Type | Wraps | Description |
|------|-------|-------------|
| `FoundryResponsesAgent` | Responses API directly | No server-side agent. |
| `FoundryProjectAgent` | Versioned agent (any kind) | Named after `AIProjectClient` which is the entry point for this path. |

- Good, because it directly ties to the `AIProjectClient` → `Agents` API surface
- Good, because it disambiguates clearly from the Responses path
- Bad, because "Project" doesn't convey what makes this agent type different
- Bad, because users may think it's about project configuration rather than agent management

### Option 5: Per-kind types (`FoundryPromptAgent`, `FoundryContainerAgent`, `FoundryHostedAgent`, `FoundryWorkflowAgent`)

| Type | Wraps |
|------|-------|
| `FoundryPromptAgent` | `PromptAgentDefinition` |
| `FoundryContainerAgent` | `ContainerApplicationAgentDefinition` |
| `FoundryHostedAgent` | `HostedAgentDefinition` |
| `FoundryWorkflowAgent` | `WorkflowAgentDefinition` |

- Good, because each type exactly maps to one agent kind
- Good, because IntelliSense shows all options with `Foundry` prefix
- Bad, because it creates 4+ types to maintain instead of 1
- Bad, because 3 of the 4 kinds are experimental and may change
- Bad, because `FoundryPromptAgent` could be confused with `FoundryResponsesAgent` (both use prompts)

## Decision Outcome

*To be decided by the team.*

## More Information

### Current State

- `FoundryResponsesAgent` exists in `Microsoft.Agents.AI.AzureAI` — wraps the Responses API path via `GetProjectResponsesClientForModel(modelId)`.
- The non-RAPI path currently has no MAF wrapper. Users use the Azure SDK directly (`AIProjectClient.Agents.CreateAgentVersionAsync()` → `GetProjectResponsesClientForAgent()`).
- PR [#4502](https://github.com/microsoft/agent-framework/pull/4502) introduces `FoundryResponsesAgent` and related samples.

### Azure SDK Entry Points for Reference

```csharp
// Responses API (RAPI) — what FoundryResponsesAgent wraps today
ResponsesClient responsesClient = projectClient.OpenAI.GetProjectResponsesClientForModel(modelId);

// Versioned Agent — what the new type would wrap
AgentVersion agentVersion = await projectClient.Agents.CreateAgentVersionAsync(agentName, new(definition));
ProjectResponsesClient responseClient = projectClient.OpenAI.GetProjectResponsesClientForAgent(agentVersion, conversationId);
```

### Metadata Consideration

The current `FoundryResponsesAgent` uses metadata provider `"microsoft.foundry"`. If a new type is introduced, consider whether it should share the same provider or use a distinct one (e.g., `"microsoft.foundry.versioned"` or `"microsoft.foundry.agents"`).
