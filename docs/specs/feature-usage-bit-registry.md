# Feature-usage bit registry (per-language)

> **Status:** draft, accompanies [ADR-0033](../decisions/0033-feature-usage-bitmask-user-agent.md)
> and [SPEC-004](004-feature-usage-telemetry.md).
> **Version:** `1` per language · **Width:** 128-bit

This document is the proposed human-readable registry for the feature-usage
mask. Until ADR-0033 is accepted and the enums ship, these tables are a
**candidate mapping**, not a stable wire contract. After implementation, each
SDK's hand-written `FeatureBit` enum is the source of truth and these tables are
the published decoder contract. A small parity test keeps each enum and table in
sync; there is no generated artifact.

This telemetry is intentionally **transparent**: this registry is public, the
emitted value is human-decodable, and two env vars disable it (mask-only or the
whole User-Agent — see [Opt-out](#opt-out)).

## What is collected

A single 128-bit integer (the *feature mask*) describing **which Agent Framework
features were exercised** in a process — not which packages are installed. The
candidate below uses package-level bits plus selected major capabilities: core
agent/workflow/MCP features, stable skill source types, each orchestration
pattern, each individual built-in context/history provider, and distinct Foundry
surfaces. ADR-0033 still leaves the final v1 granularity open. A feature sets its
bit the first time it is genuinely used; the SDK ORs the bits together and emits
the value.

No identifiers, arguments, prompts, payloads, or user data are encoded — only the
coarse boolean \"this feature was used\" per registered bit.

## Allocation tenet

**A bit represents a stable, framework-owned capability whose adoption answers a
concrete product or support question.** It has a clear actual-use mark point in a
public entry path, and the privacy review covers the resulting distinction.

Keep imports, installation state, aliases, wrappers, internal helpers, and
implementation decorators such as caching/filtering/deduplication within their
own capability bit. Customer/runtime values — names, prompts, arguments, URLs,
identifiers, configuration choices — never become bits. A proposed distinction
without a concrete query and named decision owner waits.

## Per-language, not shared

The two tables below are **independent**. Bit indexes are **not** shared across
languages — Python bit 13 and .NET bit 13 do not mean the same thing. This is
deliberate: the User-Agent product token already names the language
(`agent-framework-python` vs `agent-framework-dotnet`), so a decoder selects the
right table from the UA and decodes against it. Each SDK numbers and evolves its
features independently — no cross-language synchronization, no null placeholders,
no \"same bit, same meaning\" rule.

## Encoding

- **Width:** 128-bit unsigned integer per language.
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
  read `vN`, pick that version; `AND` the hex mask against each bit. Unknown bits
  (newer SDK than the decoder's copy) are ignored.

## Emission scope (where the mask is sent)

- **Marking is universal:** every feature sets its bit the first time it is used,
  regardless of provider.
- **User-Agent `(feat=...)` comment — approved first-party clients only, per
  request.** Stamped only through an explicit allowlist of **Azure / Foundry**
  client pipelines whose User-Agent telemetry the team can ingest, re-evaluated
  **per request** so it reflects the live mask. It is
  **never** sent to third-party providers — a feature fingerprint must not leak
  into logs we cannot read. See [SPEC-004](004-feature-usage-telemetry.md#emission).
- **OpenTelemetry: not in v1.** Deferred primarily for privacy (a span attribute
  would broadcast the fingerprint into the user's general telemetry / third-party
  APM vendors). Left open behind the version prefix; see
  [ADR-0033](../decisions/0033-feature-usage-bitmask-user-agent.md#considered-options).

## Bit table — Python (`agent-framework-python`, version 1)

Layout: core features 0–31, orchestration patterns 32–47, and
provider/integration packages from 48.

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
| 14 | `core.file_skills_source` | File-backed skills | `agent_framework.FileSkillsSource` |
| 15 | `core.in_memory_skills_source` | In-memory / programmatic skills | `agent_framework.InMemorySkillsSource` |
| 16 | `core.mcp_skills_source` | MCP-backed skills | `agent_framework.MCPSkillsSource` |
| 17–31 | _reserved_ | core growth | — |
| 32 | `orchestration.sequential` | Sequential orchestration | `agent_framework_orchestrations.SequentialBuilder` |
| 33 | `orchestration.concurrent` | Concurrent orchestration | `agent_framework_orchestrations.ConcurrentBuilder` |
| 34 | `orchestration.group_chat` | Group-chat orchestration | `agent_framework_orchestrations.GroupChatBuilder` |
| 35 | `orchestration.magentic` | Magentic orchestration | `agent_framework_orchestrations.MagenticBuilder` |
| 36 | `orchestration.handoff` | Handoff orchestration | `agent_framework_orchestrations.HandoffBuilder` |
| 37–47 | _reserved_ | orchestration growth | — |
| 48 | `foundry.chat_client` | Foundry chat client | `agent_framework_foundry.RawFoundryChatClient` |
| 49 | `foundry.agent` | Foundry agent | `agent_framework_foundry.FoundryAgent` |
| 50 | `foundry.memory` | Foundry memory provider | `agent_framework_foundry.FoundryMemoryProvider` |
| 51 | `foundry.embedding` | Foundry embedding client | `agent_framework_foundry.RawFoundryEmbeddingClient` |
| 52 | `foundry.evals` | Foundry evaluations | `agent_framework_foundry.FoundryEvals` |
| 53 | `foundry.toolbox` | Foundry Toolbox MCP tool | `agent_framework_foundry_hosting.FoundryToolbox` |
| 54 | `foundry_local` | Foundry Local client | `agent_framework_foundry_local.FoundryLocalClient` |
| 55 | `foundry_hosting` | Foundry hosting layer | `agent_framework_foundry_hosting.ResponsesHostServer` / `InvocationsHostServer` |
| 56 | `openai` | OpenAI clients | `agent_framework_openai` |
| 57 | `anthropic` | Anthropic clients | `agent_framework_anthropic` |
| 58 | `bedrock` | AWS Bedrock clients | `agent_framework_bedrock` |
| 59 | `gemini` | Gemini chat client | `agent_framework_gemini` |
| 60 | `mistral` | Mistral embedding client | `agent_framework_mistral` |
| 61 | `ollama` | Ollama clients | `agent_framework_ollama` |
| 62 | `claude` | Claude Agent SDK agent | `agent_framework_claude` |
| 63 | `copilotstudio` | Copilot Studio agent | `agent_framework_copilotstudio` |
| 64 | `github_copilot` | GitHub Copilot agent | `agent_framework_github_copilot` |
| 65 | `azure_ai_search` | Azure AI Search context provider | `agent_framework_azure_ai_search` |
| 66 | `azure_cosmos` | Azure Cosmos history / checkpoint store | `agent_framework_azure_cosmos` |
| 67 | `azure_contentunderstanding` | Azure Content Understanding context provider | `agent_framework_azure_contentunderstanding.ContentUnderstandingContextProvider` |
| 68 | `redis` | Redis context / history provider | `agent_framework_redis` |
| 69 | `mem0` | Mem0 memory provider | `agent_framework_mem0.Mem0ContextProvider` |
| 70 | `purview` | Purview client | `agent_framework_purview.PurviewClient` |
| 71 | `a2a` | A2A agent / executor | `agent_framework_a2a.A2AAgent` / `A2AExecutor` |
| 72 | `ag_ui` | AG-UI chat client / agent | `agent_framework_ag_ui` |
| 73 | `chatkit` | ChatKit integration | `agent_framework_chatkit` |
| 74 | `devui` | DevUI served | `agent_framework_devui.serve` |
| 75 | `declarative` | Declarative agent / workflow | `agent_framework_declarative` |
| 76 | `durabletask` | Durable task runtime | `agent_framework_durabletask` |
| 77 | `azurefunctions` | Azure Functions agent host | `agent_framework_azurefunctions` |
| 78 | `tools` | Shell tools | `agent_framework_tools.shell.LocalShellTool` / `DockerShellTool` |
| 79 | `monty` | Monty CodeAct provider | `agent_framework_monty.MontyCodeActProvider` |
| 80 | `hyperlight` | Hyperlight CodeAct provider | `agent_framework_hyperlight.HyperlightCodeActProvider` |
| 81 | `azure_cosmos_memory` | Azure Cosmos DB semantic-memory provider | `agent_framework_azure_cosmos_memory.CosmosMemoryContextProvider` |
| 82 | `hosting` | App-owned agent/workflow hosting state | `agent_framework_hosting.AgentState` / `WorkflowState` |
| 83 | `hosting.a2a` | A2A hosting converters | `agent_framework_hosting_a2a.a2a_to_run` / `a2a_from_run` |
| 84 | `hosting.mcp` | MCP hosting adapters | `agent_framework_hosting_mcp.AgentMCPTool` / `WorkflowMCPTool` |
| 85 | `hosting.responses` | OpenAI Responses hosting converters | `agent_framework_hosting_responses.responses_to_run` |
| 86 | `hosting.telegram` | Telegram hosting converters | `agent_framework_hosting_telegram.telegram_to_run` |
| 87 | `lab` | Experimental Agent Framework Lab features | `agent_framework.lab` feature entry points |
| 88–127 | _reserved_ | future packages | — |

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
| 14 | `core.mcp` | MCP tasks / skills integration | `Microsoft.Agents.AI.Mcp.McpClientTaskExtensions` |
| 15 | `core.file_skills_source` | File-backed skills | `Microsoft.Agents.AI.AgentFileSkillsSource` |
| 16 | `core.in_memory_skills_source` | In-memory skills | `Microsoft.Agents.AI.AgentInMemorySkillsSource` |
| 17 | `core.inline_skill` | Inline programmatic skill | `Microsoft.Agents.AI.AgentInlineSkill` |
| 18 | `core.class_skill` | Class-based programmatic skill | `Microsoft.Agents.AI.AgentClassSkill` |
| 19 | `core.mcp_skills_source` | MCP-backed skills | `Microsoft.Agents.AI.AgentSkillsProviderBuilderMcpExtensions.UseMcpSkills` |
| 20–31 | _reserved_ | core growth | — |
| 32 | `orchestration.sequential` | Sequential orchestration | `Microsoft.Agents.AI.Workflows.SequentialWorkflowBuilder` |
| 33 | `orchestration.concurrent` | Concurrent orchestration | `Microsoft.Agents.AI.Workflows.ConcurrentWorkflowBuilder` |
| 34 | `orchestration.group_chat` | Group-chat orchestration | `Microsoft.Agents.AI.Workflows.GroupChatWorkflowBuilder` |
| 35 | `orchestration.magentic` | Magentic orchestration | `Microsoft.Agents.AI.Workflows.MagenticWorkflowBuilder` |
| 36 | `orchestration.handoff` | Handoff orchestration | `Microsoft.Agents.AI.Workflows.HandoffWorkflowBuilder` |
| 37–47 | _reserved_ | orchestration growth | — |
| 48 | `foundry.chat_client` | Foundry chat client | `Microsoft.Agents.AI.Foundry.FoundryChatClient` |
| 49 | `foundry.agent` | Foundry agent | `Microsoft.Agents.AI.Foundry.FoundryAgent` |
| 50 | `foundry.memory` | Foundry memory provider | `Microsoft.Agents.AI.Foundry.FoundryMemoryProvider` |
| 51 | `foundry.evals` | Foundry evaluations | `Microsoft.Agents.AI.Foundry.FoundryEvals` |
| 52 | `foundry.toolbox` | Foundry Toolbox MCP tool | `Microsoft.Agents.AI.Foundry.HostedMcpToolboxAITool` |
| 53 | `foundry_hosting` | Foundry hosting layer | `Microsoft.Agents.AI.Foundry.Hosting.FoundryHostingExtensions.AddFoundryResponses` |
| 54 | `openai` | OpenAI integration | `Microsoft.Agents.AI.OpenAI` |
| 55 | `anthropic` | Anthropic integration | `Microsoft.Agents.AI.Anthropic` |
| 56 | `copilotstudio` | Copilot Studio agent | `Microsoft.Agents.AI.CopilotStudio.CopilotStudioAgent` |
| 57 | `github_copilot` | GitHub Copilot agent | `Microsoft.Agents.AI.GitHub.Copilot.GitHubCopilotAgent` |
| 58 | `azure_cosmos` | Cosmos history / checkpoint store | `Microsoft.Agents.AI.CosmosChatHistoryProvider` |
| 59 | `valkey` | Valkey chat-history provider | `Microsoft.Agents.AI.Valkey.ValkeyChatHistoryProvider` |
| 60 | `mem0` | Mem0 memory provider | `Microsoft.Agents.AI.Mem0.Mem0Provider` |
| 61 | `purview` | Purview integration | `Microsoft.Agents.AI.Purview` |
| 62 | `a2a` | A2A agent | `Microsoft.Agents.AI.A2A.A2AAgent` |
| 63 | `hosting.ag_ui` | AG-UI hosting endpoint | `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.AGUIEndpointRouteBuilderExtensions.MapAGUIServer` |
| 64 | `devui` | DevUI served | `Microsoft.Agents.AI.DevUI` |
| 65 | `declarative` | Declarative agent factory | `Microsoft.Agents.AI.ChatClientPromptAgentFactory` |
| 66 | `durabletask` | Durable task runtime | `Microsoft.Agents.AI.DurableTask` |
| 67 | `azurefunctions` | Azure Functions agent host | `Microsoft.Agents.AI.Hosting.AzureFunctions` |
| 68 | `tools` | Shell tools | `Microsoft.Agents.AI.Tools.Shell.ShellExecutor` |
| 69 | `hyperlight` | Hyperlight CodeAct provider | `Microsoft.Agents.AI.Hyperlight.HyperlightCodeActProvider` |
| 70 | `hosting` | Generic AF hosting | `Microsoft.Agents.AI.Hosting.AIHostAgent` |
| 71 | `local_codeact` | Local Python CodeAct provider | `Microsoft.Agents.AI.LocalCodeAct.LocalCodeActProvider` |
| 72 | `hosting.a2a` | A2A hosting endpoints | `Microsoft.AspNetCore.Builder.A2AEndpointRouteBuilderExtensions.MapA2AJsonRpc` |
| 73 | `hosting.openai` | OpenAI-compatible hosting endpoints | `Microsoft.AspNetCore.Builder.MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions.MapOpenAIResponses` |
| 74–127 | _reserved_ | future packages | — |

## Opt-out

Two independent environment variables disable the mask:

- `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED=true|1` — drops **only** the feature
  mask; the base `agent-framework-<lang>/{version}` User-Agent is still sent.
- `AGENT_FRAMEWORK_USER_AGENT_DISABLED=true|1` — suppresses the **entire** Agent
  Framework User-Agent contribution (mask included).

The dedicated flag lets a privacy-conscious user keep contributing SDK
identity/version (useful for support and compatibility triage) while withholding
the feature-usage signal. `AGENT_FRAMEWORK_USER_AGENT_DISABLED` already exists
in Python; .NET adds both names when implementing this design.

## Governance

1. One bit per package/feature, **numbered independently per language**, in the
   table for that language. New bits are added by editing this file in a reviewed
   PR; bits are never reused within a `(language, version)`.
2. The **`FeatureBit` enum in each SDK is the source of truth** after
   implementation; the matching table here is the published contract. Add the
   enum member and table row in the same PR. A small parity test keeps them
   aligned (no generated artifact).
3. Adding a feature: apply the [allocation tenet](#allocation-tenet), name the
   concrete query/decision owner, add the enum member and table row, and mark the
   stable public entry point where actual use begins.
4. Widening beyond 128-bit or re-partitioning bumps that language's version; old
   decoders keep working because the version prefix disambiguates the mapping.

> **No machine-readable registry file ships today.** Nothing consumes one at
> runtime (each SDK owns its enum). If/when a programmatic decoder is built, this
> table is the contract to export to JSON for it then.
