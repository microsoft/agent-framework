---
status: accepted
contact: rogerbarreto
date: 2026-06-29
deciders: rogerbarreto
consulted: []
informed: []
---

# Hosted platform context (user id + call id) for Foundry Hosting on AgentServer 2.0

Supersedes [ADR-0026](0026-hosted-session-identity-context.md).

## Context and Problem Statement

[ADR-0026](0026-hosted-session-identity-context.md) sourced the hosted-agent end-user identity from `ResponseContext.Isolation` (an `IsolationContext` typed `UserIsolationKey` / `ChatIsolationKey`), injected by the platform as the `x-agent-user-isolation-key` and `x-agent-chat-isolation-key` headers.

`Azure.AI.AgentServer.*` 2.0.0 (responses protocol `2.0.0`) removes that surface. `ResponseContext.Isolation` is gone; the platform now exposes `ResponseContext.PlatformContext` (a `PlatformContext` typed `UserIdKey` and `CallId`), populated from the `x-agent-user-id` and `x-agent-foundry-call-id` headers. The chat isolation key no longer exists, and a new per-request **call id** is introduced that first-party Foundry services (the toolbox proxy in particular) require on outbound calls to resolve the server-side-stored caller context. The hosting layer in `Microsoft.Agents.AI.Foundry.Hosting` had to migrate to this contract without changing the public shape that samples and providers depend on.

## Decision Drivers

- Track the breaking `Azure.AI.AgentServer.*` 2.0.0 surface (`PlatformContext` replacing `Isolation`) while keeping the same per-user partitioning guarantees from ADR-0026.
- Keep the change **internal**: existing hosted samples and `AIContextProvider`s must not need code changes. `session.GetHostedContext().UserId`, `HostedSessionIsolationKeyProvider`, and `AddFoundryResponses` stay source-compatible.
- Forward the new per-request call id verbatim on outbound calls to Foundry first-party services so per-user toolbox OAuth consent and other server-side caller-context lookups keep working.
- Remain resilient on protocol `1.0.0`: when only the legacy headers are present, `UserIdKey` still resolves and `CallId` is simply absent.
- Preserve the strict-resume tamper defense from ADR-0026 with identity now reduced to user only.

## Considered Options

For the identity source:

1. **Map `ResponseContext.PlatformContext.UserIdKey`** into the existing `HostedSessionContext` (user only), keeping ADR-0026's storage shape and read accessor.
2. Keep a `ChatId` slot on `HostedSessionContext` for backward source-compatibility, populated from `CallId` or left null.

For the call id propagation:

A. **A request-scoped ambient (`HostedCallContext`, an `AsyncLocal<string?>`)** set by the handler and re-applied before each egress point, read by the outbound delegating handler.
B. Thread the call id through every method signature down to the toolbox bearer handler.

For session keying (previously implied by the conversation/chat pairing):

I. **`HostedConversationKey`** resolving a stable partition from `conversation_id ?? partition(previous_response_id) ?? partition(responseId)`.
II. Continue keying on the container session id (`FOUNDRY_AGENT_SESSION_ID`).

## Decision Outcome

Chosen: **Option 1** for identity, **Option A** for call id, **Option I** for session keying.

Rationale:

- **`ChatId` dropped (Option 2 rejected).** The platform no longer supplies a chat key; carrying a synthetic one would invent identity the trust boundary does not provide. `HostedSessionContext` becomes user-only (`HostedSessionContext(string userId)` / `UserId`), and the strict-resume check validates `UserId` alone. The corresponding `HostedFoundryMemoryProviderScopes` values `PerChat` and `PerUserAndChat` are removed; `PerUser` is retained.
- **Ambient call id (Option B rejected).** Writing `HostedCallContext.CallId` inside the streaming `async IAsyncEnumerable` iterator is reverted across each `yield`, so a single up-front assignment is lost before the toolbox/MCP egress runs. The handler therefore captures `context.PlatformContext?.CallId` once and **re-applies it immediately before each egress point**; `FoundryToolboxBearerTokenHandler` forwards it as `x-agent-foundry-call-id`. The ambient is request-scoped and never leaks into the caller's execution context (guarded by a unit test).
- **`HostedConversationKey` (Option II rejected).** One container serves many conversations for its lifetime, so the container session id cannot key per-conversation state. The partition key is derived from the conversation/`previous_response_id`/minted response id instead.

Implementation summary in `Microsoft.Agents.AI.Foundry.Hosting`:

| Type | Visibility | Change vs ADR-0026 |
|---|---|---|
| `HostedSessionContext` | public sealed | Now user-only (`UserId`); `ChatId` removed. |
| `PlatformHostedSessionIsolationKeyProvider` | internal sealed | Maps `context.PlatformContext.UserIdKey` (was `context.Isolation.UserIsolationKey` / `ChatIsolationKey`). |
| `HostedCallContext` | internal static | New. Request-scoped `AsyncLocal<string?>` holding the `x-agent-foundry-call-id` value. |
| `HostedConversationKey` | internal | New. Resolves the per-conversation partition key. |
| `FoundryToolboxBearerTokenHandler` | internal | Now also forwards `x-agent-foundry-call-id` outbound. |
| `HostedFoundryMemoryProviderScopes` | public | `PerChat` / `PerUserAndChat` removed; `PerUser` kept. |

Package manifests bump the responses container protocol to `2.0.0` (invocations stays `1.0.0`).

## Consequences

Positive:

- Per-user memory partitioning and the strict-resume tamper defense from ADR-0026 are preserved with no public API churn for samples or providers.
- Per-user toolbox OAuth consent and other server-side caller-context lookups keep working because the per-request call id is forwarded on egress.
- Works unchanged on protocol `1.0.0` (no call id) and `2.0.0`.

Negative:

- `HostedSessionContext.ChatId` and the `PerChat` / `PerUserAndChat` memory scopes are removed; any out-of-tree consumer that referenced them must move to user-scoped partitioning.
- The call id must be re-applied before every egress point because of the async-iterator `AsyncLocal` revert; a missed re-apply silently drops the header. This is covered by unit tests.

## Out of scope

- HMAC tamper signatures over the persisted context remain unimplemented; equality comparison against `ResponseContext.PlatformContext` on every request is sufficient because the platform sets the header at the trust boundary.
- The per-request `User` field on `CreateResponse` is still intentionally not consumed.
