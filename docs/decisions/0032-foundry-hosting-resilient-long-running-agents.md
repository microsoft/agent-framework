---
status: proposed
contact: rogerbarreto
date: 2026-07-17
deciders: Roger Barreto, Ben Thomas
consulted: Tao Chen, Ravi Teja Pidaparthi, Glenn Condron
informed: Agent Framework .NET team
---

# Resilient / durable long-running agents in Microsoft.Agents.AI.Foundry.Hosting

## Context and Problem Statement

The Foundry Hosted Agents platform can now run a hosted agent as a long job that keeps going even
when no client is connected, and that the platform restarts on its own after the container crashes
or is recycled. When the platform restarts the agent after a crash, it calls the handler again with
the same original input, tells the handler this is a restart (a flag called `IsRecovery`), and hands
back the last saved copy of the response so far (a property called `PersistedResponse`).

This behavior only applies to **background** requests. A background request is one where the caller
starts the work and checks back later, instead of holding the connection open and waiting. For a
normal foreground request (the caller waits on the line), there is no durability: if the server
crashes, the request simply fails.

The Python Microsoft Agent Framework already has a reference implementation of this, authored by Tao
Chen. A workflow (a graph of steps that saves its own progress as it advances) is hosted with two
switches turned on: one that asks the platform for crash-restart plus replay of already-sent output
(`resilient_background`), and one that lets a caller send a new message in the middle of a running
turn (`steerable_conversations`).

We want the same capability in the .NET `Microsoft.Agents.AI.Foundry.Hosting` package, so a Microsoft
Agent Framework workflow hosted as an `AIAgent` can run as a durable, crash-recoverable, and
optionally steerable Foundry Hosted Agent.

The platform primitives are provided by the Azure `Azure.AI.AgentServer.*` packages (Core
`1.0.0-beta.27`, Responses `1.0.0-beta.7`, Invocations `1.0.0-beta.6`), which expose the resilience,
recovery, and steering surface used here.

## Decision Drivers

- Match the Python reference behavior: the same recovery contract and the same opt-in shape.
- Everything is opt-in and off by default. An application that does not ask for resilience must
  behave exactly as it does today and must pay no extra cost.
- Do the durable work where it makes sense. A workflow already saves its own progress, so it can be
  reloaded and continued after a crash. A single agent keeps nothing in the middle of a turn, so the
  best it can do is redo the whole turn.
- Reuse what already exists. The `AgentFrameworkResponseHandler` already implements the streaming
  `CreateAsync(CreateResponse, ResponseContext, ...)` method that recovery uses, and workflows are
  already hosted as agents through `WorkflowBuilder(...).Build().AsAIAgent(name)`.
- Keep the public API lean. Prefer the Azure SDK types directly over wrappers that only duplicate
  them.

## Considered Options

- **A. Turn resilience on through the existing handler, workflow first.** Let the registration method
  flow the two switches straight to the Azure SDK options type (`ResponsesServerOptions`), and connect
  the workflow's own saved progress to the platform's crash-restart path
  (`ResponseContext.IsRecovery` / `PersistedResponse` / `ExitForRecoveryAsync`, and
  `ResponseEventStream.Checkpoint()` to save a snapshot at a step boundary).
- **B. A separate durable-hosting package or handler.** A new package parallel to the existing one.

## Decision Outcome

Chosen option: **A**. It matches the Python behavior, reuses the handler and the workflow-hosting path
already in place, and keeps the change additive and opt-in (off by default, identical to today's
behavior unless a switch is turned on). Option B would duplicate the handler and add a parallel
hosting path for no functional gain.

### The recovery contract (same as Python)

The platform saves the inputs but not the outputs. After a crash it calls the handler again with the
same input and with `IsRecovery` set to true. On recovery the handler seeds the outgoing stream from
the last saved snapshot (`PersistedResponse`) instead of the request, so the stream continues from the
output items already sent before the crash rather than re-emitting them, and it does not re-inject the
original input (the restored session already carries the progress, so re-injecting would enqueue a
duplicate turn and the run would never finish). On a graceful shutdown the handler calls
`ExitForRecoveryAsync()` to stop cleanly so the platform can restart it later.

### How the handler knows resilience is on (the gate)

The request context does not carry a "resilience is on" flag. The handler figures it out from two
sources:

- **Recovery branch (reload after a crash):** the only condition is `context.IsRecovery`. That flag
  is true only when resilience is on and a crash happened, so on a normal run the handler never
  touches the recovery logic and pays nothing.
- **Save-progress branch (during the first run):** the condition is resilience-on **and**
  `request.Background` **and** `request.Store`. Only when all three are true is it worth saving
  progress. The handler reads whether resilience is on by injecting `IOptions<ResponsesServerOptions>`
  and reading `ResilientBackground`. Saving a snapshot is already a no-op when the response is not a
  resilient background response, so an accidental call is harmless; the gate just avoids the wasted
  work of building a snapshot that would be thrown away.

### Resilience is configured once per process, never per agent

The Responses server (and its resilience setting) is one per process. Registering it twice throws.
Multiple agents are hosted by registering each agent as a keyed service and calling the parameterless
registration method once; they all share the one server configuration. Because of this:

- The `AddFoundryResponses(agent)` overload is a shortcut for a single agent. If the server is already
  registered, it fails with a clear message telling the developer to use the parameterless
  `AddFoundryResponses()` and register each agent with `AddKeyedSingleton<AIAgent>`. This prevents
  mixing the single-agent shortcut with more agents and prevents a confusing double registration.
- The parameterless `AddFoundryResponses()` is the path for one or many keyed agents and builds the
  server once.

### Fail early when no agent is registered

Today, if no agent is registered, the failure only appears on the first request. We surface it earlier
through the readiness probe (`/readiness`), which the platform checks before sending any traffic. A
health check named for agent registration reports healthy when at least one `AIAgent` is registered
(keyed or default) and unhealthy with an actionable message when none is. This follows the same
pattern already used for the toolbox health check.

### Where the workflow's saved progress lives

The handler persists the session at each completed output item, which for a workflow hosted as an
agent is a natural step boundary, by calling `SaveSessionAsync` on the existing `AgentSessionStore`.
The default store is the current `FileSystemAgentSessionStore`, which writes the serialized session
(including the workflow's last checkpoint) under `{HOME}/.checkpoints`, the writable directory the
platform preserves across a restart. On the next invocation `GetSessionAsync` loads that session and
the workflow resumes from its last checkpoint automatically. No separate resilient store type is
needed: saving is gated so it only happens on a resilient background turn (or a recovery turn), and a
store supplied explicitly by the developer is always respected.

### Resilient workflows require stable executor ids

A workflow checkpoint records each step by its executor id, and after a crash the workflow is rebuilt
from the same application code and matched to the checkpoint by those ids. An agent-backed step
derives its executor id from the agent's `Id`. When the caller supplies no explicit id, `Id` defaults
to a fresh random value per process, so the rebuilt workflow would use different ids and the resume
would fail deep in the engine with "the specified checkpoint is not compatible with the workflow".

For resilience to work, every agent used as a workflow step must therefore be given a stable, explicit
id (for example `chatClient.AsAIAgent(options: new() { Id = "translator", Name = "translator" })`). To
turn what would otherwise be a late, cryptic resume failure into an early, actionable signal, a second
readiness health check runs only while resilience is on. It inspects every registered workflow-host
agent and reports unhealthy, before any traffic is routed, when a step's agent has an auto-generated
id. Two small, non-public hooks make this possible without adding to the public API:

- `AIAgent.HasAutoGeneratedId` (internal): true when no explicit id was supplied (`IdCore` is null).
  This is authoritative, so a caller-supplied id that happens to be a GUID is correctly treated as
  stable. It is shared with the hosting package through `InternalsVisibleTo`.
- `WorkflowHostAgent.GetService` returns the hosted `Workflow` for an unkeyed `Workflow` request, so
  the check can read the workflow's steps and their backing agents without constructing a session.

### Two focused samples

One sample demonstrates resilience only (start a long background job, crash the process in the middle,
watch it restart and continue from its last saved progress). A second sample demonstrates steering
only (send a new message while a turn is running and watch it queue and resume at a safe point).
Keeping each sample focused on one behavior makes it easier to demonstrate and to follow.

### Applicability to Microsoft Agent Framework hosting

- **Workflow hosted as an agent (full support):** the workflow reloads its own saved progress after a
  crash and continues, so at most the step that was interrupted repeats.
- **Single agent (best-effort, with documented limits):** a single agent keeps nothing in the middle
  of a turn, so after a crash it redoes the whole turn from the start. This is correct as long as the
  turn is safe to run again. If the turn performs an action that must not happen twice (for example
  sending an email or charging a card), a small guard is needed so the redo does not repeat it.
- **Do not bother** for quick foreground chat requests: there is no durability in that mode, so the
  switches change nothing.

## Implementation plan

- **Done:** reference the `Azure.AI.AgentServer.*` versions that carry the resilient surface
  (`Directory.Packages.props`), add the local package source (`dotnet/nuget.config`).
- **Done:** lean opt-in surface. `AddFoundryResponses(...)` accepts `Action<ResponsesServerOptions>?`
  directly and passes it to `AddResponsesServer(...)`. There is no wrapper options type: the Azure SDK
  `ResponsesServerOptions` already exposes `ResilientBackground` and `SteerableConversations` (along
  with `DefaultModel`, `DefaultFetchHistoryCount`, and `ResponseAcceptor`).
- **Done:** the resilience gate (`ShouldPersistForResilience` plus `IsRecovery`), the single-registration
  guard, and the agent-registration health check on the registration method.
- **Done:** the workflow recovery bridge in `AgentFrameworkResponseHandler.CreateAsync`. On
  `IsRecovery`, seed the stream from `PersistedResponse` and skip re-injecting input; save the session
  at each completed output item so a restart resumes from the last step; call `ExitForRecoveryAsync()`
  on shutdown. Persistence uses the existing `FileSystemAgentSessionStore` (no separate resilient store
  type was required).
- **Done:** stable executor ids for resilient workflows. `AIAgent.HasAutoGeneratedId` (internal, shared
  via `InternalsVisibleTo`) plus `WorkflowHostAgent.GetService<Workflow>()` back a second readiness
  health check that fails, while resilience is on, when a workflow step's agent has an auto-generated id.
- **Done:** the two focused samples, each runnable locally with crash-and-recover or steering.
- **Planned:** single-agent best-effort behavior plus a guard hook for actions that must not repeat.

## Consequences

- Good: durable long-running agents on .NET with the same developer experience as Python. The change
  is additive and off by default, so existing hosted agents are unaffected unless they opt in.
- Good: the public API stays lean by using the Azure SDK options type directly.
- Follow-up: keep the `Azure.AI.AgentServer.*` version pins tracking the resilient surface as it
  evolves.

## Python to .NET mapping

| Python (reference) | .NET |
| --- | --- |
| `ResponsesServerOptions(resilient_background=True)` | `AddFoundryResponses(o => o.ResilientBackground = true)` on `ResponsesServerOptions` |
| `steerable_conversations=True` | `o.SteerableConversations = true` on `ResponsesServerOptions` |
| `context.is_recovery` / `context.persisted_response` | `ResponseContext.IsRecovery` / `PersistedResponse` |
| `await context.exit_for_recovery()` | `ResponseContext.ExitForRecoveryAsync()` |
| `yield stream.checkpoint()` | `ResponseEventStream.Checkpoint()` |
| `Workflow.as_agent(...)` + saved workflow progress | `WorkflowBuilder(...).Build().AsAIAgent(...)` + session saved per step in `FileSystemAgentSessionStore` |
