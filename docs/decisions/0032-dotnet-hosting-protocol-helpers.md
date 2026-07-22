---
status: accepted
contact: rogerbarreto
date: 2026-07-08
deciders: rogerbarreto
consulted: eavanvalkenburg
informed: []
---

# .NET hosting: OpenAI Responses protocol helpers for app-owned routing

Realizes the helper-first direction of [ADR-0027](0027-hosting-channels.md) for .NET.

## Context and Problem Statement

[ADR-0027](0027-hosting-channels.md) refocused the (Python) hosting design away from a channel
framework toward **protocol conversion helpers plus optional execution state**: Agent Framework owns
protocol-native <-> run conversion, while the application owns HTTP routing, authentication,
middleware, storage, and native SDK calls.

.NET already ships `Microsoft.Agents.AI.Hosting.OpenAI`, a route-owning server that **exposes an
`AIAgent` (or workflow) as the OpenAI Responses API** (`MapOpenAIResponses` + `IResponsesService`). It
owns the routes, an in-memory response/conversation store, streaming, and lifecycle. The question is
what, if anything, .NET must add to satisfy the ADR-0027 boundary.

## Decision Drivers

- Do not reinvent conversion logic that already exists and is battle-tested in `Hosting.OpenAI`.
- Give applications a way to own their own route/auth/middleware/storage while reusing Agent Framework
  conversion (the ADR-0027 boundary).
- Keep the released public surface small.
- Stay consistent with the existing .NET hosting stack, which deliberately does **not** use the OpenAI
  SDK Responses types server-side (it hand-rolled its own wire model).

## Considered Options

1. Self-contained new package that reimplements conversion using the OpenAI SDK Responses types
   (mirrors the Python `agent-framework-hosting-responses` lineage).
2. New package that reuses `Hosting.OpenAI`'s internal converters (via `InternalsVisibleTo` or by
   moving the conversion core out).
3. Thin public helper facade **inside** `Hosting.OpenAI` over the existing internal converters, plus
   protocol-neutral execution-state holders in `Microsoft.Agents.AI.Hosting`.

### First-principles gap analysis

A capability comparison of the ADR-0027 / PR #6891 helper surface against the existing .NET stack:

| Python helper capability | .NET today | Status |
| --- | --- | --- |
| `responses_to_run` | `ResponseInput.GetInputMessages` + `InputMessage.ToChatMessage` + `OpenAIResponsesMapOptions.RunOptionsFactory` | exists, internal |
| `responses_from_run` | `AgentResponseExtensions.ToResponse` | exists, internal |
| `responses_from_streaming_run` | `AgentResponseUpdateExtensions.ToStreamingResponseAsync` + `SseJsonResult` (also renders workflow events) | exists, internal, richer |
| `responses_session_id` | continuity resolved inside `InMemoryResponsesService` | exists, internal, not standalone |
| `create_response_id` | `IdGenerator` | exists, internal |
| `AgentState` (target + store, get-or-create, callable/awaitable target) | `AgentSessionStore` (get-or-create + save + serialize + isolation) + DI container (target lifetime + async setup) | create-on-miss lives in the store; per-run instance and deferred/async target come from DI, so no separate holder is needed |
| `SessionStore` (get/set/delete) | `AgentSessionStore` + `InMemoryAgentSessionStore` | richer; `Delete` added |
| `WorkflowState` + checkpoint resume | `WorkflowCatalog`/`HostedWorkflowBuilder`; workflow events already render over Responses; `CheckpointManager` is session-keyed | partial; no per-session checkpoint cursor |
| App owns routing/auth/middleware/storage | `MapOpenAIResponses`/`IResponsesService` own routing + storage | **the one real gap** |

.NET already covers ~90% of the capability, and more richly (its streaming renderer even emits workflow
events; its session store serializes and supports per-principal isolation, neither of which Python's
in-memory `SessionStore` does). The single genuine gap is the **ownership model**: every conversion
primitive is bundled behind the route-owning server, so an application cannot own its own route and
call just the conversion.

Note on lineage: Python's Responses offering was introduced *as a channel* (PR #6580) and always used
the `openai` SDK Responses types. .NET's `Hosting.OpenAI` predates and is independent of channels and
hand-rolled its own server-side wire DTOs (the SDK's Responses types are client-shaped and awkward
server-side). So Option 1 would both reinvent a working asset and contradict the .NET codebase's own
precedent.

## Decision Outcome

Chosen option: **3. Thin public helper facade inside `Hosting.OpenAI` plus neutral state holders**,
because the only real gap is the ownership model, so the work is to *un-bundle* the existing
converters, not to rebuild them or add a package.

### Public surface

`Microsoft.Agents.AI.Hosting.OpenAI` gains a single public static facade, `OpenAIResponses`, whose
boundary is `System.Text.Json` (`JsonElement`/streamed events), matching Python's dict boundary and
keeping the hand-rolled wire DTOs internal:

- `OpenAIResponses.ToAgentRunRequest(JsonElement body)` -> messages + `AgentRunOptions?`.
- `OpenAIResponses.WriteResponse(AgentRunResponse response, string responseId, string? sessionId = null)`
  -> a Responses-shaped `JsonElement`.
- `OpenAIResponses.WriteResponseStreamAsync(IAsyncEnumerable<AgentRunResponseUpdate> updates, string responseId, ...)`
  -> Responses SSE `data:` frames.
- `OpenAIResponses.GetSessionId(JsonElement body)` -> `previous_response_id` or `conversation` id, or
  `null`. Kept **separate** from `ToAgentRunRequest` so the trust boundary is visible: choosing to use
  a request-derived key is an explicit application decision.
- `OpenAIResponses.CreateResponseId()` -> a `resp_*` id.

All helpers are side-effect-free and delegate to the existing internal converters. `MapOpenAIResponses`
public behavior is unchanged; it and the facade share one internal conversion core (an internal
`ToResponse` overload with an optional originating request is added so the facade can render without a
request object).

### Optional execution state (neutral package)

`Microsoft.Agents.AI.Hosting` gains:

- `AgentSessionStore.DeleteSessionAsync(...)` (+ `InMemoryAgentSessionStore` implementation and
  isolation-decorator passthrough): the one missing store operation.
- No agent-side holder. Applications use `AgentSessionStore` directly: `GetSessionAsync(agent, id)`
  already creates on miss and returns an independent session instance per call (so concurrent calls fork
  the same stored state rather than sharing an instance), `SaveSessionAsync(agent, id, session)` persists
  post-run (including under a newly minted id), and `DeleteSessionAsync(agent, id)` removes it. An earlier
  draft added a `HostedAgentState` holder, but once create-on-miss lives in the store and the store does no
  cross-call locking, the holder would only bind the `agent` argument, which is not enough to justify a
  public type. Any coordination for concurrent runs against the same id is the application's concern.
  (Unlike Python, whose `SessionStore` is get/set-only and whose `AgentState` therefore owns
  create-on-miss, .NET's store already owns it.)

  Python's `AgentState` carries two further responsibilities beyond create-on-miss: it accepts a callable
  or awaitable target so the host can (1) obtain a fresh agent instance per run and (2) defer expensive or
  asynchronous agent setup while keeping server construction synchronous. In .NET these two concerns are
  owned by the dependency-injection container, not by a hosting type. Per-run lifetime is expressed by the
  registration lifetime (`AddScoped`/`AddTransient` yields a fresh `AIAgent` per request or scope, resolved
  by the framework), and deferred or asynchronous construction is expressed by an async factory registration
  (for example an `async` factory delegate, `ActivatorUtilities`, or resolving the agent inside the request
  after any async warm-up), so the route handler resolves an already-built agent from the container. An
  `AIAgent` is also safe to invoke concurrently (per-turn state lives in `AgentSession`, not the agent), so
  the "fresh instance per run" motivation does not apply to it the way it does to a workflow. This is the
  deliberate asymmetry with `HostedWorkflowState` below: a `Workflow` instance is a stateful run engine that
  cannot be driven by two runners at once, so the factory/`cacheWorkflow` affordance is load-bearing there
  for correctness, whereas for agents the container already provides both per-run instances and async setup.
- `HostedWorkflowState`: a thin holder bundling a workflow target with a `CheckpointManager` and an
  internal `sessionId -> CheckpointInfo` head cursor, exposing `RunOrResumeAsync`. .NET's checkpoint
  store is already `sessionId`-keyed (unlike Python's workflow-name keying), but `CheckpointInfo` has
  no ordering, so the holder remembers the head checkpoint per session to resume. On subsequent turns it
  restores that checkpoint and runs the workflow forward with the new turn's input (mirroring the Python
  host's restore-then-run semantics), rather than continuing a halted run with no input. When the
  in-memory cursor misses (new holder / process restart) it reads the session's latest checkpoint from the
  `CheckpointManager`, so a durable manager resumes across restarts. It accepts either a single workflow
  instance (which cannot be run by two runners at once, so its turns are processed one at a time) or a
  workflow factory (`Func<CancellationToken, ValueTask<Workflow>>`). By default the factory builds a fresh
  instance per run so independent sessions run in parallel; with `cacheWorkflow: true` the factory is invoked
  once lazily and its result is cached and reused (a deferred, cached target that, like the instance, cannot
  run concurrent turns). A resume rehydrates an instance from the session's checkpoint in the shared store, so
  per-run instances still continue the same run; concurrent turns against the same session id remain the
  application's coordination responsibility.

### Scope

Responses only for v1; the facade is named so a parallel `OpenAIChatCompletions` facade can follow.
No new package, no OpenAI-SDK-typed reimplementation, no change to `MapOpenAIResponses` public
behavior.

### Security responsibilities

Consistent with ADR-0027, the application owns the trust boundary. `GetSessionId(...)` returns an
untrusted candidate key; the application must authenticate the caller and authorize/bind the id before
using it as an `AgentSessionStore` key or workflow checkpoint session id. Multi-user hosts must scope
the session store per principal (`IsolationKeyScopedAgentSessionStore`). Helpers stay side-effect-free;
persistence happens only after the run completes.

## Consequences

Positive:

- Smallest possible surface: the released addition is one facade type plus one thin workflow state
  holder and one new store method (agents use `AgentSessionStore` directly, no holder).
- No duplicated conversion; the app-owned-routing path and the route-owning server share one core.
- `MapOpenAIResponses` users are unaffected.

Negative:

- The facade's `JsonElement` boundary is less strongly typed than the internal DTOs (accepted to keep
  the wire model internal and mirror Python's dict boundary).
- Workflow resume relies on an in-memory head cursor by default; durable multi-replica hosts must
  supply their own cursor persistence.

## More Information

- Parent ADR: [ADR-0027](0027-hosting-channels.md).
- Spec: `docs/specs/003-dotnet-hosting-protocol-helpers.md`.
