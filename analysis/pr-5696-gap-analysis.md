# PR #5696 — Gap Analysis vs. the MSRC Session-Scoping Reports

This note evaluates how completely the changes in
[PR #5696 — ".NET: Support ClaimsIdentity-based scoping of agent sessions"](https://github.com/microsoft/agent-framework/pull/5696)
address two related MSRC reports against the .NET hosting layer:

- **Part A** — the *A2A persistence-default* report (the originally-filed
  variant): an A2A server, configured per the in-tree quickstart, persists
  sessions keyed only by the wire-supplied `contextId`, with no
  principal/owner dimension on the `AgentSessionStore` contract.
- **Part B** — the *AG-UI `ThreadId` session-hijack* report: the AG-UI
  hosting endpoint trusts the client-supplied `RunAgentInput.ThreadId` as
  the sole session-lookup key.

Both reports are rated **Low / Defense-in-Depth** by MSRC because the
default registered store is a no-op (`NoopAgentSessionStore`); the
cross-user takeover only materializes when an integrator (a) registers a
persistent store and (b) does not scope the conversation-id namespace by
principal.

> **Design constraint set by the team (applies to both parts):**
> flipping defaults so that the integrator is *required* to register a
> `SessionIsolationKeyProvider` before persistence works is **explicitly
> out of scope**. First-run / single-user / prototyping scenarios — where
> there is no `ClaimsPrincipal`, no auth scheme, and no isolation
> provider — must continue to work "out of the box". Any auto-isolation
> mechanism must therefore degrade to a transparent no-op when no
> principal context is configured.

---

## Part A — A2A persistence-default report

> Reconstructed from the prior session's notes; the verbatim text was not
> committed to the repo. Findings re-verified against PR #5696 head.

### The reported issue

The A2A hosting layer's quickstart pattern —

```csharp
services.AddAIAgent(...)
        .WithSessionStore(new InMemoryAgentSessionStore())
        .AsA2AServer();
```

— produces a server in which any caller who knows (or guesses) another
caller's `contextId` can resume that other caller's persisted thread,
because:

1. `AgentSessionStore.GetSessionAsync(AIAgent agent, string conversationId, CancellationToken)`
   is the only lookup primitive; the contract carries no principal
   dimension.
2. `A2AAgentHandler` resolves the keyed `AgentSessionStore` from DI and
   passes it directly to `AIHostAgent`, with the wire `contextId` flowing
   through unchanged.
3. The persistent stores in-tree (`InMemoryAgentSessionStore`,
   sample-grade SQLite/Redis demos) treat `(agent, conversationId)` as a
   complete primary key.

Because the documented A2A quickstart leads developers straight at this
shape, any multi-user A2A deployment that copies the quickstart inherits
the cross-tenant takeover.

### How PR #5696 changes the A2A path

The PR introduces an isolation-key abstraction and **auto-wraps on the
A2A code path** when an integrator opts in:

- `SessionIsolationKeyProvider` returns an opaque key from ambient
  context (the shipped impl reads `HttpContext.User`).
- `IsolationKeyScopedAgentSessionStore` is a `DelegatingAgentSessionStore`
  that prefixes the inbound `conversationId` with `{escapedKey}::` before
  forwarding to the inner store. It carries a `Strict` knob:
  - `Strict = false` — when the provider returns no key (e.g. anonymous
    request, no auth scheme configured), the call falls through with the
    bare `conversationId`. This is the "out-of-box" mode.
  - `Strict = true` — a missing key throws / refuses the operation.
- `A2AServerServiceCollectionExtensions.CreateA2AServer` resolves the
  keyed store, checks the `GetService<IsolationKeyScopedAgentSessionStore>()`
  service-locator chain, and wraps if needed with
  `Strict = isolationKeyProvider != null`.

Net effect on A2A:

| Scenario | Before PR | After PR |
|---|---|---|
| No persistent store registered | Ephemeral (`NoopAgentSessionStore`) | Unchanged — still ephemeral |
| Persistent store, **no** `UseClaimsBasedSessionIsolation` | Single-namespace persistence (vulnerable in multi-user) | **Same single-namespace persistence** — wrapper installed but in `Strict = false` no-op pass-through, so the out-of-box first-run scenario is preserved |
| Persistent store **plus** `services.UseClaimsBasedSessionIsolation(...)` | Still vulnerable (no wiring existed) | Auto-scoped per principal claim; missing claim → strict refusal |

### Item-by-item map of the A2A report's recommended fixes

| Recommended fix | Status |
|---|---|
| Add a principal/owner dimension to the persistence contract so multi-user safety is *expressible* without per-store rewrites | ✅ Achieved via decorator (`IsolationKeyScopedAgentSessionStore`) rather than a 3-arg `AgentSessionStore` virtual |
| Make the safe path **engage automatically** on the canonical A2A registration shape when an isolation provider is configured | ✅ `CreateA2AServer` auto-wraps the resolved keyed store |
| Preserve out-of-box single-user behaviour (no auth → still works) | ✅ `Strict = false` when no provider is registered; no behavioural change to the no-provider scenario |
| Document the trust model on `AgentSessionStore` / `InMemoryAgentSessionStore` / the A2A quickstart so integrators understand what `(agent, conversationId)` *isn't* | ❌ Not addressed; XML on the legacy surfaces is unchanged |
| Update the A2A end-to-end sample to model the safe pattern with a working auth scheme | ❌ Sample unchanged |

### Residual A2A gaps

- **A-G1.** Trust-model XML still missing on `AgentSessionStore`,
  `InMemoryAgentSessionStore`, and the A2A registration entry points.
  An integrator reading IntelliSense on the canonical pattern is not
  prompted toward `UseClaimsBasedSessionIsolation`.
- **A-G2.** No A2A sample exercises the safe configuration end-to-end.
- **A-G3.** Same `conversationId`-mutation contract caveats as Part B
  (B-G3 below): inner stores see a rewritten id; logging/telemetry sinks
  will leak the isolation key; stores with id-shape constraints must
  accept escaped keys of arbitrary length.

The headline A2A finding (the *handler-level* auto-wrap when a provider
is registered) **is** addressed by this PR, within the agreed
constraint. What remains for A2A is documentation and samples.

---

## Part B — AG-UI `ThreadId` session-hijack report

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

### What the PR delivers (AG-UI-relevant pieces only)

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

### Item-by-item map of MSRC's recommended fixes to the PR

#### MSRC Fix #1 — Strengthen XML doc on `MapAGUI`, `InMemoryAgentSessionStore`, `AgentSessionStore` to state the trust model when a persistent store is in play

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

#### MSRC Fix #2 — Compose principal into the conversation key inside the AG-UI handler when a `ClaimsPrincipal` is available, gated by a versioned opt-in (e.g. `MapAGUIOptions { ScopeSessionsByPrincipal = true }`)

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
gap **B-G1** below.)

There is also no `MapAGUIOptions` / no MapAGUI-level opt-in flag of the
shape MSRC suggested. Discoverability of the safe path lives entirely on
a separate `services.UseClaimsBasedSessionIsolation(...)` extension and
on whether the integrator happened to use the right store-registration
helper.

#### MSRC Fix #3 (optional) — Add a principal-aware overload to `AgentSessionStore` so custom stores can scope by principal without injecting `IHttpContextAccessor`

**Status: ✅ Achieved via decorator instead of a virtual overload.**

The PR does not add a 3-arg `GetSessionAsync(agent, conversationId, scopeId, ct)`
virtual on `AgentSessionStore`. Instead, scope composition is done
upstream by `IsolationKeyScopedAgentSessionStore`, and the inner store
sees a mutated `conversationId` of the form
`{escapedKey}::{conversationId}`. This achieves the *outcome* MSRC asked
for (custom stores no longer need `IHttpContextAccessor`) but with two
documented-by-implication trade-offs noted in **B-G3** below.

### Remaining gaps for the AG-UI threat scenario

#### B-G1. `MapAGUI` does not auto-wrap the keyed store; safe path requires a non-obvious registration shape

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

#### B-G2. Trust-model docs missing on the three legacy AG-UI surfaces (MSRC Fix #1)

`MapAGUI`, `InMemoryAgentSessionStore`, and `AgentSessionStore` need the
explicit "thread id is a chain-resume identifier, not an authorization
token; multi-user hosts must scope sessions by principal" wording, with
a pointer to `UseClaimsBasedSessionIsolation` /
`IsolationKeyScopedAgentSessionStore`. Today nothing on those surfaces
flags the risk or points readers at the new safe-path APIs.

#### B-G3. Decorator approach mutates `conversationId` seen by inner stores, undocumented

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

#### B-G4. Only one provider implementation ships; `ClaimType` lookup is single-claim only

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

#### B-G5. AG-UI sample is a commented reminder, not a working safe configuration

`samples/05-end-to-end/AGUIClientServer/AGUIServer/Program.cs` adds a
single commented-out line. The sample's runtime behaviour is unchanged;
copy-paste users still land on the unscoped path. At least one AG-UI
sample should compile and run with `UseClaimsBasedSessionIsolation`
plus a working auth scheme so the safe pattern is shown end-to-end. The
sample also needs to demonstrate registering the store through
`WithSessionStore(...)` rather than via raw `AddKeyedSingleton` so that
the decorator chain actually engages — unless **B-G1** is fixed first.

#### B-G6. Asymmetry between A2A and AG-UI auto-wrap behaviour

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

### Summary scorecard (AG-UI threat surface)

| MSRC ask | Status |
|---|---|
| #1 Trust-model XML on `MapAGUI`, `InMemoryAgentSessionStore`, `AgentSessionStore` | ❌ Not addressed |
| #2 Principal-scoping inside the AG-UI handler (versioned opt-in) | ⚠️ Equivalent opt-in mechanism exists (`UseClaimsBasedSessionIsolation` + decorator), but the AG-UI handler does not engage it for stores registered the canonical way |
| #3 Optional principal-aware store overload | ✅ Achieved via decorator (with caveats — see B-G3) |
| AG-UI sample shows safe pattern | ⚠️ Commented reminder only |
| Symmetric behaviour with the A2A hosting layer | ❌ A2A auto-wraps in handler; AG-UI does not |

---

## Part C — Synthesis across the two reports

The A2A and AG-UI reports describe the **same root cause** at the
abstraction layer (`AgentSessionStore` only knows
`(agent, conversationId)`; the wire-supplied id is the entire lookup
key) reached through two different hosting surfaces. Read together they
say:

1. **The contract gap is real, and the PR closes it correctly.** Adding
   a principal dimension by *decoration* (`IsolationKeyScopedAgentSessionStore`)
   rather than by adding a third parameter to every `AgentSessionStore`
   override was the right call: it keeps the contract source-compatible,
   it stacks naturally with future scoping dimensions (tenant, session
   tag), and it lets a single isolation provider cover every hosting
   surface without per-surface plumbing.
2. **"Auto-wrap when the integrator opts in" is the right shape under
   the team's design constraint.** The PR does not change defaults: with
   no `UseClaimsBasedSessionIsolation` registered, both A2A and the
   builder path remain bit-for-bit compatible. The wrapper engages only
   when an isolation provider is in the container, and even then defers
   to `Strict = false` when the provider returns no key — so the
   first-run / single-user / no-auth scenario continues to function.
3. **Coverage is asymmetric across hosting surfaces.** The PR added the
   handler-level auto-wrap to the A2A path (`CreateA2AServer`) and to
   the agent-builder path (`WithSessionStore`), but **not** to the
   AG-UI handler (`MapAGUI`). The result: an integrator who follows
   the canonical AG-UI snippet
   (`AddKeyedSingleton<AgentSessionStore>(name, store)` +
   `endpoints.MapAGUI(name, "/ag-ui")`) plus
   `UseClaimsBasedSessionIsolation(...)` still gets an unscoped store.
   This is the headline residual issue (**B-G1 / B-G6**) and is also
   the reason the AG-UI report exists as a separate finding even after
   the A2A path is fixed.
4. **Documentation and samples lag the runtime fix on both surfaces.**
   `AgentSessionStore`, `InMemoryAgentSessionStore`, the A2A quickstart,
   and the AG-UI quickstart all still describe the persistence contract
   without flagging the trust assumption that `(agent, conversationId)`
   carries no principal dimension and that multi-user hosts must compose
   one. The new types are well-documented, but nothing on the legacy
   IntelliSense path points readers at them. A second-time reader of
   either MSRC report could read the entire surface and miss the safe
   path (**A-G1 / B-G2**).
5. **One shared caveat applies to both surfaces.** Because scoping is
   done by rewriting `conversationId` to `{escapedKey}::{conversationId}`
   before forwarding, any inner store that logs, echoes, audits, or
   constrains the shape of `conversationId` is silently affected. This
   needs to be a documented contract on `IsolationKeyScopedAgentSessionStore`
   (and ideally a one-line "treat `conversationId` as opaque" note on
   `AgentSessionStore` itself). It applies identically to A2A
   (**A-G3**) and AG-UI (**B-G3**).

### Combined scorecard

| MSRC ask (collapsed across both reports) | Status |
|---|---|
| Make principal-scoping *expressible* without rewriting every store | ✅ Decorator (`IsolationKeyScopedAgentSessionStore`) |
| Auto-engage scoping on the **A2A** canonical registration shape when an isolation provider is present | ✅ `CreateA2AServer` wraps |
| Auto-engage scoping on the **AG-UI** canonical registration shape when an isolation provider is present | ❌ `MapAGUI` does not wrap |
| Preserve out-of-box single-user/no-auth behaviour | ✅ `Strict = false` when no provider; `NoopAgentSessionStore` default unchanged |
| Trust-model XML on `AgentSessionStore`, `InMemoryAgentSessionStore`, `MapAGUI`, A2A entry points | ❌ Not addressed |
| Document the `conversationId`-mutation contract the decorator imposes | ❌ Not addressed |
| Ship enough provider variants to be discoverable beyond a single Claims case | ⚠️ Only `ClaimsIdentitySessionIsolationKeyProvider`, single-claim, no `Identity.Name` fallback |
| Working safe-path samples for both A2A and AG-UI | ❌ AG-UI sample is a commented reminder; no A2A sample update |

---

## Part D — Next steps (respecting "out-of-box default must keep working")

All of the following preserve the design constraint: **with no
isolation provider registered, behaviour must not change** — same
default store (`NoopAgentSessionStore`), same wire contract, same
prototype-friendly first-run experience. None of them require an
integrator to register auth or an isolation provider before persistence
works.

Listed in priority order, with the closure mapping back to the gap IDs
above.

1. **Mirror the A2A auto-wrap inside `MapAGUI`.** In the AG-UI endpoint
   extension, after resolving the keyed `AgentSessionStore`, walk the
   `GetService<IsolationKeyScopedAgentSessionStore>()` chain; if it is
   absent, wrap with `Strict = isolationKeyProvider != null`. The
   `Strict = false` branch keeps the "no provider registered → bare
   `conversationId` passes through" behaviour the constraint requires.
   The `Strict = true` branch engages only when the integrator has
   already opted in by calling `UseClaimsBasedSessionIsolation(...)`.
   *Closes B-G1 and B-G6 (asymmetry); produces no out-of-box behaviour
   change.*

2. **Add the trust-model XML paragraph to the five legacy surfaces.**
   `AgentSessionStore`, `InMemoryAgentSessionStore`, `MapAGUI`, the A2A
   `CreateA2AServer` / `AsA2AServer` entry points. The text needs to
   say: (a) `conversationId` / `ThreadId` / `contextId` arrives from
   the wire and is not an authorization token; (b) `(agent, conversationId)`
   has no principal dimension, so persistent stores are single-namespace
   by default; (c) multi-user hosts should compose one via
   `UseClaimsBasedSessionIsolation` or a custom
   `SessionIsolationKeyProvider`. Pure docs change, no behaviour
   impact. *Closes A-G1, B-G2.*

3. **Document the `conversationId`-mutation contract** on
   `IsolationKeyScopedAgentSessionStore` and add a one-liner on
   `AgentSessionStore` saying inner stores must treat `conversationId`
   as opaque (don't parse, don't impose length/charset constraints,
   expect logs/telemetry to surface it verbatim). *Closes A-G3, B-G3.*

4. **Convert the AG-UI sample into a working safe configuration** (and
   add an equivalent slice to one A2A sample). The sample should
   register an auth scheme, call `UseClaimsBasedSessionIsolation`, and
   register the store via the canonical endpoint shape — so once
   step 1 lands, copy-paste users land on the safe path automatically.
   The unsafe path must still be reachable (constraint), but the
   in-tree sample shouldn't model it. *Closes A-G2 follow-up, B-G5.*

5. **Widen the provider story.** Either extend
   `ClaimsIdentitySessionIsolationKeyProvider` to take an ordered
   fallback chain (e.g. `ClaimTypes.NameIdentifier` → `Identity.Name`),
   or ship one or two additional providers (HTTP-header,
   mTLS-subject) so the safe path is discoverable beyond a single
   claims-based deployment. Whichever shape is chosen must continue to
   return `null` for anonymous requests so the `Strict = false`
   pass-through semantics keep holding. *Closes B-G4.*

### What is explicitly **not** proposed

- Flipping the default registered store from `NoopAgentSessionStore` to
  any persistent default — out of scope per the constraint.
- Requiring `UseClaimsBasedSessionIsolation` (or any
  `SessionIsolationKeyProvider`) before persistence works — out of
  scope per the constraint.
- Adding a third `scopeId` parameter to `AgentSessionStore` virtuals
  (would force every existing custom store to be recompiled and
  re-implemented). The decorator approach already covers this case;
  the only ask is a documented contract on inner stores.
- Treating an authenticated request without the configured claim as a
  hard error in the no-isolation-provider scenario — only applies when
  the integrator opted into `Strict = true` by registering a provider.
