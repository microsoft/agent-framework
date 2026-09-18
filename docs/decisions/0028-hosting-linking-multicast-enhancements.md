---
status: proposed
contact: eavanvalkenburg
date: 2026-06-11
deciders: eavanvalkenburg
---

# Hosting linking and multicast enhancements

## Context and Problem Statement

[ADR-0027](0027-hosting-channels.md) defines the minimal v1 hosting core: originating-channel responses, explicit `ChannelSession.isolation_key`, and no host-level identity linking, push, multicast, background delivery, or durable runners.

This ADR tracks the richer cross-channel behaviors that were removed from v1. These enhancements are **follow-up work** and are **not prerequisites** for shipping, using, or stabilizing the v1 host/channel core.

## Decision Drivers

- Cross-channel continuity must not create accidental cross-user, cross-tenant, or cross-channel data leaks.
- Non-originating delivery must be observable, idempotent, retryable, and supportable.
- Protocol payloads must remain channel-native while still being safe to persist and replay.
- App authors need opt-in policy controls, not hidden defaults.
- The enhancement stack should layer on top of the v1 host without reshaping the minimal channel contract.

## Enhancement Areas

The follow-up design should cover these capabilities together because they share identity, storage, delivery, and replay concerns:

- **Cross-channel identity linking** — a user can connect multiple `ChannelIdentity` values to one channel-neutral `isolation_key`.
- **Authorization and allowlist policy** — channels or hosts can require verified identity, allow specific native identities or claims, and deny unknown callers.
- **Non-originating response delivery** — a run can respond somewhere other than the request's originating protocol when explicitly configured.
- **Active-channel routing** — delivery can target the most recently observed linked channel for an `isolation_key`.
- **Multicast / all-linked delivery** — delivery can fan out to every linked channel or a selected set.
- **Background runs and continuation tokens** — long-running requests can return immediately and complete later, with a polling/status fallback.
- **Durable delivery runners** — delivery work can survive process restarts and support dead-letter handling.
- **Retry and replay semantics** — delivery attempts are bounded, deduplicated, and safe to replay.
- **Payload serialization** — channel-specific payloads can be persisted, redacted, versioned, and reconstructed without losing protocol fidelity.

Candidate API names from the broader design (`IdentityLinker`, `IdentityAllowlist`, `AuthPolicy`, `ResponseTarget`, `ChannelPush`, `ChannelPushCodec`, `DurableTaskRunner`, `InProcessTaskRunner`, `RetryPolicy`, `LinkPolicy`) remain design vocabulary for this ADR. They are not approved v1 APIs.

## Considered Options

### Option A — Leave all behavior to applications

Applications implement linking, authorization, push, retry, and serialization independently.

- Good: the hosting core stays very small.
- Neutral: advanced apps can still build what they need.
- Bad: every app must solve the same security and delivery problems, likely inconsistently.

### Option B — Add the full enhancement stack to v1

The first host release includes linking, authorization, active channel, multicast, background runs, durable runners, and codecs.

- Good: the original cross-channel experience is available immediately.
- Neutral: samples can demonstrate rich end-to-end flows.
- Bad: v1 becomes security-sensitive, storage-heavy, and harder to stabilize.

### Option C — Layer opt-in enhancement packages after v1

Ship the minimal host first, then add linking, authorization, and delivery packages behind explicit configuration.

- Good: v1 remains simple while leaving room for a reviewed, supportable enhancement stack.
- Neutral: apps that need advanced delivery wait for follow-up packages.
- Bad: the first release does not satisfy proactive or all-linked scenarios.

### Option D — Build only platform-specific integrations

Implement linking and proactive delivery separately in Telegram, Activity Protocol, Discord, and future channels.

- Good: each package can match its protocol exactly.
- Neutral: some shared abstractions may emerge later.
- Bad: cross-channel behavior becomes fragmented and hard to reason about.

## Decision Outcome

Proposed direction: **Option C — layered opt-in enhancement packages after v1**.

The minimal host remains the foundation. Follow-up packages may add linking, authorization, delivery, and durable execution, but must be explicitly enabled and must pass the validation gates below before becoming part of the public contract.

## Safety Requirements

### Threat model

The design must account for:

- spoofed channel-native identities,
- stolen or replayed link challenges,
- cross-tenant or cross-confidentiality data leakage,
- unsolicited proactive messages,
- malicious payloads persisted for replay,
- denial-of-service through fan-out or retry storms, and
- privacy leakage through logs, metrics, or support tooling.

Required mitigations include verified identity claims where available, signed and expiring link challenges, explicit user consent, per-channel capability checks, default-deny policy options, tenant partitioning, and uninformative denial messages on shared channels.

### Idempotency and replay

Exactly-once delivery is not a realistic guarantee. The design must provide:

- stable run, continuation, and delivery-attempt identifiers,
- channel-level idempotency keys where protocols support them,
- bounded retry with jitter and explicit terminal states,
- replay windows and expiration,
- duplicate suppression for persisted attempts, and
- clear semantics for "delivered", "accepted by platform", and "observed by user".

### Storage

Enhancement storage must stay distinct from v1 `AgentSession` history and workflow checkpoints unless an implementation deliberately backs them with the same physical store.

Stored data should be schema-versioned, minimized, encrypted or otherwise protected as appropriate, and partitioned by tenant/project. Link records, continuation records, active-channel state, delivery attempts, dead letters, and serialized payloads need independent TTL and deletion policies.

### Observability and support

The design must include structured logs, traces, and metrics for link attempts, authorization decisions, delivery scheduling, retries, replay, and dead-letter outcomes. Logs must avoid message content and sensitive identity claims by default. Operators need a way to inspect, revoke, replay, or purge stuck records safely.

## Validation Gates

Before these enhancements are accepted:

- A reviewed threat model covers identity linking, authorization, non-originating delivery, multicast, and replay.
- Cross-channel linking tests prove a verified identity can link two channels and that unlink/deny paths do not leak information.
- Authorization tests cover native-id allowlists, verified-claim allowlists, default-deny behavior, and misconfiguration failures.
- Delivery tests cover originating-only, specific-channel, active-channel, selected-channel, and all-linked routing.
- Background/continuation tests cover polling fallback, cancellation or expiration, process restart, retry, and dead-letter behavior.
- Codec tests prove payloads are versioned, redacted where needed, backward compatible, and rejected safely when unknown.
- Multicast tests prove fan-out is bounded, independently retried, and idempotent per destination.
- Observability tests or manual validation prove support operators can correlate a request to delivery attempts without exposing sensitive content.

## Relationship to ADR-0027

ADR-0027 remains valid without any of these enhancements. This ADR extends the hosting model only after the safety, storage, and support requirements above are satisfied.
