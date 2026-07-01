# Feature-usage bit registry (per-language)

> **Status:** draft, accompanies [ADR-0029](../decisions/0029-feature-usage-bitmask-user-agent.md)
> and [SPEC-002](002-feature-usage-telemetry.md).
> **Version:** `1` per language · **Width:** 64-bit

This document is the human-readable registry for the feature-usage mask. The
**source of truth for each SDK is its own hand-written `FeatureBit` enum**; the
tables below are the published contract a decoder (or a human) uses to turn a
mask back into feature names. Keep the enum and the matching table in sync in the
same PR — review is the check; there is no generated artifact.

This telemetry is intentionally **transparent**: this registry is public, the
emitted value is human-decodable, and two env vars disable it (mask-only or the
whole User-Agent — see [Opt-out](#opt-out)).

## What is collected

A single 64-bit integer (the *feature mask*) describing **which Agent Framework
features were exercised** in a process — not which packages are installed.
**Granularity is per package**, with core broken out per feature — each agent,
workflow engine, MCP, orchestration pattern, and **each individual built-in
context/history provider** gets its own bit, because they serve different
purposes and we want to know which are used. A feature sets its bit the first
time it is genuinely used; the SDK ORs the bits together and emits the value.

No identifiers, arguments, prompts, payloads, or user data are encoded — only the
coarse boolean \"this feature was used\" per registered bit.

## Per-language, not shared

The two tables below are **independent**. Bit indexes are **not** shared across
languages — Python bit 13 and .NET bit 13 do not mean the same thing. This is
deliberate: the User-Agent product token already names the language
(`agent-framework-python` vs `agent-framework-dotnet`), so a decoder selects the
right table from the UA and decodes against it. Each SDK numbers and evolves its
features independently — no cross-language synchronization, no null placeholders,
no \"same bit, same meaning\" rule.

## Encoding

- **Width:** 64-bit unsigned integer per language.
- **Versioning:** the emission carries the version so a decoder knows the bit
  mapping in effect (version is per language).
- **User-Agent:** the mask is an RFC 7231 **comment** (metadata, not a product
  token), placed after the agent-framework product token:

  ```text
  agent-framework-python/1.2.3 (feat=v1.<hex_mask>)
  ```

  where `<hex_mask>` is lowercase hex, no leading zeros, no `0x` prefix. Example
  for bits 0, 1, 5 set (`0b100011 = 0x23`):

  ```text
  agent-framework-python/1.2.3 (feat=v1.23)
  ```

- **Decoding:** read the **language** from the product token, pick that table;
  read `vN`, pick that version; `AND` the hex mask against each bit. Unknown high
  bits (newer SDK than the decoder's copy) are ignored.

## Emission scope (where the mask is sent)

- **Marking is universal:** every feature sets its bit the first time it is used,
  regardless of provider.
- **User-Agent `(feat=...)` comment — first-party only, per request.** Stamped
  only on requests to **Azure / Foundry** endpoints (the telemetry the team can
  ingest), re-evaluated **per request** so it reflects the live mask. It is
  **never** sent to third-party providers — a feature fingerprint must not leak
  into logs we cannot read. See [SPEC-002](002-feature-usage-telemetry.md#emission).
- **OpenTelemetry: not in v1.** Deferred primarily for privacy (a span attribute
  would broadcast the fingerprint into the user's general telemetry / third-party
  APM vendors). Left open behind the version prefix; see
  [ADR-0029](../decisions/0029-feature-usage-bitmask-user-agent.md#considered-options).

## Bit table — Python (`agent-framework-python`, version 1)

Layout: core feature + provider bits 0–15 (contiguous, with room to grow),
orchestration patterns 16–21, provider/integration packages from 22.

| Bit | Id | Feature | Marked at (representative) |
| --- | --- | --- | --- |
| 0 | `core.agent` | Agent | `agent_framework.Agent` |
| 1 | `core.harness_agent` | Harness agent | `agent_framework.create_harness_agent` |
| 2 | `core.workflow` | Workflow engine (custom graphs) | `agent_framework.WorkflowBuilder` |
| 3 | `core.mcp` | MCP tool (any transport) | `agent_framework.MCPStdioTool` |
| 4 | `core.tool_approval` | Tool-approval harness | `agent_framework.ToolApprovalMiddleware` |
| 5 | `core.memory_provider` | Memory context provider | `agent_framework.MemoryContextProvider` |
| 6 | `core.skills_provider` | Skills provider | `agent_framework.SkillsProvider` |
| 7 | `core.file_access_provider` | File-access provider | `agent_framework.FileAccessProvider` |
| 8 | `core.compaction_provider` | Context compaction provider | `agent_framework.CompactionProvider` |
| 9 | `core.todo_provider` | Todo provider | `agent_framework.TodoProvider` |
| 10 | `core.agent_mode_provider` | Agent-mode provider | `agent_framework.AgentModeProvider` |
| 11 | `core.background_agents_provider` | Background-agents provider | `agent_framework.BackgroundAgentsProvider` |
| 12 | `core.in_memory_history_provider` | In-memory history provider | `agent_framework.InMemoryHistoryProvider` |
| 13 | `core.file_history_provider` | File history provider | `agent_framework.FileHistoryProvider` |
| 14–15 | _reserved_ | growth | — |
| 16 | `orchestration.sequential` | Sequential orchestration | `agent_framework_orchestrations.SequentialBuilder` |
| 17 | `orchestration.concurrent` | Concurrent orchestration | `agent_framework_orchestrations.ConcurrentBuilder` |
| 18 | `orchestration.group_chat` | Group-chat orchestration | `agent_framework_orchestrations.GroupChatBuilder` |
| 19 | `orchestration.magentic` | Magentic orchestration | `agent_framework_orchestrations.MagenticBuilder` |
| 20 | `orchestration.handoff` | Handoff orchestration | `agent_framework_orchestrations.HandoffBuilder` |
| 21 | _reserved_ | growth | — |
| 22 | `foundry.chat_client` | Foundry chat client | `agent_framework_foundry` `RawFoundryChatClient` |
| 23 | `foundry.agent` | Foundry agent | `agent_framework_foundry.FoundryAgent` |
| 24 | `foundry.memory` | Foundry memory provider | `agent_framework_foundry.FoundryMemoryProvider` |
| 25 | `foundry_local` | Foundry Local client | `agent_framework_foundry_local.FoundryLocalClient` |
| 26 | `foundry_hosting` | Foundry hosting layer | `agent_framework_foundry_hosting` |
| 27 | `openai` | OpenAI clients | `agent_framework_openai` |
| 28 | `anthropic` | Anthropic clients | `agent_framework_anthropic` |
| 29 | `bedrock` | AWS Bedrock clients | `agent_framework_bedrock` |
| 30 | `gemini` | Gemini chat client | `agent_framework_gemini` |
| 31 | `mistral` | Mistral embedding client | `agent_framework_mistral` |
| 32 | `ollama` | Ollama clients | `agent_framework_ollama` |
| 33 | `claude` | Claude Agent SDK agent | `agent_framework_claude` |
| 34 | `copilotstudio` | Copilot Studio agent | `agent_framework_copilotstudio` |
| 35 | `github_copilot` | GitHub Copilot agent | `agent_framework_github_copilot` |
| 36 | `azure_ai_search` | Azure AI Search context provider | `agent_framework_azure_ai_search` |
| 37 | `azure_cosmos` | Azure Cosmos history / checkpoint store | `agent_framework_azure_cosmos` |
| 38 | `azure_contentunderstanding` | Azure Content Understanding context provider | `agent_framework_azure_contentunderstanding` |
| 39 | `redis` | Redis context / history provider | `agent_framework_redis` |
| 40 | `mem0` | Mem0 memory provider | `agent_framework_mem0` |
| 41 | `purview` | Purview client | `agent_framework_purview` |
| 42 | `a2a` | A2A agent / executor | `agent_framework_a2a` |
| 43 | `ag_ui` | AG-UI chat client / agent | `agent_framework_ag_ui` |
| 44 | `chatkit` | ChatKit integration | `agent_framework_chatkit` |
| 45 | `devui` | DevUI served | `agent_framework_devui` |
| 46 | `declarative` | Declarative agent / workflow | `agent_framework_declarative` |
| 47 | `durabletask` | Durable task runtime | `agent_framework_durabletask` |
| 48 | `azurefunctions` | Azure Functions agent host | `agent_framework_azurefunctions` |
| 49 | `tools` | Shell tools | `agent_framework_tools.shell` |
| 50 | `monty` | Monty CodeAct provider | `agent_framework_monty` |
| 51 | `hyperlight` | Hyperlight CodeAct provider | `agent_framework_hyperlight` |
| 52–63 | _reserved_ | future packages | — |

## Bit table — .NET (`agent-framework-dotnet`, version 1)

| Bit | Id | Feature | Marked at (representative) |
| --- | --- | --- | --- |
| 0 | `core.agent` | Agent | `Microsoft.Agents.AI.ChatClientAgent` |
| 1 | `core.harness_agent` | Harness agent | `Microsoft.Agents.AI.HarnessAgent` |
| 2 | `core.workflow` | Workflow engine (custom graphs) | `Microsoft.Agents.AI.Workflows.WorkflowBuilder` |
| 3 | `core.tool_approval` | Tool-approval agent | `Microsoft.Agents.AI.ToolApprovalAgent` |
| 4 | `core.chat_history_memory_provider` | Chat-history memory provider | `Microsoft.Agents.AI.ChatHistoryMemoryProvider` |
| 5 | `core.file_memory_provider` | File memory provider | `Microsoft.Agents.AI.FileMemoryProvider` |
| 6 | `core.text_search_provider` | Text-search provider | `Microsoft.Agents.AI.TextSearchProvider` |
| 7 | `core.file_access_provider` | File-access provider | `Microsoft.Agents.AI.FileAccessProvider` |
| 8 | `core.skills_provider` | Skills provider | `Microsoft.Agents.AI.AgentSkillsProviderBuilder` |
| 9 | `core.compaction_provider` | Context compaction provider | `Microsoft.Agents.AI.Compaction.CompactionProvider` |
| 10 | `core.todo_provider` | Todo provider | `Microsoft.Agents.AI.TodoProvider` |
| 11 | `core.agent_mode_provider` | Agent-mode provider | `Microsoft.Agents.AI.AgentModeProvider` |
| 12 | `core.background_agents_provider` | Background-agents provider | `Microsoft.Agents.AI.BackgroundAgentsProvider` |
| 13 | `core.in_memory_history_provider` | In-memory history provider | `Microsoft.Agents.AI.InMemoryChatHistoryProvider` |
| 14–15 | _reserved_ | growth | — |
| 16 | `orchestration.sequential` | Sequential orchestration | `Microsoft.Agents.AI.Workflows.SequentialWorkflowBuilder` |
| 17 | `orchestration.concurrent` | Concurrent orchestration | `Microsoft.Agents.AI.Workflows.ConcurrentWorkflowBuilder` |
| 18 | `orchestration.group_chat` | Group-chat orchestration | `Microsoft.Agents.AI.Workflows.GroupChatWorkflowBuilder` |
| 19 | `orchestration.magentic` | Magentic orchestration | `Microsoft.Agents.AI.Workflows.MagenticWorkflowBuilder` |
| 20 | `orchestration.handoff` | Handoff orchestration | `Microsoft.Agents.AI.Workflows.HandoffWorkflowBuilder` |
| 21 | _reserved_ | growth | — |
| 22 | `foundry.chat_client` | Foundry chat client | `Microsoft.Agents.AI.Foundry.FoundryChatClient` |
| 23 | `foundry.agent` | Foundry agent | `Microsoft.Agents.AI.Foundry.FoundryAgent` |
| 24 | `foundry.memory` | Foundry memory provider | `Microsoft.Agents.AI.Foundry.FoundryMemoryProvider` |
| 25 | `foundry_hosting` | Foundry hosting layer | `Microsoft.Agents.AI.Foundry.Hosting` |
| 26 | `openai` | OpenAI integration | `Microsoft.Agents.AI.OpenAI` |
| 27 | `anthropic` | Anthropic integration | `Microsoft.Agents.AI.Anthropic` |
| 28 | `copilotstudio` | Copilot Studio agent | `Microsoft.Agents.AI.CopilotStudio.CopilotStudioAgent` |
| 29 | `github_copilot` | GitHub Copilot agent | `Microsoft.Agents.AI.GitHub.Copilot.GitHubCopilotAgent` |
| 30 | `azure_cosmos` | Cosmos history / checkpoint store | `Microsoft.Agents.AI.CosmosChatHistoryProvider` |
| 31 | `valkey` | Valkey chat-history provider | `Microsoft.Agents.AI.Valkey.ValkeyChatHistoryProvider` |
| 32 | `mem0` | Mem0 memory provider | `Microsoft.Agents.AI.Mem0.Mem0Provider` |
| 33 | `purview` | Purview integration | `Microsoft.Agents.AI.Purview` |
| 34 | `a2a` | A2A agent | `Microsoft.Agents.AI.A2A.A2AAgent` |
| 35 | `ag_ui` | AG-UI chat client | `Microsoft.Agents.AI.AGUI.AGUIChatClient` |
| 36 | `devui` | DevUI served | `Microsoft.Agents.AI.DevUI` |
| 37 | `declarative` | Declarative agent factory | `Microsoft.Agents.AI.ChatClientPromptAgentFactory` |
| 38 | `durabletask` | Durable task runtime | `Microsoft.Agents.AI.DurableTask` |
| 39 | `azurefunctions` | Azure Functions agent host | `Microsoft.Agents.AI.Hosting.AzureFunctions` |
| 40 | `tools` | Shell tools | `Microsoft.Agents.AI.Tools.Shell.ShellExecutor` |
| 41 | `hyperlight` | Hyperlight CodeAct provider | `Microsoft.Agents.AI.Hyperlight.HyperlightCodeActProvider` |
| 42 | `hosting` | Generic AF hosting | `Microsoft.Agents.AI.Hosting` |
| 43–63 | _reserved_ | future packages | — |

## Opt-out

Two independent environment variables disable the mask:

- `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED=true|1` — drops **only** the feature
  mask; the base `agent-framework-<lang>/{version}` User-Agent is still sent.
- `AGENT_FRAMEWORK_USER_AGENT_DISABLED=true|1` — suppresses the **entire** Agent
  Framework User-Agent contribution (mask included).

The dedicated flag lets a privacy-conscious user keep contributing SDK
identity/version (useful for support and compatibility triage) while withholding
the feature-usage signal.

## Governance

1. One bit per package/feature, **numbered independently per language**, in the
   table for that language. New bits are added by editing this file in a reviewed
   PR; bits are never reused within a `(language, version)`.
2. The **`FeatureBit` enum in each SDK is the source of truth**; the matching
   table here is the published contract. Add the enum member and the table row in
   the same PR — review keeps them aligned (no generated artifact).
3. Adding a feature: add the enum member, add the table row, mark it at the call
   site (the `Raw*` base / entry point so wrappers inherit it).
4. Widening beyond 64-bit or re-partitioning bumps that language's version; old
   decoders keep working because the version prefix disambiguates the mapping.

> **No machine-readable registry file ships today.** Nothing consumes one at
> runtime (each SDK owns its enum). If/when a programmatic decoder is built, this
> table is the contract to export to JSON for it then.
