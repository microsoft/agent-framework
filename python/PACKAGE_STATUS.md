# Python Package Status

This file tracks the current lifecycle state of the Python packages in this workspace. Some packages at later stages might have features within them that are not ready yet, these have feature stage decorators on the relevant APIs, and for `experimental` features warnings are raised. See the [Feature-level staged APIs](#feature-level-staged-apis) section below for details on which features are in which stage and where to find them.

Status is grouped into these buckets:

- `alpha` - initial release and early development packages that are not yet ready for general use
- `beta` - prerelease packages that are not currently release candidates
- `rc` - release candidate packages, these are close to ready for release but may still have some breaking changes before the final release
- `released` - stable packages without a prerelease suffix, these are stable packages that should not have breaking changes between versions
- `deprecated` - removed or deprecated packages that should not be used for new work

## Current packages

| Package | Path | State |
| --- | --- | --- |
| `agent-framework` | `python/` | `released` |
| `agent-framework-a2a` | `python/packages/a2a` | `beta` |
| `agent-framework-ag-ui` | `python/packages/ag-ui` | `released` |
| `agent-framework-anthropic` | `python/packages/anthropic` | `beta` |
| `agent-framework-azure-contentunderstanding` | `python/packages/azure-contentunderstanding` | `beta` |
| `agent-framework-azure-ai-search` | `python/packages/azure-ai-search` | `beta` |
| `agent-framework-azure-cosmos` | `python/packages/azure-cosmos` | `beta` |
| `agent-framework-azure-cosmos-memory` | `python/packages/azure-cosmos-memory` | `alpha` |
| `agent-framework-bedrock` | `python/packages/bedrock` | `beta` |
| `agent-framework-chatkit` | `python/packages/chatkit` | `beta` |
| `agent-framework-claude` | `python/packages/claude` | `beta` |
| `agent-framework-copilotstudio` | `python/packages/copilotstudio` | `beta` |
| `agent-framework-core` | `python/packages/core` | `released` |
| `agent-framework-declarative` | `python/packages/declarative` | `released` |
| `agent-framework-devui` | `python/packages/devui` | `beta` |
| `agent-framework-foundry` | `python/packages/foundry` | `released` |
| `agent-framework-foundry-hosting` | `python/packages/foundry_hosting` | `beta` |
| `agent-framework-foundry-local` | `python/packages/foundry_local` | `beta` |
| `agent-framework-gemini` | `python/packages/gemini` | `beta` |
| `agent-framework-github-copilot` | `python/packages/github_copilot` | `released` |
| `agent-framework-hosting` | `python/packages/hosting` | `alpha` |
| `agent-framework-hosting-a2a` | `python/packages/hosting-a2a` | `alpha` |
| `agent-framework-hosting-mcp` | `python/packages/hosting-mcp` | `alpha` |
| `agent-framework-hosting-responses` | `python/packages/hosting-responses` | `alpha` |
| `agent-framework-hosting-telegram` | `python/packages/hosting-telegram` | `alpha` |
| `agent-framework-hyperlight` | `python/packages/hyperlight` | `beta` |
| `agent-framework-lab` | `python/packages/lab` | `beta` |
| `agent-framework-mem0` | `python/packages/mem0` | `beta` |
| `agent-framework-mistral` | `python/packages/mistral` | `beta` |
| `agent-framework-monty` | `python/packages/monty` | `beta` |
| `agent-framework-ollama` | `python/packages/ollama` | `beta` |
| `agent-framework-openai` | `python/packages/openai` | `released` |
| `agent-framework-orchestrations` | `python/packages/orchestrations` | `released` |
| `agent-framework-purview` | `python/packages/purview` | `beta` |
| `agent-framework-redis` | `python/packages/redis` | `beta` |
| `agent-framework-tools` | `python/packages/tools` | `beta` |

## Deprecated / removed packages

| Package | Previous path | State | Notes |
| --- | --- | --- | --- |
| `agent-framework-azure-ai` | `python/packages/azure-ai` | `deprecated` | The client classes within the `azure-ai` package were renamed, sometimes changed, and moved to `agent-framework-foundry`. |

## Feature-level staged APIs

The following feature IDs have explicit feature-stage decorators on public APIs in the packages
listed below.

### Experimental features

#### `AGENT_HOOKS`

- `agent-framework-core`: `create_agent_hooks_middleware` and
  `create_agent_hooks_middleware_from_emitter` from `agent_framework/_agent_hooks.py`,
  the AGENT-HOOKS-0.1 enforcement middleware bundle, and the `MiddlewareBundle`
  container from `agent_framework/_middleware.py` that both factories produce
  (`MiddlewareBundle` itself needs no extra). Requires the opt-in
  `agent-framework-core[agent-hooks]` extra (`agent-hooks-sdk`), which is deliberately
  not part of `agent-framework-core[all]`. Known limitation: service-side (hosted) tool
  execution never passes through the framework's function-invocation seam, so the
  `pre_tool_call`/`post_tool_call` points cannot intercept it; hosted tool calls and
  outputs are surfaced in the `post_model_call` content projection instead.

#### `DECLARATIVE_AGENTS`

- `agent-framework-declarative`: declarative agent loading APIs from
  `agent_framework_declarative`, including `AgentFactory`,
  `DeclarativeLoaderError`, `ProviderLookupError`, and `ProviderTypeMapping`
  from `agent_framework_declarative/_loader.py`

#### `EVALS`

- `agent-framework-core`: exported evaluation APIs from `agent_framework`, including
  `LocalEvaluator`, `evaluate_agent`, `evaluate_workflow`, and the related evaluation types and
  helper checks defined in `agent_framework/_evaluation.py`
- `agent-framework-foundry`: `FoundryEvals`, `evaluate_traces`, and `evaluate_foundry_target`

#### `FILE_HISTORY`

- `agent-framework-core`: `FileHistoryProvider` from `agent_framework/_sessions.py`

#### `FIDES`

- `agent-framework-core`: security labeling, content indirection, policy enforcement, and secure MCP
  APIs from `agent_framework/security.py`, including `IntegrityLabel`, `ConfidentialityLabel`,
  `ContentLabel`, `ContentVariableStore`, `SecureAgentConfig`, and `SecureMCPToolProxy`

#### `FOUNDRY_TOOLS`

- `agent-framework-foundry`: released-service tool helpers on `FoundryChatClient`, currently
  `get_bing_grounding_tool` and `get_azure_ai_search_tool`

#### `FOUNDRY_PREVIEW_TOOLS`

- `agent-framework-foundry`: preview-service tool helpers on `FoundryChatClient`, including Bing
  Custom Search, SharePoint, Fabric, Memory Search, Computer Use, Browser Automation, and A2A

#### `FUNCTIONAL_WORKFLOWS`

- `agent-framework-core`: functional workflow APIs from
  `agent_framework/_workflows/_functional.py`, including `RunContext`, `step`,
  `FunctionalWorkflow`, `workflow`, and `FunctionalWorkflowAgent`

#### `HARNESS`

- `agent-framework-core`: experimental harness APIs for background agents, file access, looping,
  memory, and file-backed todo storage under `agent_framework/_harness/`

#### `MCP_LONG_RUNNING_TASKS`

- `agent-framework-core`: `MCPTaskOptions` from `agent_framework/_mcp.py`

#### `MCP_SKILLS`

- `agent-framework-core`: `MCPSkillResource`, `MCPSkill`, and `MCPSkillsSource` from
  `agent_framework/_skills.py`

#### `PROGRESSIVE_TOOLS`

- `agent-framework-core`: `FunctionInvocationContext.add_tools` and
  `FunctionInvocationContext.remove_tools` from `agent_framework/_middleware.py`

#### `SESSION_STORE`

- `agent-framework-core`: `SessionStore` and `FileSessionStore` from
  `agent_framework/_sessions.py`
- `agent-framework-foundry-hosting`: `FoundryAgentSessionStore` from
  `agent_framework_foundry_hosting/_state_store.py`

#### `TO_PROMPT_AGENT`

- `agent-framework-foundry`: `to_prompt_agent` from
  `agent_framework_foundry/_to_prompt_agent.py`

### Release-candidate features

There are currently no feature-level `rc` APIs.
