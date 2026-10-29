# Python Package Status

This file tracks the current lifecycle state of the Python packages in this workspace. Some packages at later stages might have features within them that are not ready yet, these have feature stage decorators on the relevant APIs, and for `experimental` features warnings are raised. See the [Feature-level staged APIs](#feature-level-staged-apis) section below for details on which features are in which stage and where to find them.

Status is grouped into these buckets:

- `alpha` - initial release and early development packages that are not yet ready for general use
- `beta` - prerelease packages that are not currently release candidates
- `rc` - release candidate packages, these are close to ready for release but may still have some breaking changes before the final release
- `released` - stable packages without a prerelease suffix, these are stable packages that should not have breaking changes between versions
- `deprecated` - removed or deprecated packages that should not be used for new work

Lifecycle state and membership in the root `agent-framework` meta-package are independent. The `Meta package`
column records whether `pip install agent-framework` installs the workspace package:

- `yes` - included directly or through `agent-framework-core[all]`; environment markers may still limit supported
  Python versions or platforms
- `no` - installed separately when needed
- `n/a` - the root meta-package itself

## Current packages

| Package | Path | State | Meta package |
| --- | --- | --- | --- |
| `agent-framework` | `python/` | `released` | `n/a` |
| `agent-framework-a2a` | `python/packages/a2a` | `beta` | `yes` |
| `agent-framework-ag-ui` | `python/packages/ag-ui` | `released` | `yes` |
| `agent-framework-anthropic` | `python/packages/anthropic` | `beta` | `yes` |
| `agent-framework-azure-contentunderstanding` | `python/packages/azure-contentunderstanding` | `beta` | `yes` |
| `agent-framework-azure-ai-search` | `python/packages/azure-ai-search` | `beta` | `yes` |
| `agent-framework-azure-documentdb` | `python/packages/azure-documentdb` | `alpha` | `no` |
| `agent-framework-azure-cosmos` | `python/packages/azure-cosmos` | `beta` | `yes` |
| `agent-framework-azure-cosmos-memory` | `python/packages/azure-cosmos-memory` | `alpha` | `no` |
| `agent-framework-bedrock` | `python/packages/bedrock` | `beta` | `yes` |
| `agent-framework-chatkit` | `python/packages/chatkit` | `beta` | `yes` |
| `agent-framework-claude` | `python/packages/claude` | `beta` | `yes` |
| `agent-framework-copilotstudio` | `python/packages/copilotstudio` | `beta` | `yes` |
| `agent-framework-core` | `python/packages/core` | `released` | `yes` |
| `agent-framework-declarative` | `python/packages/declarative` | `released` | `yes` |
| `agent-framework-devui` | `python/packages/devui` | `beta` | `yes` |
| `agent-framework-duckdb` | `python/packages/duckdb` | `alpha` | `no` |
| `agent-framework-foundry` | `python/packages/foundry` | `released` | `yes` |
| `agent-framework-foundry-hosting` | `python/packages/foundry_hosting` | `beta` | `yes` |
| `agent-framework-foundry-local` | `python/packages/foundry_local` | `beta` | `yes` |
| `agent-framework-gemini` | `python/packages/gemini` | `beta` | `yes` |
| `agent-framework-github-copilot` | `python/packages/github_copilot` | `released` | `yes` |
| `agent-framework-hosting` | `python/packages/hosting` | `alpha` | `no` |
| `agent-framework-hosting-a2a` | `python/packages/hosting-a2a` | `alpha` | `no` |
| `agent-framework-hosting-mcp` | `python/packages/hosting-mcp` | `alpha` | `no` |
| `agent-framework-hosting-responses` | `python/packages/hosting-responses` | `alpha` | `no` |
| `agent-framework-hosting-telegram` | `python/packages/hosting-telegram` | `alpha` | `no` |
| `agent-framework-hyperlight` | `python/packages/hyperlight` | `beta` | `yes` |
| `agent-framework-lab` | `python/packages/lab` | `beta` | `no` |
| `agent-framework-mem0` | `python/packages/mem0` | `beta` | `yes` |
| `agent-framework-mistral` | `python/packages/mistral` | `beta` | `yes` |
| `agent-framework-mongodb` | `python/packages/mongodb` | `alpha` | `no` |
| `agent-framework-monty` | `python/packages/monty` | `beta` | `yes` |
| `agent-framework-nvidia` | `python/packages/nvidia` | `alpha` | `no` |
| `agent-framework-ollama` | `python/packages/ollama` | `beta` | `yes` |
| `agent-framework-openai` | `python/packages/openai` | `released` | `yes` |
| `agent-framework-oracle` | `python/packages/oracle` | `alpha` | `no` |
| `agent-framework-orchestrations` | `python/packages/orchestrations` | `released` | `yes` |
| `agent-framework-postgres` | `python/packages/postgres` | `alpha` | `no` |
| `agent-framework-purview` | `python/packages/purview` | `beta` | `yes` |
| `agent-framework-qdrant` | `python/packages/qdrant` | `alpha` | `no` |
| `agent-framework-redis` | `python/packages/redis` | `beta` | `yes` |
| `agent-framework-sql-server` | `python/packages/sql-server` | `alpha` | `no` |
| `agent-framework-tools` | `python/packages/tools` | `beta` | `yes` |
| `agent-framework-typesafe` | `python/packages/typesafe` | `alpha` | `no` |

## Deprecated / removed packages

| Package | Previous path | State | Notes |
| --- | --- | --- | --- |
| `agent-framework-azure-ai` | `python/packages/azure-ai` | `deprecated` | The client classes within the `azure-ai` package were renamed, sometimes changed, and moved to `agent-framework-foundry`. |

## Feature-level staged APIs

The following feature IDs have explicit feature-stage decorators on public APIs in the packages
listed below.

### Experimental features

#### `AGENT_HOOKS`

- `agent-framework-core`: `create_agent_hooks_middleware`,
  `create_agent_hooks_middleware_from_emitter` and the host-declaration factory
  `create_agent_hooks_middleware_from_declaration` from `agent_framework/_agent_hooks.py`,
  the AGENT-HOOKS-0.1 enforcement middleware bundle, and the `MiddlewareBundle`
  container from `agent_framework/_middleware.py` that the factories produce
  (`MiddlewareBundle` itself needs no optional dependency). Requires installing the
  `agent-hooks-sdk` package separately (0.1.0b2 or later for the host-declaration
  factory). Known limitation: service-side (hosted) tool
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
  `FunctionalWorkflowDefinition`, `FunctionalWorkflow`, `workflow`, and
  `FunctionalWorkflowAgent`

#### `HARNESS`

- `agent-framework-core`: experimental harness APIs for background agents, file access, looping,
  memory, and file-backed todo storage under `agent_framework/_harness/`

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
