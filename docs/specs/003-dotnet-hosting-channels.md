---
status: proposed
contact: RogerBarreto
date: 2026-05-28
deciders: RogerBarreto
informed: eavanvalkenburg, agent-framework dotnet contributors
---

# .NET minimal hosting core and pluggable channels

> **Posture: translate, minimal core first.** Scope mirrors [ADR-0027](../decisions/0027-hosting-channels.md)
> ("minimal hosting core and pluggable channels") exactly. The richer cross-channel behaviors (identity
> linking, authorization/allowlists, response targeting beyond the originating channel, push/codecs,
> background + continuation delivery, durable runners, retry/replay, link policy, confidentiality tiers,
> multicast) are **out of scope for v1** and tracked by [ADR-0028](../decisions/0028-hosting-linking-multicast-enhancements.md).
> The Python implementation (`agent-framework-hosting` + `agent-framework-hosting-responses`) is the
> canonical reference; this spec records the idiomatic .NET shape (`IHostApplicationBuilder` +
> `IEndpointRouteBuilder` composition on ASP.NET Core / Generic Host). Where this spec is silent, ADR-0027
> governs.

## What are the business goals for this feature?

Give .NET app authors one low-level hosting surface that exposes a single **hostable target** — an `AIAgent`
or a `Workflow` — on one or more **channels** without writing per-protocol routing or server glue, with
**explicit, debuggable session continuity** via a channel-supplied `ChannelSession(IsolationKey)`.

The first slice ships the channel-neutral host plus one channel package (Responses) so the host/channel
boundary can be implemented, tested, and explained without designing identity linking or durable delivery
at the same time.

**Success criteria (mirror ADR-0027 validation gates):**

- A sample exposes one target over the Responses channel with one `AgentFrameworkHost` and a single
  `app.MapAgentFrameworkHost()` call. No hand-written route composition.
- Channel tests prove routes, commands, startup, and shutdown callbacks are contributed by channels and
  aggregated by the host.
- Session tests prove identical `ChannelSession.IsolationKey` values resolve to the **same** cached
  `AgentSession`, and `ResetSession` rotates that mapping.
- Each channel renders only its own originating response; there is no host-level push, multicast, or
  active-channel delivery.
- A workflow sample uses an explicit checkpoint location.

## What is the problem being solved?

Every protocol surface today is its own package with its own `Map*` extension. A developer exposing one
agent over two protocols stands up two hosts and stitches lifecycle, routing, and session handling by hand.
The gap is between **owning a hostable target** and **operationalizing it on a channel**: Agent Framework
already provides agents, workflows, sessions, run inputs, streaming, and the `AIAgent` / `Workflow`
execution seams. What is missing is a small channel-neutral host that owns route/lifecycle aggregation,
target invocation, `IsolationKey -> AgentSession` resolution + caching, per-channel hooks, and workflow
checkpoint wiring — and leaves protocol shape inside channel packages.

## Decisions

1. **Posture: minimal core, translate.** Scope = ADR-0027. ADR-0028 capabilities are deferred and must not
   appear in the v1 public surface.
2. **Composition: builder-centric.** `builder.AddAgentFrameworkHost(target).AddXxxChannel(...)` then
   `app.MapAgentFrameworkHost()`.
3. **Channel contract: `abstract class Channel` + hook interfaces.** `Channel` exposes `Name`, `Path`,
   `ConfigureServices`, `Contribute`. `ChannelContribution` (a plain mutable `sealed class`) carries routes,
   endpoint filters (middleware), commands, and startup/shutdown callbacks. Optional per-channel hooks
   (`IChannelRunHook`, `IChannelResponseHook`, `IChannelStreamTransformHook`) are small separate interfaces.
4. **Channel lifecycle: two-phase.** `ConfigureServices(IServiceCollection)` at `AddXxxChannel` time;
   `Contribute(ChannelContext)` at `MapAgentFrameworkHost` time. Matches the ASP.NET Core
   `ConfigureServices` + `Configure` split.
5. **Target runner: swappable `IHostedTargetRunner`.** `AIAgentRunner` for `AIAgent`, `WorkflowRunner` for
   `Workflow`. Channels never branch on target type. (A Foundry hosted-agent runner is a later, additive
   package — not part of this slice.)
6. **Session continuity: explicit `ChannelSession(IsolationKey)`.** The host treats `IsolationKey` as an
   opaque **session partition key**, not proof of identity. Channels / host middleware must authenticate and
   authorize any externally supplied value before passing it to the host. Two channels share history only
   when they produce the same `IsolationKey`.
7. **`ChannelIdentity` is request metadata only.** In v1 it is **not** a linking, authorization, or delivery
   key. (Those uses are ADR-0028.)
8. **Host state store: new `IHostStateStore`, limited.** Owns only reset-session aliases and workflow
   checkpoint path derivation. It does **not** store linked identities, active-channel state, response
   routing, continuation records, durable runner queues, or delivery attempts (all ADR-0028). Ships
   `InMemoryHostStateStore` and `FileHostStateStore`.
9. **Hosting target: Generic Host + ASP.NET Core.** `AddAgentFrameworkHost(this IHostApplicationBuilder, target)`
   accepts both `WebApplicationBuilder` and `HostApplicationBuilder`. HTTP routes via
   `app.MapAgentFrameworkHost(this IEndpointRouteBuilder)`. Non-HTTP channels auto-start via `IHostedService`.
10. **Naming: literal port.** Host type `AgentFrameworkHost`; extensions `AddAgentFrameworkHost(...)` /
    `MapAgentFrameworkHost(...)`; channel-add extensions `AddResponsesChannel(...)`.
11. **Isolation context propagation: `IsolationKeys.Current` (AsyncLocal) + DI `IIsolationKeysAccessor`,**
    lifted from `x-agent-user-isolation-key` / `x-agent-chat-isolation-key` by a host-applied endpoint filter
    **only when the Foundry hosting environment flag (`FOUNDRY_HOSTING_ENVIRONMENT`) is present**. Distinct
    from the app-level `ChannelSession.IsolationKey`. Mirrors the Python host's Foundry isolation middleware;
    reusing the header names does not make this the supported Foundry Hosted Agents surface.
12. **Workflow channel surface: workflow-agnostic channels.** Carried by `WorkflowRunner : IHostedTargetRunner`,
    generic `HostedRunResult<TResult>`, free-form `ChannelRequest.Attributes` (reserved key
    `workflow.checkpoint_id` for caller-supplied checkpoint resume), and workflow checkpoint storage on
    `WorkflowBuilder`. The host does not own a continuation store in v1.
13. **v1 scope: net-new only.** Existing `Hosting.OpenAI` / `Hosting.A2A*` / `Hosting.AGUI.AspNetCore` /
    `Hosting.AzureFunctions` / `Foundry.Hosting` `Map*` extensions stay untouched.

## Package layout

### v1 NuGet packages (new)

```
Microsoft.Agents.AI.Hosting.Channels                 (core)
├── AgentFrameworkHost
├── AgentFrameworkHostOptions                         (StatePaths)
├── IAgentFrameworkHostBuilder
├── HostApplicationBuilderHostingChannelsExtensions   (AddAgentFrameworkHost on IHostApplicationBuilder)
├── EndpointRouteBuilderHostingChannelsExtensions     (MapAgentFrameworkHost on IEndpointRouteBuilder)
├── Channel                                           (abstract class)
├── ChannelContribution                               (sealed class; mutable get/set)
├── ChannelCommand                                    (Name / Description / Handler)
├── ChannelCommandContext                             (Request / Reply callback)
├── ChannelRequest                                    (sealed class; ctor Channel/Operation/Input + copy ctor)
├── ChannelSession                                    (sealed class; Key / ConversationId / IsolationKey nullable + copy ctor)
├── SessionMode                                       (enum: Auto / Required / Disabled)
├── ChannelIdentity                                   (sealed class; ctor Channel/NativeId; request metadata only)
├── HostedRunResult                                   (abstract class; non-generic base)
├── HostedRunResult<TResult>                          (sealed class; generic envelope)
├── HostedStreamItem                                  (abstract class; Update / Event / Completed)
├── ChannelContext                                    (sealed class; host-constructed run/stream surface)
├── IChannelRunHook        + ChannelRunHookContext
├── IChannelResponseHook   + ChannelResponseContext
├── IChannelStreamTransformHook
├── IHostedTargetRunner
│   ├── AIAgentRunner
│   └── WorkflowRunner
├── WorkflowRunResult                                 (Completed / AwaitingInput / Failed)
├── IHostStateStore                                   (reset-session aliases + checkpoint path only)
├── InMemoryHostStateStore
├── FileHostStateStore
├── HostStatePathOptions                              (Root / Aliases / Checkpoints)
├── IsolationKeys                                     (sealed class; Current AsyncLocal + Foundry header consts)
└── IIsolationKeysAccessor                            (DI accessor; internal Foundry-flag-gated lift filter)

Microsoft.Agents.AI.Hosting.Channels.Responses
├── ResponsesChannel
├── ResponsesChannelOptions                           (Path / RunHook / ResponseHook / StreamTransformHook)
└── AgentFrameworkHostBuilderResponsesExtensions      (AddResponsesChannel)
```

### v1 NuGet packages (untouched)

`Microsoft.Agents.AI.Hosting.OpenAI`, `.Hosting.A2A`, `.Hosting.A2A.AspNetCore`, `.Hosting.AGUI.AspNetCore`,
`.Hosting.AzureFunctions`, `.Foundry.Hosting`. The Responses channel reuses Responses models / parsing from
`Microsoft.Agents.AI.Hosting.OpenAI` where practical rather than reimplementing the wire format.

## API changes

> Draft signatures; nullability and `Experimental` attributes sharpen during implementation. Every public
> type ships the standard copyright header and is `[Experimental(...)]` for the v1 release.
>
> **Namespace convention.** Public types live in `Microsoft.Agents.AI.Hosting.Channels` (and `*.Responses`).
> `IHostApplicationBuilder` extensions live in `namespace Microsoft.Extensions.Hosting`; `IEndpointRouteBuilder`
> extensions in `namespace Microsoft.AspNetCore.Builder`; channel-add extensions in
> `Microsoft.Agents.AI.Hosting.Channels`.

### Host + builder

```csharp
namespace Microsoft.Agents.AI.Hosting.Channels;

public sealed class AgentFrameworkHost
{
    public IServiceProvider Services { get; }
    public IReadOnlyList<Channel> Channels { get; }
    public IHostedTargetRunner TargetRunner { get; }
    public IHostStateStore StateStore { get; }
    public AgentFrameworkHostOptions Options { get; }

    public ValueTask<HostedRunResult> RunAsync(ChannelRequest request, CancellationToken cancellationToken = default);
    public IAsyncEnumerable<HostedStreamItem> StreamAsync(ChannelRequest request, CancellationToken cancellationToken = default);

    // Rotates the active session-id alias for an isolation key (host-tracked channels' /new-style commands).
    public ValueTask ResetSessionAsync(string isolationKey, CancellationToken cancellationToken = default);
}

public sealed class AgentFrameworkHostOptions
{
    public HostStatePathOptions? StatePaths { get; set; }
}
```

```csharp
namespace Microsoft.Extensions.Hosting;

public static class HostApplicationBuilderHostingChannelsExtensions
{
    public static IAgentFrameworkHostBuilder AddAgentFrameworkHost(
        this IHostApplicationBuilder builder, AIAgent target, Action<AgentFrameworkHostOptions>? configure = null);

    public static IAgentFrameworkHostBuilder AddAgentFrameworkHost(
        this IHostApplicationBuilder builder, Workflow target, Action<AgentFrameworkHostOptions>? configure = null);

    public static IAgentFrameworkHostBuilder AddAgentFrameworkHost<TTarget>(
        this IHostApplicationBuilder builder, Func<IServiceProvider, TTarget> targetFactory,
        Action<AgentFrameworkHostOptions>? configure = null) where TTarget : class;
}
```

```csharp
namespace Microsoft.AspNetCore.Builder;

public static class EndpointRouteBuilderHostingChannelsExtensions
{
    public static IEndpointConventionBuilder MapAgentFrameworkHost(this IEndpointRouteBuilder endpoints);
}
```

```csharp
namespace Microsoft.Agents.AI.Hosting.Channels;

public interface IAgentFrameworkHostBuilder
{
    IServiceCollection Services { get; }
    AgentFrameworkHostOptions Options { get; }

    IAgentFrameworkHostBuilder AddChannel(Channel channel);
    IAgentFrameworkHostBuilder AddChannel<TChannel>(Func<IServiceProvider, TChannel> factory) where TChannel : Channel;

    IAgentFrameworkHostBuilder UseHostStateStore<TStore>() where TStore : class, IHostStateStore;
}
```

### Channel contract

```csharp
public abstract class Channel
{
    public abstract string Name { get; }
    public virtual string Path => string.Empty;       // host wraps Routes in endpoints.MapGroup(Path)
    public virtual void ConfigureServices(IServiceCollection services) { }
    public abstract ChannelContribution Contribute(ChannelContext context);
}

public sealed class ChannelContribution
{
    public IReadOnlyList<Action<IEndpointRouteBuilder>> Routes { get; set; } = [];
    public IReadOnlyList<IEndpointFilter> EndpointFilters { get; set; } = [];   // host-level middleware
    public IReadOnlyList<ChannelCommand> Commands { get; set; } = [];
    public Func<CancellationToken, ValueTask>? OnStartup { get; set; }
    public Func<CancellationToken, ValueTask>? OnShutdown { get; set; }
}

// Host-owned, channel-consumed: a sealed class with an internal constructor, not an interface
// (channels only consume it, so the interface added nothing).
public sealed class ChannelContext
{
    internal ChannelContext(IServiceProvider services, AgentFrameworkHost host);

    public IServiceProvider Services { get; }
    public AgentFrameworkHost Host { get; }
    public IHostStateStore StateStore { get; }

    public ValueTask<HostedRunResult> RunAsync(ChannelRequest request, CancellationToken cancellationToken = default);
    public IAsyncEnumerable<HostedStreamItem> StreamAsync(ChannelRequest request, CancellationToken cancellationToken = default);
}
```

> Hooks are discovered by the host: a channel implements `IChannelRunHook` / `IChannelResponseHook` /
> `IChannelStreamTransformHook` directly, or routes app-supplied hooks through its options object
> (`ResponsesChannelOptions.RunHook`, etc.). `ChannelRunHook` runs after channel parsing and before target
> invocation; `ChannelResponseHook` runs after invocation and before the originating channel serializes;
> `ChannelStreamTransformHook` is applied by the host while the channel consumes streamed updates.

### Channel-neutral request envelope

```csharp
public sealed class ChannelRequest
{
    public ChannelRequest(string channel, string operation, object input);   // required members -> ctor params
    public ChannelRequest(ChannelRequest other);                             // copy constructor (replaces `with`)

    public string Channel { get; }                           // get-only
    public string Operation { get; }                         // get-only ("message.create", "command.invoke", ...)
    public object Input { get; set; }                        // string / ChatMessage / IEnumerable<ChatMessage> / workflow input
    public ChannelSession? Session { get; set; }
    public ChannelIdentity? Identity { get; set; }           // request metadata only
    public string? ConversationId { get; set; }
    public ChatOptions? Options { get; set; }
    public SessionMode SessionMode { get; set; } = SessionMode.Auto;
    public IReadOnlyDictionary<string, object?> Metadata { get; set; } = ImmutableDictionary<string, object?>.Empty;
    public IReadOnlyDictionary<string, object?> Attributes { get; set; } = ImmutableDictionary<string, object?>.Empty;
    public bool Stream { get; set; }
}

public sealed class ChannelSession
{
    public ChannelSession();
    public ChannelSession(ChannelSession other);             // copy constructor (replaces `with`)

    public string? Key { get; set; }                         // caller-supplied (previous_response_id, ...)
    public string? ConversationId { get; set; }
    public string? IsolationKey { get; set; }                // opaque session partition key
    public IReadOnlyDictionary<string, object?> Attributes { get; set; } = ImmutableDictionary<string, object?>.Empty;
}

public sealed class ChannelIdentity
{
    public ChannelIdentity(string channel, string nativeId);

    public string Channel { get; }                           // get-only
    public string NativeId { get; }                          // get-only (the USER id, never the chat/conversation id)
    public IReadOnlyDictionary<string, string> Attributes { get; set; } = ImmutableDictionary<string, string>.Empty;
}

public enum SessionMode { Auto, Required, Disabled }
```

### Results + streaming

```csharp
public abstract class HostedRunResult
{
    public ChannelSession? Session { get; set; }
    public abstract object? ResultObject { get; }
}

public sealed class HostedRunResult<TResult> : HostedRunResult
{
    public HostedRunResult(TResult result);
    public TResult Result { get; }                           // get-only
    public override object? ResultObject => this.Result;
    public HostedRunResult<TNew> Replace<TNew>(TNew newResult) => new(newResult) { Session = this.Session };
}

public abstract class HostedStreamItem { private protected HostedStreamItem() { } }

public sealed class HostedStreamUpdate : HostedStreamItem     // normalized agent stream
{
    public HostedStreamUpdate(AgentResponseUpdate update);
    public AgentResponseUpdate Update { get; }
}

public sealed class HostedStreamEvent : HostedStreamItem      // protocol/workflow events
{
    public HostedStreamEvent(object @event);
    public object Event { get; }
}

public sealed class HostedStreamCompleted : HostedStreamItem  // terminal
{
    public HostedStreamCompleted(HostedRunResult result);
    public HostedRunResult Result { get; }
}
```

### Host state store (limited)

```csharp
public interface IHostStateStore
{
    // Session-alias rotation backing ResetSessionAsync (host-tracked channels' /new).
    ValueTask RotateSessionAliasAsync(string isolationKey, CancellationToken cancellationToken);
    ValueTask<string?> GetActiveSessionAliasAsync(string isolationKey, CancellationToken cancellationToken);

    // Persistent workflow checkpoint location for an isolation key, or null when this store does not persist
    // checkpoints (e.g. the in-memory store). Implementations reject path-traversal patterns in the key.
    ValueTask<string?> GetCheckpointLocationAsync(string isolationKey, CancellationToken cancellationToken);
}

public sealed class HostStatePathOptions
{
    public string? Root { get; set; }               // shorthand: derives subpaths if unset
    public string? AliasesPath { get; set; }        // reset-session aliases
    public string? CheckpointsPath { get; set; }    // workflow checkpoint derivation root
}
```

> `InMemoryHostStateStore` (default) returns `null` from `GetCheckpointLocationAsync` (no persistent
> checkpoints). `FileHostStateStore` is `IDisposable`: it takes an exclusive single-owner OS lock on its root
> directory (a second store over the same directory fails fast), validates the isolation key against a
> path-traversal denylist (no separators/NUL, not dot-only/absolute/drive-rooted), and returns a per-key
> checkpoint directory. There is no continuation store, link grant, last-seen ledger, or identity registry
> in v1.

### Hosted target runner

```csharp
public interface IHostedTargetRunner
{
    ValueTask<HostedRunResult> RunAsync(ChannelRequest request, CancellationToken cancellationToken);
    IAsyncEnumerable<HostedStreamItem> StreamAsync(ChannelRequest request, CancellationToken cancellationToken);
}

public sealed class AIAgentRunner(AIAgent agent, IHostStateStore stateStore) : IHostedTargetRunner { /* ... */ }
public sealed class WorkflowRunner(Workflow workflow, IHostStateStore? stateStore = null) : IHostedTargetRunner { /* ... */ }
```

`AIAgentRunner` resolves an `AgentSession` per isolation key, enforces `SessionMode.Required`, and forwards
`ChannelRequest.Options` (wrapped in `ChatClientAgentRunOptions`). `WorkflowRunner` drives
`InProcessExecution.OpenStreamingAsync`, sends the input by its runtime type plus a `TurnToken` (so agent-based
workflows take a turn), collects terminal `WorkflowOutputEvent`s (excluding streaming `AgentResponseUpdateEvent`
deltas), and pauses on `RequestInfoEvent` into `WorkflowRunResult { Status = AwaitingInput }`. When the state
store yields a persistent checkpoint location for the request's isolation key, the run is checkpointed there
(via a `FileSystemJsonCheckpointStore` + `CheckpointManager`); the committed checkpoint id is surfaced on the
result session attributes (`"workflow.checkpoint_id"`), and a request carrying that id on
`ChannelRequest.Attributes` resumes from it (rehydrate, then apply the new input).

### Isolation keys

```csharp
public sealed class IsolationKeys
{
    public IsolationKeys(string? userKey, string? chatKey);

    public string? UserKey { get; }                          // get-only
    public string? ChatKey { get; }                          // get-only
    public bool IsEmpty => this.UserKey is null && this.ChatKey is null;

    public static IsolationKeys? Current { get; set; }       // AsyncLocal-backed, scoped to the request flow

    public const string UserHeader = "x-agent-user-isolation-key";
    public const string ChatHeader = "x-agent-chat-isolation-key";
}

public interface IIsolationKeysAccessor { IsolationKeys? Current { get; } }
```

An internal `IsolationKeysEndpointFilter` lifts the two headers into `IsolationKeys.Current` for the request
and resets it afterwards. `MapAgentFrameworkHost` applies the filter to every channel route **only when
`FOUNDRY_HOSTING_ENVIRONMENT` is set**; absent the flag (or absent both headers) the request passes through and
`Current` stays `null`. `AddAgentFrameworkHost` registers `IIsolationKeysAccessor` so Foundry-aware providers
read the keys without each channel parsing headers. Mirrors the Python host's `_FoundryIsolationASGIMiddleware`.

## Responses channel

`Microsoft.Agents.AI.Hosting.Channels.Responses` maps OpenAI Responses-shaped requests and streams onto the
host and renders Responses-compatible output, reusing the Responses models / converters / streaming
generators from `Microsoft.Agents.AI.Hosting.OpenAI` where practical.

```csharp
public sealed class ResponsesChannel : Channel
{
    public ResponsesChannel(ResponsesChannelOptions options);
    public override string Name => "responses";
    public override string Path => this._options.Path;       // default "/responses"
    public override ChannelContribution Contribute(ChannelContext context);  // POST {Path}
}

public sealed class ResponsesChannelOptions
{
    public string Path { get; set; } = "/responses";        // "" mounts at the app root
    public IChannelRunHook? RunHook { get; set; }
    public IChannelResponseHook? ResponseHook { get; set; }
    public IChannelStreamTransformHook? StreamTransformHook { get; set; }
}
```

- A Responses request maps to a `ChannelRequest` (`Operation = "message.create"`, `Input` = parsed input
  items incl. `input_text` / `input_image` / `input_file` / hosted-file content, generation options remapped
  to `ChatOptions` and stripped by the default run hook, identity from `safety_identifier`/`user` — a
  non-string identifier is ignored rather than rejected, `Session.IsolationKey` = `previous_response_id` ->
  Foundry chat key -> minted `response_id`). Malformed input is rejected with HTTP 422.
- The originating Responses response is rendered by the channel (`ResponsesOutputRenderer`) as typed output
  items: assistant text coalesced into `message` items, `reasoning`, `function_call`, `function_call_output`
  (with media results projected into `input_text` / `input_image` / `input_file` parts), `mcp_call`,
  `code_interpreter_call`, `image_generation_call`, and `mcp_approval_request` / `mcp_approval_response`.
  Adjacent call/result content for the same id coalesces into a single item (across messages too), and a
  provider raw item carried on `AIContent.RawRepresentation` is passed through verbatim, with a later raw item
  of the same `(type, id)` replacing an earlier partial. Workflow outputs (messages, agent responses, or bare
  content) project through the same renderer. Streaming emits the richer SSE sequence — `response.created`,
  `response.output_item.added`, `response.content_part.added`, `response.output_text.delta`,
  `response.output_text.done`, `response.content_part.done`, `response.output_item.done`, `response.completed`
  — and additionally emits `response.reasoning_text.delta`/`.done` and
  `response.function_call_arguments.delta`/`.done` plus dedicated output items for non-text streamed content;
  the completed envelope is rendered from the accumulated streamed updates when no final agent response is
  available. It applies the `IChannelResponseHook` to the final streamed result, and on a mid-stream error
  emits a `response.failed` event (not a post-headers JSON error). The host applies
  `IChannelStreamTransformHook` as updates are consumed. The deferred SSE stream runs under the request's
  parent trace span.
- For a `Workflow` target, the run hook prepares typed workflow input; agent-based workflows are driven with a
  `TurnToken` so their replies render, and the channel renders `RequestInfoEvent` as the protocol's
  awaiting-input shape. Resume is caller-driven via the surfaced checkpoint id: the runner rehydrates from the
  checkpoint and then applies the new input so the resumed run advances.

## E2E code samples

### Sample 1: Responses agent on one host

```csharp
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.Hosting;
using OpenAI.Chat;

var builder = WebApplication.CreateBuilder(args);

AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetChatClient(deployment)
    .AsAIAgent(name: "Concierge", instructions: "You are a helpful concierge.");

builder.AddAgentFrameworkHost(agent)
    .AddResponsesChannel();

var app = builder.Build();
app.MapAgentFrameworkHost();
app.Run();
```

### Sample 2: Responses-hosted workflow with run-hook input prep + checkpoints

```csharp
var workflow = new WorkflowBuilder(checkpointStorage: new FileCheckpointStorage("./.checkpoints"))
    .AddExecutor(/* intake */)
    .Build();

builder.AddAgentFrameworkHost(workflow, o => o.StatePaths = new HostStatePathOptions { Root = "./.afhost" })
    .AddResponsesChannel(o => o.RunHook = new MyWorkflowInputRunHook());

var app = builder.Build();
app.MapAgentFrameworkHost();
app.Run();
```

The run hook turns the parsed Responses input into the workflow's typed input. If the workflow pauses on a
`RequestInfoEvent`, the channel renders an awaiting-input response; the caller resumes by re-invoking with
`attributes["workflow.checkpoint_id"]`.

## Test strategy

| Layer | Test type | Proves |
|---|---|---|
| Channel contract | Unit | `Contribute` returns routes/commands/lifecycle; host aggregates them under `MapGroup(Path)`. |
| Host composition | Unit | `AddAgentFrameworkHost` + `AddResponsesChannel` produces a host whose `Channels` list matches; `ConfigureServices` runs pre-Build, `Contribute` post-Build. |
| Session continuity | Unit | Identical `IsolationKey` resolves to the same cached `AgentSession`; `ResetSessionAsync` rotates the alias. |
| `ResponsesChannel` | Integration (`TestServer`) | Responses request round-trips the full `ChatMessage` content list (no lossy collapse); SSE stream renders. |
| Workflow path | Integration | `RequestInfoEvent` renders awaiting-input; re-invoke with `workflow.checkpoint_id` resumes. |
| Isolation lift | Unit + Integration | `IsolationKeys.Current` binds from the two headers under the Foundry flag and resets per request; ignored without the flag; empty header treated as absent; concurrent requests stay isolated. |

## Phasing

1. **Core** — `Microsoft.Agents.AI.Hosting.Channels`: every type in the core layout. `InMemoryHostStateStore`,
   `FileHostStateStore`, `AIAgentRunner`, `WorkflowRunner`. Unit tests per type.
2. **Responses channel** — `Microsoft.Agents.AI.Hosting.Channels.Responses` reusing Hosting.OpenAI Responses
   models. Integration tests for agent + workflow targets.
3. **Samples + docs** — the two samples above. README per package.

## Non-goals for v1 (deferred to ADR-0028)

Deliberately **not** part of this contract; tracked by
[ADR-0028](../decisions/0028-hosting-linking-multicast-enhancements.md):

- cross-channel identity linking (`IIdentityLinker`, one-time-code / Entra linkers),
- identity allowlists / authorization policy (`IIdentityAllowlist`, `AuthorizationProfile`),
- response routing beyond the originating channel (`ResponseTarget`, active channel, all-linked),
- push or payload codecs (`IChannelPush`, `IChannelPushCodec`),
- background runs + continuation tokens,
- durable task runners (`IDurableTaskRunner`, in-process runner),
- retry / replay (`RetryPolicy`),
- fan-out / multicast / all-linked delivery,
- confidentiality tiers and `ILinkPolicy`,
- multi-user conversation scoping / group addressing (`ConversationScope`, `AcceptInGroup`),
- additional channel packages (Invocations, Telegram, Discord, Activity Protocol),
- a host-level multi-agent router.

These are follow-up enhancements, not prerequisites for shipping or using the v1 host.

## References

- .NET ADRs (scope): [`0027-hosting-channels.md`](../decisions/0027-hosting-channels.md) (v1 core),
  [`0028-hosting-linking-multicast-enhancements.md`](../decisions/0028-hosting-linking-multicast-enhancements.md) (deferred).
- Python reference impl: PR microsoft/agent-framework#6580 (`agent-framework-hosting` + `agent-framework-hosting-responses`).
- Python spec: [`002-python-hosting-channels.md`](./002-python-hosting-channels.md).
- Existing .NET hosting packages this work coexists with: `Microsoft.Agents.AI.Hosting.OpenAI`,
  `Microsoft.Agents.AI.Hosting.A2A(.AspNetCore)`, `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore`,
  `Microsoft.Agents.AI.Hosting.AzureFunctions`, `Microsoft.Agents.AI.Foundry.Hosting`.