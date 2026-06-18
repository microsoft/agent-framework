---
status: accepted
contact: eavanvalkenburg
date: 2026-06-11
deciders: eavanvalkenburg
---

# Python minimal hosting core and pluggable channels

## Context and Problem Statement

Agent Framework has several protocol-specific hosting surfaces. App authors who want one agent or workflow on multiple protocols must compose servers, routes, middleware, session handling, and lifecycle code by hand.

We will introduce a small Python hosting core that owns the common server shape and leaves protocol details inside channel packages. The first public contract must be intentionally narrow so Python can ship a base contract before adding identity linking, proactive delivery, or multicast behavior. Other language implementations may reuse the same conceptual boundary, but this ADR records the Python decision.

## Decision Drivers

- Keep the first host easy to explain: one app, one hostable target, one or more channels.
- Reuse Agent Framework's existing agent, workflow, session, history, and checkpoint primitives.
- Let channel packages own protocol parsing, protocol responses, authentication details, and native command surfaces.
- Make session continuity explicit through a channel-supplied `ChannelSession(isolation_key=...)`.
- Avoid approving cross-channel identity and delivery semantics before their safety model is reviewed.

## Considered Options

1. Keep only protocol-specific hosts.
2. Ship a large hosting core with identity linking, authorization, background delivery, active-channel routing, and multicast in v1.
3. Ship a minimal host/channel core now and track linking/multicast as follow-up work.

### Keep only protocol-specific hosts

- Good: no new abstraction or package surface.
- Neutral: each protocol can continue evolving independently.
- Bad: every multi-channel app still has to compose servers, lifecycle, and session handling by hand.

### Ship the large cross-channel host in v1

- Good: the richest cross-channel scenarios are available immediately.
- Neutral: the host becomes the natural place to demonstrate identity and delivery policy.
- Bad: v1 becomes a security-sensitive identity and delivery system before the safety model is reviewed.

### Ship the minimal core now

- Good: the host/channel boundary can be implemented, tested, and explained without solving linking and durable delivery at the same time.
- Neutral: apps that need richer behavior must build it locally or wait for ADR-0028 follow-up work.
- Bad: proactive delivery and multicast scenarios are deliberately absent from v1.

## Decision Outcome

Chosen option: **minimal host/channel core now, follow-up enhancements later**.

`AgentFrameworkHost` owns:

- one application object,
- one hostable target (`SupportsAgentRun` agent-compatible object or a `Workflow`), and
- one or more channels.

Channels own:

- contributed routes, middleware, commands, and lifecycle callbacks,
- protocol-native request parsing into `ChannelRequest`,
- protocol-native rendering of the originating response, and
- any channel-specific authentication or signature validation.

The host owns:

- route/lifecycle aggregation,
- invocation of the target,
- `ChannelSession(isolation_key=...)` to `AgentSession` resolution and caching,
- `reset_session(isolation_key=...)`,
- host-level middleware, including Foundry isolation middleware only when the Foundry hosting environment flag is present,
- invocation of per-channel hooks (`ChannelRunHook`, `ChannelResponseHook`, `ChannelStreamUpdateHook`), and
- workflow checkpoint wiring through an explicit `checkpoint_location`.

`ChannelIdentity`, when present, is request metadata only. In v1 it is not a linking, authorization, or delivery key.

### Trust boundary for `isolation_key`

The host treats `ChannelSession.isolation_key` as a session partition key, not as proof of identity. Channels or host middleware must authenticate and authorize any externally supplied value before passing it to the host. For example, a Responses caller must not be allowed to choose an arbitrary `previous_response_id` or header-derived key unless the platform or middleware has already established that the caller owns that conversation. The host deliberately does not infer that trust from the string itself.

### Hook ownership

Channels provide hook configuration and protocol-native context. The host invokes those hooks as part of the common invocation pipeline:

- `ChannelRunHook` runs after channel parsing and before target invocation.
- `ChannelResponseHook` runs after target invocation and before the originating channel serializes its response.
- `ChannelStreamUpdateHook` is applied by the host while the channel consumes streamed updates because streaming serialization is protocol-specific.

`ChannelStreamUpdateHook` is an update hook, not a final-response sanitizer. Channels that use it for redaction or filtering must also apply equivalent policy to any final response they render. Channels choose whether the response is streaming before run hooks execute.

This keeps hook call conventions centralized while leaving protocol payload parsing and response formatting in channel packages.

### State owned by v1

`state_dir` is limited to host-owned local files for reset-session aliases and workflow checkpoint path derivation. It does not store linked identities, active-channel state, response-routing state, continuation records, durable runner queues, or delivery attempts. Those storage concerns belong to ADR-0028.

## Non-goals for v1

The following are deliberately **not** part of the v1 contract:

- cross-channel identity linking (`IdentityLinker`, `local_identity_link`, or `agent-framework-hosting-entra`),
- identity allowlists or authorization policy (`IdentityAllowlist`, `AuthPolicy`),
- response routing beyond the originating channel (`ResponseTarget`, active channel, specific linked channel, `all_linked`),
- push or payload codecs (`ChannelPush`, `ChannelPushCodec`),
- background/continuation delivery,
- durable task runners (`DurableTaskRunner`, `InProcessTaskRunner`),
- retry/replay policy (`RetryPolicy`),
- fan-out, multicast, or all-linked delivery,
- confidentiality tiers and `LinkPolicy`, and
- a host-level multi-agent router.

These areas are follow-up enhancements covered by [ADR-0028](0028-hosting-linking-multicast-enhancements.md). They are not prerequisites for shipping or using the v1 host.

## Consequences

Positive:

- The host/channel model can be implemented and tested without designing a security-sensitive identity graph.
- Existing and new channel packages can share one Starlette app, middleware stack, lifecycle, and target invocation path.
- Session continuity is explicit and debuggable: two channels share history only when they produce the same `isolation_key`.
- Hook invocation is centralized in the host, so channels do not each invent the call convention.

Negative:

- Apps that need OAuth linking, allowlists, proactive messages, or multicast must continue to implement those behaviors outside the v1 host.
- Some richer cross-channel scenarios from the original design move to a separate decision and validation cycle.
- The host must document `isolation_key` trust clearly because it now provides the shared session boundary.

## Validation Gates

Before this ADR is accepted:

- A sample can expose one target on multiple channels with one `AgentFrameworkHost` and no handwritten Starlette route composition.
- Built-in channel tests prove that routes, commands, startup, and shutdown callbacks are contributed by channels and aggregated by the host.
- Session tests prove that identical `ChannelSession.isolation_key` values resolve to the same cached `AgentSession`, and `reset_session` rotates that mapping.
- Channel tests prove that each channel renders only its own originating response; there is no host-level push, multicast, or active-channel delivery path.
- Workflow tests or samples use an explicit `checkpoint_location`.
- Foundry isolation middleware is documented and covered by integration or contract tests, including the non-Foundry case where raw isolation headers are ignored.
- The v1 API and packages do not expose the removed symbols or packages listed in [Non-goals for v1](#non-goals-for-v1).
- The Python spec is updated to match this simplified contract and uses "public", "stable", or "released" terminology for Agent Framework APIs.

## More Information

- Follow-up linking and multicast ADR: [ADR-0028](0028-hosting-linking-multicast-enhancements.md)
