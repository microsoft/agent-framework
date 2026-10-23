---
name: agent-framework-builder-python
description: Use this skill when building, modifying, reviewing, evaluating, integrating, or hosting Python applications with Microsoft Agent Framework. Use it for Agent Framework agents, harness agents, workflows, orchestrations, declarative definitions, tools, sessions, middleware, evaluation, observability, integrations, or hosting, even when the user has not yet chosen the correct framework pattern.
license: MIT
metadata:
  version: "0.3"
  project: agent-framework
  language: python
---

# Agent Framework builder for Python

Use this skill as the entry point for Python Agent Framework application work. Choose the smallest framework pattern
that preserves the required behavior, load only the relevant references, and validate against current APIs instead of
relying on remembered preview-era syntax.

## Workflow

1. Inspect the existing project, Python version, dependency manager, and installed Agent Framework packages.
2. Choose the simplest matching path from the table below.
3. Resolve design questions only when they materially change the implementation.
4. Read only the linked reference for the selected path.
5. Implement the smallest coherent change and run the narrowest validation that exercises it.

## Core abstractions

- A **chat client** implements the model-facing `SupportsChatGetResponse` protocol. It sends messages and options to a
  model provider and returns chat responses or streaming updates.
- An **agent** implements the `SupportsAgentRun` protocol. The standard `Agent` implementation combines a chat client
  with instructions, tools, middleware, context providers, and session handling behind one `run(...)` interface.
- A **harness agent** is a regular `Agent` assembled by `create_harness_agent`. It adds an opinionated set of context
  providers and middleware; it does not introduce a separate agent abstraction.
- A **workflow** coordinates explicit execution paths. Graph workflows and most orchestration builders can use multiple
  `SupportsAgentRun` implementations or executors. `HandoffBuilder` is the exception: its participants must be concrete
  `Agent` instances.

## User interface options

- **DevUI** is a local development, testing, and debugging tool for interacting with agents and workflows. Never run
  or deploy DevUI as a production application host.
- **AG-UI** is the application-facing protocol integration for connecting an agent or workflow to an AG-UI-compatible
  frontend. Use the `agent-framework-ag-ui` package when the product needs streaming UI events, tool interactions,
  shared state, interrupts, or resume behavior.

## Choose the build path

| Path | Choose it when | Details |
| --- | --- | --- |
| Plain agent | One model-driven actor owns the task and tools, sessions, context, and middleware are sufficient. | [Plain agents](references/agent-builder.md) |
| Harness agent | The product needs an operating loop with todos, modes, memory, approvals, skills, optional file access, background agents, shell, compaction, or repeated execution. | [Harness agents](references/harness-agent-builder.md) |
| Workflow or orchestration | Explicit stages, routing, parallelism, multiple participants, checkpointing, human input, or intermediate outputs are central to correctness. | [Workflows](references/workflow-builder.md) |
| Declarative definition | YAML or JSON should be the source of truth for a supported agent or workflow. | [Declarative definitions](references/declarative.md) |
| Evaluation | Expected outputs, tool calls, failed runs, or quality regressions are the main concern. | [Evaluation](references/evaluation.md) |
| Observability | The task is diagnosing or monitoring runtime behavior with traces, logs, and metrics. | [Observability](references/observability.md) |
| Extensibility | The application needs a custom provider, ContextProvider, or middleware component. | [Extensibility](references/extensibility.md) |
| Integration | The task is choosing or wiring a provider, protocol, memory store, tool service, UI, or platform extension. | [Integrations](references/integrations.md) |
| Hosting and deployment | Working Agent Framework code needs a process host, protocol endpoint, identity contract, or deployment shape. | [Hosting and deployment](references/hosting-and-deployment.md) |

## Defaults

- For new environments, use Python 3.11 or later within Agent Framework's currently supported range. Prefer the latest
  supported Python release or the previous release (N-1), unless a required dependency has a narrower compatibility
  range.
- Install the narrow Agent Framework distribution needed by the application instead of defaulting to the
  `agent-framework` meta-package.
- Agent Framework does not automatically read `.env` files. If the project uses one, call `load_dotenv()` explicitly
  or use the selected API's documented `env_file_path` or equivalent initialization option.

## Current documentation lookup

Use local guidance for stable decisions and common patterns. For provider matrices, package maturity, hosted tools,
deployment details, or unfamiliar APIs, consult current sources before generating code:

The reference pages intentionally describe selection rules, invariants, and non-obvious gotchas. Use public docstrings
or API reference pages for signatures and option details, and use Learn or maintained samples for end-to-end
procedures.

When the coding agent supports MCP, configure the Microsoft Learn MCP Server as a Streamable HTTP server:

```text
https://learn.microsoft.com/api/mcp
```

See [Microsoft Learn MCP Server setup](https://learn.microsoft.com/training/support/mcp-get-started) for client
configuration. The endpoint is for MCP clients and returns an error when opened directly in a browser.

1. Search Microsoft Learn with `microsoft_docs_search`.
2. Fetch the relevant page with `microsoft_docs_fetch`.
3. Use `microsoft_code_sample_search` when a current implementation example is needed.
4. If Learn MCP is unavailable and a trusted `mslearn` CLI is already installed, use the equivalent command:

| MCP tool | Preinstalled CLI |
| --- | --- |
| `microsoft_docs_search(query="...")` | `mslearn search "..."` |
| `microsoft_docs_fetch(url="...")` | `mslearn fetch "..."` |
| `microsoft_code_sample_search(query="...", language="python")` | `mslearn code-search "..." --language python` |

Do not fetch and execute an unpinned CLI package during a coding session. Use the
[official Microsoft Learn MCP/CLI setup](https://github.com/MicrosoftDocs/mcp) to install or update it intentionally.

Canonical starting points:

- [Agent Framework overview](https://learn.microsoft.com/agent-framework/overview/)
- [Your first agent](https://learn.microsoft.com/agent-framework/get-started/your-first-agent)
- [Python SDK samples](https://github.com/microsoft/agent-framework/tree/main/python/samples)
- [Foundry-hosted Agent Framework samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/agent-framework)
