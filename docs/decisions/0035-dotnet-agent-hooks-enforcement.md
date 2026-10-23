---
status: proposed
contact: MohammadHaroonAbuomar
date: 2026-08-07
deciders: agent-framework .NET maintainers
---

# .NET agent-hooks enforcement: composed factory over three seams

## Context and Problem Statement

The [AGENT-HOOKS-0.1](https://github.com/responsibleai/agent-hooks) interception contract shipped for Python as a first-class experimental core feature (#7515): a middleware bundle emitting eight interception points with three-verdict, fail-closed enforcement, transform write-back, buffered streaming, and verdict-before-durability persistence gating. The .NET side needs the same semantics, but the .NET framework has no category-based middleware lists — interception is decorator composition (`DelegatingAIAgent`, Microsoft.Extensions.AI `DelegatingChatClient`, the function-invocation middleware seam). How should the contract's indivisibility and enforcement properties be realized in that model?

## Decision Drivers

- Identical enforcement semantics to the merged Python feature (same spec, same fail-closed rules), diverging only where the .NET seam model requires it — never by weakening an enforcement property.
- Partial installation of the enforcement must be impossible or loudly rejected, not silently degraded.
- Denied content must never become durable; transformed content must persist post-transform.
- No changes to existing framework source; the optional native-runtime dependency (`ResponsibleAI.AgentHooks`) must not be referenced by core packages.

## Decision Outcome

**A single factory (`AsAIAgentWithAgentHooks`, per-run and host-owned-session overloads) in a new package `Microsoft.Agents.AI.AgentHooks` composes the full enforcement itself** instead of exposing middleware values:

- **Seam order (fixed by construction):** `AgentHooksAgent` (agent seam: `agent_startup`/`input`/`output`/`agent_shutdown`, per-run `AsyncLocal` state, buffered streaming, persistence gate) → framework function-invocation middleware (`pre_tool_call`/`post_tool_call`) → `ChatClientAgent` with its default pipeline → `AgentHooksChatClient` **below** `FunctionInvokingChatClient` (so `pre_model_call`/`post_model_call` bracket every model service call of the tool loop individually).
- **Indivisibility:** the seam decorators are `internal`; only the factory composes them. Two pipeline-replacement affordances of `ChatClientAgent` are rejected loudly (fail closed): a caller-supplied per-run `ChatClientFactory` (the framework's own function-middleware factory is recognized and allowed — it wraps, not replaces), and a supplied chat client that already contains a `FunctionInvokingChatClient` (it would execute tools below the verdicts).
- **Verdict-before-durability:** end-of-run history and context-provider writes defer behind the `output` verdict via gating provider wrappers installed by the factory (dropped on deny, flushed post-transform with verdicted-message substitution for streamed runs). The implicit default `InMemoryChatHistoryProvider` is materialized and gated, with the history-conflict flags set to mimic implicit-default semantics. Per-service-call persistence sits above the chat seam, so it is covered by its own `post_model_call` verdict. Per-run provider overrides are wrapped in both `AdditionalProperties` dictionaries, copy-on-write. Nested agents persist inline at their own boundaries (they have their own providers) — no run-identity bookkeeping is needed, unlike Python.
- **Fail-closed error behavior:** interceptor crashes/timeouts surface as `host_error:*` denies; enforcement-layer failures at the tool seam halt the run through `FunctionInvocationContext.Terminate` (the loop's only loud escape — thrown exceptions are converted to tool errors by the loop, which would fail open); wire projections run inside the guarded blocks; failure notifications to providers are redacted (empty request messages) once a deny/halt stands.
- **Streaming:** fully buffered per the spec's `buffered_output` semantics — zero egress ahead of a verdict; transformed responses re-derive the released updates (preserving continuation tokens) so egress never diverges from verdicted content.

### Considered Alternatives

- **Port Python's middleware-value model (a `MiddlewareBundle` type):** rejected — .NET has no middleware list to put a bundle into; indivisibility via runtime validation is weaker than construction ownership.
- **Core-framework persistence gate (as Python added in `_sessions.py`):** rejected — unnecessary in .NET; construction ownership of the provider instances gives the same property with zero core changes.
- **Per-run `ChatClientFactory` as the chat-seam install point:** rejected — it wraps the whole pipeline above the function-invocation loop, so per-model-call points would be impossible.

## Consequences

- Good: zero existing-source changes; the optional native dependency is isolated in one leaf package; enforcement properties are structural rather than convention-based.
- Accepted: the package ships in the release solution filter as an **alpha** package (maintainer decision on the PR) — the version suffix follows the maturity of the `ResponsibleAI.AgentHooks` dependency it is built on, and the whole surface stays `[Experimental]`; a sample follows once the API shape settles.
- Known limitations (documented on the factory): hosted (service-executed) tools never reach the function seam and are intercepted via the `post_model_call` content projection; service-managed (conversation-id) history is durable at the service and ungateable; the deferred-OTel decorator sits above the chat seam, so sensitive-data request spans observe pre-transform content; a chat-seam projection failure fails the run closed but without a synthesized `host_error` record (SDK affordance gap, responsibleai/agent-hooks#70).
- The trust model is the spec's: cooperative contract, not a security boundary — the misuse rejections catch accidental foot-guns loudly, not in-process adversaries.

## Update: host declaration loading (2026-10)

The agent-hooks spec added the host declaration document (§7.7, contract `agent-hooks-declaration/1.0`): a JSON file that states the enforcement configuration (mode, composition, identity provider, approval references, timeouts) and the interceptor bindings, resolved by the Rust core against the surface the host code declares. The package now accepts one next to the code path:

- `AgentHooksOptions.FromDeclaration` and its `FromDeclarationPath`, `FromDeclarationJson` and `FromDeclarationNode` variants build options from a document. The host registers its binding kinds and any custom names in the `HostRegistry` the factory hands it. The document is resolved and every kind resolver runs when the options are built, so a refused document never becomes an agent.
- `AgentHooksHostSurface.Surface` states what this package's code emits and honours: all eight points, buffered output, posture `terminate` at the tool seam (the decision above). A document has to state that posture; the contract default (`continue`) is refused as `surface_unsupported`.
- Options built from a declaration are sealed (the setters throw), except `RecordSink`. The per-run factory builds each run's emitter with `InterceptionEmitter.FromDeclaration`, so records carry the `declaration` stamp. The code path and the host-owned-session overload are unchanged; a host that owns its session can already pass an emitter built by the SDK loader.
- Options built from a declaration mirror its mode and composition. The approval resolver, identity provider and the two timeouts are names and values in `ResolvedDeclaration`, which is the source of truth for the declaration path.
- `AgentHooksHostSurface.Surface` claims `int64_json` and `bigint_json`: tool-call arguments arrive as `JsonElement` values and the wire projection keeps their text, so an integer beyond 2^53 or beyond u64 reaches the core as the token the model produced and is refused there (a test pins this).
- Package pin: central package management pins `ResponsibleAI.AgentHooks` at `0.1.0-beta.2`, the first release that ships the loader (see the agent-hooks `DECLARATION-VERSIONS.md`).
