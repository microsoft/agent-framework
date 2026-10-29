---
name: agent-framework-builder-dotnet
description: Use this skill when building, modifying, reviewing, evaluating, integrating, or hosting .NET (C#) applications with Microsoft Agent Framework. Use it for Agent Framework agents, harness agents, workflows, orchestrations, declarative definitions, tools, sessions, middleware, evaluation, observability, integrations, or hosting, even when the user has not yet chosen the correct framework pattern.
license: MIT
metadata:
  version: "0.1"
  project: agent-framework
  language: dotnet
---

# Agent Framework builder for .NET

Use this skill as the entry point for .NET Agent Framework application work. Choose the smallest framework pattern
that preserves the required behavior, load only the relevant references, and validate against current APIs instead of
relying on remembered preview-era syntax.

## Workflow

1. Inspect the existing solution: target frameworks, SDK version, package management (central package management or
   per-project), and installed `Microsoft.Agents.AI.*` packages and versions.
2. Choose the simplest matching path from the table below.
3. Resolve design questions only when they materially change the implementation.
4. Read only the linked reference for the selected path.
5. Implement the smallest coherent change and run the narrowest validation that exercises it.

## Core abstractions

- A **chat client** is a `Microsoft.Extensions.AI.IChatClient`. It sends messages and options to a model provider and
  returns chat responses or streaming updates. Agent Framework builds on `Microsoft.Extensions.AI` types such as
  `ChatMessage`, `AIFunction`, and `ChatOptions` instead of redefining them.
- An **agent** derives from `AIAgent` and exposes `RunAsync(...)` and `RunStreamingAsync(...)`. `ChatClientAgent` is the
  standard implementation: it wraps an `IChatClient` with instructions, tools, context providers, a chat history
  provider, and session handling. Provider packages usually create one through an `AsAIAgent(...)` extension method.
- A **harness agent** is a `HarnessAgent` from `Microsoft.Agents.AI.Harness`. It wraps a `ChatClientAgent` with an
  opinionated set of context providers and agent decorators; it is still an `AIAgent`.
- A **workflow** (`Microsoft.Agents.AI.Workflows`) coordinates explicit execution paths between executors and agents.
  `AgentWorkflowBuilder` provides standard sequential, concurrent, handoff, group-chat, and Magentic patterns over
  `AIAgent` participants. A workflow can be exposed as an `AIAgent` when callers need the agent contract.

## User interface options

- **DevUI** (`Microsoft.Agents.AI.DevUI`) is a local development, testing, and debugging tool for interacting with
  agents and workflows. Never run or deploy DevUI as a production application host.
- **AG-UI** is the application-facing protocol integration for connecting an agent or workflow to an AG-UI-compatible
  frontend. Use `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore` (server) when the product needs streaming UI events,
  tool interactions, shared state, interrupts, or resume behavior.

## Choose the build path

| Path | Choose it when | Details |
| --- | --- | --- |
| Plain agent | One model-driven actor owns the task and tools, sessions, context, and middleware are sufficient. | [Plain agents](references/agent-builder.md) |
| Harness agent | The product needs an operating loop with todos, modes, memory, approvals, skills, optional file access, background agents, shell, compaction, or repeated execution. | [Harness agents](references/harness-agent-builder.md) |
| Workflow or orchestration | Explicit stages, routing, parallelism, multiple participants, checkpointing, human input, or intermediate outputs are central to correctness. | [Workflows](references/workflow-builder.md) |
| Declarative definition | YAML should be the source of truth for a supported agent or workflow. | [Declarative definitions](references/declarative.md) |
| Evaluation | Expected outputs, tool calls, failed runs, or quality regressions are the main concern. | [Evaluation](references/evaluation.md) |
| Observability | The task is diagnosing or monitoring runtime behavior with traces, logs, and metrics. | [Observability](references/observability.md) |
| Extensibility | The application needs a custom chat client, agent, context provider, chat history provider, or middleware. | [Extensibility](references/extensibility.md) |
| Integration | The task is choosing or wiring a provider, protocol, memory store, tool service, UI, or platform extension. | [Integrations](references/integrations.md) |
| Hosting and deployment | Working Agent Framework code needs a process host, protocol endpoint, identity contract, or deployment shape. | [Hosting and deployment](references/hosting-and-deployment.md) |

## Defaults

- Target a currently supported .NET release. The packages multi-target current and recent LTS .NET versions, and some
  also support .NET Standard 2.0 and .NET Framework 4.7.2. Prefer the latest supported SDK unless the project pins one.
- Add only the narrow packages the application needs (for example `Microsoft.Agents.AI` plus one provider package)
  instead of every `Microsoft.Agents.AI.*` package.
- Package maturity differs per package: some are released, others are `-preview` or `-alpha`. Check the package's
  current status before depending on it and allow prerelease versions only when required.
- Some APIs are marked `[Experimental]` and surface diagnostic IDs (for example `MAAI001`). Suppress a diagnostic only
  deliberately, scoped to the code that uses the API, after confirming the feature may change.
- Agent Framework does not read configuration on your behalf. Read endpoints, models, and keys through
  `IConfiguration`, user secrets, or environment variables and pass them to the client explicitly. Prefer a token
  credential such as `DefaultAzureCredential` over API keys, and never hard-code secrets.
- `DefaultAzureCredential` probes several credential sources, which adds latency and risk in production. When the
  hosting identity is known (for example managed identity), use that specific credential instead.

## Current documentation lookup

Use local guidance for stable decisions and common patterns. For provider matrices, package maturity, hosted tools,
deployment details, or unfamiliar APIs, consult current sources before generating code.

The reference pages intentionally describe selection rules, invariants, and non-obvious gotchas. Use XML docs or API
reference pages for signatures and option details, and use Learn or maintained samples for end-to-end procedures.

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
| `microsoft_code_sample_search(query="...", language="csharp")` | `mslearn code-search "..." --language csharp` |

Do not fetch and execute an unpinned CLI package during a coding session. Use the
[official Microsoft Learn MCP/CLI setup](https://github.com/MicrosoftDocs/mcp) to install or update it intentionally.

Canonical starting points:

- [Agent Framework overview](https://learn.microsoft.com/agent-framework/overview/)
- [Your first agent](https://learn.microsoft.com/agent-framework/get-started/your-first-agent)
- [.NET SDK samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples)
- [Foundry-hosted Agent Framework samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/csharp/hosted-agents/agent-framework)
