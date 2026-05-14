# PR #5696 — Gap Analysis vs. MSRC AG-UI `ThreadId` Session-Hijack Report

This note evaluates how completely the changes in
[PR #5696 — ".NET: Support ClaimsIdentity-based scoping of agent sessions"](https://github.com/microsoft/agent-framework/pull/5696)
address the **AG-UI**-specific MSRC report:

> The Microsoft Agent Framework AG-UI hosting endpoint (.NET) trusts the
> client-supplied `RunAgentInput.ThreadId` as the sole key for persisted
> session lookup. […] The `AgentSessionStore` abstract contract carries
> only `(AIAgent agent, string conversationId)` with no principal/owner
> parameter, making caller-scoped sessions architecturally impossible
> without a custom implementation.

The MSRC severity rationale is *Low / Defense in Depth* — the default
AG-UI store is `NoopAgentSessionStore`, so the cross-user takeover only
materializes when the integrator (a) registers a persistent store and
(b) does not scope the thread-ID namespace by principal. The framework's
job here is to make the safe path obvious and to document the trust
assumption.

> **Design constraint set by the team:** flipping defaults so that the
> integrator is *required* to register a `SessionIsolationKeyProvider`
> before persistence works is **explicitly out of scope** — first-run /
> single-user / prototyping scenarios must continue to work
> "out of the box". Any auto-isolation mechanism must therefore degrade
> to a transparent no-op when no principal context is configured.

## What the PR delivers (AG-UI-relevant pieces only)

- `SessionIsolationKeyProvider` abstraction
  (`dotnet/src/Microsoft.Agents.AI.Hosting/SessionIsolationKeyProvider.cs`).
- `IsolationKeyScopedAgentSessionStore` decorator that prefixes
  `conversationId` with `{escapedKey}::` before forwarding to the inner
  store, with a `Strict` knob.
- `DelegatingAgentSessionStore` base + `AgentSessionStore.GetService(...)`
  service-locator hooks so wrappers can be discovered in a chain.
- `Microsoft.Agents.AI.Hosting.AspNetCore` package shipping
  `ClaimsIdentitySessionIsolationKeyProvider` and
  `services.UseClaimsBasedSessionIsolation(...)`.
- Auto-wrap on the **`HostedAgentBuilderExtensions.WithSessionStore(...)`**
  path: stores registered through `WithSessionStore(...)` /
  `WithInMemorySessionStore(...)` are wrapped in
  `IsolationKeyScopedAgentSessionStore` by default
  (`withIsolation: true`). When no provider is registered, the wrapper
  is constructed with `Strict = false` so it passes the bare
  `conversationId` through — i.e. the "out-of-box first-run" constraint
  above is honoured.
- AG-UI sample
  (`dotnet/samples/05-end-to-end/AGUIClientServer/AGUIServer/Program.cs`)
  gets a single commented reminder pointing at
  `UseClaimsBasedSessionIsolation`.

## Item-by-item map of MSRC's recommended fixes to the PR

### MSRC Fix #1 — Strengthen XML doc on `MapAGUI`, `InMemoryAgentSessionStore`, `AgentSessionStore` to state the trust model when a persistent store is in play

**Status: ❌ Not addressed on the named surfaces.**

- `AGUIEndpointRouteBuilderExtensions.MapAGUI(...)` doc
  (`dotnet/src/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore/AGUIEndpointRouteBuilderExtensions.cs:70-76`)
  still reads:
  > If an `AgentSessionStore` is registered in dependency injection
  > keyed by the agent's name, it will be used to persist conversation
  > sessions across requests using the AG-UI thread ID as the
  > conversation identifier. If no session store is registered, sessions
  > are ephemeral (not persisted).
  No mention of the trust assumption (thread-id = chain-resume token, not
  an authorization token; multi-user hosts must scope by principal).
- `InMemoryAgentSessionStore` XML
  (`dotnet/src/Microsoft.Agents.AI.Hosting/Local/InMemoryAgentSessionStore.cs:13-27`)
  warns about restart loss but says nothing about the multi-user
  takeover risk.
- `AgentSessionStore` base class XML
  (`dotnet/src/Microsoft.Agents.AI.Hosting/AgentSessionStore.cs`) only
  describes the persistence contract; it does not call out that
  `(agent, conversationId)` carries no principal dimension and that
  custom implementations must compose one for multi-user hosts.

The new types (`IsolationKeyScopedAgentSessionStore`,
`SessionIsolationKeyProvider`, `ClaimsIdentitySessionIsolationKeyProvider`,
`UseClaimsBasedSessionIsolation`) are themselves well documented, but
nothing on the legacy IntelliSense path prompts the integrator to look
for them.

### MSRC Fix #2 — Compose principal into the conversation key inside the AG-UI handler when a `ClaimsPrincipal` is available, gated by a versioned opt-in (e.g. `MapAGUIOptions { ScopeSessionsByPrincipal = true }`)

**Status: ⚠️ Partially addressed; opt-in path exists but does not cover
the canonical AG-UI registration shape.**

The PR does *not* edit the AG-UI handler to read `HttpContext.User`. It
takes a different architectural shape: the scoping is done by a
decorator inserted around the store. That decorator must actually be
present in the chain that `MapAGUI` resolves, which means one of these
must be true:

1. The integrator registered the store via the
   `IHostedAgentBuilder.WithSessionStore(...)` / `WithInMemorySessionStore(...)`
   helper. Those auto-wrap with `IsolationKeyScopedAgentSessionStore`
   (the new `withIsolation: true` default).
2. The integrator manually composes
   `new IsolationKeyScopedAgentSessionStore(innerStore, provider)` and
   registers that as the keyed store.

But the **AG-UI handler resolves the store directly from DI**:

```csharp
// AGUIEndpointRouteBuilderExtensions.cs:85-86
var agentSessionStore = endpoints.ServiceProvider.GetKeyedService<AgentSessionStore>(aiAgent.Name);
var hostAgent = new AIHostAgent(aiAgent, agentSessionStore ?? new NoopAgentSessionStore());
```

So an integrator who follows the most natural "I want persistence" line —

```csharp
services.AddKeyedSingleton<AgentSessionStore>(agentName, new InMemoryAgentSessionStore());
// + services.UseClaimsBasedSessionIsolation(...);
```

— still gets **no scoping on AG-UI**, even with an isolation provider
registered, because the keyed store goes straight into `AIHostAgent`
without ever passing through `WithSessionStore`'s wrapping logic. That
is precisely the precondition pattern the MSRC report calls out. (See
gap **G1** below.)

There is also no `MapAGUIOptions` / no MapAGUI-level opt-in flag of the
shape MSRC suggested. Discoverability of the safe path lives entirely on
a separate `services.UseClaimsBasedSessionIsolation(...)` extension and
on whether the integrator happened to use the right store-registration
helper.

### MSRC Fix #3 (optional) — Add a principal-aware overload to `AgentSessionStore` so custom stores can scope by principal without injecting `IHttpContextAccessor`

**Status: ✅ Achieved via decorator instead of a virtual overload.**

The PR does not add a 3-arg `GetSessionAsync(agent, conversationId, scopeId, ct)`
virtual on `AgentSessionStore`. Instead, scope composition is done
upstream by `IsolationKeyScopedAgentSessionStore`, and the inner store
sees a mutated `conversationId` of the form
`{escapedKey}::{conversationId}`. This achieves the *outcome* MSRC asked
for (custom stores no longer need `IHttpContextAccessor`) but with two
documented-by-implication trade-offs noted in **G3** below.

## Remaining gaps for the AG-UI threat scenario

### G1. `MapAGUI` does not auto-wrap the keyed store; safe path requires a non-obvious registration shape

This is the headline gap relative to the MSRC AG-UI report. The
isolation wrapper is auto-installed only on the
`HostedAgentBuilder.WithSessionStore(...)` path and on the
A2A `CreateA2AServer` code path. `MapAGUI` reads the keyed
`AgentSessionStore` from DI directly
(`AGUIEndpointRouteBuilderExtensions.cs:85`) and never inspects whether
an `IsolationKeyScopedAgentSessionStore` is in the chain.

Concrete consequence: the canonical "I want persistent AG-UI sessions"
snippet —

```csharp
services.AddKeyedSingleton<AgentSessionStore>("myAgent", new InMemoryAgentSessionStore());
services.UseClaimsBasedSessionIsolation(new() { ClaimType = ClaimTypes.NameIdentifier });
endpoints.MapAGUI("myAgent", "/ag-ui");
```

does *not* scope by principal. The integrator must additionally know to
either (a) register their store via the `WithSessionStore` builder
helper, or (b) hand-compose
`new IsolationKeyScopedAgentSessionStore(inner, provider)` themselves.

**Suggested closure**: in `MapAGUI` (mirroring the A2A pattern), if the
resolved store does not already expose
`IsolationKeyScopedAgentSessionStore` via the new `GetService(...)`
chain, wrap it. Use the same `Strict = isolationKeyProvider != null`
construction the A2A path uses, so the no-provider case stays a
transparent no-op (preserving the out-of-box constraint).

### G2. Trust-model docs missing on the three legacy AG-UI surfaces (MSRC Fix #1)

`MapAGUI`, `InMemoryAgentSessionStore`, and `AgentSessionStore` need the
explicit "thread id is a chain-resume identifier, not an authorization
token; multi-user hosts must scope sessions by principal" wording, with
a pointer to `UseClaimsBasedSessionIsolation` /
`IsolationKeyScopedAgentSessionStore`. Today nothing on those surfaces
flags the risk or points readers at the new safe-path APIs.

### G3. Decorator approach mutates `conversationId` seen by inner stores, undocumented

`IsolationKeyScopedAgentSessionStore` rewrites the `conversationId` to
`{escapedKey}::{conversationId}` before forwarding. Two things follow
that custom-store authors would benefit from being told:

1. Stores that log, echo, or surface `conversationId` (telemetry,
   audit, error messages) will leak the isolation key into those sinks.
2. Stores with constraints on conversation-id shape (length, allowed
   characters, URL-safety, hashing) must accept `\\`/`\:`-escaped keys
   of arbitrary length.

A short note on `IsolationKeyScopedAgentSessionStore` (and ideally on
`AgentSessionStore` itself — "implementations should treat
`conversationId` as opaque") would close this.

### G4. Only one provider implementation ships; `ClaimType` lookup is single-claim only

The MSRC suggested fix uses
`ClaimTypes.NameIdentifier ?? Identity.Name` as the fallback chain.
`ClaimsIdentitySessionIsolationKeyProvider` only resolves a single
configured `ClaimType` and does not fall back to `Identity.Name`. That
will silently produce a `null` key (and, in the non-strict default
configuration on the A2A auto-wrap path, a silent no-op) for valid
authenticated identities that don't carry the configured claim. A
second-chance fallback list, or shipping a small set of common
providers (e.g. `Identity.Name`, an HTTP-header provider, an mTLS
subject provider), would close the discoverability gap on the safe
path.

### G5. AG-UI sample is a commented reminder, not a working safe configuration

`samples/05-end-to-end/AGUIClientServer/AGUIServer/Program.cs` adds a
single commented-out line. The sample's runtime behaviour is unchanged;
copy-paste users still land on the unscoped path. At least one AG-UI
sample should compile and run with `UseClaimsBasedSessionIsolation`
plus a working auth scheme so the safe pattern is shown end-to-end. The
sample also needs to demonstrate registering the store through
`WithSessionStore(...)` rather than via raw `AddKeyedSingleton` so that
the decorator chain actually engages — unless **G1** is fixed first.

### G6. Asymmetry between A2A and AG-UI auto-wrap behaviour

`A2AServerServiceCollectionExtensions.CreateA2AServer` was edited to
auto-wrap any keyed store with `IsolationKeyScopedAgentSessionStore`
when one isn't already in the chain
(`A2AServerServiceCollectionExtensions.cs:140-146` after the PR).
The equivalent change was *not* made on the AG-UI endpoint
extension, so the two hosting layers now have asymmetric behaviour:
isolation kicks in automatically on A2A but only on AG-UI when the
integrator routes their store through the builder helpers. This
re-creates, in a different shape, the "asymmetric defaults are a
perpetual source of integrator confusion" anti-pattern that MSRC
called out for the persistence default. (Note: this is **not** a
"flip the default" ask — it's a "make the two hosting layers behave
the same when an isolation provider is registered" ask. The
out-of-box no-provider behaviour stays unchanged.)

## Summary scorecard (AG-UI threat surface)

| MSRC ask | Status |
|---|---|
| #1 Trust-model XML on `MapAGUI`, `InMemoryAgentSessionStore`, `AgentSessionStore` | ❌ Not addressed |
| #2 Principal-scoping inside the AG-UI handler (versioned opt-in) | ⚠️ Equivalent opt-in mechanism exists (`UseClaimsBasedSessionIsolation` + decorator), but the AG-UI handler does not engage it for stores registered the canonical way |
| #3 Optional principal-aware store overload | ✅ Achieved via decorator (with caveats — see G3) |
| AG-UI sample shows safe pattern | ⚠️ Commented reminder only |
| Symmetric behaviour with the A2A hosting layer | ❌ A2A auto-wraps in handler; AG-UI does not |

## Recommended follow-ups (priority order)

1. **Auto-wrap inside `MapAGUI`** mirroring the A2A pattern: if the
   resolved keyed store does not expose `IsolationKeyScopedAgentSessionStore`
   via `GetService<...>()`, wrap it with
   `Strict = isolationKeyProvider != null`. This preserves the
   out-of-box no-provider behaviour while making the safe path engage
   automatically as soon as the integrator opts in via
   `UseClaimsBasedSessionIsolation` (closes **G1** and **G6**).
2. Add the trust-model XML paragraph to `MapAGUI`,
   `InMemoryAgentSessionStore`, and `AgentSessionStore`, each pointing
   at `UseClaimsBasedSessionIsolation` and
   `IsolationKeyScopedAgentSessionStore` (closes **G2**).
3. Document the `conversationId`-mutation contract that the decorator
   imposes on inner stores (closes **G3**).
4. Either widen `ClaimsIdentitySessionIsolationKeyProvider` to a
   fallback chain (`ClaimType` → `Identity.Name`) or ship one or two
   additional providers (header / mTLS subject) so the safe path is
   discoverable beyond the single Claims case (closes **G4**).
5. Convert the AG-UI sample from a commented reminder into a working
   safe-by-default configuration (closes **G5**).
