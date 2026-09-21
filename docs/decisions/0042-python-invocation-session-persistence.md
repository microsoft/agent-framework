---
status: proposed
contact: jpalvarezl
date: 2026-09-21
deciders: jpalvarezl
---

# Persist Python invocation sessions through the existing session-store abstraction

## Context and Problem Statement

`InvocationsHostServer` keeps conversation sessions in a host-owned dictionary for the
process lifetime. Request-scoped agent factories do not change that ownership: even after
an agent is disposed, the host still owns the session. We need to release completed
request state without losing multi-turn conversation continuity.

## Decision Drivers

- Restore conversation state rather than silently evicting live sessions.
- Preserve hosted user/session partition boundaries and request-scoped agent ownership.
- Reuse existing storage and serialization contracts instead of adding another cache policy.
- Keep streaming, failure, and cancellation cleanup inside the session's coordination scope.
- Make persistence and retention behavior explicit to applications.

## Considered Options

- **Cap the in-memory dictionary and refuse new conversations.** Bounds retained entry
  count, but needs a new capacity policy and eventually refuses new work until an
  application deletes state. It does not bound the size of each session.
- **Evict idle sessions.** Releases memory but loses conversation state unless backed by
  persistent storage. Adds a separate host retention policy and active-session tracking.
- **Use the existing session-store provider.** Releases host-owned session objects while
  preserving restorable state. Adds storage I/O and requires serializable state, but
  reuses the established hosting extension point and backend retention policy.

## Decision Outcome

Choose the existing session-store provider. `InvocationsHostServer` accepts
`agent_session_store_provider`, defaulting to `AgentSessionStoreProvider`, like Python
`ResponsesHostServer`. The default is Foundry storage when hosted and the SDK's file-backed
store locally. New default stores inherit the existing SDK retention policy: 30 days
since the last write. Existing stores and custom providers retain their own policies.
Absent or expired state starts a new conversation; there is no permanent tombstone registry.

### Alignment with .NET

This follows **.NET Foundry Responses hosting's persistence architecture**, not a purported
.NET Invocations cache limit:

- [`AddFoundryResponses`](../../dotnet/src/Microsoft.Agents.AI.Foundry.Hosting/ServiceCollectionExtensions.cs)
  defaults to `FoundryAgentSessionStore`.
- [`.NET FoundryAgentSessionStore`](../../dotnet/src/Microsoft.Agents.AI.Foundry.Hosting/FoundryAgentSessionStore.cs)
  serializes sessions into the AgentServer state store, with a local fallback and the
  platform's 30-day default item retention.
- The .NET in-memory session store remains a development/testing alternative; it does not
  supply an eviction policy. The Invocations echo sample is stateless.

Python reuses its own existing `StoreProvider[SessionStore]` contract. This is architectural
alignment, not shared storage-key formats, cross-language state compatibility, or identical
concurrency implementations.

### Lifecycle and limitations

Invocation storage keys hash an unambiguous partition encoding and use a versioned,
protocol-specific namespace; runtime `AgentSession.session_id` values remain unchanged.
Same-partition requests serialize within one host. Reference-counted lock entries exist
only for active/waiting requests and are removed after the final request leaves.

The coordination scope includes stream closure, factory-agent cleanup, and session saving.
The host attempts to save state on success, execution failure, and interruption, without
retrying agent execution. Disconnect cleanup is shielded from the ASGI cancellation scope.
Persistence errors are reported; there is no success-shaped in-memory fallback.
After streaming headers have been sent, a persistence failure terminates the stream and is
logged; already delivered text cannot be retracted.

Starlette uses AnyIO cancellation scopes even when running on asyncio. `asyncio.shield()`
protects the child operation but still allows the awaiting request to unwind on cancellation.
Using `CancelScope(shield=True)` instead keeps cleanup awaited inside the request's ownership
scope before releasing session coordination. This does not replace the asyncio event loop.
AnyIO is already a transitive dependency and is declared directly because hosting imports it.

This removes cumulative host retention of completed session objects. It does not bound
individual session size, active request count, backend storage, or total process memory.
The SDK local backend reads its entire logical-store file per operation. The store API
does not provide distributed transactions, so concurrent updates across hosts still
require application-level coordination. Durable serialization also replaces Python
object-identity reuse with restored state, and custom state needs registered codecs.

### Migration and provider configuration

Existing process-local invocation sessions are not migrated across deployment; the previous
implementation also lost them on restart. Local sessions now survive host recreation and are
written under `AGENTSERVER_STATE_ROOT` or the SDK's default state directory. Independent
applications should use separate storage roots or providers.

State must support `AgentSession.to_dict()` / `AgentSession.from_dict()`. Custom state types
need registered codecs rather than arbitrary live Python objects. Restored sessions preserve
state, not Python object identity.

A custom provider's `get_store` receives host configuration and request platform context.
The provider owns retention and deletion; an explicitly selected in-memory store remains
volatile and does not gain automatic eviction. For new default stores, writes renew the
30-day expiry window and reads do not. Missing, deleted, or expired state starts fresh on
the next invocation, including when its caller reuses the same session ID.
