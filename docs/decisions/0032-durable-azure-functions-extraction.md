---
status: proposed
contact: cgillum
date: 2026-07-21
deciders: cgillum, vameru, ctoshniwal
consulted:
informed:
---

# Extract Durable Task and Azure Functions hosting into a separate repository

## Context and Problem Statement

The Durable Task and Azure Functions hosting integrations (`agent-framework-durabletask`,
`agent-framework-azurefunctions`, plus their samples, docs, and CI) currently live in the
`microsoft/agent-framework` (MAF) monorepo. They carry heavyweight specialized dependencies
(Azure Functions runtime, Durable Task) and need integration-test infrastructure (Functions Core
Tools, Azurite, a DTS emulator) that the core repo otherwise does not.

This ADR proposes moving them into a dedicated repository
([`microsoft/agent-framework-durable-extension`](https://github.com/microsoft/agent-framework-durable-extension))
and considers how to do so without breaking existing users who import them today.

## Decision Drivers

- **Independent lifecycle** — the hosting integrations should be able to version and release on their
  own cadence, decoupled from core (extends [ADR-0008](0008-python-subpackages.md)'s goal of keeping
  heavyweight/optional dependencies out of the main package).
- **Dependency & CI isolation** — keep core lean and its PR pipeline free of heavyweight hosting
  dependencies and integration-test prerequisites.
- **Ownership** — a dedicated repo would give the integrations their own issues, CODEOWNERS, and
  contribution flow.
- **No breaking change** — existing `from agent_framework.azure import …` code and
  `pip install agent-framework[all]` should keep working (stable-import-path guarantee, ADR-0008).

## Considered Options

1. **Keep in the MAF repo** (status quo).
2. **Move out, drop the core shim** — the extension becomes standalone; core stops re-exporting the
   types and removes them from `[all]`.
3. **Move out, keep core's backward-compat shim + `[all]`** (proposed) — the code would live in the
   new repo; core would still lazily re-export the entry-point types from `agent_framework.azure` and
   keep both packages in the `[all]` extra (resolved from PyPI).

## Decision Outcome

Proposed choice: **Option 3.** Extract the integrations for lifecycle, dependency, and ownership
isolation, while preserving the existing import surface so the move is invisible to consumers.
Option 1 forgoes the isolation benefits; Option 2 achieves them but would be a breaking change for
existing imports and the `[all]` extra.

### Consequences

- Good — would give independent release cadence, a leaner/faster core repo and CI, and clear
  ownership for the hosting integrations.
- Good — no user-visible break: existing imports and `agent-framework[all]` would continue to work
  unchanged.
- Neutral — type *definitions* would live once in the extension; the core shim would re-export only a
  curated subset of entry-point types (no metadata duplication). The extension's own samples/docs
  would import directly from `agent_framework_durabletask` / `agent_framework_azurefunctions`; the
  shim would be compatibility-only.
- Bad — **cross-repo coupling.** Core's shim correctness would track the extension's publish cadence
  (a shim symbol newer than the last published beta would not resolve until republished), and the
  .NET extension would still consume internal `Microsoft.Agents.AI.Workflows` surface, so the
  `InternalsVisibleTo("Microsoft.Agents.AI.DurableTask")` grant would need to remain in core.

## Validation

Compliance would be validated by: `uv lock --check` passing with both packages resolving from PyPI;
the shim entry-point symbols importing at runtime after `uv sync --all-extras`; and `pyright` staying
clean on `agent_framework/azure/__init__.pyi`.

A known risk is **publish-lag**: a shim symbol added to core before the extension republishes would
not resolve. For example, `WorkflowHitlContext` was added after the latest published Azure Functions
beta. The mitigation would be to omit such a symbol from the shim until the extension publishes it,
then add the entry and re-lock.

## More Information

- Related: [ADR-0008](0008-python-subpackages.md) (vendor namespaces + stable import paths),
  [ADR-0021](0021-provider-leading-clients.md) (lazy-loading gateways).
- Follow-ups: add the `WorkflowHitlContext` shim entry once the extension publishes a beta that
  exports it; document the direct-import convention in the extension's samples READMEs so samples are
  not switched back to the shim.
