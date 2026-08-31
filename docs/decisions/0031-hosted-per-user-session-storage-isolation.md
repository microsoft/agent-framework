---
status: accepted
contact: rogerbarreto
date: 2026-06-30
deciders: rogerbarreto
consulted: []
informed: []
---

# Per-agent and per-user session-storage isolation for Foundry Hosting

Builds on [ADR-0030](0030-hosted-platform-context-agentserver-2.0.md).

## Context and Problem Statement

A Foundry hosted container can serve many end users (and, in .NET, many agents) over its lifetime. The
`AgentSessionStore` persists each turn's `AgentSession` (which for a workflow agent carries the workflow
checkpoint, and which also carries the tool-approval mapping via `ToolApprovalIdMap` in the session state
bag). [ADR-0030](0030-hosted-platform-context-agentserver-2.0.md) protected cross-user access only through
the strict-resume identity check (a 403 when the persisted `HostedSessionContext.UserId` does not match the
live request). The persisted artifacts themselves were keyed by `conversationId` (+ agent name), not
physically partitioned per user, so a forged `conversation_id` would still resolve to another user's file
path before the identity check rejected it.

The Python hosting package added physical per-user partitioning (`<root>/<user_id>/<context_id>`) plus a
reject-style path-traversal guard. We want .NET to provide the same defense-in-depth, adapted to the .NET
hosting model.

## Decision Drivers

- Defense in depth: a forged/guessed id must not even resolve to another tenant's storage path, independent
  of the identity check.
- Multi-agent hosting: a single .NET container hosts multiple agents resolved from keyed DI, so the layout
  must isolate per agent as well as per user (Python hosts a single agent and needs no agent layer).
- Path-traversal safety (CWE-22) for the untrusted, platform-injected user id.
- Back-compat for local development (no `x-agent-user-id` header) and for direct/non-hosted store use.
- Keep the change contained and avoid the async-iterator `AsyncLocal` revert hazard from ADR-0030.

## Considered Options

- **Path partition inside `FileSystemAgentSessionStore`**, threading the user id explicitly through the
  `AgentSessionStore` API, with self-describing prefixed segments.
- A delegating store that prefixes the conversation id with the user id (the
  `IsolationKeyScopedAgentSessionStore` pattern from `Microsoft.Agents.AI.Hosting`). Rejected: still needs the
  user id on the read path and yields a flat key rather than nested per-tenant directories.
- An `AsyncLocal<string?>` user-context set by the handler. Rejected: the session is saved in the handler's
  `finally` after the streaming `yield`s, where an `AsyncLocal` set up front is reverted (the same hazard
  that forced explicit call-id re-application in ADR-0030). Explicit threading is safer and clearer.
- A separate per-user approval store (as in Python). Rejected as unnecessary: see below.

## Decision Outcome

Path layout with self-describing, prefixed segments; user id threaded explicitly:

    {root}/ a-{agentName} / u-{userId} / c-{contextId}.json

- `a-` (agent), `u-` (user), `c-` (context) are constant literals applied to the sanitized/validated value,
  so a collapsed layout is never ambiguous and a user id can never masquerade as an agent name.
- `contextId` is `HostedConversationKey.Resolve` (conversation_id, else the partition of
  previous_response_id, else of the minted response id).
- The agent and context layers are always present (Foundry always deploys a named agent). The only
  collapse is the `u-` layer: present when a user id is resolved (Foundry header, or local dev fallback),
  absent for raw local runs with no header (`{root}/a-{agent}/c-{conv}.json`). There is no user-only or
  no-agent layout.

Other elements:

- `string? userId` was added as a **required** parameter (no default) on `AgentSessionStore.GetSessionAsync` /
  `SaveSessionAsync` (a contained, breaking change to the experimental Foundry abstraction; both in-tree
  implementations and the two handler call sites were updated). It is required rather than optional so a
  caller can never silently persist a session unscoped; a genuine no-user caller (local without the header,
  or a non-hosted direct caller) passes `null` explicitly. `AgentFrameworkResponseHandler` resolves the user
  id before loading the session.
- Path-traversal guard: the user id is rejected (not sanitized) when it is not a single safe path segment
  (path separators, NUL, drive letters, rooted paths, all-dot segments). After building the path, the
  fully-resolved path is asserted to remain under the storage root.
- The strict-resume 403 identity check from ADR-0030 is **kept** as the second defense layer (it still
  catches a session that reaches the wrong partition, e.g. via a non-partitioning custom store or in-process
  tampering).
- **No separate approval store.** The tool-approval mapping lives in `ToolApprovalIdMap` ->
  `AgentSessionStateBag`, which is serialized into the session checkpoint, so partitioning the session path
  isolates pending approvals per tenant automatically. (Python needs a separate per-user approval store only
  because it models approvals as a standalone store.)

## Consequences

Positive:

- Cross-tenant isolation is now defense-in-depth: physical per-agent/per-user partitioning plus the identity
  check. Approvals and workflow checkpoints inherit the partitioning because they ride in the session.
- Self-describing prefixes make the on-disk layout auditable and collision-free across collapse cases.

Negative:

- Breaking change to the experimental Foundry `AgentSessionStore` API (added `userId`).
- The on-disk layout and leaf filename change (`<conv>.json` -> `c-<conv>.json`), orphaning sessions written
  by the ADR-0030 release. Acceptable for an experimental package; a fresh session is created on next use.

## Out of scope

- Encryption at rest and quota enforcement remain platform concerns.
- Non-Foundry hosting layers can adopt an equivalent scheme independently.

## Update (2026-07-01): local runs no longer fail closed; sample dev provider removed

Superseding the ADR-0026/0030 behavior where a `null` result from `HostedSessionIsolationKeyProvider`
always became a 500, `AgentFrameworkResponseHandler` now branches on `FoundryEnvironment.IsHosted`:

- **Hosted** (`IsHosted == true`, production): a `null` identity is still a hard error (500). Isolation
  stays strict; the platform always injects `x-agent-user-id`.
- **Not hosted** (local `docker run` / `dotnet run`): a `null` identity is tolerated. Per-user isolation
  is simply not triggered — the handler passes `userId == null` to the store (the documented "no user
  partition", `{root}/a-{agent}/c-{conv}.json`), stamps no `HostedSessionContext`, and runs no
  strict-resume check. Contributors can run a hosted image locally with zero extra setup.

Consequently the sample-side `DevTemporaryLocalUserIdProvider` and `AddDevTemporaryLocalContributorSetup`
were removed. To simulate distinct users locally, send an `x-agent-user-id` request header; the default
`PlatformHostedSessionIsolationKeyProvider` reads it via `ResponseContext.PlatformContext.UserIdKey`
(the SDK's `PlatformContext.FromRequest` populates it from the header unconditionally, hosted or not).
