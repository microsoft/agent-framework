# Squad + DTS Sample

This sample demonstrates how to compose [Squad](https://github.com/bradygaster/squad) (a multi-agent orchestration framework for GitHub Copilot — one coordinator, many specialist sub-agents, with shared memory, routing, and structured handoffs) with [Microsoft Agent Framework (MAF)](https://github.com/microsoft/agent-framework) and [Durable Task Scheduler (DTS)](https://learn.microsoft.com/azure/durable-task-scheduler/overview) to build governance-driven, durably-orchestrated AI workflows.

> **Companion to the blog post:** ["Make It So — But Let the Computer Handle the Math"](https://tamirdresher.com/2026/05/20/deterministic-meets-squads/)

## What this sample demonstrates

- **`SquadAgent : AIAgent`** — Squad wrapped as a first-class MAF `AIAgent`, composable with any other MAF participant
- **DTS-backed durable orchestration** — A 9-executor incident-response workflow where every step is checkpointed by the Durable Task Scheduler emulator
- **Dynamic subsystem routing** — AI triage classifies the incident; conditional workflow edges route to the correct subsystem Squad (Database / Network / Auth / Payments)
- **Deterministic + non-deterministic composition** — Pure-C# enrichment executors alongside AI-powered triage, diagnosis, and per-subsystem analysis
- **Diagnose-loop** — Squad reviews accumulated context and can request another enrichment cycle (capped at `MaxDiagnosisIterations`)
- **Aspire AppHost wiring** — DTS emulator, Foundry Local LLM, and demo project all wired together via .NET Aspire
- **OpenTelemetry** — MAF workflow spans, DTS activity, Squad CLI spans, and Copilot SDK spans all converge on the Aspire dashboard

## Architecture

```
                    ┌──────────────────────────────────────────────────────┐
                    │              Durable Task Scheduler (DTS)             │
                    │  ┌──────────────────────────────────────────────┐    │
                    │  │           Incident-Response Workflow           │    │
                    │  │                                                │    │
                    │  │  triage (Squad AI)                             │    │
                    │  │    └──► enrich (C#) ◄── loop-back ────────┐  │    │
                    │  │            └──► externalComms (C#)         │  │    │
                    │  │                   ├──► DatabaseSquad (AI)  │  │    │
                    │  │                   ├──► NetworkSquad (AI)   │  │    │
                    │  │                   ├──► AuthSquad (AI)      ├──► mitigate (C#) ──► diagnose (Squad AI)
                    │  │                   └──► PaymentsSquad (AI)  │  │    │
                    │  └──────────────────────────────────────────────┘    │
                    └──────────────────────────────────────────────────────┘
                                             ▲
                    ┌────────────────────────┤
                    │  .NET Aspire AppHost    │
                    │  • DTS emulator (Docker)│
                    │  • Foundry Local LLM   │
                    │  • OTLP dashboard       │
                    └────────────────────────┘
```

## Three examples included

| Example | What it shows |
| --- | --- |
| `incident` | **Start here.** DTS-backed durable incident-response workflow: AI triage → enrichment → external comms → dynamic subsystem-squad routing → mitigation → diagnose-loop |
| `squad-as-agent` | `SquadAgent` as a plain MAF participant: Planner → Squad → Reviewer three-agent flow |
| `workflow` | Sequential MAF workflow: Writer (Foundry Local) → Squad |

## Governance pattern: `OnPermissionRequest`

Squad's `OnPermissionRequest` is policy-structured and charter-bounded — when a tool call requires
governance approval, Squad evaluates it against the `.squad/` charter definitions before approving
or denying. This is distinct from MAF Harness's `ToolApproval` (session-level auto-approval after
first confirm) and models a different point on the trust spectrum:

```
 Harness ToolApproval           Squad OnPermissionRequest
 ─────────────────────          ────────────────────────────
 session-scoped                 charter-bounded
 user confirms once             policy evaluated per request
 subsequent calls auto-approved role-based (Data / Picard / Worf / etc.)
 good for: dev workflows        good for: production-grade AI agents
```

See [Squad governance docs](https://github.com/github/copilot-extensions) for details.

## Prerequisites

1. [.NET 9 SDK](https://dotnet.microsoft.com/download)
2. [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for the DTS emulator)
3. [.NET Aspire workload](https://learn.microsoft.com/dotnet/aspire/fundamentals/setup-tooling): `dotnet workload install aspire`
4. [GitHub Copilot](https://github.com/features/copilot) subscription (Squad uses the real Copilot CLI)
5. [Foundry Local](https://github.com/microsoft/foundry-local) (optional — AppHost downloads `phi-3.5-mini` on first run, ~5 GB)

## Running the sample

### Via Aspire AppHost (recommended)

```powershell
cd dotnet/samples/02-agents/SquadWithDTS/Squad.SquadWithDTS.AppHost
dotnet run
```

This starts the Aspire dashboard, the DTS emulator (Docker), and Foundry Local. Wait for the `chat` resource to show **Healthy** before expecting console output.

**Pre-select an example:**

```powershell
$env:SQUAD_AF_EXAMPLE = "incident"   # or: squad-as-agent, workflow
$env:SQUAD_AF_TRACE   = "true"
dotnet run
```

### Standalone (advanced)

Run without AppHost using Azure OpenAI, OpenAI-compatible endpoint, or Foundry Local:

```powershell
# Azure OpenAI
$env:SQUAD_AF_PROVIDER    = "azure-openai"
$env:SQUAD_AF_ENDPOINT    = "https://<resource>.openai.azure.com/"
$env:SQUAD_AF_DEPLOYMENT  = "<deployment>"
dotnet run --project Squad.SquadWithDTS -- --example squad-as-agent

# OpenAI-compatible (e.g. Ollama)
$env:SQUAD_AF_PROVIDER = "openai-compatible"
$env:SQUAD_AF_ENDPOINT = "http://localhost:11434/v1"
$env:SQUAD_AF_MODEL    = "<model>"
dotnet run --project Squad.SquadWithDTS -- --example workflow
```

> **Note:** The `incident` example requires a running DTS emulator. Start one with Docker:
> `docker run -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest`

## SquadAgent configuration

`SquadAgent` is configurable via the `SquadAgent` section in `appsettings.json` or via environment variables using the .NET double-underscore convention:

| Option | Environment variable | Default |
|--------|---------------------|---------|
| `SquadFolderPath` | `SquadAgent__SquadFolderPath` | workspace discovery |
| `AgentId` | `SquadAgent__AgentId` | `"repo-local-squad"` |
| `AgentName` | `SquadAgent__AgentName` | `"Squad"` |
| `AgentDescription` | `SquadAgent__AgentDescription` | default text |

> **Note:** The Copilot CLI extension slug `"Squad"` is an internal protocol contract and is **not** configurable.

## Tracing

Enable Copilot SDK event tracing:

```powershell
$env:SQUAD_AF_TRACE = "true"   # console output
$env:SQUAD_AF_TRACE = "events.jsonl"  # also write JSONL to file
```

Or use the `--trace[=<path>]` CLI flag.

## Key files

| File | What it shows |
|------|---------------|
| [`Squad.SquadWithDTS/Agents/SquadAgent.cs`](Squad.SquadWithDTS/Agents/SquadAgent.cs) | `SquadAgent : AIAgent` — the MAF wrapper around GitHubCopilotAgent with OTel |
| [`Squad.SquadWithDTS/Workflows/IncidentExample.cs`](Squad.SquadWithDTS/Workflows/IncidentExample.cs) | 9-executor durable workflow graph — the deterministic backbone |
| [`Squad.SquadWithDTS/Workflows/Executors/TriageExecutor.cs`](Squad.SquadWithDTS/Workflows/Executors/TriageExecutor.cs) | AI triage via Squad: severity, subsystem, hypothesis, required evidence |
| [`Squad.SquadWithDTS/Workflows/Executors/DiagnoseExecutor.cs`](Squad.SquadWithDTS/Workflows/Executors/DiagnoseExecutor.cs) | Squad diagnose-loop: Resolved / NeedsMoreInvestigation / Inconclusive |
| [`Squad.SquadWithDTS.AppHost/AppHost.cs`](Squad.SquadWithDTS.AppHost/AppHost.cs) | Aspire host wiring DTS, Foundry Local, and the demo project |

## See also

- [Harness Agent Samples](../Harness/README.md) — `HarnessAgent` with `TodoProvider`, `AgentModeProvider`, and `ToolApproval`
- [Agent Framework samples overview](../README.md)
- [Squad + DTS blog post](https://tamirdresher.com/2026/05/20/deterministic-meets-squads/)
- [Durable Task Scheduler docs](https://learn.microsoft.com/azure/durable-task-scheduler/overview)
