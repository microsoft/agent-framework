---
status: accepted
contact: eavanvalkenburg
date: 2026-09-09
deciders: eavanvalkenburg, moonbox3
informed: chetantoshniwal, giles17, TaoChenOSU, jpalvarezl
---

# Isolate Python Lab from the released package workspace

## Context and Problem Statement

The Python root uv workspace resolves released packages and experimental Lab features in one universal lockfile.
Lab extras depend on Agent Lightning and Tau2, which currently require LiteLLM and OpenAI 2.x. That constraint prevents
the released Foundry package from using Azure AI Projects versions that require OpenAI 3.x, even though Lab is
developed and tested independently.

## Decision Drivers

- Keep experimental Lab dependencies from constraining released provider packages.
- Preserve reproducible Lab development and CI with a committed lockfile.
- Resolve Lab against released Core and provider distributions without root-workspace source overrides.
- Keep the standard `agent-framework[all]` installation free of experimental Lab modules.
- Avoid artificial uv conflict groups in the released workspace.

## Considered Options

### Keep Lab in the root workspace and cap Foundry

- Good: one environment and one lockfile.
- Bad: experimental dependencies determine the supported dependency range of released providers.
- Bad: the root workspace cannot exercise Foundry with OpenAI 3.x.

### Add mutually exclusive uv dependency groups

- Good: one lockfile can contain separate OpenAI 2.x and 3.x forks.
- Bad: requires an artificial OpenAI 3 group and explicit group switching.
- Bad: makes ordinary setup behavior depend on selecting the correct conflict branch.

### Give Lab a standalone uv project

- Good: released and experimental dependency graphs resolve independently.
- Good: Lab retains a reproducible environment and can keep its current LiteLLM and OpenAI 2.x stack.
- Good: Lab already has dedicated CI and is documented as outside `agent-framework[all]`.
- Bad: contributors and automation must run a separate Lab sync.
- Bad: the repository maintains two Python lockfiles.

## Decision Outcome

Chosen option: "Give Lab a standalone uv project", because it creates a direct dependency boundary without adding
selection rules to the released workspace.

The root workspace excludes `packages/lab`, and `agent-framework-core[all]` no longer installs
`agent-framework-lab`. Lab uses its own lockfile, uv cache key, CI installation, and dependency updates. It resolves
released Core and provider distributions so root-workspace metadata changes cannot stale the Lab lock.

### Consequences

- Root dependency resolution can select OpenAI 3.x and Azure AI Projects 2.6 without considering Lab extras.
- Lab continues to resolve LiteLLM and OpenAI 2.x until those dependencies add OpenAI 3.x support.
- Cross-package changes that require unreleased Core or provider APIs must land and release those dependencies before
  updating Lab.
- Users install Lab explicitly with `pip install agent-framework-lab`.
- Root workspace validation and dependency maintenance do not include Lab.
- Lab-only dependency changes update `python/packages/lab/uv.lock`.
