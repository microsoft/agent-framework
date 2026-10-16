---
status: approved
date: 2026-10-15
deciders: jpalvarezl, eavanvalkenburg
---

# Use the MCP SDK Client as the primary Python MCP client

## Context and Problem Statement

The Python `MCPTool` implementation originally owned an MCP transport, constructed a low-level `ClientSession`, and
used that session for every operation. The MCP Python SDK 2.x adds a high-level `Client` that owns protocol
negotiation and standard client behavior across modern and legacy peers.

Using `Client` only for negotiation and then routing operations through `client.session` would bypass high-level
behavior such as multi-round-trip request (MRTR) handling and response caching. At the same time, existing callers
can supply an already-created `ClientSession` and expect Agent Framework not to take ownership of it, while callers
using the modern API need to supply an already-entered high-level `Client` without transferring its ownership.

This decision defines the lasting boundary between the two SDK levels and three ownership modes, including lifecycle,
caching, subscription recovery, and the meaning of `MCPTool.session`.

This ADR covers the outbound Python MCP client. Hosting/server code continues to use the SDK server APIs.

## Decision Drivers

- One Agent Framework API must support modern and legacy MCP peers.
- Standard protocol behavior should remain owned by the MCP SDK rather than be duplicated in Agent Framework.
- Framework-created resources must be closed by the task that opened them, including cancellation and failed
  connection attempts.
- Caller-supplied Clients, sessions, and HTTP clients must remain caller-owned.
- Reconnect, authenticated header identity, catalog publication, security, tracing, and result conversion remain
  Agent Framework policy.
- Tools, prompts, and resources should follow one operation-routing rule.
- Tasks and durable human-input continuation are separate from base MRTR support.

## Considered Options

- Retain the high-level SDK `Client` and use it for standard operations in both ownership modes, with `ClientSession`
  as a deprecated caller-owned low-level compatibility path.
- Use `Client` only for negotiation while continuing operations through `client.session`.
- Reimplement negotiation, MRTR, caching, and subscriptions around `ClientSession`.
- Add separate modern and legacy Agent Framework tool classes or a public protocol-mode switch.

## Decision Outcome

Chosen option: use the high-level SDK `Client` for both framework-owned and caller-owned high-level connections.
The caller-owned `ClientSession` path is retained for backward compatibility but is considered deprecated for new
usage; callers should prefer supplying a high-level `Client`.

The private `_MCPConnection` protocol is the operation seam. Its implementations deliberately do not expose both
SDK levels:

- `_ClientMCPConnection` uses an entered high-level `mcp.Client`. Its `is_framework_owned` flag records whether
  Agent Framework created and manages the Client or the caller supplied and manages it. Its `client` property
  references that Client and its `session` property remains `None`. Tool, prompt, resource, catalog, logging, and
  liveness operations route through `Client`; they never use `client.session` as the operation provider.
- `_SessionMCPConnection` wraps a caller-supplied `ClientSession`. This is a deprecated low-level compatibility
  path retained for existing applications. Its `session` property references that session and its `client` property
  remains `None`. Operations call the session directly and do not gain high-level caching or automatic MRTR behavior.

`MCPTool.session` is therefore meaningful only for the deprecated caller-supplied low-level path. High-level Client
connections do not publish the SDK Client's internal compatibility session through that property.

### Ownership model

Agent Framework owns:

- transport and Client construction, Client entry, and resource cleanup for framework-created connections;
- the lifecycle-owner task, locks, connection publication, reset coordination, and cancellation cleanup;
- request-scoped HTTP header identity and reconnects caused by identity changes;
- tool argument filtering and trusted request metadata merging;
- result parsing, Agent Framework content conversion, tracing, and error translation;
- atomic catalog publication and rollback after a failed complete fetch;
- the background catalog-subscription task for any high-level Client, including refresh scheduling, retry/backoff,
  cancellation, and recovery after a subscription ends or is lost;
- security and approval policy.

For **caller-supplied** connections, the caller owns:

- entering and closing a **supplied** high-level `Client`;
- constructing and closing a **supplied** low-level `ClientSession`;
- the transport, authentication, callbacks, and other configuration already captured by either supplied object.

The SDK `Client` owns:

- modern negotiation and legacy initialization fallback;
- standard tool, prompt, and resource operations;
- MRTR callback dispatch, retries, round limits, request state, and input responses;
- response-cache storage and protocol-driven invalidation;
- `Client.listen()` acknowledgment and the subscription event stream;
- protocol, client, and capability metadata.

### Operation ownership

| Operation | Framework-owned `Client` | Caller-owned `Client` | Caller-owned `ClientSession` |
|---|---|---|---|
| Connection lifecycle | Agent Framework constructs, enters, and closes the Client | Caller constructs, enters, and closes the Client | Caller constructs and closes the session |
| Connection negotiation | Enter `Client` in automatic mode | Reuse the already-entered Client | Initialize only when required for legacy compatibility |
| `tools/list`, `tools/call` | High-level `Client` operation | High-level `Client` operation | Direct `ClientSession` operation |
| `prompts/list`, `prompts/get` | High-level `Client` operation | High-level `Client` operation | Direct `ClientSession` operation |
| Resource reads | `Client` with SDK cache behavior | `Client` with SDK cache behavior | Direct, uncached session call |
| Catalog subscriptions | Agent Framework owns recovery around `Client.listen()` | Agent Framework owns recovery around `Client.listen()` | Legacy notification handling only |
| `MCPTool.session` | `None` | `None` | The caller-supplied `ClientSession` |
| Tasks or arbitrary extension RPCs | Future supported Client API | Future supported Client API | Raw session request only at an explicit extension boundary |

### Cache policy

High-level Clients use SDK response caching for catalog and resource operations regardless of whether Agent Framework
or the caller owns the Client. Modern server `ttlMs` and `cacheScope` hints control reuse and invalidation. Legacy
peers do not provide those hints and remain effectively uncached under the default zero TTL.

Caller-supplied `ClientSession` connections always call the server directly. Agent Framework does not expose a
shared cache store or cache-mode configuration. Reconnect or an effective header-identity change replaces the
framework-owned Client and its per-client cache.

### MRTR

For both framework-owned and caller-owned high-level connections, `tools/call`, `prompts/get`, and `resources/read`
use the Client. The SDK drives embedded elicitation, sampling, and roots requests and retries the original operation
with the required responses and state.

Agent Framework does not import the SDK's private MRTR driver or implement parallel MRTR loops. A caller-supplied
session remains a raw low-level path and does not gain automatic MRTR merely because callbacks are configured on it.

Durable pause/resume across processes would require a separate continuation design and function-calling-loop review;
it is not part of this decision.

### Subscription recovery

The SDK Client owns protocol-level `listen` acknowledgment and event delivery. Agent Framework owns the long-running
subscription lifecycle around it:

- one background subscription task per active high-level Client;
- tool and prompt catalog refresh when events arrive;
- refresh before reopening after stream loss or completion;
- retry with bounded backoff for recoverable subscription failures;
- cancellation when the connection is reset, replaced, or closed;
- fallback to legacy catalog notifications when the peer does not support `listen`.

The recovery task always verifies that the Client is still the active connection before refreshing or reopening, so
an obsolete subscription cannot mutate a replacement connection's catalogs.

### Caller-supplied high-level Clients

A caller-supplied `Client` is the preferred way to provide an existing connection:

- The Client must already be entered before the MCP tool connects.
- Agent Framework does not enter, close, replace, or recreate it.
- Standard operations continue through the high-level Client and retain SDK MRTR and response-cache behavior.
- Agent Framework manages its own catalog-subscription task around `Client.listen()` while the wrapper is connected.
- `MCPTool.session` remains `None`.
- Closing or resetting the wrapper preserves the supplied Client so the caller can continue using or closing it.

### Caller-supplied low-level sessions

A caller-supplied `ClientSession` remains a deprecated low-level compatibility path:

- Agent Framework does not enter, close, replace, wrap, or reconnect it.
- An already negotiated session is reused.
- An unnegotiated session retains legacy initialization compatibility.
- Standard calls remain direct and do not gain high-level MRTR or SDK response caching.
- `MCPTool.session` returns this session and can replace or clear this low-level connection path.

The SDK does not provide a public API that adopts an existing `ClientSession` into a high-level Client without
opening a separate connection, so Agent Framework does not simulate adoption.

### Legacy callbacks, logging, and liveness

Framework-created connections use automatic protocol negotiation even when sampling is configured. The SDK routes
the same callback through the legacy server-to-client back-channel and through modern embedded MRTR requests.

Modern request metadata carries log-level preference. Legacy `logging/setLevel` and ping behavior remain explicitly
protocol-gated compatibility operations; they are not universal preflights.

### Tasks

The supported MCP Python SDK 2.x runtime does not expose the current `io.modelcontextprotocol/tasks` extension.
Tools that may require Tasks are not presented as ordinary supported calls, and the removed long-running Tasks
sample remains deferred. An MRTR `InputRequiredResult` is not a Tasks `input_required` status.

## Consequences

- Good, because modern and legacy peers use one public Agent Framework API.
- Good, because standard operations, MRTR, and caching stay on the supported high-level SDK surface.
- Good, because the connection seam distinguishes framework-owned and caller-owned high-level Clients from the
  deprecated low-level session path.
- Good, because reconnect, cancellation, header identity, subscription recovery, parsing, and policy remain Agent
  Framework concerns.
- Neutral, because caller-supplied low-level sessions intentionally have fewer protocol conveniences.
- Neutral, because `MCPTool.session` returns `None` for all high-level Client connections.
- Bad, because integrations that previously treated `session` as a universal connection handle must instead use the
  operation seam, a caller-owned Client, or the deprecated caller-owned session path.

## Validation

Committed contract tests cover:

- modern negotiation and legacy fallback;
- framework-owned Client publication, failure cleanup, reset, reconnect, cancellation, and header identity changes;
- caller-owned Client publication, high-level operation routing, capability reuse, reset preservation, and cleanup;
- standard operations routing through the active Client;
- tool, prompt, and resource MRTR;
- cache TTL, pagination, invalidation, reconnect, and identity changes;
- caller-owned session behavior remaining direct, uncached, and caller-owned;
- subscription refresh, stream loss, retry/backoff, replacement, cancellation, and legacy notification fallback;
- legacy sampling, logging, and ping compatibility.

## Pros and Cons of the Options

### Use Client for high-level operations

- Good, because it uses the SDK's supported high-level surface.
- Good, because it avoids duplicate negotiation, MRTR, and caching code.
- Good, because the low-level session remains available as a deprecated caller-owned compatibility path.
- Bad, because code cannot assume every MCP connection exposes a `ClientSession`.

### Use Client only for negotiation

- Good, because it would minimize immediate routing changes.
- Bad, because calling `client.session` for operations bypasses SDK-owned MRTR and caching.
- Bad, because each new protocol feature would reopen the same ownership question.

### Reimplement behavior around ClientSession

- Good, because Agent Framework could expose every intermediate protocol round.
- Bad, because it would duplicate SDK protocol policy, cancellation behavior, round limits, and cache invalidation.
- Bad, because it would add continuation complexity without a durable continuation requirement.

### Add era-specific public classes

- Good, because callers could force a known protocol era.
- Bad, because callers should not need to know the peer's era before connecting.
- Bad, because it would fragment public classes, samples, and tests.

## More Information

- [Python MCP 2026-07-28 umbrella issue](https://github.com/microsoft/agent-framework/issues/8245)
- [MCP Python SDK client guide](https://py.sdk.modelcontextprotocol.io/client/)
- [MCP Python SDK MRTR guide](https://py.sdk.modelcontextprotocol.io/handlers/multi-round-trip/)
- [MCP Python SDK caching guide](https://py.sdk.modelcontextprotocol.io/client/caching/)
- [MCP Python SDK subscriptions guide](https://py.sdk.modelcontextprotocol.io/client/subscriptions/)
- [MCP MRTR specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr)
- [MCP subscriptions specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/subscriptions)
- [MCP caching specification](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching)
- [ADR 0043: MCP runtime context](0043-python-mcp-runtime-context.md)

This ADR remains `proposed` until accepted through the repository ADR review process.
