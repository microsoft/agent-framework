---
status: accepted
contact: eavanvalkenburg
date: 2026-03-20
deciders: eavanvalkenburg, sphenry, chetantoshnival
consulted: taochenosu, moonbox3, dmytrostruk, giles17, alliscode
---

# Provider-Leading Client Design & OpenAI Package Extraction

## Context and Problem Statement

The `agent-framework-core` package currently bundles OpenAI and Azure OpenAI client implementations along with their dependencies (`openai`, `azure-identity`, `azure-ai-projects`, `packaging`). This makes core heavier than necessary for users who don't use OpenAI, and it conflates the core abstractions with a specific provider implementation. Additionally, the current class naming (`OpenAIResponsesClient`, `OpenAIChatClient`) is based on the underlying OpenAI API names rather than what users actually want to do, making discoverability harder for newcomers.

## Decision Drivers

- **Lightweight core**: Core should only contain abstractions, middleware infrastructure, and telemetry — no provider-specific code or dependencies.
- **Discoverability-first**: Import namespaces should guide users to the right client. `from agent_framework.openai import ...` should surface all OpenAI-related clients; `from agent_framework.azure import ...` should surface Foundry, Azure AI, and other Azure-specific classes.
- **Provider-leading naming**: The primary client name should reflect the provider, not the underlying API. The Responses API is now the recommended default for OpenAI, so its client should be called `OpenAIChatClient` (not `OpenAIResponsesClient`).
- **Clean separation of concerns**: Azure-specific deprecated wrappers belong in the azure-ai package, not in the OpenAI package.

## Considered Options

- **Keep OpenAI in core**: Simpler but keeps core heavy; doesn't help discoverability.
- **Extract OpenAI with Azure wrappers in the OpenAI package**: Keeps Azure OpenAI wrappers alongside OpenAI code, but pollutes the OpenAI package with Azure concerns.
- **Extract OpenAI, place Azure wrappers in azure-ai**: Clean separation; the OpenAI package has zero Azure dependencies; deprecated Azure wrappers live in a single file in azure-ai for easy future deletion.

## Decision Outcome

Chosen option: "Extract OpenAI, place Azure wrappers in azure-ai", because it achieves the lightest core, cleanest OpenAI package, and the most maintainable deprecation path.

Key changes:

1. **New `agent-framework-openai` package** with dependencies on `agent-framework-core`, `openai`, and `packaging` only.
2. **Class renames**: `OpenAIResponsesClient` → `OpenAIChatClient` (Responses API), `OpenAIChatClient` → `OpenAIChatCompletionClient` (Chat Completions API). Old names remain as deprecated aliases.
3. **Deprecated classes**: `OpenAIAssistantsClient`, all `AzureOpenAI*Client` classes, `AzureAIClient`, `AzureAIAgentClient`, and `AzureAIProjectAgentProvider` are marked deprecated.
4. **New `FoundryChatClient`** in azure-ai for Azure AI Foundry Responses API access, built on `RawFoundryChatClient(RawOpenAIChatClient)`.
5. **All deprecated `AzureOpenAI*` classes** consolidated into a single file (`_deprecated_azure_openai.py`) in the azure-ai package for clean future deletion.
6. **Core's `agent_framework.openai` and `agent_framework.azure` namespaces** become lazy-loading gateways, preserving backward-compatible import paths while removing hard dependencies.
7. **Unified `model` parameter** replaces `model_id` (OpenAI), `deployment_name` (Azure OpenAI), and `model_deployment_name` (Azure AI) across all client constructors. The term `model` is intentionally generic: it naturally maps to an OpenAI model name *and* to an Azure OpenAI deployment name, making it straightforward to use `OpenAIChatClient` with either OpenAI or Azure OpenAI backends (via `AsyncAzureOpenAI`). Environment variables are similarly unified (e.g., `OPENAI_MODEL` instead of separate `OPENAI_CHAT_MODEL_ID` / `OPENAI_CHAT_COMPLETION_MODEL_ID`).
8. **`FoundryAgent`** replaces the pattern of `Agent(client=AzureAIClient(...))` for connecting to pre-configured agents in Azure AI Foundry (PromptAgents and HostedAgents). The underlying `RawFoundryAgentChatClient` is an implementation detail — most users interact only with `FoundryAgent`. `AzureAIAgentClient` is separately deprecated as it refers to the V1 Agents Service API. See below for design rationale.

### Foundry Agent Design: `FoundryAgentClient` vs `FoundryAgent`

The existing `AzureAIClient` combines two concerns: CRUD lifecycle management (creating/deleting agents on the service) and runtime communication (sending messages via the Responses API). The new design removes CRUD entirely — users connect to agents that already exist in Foundry.

**Two approaches were considered:**

**Option A — `FoundryAgentClient` only (public ChatClient):**
Users compose `Agent(client=FoundryAgentClient(...), tools=[...])`. This follows the universal `Agent(client=X)` pattern used by every other provider. However, a "client" that wraps a named remote agent (with `agent_name` as a constructor param) is semantically odd — clients typically wrap a model endpoint, not a specific agent.

**Option B — `FoundryAgent` (Agent subclass) + private `_FoundryAgentChatClient` and public `RawFoundryAgentChatClient`:**
Users write `FoundryAgent(agent_name="my-agent", ...)` for the common case. Internally, `FoundryAgent` creates a `_FoundryAgentChatClient` and passes it to the standard `Agent` base class. For advanced customization, users pass `client_type=RawFoundryAgentChatClient` (or a custom subclass) to control the client middleware layers. The `Agent(client=RawFoundryAgentChatClient(...))` composition pattern still works for users who prefer it.

**Chosen option: Option B**, because:
- The common case (`FoundryAgent(...)`) is a single object with no boilerplate.
- `client_type=` gives full control over client middleware without parameter duplication — the agent forwards connection params to the client internally.
- `RawFoundryAgent(RawAgent)` and `FoundryAgent(Agent)` mirror the established `RawAgent`/`Agent` pattern.
- Runtime validation (only `FunctionTool` allowed) lives in `RawFoundryAgentChatClient._prepare_options`, ensuring it applies regardless of how the client is used — through `FoundryAgent`, `Agent(client=...)`, or any custom composition.

**Public classes:**
- `RawFoundryAgentChatClient(RawOpenAIChatClient)` — Responses API client that injects agent reference and validates tools. Extension point for custom client middleware.
- `RawFoundryAgent(RawAgent)` — Agent without agent-level middleware/telemetry.
- `FoundryAgent(AgentTelemetryLayer, AgentMiddlewareLayer, RawFoundryAgent)` — Recommended production agent.

**Internal (private):**
- `_FoundryAgentChatClient` — Full client with function invocation, chat middleware, and telemetry layers. Created automatically by `FoundryAgent`; users customize via `client_type=RawFoundryAgentChatClient` or a custom subclass.

**Deprecated:**
- `AzureAIClient` — replaced by `FoundryAgent` (which uses `FoundryAgentClient` internally).
- `AzureAIAgentClient` — refers to V1 Agents Service API, no direct replacement.
- `AzureAIProjectAgentProvider` — replaced by `FoundryAgent`.
