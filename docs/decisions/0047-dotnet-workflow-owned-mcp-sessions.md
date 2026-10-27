---
status: proposed
contact: baywet
date: 2026-10-26
deciders: [baywet, westey-m]
informed: [rhurey]
---

# .NET workflow MCP isolation without workflow-lifetime connection ownership

## Context and Problem Statement

This ADR was recovered from [#9545](https://github.com/microsoft/agent-framework/pull/9545).
Its original proposal tied initialized MCP clients to logical workflow sessions,
including approval waits and later resumes. This revision separates the need for
client isolation from the assumption that a workflow must retain a connection to
preserve protocol state.

The implementation proposed in #9545 combines several resource-management
policies: workflow-specific MCP session lookup, bounded least-recently-used
eviction, active-call tracking, concurrent initialization, shutdown draining, and
reference-counted sharing of handler-owned `HttpClient` instances. Extracting these
into separate classes improves code organization but does not establish that
workflow-lifetime connection retention is necessary.

### Workflow tool calls are normally unattended

Declarative workflows use MCP primarily to discover and invoke tools. They
typically run without a user available to answer interactive questions. MCP
elicitation therefore is not a reason to preserve a connection for these
workflows. A workflow approval is a workflow-runtime interaction, not an MCP
`elicitation/create` exchange. Waiting for approval before invoking a tool does
not require keeping an MCP operation or connection open.

Resource subscriptions and background catalog-change subscriptions are likewise
outside this tool-invocation use case. The workflow does not need to maintain a
live resource view while paused. If future functionality introduces interactive
MCP exchanges or subscriptions, it must define their explicit lifetimes rather
than assuming every workflow already owns a permanent connection.

Durable workflow state belongs in workflow state and checkpoints. Server-side
application state needed across calls should have an explicit handle and
authorization contract; it must not depend implicitly on retaining one live
`McpClient` object in the workflow host.

### HTTP connections, protocol sessions, and clients are different boundaries

| Concern | Lifetime and isolation |
|---|---|
| Physical HTTP connection | A transport resource; pooling and reconnection do not by themselves define MCP session identity |
| MCP protocol session in initialization-based revisions | A logical interaction identified by protocol state and, when supplied, `MCP-Session-Id`; it can span HTTP connections |
| MCP client and transport objects | SDK resources that may contain mutable protocol, authentication, or callback state; their safe reuse needs a separate isolation contract |
| Active tool invocation | Must retain the resources needed to complete the entire operation, not merely until headers or an intermediate result arrive |
| Workflow execution | Owns durable execution state, approvals, and checkpoint/resume behavior; does not inherently require a live MCP connection between tool calls |

Under the `2025-11-25` Streamable HTTP specification, closing an HTTP connection
does not necessarily end the logical MCP session. Session IDs can be carried on
subsequent HTTP requests, and optional SSE replay can recover a disconnected
stream. Conversely, creating a fresh initialized client is not guaranteed to
reattach to an existing session. HTTP handler pooling alone provides neither
protocol session continuity nor durable application state.

### Protocol evolution removes most cross-call state requirements

The following reflects the `2026-07-28` specification text, not a claim that the
repository's current SDK or every deployed server already implements it.
Compatibility with initialization-based protocol revisions remains necessary.

| Feature | Protocol direction | Relevance to unattended workflow tool calls |
|---|---|---|
| Initialization and protocol sessions | Remove `initialize` / `notifications/initialized` and `MCP-Session-Id`; carry version and client capabilities per request, with `server/discover` for discovery | No protocol-session retention requirement in the newer revision |
| Roots | Deprecated; prefer explicit tool parameters, resource URIs, or server configuration | Not a reason to retain workflow-lifetime client state |
| Sampling | Deprecated; prefer direct LLM-provider integration; remaining support uses multi round-trip requests (MRTR) | Not a baseline requirement of the workflow MCP tool handler |
| Logging | Deprecated; prefer stderr for stdio or OpenTelemetry; remove `logging/setLevel` in favor of per-request metadata for remaining protocol logging | No persistent per-session log-level setting to preserve in the newer revision |
| Elicitation | Retained through MRTR: return input requirements, then retry with answers and opaque `requestState`; remove URL-elicitation completion notifications | Interactive elicitation is outside the normal unattended workflow use case |
| Resource and catalog subscriptions | Replace `resources/subscribe`, `resources/unsubscribe`, and the HTTP GET stream with `subscriptions/listen` | Outside this use case; a future subscription needs its own explicit stream lifetime |
| In-flight calls, progress, and cancellation | Remain request-scoped; closing the SSE response stream cancels the request, and `Last-Event-ID` replay is removed | Protect the active invocation; a new connection cannot transparently resume the old stream |
| Experimental tasks | Move out of core into an official extension with polling and explicit input updates | A future integration should persist authorized task handles, not rely on a workflow keeping a connection open |

Deprecated features remain available during their deprecation window; they are
not already removed. MRTR itself does not require connection continuity between
round trips: the client resubmits the original request with input responses and
any opaque server state.

For older protocol revisions, subscriptions, pending server-to-client requests,
and session configuration can require retained state. They must not be silently
broken if an application explicitly depends on them. However, their existence
does not justify imposing their retention model on unattended workflow tool
calls that do not use them.

The remaining baseline continuity requirement is the **active invocation**, not
the entire workflow execution. A completed call followed by an approval wait is
different from a tool call that is still awaiting its result.

The accompanying implementation changes the .NET default tool handler's client
lifetime, not the supported MCP protocol or the workflow runtime's ownership
model. It does not change the Python implementation.

## Decision Drivers

- Avoid coupling workflow lifetime to protocol state unused by unattended tools.
- Preserve isolation between callers, workflows, and authentication identities.
- Protect active operations during cancellation and disposal.
- Keep durable workflow state independent of live network objects.
- Respect ownership and configuration of application-provided HTTP infrastructure.
- Delegate reusable HTTP handler management to standard .NET infrastructure.
- Support console applications, worker services, and web applications without
  requiring ASP.NET or a DI container per invocation.
- Preserve transport protections with explicit factory-based authentication.
- Make compatibility, resource limits, and any stateful opt-in behavior explicit.

## Considered Options

1. Retain the handler-wide bounded MCP cache and reference-counted HTTP sharing.
2. Own MCP connections for the entire logical workflow session, with optional
   factory-managed HTTP handler reuse, as originally proposed in this ADR.
3. Use invocation-scoped MCP clients, with reusable HTTP handlers and a
   separately defined client-isolation policy.
4. Share one application-wide initialized MCP client or `HttpClient`.

## Decision Outcome

Proposed chosen option: **invocation-scoped MCP clients with reusable HTTP
handlers**, decoupling connection lifetime from workflow state management.

Do not introduce workflow-runtime resource ownership hooks solely to preserve MCP
session state between completed tool calls. A workflow pause, approval wait, or
checkpoint does not by itself require keeping an MCP client alive. Reuse of a
compatible HTTP handler and connection pool is independent of MCP client reuse.

This revises the original workflow-lifetime ownership proposal. It does not
establish that arbitrary MCP clients are interchangeable or safe to share across
workflows. The default handler uses invocation-scoped clients; applications
requiring cross-call session continuity supply an explicitly scoped integration.
The public invocation contract remains unchanged. The callback constructor and
handler-level disposal contract are removed in favor of a stateless handler.
Review of these breaking changes and their migration guidance remains required.

### Security isolation remains a separate requirement

Not needing session continuity is not permission to share an initialized
`McpClient` across unrelated executions. A client, transport, authentication
provider, or handler pipeline can contain credentials, headers, pending requests,
callbacks, or server-side state from an older protocol revision.

Invocation-scoped clients are one way to limit retention of such state. Any
client reuse must establish an explicit trusted isolation boundary:

- Different principals, tenants, credentials, endpoints, or transport policies
  must not select an incompatible existing client.
- A workflow identifier alone is not authority to access another execution's
  client or resources.
- Changed credentials or configuration must not silently select stale client
  state. Token refresh and identity changes need distinct, documented behavior.
- Shared pooled handlers must not retain per-workflow credentials, mutable
  default headers, cookies, or origin-pinning state.
- Existing distinctions such as connection name, label, and explicit headers
  must not be collapsed without a compatibility decision.

A security requirement may justify a workflow-scoped client boundary for a
particular integration. That is a reason to isolate a client, not proof that its
connection must remain open throughout an approval wait. The concrete client
isolation and transport policy must be reviewed before implementation.

### Invocation lifecycle and workflow resume

An invocation must hold its MCP client and transport until the entire operation
has completed or unwound. Initialization, protocol round trips, result
consumption, and cleanup are part of that protected lifetime. Do not dispose
resources immediately after starting an asynchronous call or receiving an
intermediate result.

Cancellation is a request, not evidence that work has stopped. Each invocation
awaits its own cleanup before completing. Initialization and cleanup failures
must have explicit, observable handling rather than leaking resources.
The handler owns no shared disposable resources and has no shutdown operation,
active-call registry, synchronization lock, or reentrant-disposal guard.

An approval continuation starts the approved invocation with the current
authorized connection configuration. It does not require retaining an idle MCP
client from before the approval. Restoring a checkpoint likewise creates the
resources required for subsequent calls; checkpoints do not serialize clients,
transports, HTTP objects, or promises of protocol-session reattachment.

The host owns admission limits, invocation deadlines, and shutdown cancellation.
It should bound submitted work, pass cancellation covering the entire invocation,
and cancel and await calls before disposing the application's HTTP factory
infrastructure or service provider. The handler does not impose a new global
concurrency limit or a fixed shutdown deadline that could interrupt supported
long-running tools.

Do not automatically retry a tool invocation merely because the connection was
lost. The server may already have performed side effects even if the result was
not received. Newer protocol stream cancellation is not an application rollback.
Retry and idempotency behavior must follow the tool's explicit contract.

Support for durable remote tasks would require persisting authorized task
handles and defining polling, expiry, input delivery, and cancellation behavior.
It is not supplied by retaining a workflow-lifetime connection.

### HTTP ownership and factory integration

| Source of HTTP client | Use and disposal contract |
|---|---|
| Application-provided factory | Obtain an owned wrapper for the chosen client scope; dispose it after MCP cleanup; let the factory manage pooled handlers |
| No factory | Preserve a parameterless non-DI path that creates and owns a client with documented transport defaults |

Owned wrappers must be disposed exactly once, including when initialization
fails. MCP and transport cleanup must release owned HTTP resources even if
earlier cleanup fails. Application factories must not be disposed by the MCP
integration. A factory must return a fresh client wrapper, not a borrowed shared
client.

`IHttpClientFactory` belongs to `Microsoft.Extensions.Http` and does not require
ASP.NET. The application may use the Generic Host or a `ServiceCollection`.
The `DefaultMcpToolHandler(IHttpClientFactory, string)` constructor uses
the application's stable named-client configuration on every invocation. The
name parameter selects the named configuration, with an empty string selecting
the default configuration.
Do not create a service provider or factory per invocation. Use a bounded set of
stable factory configuration names, not names derived from workflow IDs,
credentials, or arbitrary server URLs.

Factory reuse is not exclusive checkout/return: multiple wrappers may use one
underlying handler concurrently. Distinct proxies, client certificates, or other
transport policies can require separate configurations. There is no additional
handler-owned HTTP-client dictionary or reference-counted lease layer solely to
provide pooling.

### Transport policy

Non-DI fallback clients retain explicit defaults: cookies disabled, automatic
redirects disabled, certificate revocation checking, Streamable HTTP, and
origin-bound credential handling. Factory defaults alone are not a substitute.

Disable the SDK's standalone GET/SSE stream for unsolicited server messages.
Unattended tool invocations do not require a background subscription channel.
This avoids opening and closing that channel for each legacy initialization;
request-scoped SSE responses to tool calls remain supported. This policy applies
to both factory-backed and non-DI calls and does not change session ownership.

The integration does not silently replace application factory clients'
pipelines. Configure their primary handlers with cookies and automatic redirects
disabled and certificate revocation checking enabled. Any credential-injecting
handler must restrict credentials to the configured server origin. Streamable
HTTP remains enforced regardless of the HTTP client's source.

The fallback's `OriginPinningHandler` stores one origin and is owned by one
invocation. Do not move this mutable policy into one pooled pipeline for
unrelated origins. Factory handlers must instead use an appropriately bounded,
stable configuration or validated request-specific policy. Origin checks must
account for every credential-injection step in outbound processing.

Wrapper disposal must not disrupt other invocations sharing a factory-managed
handler. Conversely, factory handler expiry must not terminate an active call.
Any supported long-lived integration must deliberately configure connection
refresh; pooled connection lifetime does not transfer protocol-session state.

The package supports modern .NET, .NET Standard 2.0, and .NET Framework 4.7.2.
Compatible factory-package versions, handler APIs, and DNS-refresh behavior must
be established for every supported target; this proposal does not drop targets.

### Protocol setup

Expose an init-only optional `DefaultMcpToolHandler.ProtocolVersion` property
and pass it through a fresh SDK `McpClientOptions` for every invocation.
Leave it unset by default so the SDK retains automatic discovery and legacy
fallback. Do not select an older version globally to optimize one server.

An application that knows a server requires an initialize-handshake revision
can explicitly select that version to avoid the initial discovery probe and its
possible timeout. The server must negotiate that exact legacy version. This
does not skip initialization, share a session, or eliminate session termination.
Explicit newer revisions still perform discovery and reject legacy-only servers
rather than silently downgrading. Incompatible selections surface SDK errors.
Use separately configured handlers where server protocol policies differ.

### Compatibility and explicitly stateful integrations

Remove the `httpClientProvider` callback constructor and the internal
`httpMessageHandlerFactory` callback seam. Applications migrate authentication
to named `IHttpClientFactory` configurations and origin-bound delegating handlers.
Credentials that change per invocation must be resolved per request, not retained
in pooled handlers. Tests use the same factory interface as applications.

Remove `IAsyncDisposable` and `DisposeAsync` from `DefaultMcpToolHandler`.
Applications remove handler disposal and instead cancel and await their active
calls before disposing application-owned HTTP infrastructure.

The previous non-provider path cached initialized clients by server URL, label,
connection name, and explicit headers. Moving that path to invocation-scoped
clients is a behavioral change for servers relying on implicit session state,
and adds initialization cost for older protocol revisions. It needs explicit
migration documentation, not a claim that all deployed MCP servers are stateless.

Applications that genuinely require cross-call MCP session continuity need an
explicitly scoped integration, such as a custom `IMcpToolHandler`, with
documented ownership, authentication, capacity, and release contracts. It must
not be the default requirement for all workflows. Such an integration must not
evict live state silently or promise checkpoint reattachment unsupported by its
SDK and server.

Keep public API changes additive where possible; do not introduce mandatory
members on existing custom handlers or ambiguous constructor overloads. Released
API changes require the repository's API-baseline and compatibility process.
Intentional breaking changes require the appropriate designation and release
notes when implementation is proposed.

### Consequences

- Good, because unattended workflow state and resume behavior do not depend on
  retaining idle MCP connections.
- Good, because invocation-scoped clients can avoid implicit cross-call
  client-state reuse while compatible HTTP infrastructure can still be pooled.
- Good, because workflow state continuity alone does not require a
  workflow-session connection registry, idle-session LRU policy, or HTTP
  reference-counting layer.
- Good, because invocation-local resource ownership removes handler-level
  admission/drain synchronization and reentrant-disposal bookkeeping.
- Neutral, because safe shutdown remains a host responsibility and explicit
  authentication boundaries remain necessary.
- Bad, because invocation-scoped clients require initialization per invocation
  with older protocol revisions.
- Bad, because applications relying on the existing cached session behavior
  need a migration path or an explicit stateful integration.
- Bad, because factory integration still requires careful transport-policy and
  cross-target configuration.

## Validation

Before implementation is accepted, add focused regression coverage for:

- Sequential invocations, concurrent workflows, and sibling executions do not
  inherit one another's MCP client state or credentials.
- Approval waits and checkpoint resumes require no retained live connection;
  the resumed invocation uses the correct authorized configuration.
- Initialization, cancellation, and host shutdown do not cause early
  disposal, duplicate cleanup, leaked resources, or deadlock.
- A lost result does not silently trigger a duplicate side-effecting tool call.
- Owned wrappers are disposed once; application factories are not disposed;
  cleanup does not disrupt another invocation's pooled HTTP resources.
- Shared handlers contain no per-caller mutable authentication or origin state;
  origin, redirect, cookie, and credential protections remain intact.
- Factory-created wrappers are acquired per invocation and the configured named
  pipeline is preserved.
- Compatibility with the currently supported SDK and protocol revisions is
  preserved; tests do not assume the newer protocol is already deployed.
- Any explicit stateful integration follows its documented isolation and release
  contract without imposing connection retention on the default path.

Validate HTTP configuration and public API compatibility on every supported
target. Compare initialization cost, resource retention, shutdown behavior, and
handler/connection reuse before claiming a performance improvement.

## Pros and Cons of the Options

### 1. Handler-wide bounded cache and reference-counted HTTP sharing

- Good, because it limits retained entries and reduces repeated initialization.
- Neutral, because active-operation coordination is still needed.
- Bad, because shared cache identity and eviction become correctness and
  isolation concerns unrelated to the default unattended tool-call use case.

### 2. Workflow-lifetime MCP connections with optional HTTP factory reuse

- Good, because an explicitly stateful integration can retain its protocol state
  and have a deterministic release boundary.
- Neutral, because HTTP factory reuse remains independent of MCP ownership.
- Bad, because it introduces runtime ownership across waits, run handles,
  workflow-backed agents, and subworkflows without a default tool-call need.
- Bad, because idle retention consumes resources and does not provide
  cross-process checkpoint continuity or justify safe client sharing.

### 3. Invocation-scoped clients with reusable HTTP handlers

- Good, because resource retention can follow actual security and operation
  requirements rather than the workflow's potentially long unattended lifetime.
- Good, because compatible pooled HTTP infrastructure is reusable without
  retaining MCP session state or sharing initialized clients.
- Neutral, because invocation-scoped clients and explicit stateful integrations
  require different ownership and compatibility contracts.
- Bad, because choosing invocation-scoped clients adds setup per call on
  initialization-based servers and requires a documented cache migration.

### 4. One application-wide initialized MCP client or HttpClient

- Good, because compatible HTTP requests can share transport infrastructure.
- Neutral, because a shared HTTP wrapper does not imply shared MCP state.
- Bad, because one initialized MCP client can mix protocol and caller state;
  one mutable HTTP pipeline also cannot safely represent every authentication,
  origin, proxy, or client-certificate policy.

## More Information

### Protocol references

- [2025-11-25 Streamable HTTP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports):
  logical sessions, optional SSE replay, and disconnect versus cancellation.
- [2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog):
  stateless request metadata, session removal, MRTR, and the tasks extension.
- [Deprecated features](https://modelcontextprotocol.io/specification/2026-07-28/deprecated):
  roots, sampling, and logging migration paths and deprecation windows.
- [Multi round-trip requests](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr):
  client-carried input responses and opaque request state across independent requests.
- [Subscriptions](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/subscriptions):
  explicit subscription stream lifetimes.
- [2026-07-28 Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http):
  request-scoped streams, cancellation on disconnect, and no SSE replay.

### HTTP infrastructure references

- [IHttpClientFactory with .NET](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory):
  registration through `AddHttpClient`, including non-web usage.
- [HTTP client lifetime management](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory#httpclient-lifetime-management):
  wrappers, pooled handlers, and disposal.
- [Using the factory with SocketsHttpHandler](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory#using-ihttpclientfactory-together-with-socketshttphandler):
  connection refresh for explicitly long-lived integrations.
- [Message handler scopes](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory#message-handler-scopes-in-ihttpclientfactory):
  handler scopes and connection-specific outer policy handlers.
- [Named clients](https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory#named-clients):
  avoid unbounded configuration names.

### Implementation scope

This proposal targets the .NET declarative MCP integration. It does not implement
the new protocol, add interactive elicitation or subscriptions, redesign Python,
change result conversion, or introduce durable MCP reconnection.

The implementation uses an application-provided `IHttpClientFactory` for
reusable HTTP infrastructure. Each invocation requests a fresh named HTTP
wrapper, owns its separate MCP client and transport, and disposes the wrapper
after MCP cleanup. The factory owns handler pooling and rotation; the MCP handler
does not dispose the application factory or its shared handlers.

The non-DI path creates and owns a dedicated HTTP handler and origin-policy
handler for each invocation. Callback construction and handler-level disposal
are removed. The host awaits its own invocations during shutdown. No
handler-owned shared invoker, internal service provider, workflow-runtime
ownership hooks, invocation registry, synchronization lock, HTTP-client cache, or lease-counting pool
are introduced.

The package references `Microsoft.Extensions.Http` for all supported target
frameworks. New constructors and removed APIs are recorded in each target's public
API baseline. Factory integration is the reusable-transport path, not deferred work
or a bespoke connection-rotation implementation.

Deciders must review the invocation boundary, legacy-cache migration, transport
configuration, and explicitly stateful escape hatch before accepting the ADR.

Confirm EM/architect involvement through the listed review participants before
acceptance. Request `westey-m`'s review and inform `rhurey`; PR approval is the
decision record, not an assertion made by this document.
