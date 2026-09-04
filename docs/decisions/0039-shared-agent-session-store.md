---
status: proposed
contact: rogerbarreto
date: 2026-09-01
deciders: rogerbarreto
consulted: []
informed: []
---

# Shared AgentSessionStore abstraction

## Context and Problem Statement

.NET has two public `AgentSessionStore` abstract classes. `Microsoft.Agents.AI.Hosting` defines a store
whose lookup creates a session when no value exists. `Microsoft.Agents.AI.Foundry.Hosting` defines a store
whose lookup returns `null`, accepts an explicit user partition, and provides a separate convenience method
that creates a session when needed. The types cannot be used interchangeably, so storage integrations depend
on a specific hosting protocol package instead of the core agent abstractions.

## Decision Drivers

- One storage contract must work across all hosting packages.
- Storage implementations must depend only on `Microsoft.Agents.AI.Abstractions`.
- A lookup must distinguish a missing value from a stored value without creating state as a side effect.
- The contract must support any number of isolation dimensions without privileging user identity.
- Existing Foundry storage behavior and per-user isolation must remain unchanged.

## Considered Options

1. Promote the Foundry Hosting contract to `Microsoft.Agents.AI.Abstractions`.
2. Promote the conventional Hosting contract and adapt Foundry Hosting to it.
3. Add a third contract and keep adapters for both existing contracts.
4. Represent session identity as an immutable key with arbitrary named partitions.

## Decision Outcome

Chosen option: **Promote the Foundry Hosting contract to `Microsoft.Agents.AI.Abstractions`**.

`AgentSessionStore` moves to the `Microsoft.Agents.AI` namespace and keeps the Foundry Hosting behavior:

- The abstraction and every public implementation start as experimental under diagnostic `MAAI001`.
- `GetSessionAsync` returns `AgentSession?` and returns `null` when no session is stored.
- `GetOrCreateSessionAsync` performs the explicit lookup or creation operation.
- `SaveSessionAsync` and both lookup methods receive an `AgentSessionStoreKey`.
- `AgentSessionStoreKey.SessionId` identifies the logical session.
- `AgentSessionStoreKey.Partitions` holds zero or more named isolation dimensions. Every partition is
  part of identity and implementations cannot ignore unknown partitions.
- Partition order does not affect identity. Physical encoding remains the responsibility of each store.
- `DeleteSessionAsync` and service inspection are not part of the shared contract.

The duplicate types in `Microsoft.Agents.AI.Hosting` and `Microsoft.Agents.AI.Foundry.Hosting` are removed.
Both packages reference the shared type directly.

`DelegatingAgentSessionStore` lives in the `Microsoft.Agents.AI` package beside `ChatClientAgent`, providing
the common decorator base without requiring a hosting-protocol package.

The conventional Hosting implementations adopt the same behavior. `IsolationKeyScopedAgentSessionStore`
adds the value from `AgentIsolationKeyProvider` under the `isolation` partition while preserving existing
partitions. Protocol-specific hosting can add named partitions such as `user`, `tenant`, or `chat` before
loading the session. `AIHostAgent` uses `GetOrCreateSessionAsync` when it needs a ready session.

Azure Blob Storage, filesystem storage, and Foundry State Store each encode the session id and every
partition into their own collision-safe physical key. Version 1 Azure
Blob keys are not read because the package is still preview and the previous format cannot distinguish
all partition combinations safely.

Provider-specific metadata does not belong in `AgentSessionStoreKey`. For example, Foundry item tags can
be exposed by an overload or options type on `FoundryAgentSessionStore` without adding tags to Abstractions.

## Consequences

Positive:

- Storage implementations can be shared by Foundry Hosting, conventional Hosting, and future protocols.
- Missing session handling is explicit and consistent.
- Isolation dimensions are explicit, composable, and independent from any hosting protocol.
- `Microsoft.Agents.AI.Abstractions` owns the contract alongside `AIAgent` and `AgentSession`.

Negative:

- This is a source-breaking change for implementations of the preview Hosting contract.
- Callers must construct an `AgentSessionStoreKey`; unpartitioned sessions use only `SessionId`.
- Consumers that need deletion must use a storage-specific API until a separate shared deletion capability is defined.

## More Information

- [ADR-0031](0031-hosted-per-user-session-storage-isolation.md) records the earlier Foundry-specific user partition.
- [ADR-0032](0032-dotnet-hosting-protocol-helpers.md) records the previous conventional Hosting contract.
