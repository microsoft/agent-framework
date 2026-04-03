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
| `agent-framework-ag-ui` | `python/packages/ag-ui` | `beta` |
| `agent-framework-anthropic` | `python/packages/anthropic` | `beta` |
| `agent-framework-azure-ai-search` | `python/packages/azure-ai-search` | `beta` |
| `agent-framework-azure-cosmos` | `python/packages/azure-cosmos` | `beta` |
| `agent-framework-azurefunctions` | `python/packages/azurefunctions` | `beta` |
| `agent-framework-bedrock` | `python/packages/bedrock` | `beta` |
| `agent-framework-chatkit` | `python/packages/chatkit` | `beta` |
| `agent-framework-claude` | `python/packages/claude` | `beta` |
| `agent-framework-copilotstudio` | `python/packages/copilotstudio` | `beta` |
| `agent-framework-core` | `python/packages/core` | `released` |
| `agent-framework-declarative` | `python/packages/declarative` | `beta` |
| `agent-framework-devui` | `python/packages/devui` | `beta` |
| `agent-framework-durabletask` | `python/packages/durabletask` | `beta` |
| `agent-framework-foundry` | `python/packages/foundry` | `released` |
| `agent-framework-foundry-local` | `python/packages/foundry_local` | `beta` |
| `agent-framework-github-copilot` | `python/packages/github_copilot` | `beta` |
| `agent-framework-lab` | `python/packages/lab` | `beta` |
| `agent-framework-mem0` | `python/packages/mem0` | `beta` |
| `agent-framework-ollama` | `python/packages/ollama` | `beta` |
| `agent-framework-openai` | `python/packages/openai` | `released` |
| `agent-framework-orchestrations` | `python/packages/orchestrations` | `beta` |
| `agent-framework-purview` | `python/packages/purview` | `beta` |
| `agent-framework-redis` | `python/packages/redis` | `beta` |

## Deprecated / removed packages

| Package | Previous path | State | Notes |
| --- | --- | --- | --- |
| `agent-framework-azure-ai` | `python/packages/azure-ai` | `deprecated` | The client classes within the `azure-ai` package were renamed, sometimes changed, and moved to `agent-framework-foundry`. |

## Feature-level staged APIs

The following feature IDs have explicit feature-stage decorators on public APIs in the packages
listed below.

### Experimental features

#### `EVALS`

- `agent-framework-core`: exported evaluation APIs from `agent_framework`, including
  `LocalEvaluator`, `evaluate_agent`, `evaluate_workflow`, and the related evaluation types and
  helper checks defined in `agent_framework/_evaluation.py`
- `agent-framework-foundry`: `FoundryEvals`, `evaluate_traces`, and `evaluate_foundry_target`

#### `SKILLS`

- `agent-framework-core`: exported skills APIs from `agent_framework`, including `Skill`,
  `SkillResource`, `SkillScript`, `SkillScriptRunner`, and `SkillsProvider` from
  `agent_framework/_skills.py`

### Release-candidate features

There are currently no feature-level `rc` APIs.
