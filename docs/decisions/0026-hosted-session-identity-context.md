---
status: accepted
contact: rogerbarreto
date: 2026-05-07
deciders: rogerbarreto
consulted: []
informed: []
---

# Hosted session identity context for Foundry Hosting

## Context and Problem Statement

Server-hosted Foundry agents need a way to scope per-user state (most notably `FoundryMemoryProvider` memories) by the end user that initiated the request. The Foundry platform already injects `x-agent-user-isolation-key` and `x-agent-chat-isolation-key` headers on every Responses request, but the agent-framework hosting layer did not surface those values to `AIContextProvider` instances. The provider's `stateInitializer` only received an `AgentSession?` with no identity attached, so per-user scoping was impossible without out-of-band plumbing.

## Decision Drivers

- Memory and any future user-private context must be partitioned per end user without per-sample boilerplate.
- The identity must be **read-only** from the perspective of `AIContextProvider`s, so a buggy or hostile provider cannot escalate or leak across users.
- The persisted session must validate against the live request on every resume to defend against session-id leak and in-process tampering.
- The change must work for every existing hosted-agent type (`ChatClientAgent`, `FoundryAgent`, future ones) without per-type refactoring of cast-heavy code paths in `Microsoft.Agents.AI`.
- Local Docker debugging must remain possible when the platform headers are absent.

## Considered Options

1. **`HostedSessionContext` stored in `AgentSessionStateBag`, exposed via a public read accessor and an `internal` setter.** Hosting writes once on session creation and validates on every resume.
2. **Specialised `HostedAgentSession : AgentSession` wrapper** that carries `UserId`/`ChatId` properties, with `GetService<ChatClientAgentSession>()` as the unwrap escape hatch.
3. **New property on `AgentSession` base class** (`HostedSessionContext? HostedContext { get; internal set; }`).
4. **AsyncLocal middleware** that reads the headers and stuffs them into a per-request `AsyncLocal<HostedSessionContext>` consumed by the provider.

For the source of identity:
- A. The platform-injected `IsolationContext` exposed by `ResponseContext.Isolation` (typed `UserIsolationKey`/`ChatIsolationKey`).
- B. The OpenAI Responses spec's top-level `request.User` field.
- C. A custom HTTP header `x-client-user`.

## Decision Outcome

**Option 1** was chosen for the storage shape, sourced from **Option A** (`ResponseContext.Isolation`).

Rationale:

- **Wrapper rejected (Option 2).** `ChatClientAgentSession` is `sealed` and `ChatClientAgent` rejects any other session type via direct `is not ChatClientAgentSession` checks at multiple call sites. Wrapping would force non-trivial refactors across `Microsoft.Agents.AI` and a corresponding repeat for every other agent type.
- **Base-class property rejected (Option 3).** Leaks "hosted" semantics into the universal `AgentSession` abstraction used by Durable, A2A, and CopilotStudio agents that have no notion of a hosted user.
- **AsyncLocal rejected (Option 4).** Surfaces the concept only locally, requires every consumer to re-implement the bridge, and cannot be enforced as read-only.
- **`request.User` rejected (Option B).** Set by the caller, not the platform. Forging it client-side trivially defeats per-user partitioning.
- **`x-client-user` rejected (Option C).** Non-standard, requires custom HTTP plumbing, and duplicates the platform-provided isolation contract.

Implementation summary in `Microsoft.Agents.AI.Foundry.Hosting`:

| Type | Visibility | Purpose |
|---|---|---|
| `HostedSessionContext` | public sealed | Captures `UserId` and `ChatId` (both required, non-whitespace). |
| `HostedSessionContextExtensions.GetHostedContext` | public | Read accessor for `AIContextProvider`s. |
| `HostedSessionContextExtensions.SetHostedContext` | internal | Writer reserved for the hosting assembly. Backed by `AgentSessionStateBag` under a well-known key for serialisation. |
| `HostedSessionIsolationKeyProvider` (abstract) | public | DI-resolvable factory. Async signature: `ValueTask<HostedSessionContext?> GetKeysAsync(ResponseContext, CreateResponse, CancellationToken)`. |
| `PlatformHostedSessionIsolationKeyProvider` | internal sealed | Default implementation. Maps `context.Isolation.UserIsolationKey` and `context.Isolation.ChatIsolationKey`. Returns `null` when either is absent. |

Behaviour added to `AgentFrameworkResponseHandler.CreateAsync`:

1. Resolve `HostedSessionIsolationKeyProvider` from DI; fall back to `PlatformHostedSessionIsolationKeyProvider`.
2. Call `GetKeysAsync(context, request, cancellationToken)`. A `null` result throws `InvalidOperationException` (becomes 500). A null/whitespace `UserId` or `ChatId` is rejected by `HostedSessionContext`'s constructor.
3. Branch on the **session's existing context**, not on whether a `conversation_id` was supplied:
   - **No session (`session is null`):** nothing to stamp; skip.
   - **Session present but un-stamped (`GetHostedContext() is null`):** treat as fresh. This covers both newly-created sessions and pre-existing sessions whose `conversation_id` was provisioned externally (e.g. via `conversations.CreateProjectConversationAsync()`) before the first hosted-agent request. Stamp the resolved identity now.
   - **Session present with stamped context:** strict resume. The persisted `UserId` and `ChatId` must equal the resolved values exactly. Mismatch throws `ResponsesApiException` with status 403 and body `Hosted session identity context mismatch`.

## Consequences

Positive:

- Per-user memory partitioning works out of the box for any agent that consumes a `Microsoft.Agents.AI.Foundry.FoundryMemoryProvider` configured to read `session.GetHostedContext().UserId`.
- Cross-user session-id leak and in-process tampering of the persisted identity both surface as a 403 with a deliberately uninformative body.
- The identity is opaque to the framework, matching the platform's semantics. The framework never inspects user identity; the `IsolationContext` keys are pre-partitioned per agent.

Negative:

- Every existing hosted sample fails locally without a `HostedSessionIsolationKeyProvider` registered, because the platform headers are absent outside the platform. Mitigated by shipping `Hosted_Shared_Contributor_Setup` with `DevTemporaryLocalSessionIsolationKeyProvider` and `AddDevTemporaryLocalContributorSetup`, and migrating all 9 existing responses samples.
- An attacker who can plant an un-stamped session under a victim's `conversation_id` *before* the victim's first hosted-agent request would be stamped with the attacker's identity on that first request. This is not a regression vs. behaviour without this contract, and is mitigated in practice because the `conversation_id` namespace is allocated by the platform per project. Once a session is stamped, the strict equality check fully defends the resume path.

## Out of scope

- Per-request `User` field on `CreateResponse` is intentionally not consumed; only the platform `IsolationContext` headers carry trustworthy identity.
- Generic (non-Foundry) hosting layers can re-define an equivalent type if needed; nothing in this ADR is moved into `Microsoft.Agents.AI.Hosting` because `Microsoft.Agents.AI.Foundry.Hosting` does not depend on it.
- HMAC tamper signatures over the persisted context are not implemented; comparison against `ResponseContext.Isolation` on every request is sufficient because the platform sets those headers at the trust boundary.
