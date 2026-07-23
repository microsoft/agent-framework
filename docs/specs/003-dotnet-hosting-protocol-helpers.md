---
status: accepted
contact: rogerbarreto
date: 2026-07-08
deciders: rogerbarreto
consulted: eavanvalkenburg
informed: []
---

# .NET hosting: OpenAI Responses protocol helpers and optional execution state

Implements [ADR-0032](../decisions/0032-dotnet-hosting-protocol-helpers.md), which realizes the
helper-first direction of [ADR-0027](../decisions/0027-hosting-channels.md) for .NET.

## What is the goal of this feature?

Let application developers expose an `AIAgent` or workflow over the OpenAI Responses protocol **while
owning their own ASP.NET Core route, authentication, middleware, and storage**, by calling small,
side-effect-free Agent Framework conversion helpers instead of adopting the batteries-included,
route-owning `MapOpenAIResponses` server.

Success: an application can implement a working `POST /responses` endpoint (sync + streaming) in its
own minimal-API handler using only the public helpers plus its own auth/storage, with no dependency on
`MapOpenAIResponses` or `IResponsesService`.

## What is the problem being solved?

.NET already exposes agents as the OpenAI Responses API, but only through the route-owning
`MapOpenAIResponses`/`IResponsesService`, which also owns routing, response/conversation storage,
streaming, and lifecycle. An application that wants its own routing (custom auth, middleware, status
codes, durable storage, or a different framework surface) currently has no supported way to reuse the
framework's Responses<->agent conversion. Every conversion primitive that would make this possible
already exists in `Microsoft.Agents.AI.Hosting.OpenAI` but is `internal`.

This feature un-bundles that conversion into a public, app-callable surface, and adds the minimal
execution-state helpers an app needs for session continuity and workflow checkpoint resume.

## API Changes

### `Microsoft.Agents.AI.Hosting.OpenAI` (new public static facade `OpenAIResponses`)

Boundary is `System.Text.Json`; the wire DTOs stay internal. All members are side-effect-free.

```csharp
namespace Microsoft.Agents.AI.Hosting.OpenAI;

public static class OpenAIResponses
{
    // Wire -> Agent Framework run input.
    public static OpenAIResponsesRunRequest ToAgentRunRequest(
        JsonElement body,
        OpenAIResponsesMapOptions? mapOptions = null);

    // Agent Framework result -> Responses payload (no originating request required).
    public static JsonElement WriteResponse(
        AgentResponse response,
        string responseId,
        string? sessionId = null);

    // Agent Framework stream -> Responses SSE `data:` frames.
    public static IAsyncEnumerable<string> WriteResponseStreamAsync(
        IAsyncEnumerable<AgentResponseUpdate> updates,
        string responseId,
        string? sessionId = null,
        CancellationToken cancellationToken = default);

    // Untrusted candidate continuation key: previous_response_id or conversation id (or null).
    // Kept SEPARATE from ToAgentRunRequest so using a request-derived key is an explicit decision.
    public static string? GetSessionId(JsonElement body);

    // Mint a `resp_*` id.
    public static string CreateResponseId();
}

// Result of ToAgentRunRequest.
public sealed class OpenAIResponsesRunRequest
{
    public IList<ChatMessage> Messages { get; }
    public AgentRunOptions? Options { get; }
}
```

`ToAgentRunRequest` honors `OpenAIResponsesMapOptions.RunOptionsFactory` exactly as the route model
does (by default no request setting is mapped onto the run; unsupported settings surface as a
`NotSupportedException`). `WriteResponse`/`WriteResponseStreamAsync` reuse the existing internal
`AgentResponseExtensions.ToResponse` / `AgentResponseUpdateExtensions.ToStreamingResponseAsync`
converters (an internal `ToResponse` overload with an optional originating request is added so the
facade can render without one). The streaming renderer's existing workflow-event support is preserved.

### `Microsoft.Agents.AI.Hosting` (execution state, protocol-neutral)

```csharp
namespace Microsoft.Agents.AI.Hosting;

public abstract class AgentSessionStore
{
    // ... existing members ...

    // New: the one missing store operation. Virtual (not abstract) with a default that throws
    // NotSupportedException, so existing external stores (e.g. the Foundry hosting stores) keep
    // compiling; the in-box Hosting stores override it. In-box overrides treat deleting a missing
    // session as a no-op.
    public virtual ValueTask DeleteSessionAsync(
        AIAgent agent, string conversationId, CancellationToken cancellationToken = default);
}

// Thin holder: pairs a workflow target with checkpointing + a per-session head cursor.
public sealed class HostedWorkflowState
{
    // Shared-instance mode: one instance cannot be run by two runners at once, so turns run one at a time.
    public HostedWorkflowState(Workflow workflow, CheckpointManager? checkpointManager = null);

    // Factory mode: by default a fresh instance is built per run, so independent sessions run in parallel.
    // With cacheWorkflow: true the factory is invoked once lazily and the built instance is cached and reused.
    public HostedWorkflowState(Func<CancellationToken, ValueTask<Workflow>> workflowFactory, CheckpointManager? checkpointManager = null, bool cacheWorkflow = false);

    // First turn runs forward from the start; subsequent turns restore the session's latest
    // checkpoint and run forward with the new turn's input, then record the new head checkpoint.
    public ValueTask<HostedWorkflowRunResult> RunOrResumeAsync(
        string sessionId, object input, CancellationToken ct = default);
}
```

For agents, the application uses `AgentSessionStore` directly: `GetSessionAsync(agent, id)` creates a
session on miss and returns an independent instance per call (so concurrent calls can fork the same
stored state — for example branching from a `previous_response_id` or managing several `conversation`
ids side by side — without one branch observing another's in-flight mutations). The store performs no
cross-call locking; an application that needs concurrent runs against the same id to be serialized owns
that coordination. `SaveSessionAsync(agent, id, session)` persists post-run, including under a newly
minted `resp_*` id when the protocol mints a new continuation id. `DeleteSessionAsync` uses the new
store method. No agent-side holder is needed: create-on-miss already lives in the store, so a
pass-through wrapper would only bind the `agent` argument.

`HostedWorkflowState` defaults to `CheckpointManager.CreateInMemory()` and an in-memory
`sessionId -> CheckpointInfo` cursor. Because the checkpoint store is already `sessionId`-keyed but
`CheckpointInfo` carries no ordering, the holder remembers the head checkpoint per session so
`RunOrResumeAsync` can resume the correct one. On subsequent turns it restores that checkpoint to
rehydrate accumulated workflow state and then runs the workflow forward with the new turn's input,
rather than continuing a halted run with no input (which would wait for input
indefinitely). For agent (chat-protocol) workflows the new input is accompanied by a `TurnToken` so the
turn is driven. When the in-memory cursor misses (a new holder or a process restart), the holder falls
back to `CheckpointManager.GetLatestCheckpointAsync(sessionId)`, so a durable `CheckpointManager` resumes
correctly across restarts (the default in-memory manager does not persist, so a restart starts fresh). A
resume that produces no events is logged as a warning (possible stale checkpoint or mismatched input).
Concurrency depends on how the holder is constructed. With a single shared workflow instance, concurrent runs
are not supported, because a workflow instance cannot be run by two runners at once; process turns one at a
time. With a workflow factory
(`Func<CancellationToken, ValueTask<Workflow>>`) it builds a fresh instance per run by default, so independent
sessions run in parallel; a resume rehydrates a fresh instance
from the session's checkpoint in the shared store, and concurrent turns against the same session id remain the
application's coordination responsibility. Passing `cacheWorkflow: true` instead builds the workflow once,
lazily on first use, and reuses it (a deferred, cached target that — like the instance — cannot run concurrent
turns). A
streaming counterpart, `RunOrResumeStreamingAsync`, yields the turn's `WorkflowEvent`s as they occur (for
example to render agent updates over the Responses SSE wire) and records the head checkpoint once the
stream is fully enumerated, keeping the blocking and streaming workflow paths in lockstep.
Because `RunOrResumeAsync`/`RunOrResumeStreamingAsync` are generic over the input type, the application
adapts the Responses input into the workflow's start-executor input type at the call site (for example
parsing a structured payload into a typed record), without coupling the holder to a specific wire type.

## Non-goals for v1

- ChatCompletions / Conversations helper surfaces (the facade is named so `OpenAIChatCompletions` can
  follow).
- Changing `MapOpenAIResponses` public behavior.
- A new package or an OpenAI-SDK-typed reimplementation.
- Durable/pluggable workflow checkpoint-cursor storage (in-memory default only for v1).

## Security responsibilities (application-owned)

- Authenticate the caller before using any `GetSessionId(...)` result.
- Authorize and bind the candidate id to the authenticated principal/tenant before using it as an
  `AgentSessionStore` key or a workflow checkpoint session id.
- For multi-user hosts, wrap the store with `IsolationKeyScopedAgentSessionStore` (for example via
  `UseClaimsBasedSessionIsolation(...)`), so the session namespace is scoped per principal.
- Persist session/checkpoint state only after the run or stream has completed.

## E2E Code Samples

### Agent over Responses, app-owned route (non-streaming + SSE)

```csharp
var agent = /* an AIAgent */;
AgentSessionStore sessionStore = new InMemoryAgentSessionStore(); // in-memory session store

app.MapPost("/responses", async (HttpContext http, CancellationToken ct) =>
{
    using var doc = await JsonDocument.ParseAsync(http.Request.Body, cancellationToken: ct);
    JsonElement body = doc.RootElement;

    // App owns auth + id trust decisions.
    string? candidate = OpenAIResponses.GetSessionId(body);
    string sessionId = Authorize(http.User, candidate) ?? OpenAIResponses.CreateResponseId();

    var run = OpenAIResponses.ToAgentRunRequest(body);
    var session = await sessionStore.GetSessionAsync(agent, sessionId, ct);

    string responseId = OpenAIResponses.CreateResponseId();

    if (body.TryGetProperty("stream", out var s) && s.GetBoolean())
    {
        http.Response.ContentType = "text/event-stream";
        var updates = agent.RunStreamingAsync(run.Messages, session, run.Options, ct);
        await foreach (var frame in OpenAIResponses.WriteResponseStreamAsync(updates, responseId, sessionId, ct))
        {
            await http.Response.WriteAsync(frame, ct);
            await http.Response.Body.FlushAsync(ct);
        }
        await sessionStore.SaveSessionAsync(agent, responseId, session, ct);
        return Results.Empty;
    }

    var result = await agent.RunAsync(run.Messages, session, run.Options, ct);
    await sessionStore.SaveSessionAsync(agent, responseId, session, ct);
    return Results.Json(OpenAIResponses.WriteResponse(result, responseId, sessionId));
});
```

### Workflow over Responses with checkpoint resume

Workflow checkpoint resume requires a **stable** session key across turns. `previous_response_id` changes
every turn, so it is not a valid checkpoint key; use the `conversation` id (constant for the conversation).
Because `GetSessionId(...)` prefers `previous_response_id`, a workflow route reads the conversation id
directly rather than calling `GetSessionId(...)`.

```csharp
var state = new HostedWorkflowState(workflow); // in-memory checkpoints + cursor

app.MapPost("/responses", async (HttpContext http, CancellationToken ct) =>
{
    using var doc = await JsonDocument.ParseAsync(http.Request.Body, cancellationToken: ct);
    JsonElement body = doc.RootElement;

    // Stable, authorized checkpoint key. GetConversationId(...) reads the conversation id (string or object).
    string sessionId = Authorize(http.User, GetConversationId(body))
        ?? OpenAIResponses.CreateResponseId();

    var run = OpenAIResponses.ToAgentRunRequest(body);

    // Runs forward on first call, resumes from the session's head checkpoint thereafter.
    var result = await state.RunOrResumeAsync(sessionId, run.Messages, ct);

    return Results.Json(OpenAIResponses.WriteResponse(result.AsAgentResponse(),
        OpenAIResponses.CreateResponseId(), sessionId));
});
```
