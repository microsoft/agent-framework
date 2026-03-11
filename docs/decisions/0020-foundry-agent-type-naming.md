---
status: accepted
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

### Option 6: `FoundryAgent` + `FoundryVersionedAgent` with self-contained factories, `FoundryAITool`, and explicit configuration

Combines **Option 1** naming for the Responses API path with **Option 2** naming for the versioned path, plus architectural decisions about construction patterns, tool factories, and sample conventions.

#### Naming

| Type | Wraps | Description |
|------|-------|-------------|
| `FoundryAgent` | Responses API directly | No server-side agent. Uses `GetProjectResponsesClientForModel()`. Public constructors with explicit endpoint, credential, and model configuration. |
| `FoundryVersionedAgent` | Versioned agent (any kind) | Creates/manages an `AgentVersion`. Private constructor, async static factory methods only. |
| `FoundryAITool` | `AgentTool` + `ResponseTool` factories | Static factory returning `AITool` directly, eliminating cast+`.AsAITool()` ceremony. |

#### `FoundryAgent` (Responses API)

Self-contained agent that creates its own `AIProjectClient` internally. Construction is explicit:

- **Simple constructor**: Accepts `Uri endpoint` + `AuthenticationTokenProvider` + `model`, plus optional instructions, name, description, tools, and `AIProjectClientOptions`.
- **Options-based constructor**: Accepts `Uri endpoint` + `AuthenticationTokenProvider` + `ChatClientAgentOptions`. `options.ChatOptions.ModelId` is required.

Both constructors inject MEAI user-agent headers via `clientOptions.AddPolicy(UserAgentPolicy, PerCall)`.

#### `FoundryVersionedAgent` (Versioned Agents)

Self-contained agent with **private constructor** — only instantiated via async static factory methods:

- **`CreateAIAgentAsync`** — Creates a new server-side agent version (overload groups for simple params, `ChatClientAgentOptions`, and `AgentVersionCreationOptions`).
- **`GetAIAgentAsync`** — Retrieves an existing agent by name or by `ChatClientAgentOptions`.
- **`AsAIAgent`** — Wraps an existing `AgentReference`, `AgentRecord`, or `AgentVersion` without a server round-trip.
- **`DeleteAIAgentAsync` / `DeleteAIAgentVersionAsync`** — Deletes the whole agent or only the bound version.

All factory methods require explicit `Uri endpoint` + `AuthenticationTokenProvider`; creation overloads also require an explicit `model`.

Both agents expose `CreateConversationSessionAsync()` — creates a server-side `ProjectConversation` and returns a `ChatClientAgentSession` linked to it, so conversations appear in the Foundry Project UI.

Internally, `FoundryVersionedAgent` reuses the same shared helpers as the existing `AIProjectClient` extension methods (`CreateChatClientAgentOptions`, `ApplyToolsToAgentDefinition`, `CreateAgentVersionWithProtocolAsync`, etc.), which were refactored from `private` to `internal` to enable code sharing.

#### `FoundryAITool` (Tool Factory)

Static class wrapping all `AgentTool.Create*` (Azure SDK, 9 methods) and `ResponseTool.Create*` (OpenAI SDK, 8+ methods) factory methods, each returning `AITool` directly:

```csharp
// Before
tools: [((ResponseTool)AgentTool.CreateOpenApiTool(definition)).AsAITool()]

// After
tools: [FoundryAITool.CreateOpenApiTool(definition)]
```

Also provides `FromResponseTool(ResponseTool)` for converting existing `ResponseTool` instances (e.g., `MemorySearchPreviewTool`).

#### `GetService` surface

Both `FoundryAgent` and `FoundryVersionedAgent` expose via `GetService<T>()`:
- `AIProjectClient` — the internally-managed client
- `ChatClientAgent` — the inner agent
- `AIAgentMetadata` — `"microsoft.foundry"` for both types
- `AgentVersion` — (FoundryVersionedAgent only) the server-side agent version

#### Sample conventions

- Samples read `AZURE_AI_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` explicitly near the start of `Program.cs`
- Non-discoverable env vars (tool connection IDs, App Insights, etc.) are still read explicitly
- **Explicit types** preferred over `var` for agent and session variables
- **One-line construction** remains appropriate for simple `FoundryAgent` cases when only `instructions` + `name` vary, but endpoint, credential, and model stay explicit
- Folder structure: `FoundryAgents/` (Responses API, default path), `FoundryVersionedAgents/` (versioned, alternative)

#### Pros

- Good, because both types are fully self-contained — no external `AIProjectClient` required
- Good, because explicit endpoint, credential, and model parameters keep API behavior predictable and consistent with the rest of the repo
- Good, because `FoundryAITool` eliminates the `((ResponseTool)...).AsAITool()` casting ceremony
- Good, because `FoundryAgent` naming positions the Responses API as the primary/default path
- Good, because private constructor + async factories enforce correct async initialization for `FoundryVersionedAgent`
- Good, because `DeleteAIAgentAsync` and `DeleteAIAgentVersionAsync` centralize cleanup semantics
- Good, because `CreateConversationSessionAsync` eliminates multi-step conversation setup boilerplate
- Good, because `AsAIAgent` provides the replacement for obsolete extension methods when callers already have SDK agent objects
- Good, because shared internal helpers avoid code duplication between `FoundryVersionedAgent` and extension methods

## Decision Outcome

**Chosen option: Option 6** — `FoundryAgent` + `FoundryVersionedAgent` with self-contained factories, `FoundryAITool`, and explicit configuration.

This option was chosen because it:

1. **Positions the Responses API as the default path** — `FoundryAgent` is the simplest name, signaling this is the recommended starting point. `FoundryVersionedAgent` clearly marks the server-side versioned alternative.
2. **Keeps construction explicit** — Samples can still read environment variables for convenience, but constructors and factory methods behave predictably and do not hide configuration.
3. **Enforces correct patterns** — Private constructor + async factories prevent misuse of the versioned agent path. Self-contained client management prevents credential and endpoint misconfiguration.
4. **Maintains backward compatibility while steering new code forward** — Existing `AIProjectClient` extension methods remain available but are marked obsolete; new code should use `FoundryVersionedAgent`.
5. **Uses shared metadata** — Both types use `AIAgentMetadata("microsoft.foundry")` since they share the same backing service.

## More Information

### Current State

- `FoundryAgent` (renamed from `FoundryResponsesAgent`) exists in `Microsoft.Agents.AI.AzureAI` — wraps the Responses API path with explicit constructors.
- `FoundryVersionedAgent` exists in `Microsoft.Agents.AI.AzureAI` — wraps the versioned agent path with async static factory methods.
- `FoundryAITool` exists in `Microsoft.Agents.AI.AzureAI` — static factory for creating `AITool` from Azure SDK and OpenAI SDK tool types.
- Existing `AIProjectClient` extension methods (`CreateAIAgentAsync`, `GetAIAgentAsync`, `AsAIAgent`) remain available for compatibility but are marked `[Obsolete]` with messages pointing to `FoundryVersionedAgent`.
- Samples are organized under `FoundryAgents/` (Responses API samples) and `FoundryVersionedAgents/` (versioned agent samples), and they read environment variables explicitly at the start of `Program.cs`.
- Integration tests exist for both `FoundryAgent` and `FoundryVersionedAgent`, covering run, streaming, structured output, and agent creation scenarios. Old tests targeting the obsolete extension methods are themselves marked `[Obsolete]`.

### Azure SDK Entry Points for Reference

```csharp
// Responses API (RAPI) — what FoundryAgent wraps today
ResponsesClient responsesClient = projectClient.OpenAI.GetProjectResponsesClientForModel(modelId);

// Versioned Agent — what the new type would wrap
AgentVersion agentVersion = await projectClient.Agents.CreateAgentVersionAsync(agentName, new(definition));
ProjectResponsesClient responseClient = projectClient.OpenAI.GetProjectResponsesClientForAgent(agentVersion, conversationId);
```

### Metadata

Both `FoundryAgent` and `FoundryVersionedAgent` use metadata provider `"microsoft.foundry"` — they share the same backing service and the distinction is in construction pattern, not service identity.
