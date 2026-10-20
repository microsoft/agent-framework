---
status: proposed
contact: baywet
date: 2026-10-20
deciders: [baywet, westey-m]
informed: [rhurey]
---

# .NET workflow-owned MCP sessions and factory-managed HTTP transport

## Context and Problem Statement

An initialized MCP `McpClient` represents a protocol connection that can have
associated server-side session state. It is not interchangeable with an arbitrary
idle client for the same server. A workflow must use its own connection when
continuing work, including after waiting for approval or another external event.

The implementation in [#9545](https://github.com/microsoft/agent-framework/pull/9545)
combines several resource-management policies: workflow-specific MCP session
lookup, bounded least-recently-used eviction, active-call tracking, concurrent
initialization, shutdown draining, and reference-counted sharing of handler-owned
`HttpClient` instances. Extracting these into separate classes improves code
organization but does not remove the policy coupling.

There are two different concerns:

| Concern | Required isolation and ownership |
|---|---|
| MCP protocol session | Belongs to a logical workflow execution/session and its connection configuration |
| HTTP transport | Can reuse handlers and connection pools when transport configuration permits |

The earlier handler already retained initialized MCP connections. Workflow
partitioning changes which connection is selected; it does not require a custom
HTTP-client pool. In particular, no active tool call does not imply that a
workflow has finished. Evicting an idle but live MCP session can change the
behavior of its next call.

This ADR proposes a different ownership model for the .NET implementation. It is
**not implemented by adding this document**, does not declare the current PR's
behavior changed, and does not change the Python implementation.

## Decision Drivers

- Make workflow isolation a property of resource ownership rather than a
  handler-wide cache key alone.
- Preserve MCP session continuity throughout a live workflow session.
- Keep active calls safe during completion, cancellation, and disposal.
- Respect ownership and configuration of user-supplied HTTP clients.
- Delegate reusable HTTP handler management to standard .NET infrastructure.
- Support console applications, worker services, and web applications.
- Avoid introducing an ASP.NET requirement or a DI container per MCP connection.
- Preserve existing transport protections and authentication boundaries.
- Make abandonment, checkpoint restore, resource limits, and migration behavior
  explicit rather than hiding them behind eviction.

## Considered Options

1. Retain the handler-wide bounded MCP cache and reference-counted HTTP sharing.
2. Own MCP connections in a workflow session, with dedicated HTTP-client wrappers
   and optional factory-managed handler reuse.
3. Own MCP connections in a workflow session, but create a dedicated HTTP handler
   for every internally created client.
4. Share one application-wide `HttpClient` while retaining workflow-owned MCP
   sessions.
5. Create a new MCP session for every tool invocation.

## Decision Outcome

Proposed chosen option: **own MCP connections in a workflow session, with
dedicated HTTP-client wrappers and optional factory-managed handler reuse**.

The workflow execution/session owns its live connections. The tool handler
coordinates protocol operations but does not independently retain all workflows'
connections in a global LRU cache. The application owns its HTTP factory and any
HTTP clients it supplies. Exact public API names and runtime integration remain
subject to design review before implementation.

### Workflow ownership boundary

"Workflow instance" means the **logical execution/session**, not the reusable
`Workflow` graph, an executor, an individual tool call, a superstep, or the
duration of one `RunAsync`/resume operation.

The current object model includes `Workflow`, disposable `Run` and
`StreamingRun` handles, and an internal `WorkflowSession` used by workflow-backed
agents. These are not automatically equivalent ownership boundaries. In
particular, agent execution can create successive run handles from checkpoints.
Implementation must connect both direct workflow execution and workflow-backed
agents to a session-level resource owner; attaching resources only to a temporary
run handle would not satisfy this ADR.

Conceptual ownership:

```text
Application
  +-- IHttpClientFactory / pooled HTTP handler infrastructure
  +-- caller-owned HttpClients, if supplied
  +-- logical workflow session A
  |     +-- MCP connection for configuration X
  |           +-- McpClient and transport
  |           +-- owned HttpClient wrapper OR borrowed caller HttpClient
  +-- logical workflow session B
        +-- distinct MCP connection for configuration X
              +-- distinct McpClient and transport
              +-- owned HttpClient wrapper OR borrowed caller HttpClient
```

Sessions A and B must not share their MCP protocol session even when their
HTTP-client wrappers share a factory-managed handler and connection pool.
Different caller-provided HTTP clients may also legitimately share a transport
pool; this does not authorize sharing MCP sessions.
This proposal does not change existing graph/executor concurrency restrictions.

Within one workflow owner, connection lookup still distinguishes server endpoint,
connection configuration, and authentication identity. Existing distinctions
such as connection name, label, and explicit headers must not be collapsed
without a separate compatibility decision. Changed credentials/configuration
must not silently select an incompatible existing MCP session.

Session ownership is a runtime capability, not just an arbitrary string supplied
by an action. Trusted workflow identity remains useful for continuations,
diagnostics, and child scopes, but a matching string alone must not grant access
to another owner's live resources. Sibling subworkflows receive separate child
owners; the parent coordinates their shutdown before releasing its resources.
Checkpoint identifiers must retain their existing meaning.

### HTTP ownership and factory integration

| Source of HTTP client | Use and disposal contract |
|---|---|
| User-supplied client | Borrow as supplied; do not mutate shared client configuration or dispose it |
| Application-provided factory | Obtain a dedicated wrapper for the MCP connection; dispose the wrapper with that connection; let the factory manage pooled handlers |
| No supplied client or factory | Preserve a non-DI path that creates and owns a dedicated client with documented defaults |

An MCP transport must not dispose a borrowed HTTP client. Owned wrappers must be
disposed exactly once, including when initialization fails. MCP and transport
cleanup must release owned HTTP resources even when earlier cleanup fails.
Supplying an already initialized `McpClient`, if exposed by a future API, likewise
requires an explicit ownership contract; accepting it must not implicitly allow
cross-workflow sharing.

`IHttpClientFactory` belongs to `Microsoft.Extensions.Http` and does not require
ASP.NET. The application can use the Generic Host or a `ServiceCollection`.
The library must not create a service provider/factory for each MCP connection.
Retaining the non-DI path avoids making hosting infrastructure mandatory merely
to construct a handler.

Use a bounded set of stable factory configuration names, not names derived from
workflow IDs, credentials, or arbitrary server URLs. The factory handles reuse of
the underlying pipelines. There is no additional handler-owned HTTP-client
dictionary, eviction policy, or reference-counted lease layer.

Factory reuse is not exclusive checkout/return: multiple HTTP clients can use
the same underlying handler concurrently. Distinct transport policies, such as
proxies or client certificates, can still require separate configurations.

### Transport policy and long-lived connections

Internally created clients retain explicit defaults: cookies disabled, automatic
redirects disabled, certificate revocation checking, Streamable HTTP, and
origin-bound credential handling. Factory defaults alone are not a substitute
for this configuration.

The current `OriginPinningHandler` stores one origin. It cannot be placed in a
single pooled pipeline for unrelated origins. To preserve this behavior while
sharing underlying handlers, use a connection-specific outer policy handler over
a factory-managed pipeline, following the documented `IHttpMessageHandlerFactory`
pattern, or an equivalently validated request-specific policy. The policy must
run after credential injection in outbound processing. Workflow identity,
credentials, and origin state must not be stored in shared mutable handlers.

An outer policy handler and `HttpClient` wrapper may still be constructed per
connection. The objective is reuse of the expensive underlying HTTP handlers
and connection pools, not eliminating every `new HttpClient(...)` expression.
Caller-supplied clients remain under the caller's transport-policy contract;
the library must not silently replace their handler pipelines.

Factory-created clients normally are short-lived. An MCP connection can instead
retain its wrapper for a long time. Factory handler expiry does not replace the
handler under that wrapper and must not terminate its active requests. On
supported runtimes, explicitly configure `SocketsHttpHandler.PooledConnectionLifetime`
to refresh network connections independently of the MCP session. This does not
renew or transfer server-side MCP state, and does not interrupt an active stream
merely because its connection age has elapsed.

The package targets .NET 8, 9, and 10, .NET Standard 2.0, and .NET Framework 4.7.2.
Modern handler APIs are not uniformly available across these targets. Compatible
registration, DNS-refresh behavior, and supported factory-package versions must
be established per target; this proposal does not silently drop older targets.

### Lifecycle and protection of active invocations

An owner progresses through:

```text
Open -> Closing -> Disposed
```

Waiting for external input is still `Open`, not a transition to `Closing`.

1. **Acquire:** atomically confirm that the owner is open and register the work.
   Resolve or initialize its connection. Concurrent first use of the same
   configuration must not publish duplicate connections.
2. **Invoke:** keep the connection alive for the entire asynchronous operation.
   Release the operation registration in `finally`, including on failure.
3. **Close:** reject new work and coordinate cancellation, where requested.
   Await initialization and operations already admitted. Closing must also
   account for a connection whose initialization completes during shutdown.
4. **Dispose:** after draining, release MCP clients, transports, and owned HTTP
   wrappers. Do not dispose borrowed clients or the application's factory.

Structured execution can supply the operation tracking if the runtime guarantees
that all tasks are joined before disposal. Otherwise retain a small per-owner
acquire/drain mechanism. Workflow ownership does not remove the need for
initialization synchronization, cleanup of unpublished resources, or safe
shutdown ordering.

Cancellation is a request, not evidence that an operation has stopped. Cancelling
one waiter must not dispose a connection still used by another operation.
Session closure cancels shared initialization only according to an explicit
owner policy. Disposal requested from inside an admitted operation must not wait
on that same operation and deadlock; defer draining to the owner or reject that
reentrant request explicitly.

Completion, abandonment, and process shutdown must have observable release paths.
A recoverable execution failure or cancellation of one run does not automatically
mean that the logical session has been abandoned; the owner must decide whether
to retain it for retry or close it.
A host shutdown deadline may stop waiting, but must report incomplete cleanup;
it must not pretend that a still-running operation drained successfully.
Cleanup errors must follow the repository's error-reporting conventions rather
than disappear.

### Waiting, checkpoints, and capacity

Returning control to the caller, yielding output, or writing a checkpoint does
not by itself release a live session. Approval continuations must return to the
original owner, even when they arrive through a new execution call.

Live `McpClient`, transport, and HTTP objects are not checkpoint data. Restoring
in another process, or after explicitly releasing the original owner, requires
new connections. Retaining a workflow ID or MCP session identifier is not proof
that a server session can be reattached. Any durable reattachment requires
separate SDK/server support and an explicit contract; this ADR does not promise it.
Forking a checkpoint into an independent execution requires a distinct owner.

There is no LRU eviction of still-open workflow sessions, including sessions
waiting for external input. Resource limits belong to explicit admission and
session-retention policy. Hosts may configure quotas, backpressure, or documented
expiration/abandonment, with appropriate tenant/owner boundaries. Exhaustion must
be observable; it must not silently replace a live MCP session with a new one.
This replaces the current fixed handler-wide limit rather than asserting that
resource use can be unlimited.

### Authentication-provider compatibility

The existing `httpClientProvider` callback runs for every invocation and creates
a fresh MCP session for every call, even when it returns the same HTTP client or
`null`. The callback may select different credentials on successive invocations.

Do not reinterpret that callback as a once-per-session factory or begin retaining
its MCP connections silently. Preserve its existing semantics through a legacy
adapter, and offer an explicit opt-in connection-scoped contract for the new
ownership model. A session-aware application must define credential identity and
refresh behavior, for example through an application-owned authentication
handler. Obtaining a new token must not depend implicitly on recreating the MCP
session before every tool call.

This compatibility mode intentionally retains per-call MCP sessions; it does
not gain state continuity merely because HTTP factory pooling is introduced.

### Examples

#### Non-web application registration

The following uses existing .NET APIs to demonstrate that no ASP.NET application
or running host is required. It shows registration and ownership only, not the
complete origin-protection and handler configuration described above.

```csharp
using System.Net.Http;
using Microsoft.Extensions.DependencyInjection;

ServiceCollection services = new();
services.AddHttpClient("WorkflowMcp");

using ServiceProvider applicationServices = services.BuildServiceProvider();
IHttpClientFactory httpClients =
    applicationServices.GetRequiredService<IHttpClientFactory>();

using HttpClient connectionHttpClient = httpClients.CreateClient("WorkflowMcp");
```

The connection, not an individual tool call, would hold `connectionHttpClient`.
The application service provider must outlive all sessions using its factory.
Two wrappers created under the same configuration can share an underlying
handler. The factory remains responsible for that handler after wrapper disposal.

For a long-lived wrapper on modern .NET, the documented configuration pattern is:

```csharp
services.AddHttpClient("WorkflowMcp")
    .UseSocketsHttpHandler((handler, _) =>
    {
        handler.UseCookies = false;
        handler.AllowAutoRedirect = false;
        handler.SslOptions.CertificateRevocationCheckMode =
            System.Security.Cryptography.X509Certificates.X509RevocationMode.Online;
        handler.PooledConnectionLifetime = TimeSpan.FromMinutes(5);
    })
    .SetHandlerLifetime(Timeout.InfiniteTimeSpan);
```

Five minutes is illustrative, not a required default. Connection-specific origin
policy is still required. This example is not a cross-target implementation recipe.

#### Logical workflow ownership across approval

The following is **proposed pseudocode**. These session/resource APIs do not
currently exist under the names shown and are not a public API commitment.

```csharp
await using var session =
    await runtime.OpenWorkflowSessionAsync(workflow, httpClients);

var pendingApproval = await session.RunUntilWaitingAsync(input);
var approvalResponse = await application.GetApprovalAsync(pendingApproval);
await session.ResumeAsync(approvalResponse);
await session.CompleteAsync();
```

The owner remains alive throughout the approval wait and resume. `CompleteAsync`
closes admission and drains work; leaving the scope is an explicit release or
abandonment boundary. Disposing a request-local HTTP/DI scope while waiting must
not accidentally dispose this longer-lived workflow owner. Web applications
must retain it independently of an individual request, or explicitly choose a
checkpoint/connection-recreation policy instead.

Two sessions created from the same workflow graph each get distinct MCP clients.
A tool invocation in either session cannot dispose the other's HTTP wrapper.
No extra workflow ID is required in YAML; ownership comes from the runtime.

#### Shutdown racing with an active tool invocation

```text
Call A:  admitted -> initialize/get MCP connection -> await tools/call -> release
Owner:                    request close -> reject Call B -> await A -> dispose
HTTP factory:             shared handler remains usable by other sessions
```

An approval wait with no active tool calls does not initiate the closing sequence.
A cancelled caller releases its registration only after its operation unwinds.
HTTP handler rotation neither ends the MCP session nor completes the tool call.

### Consequences

- Good, because MCP session identity and ownership follow the workflow object
  model, while HTTP pooling follows application infrastructure.
- Good, because workflow completion provides a natural resource-release boundary
  without evicting another still-live workflow's state.
- Good, because the handler-wide LRU, retired-entry policy, and HTTP-client
  reference counts are no longer the primary lifetime mechanism.
- Neutral, because per-owner connection lookup and concurrency coordination still
  exist; this is not a claim that all bookkeeping can be removed.
- Bad, because runtime ownership must span direct runs, workflow-backed agents,
  approval continuations, and child workflows rather than just the MCP package.
- Bad, because hosts must handle abandoned/waiting sessions explicitly, and
  retaining them can consume more resources than the current bounded cache.
- Bad, because factory integration adds package/configuration considerations,
  especially for older targets and connection-specific outer policy handlers.

### User experience and potential breaking changes

Adding this ADR is documentation-only. The following impacts describe a future
implementation, not behavior already delivered by this PR.

| Area | Proposed experience and compatibility impact |
|---|---|
| Workflow authoring | No proposed YAML change or manual workflow-ID argument; runtime ownership remains transparent to workflow definitions |
| Application setup | Optional factory registration/injection for handler reuse; do not require ASP.NET or remove non-DI construction |
| Session cleanup | A logical owner must be retained and explicitly completed/disposed; applications that treated a shared handler as the sole owner may require changes |
| Approval and resume | Same-owner resumes preserve the MCP session between calls rather than depending on idle-cache retention |
| Capacity | Remove implicit live-session LRU replacement and the fixed global 32-entry behavior; configure admission/retention explicitly instead |
| Provider callbacks | Preserve per-invocation legacy behavior; adopting a connection-scoped provider is explicit and can change token-refresh timing |
| Custom handlers/contexts | Existing `IMcpToolHandler` implementations must not acquire new mandatory members silently; use adapters or an additive scoped contract |
| Constructor APIs | Prefer additive options/registration; a new overload must not make existing calls such as `new DefaultMcpToolHandler(null)` ambiguous |
| Checkpoint restoration | Serialized workflow state does not serialize a live MCP connection; no new cross-process continuity guarantee |
| Handler disposal | A shared handler must not unexpectedly destroy workflow-owned sessions; changing its existing drain/disposal contract requires explicit migration |
| Dependencies and targets | Factory integration can introduce `Microsoft.Extensions.Http` dependencies; preserve target support and document registration/version requirements |
| Diagnostics | Factory logging is additional observable behavior; configure redaction and do not log credentials, authentication partitions, or sensitive URLs |

Removing existing constructors or interfaces, requiring a new session-owner
argument everywhere, changing callback frequency, or changing handler-disposal
semantics can be source, binary, or behavioral breaking changes. An adapter that
uses a short-lived owner per legacy invocation cannot claim state continuity.
Any compatibility layer retaining sessions must define its explicit lifetime,
not conceal another global cache.

Released public API changes require the repository's API-baseline and package
compatibility process. Any intentional breaking change needs release notes and
the repository's breaking-change designation when implementation is proposed;
the documentation-only addition is not itself an API break.

## Validation

Before implementation is accepted, add focused regression coverage for:

- Distinct sessions from the same workflow graph cannot share MCP state, while
  successive calls and approval resumes in one live owner reuse its connection.
- Concurrent first use initializes one connection per configuration; changed
  connection/authentication identity does not select an incompatible connection.
- Closing races with acquisition, initialization, and active calls without early
  disposal, leaked unpublished connections, duplicate cleanup, or deadlock.
- Waiter cancellation does not terminate another invocation's work; initialization
  failure and cleanup failure remain observable and permit appropriate retry.
- Child workflow resources are isolated and drained in the required owner order.
- Owned HTTP wrappers are disposed once; borrowed clients and application factories
  are not disposed; wrapper disposal does not disrupt other factory clients.
- Shared handlers contain no per-workflow or per-caller mutable authentication
  state, and origin and redirect behavior remain consistent with the current
  transport contract.
- Waiting sessions remain live under unrelated workflow activity; admission
  limits do not evict them or silently recreate their sessions.
- Same-process resume, explicit abandonment, shutdown, and checkpoint restore
  follow their documented continuity and release contracts.
- Existing provider callbacks and custom handlers retain their documented behavior.

Validate HTTP configuration and public API compatibility on every supported
target, and exercise console and hosted applications. Compare initialization
count, resource retention, shutdown behavior, and handler/connection reuse before
claiming a performance improvement.

## Pros and Cons of the Options

### 1. Handler-wide bounded cache and reference-counted HTTP sharing

- Good, because it preserves the current entry points and bounds retained entries.
- Neutral, because synchronization and invocation protection already exist.
- Bad, because idle eviction can end a live workflow's stateful MCP session.
- Bad, because global capacity couples unrelated workflow owners and transport
  sharing requires another ownership mechanism.

### 2. Workflow-owned MCP connections with optional HTTP factory reuse

- Good, because the ownership boundary matches protocol state and deterministic
  release, while the factory manages reusable HTTP infrastructure.
- Neutral, because each session still needs a small connection registry and
  synchronization; factory integration can remain optional.
- Bad, because explicit runtime lifecycle integration and migration are required,
  and long-lived HTTP wrappers need deliberate connection-refresh configuration.

### 3. Workflow-owned MCP connections with dedicated HTTP handlers

- Good, because ownership and origin policy are straightforward without DI.
- Neutral, because this remains a valid non-DI fallback.
- Bad, because every connection can create another network connection pool,
  increasing connection establishment and socket pressure at high session counts.

### 4. One application-wide HttpClient

- Good, because compatible requests can share one wrapper and its connection pools.
- Neutral, because HTTP supports concurrent requests to multiple origins.
- Bad, because it does not solve MCP ownership, and one common pipeline cannot
  carry different per-origin pinning, proxy, or client-certificate configurations
  without additional request-aware design.

### 5. A new MCP session for every tool invocation

- Good, because connection lifetime is limited to one operation.
- Neutral, because the existing provider-backed path deliberately uses this model.
- Bad, because it adds initialization per call and cannot preserve MCP session
  state between calls; HTTP handler reuse does not restore that state.

## More Information

### Public documentation

- [IHttpClientFactory with .NET](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory):
  registration through `AddHttpClient`, including non-web Generic Host usage.
- [HTTP client lifetime management](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory#httpclient-lifetime-management):
  new wrappers, pooled handlers, default two-minute handler lifetime, safe wrapper
  disposal, and the expectation of short-lived factory clients.
- [Using the factory with SocketsHttpHandler](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory#using-ihttpclientfactory-together-with-socketshttphandler):
  explicit `PooledConnectionLifetime` for long-lived connections.
- [Message handler scopes](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory#message-handler-scopes-in-ihttpclientfactory):
  handler scopes are separate from application scopes; the documented outer
  handler pattern uses `IHttpMessageHandlerFactory` for the pooled pipeline.
- [Named clients](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory#named-clients):
  avoid an unbounded number of client names.

### Implementation scope and remaining design work

This proposal targets the .NET declarative MCP integration and the workflow
runtime ownership hooks it needs. It does not redesign Python, change protocol
result conversion, or introduce durable MCP reconnection.

Before implementation, deciders must approve the concrete owner/API shape,
legacy-handler disposal adapter, ownership across run-handle replacement,
credential-refresh contract, capacity/abandonment configuration, and cross-target
HTTP configuration. Confirm EM/architect involvement through the listed review
participants before acceptance. Request `westey-m`'s review and inform `rhurey`;
PR approval is the decision record, not an assertion made by this document.

Implement and validate the new lifecycle before removing existing guards.
HTTP factory integration alone must not be treated as fixing MCP session lifetime.
