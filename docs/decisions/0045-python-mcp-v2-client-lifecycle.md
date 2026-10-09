---
status: proposed
date: 2026-10-06
deciders: jpalvarezl, eavanvalkenburg
---

# Use the MCP SDK Client as the primary Python MCP client

## Context and Problem Statement

The Python `MCPTool` implementation originally owned an MCP transport, constructed a low-level `ClientSession`, and
used that session for every operation. That design matched handshake-era protocol versions through 2025-11-25.

The MCP Python SDK v2 adds a high-level `Client` that owns protocol negotiation and standard client behavior. In
`mode="auto"` it probes `server/discover` for a 2026-07-28 peer and falls back to the legacy `initialize` handshake.
Its standard operation methods add automatic multi-round-trip request (MRTR) handling, response caching and cache
invalidation coordination, and claimed extension-result resolution that session-tier calls do not provide.
`ClientSession` can still declare callback capabilities from its configured callbacks, and the SDK exposes a typed
subscription helper over an entered session; the high-level `Client` is the normal API that configures and coordinates
those features with its own operations and cache.

The first migration pass entered `Client` for framework-created connections but continued to route most operations
through `client.session`. That partial adoption supports both protocol eras, but it bypasses SDK-owned behavior and
leaves later migration work with two possible implementations.

This decision defines the lasting ownership boundary: which work belongs to the SDK `Client`, which work remains
Agent Framework policy, and when direct `ClientSession` access is justified.

This ADR covers the outbound Python MCP client. Hosting/server code uses the SDK server APIs and is not converted to
`Client`.

## Decision Drivers

- One Agent Framework path must support 2026-07-28 and 2025-era MCP peers.
- Standard protocol behavior should remain owned by the MCP SDK rather than being copied into Agent Framework.
- Existing `MCPTool`, `MCPStdioTool`, and `MCPStreamableHTTPTool` APIs and `async with` ergonomics must remain
  compatible.
- Framework-created resources must still be closed by the task that opened them, including cancellation and failed
  connection attempts.
- Caller-supplied sessions and HTTP clients must remain caller-owned.
- Existing tool argument filtering, parsing, tracing, reconnect, header identity, and security behavior must remain
  Agent Framework policy around the SDK operation.
- Moving from `ClientSession` to `Client` must not silently change cache or refresh behavior.
- Tools, prompts, and resources must share one client-ownership rule rather than acquire separate MRTR loops.
- Tasks and delayed/durable human-input continuation must remain separate from base MRTR support.

## Considered Options

- Retain the high-level SDK `Client` and use it for standard operations, with `ClientSession` as an explicit escape
  hatch.
- Use `Client` only for negotiation while continuing all operations through `client.session`.
- Reimplement negotiation, MRTR, caching, and subscriptions around `ClientSession`.
- Add separate modern and legacy Agent Framework tool classes or a public protocol-mode switch.

## Decision Outcome

Chosen option: "Retain the high-level SDK `Client` and use it for standard operations, with `ClientSession` as an
explicit escape hatch", because it delegates protocol mechanics to the supported SDK surface while preserving Agent
Framework's lifecycle and application policy.

### Decided target ownership model

The following is the target state established by this decision; the branch has not implemented every item yet.

For a framework-created connection, `MCPTool` will own and retain one entered `mcp.Client`. It will continue exposing
that client's underlying `ClientSession` through the existing `session` attribute for compatibility and advanced use.
The client and session form one connection unit: they are published only after successful negotiation and are cleared
and replaced together on close, reset, reconnect, cancellation cleanup, or authenticated-header identity change.

Agent Framework continues to own:

- the lifecycle-owner task and locks;
- transport construction and request-scoped HTTP header identity;
- reconnect policy around complete high-level operations;
- tool argument filtering and trusted request metadata merging;
- result parsing, Agent Framework content conversion, tracing, and error translation;
- catalog publication and rollback after a failed complete fetch;
- security and approval policy.

The SDK `Client` owns:

- `server/discover` negotiation and legacy `initialize` fallback;
- standard tools, prompts, and resources operations;
- MRTR callback dispatch, retries, round limits, state echo, and state-only backoff;
- response-cache storage and protocol notification invalidation;
- `subscriptions/listen` acknowledgment and event delivery;
- protocol/client/capability metadata stamps;
- extension result-claim resolution registered on the client.

### Operation ownership

| Operation | Default path | Direct `ClientSession` exception |
|---|---|---|
| Connection negotiation | `Client(mode="auto")` | A caller-supplied session is already negotiated, or an unnegotiated supplied session retains legacy `initialize()` compatibility. |
| `tools/list`, `tools/call` | `Client` | Manual MRTR or raw claimed-extension results. |
| `prompts/list`, `prompts/get` | `Client` | Manual MRTR. |
| `resources/list`, `resources/templates/list`, `resources/read` | `Client` | Manual MRTR or a deliberately uncached low-level caller-owned session. |
| `subscriptions/listen` | `Client.listen()` | The SDK session helper may be used for a caller-supplied session, without a framework-owned client cache. |
| Standard request metadata | High-level operation `meta=` | Raw extension requests use `ClientSession.send_request()`. |
| Modern log-level opt-in | `Client(log_level=...)` | Legacy `logging/setLevel` remains negotiated-version compatibility only. |
| Legacy ping | None for modern connections | A protocol-gated legacy session call may remain temporarily. |
| Tasks or arbitrary extension RPCs | Future extension/client API | Raw `ClientSession.send_request()` at the extension boundary only. |

Code should use one private, connection-bound operation provider rather than repeat `Client`/`ClientSession`
selection independently across tools, prompts, skills, security helpers, and Foundry integrations.

### Cache policy is explicit

High-level and low-level calls are not interchangeable. `ClientSession` always reaches the server. In SDK 2.2.0,
`Client` makes page-one results for tools, prompts, resources, and resource templates, plus `resources/read`, cache
aware; `tools/call` and `prompts/get` are not cached. A result is reusable only when it has a positive effective TTL.
Absent server hints use `CacheConfig.default_ttl_ms`, whose default is `0`. Under `cache_mode="use"`, non-`None`
request metadata forces a wire refresh. Although `server/discover` carries protocol cache hints, SDK 2.2.0 deliberately
excludes it from the response cache; persisting or reusing `prior_discover` is caller-managed.

Framework-owned connections use the SDK's default `cache_mode="use"` for tool and prompt catalogs and resource
reads. Modern server-provided `ttlMs` / `cacheScope` hints therefore control freshness. Legacy peers provide no
hints and remain uncached under the SDK's default zero TTL; caller-supplied `ClientSession` connections bypass the
SDK response cache.

Agent Framework does not expose a cache-mode or shared-cache configuration surface. A reconnect or effective
header-identity change replaces the whole Client and its default per-client cache. Exposing a shared store would
require a separate authorization-partition design and, because Agent Framework constructs `Client` from a transport
rather than a URL, an explicit stable `CacheConfig.target_id`.

Resource and catalog cache tests cover positive TTLs, pagination, empty snapshots, reconnect, notifications, and
authenticated identity changes.

MRTR-seeded and MRTR-resolved resource reads are not cached by the SDK.

### MRTR

For framework-owned connections, Agent Framework delegates MRTR for `tools/call`, `prompts/get`, and
`resources/read` to the high-level `Client`. The SDK dispatches embedded elicitation, sampling, and roots requests to
the callbacks configured on that client, retries with `inputResponses`, echoes `requestState` unchanged, assigns a
new JSON-RPC request ID, and applies its round limit and state-only backoff.

Agent Framework does not import the private `mcp.client._input_required` driver and does not implement separate
tool, prompt, or resource loops.

Direct session handling with `allow_input_required=True` is reserved for a future requirement to persist, inspect, or
resume MRTR rounds outside the process that began the operation. `UserInputRequiredException` is currently a way to
surface a pause, not a complete persisted MCP continuation model. Delayed or durable human-input continuation
therefore requires a separate design and function-calling-loop review; it is not part of the base MRTR migration.

### Caller-supplied clients and sessions

A caller-supplied `ClientSession` remains a low-level compatibility path:

- Agent Framework does not enter, close, replace, wrap, or reconnect it.
- An already negotiated session is reused through its era-neutral properties.
- An unnegotiated session retains legacy `initialize()` compatibility.
- Standard calls remain direct and therefore do not gain automatic MRTR or SDK response caching.
- Callbacks configured on the session do not by themselves drive MRTR.

SDK 2.2.0 has no public API that adopts an existing `ClientSession` into `Client`, and it does not export the MRTR
driver. Agent Framework must not open a second connection to simulate adoption.

Experiments proved that an already-entered, caller-owned high-level `Client` can be reused without transferring
ownership and can provide automatic MRTR. A public API for that path is preferred over a framework-owned MRTR loop,
but it requires a separate API decision. It should not force callers to provide dummy transport arguments to
transport-specific wrappers.

### Legacy callbacks, logging, and liveness

Framework-created connections use `mode="auto"` even when sampling is configured. The SDK routes the same
`sampling_callback` through the legacy server-to-client back-channel after a 2025 fallback and through embedded MRTR
requests after modern discovery. Agent Framework does not infer the protocol era from the presence of its sampling
ChatClient.

Modern protocol logging is per-request metadata. Agent Framework should pass the selected log level to `Client` so
the SDK stamps `io.modelcontextprotocol/logLevel`; `logging/setLevel` is retained only for a negotiated legacy peer.
New logging behavior should prefer normal Python logging and OpenTelemetry because MCP protocol logging is
deprecated.

`ping` is removed in 2026-07-28. It is not a universal liveness preflight. Operation failures drive reconnect; any
remaining ping call is explicitly gated to a legacy session.

### Checklist boundaries

The Client-first cleanup strengthens the foundation of completed migration rows without reopening their accepted
scope:

- Hosting/server remains server-side and checked.
- Tools, Tool refresh, Prompts, and Skills remain checked for their stated dual-era behavior.
- MRTR, Caching, Logging, Samples/docs, local validation, and live dual-era validation remain separate checklist work.
- The protocol-independent prompt snapshot bug remains in
  [microsoft/agent-framework#9115](https://github.com/microsoft/agent-framework/issues/9115).
- Optional subscription stream recovery remains in
  [microsoft/agent-framework#9109](https://github.com/microsoft/agent-framework/issues/9109).
- Tasks and the removed task sample remain blocked until the Python SDK exposes the current
  `io.modelcontextprotocol/tasks` runtime. A task status of `input_required` is not MRTR `InputRequiredResult`.

### Consequences

- Good, because modern and legacy servers use one public Agent Framework API and SDK-supported negotiation.
- Good, because standard protocol behavior, MRTR, subscriptions, and caching stay with the SDK.
- Good, because stdio, Streamable HTTP, reconnect, cancellation, header identity, parsing, and policy remain Agent
  Framework concerns.
- Good, because tools, prompts, and resources follow one ownership rule.
- Neutral, because Agent Framework keeps both a private high-level client and the public low-level `session` view.
- Neutral, because caller-supplied `ClientSession` objects intentionally remain lower level.
- Bad, because tests and integrations that mock `tool.session` may need to move toward operation or transport
  contract tests.
- Bad, because adopting `Client` exposes cache behavior that must be selected and tested explicitly.

## Validation

Existing committed contract tests cover:

- modern Streamable HTTP discovery without `initialize`;
- legacy fallback on the same public tool path;
- modern and legacy stdio list/call behavior;
- required headers, `_meta`, parsing, tracing, reconnect, lifecycle ownership, and caller-owned sessions;
- modern `Client.listen()` with legacy notification fallback;
- dual-era prompts and skills resource-not-found behavior.

Separate detached-worktree experiments based on commit `a02f9ff8c487d04c719d4ce5e3a3a8326b856673` established:

- the existing direct-session tool call raises on the first state-only `InputRequiredResult`;
- retaining and calling `Client` causes SDK 2.2.0 to retry with the same operation arguments, exact
  `requestState`, omitted empty `inputResponses`, and a new JSON-RPC request ID;
- high-level tools, prompts, and resources MRTR work without function-calling-loop changes;
- metadata, parsing, tracing, reconnect, subscriptions, and legacy fallback remain compatible;
- a caller-owned, already-entered `Client` remains usable after an Agent Framework wrapper closes;
- a caller-supplied `ClientSession` does not gain automatic MRTR merely by having callbacks.

Implementation validation for this decision must cover:

- retained Client publication, failure cleanup, close, reset, reconnect, cancellation, and header identity change;
- standard operations routing through the current owned Client, never a stale prior Client;
- tool, prompt, and resource MRTR, including state-only and embedded callback rounds;
- explicit cache modes, positive TTLs, pagination, invalidation, and refresh;
- caller-owned `ClientSession` behavior remaining direct, uncached, and caller-owned;
- legacy sampling, logging, and ping compatibility;
- full core source and test typing plus the complete affected unit suites.

## Pros and Cons of the Options

### Retain Client and use it for standard operations

- Good, because it uses the SDK's supported, documented client surface.
- Good, because it avoids duplicate negotiation, MRTR, caching, and subscription code.
- Good, because the low-level session remains available where genuinely required.
- Bad, because operation mocks and cache-sensitive tests need deliberate migration.

### Use Client only for negotiation and session for operations

- Good, because it minimizes immediate code changes.
- Bad, because it bypasses SDK-owned MRTR, caching, extension claims, and subscription cache coordination.
- Bad, because every new protocol feature reopens the same ownership question.
- Bad, because the difference between framework-owned and caller-owned sessions becomes implicit.

### Reimplement behavior around ClientSession

- Good, because it could expose every intermediate round to Agent Framework.
- Bad, because Agent Framework would duplicate SDK protocol policy and future changes.
- Bad, because exactly-once execution, cancellation, concurrent callback dispatch, round limits, and cache
  invalidation become framework responsibilities.
- Bad, because the function-calling loop would be changed before a durable continuation requirement exists.

### Add era-specific tool classes or a public protocol-mode switch

- Good, because callers could force a known era.
- Bad, because callers should not need to know the peer's era before connecting.
- Bad, because it fragments public classes, tests, and documentation.
- Bad, because it can disable SDK fallback accidentally.

## More Information

- [Python MCP 2026-07-28 umbrella issue](https://github.com/microsoft/agent-framework/issues/8245)
- [MCP Python SDK v1-to-v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/#clients)
- [MCP Python SDK Client guide](https://py.sdk.modelcontextprotocol.io/client/)
- [MCP Python SDK MRTR guide](https://py.sdk.modelcontextprotocol.io/handlers/multi-round-trip/)
- [MCP Python SDK caching guide](https://py.sdk.modelcontextprotocol.io/client/caching/)
- [MCP Python SDK subscriptions guide](https://py.sdk.modelcontextprotocol.io/client/subscriptions/)
- [MCP 2026 MRTR specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr)
- [MCP 2026 subscriptions specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/subscriptions)
- [MCP 2026 caching specification](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching)
- [ADR 0043: MCP runtime context](0043-python-mcp-runtime-context.md)

While this ADR remains `proposed`, implementation sessions should treat it as the current evidence-backed direction
for microsoft/agent-framework#8245 and revise it if new SDK or code evidence changes the decision. It becomes
`accepted` only through the repository ADR review process.
