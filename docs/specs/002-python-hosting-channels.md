---
status: proposed
contact: eavanvalkenburg
date: 2026-04-24
deciders: eavanvalkenburg
---

# Python hosting core and pluggable channels

## What are the business goals for this feature?

Give Python app authors one low-level, Starlette-based hosting surface that can expose a single **hostable target** — either a `SupportsAgentRun`-compatible agent **or** a `Workflow` — on one or more channels (Responses API, Invocations API, Telegram, future WhatsApp/Teams, etc.) without requiring them to hand-build protocol routing or server glue per protocol, **and** let an end user start a conversation on one channel (e.g. Telegram on their phone) and seamlessly continue it on another (e.g. Teams at their desk) against the same target and the same conversation history.

This consolidates the protocol-specific hosting layers that exist today (`agent-framework-foundry-hosting`, `agent-framework-ag-ui`, `agent-framework-a2a`, `agent-framework-devui`) into a shared composable model where:

- a host owns the ASGI app and channels own protocol shape,
- session identity is **channel-neutral** — the host resolves a session from a channel-supplied `isolation_key` (e.g. a stable user identity) so two channels mounted on the same host can resolve to the **same** `AgentSession` for the same end user, and a future pluggable session store extends that continuity across hosts and processes, and
- channel-native identity is **mapped, not assumed** — the host owns a first-class `IdentityResolver` seam (channel-native id → `isolation_key`) and an `IdentityLinker` seam (well-known connect ceremony — OAuth, MFA, signed one-time code — to associate a new channel-native id with an existing `isolation_key`), so cross-channel continuity does not depend on each channel's user namespace happening to align, and
- response delivery is **decoupled from request origin** — every `ChannelRequest` carries a `ResponseTarget` (`originating` (default), `active` for the user's most recently used channel, a specific channel id, all linked channels, or `none` for background-only). Background/asynchronous runs are first-class via a `RunHandle` returned by `host.run_in_background(...)` so a user can submit a long-running request on one channel and receive the result on another (or poll by run id), and
- channels can be assigned different **confidentiality tiers** so two channels on one host can share an agent without sharing a session — e.g. Teams (corporate, allowed to access internal resources) and Telegram (public) can run against the same target while remaining session-isolated, with a host-level `LinkPolicy` that decides which confidentiality tiers may be linked (and includes an explicit "deny all" variant for hosts that want no cross-channel continuity at all). Running two separate hosts is always a valid alternative; the per-tier policy exists for cases where one shared host with two policy-isolated tiers is preferred.

We know we're successful when:

- after the agent is created, a basic multi-channel sample requires only one `AgentFrameworkHost`, channel objects, and one `host.serve(...)` call — no handwritten protocol routes, no per-protocol server bootstrap, and no `agentserver` dependency for new channel packages,
- a single `AgentFrameworkHost` configured with two channels (e.g. Telegram + a future Teams channel) can be exercised by one end user across both channels and observe one continuous conversation,
- an end user known on one channel can run a host-provided `link`/`connect` command on a second channel, complete an OAuth (or MFA, or one-time-code) ceremony, and see subsequent messages on the second channel resolved against the same `AgentSession` as the first, **and**
- a user can submit a long-running request on Telegram with `response_target="active"`, switch to Teams, and receive the result there as a proactive message — with a poll route as a fallback for callers that prefer polling.

## Problem Statement

### How do developers solve this problem today?

Today, every protocol surface is its own package with its own server. A developer who wants to expose one agent over both the Responses API and a webhook channel has to stand up two separate hosts and stitch them into one ASGI app by hand:

```python
# Today: developer composes two protocol-specific hosts manually
import os
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework.foundry_hosting import (
    ResponsesHostServer,
    InvocationsHostServer,
)

agent = Agent(
    name="WeatherAgent",
    instructions="You are a helpful weather agent.",
    client=OpenAIChatClient(model="gpt-4.1-mini"),
)

# Two separate, protocol-specific host wrappers, each with their own
# request/session/event mapping inside.
responses_host = ResponsesHostServer(agent=agent)
invocations_host = InvocationsHostServer(agent=agent)

# Manually mount each into a Starlette app so they share a process.
app = Starlette(routes=[
    Mount("/responses", app=responses_host.app),
    Mount("/invocations", app=invocations_host.app),
])

# Bring up the server by hand.
if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)
```

Adding a Telegram bot to the same agent today means leaving this stack entirely: spinning up a separate process, installing a Telegram SDK, writing the polling/webhook loop, manually translating updates into agent calls, and wiring command handlers (`/start`, `/new`, `/cancel`, ...) and `set_my_commands(...)` registration by hand — none of which is reusable across other message channels.

### Why does this problem require a new hosting abstraction?

The gap is between **owning a hostable target** (a `SupportsAgentRun` agent or a `Workflow`) and **operationalizing it on multiple channels**. Agent Framework already provides agents, workflows, sessions, run inputs, response/update streaming, the `SupportsAgentRun` execution seam, and the `Workflow` execution seam. What's missing is a generic host that:

1. Owns one Starlette app and one set of lifecycle hooks.
2. Lets channels contribute routes, middleware, commands, and startup/shutdown without protocol leakage into the host.
3. Standardizes how protocol requests become agent invocations (input, options, session, streaming) and how agent results flow back out.
4. **Resolves a session from a channel-neutral `isolation_key`** so two channels mounted on the same host can converge on the same `AgentSession` for the same end user — enabling cross-channel chat continuity (start on Telegram, continue on Teams) without per-channel session bookkeeping.
5. Provides a first-class extension seam for webhook/message channels with native command catalogs (per PR #5393 Telegram sample).

The current `agentserver`-based hosts are valuable prior art but sit too high in the stack — they encode protocol ownership at the host level. A generic core can learn from their behavior without depending on `agentserver`.

## Non-Goals / Relationship to existing hosting packages

The hosting core is deliberately **not** a replacement for the existing protocol packages in their first form, and it is not a multi-agent router. Hosting core, `ag-ui`, `a2a`, `devui`, and `foundry-hosting` solve adjacent but distinct problems:

| Dimension | Existing protocol packages | `agent-framework-hosting` |
|---|---|---|
| **Mental model** | One package = one protocol surface, owns its own server | One host owns ASGI app; channels plug protocols in |
| **Scope** | Protocol-specific request/session/event mapping | Generic host + channel contract; protocol logic lives in channel packages |
| **Composition** | One protocol per process or per Mount | Many channels per host, shared middleware, lifecycle, session resolution |
| **Multi-agent** | Out of scope per package | **No.** One host = one agent. Future work. |

**Explicit non-goals:**
- Migrating `ag-ui`, `a2a`, or `devui` onto the new core in the first implementation.
- Standardizing a persistent session storage contract across all channels.
- Hosting multiple agents behind one router in this first design.
- Designing every detail of WhatsApp, Teams, or Bot Framework payloads now (only Telegram is concretely targeted, informed by PR #5393).
- Replacing protocol-specific serializers with one generic event model.
- Taking a runtime or package dependency on `agentserver` in the new hosting core or its new channel packages.

**Boundary rule:** If you need protocol-specific event semantics, codecs, or signature validation, that lives in the channel package. The host owns ASGI, lifecycle, session resolution, and the call into the target's execution seam (`SupportsAgentRun.run(...)` for agents, the workflow execution seam for workflows).

## Requirements

After we deliver `agent-framework-hosting` and its first channel packages, users will be able to:

1. **Compose one host with one or more channels** — instantiate `AgentFrameworkHost(target=..., channels=[...])` where `target` is either a `SupportsAgentRun`-compatible agent or a `Workflow`, and get one Starlette application with all channels mounted.
2. **Expose the Responses API** — add `ResponsesChannel()` and serve `/responses/v1` (and conversation routes) without writing protocol handlers.
3. **Expose the Invocations API** — add `InvocationsChannel()` and serve `/invocations/invoke` without writing protocol handlers.
4. **Expose a Telegram bot** — add `TelegramChannel(bot_token=...)` with either `polling` or `webhook` transport, and register native commands declaratively with `ChannelCommand`.
5. **Override mount roots without breaking protocol paths** — pass `path="/public/responses"` and the channel still owns the protocol-relative suffix (`/v1`, `/invoke`, `/webhook`).
6. **Customize per-request invocation behavior** — pass a `run_hook` to any built-in channel. The hook receives the channel-produced `ChannelRequest` (the host-neutral envelope each channel builds from its own protocol parsing — see [Key Types](#key-types)) and returns a possibly-modified `ChannelRequest`. Use it to validate, rewrite, or strip channel-derived options (e.g. enforce or drop `temperature`, override `session_mode`) before the host calls the target's execution seam. It is also the **adapter** that reshapes the channel's default `ChannelRequest.input` into the typed inputs a workflow target requires.
7. **Control session use per request** — built-in channels set `ChannelRequest.session_mode` to `auto`, `required`, or `disabled`; the host honors that when resolving `AgentSession`.
8. **Partition sessions by isolation key** — channels populate `ChannelSession.isolation_key` (user, tenant, chat, …) using hosted-agent terminology.
9. **Resolve to the same session across channels on one host** — two channels mounted on the same `AgentFrameworkHost` that produce the same `isolation_key` (e.g. a stable user identity mapped from each channel's native identifier) resolve to the same `AgentSession`, so an end user starting a chat on Telegram can continue it on Teams against the same conversation history without per-channel session bookkeeping.
10. **Map channel-native identity into `isolation_key`** — every channel has its own user namespace (Telegram `chat_id`, Teams AAD object id, WhatsApp phone, Slack user id). The host accepts a host-level `identity_resolver` callable that maps a `ChannelIdentity(channel_id, native_id, attributes)` into an `isolation_key` (or `None` if unknown). Channels publish the native identity they observed; the resolver decides whether it maps to an existing user.
11. **Link a new channel to an existing identity through a well-known ceremony** — the host accepts a host-level `identity_linker` (e.g. `OAuthIdentityLinker(...)`, `OneTimeCodeIdentityLinker(...)`, `MfaIdentityLinker(...)`) which contributes its own routes/lifecycle and exposes a `begin(channel_identity) -> LinkChallenge` / `complete(challenge_id, proof) -> isolation_key` flow. Channels surface a `link`/`connect` `ChannelCommand` that delegates to the linker; on success the resolver subsequently maps the new channel-native identity to the existing `isolation_key`. Mechanism (OAuth provider, MFA factor, signed one-time code) is pluggable; the contract is fixed.
12. **Route the response to a chosen channel** — `ChannelRequest.response_target` accepts `ResponseTarget.originating` (default — synchronous response on the originating channel), `ResponseTarget.active` (the channel most recently observed for the resolved `isolation_key`), `ResponseTarget.channel("teams")` (specific channel id), `ResponseTarget.channels([...])` (a list), `ResponseTarget.all_linked` (every channel where this `isolation_key` is known), or `ResponseTarget.none` (background-only — caller must poll the `RunHandle`). When the target is not the originating channel, the host delivers via the destination channel's `ChannelPush` capability.
13. **Push proactively from a channel** — channels that can deliver outbound messages without a prior request (Telegram bot proactive message, Teams proactive bot message, webhook callbacks, SSE broadcasts) implement an optional `ChannelPush` capability on top of the base `Channel` protocol. Channels without push can only be the `originating` target.
14. **Submit background runs as a first-class operation** — `host.run_in_background(request) -> RunHandle` returns immediately with a stable run id and status (`queued` | `running` | `completed` | `failed`). The host invokes the target asynchronously and, when complete, both delivers the result via the configured `ResponseTarget` push **and** records it against the run id so callers can poll `host.get_run(run_id)`. Built-in channels expose poll routes (`/responses/v1/{run_id}`, `/invocations/{run_id}`) that surface this without app code.
15. **Track the active channel per `isolation_key`** — the host records `(isolation_key, last_seen_channel, last_seen_at)` on every successfully resolved request so `ResponseTarget.active` resolves correctly. Apps can override in the `run_hook` (e.g. force `active` to a specific channel for a particular request).
16. **Add Starlette middleware at the host level** — pass `middleware=[Middleware(CORSMiddleware, ...)]` to `AgentFrameworkHost`.
17. **Serve with one call** — call `host.serve(host="localhost", port=8000)` without manually importing `uvicorn`, while `host.app` remains the canonical ASGI surface for any other server (Hypercorn, Daphne, Granian, Gunicorn+uvicorn workers).
18. **Author new channels** — implement the `Channel` protocol, return a `ChannelContribution` with routes/middleware/commands/lifecycle hooks, and call `context.run(...)` or `context.stream(...)` to invoke the agent.
19. **Target any `SupportsAgentRun` or `Workflow`** — host an `Agent`, `A2AAgent`, or a `Workflow`; the `run_hook` is the seam for adapting the channel's default `ChannelRequest` into the target-specific input shape (free-form messages for agents, typed inputs for workflows).
20. **Contribute WebSocket endpoints from a channel** — `ChannelContribution.routes` accepts both `Route` (HTTP) and `WebSocketRoute` (WS); the channel codec is responsible for framing and the same `run_hook` / default mapping pipeline applies. Built-in `ResponsesChannel` exposes a WebSocket transport (default `/responses/ws`, controlled by `transports=("http", "websocket")`) alongside its HTTP+SSE transport, anticipating the OpenAI Responses WebSocket transport. The host requires an ASGI server with WebSocket scope support (Uvicorn, Hypercorn, Daphne, Granian).
21. **Mix channels of different confidentiality tiers on one host** — every `Channel` may declare an opaque `confidentiality_tier: str | None` (e.g. `"corp"`, `"public"`). The host's `LinkPolicy` decides which `(source_tier, target_tier)` pairs may share an `isolation_key` (link) and which may be `ResponseTarget` source/destination for one another (deliver). Built-in policies (`AllowAllLinks` (default), `SameConfidentialityTierOnly`, `ExplicitAllowList`, `DenyAllLinks`) and the policy contract are defined in [LinkPolicy](#linkpolicy-and-confidentiality_tier). Cross-tier link attempts are refused with a typed error; cross-tier deliveries are dropped — so two tiers can share **an agent target** on one host while remaining strictly session-isolated.

### v1 Fast Follow
22. **Generic auth helpers** — shared middleware for common channel auth patterns (HMAC signature, bearer token).
23. **Pluggable session and run-handle store** — interface for cross-channel, cross-host session persistence; same store persists `RunHandle`s and identity-link grants beyond process lifetime. Extends cross-channel chat continuity (req #9) and background runs (req #14) beyond a single host/process.
24. **First-party identity linker helpers** — concrete `OAuthIdentityLinker` (with provider presets), `OneTimeCodeIdentityLinker` (cross-channel code exchange), and an `MfaIdentityLinker` shipped as opt-in helpers on top of the `IdentityLinker` contract.

### Stretch
25. **WhatsApp and Teams channel packages** — using the same `Channel` + `ChannelCommand` model, designed so they participate in cross-channel continuity (req #9) and can serve as `ChannelPush` destinations (req #13) when paired with a stable per-user `isolation_key`.

## API Surface

### Packages

| Distribution package | Public import surface | Purpose |
| --- | --- | --- |
| `agent-framework-hosting` | `agent_framework.hosting` | Core Starlette host, channel contract, session/request bridge |
| `agent-framework-hosting-responses` | `agent_framework.hosting` (lazy) | `ResponsesChannel` |
| `agent-framework-hosting-invocations` | `agent_framework.hosting` (lazy) | `InvocationsChannel` |
| `agent-framework-hosting-telegram` | `agent_framework.hosting` (lazy) | `TelegramChannel` and Telegram-specific helpers |

The split is between distribution packages. The **public import path stays stable at `agent_framework.hosting`** via lazy imports, consistent with the repository's packaging conventions.

### Built-in routes

For built-in channels, `path` is the configurable mount root, not the full final endpoint. The channel package owns the fixed protocol-relative suffix.

| Channel | Default `path` | Default exposed route(s) |
| --- | --- | --- |
| `ResponsesChannel` | `/responses` | `/responses/v1` and nested responses/conversation routes below it |
| `InvocationsChannel` | `/invocations` | `/invocations/invoke` |
| `TelegramChannel` | `/telegram` | webhook mode: `/telegram/webhook`; polling mode: no required HTTP route |

Overrides only replace the outer mount root:

```python
ResponsesChannel(path="/public/responses")        # -> /public/responses/v1
InvocationsChannel(path="/internal/invocations")  # -> /internal/invocations/invoke
TelegramChannel(path="/bots/telegram", bot_token=token)  # -> /bots/telegram/webhook
```

### Key Types

**`AgentFrameworkHost`** — owner of the Starlette app and channel lifecycle. Fronts one **hostable target** (an agent or a workflow).

| Field / Method | Type | Description |
|---|---|---|
| `__init__(target, *, channels, middleware=(), identity_resolver=None, identity_linker=None, debug=False)` | constructor | Composes one host from one **hostable target** (`SupportsAgentRun` or `Workflow`) and a sequence of channels. Optional `identity_resolver` and `identity_linker` provide channel-native-id → `isolation_key` mapping and a connect ceremony for linking new channels to existing identities. The host detects the target kind and dispatches to the appropriate runner. |
| `app` | `Starlette` | Canonical ASGI surface; can be handed to any ASGI server. |
| `serve(*, host="127.0.0.1", port=8000, **kwargs)` | method | Convenience wrapper around `uvicorn.run(self.app, ...)`. Lazy-imports `uvicorn`. |
| `run_in_background(request)` | `-> RunHandle` | Submits a `ChannelRequest` for asynchronous execution. Returns a `RunHandle` immediately; the result is delivered via the configured `ResponseTarget` push when ready and recorded against the run id for polling. Channels typically call this when their protocol response should be a 202 / acknowledgement rather than the agent reply. |
| `get_run(run_id)` | `-> RunHandle` | Look up a previously submitted background run by id. |

**`HostableTarget`** — the union of executable targets the host can front.

| Variant | Type | Execution seam |
|---|---|---|
| Agent | `SupportsAgentRun` | `target.run(input, *, session=..., stream=...)` |
| Workflow | `Workflow` | `target.run(input, ...)` (workflow execution seam) |

**`Channel`** (Protocol) — anything that contributes routes/commands/lifecycle to a host.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Channel name used for routing, telemetry, and `ChannelRequest.channel`. |
| `confidentiality_tier` | `str?` | Optional opaque confidentiality tier (e.g. `"corp"`, `"public"`). Consumed by the host's `LinkPolicy` to decide which channels may be linked into the same `isolation_key` and which may be `ResponseTarget` destinations for a given originating request. `None` = single-tier (no policy filtering). See `LinkPolicy`. |
| `contribute(context: ChannelContext) -> ChannelContribution` | method | Called once at host construction; returns routes/middleware/commands/lifecycle. |

**`ChannelContext`** — host-owned bridge channels use to invoke the agent.

| Method | Type | Description |
|---|---|---|
| `run(request: ChannelRequest)` | `-> HostedRunResult` | One-shot invocation. |
| `stream(request: ChannelRequest)` | `-> HostedStreamResult` | Streaming invocation. |

**`ChannelContribution`** — what a channel returns from `contribute(...)`.

| Field | Type | Description |
|---|---|---|
| `routes` | `Sequence[BaseRoute]` | Starlette routes mounted under the channel's `path`. Accepts both `Route` (HTTP) and `WebSocketRoute` (WS) — both are `BaseRoute`. |
| `middleware` | `Sequence[Middleware]` | Channel-scoped middleware. |
| `commands` | `Sequence[ChannelCommand]` | Native command catalog (e.g. Telegram bot commands). |
| `on_startup` | `Sequence[Callable]` | Lifecycle hooks for polling workers, command registration, etc. |
| `on_shutdown` | `Sequence[Callable]` | Lifecycle hooks for cleanup. |

**`ChannelRequest`** — normalized ingress passed to the host.

| Field | Type | Description |
|---|---|---|
| `channel` | `str` | Originating channel name. |
| `operation` | `str` | e.g. `message.create`, `command.invoke`, `approval.respond`. |
| `input` | `AgentRunInputs` | Reuses framework input types. |
| `session` | `ChannelSession?` | Session hint from the channel. |
| `options` | `ChatOptions?` | Caller-derived options (e.g. Responses `temperature`). |
| `session_mode` | `Literal["auto", "required", "disabled"]` | Whether host-managed session use is automatic, mandatory, or bypassed. |
| `metadata` | `Mapping[str, Any]` | Protocol-level metadata for telemetry. |
| `attributes` | `Mapping[str, Any]` | Channel-specific structured values (signature state, capability hints). Host code never reads this map; reserved for channel-private bookkeeping. |
| `client_state` | `Mapping[str, Any] \| None` | Bidirectional, mutable per-request state object supplied by event-rich front-ends (e.g. AG-UI). Channel-defined shape; the host treats it as opaque. Channels typically thread this into a channel-owned `ContextProvider` (see [Channel-owned per-thread state](#channel-owned-per-thread-state)) and read it back after the run to emit state-snapshot/delta events. |
| `client_tools` | `Sequence[ToolDescriptor] \| None` | Frontend tool catalog supplied per request. The channel forwards definitions onto the agent's `ChatOptions` so the LLM can call them, but tool *execution* returns to the originating client (the host does not invoke them). Run hooks may filter or rewrite the catalog. |
| `forwarded_props` | `Mapping[str, Any] \| None` | Pass-through bag for channel-protocol extras the run hook needs to route into the target — e.g. AG-UI `resume` / `command` / HITL response payloads that drive workflow `RequestInfo` / `RequestResponse` round-trips. Opaque to the host; the run hook decides where it lands on the rebuilt `ChannelRequest.input`. |
| `identity` | `ChannelIdentity?` | Channel-native identity observed on this request — `(channel, native_id, attributes)`. Channels populate it from the inbound payload (Telegram `chat.id`, Teams `from.aadObjectId`, Responses `safety_identifier`, …). The host records `(isolation_key, channel) → identity` on every successful resolve so `ResponseTarget.active`, `.channel(name)`, `.channels([...])`, and `.all_linked` can find a destination native id without per-request payload bookkeeping. |
| `stream` | `bool` | Whether to invoke `stream(...)` rather than `run(...)`. |
| `response_target` | `ResponseTarget` | Where the response is delivered (default: `ResponseTarget.originating`). See `ResponseTarget` below. |
| `background` | `bool` | If `True`, host returns a `RunHandle` immediately rather than awaiting the response. Forced `True` when `response_target == ResponseTarget.none`. |

**`ChannelSession`** — small, host-neutral session hint.

| Field | Type | Description |
|---|---|---|
| `key` | `str?` | Stable host lookup key for an `AgentSession`. **Caller-supplied** channels populate it from the wire payload (e.g. `previous_response_id`, request-body `session_id`). **Host-tracked** channels leave it `None` and let the host's per-`isolation_key` alias decide which `AgentSession` to resolve (see [Channel session-carriage models](#channel-session-carriage-models)). |
| `conversation_id` | `str?` | Protocol-visible conversation/thread identifier when one exists. |
| `isolation_key` | `str?` | Opaque isolation boundary (user, tenant, chat, …) using hosted-agent terminology. |
| `attributes` | `Mapping[str, Any]` | Channel-specific session hints. |

**`ChannelRunHook`** — per-request escape hatch for built-in channels.

```python
ChannelRunHook = Callable[..., Awaitable[ChannelRequest] | ChannelRequest]
```

Channels invoke the hook positionally with the channel-built `ChannelRequest` and pass named extras as keyword arguments. The minimum signature an app author needs is:

```python
def my_hook(request: ChannelRequest, **kwargs) -> ChannelRequest: ...
```

Hooks that want the named extras pull them out by name:

| Keyword | Type | Description |
|---|---|---|
| `target` | `SupportsAgentRun \| Workflow` | The hosted target (so hooks can adapt to e.g. `A2AAgent` or to a `Workflow`'s typed inputs). |
| `protocol_request` | `Any?` | Original channel-native protocol payload — Responses JSON body, Telegram `Update` dict, Teams `Activity` dict, Invocations body, … (loosely typed in v1). |

Runs **after** the channel has produced its default `ChannelRequest`, **before** the host resolves session behavior and calls the target's execution seam. This is the canonical adapter point for workflow targets, where the channel's free-form input must be reshaped into the workflow's typed inputs.

> Earlier drafts wrapped these arguments into a `ChannelRunHookContext` object. The signature was simplified so the typical hook only needs `(request, **kwargs)` — making it safe against future named extras and easier to write inline.

**`ChannelIdentity`** — the channel-native identity the host sees on each request, used as the resolver/linker input.

| Field | Type | Description |
|---|---|---|
| `channel` | `str` | Originating channel name (matches `Channel.name`). |
| `native_id` | `str` | Channel-native identifier (Telegram `chat_id`, Teams AAD object id, WhatsApp phone number, Slack user id, …). Always per-channel; never assumed to align across channels. |
| `attributes` | `Mapping[str, Any]` | Optional per-channel context (display name, locale, group/private chat flag) the resolver/linker may key on. |

**`IdentityResolver`** — host-level seam that maps a `ChannelIdentity` to an `isolation_key`.

```python
IdentityResolver = Callable[[ChannelIdentity], Awaitable[str | None] | (str | None)]
```

The **default resolver auto-issues** an `isolation_key` the first time a `(channel, native_id)` is seen and persists the mapping in the host's identity store, so every end user automatically gets a stable per-user `isolation_key` on first contact through **any** channel — no per-channel boilerplate is required for the single-channel case. Returning `None` is reserved for advanced cases where the resolver wants to refuse unknown identities (e.g. allow-list enforcement).

Cross-channel continuity is then a one-shot **merge** operation: after a successful link ceremony (Scenario 7), the host atomically rewrites the second channel's auto-issued key to point at the first channel's existing `isolation_key`. Apps never have to write per-channel mapping hooks just to get continuity to work.

Apps that already own an identity namespace (corporate user id, tenant-scoped account id) can supply a custom resolver that returns those values directly — bypassing auto-issuance.

**`IdentityLinker`** (Protocol) — host-level seam that runs a connect ceremony to associate a new `ChannelIdentity` with an existing `isolation_key`. The linker is a peer of `Channel` for routing purposes and contributes its own routes/lifecycle.

| Field / Method | Type | Description |
|---|---|---|
| `name` | `str` | Linker name; used for telemetry and to namespace its routes. |
| `contribute(context: ChannelContext) -> ChannelContribution` | method | Same shape as `Channel.contribute(...)`; lets the linker publish callback/verification routes (e.g. `/identity/oauth/callback`, `/identity/verify`) and lifecycle hooks. |
| `begin(identity: ChannelIdentity, *, requested_isolation_key=None) -> LinkChallenge` | method | Starts the ceremony for a channel-native identity. Returns a `LinkChallenge` describing what the user must do (URL to visit, code to enter, MFA prompt). |
| `complete(challenge_id: str, proof: Mapping[str, Any]) -> str` | method | Verifies the proof and returns the resolved `isolation_key`. On success the host atomically records both `(channel, native_id) → isolation_key` and any verified IdP claim recovered from the proof (e.g. `(microsoft.oid, <oid>)`) so subsequent channels that supply the same claim auto-link without a second ceremony. |
| `is_linked(identity: ChannelIdentity, *, verified_claims: Mapping[str, str] = {}) -> str \| None` | method | Returns the `isolation_key` for an already-linked identity, or `None` if no link exists. Channels with `require_link=True` call this on every inbound request before invoking the agent. When `verified_claims` are supplied (e.g. Teams' AAD `oid` from the inbound activity bearer) and a match exists in the link store, the linker silently auto-merges the new `(channel, native_id)` onto the existing `isolation_key` and returns it — this is the "sign in once, every other channel just works" mechanism. |

| Built-in helper | Mechanism | Notes |
|---|---|---|
| `OAuthIdentityLinker(provider, ...)` | OAuth authorization-code redirect | Contributes `/identity/oauth/{provider}/start` + `/callback`; ships with provider presets (Microsoft, Google, GitHub) as opt-in helpers. Stores the verified IdP `sub` / `oid` as a verified claim alongside the channel-native identity so channels that authenticate with the same IdP (e.g. Teams via Entra ID) auto-link on first contact. |
| `OneTimeCodeIdentityLinker(...)` | Signed short-lived code | User runs `/link` on channel A, receives a code; runs `/link <code>` on channel B; host verifies and merges. |
| `MfaIdentityLinker(factor, ...)` | Identity-provider MFA challenge | For environments where a corporate IdP already owns identity assurance. |

A built-in `link` (or `connect`) `ChannelCommand` is exposed automatically when an `IdentityLinker` is configured. Its `handle` invokes `linker.begin(...)` and replies with the `LinkChallenge` payload (URL, code, instructions) projected through the channel's native rendering. Channels may opt out (`expose_in_ui=False`) or override the command's name per channel.

**`require_link` (per-channel)** — every channel that emits a `ChannelIdentity` accepts a `require_link: bool = False` constructor argument. When `True`, the channel calls `linker.is_linked(identity, verified_claims=…)` before producing a `ChannelRequest`; un-linked identities are short-circuited to a rendered `LinkChallenge` reply (the same payload the `link` command would emit) and the agent is **not** invoked for that turn. Combined with the linker's verified-claim auto-link, this gives an "authenticate before chatting" enforcement model where the first channel forces the OAuth ceremony and subsequent channels join the same `isolation_key` silently. See [Scenario 7](#scenario-7-linking-a-new-channel-to-an-existing-identity-via-oauth) for the end-to-end flow. Default is `False`, which preserves the opportunistic flow (auto-issued `isolation_key`, link manually later). Channels whose protocol does not authenticate the user (e.g. anonymous Responses calls) ignore the flag.

#### `LinkPolicy` and `confidentiality_tier`

**`LinkPolicy`** — host-level decision over which channels may share an `isolation_key` and which channels may be a `ResponseTarget` for one another. Consumed by both the `IdentityLinker` (to refuse incompatible link attempts) and the host's response-routing layer (to filter `all_linked` / `active` / specific destinations).

```python
LinkPolicy = Callable[[LinkPolicyContext], bool]
```

`LinkPolicyContext` carries the originating `Channel` (and its `confidentiality_tier`), the prospective destination `Channel` (and its `confidentiality_tier`), and the operation kind (`"link"` or `"deliver"`). Returns `True` to allow, `False` to refuse. Refusal during `link` raises a typed error to the user; refusal during `deliver` excludes that destination from the route set (and falls back to `originating` if the route set becomes empty).

| Built-in policy | Behavior |
|---|---|
| `AllowAllLinks()` | Default. Any pair allowed; preserves today's single-tier behavior. |
| `SameConfidentialityTierOnly()` | Only allows pairs whose `confidentiality_tier` matches (including both `None`). Most common multi-tier setup. |
| `ExplicitAllowList(allowed_pairs={("public", "corp"), ...})` | Allows only the listed `(source, target)` pairs. Useful for one-directional escalation flows. |
| `DenyAllLinks()` | Refuses every link attempt and excludes every non-`originating` destination — channels share an agent target on the host but never share sessions. Equivalent to running each channel on its own host minus the deployment overhead. |

Confidentiality tiers are **opaque labels** — the host does not interpret them; the policy decides what they mean. Setting `confidentiality_tier=None` on every channel preserves single-tier behavior. Two separate hosts is always a valid alternative to using `LinkPolicy`; the policy exists for cases where shared deployment, shared middleware, or a shared target object are preferred over running multiple hosts.

**`ResponseTarget`** — directs **where** the host delivers the agent response. Independent of `session_mode`.

| Variant | Constructor | Behavior |
|---|---|---|
| Originating | `ResponseTarget.originating` (default) | Synchronous response on the originating channel. |
| Active | `ResponseTarget.active` | Delivered to the channel most recently observed for the resolved `isolation_key`. |
| Specific | `ResponseTarget.channel("teams")` | Delivered to the named channel via its `ChannelPush`. |
| Multiple | `ResponseTarget.channels(["telegram", "teams"])` | Delivered to each named channel. |
| All linked | `ResponseTarget.all_linked` | Delivered to every channel where the resolved `isolation_key` is known. |
| None | `ResponseTarget.none` | Background-only — caller must poll the `RunHandle`. Forces `background=True`. |

When `response_target` is anything other than `originating`, the originating channel's protocol response is the **`RunHandle`** (e.g. an Invocations 202 with the run id), and the actual agent response is delivered out-of-band via the destination channel(s)' `ChannelPush`. If the destination channel doesn't implement `ChannelPush`, the host falls back per the configured policy (default: deliver to `originating`; surfaces a warning in telemetry). The configured `LinkPolicy` is consulted for every destination — destinations that fail the policy (e.g. a corp-tier channel addressed from a public-tier originating request) are dropped, and if every destination is dropped the host falls back to `originating`.

**`ChannelPush`** (Protocol) — optional capability for channels that can deliver outbound messages without a prior request.

| Method | Type | Description |
|---|---|---|
| `push(identity: ChannelIdentity, payload: HostedRunResult)` | async | Proactively delivers a completed run result to the given channel-native identity (Telegram proactive message, Teams proactive bot message, webhook callback, SSE broadcast). Channels implement this in addition to `Channel`; channels that cannot push omit it. |

**`RunHandle`** — first-class artifact for asynchronous / background runs.

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Stable run id (URL-safe). |
| `status` | `Literal["queued", "running", "completed", "failed"]` | Current status. |
| `isolation_key` | `str?` | The resolved isolation key the run is associated with. |
| `created_at` | `datetime` | Submission time. |
| `completed_at` | `datetime?` | Set when status is `completed` or `failed`. |
| `result` | `HostedRunResult?` | Populated on `completed`. |
| `error` | `str?` | Populated on `failed`. |
| `response_target` | `ResponseTarget` | The configured delivery target (recorded for diagnostics). |

The host stores `RunHandle`s; v1 uses an in-memory store, v1 fast follow (req #23) makes it pluggable. Built-in channels expose poll routes that surface the handle in their native shape (`/responses/v1/{run_id}` returns a Responses-shaped object; `/invocations/{run_id}` returns the Invocations status envelope).

**`ChannelCommand` / `ChannelCommandContext` / `CommandHandler`** — cross-channel native command model (per PR #5393).

| Type | Fields | Description |
|---|---|---|
| `ChannelCommand` | `name`, `description`, `handle`, `expose_in_ui=True`, `metadata={}` | Transport-neutral command descriptor. |
| `ChannelCommandContext` | `session`, `state`, `raw_event`, `reply(...)`, `run(request)` | Runtime context for command handlers. |
| `CommandHandler` | `Callable[[ChannelCommandContext], Awaitable[None] \| None]` | Command implementation; may reply locally, mutate state, or invoke the agent. |

**`HostedRunResult` / `HostedStreamResult`** — outbound results from the host.

| Type | Fields | Description |
|---|---|---|
| `HostedRunResult` | `response: AgentResponse`, `session: AgentSession?`, `text` | One-shot outcome. |
| `HostedStreamResult` | `updates: ResponseStream[...]`, `raw_events: AsyncIterable[Any] \| None`, `session: AgentSession?` | Streaming outcome. `updates` is the **normalized** stream of `AgentRunResponseUpdate` (lossless for messages, function calls, usage) and is the happy path for Responses, Invocations, Telegram, and most channels. `raw_events` is an optional **passthrough seam** onto the underlying agent event stream (before update normalization) for channels whose protocol carries domain events the framework does not model — e.g. AG-UI's `StateSnapshotEvent` / `StateDeltaEvent` / `ToolCallStartEvent`. Channels that consume `raw_events` bear responsibility for the full event translation; the request still flows through `context.stream(...)` so session resolution, identity, push, and policy continue to apply. `None` when the host has no raw upstream (e.g. a workflow-only target produced from cached events). |

The host does **not** emit protocol events directly — channels translate `HostedRunResult`/`HostedStreamResult` into Responses events, Invocations SSE, webhook callbacks, or platform messages.

### Built-in channel constructors

```python
class ResponsesChannel(Channel):
    def __init__(
        self,
        *,
        path: str = "/responses",
        run_hook: ChannelRunHook | None = None,
        expose_conversations: bool = True,
        transports: Sequence[Literal["http", "websocket"]] = ("http",),
        websocket_path: str = "/ws",
        options: object | None = None,
    ) -> None: ...

class InvocationsChannel(Channel):
    def __init__(
        self,
        *,
        path: str = "/invocations",
        run_hook: ChannelRunHook | None = None,
        openapi_spec: dict[str, Any] | None = None,
    ) -> None: ...

class TelegramChannel(Channel):
    def __init__(
        self,
        *,
        bot_token: str,
        transport: Literal["webhook", "polling"] = "webhook",
        path: str = "/telegram",
        run_hook: ChannelRunHook | None = None,
        commands: Sequence[ChannelCommand] = (),
        register_native_commands: bool = True,
        require_link: bool = False,
    ) -> None: ...
```

`options` on `ResponsesChannel` is intentionally loosely typed in this draft because the option-mapping boundary is still settling. If it becomes a formal type later, it should be Agent Framework-owned, not imported from `agentserver`.

#### Conversation history for the Responses channel

The Responses channel does **not** introduce its own history seam. Conversation history for every channel — Responses, Invocations, Telegram, Teams — flows through the agent's standard core `HistoryProvider` (`agent_framework._sessions.HistoryProvider`). The Responses channel is a *caller-supplied session* channel (see [Channel session-carriage models](#channel-session-carriage-models)): it parses `previous_response_id` (and/or `conversation_id`) off the inbound request and projects it into `ChannelSession.key`. The host then resolves an `AgentSession` for that key and the agent's `HistoryProvider` does the load / append exactly as it would for any other session.

```text
POST /responses { "previous_response_id": "resp_018f…", "input": [...] }
    -> ResponsesChannel parses previous_response_id
    -> ChannelRequest.session = ChannelSession(key="resp_018f…")
    -> host resolves AgentSession(id="resp_018f…")
    -> agent.HistoryProvider.load_messages(session=…)  # if load_messages=True
    -> agent.run(input, session=…)
    -> agent.HistoryProvider.save_messages(session=…, new_messages)
    -> ResponsesChannel serializes the result with response_id="resp_018f…+1"
```

This means **any** AF `HistoryProvider` backs Responses out of the box — `FileHistoryProvider`, an in-memory provider, a future `CosmosHistoryProvider`, etc. The wire `previous_response_id` is just a session id with channel-defined formatting; nothing in the provider has to know "this is a Responses session".

##### `FoundryHistoryProvider` — Foundry-backed history

For users who want the conversation persisted in the **same Foundry response store** that today's `azure.ai.agentserver.responses.store._foundry_provider.FoundryStorageProvider` writes to (so e.g. Foundry Workbench can replay the conversation, or other Foundry tools can introspect it), a new provider is added — proposed name `FoundryHistoryProvider` — implementing the standard `HistoryProvider` Protocol and ported from agentserver's storage code (no `agentserver` runtime dependency). Shipped in `agent-framework-foundry`, attached the same way any other history provider is attached to an agent:

```python
agent = ChatClientAgent(
    chat_client=client,
    history_provider=FoundryHistoryProvider(
        endpoint=os.environ["FOUNDRY_ENDPOINT"],
        load_messages=True,
    ),
)

host = AgentFrameworkHost(target=agent, channels=[ResponsesChannel()])
```

The provider implements the standard `HistoryProvider` interface — there is no Responses-specific Protocol in between. It is also valid for any other channel (Telegram, Invocations, …) — Foundry storage simply becomes the chosen backend.

Foundry's storage backend keys writes off two platform-injected request headers (`x-agent-user-isolation-key`, `x-agent-chat-isolation-key`) rather than the request body. The Responses and Invocations channels parse both headers off the inbound request and forward them as an opaque mapping on `ChannelRequest.attributes["isolation"]` (`{"user_key", "chat_key"}`); the host's per-request `bind_request_context` then passes that value to `FoundryHostedAgentHistoryProvider.bind_request_context(isolation=...)`, which the provider applies to its storage calls. Channels never import `IsolationContext`; the provider accepts both an `IsolationContext` instance and a plain mapping. When the headers are absent (local dev outside the Hosted Agents runtime) the attribute is omitted and storage falls back to non-isolated reads/writes, so the same code path works in both environments.

##### Multi-provider composition

The existing AF convention applies: an agent may compose **multiple** `HistoryProvider`s, but **only one** carries `load_messages=True`. Common patterns:

- *Single store.* `FileHistoryProvider(load_messages=True)` — local dev. Or `FoundryHistoryProvider(load_messages=True)` — Foundry-backed prod.
- *Audit dual-write.* `FoundryHistoryProvider(load_messages=True)` + `CosmosHistoryProvider(load_messages=False)` — Foundry is the source of truth used to reconstruct context for the LLM; Cosmos receives a write-only audit copy.
- *Mirror to Foundry for Workbench replay only.* Conversely, an in-house store can hold `load_messages=True` while `FoundryHistoryProvider(load_messages=False)` mirrors writes into Foundry purely so the conversation shows up in Foundry tooling.

The choice of where to store, and whether to dual-write, is fully the developer's. The channel does not need to know which backing store(s) the agent is using.

#### Channel-owned per-thread state

Some channel protocols carry **non-message** durable state attached to the conversation — most notably AG-UI's per-thread `state` object, mutated mid-stream via `StateSnapshotEvent` / `StateDeltaEvent` (JSON-Patch-shaped) and read by the front-end on the next turn. This is *not* message history, so it does not belong on `HistoryProvider`; but it has the same lifetime, isolation, and "opaque to the host" properties as messages, so the framework already has the right primitive: **`ContextProvider`**.

`HistoryProvider` is only one concrete `ContextProvider` (the one that uses the per-source `state: dict[str, Any]` slot to hold messages). Channels with non-message per-thread state SHOULD ship their own `ContextProvider` subclass and write into the same per-source `state` slot.

Sketch (for AG-UI; the same pattern applies to any event-rich front-end):

```python
from agent_framework import ContextProvider, ContextProviderState

class AgUiStateProvider(ContextProvider):
    """Per-thread non-message state for AG-UI front-ends.

    Persists the AG-UI ``state`` object scoped by ``source_id`` (the
    AgentSession id). Reads from ``ChannelRequest.client_state`` before
    the run, exposes the current value to the agent via Context, and lets
    the channel diff it after the run to emit StateSnapshotEvent /
    StateDeltaEvent on the wire.
    """

    state_key = "ag_ui_state"  # slot in the per-source state dict

    async def before_run(self, context, *, source_id, **kw):
        slot = context.state.setdefault(source_id, {})
        # If the request supplied a fresh client_state, seed/replace it.
        if (incoming := context.request.client_state) is not None:
            slot[self.state_key] = dict(incoming)
        # Expose the live value to the agent (e.g. into context.metadata).

    async def after_run(self, context, *, source_id, **kw):
        # The current value lives in context.state[source_id][self.state_key];
        # the channel reads it and emits StateSnapshotEvent / StateDeltaEvent.
        ...
```

Composition rules are unchanged: one `HistoryProvider` carries `load_messages=True`, additional `ContextProvider`s (including `AgUiStateProvider`) attach alongside. Backing storage is whatever the user wires — in-memory for dev, the same physical store as messages for prod. **No new storage protocol is introduced for channel state**; it shares the same per-source state slot that `HistoryProvider` uses.

#### Storage taxonomy

To make the picture explicit: there are exactly three distinct *storage seams* in the hosting design, each with a clear scope. The first two are usually backed by the same physical store the user wires; they stay distinct as protocols because the data shapes differ.

| Seam | Scope | Examples |
|---|---|---|
| **`ContextProvider`** (per-conversation) | Per-`source_id` data the agent needs at run time. Messages (via `HistoryProvider`), AG-UI per-thread state (via `AgUiStateProvider`), or any future per-conversation extension. **The only public per-conversation seam.** | `FileHistoryProvider`, `FoundryHistoryProvider`, `AgUiStateProvider` |
| **Host-level pluggable store** (per-host) | `RunHandle`s for background runs, identity-link grants, last-seen `(isolation_key, channel)` records. In-memory in v1; pluggable in v1 fast follow (req #23). MAY be backed by the same physical store as `ContextProvider`, but the protocol is distinct because the data is host-execution metadata, not per-conversation context. | (in-memory v1; future Cosmos / SQL adapter) |
| **`CheckpointStorage`** (workflow runtime) | Workflow executor frames so a workflow can resume after process restart. Structurally distinct from both seams above (the data is workflow-runtime state, not session/identity state). MAY share a physical backend, but the protocol stays separate. | `FileCheckpointStorage`, future `CosmosCheckpointStorage` |

Concretely, this means an app deploying onto e.g. Foundry storage can run **all three** against the same Foundry backend and still have three orthogonal protocol surfaces — one per concern — instead of one universal store everything accidentally collides in.

Channels surface per-request transport state (response ids, isolation keys, future signals) on `ChannelRequest.attributes`; the host's `bind_request_context` forwards those attributes as kwargs to each `ContextProvider.bind_request_context` call so providers can apply them to their reads and writes. Providers SHOULD accept `**_` to ignore unknown attributes for forward-compat. This keeps channel↔provider coupling to a documented attribute name (e.g. `"isolation"`) instead of requiring providers to install ASGI middleware.

The `ResponsesChannel` exposes both an HTTP transport (`{path}/v1/...`) and an optional **WebSocket transport** (`{path}{websocket_path}`, default `/responses/ws`) controlled by `transports`. The WS transport carries the same Responses request/event model as the HTTP+SSE variant — clients open a single connection per conversation and send/receive Responses frames as JSON messages. Both transports go through the same `run_hook`, the same default mapping, and the same `ChannelRequest` shape; the channel codec is responsible for framing only. Auth is reused from the HTTP transport (Authorization header on the `Upgrade` request); subprotocol negotiation is open (see Open Questions).

### Default invocation behavior by channel

Each built-in channel owns a **default** mapping from its protocol request model into a `ChannelRequest`. That mapping flows through the optional `run_hook` before the host resolves session behavior and invokes the target.

| Channel | Default mapping |
|---|---|
| `ResponsesChannel` | Forwards relevant caller settings (e.g. `temperature`) into `ChannelRequest.options`; maps `store=False` to `session_mode="disabled"`. The same default mapping is used for both HTTP and WebSocket transports — WS frames are decoded into the same Responses request model before invocation. |
| `InvocationsChannel` | Maps the request body into `input`, `options`, and session behavior for the hosted target. |
| `TelegramChannel` | Maps incoming messages or commands into `input`, `stream`, and session defaults appropriate for the chat. |

### ASGI server portability

The hosting architecture is coupled to **ASGI/Starlette**, not to **Uvicorn** specifically.

- `host.app` is the canonical portability surface.
- `host.serve(...)` is only the default convenience path (lazy-imports `uvicorn`).
- Because `host.app` is a standard Starlette/ASGI app, it can run on Hypercorn, Daphne, Granian, or Gunicorn-with-Uvicorn-workers.
- ASGI **WebSocket** scope/frames are first-class: any channel may contribute `WebSocketRoute`s alongside HTTP routes, and the chosen ASGI server must support the WebSocket scope (Uvicorn, Hypercorn, Daphne, and Granian all do).

The packaging question for `uvicorn` (required dependency vs optional extra) is therefore a **convenience choice**, not an architectural constraint. See Open Questions.

### Error Responses

| Status | Condition | Notes |
|---|---|---|
| `400 Bad Request` | Channel-specific protocol validation failure | Owned by the channel codec. |
| `401 Unauthorized` / `403 Forbidden` | Channel-specific auth/signature validation failure | Owned by channel middleware (e.g. Telegram secret token, Invocations auth). |
| `404 Not Found` | Route not contributed by any channel | Standard Starlette behavior. |
| `409 Conflict` | Session-resolution conflict with `session_mode="required"` and no resolvable session | Host-level. |
| `422 Unprocessable Entity` | `run_hook` raised a validation error | Channel surfaces the hook's error per protocol conventions. |

## Terminology

- **Host** (`AgentFrameworkHost`): The Python object that owns one Starlette app, one **hostable target** (an agent or a workflow), and a sequence of channels. Provides `host.app` (canonical ASGI surface) and `host.serve(...)` (uvicorn convenience). Named `AgentFrameworkHost` rather than `AgentHost` because the target is not restricted to agents.
- **Hostable target**: The executable object the host fronts — either a `SupportsAgentRun`-compatible agent or a `Workflow`. The host detects the kind and dispatches to the appropriate execution seam; channels remain unchanged.
- **Channel**: A pluggable component that contributes routes, middleware, commands, and lifecycle hooks to a host. One channel = one external protocol surface (Responses, Invocations, Telegram, …). Used interchangeably with "head" in earlier discussions; **Channel** is the canonical name.
- **`ChannelRequest`**: The host-neutral, normalized invocation envelope produced by a channel before the host calls the target's execution seam. Carries `input`, `options`, `session`, `session_mode`, and channel-specific `attributes`.
- **`ChannelSession`**: A small session hint with a stable `key`, an optional protocol-visible `conversation_id`, and an opaque `isolation_key`. The host resolves it into an `AgentSession`; storage specifics are deferred.
- **`isolation_key`**: An opaque partition boundary aligned with hosted-agent terminology — may represent a user, tenant, chat, or other scope without baking direct identity semantics into the generic host.
- **Channel-native identity** (`ChannelIdentity`): The user/account identifier the channel observes from its own platform (Telegram `chat_id`/`user_id`, Teams AAD object id, WhatsApp phone number, Slack user id). Always per-channel; never assumed to align across channels.
- **`IdentityResolver`**: Host-level callable that maps a `ChannelIdentity` to an `isolation_key`. The default resolver **auto-issues** a fresh, stable `isolation_key` the first time a `(channel, native_id)` pair is seen and persists it in the host's identity store, so every end user automatically gets a per-user partition on first contact through any channel — without app code. Linking (see `IdentityLinker`) **merges** the second channel's auto-issued key onto the first channel's `isolation_key`, so cross-channel continuity is a one-shot operation, not a per-channel mapping hook. Apps that already own an identity namespace (corporate user id, tenant-scoped account id) can supply a custom resolver that returns those values directly.
- **`IdentityLinker`**: Host-level component that runs a connect ceremony — typically OAuth, MFA, or a signed one-time code — to associate a new `ChannelIdentity` with an existing `isolation_key`. Contributes its own routes (e.g. OAuth callback) and lifecycle to the host. A built-in `link`/`connect` `ChannelCommand` is exposed automatically when one is configured. On successful ceremony completion, also stores any verified IdP claim recovered from the proof (e.g. Entra ID `oid`) so subsequent channels that supply the same claim can be auto-merged onto the same `isolation_key` silently. Combined with `Channel(require_link=True)`, this enables an "authenticate before chatting" enforcement model where the first channel forces the OAuth ceremony and every other channel using the same IdP joins the same session without a second `/link`.
- **`LinkChallenge`**: The protocol-neutral artifact returned by `IdentityLinker.begin(...)` describing what the user must do to complete the ceremony — typically one of: a URL to visit (OAuth), a short code to enter on the other channel (one-time code), or an MFA prompt.
- **`ResponseTarget`**: Per-request directive on `ChannelRequest` controlling **where** the response is delivered: `originating` (default), `active`, a specific channel, a list of channels, `all_linked`, or `none`. Independent of `session_mode`.
- **`ChannelPush`**: Optional channel capability for proactive outbound delivery — Telegram proactive message, Teams proactive bot message, webhook callback, SSE broadcast. Required to be the destination of a non-`originating` `ResponseTarget`.
- **Active channel**: The channel most recently observed for a given `isolation_key`. Tracked by the host on every successfully resolved request; consumed by `ResponseTarget.active`.
- **`RunHandle`**: First-class artifact for background/asynchronous runs, returned immediately from `host.run_in_background(request)`. Carries `id`, `status`, `isolation_key`, `result`/`error`, and the configured `response_target`. Host pushes the result to the response target when ready and serves it via channel poll routes.
- **Background run**: A `ChannelRequest` submitted via `host.run_in_background(request)` (or any request with `background=True`). The originating call returns a `RunHandle` immediately; the response is delivered later via the configured `ResponseTarget` and/or polled by run id.
- **`session_mode`**: Per-request directive (`auto` | `required` | `disabled`) that controls whether the host resolves a session before invoking the target. Lets channels honor protocol semantics like Responses `store=False` and lets app authors enforce extra policy.
- **`confidentiality_tier`** (channel-level): Opaque label (`"corp"`, `"public"`, `"internal"`, …) declared on a `Channel` and consumed by the host's `LinkPolicy`. Two channels with different confidentiality tiers can share an agent target on one host while remaining session-isolated.
- **`LinkPolicy`**: Host-level decision over which channel pairs may share an `isolation_key` (link) and which channel pairs may be `ResponseTarget` source/destination for one another (deliver). Built-in variants: allow-all (default), same-tier-only, explicit allow-list, deny-all. See [LinkPolicy and confidentiality_tier](#linkpolicy-and-confidentiality_tier) for the full contract and built-ins table.
- **`ChannelContribution`**: What a channel returns from `contribute(...)` — routes, middleware, commands, and `on_startup`/`on_shutdown` hooks. The host aggregates contributions into one Starlette app.
- **`ChannelCommand`**: A transport-neutral command descriptor (`name`, `description`, `handle`). Message channels project these into native command surfaces — Telegram bot commands, future Teams slash commands, WhatsApp menus.
- **`ChannelRunHook`**: Per-request callable on built-in channels. Runs after the channel's default `ChannelRequest` is produced, before session resolution. The escape hatch for forcing or forbidding session use, requiring extra options, adapting to targets like `A2AAgent`, **and** reshaping a channel's free-form input into the typed inputs a `Workflow` target expects.
- **Native command registration**: The startup-time projection of `ChannelCommand` metadata into a platform's native command catalog (e.g. Telegram `set_my_commands(...)`).
- **`SupportsAgentRun`**: The existing framework agent execution seam (`run(..., session=..., stream=...)`) — the contract the host uses when the hostable target is an agent.
- **`Workflow`**: The framework workflow execution seam — the contract the host uses when the hostable target is a workflow. The host wraps the workflow's outputs into the same `HostedRunResult` / `HostedStreamResult` shape so channels do not need to distinguish.

## Hero Code Samples

> **Common prerequisite:** Every sample below calls `host.serve(...)`, which lazy-imports `uvicorn`. Install `uvicorn` (e.g. `pip install uvicorn`) — or the corresponding `agent-framework-hosting[serve]` extra if the package ships one (see Open Question #2) — alongside the per-sample dependencies listed in each scenario's **Prerequisites** block. Samples that use `host.app` directly (handed to Hypercorn/Daphne/Granian/Gunicorn+uvicorn workers) do not require `uvicorn`.

### Scenario 1: Expose one agent on the Responses API

A developer has an agent and wants to expose it as the OpenAI-compatible Responses API on `localhost:8000` with no manual server bootstrap.

> **Prerequisites:** This sample assumes:
> - `agent-framework-hosting` and `agent-framework-hosting-responses` are installed
> - An `OPENAI_API_KEY` is available in the environment

```python
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework.hosting import AgentFrameworkHost, ResponsesChannel

agent = Agent(
    name="WeatherAgent",
    instructions="You are a helpful weather agent.",
    client=OpenAIChatClient(model="gpt-4.1-mini"),
)

host = AgentFrameworkHost(
    target=agent,
    channels=[ResponsesChannel()],
)

if __name__ == "__main__":
    host.serve(host="localhost", port=8000)
```

This exposes the Responses routes under `/responses/v1`. No manual `uvicorn` import, no protocol handlers written by the user.

### Scenario 2: Expose Responses + Invocations on one host with shared Starlette middleware

Same agent, both protocols, with CORS applied at the host level.

> **Prerequisites:** This sample assumes:
> - `agent-framework-hosting`, `-responses`, and `-invocations` are installed
> - A Foundry project with a `gpt-4.1` model deployment

```python
from azure.identity import AzureCliCredential
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.hosting import AgentFrameworkHost, InvocationsChannel, ResponsesChannel

agent = Agent(
    name="TravelAgent",
    instructions="Help users plan travel and keep answers concise.",
    client=FoundryChatClient(
        project_endpoint="https://my-project.services.ai.azure.com/api/projects/travel",
        model="gpt-4.1",
        credential=AzureCliCredential(),
    ),
)

host = AgentFrameworkHost(
    target=agent,
    channels=[
        ResponsesChannel(),         # -> /responses/v1
        InvocationsChannel(),       # -> /invocations/invoke
    ],
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["https://chat.contoso.com"],
            allow_methods=["*"],
            allow_headers=["*"],
        ),
    ],
)

# Hand the canonical ASGI app to any server, or use the convenience method.
app = host.app  # for Hypercorn / Granian / Gunicorn+uvicorn workers
host.serve(host="localhost", port=8000)
```

### Scenario 3: Per-request run hook on the Responses channel

The developer wants to enforce that every Responses call sets `temperature`, ignore caller `store=False`, and force host-managed session use — none of which is part of the official Responses spec, but all of which is valid app policy.

> **Prerequisites:** This sample assumes:
> - The Responses channel is wired into an `AgentFrameworkHost` (see Scenario 1)

```python
from dataclasses import replace

from agent_framework.hosting import (
    AgentFrameworkHost,
    ChannelRequest,
    ResponsesChannel,
)


def responses_policy(request: ChannelRequest, **kwargs) -> ChannelRequest:
    if request.options is None or request.options.temperature is None:
        raise ValueError("This host requires temperature on every Responses call.")

    # Intentionally ignore caller store=False and always require host-managed sessions.
    return replace(request, session_mode="required")


host = AgentFrameworkHost(
    target=agent,
    channels=[ResponsesChannel(run_hook=responses_policy)],
)
host.serve(host="localhost", port=8000)
```

The hook runs **after** the channel produces its default `ChannelRequest` and **before** the host resolves session behavior and calls `SupportsAgentRun.run(...)`. The same shape works to adapt to targets like `A2AAgent` — strip or remap channel-derived options that the target does not consume.

### Scenario 4: Telegram channel with native command catalog (polling)

A developer wants to expose the same agent as a Telegram bot, with first-class native commands (`/start`, `/new`, `/sessions`, …) registered into Telegram's command menu at startup. Modeled after PR #5393.

> **Prerequisites:** This sample assumes:
> - `agent-framework-hosting-telegram` is installed
> - `TELEGRAM_BOT_TOKEN` is set in the environment

```python
import os

from agent_framework.hosting import (
    AgentFrameworkHost,
    ChannelCommand,
    ChannelCommandContext,
    TelegramChannel,
)


async def handle_start(context: ChannelCommandContext) -> None:
    await context.reply(
        "Hi! Commands: /new, /sessions, /todo, /memories, /reminders, "
        "/resume, /cancel, /reasoning, /tokens."
    )


async def handle_noop(context: ChannelCommandContext) -> None:
    await context.reply("Command received.")


TELEGRAM_COMMANDS = [
    ChannelCommand("start", "Introduce the bot", handle_start),
    ChannelCommand("new", "Start a new local session", handle_noop),
    ChannelCommand("sessions", "List local sessions", handle_noop),
    ChannelCommand("todo", "List todos for the active session", handle_noop),
    ChannelCommand("memories", "List memory topics for the active session", handle_noop),
    ChannelCommand("reminders", "List reminders for the active session", handle_noop),
    ChannelCommand("resume", "Resume the latest pending or previous session", handle_noop),
    ChannelCommand("cancel", "Cancel the active response", handle_noop),
    ChannelCommand("reasoning", "Toggle the transient reasoning preview", handle_noop),
    ChannelCommand("tokens", "Toggle token usage details", handle_noop),
]

telegram = TelegramChannel(
    bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
    transport="polling",
    commands=TELEGRAM_COMMANDS,
    register_native_commands=True,
)

host = AgentFrameworkHost(target=agent, channels=[telegram])
host.serve(host="localhost", port=8000)
```

This mirrors the important shape from PR #5393: command metadata is declared once, the channel registers it into Telegram's native menu at startup (`set_my_commands(...)`), and runtime command dispatch stays channel-local.

### Scenario 5: Telegram webhook mode on the same host as Responses + Invocations

Same agent, three channels, one Starlette app, one process.

> **Prerequisites:** Same as Scenario 4, plus a public HTTPS URL for the webhook.

```python
host = AgentFrameworkHost(
    target=agent,
    channels=[
        ResponsesChannel(),                          # -> /responses/v1
        InvocationsChannel(),                        # -> /invocations/invoke
        TelegramChannel(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            transport="webhook",                     # -> /telegram/webhook
            commands=TELEGRAM_COMMANDS,
        ),
    ],
)

host.serve(host="0.0.0.0", port=8000)
```

Webhook transport contributes `/telegram/webhook` by default; the command catalog remains identical to the polling sample.

### Scenario 6: Cross-channel chat continuity (Telegram → Teams) with zero per-channel boilerplate

A developer wants the same end user to start a conversation on Telegram and continue it on a future Teams channel against the same agent and the same conversation history. **No per-channel mapping code is required.** The default `IdentityResolver` auto-issues an `isolation_key` to each `(channel, native_id)` on first contact and persists it; cross-channel continuity is one one-shot link/merge operation (Scenario 7).

> **Prerequisites:** This sample assumes:
> - `agent-framework-hosting-telegram` is installed (and a future `-teams` channel package)

```python
import os

from agent_framework.hosting import AgentFrameworkHost, TelegramChannel
# from agent_framework.hosting import TeamsChannel  # future


host = AgentFrameworkHost(
    target=agent,
    channels=[
        TelegramChannel(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            transport="webhook",
        ),
        # TeamsChannel(...),  # future
    ],
)
host.serve(host="0.0.0.0", port=8000)
```

That's the entire setup. No `run_hook`, no per-channel `resolve_user_id_from_*` function, no manual `ChannelSession` construction. The flow:

1. End user `alice` chats with the bot on Telegram for the first time. The default resolver sees `ChannelIdentity(channel="telegram", native_id="<chat_id>", ...)`, auto-issues `isolation_key="hk_018f…a3"`, persists `("telegram", "<chat_id>") → "hk_018f…a3"`, and the host resolves a fresh `AgentSession` scoped by that key.
2. Subsequent Telegram messages from the same `chat_id` resolve to the same `isolation_key` and the same `AgentSession` — `alice`'s Telegram conversation history is intact.
3. The first time `alice` messages the bot on Teams, the resolver auto-issues a **different** `isolation_key="hk_018f…b7"` for `("teams", "<aad-oid>")` — Teams sees a fresh conversation, because the host has no way to know yet that the two channel-native identities belong to the same person.
4. To converge them, `alice` runs the host-provided `/link` command on Teams (Scenario 7). The link ceremony **merges** `("teams", "<aad-oid>")` onto her existing Telegram-issued `isolation_key="hk_018f…a3"`. From the next turn on, Teams resolves to the same `AgentSession` as Telegram, and the agent sees one continuous thread.

Two notes:

- **The `isolation_key` is opaque on purpose.** The default auto-issued key (`"hk_018f…a3"`) is just a stable handle the host uses to partition sessions; apps that own a real identity namespace (corporate user id, tenant-scoped account id) can supply a custom `identity_resolver` that returns those values directly and skip auto-issuance entirely.
- **No app-supplied identity store is required for the single-host case.** The host's built-in identity store handles auto-issuance and atomic merge-on-link in process. Cross-host/cross-process continuity (and surviving restarts) needs the pluggable session/identity store (req #23).

### Scenario 7: Linking a new channel to an existing identity via OAuth

A developer wants every Telegram chat to be **authenticated up front** via OAuth (Microsoft Entra ID) before the agent will respond, and wants Teams chats from the same Entra ID user to be **auto-linked** to the existing session — no second `/link` ceremony, just sign in once on the first channel and the rest follow automatically.

> **Prerequisites:** This sample assumes:
> - `agent-framework-hosting`, `agent-framework-hosting-telegram`, and the (future) Teams channel are installed
> - An OAuth provider is configured (Microsoft Entra ID in this example)

```python
import os

from agent_framework.hosting import (
    AgentFrameworkHost,
    OAuthIdentityLinker,
    TelegramChannel,
)


# The OAuth linker contributes its own /identity/oauth/microsoft/{start,callback}
# routes to the host. On successful completion, the host's built-in identity
# store atomically records BOTH the originating channel-native identity AND the
# verified IdP claim (Entra ID object id) so future channels that authenticate
# the same IdP account can auto-link without a second ceremony.
linker = OAuthIdentityLinker(
    provider="microsoft",
    client_id=os.environ["AAD_CLIENT_ID"],
    client_secret=os.environ["AAD_CLIENT_SECRET"],
)

host = AgentFrameworkHost(
    target=agent,
    identity_linker=linker,
    channels=[
        # require_link=True gates the channel: any inbound message from an
        # un-linked ChannelIdentity is short-circuited to a LinkChallenge reply
        # instead of being dispatched to the agent.
        TelegramChannel(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            transport="webhook",
            require_link=True,
        ),
        # TeamsChannel(app_id=..., require_link=True),  # future — same flag
    ],
)
host.serve(host="0.0.0.0", port=8000)
```

The flow:

1. `alice` sends her first message on Telegram. The `TelegramChannel` extracts `ChannelIdentity(channel="telegram", native_id="<chat_id>")` and asks the linker `is_linked(...)`. It is not. Because `require_link=True`, the channel does **not** invoke the agent; instead it asks `linker.begin(channel_identity)` for a `LinkChallenge`, renders the challenge URL into Telegram (clickable button), and returns.
2. `alice` clicks the button, signs in with Microsoft Entra ID, and the OAuth callback hits the linker's route. `linker.complete(...)` verifies the authorization code and records **two things atomically** in the identity store:
   - `(channel="telegram", native_id="<chat_id>") → isolation_key="hk_018f…a3"`
   - `verified_claim("microsoft.oid", "<aad-object-id>") → isolation_key="hk_018f…a3"`
3. `alice` replies on Telegram. The channel sees the link is now present, resolves the existing `isolation_key`, and forwards the message to the agent normally. From here on, Telegram chats are routed without further ceremony.
4. The next day, `alice` opens Teams. The `TeamsChannel` extracts both the channel-native identity (`teams`, `<aad-oid>`) **and** the verified IdP claim from the inbound activity (Teams already authenticates with Entra ID, so the AAD object id is trusted). It asks the linker `is_linked(...)`. The `(teams, <aad-oid>)` pair is **not** in the store — but the verified claim `("microsoft.oid", "<aad-object-id>")` **is**. The linker auto-merges `(teams, <aad-oid>) → isolation_key="hk_018f…a3"` without any user-visible `/link` ceremony.
5. From the next turn on, both Telegram and Teams resolve to the **same** `isolation_key` and the **same** `AgentSession`. The agent sees the conversation history from both channels as one continuous thread.

The two enabling pieces:

- **`require_link: bool` on the channel** — when `True`, the channel checks the linker before dispatching every inbound request. Un-linked identities are short-circuited to a rendered `LinkChallenge` instead of an agent invocation. Default is `False` (the opportunistic flow below).
- **Verified IdP claims in the linker's identity store** — when an OAuth ceremony completes, the linker records the verified identity claim (e.g. `(microsoft.oid, <oid>)`) alongside the channel-native identity. Channels that can supply the same kind of verified claim from their own auth context (Teams via the AAD bearer on the activity, future M365 channels via the same bearer, …) get **auto-linked silently** on first contact when their claim matches an existing entry. This is what makes "sign in once on Telegram, Teams just works" possible without any per-channel link ceremony.

**Variant — opportunistic linking (`require_link=False`).** Leave the flag at its default and the channel will dispatch un-linked identities straight to the agent (the host's default resolver auto-issues a fresh `isolation_key` for them). The user can later run the `link` `ChannelCommand` manually to merge that auto-issued key onto an existing one. This is the lower-friction onboarding flow at the cost of allowing pre-link conversations to exist in their own isolated session until merged.

**Variant — alternative ceremony.** Swapping the linker for `OneTimeCodeIdentityLinker(...)` changes the ceremony to "complete `/link` on channel A, get a 6-digit code, run `/link 482931` on channel B"; with `require_link=True` the channel just renders the code-entry instructions instead of an OAuth URL. `MfaIdentityLinker(factor=...)` defers identity assurance to the IdP's MFA factor. Apps with their own corporate identity namespace can additionally pass a custom `identity_resolver` so the post-link `isolation_key` is the corporate user id instead of the host-issued opaque key. Channels themselves are unchanged across all three variants — only the linker and (optionally) the resolver change.

### Scenario 8: Background run with cross-channel response delivery

A developer wants the user to start a long-running task on Telegram and pick up the response on Teams (whichever channel the user happens to be on when the result is ready). The originating Telegram message returns a `RunHandle` immediately; when the agent completes, the host pushes the result to the user's currently active channel via `ChannelPush`. A poll route is also exposed for callers that prefer polling.

> **Prerequisites:** This sample assumes:
> - `agent-framework-hosting`, `agent-framework-hosting-telegram`, and the (future) Teams channel are installed
> - The user is already linked across Telegram and Teams (Scenario 7)

```python
import os
from dataclasses import replace

from agent_framework.hosting import (
    AgentFrameworkHost,
    ChannelRequest,
    ResponseTarget,
    TelegramChannel,
)


# Override the Telegram channel default: any inbound message becomes a
# background run delivered to the user's currently active channel.
async def telegram_background(request: ChannelRequest, **kwargs) -> ChannelRequest:
    return replace(
        request,
        background=True,
        response_target=ResponseTarget.active,
    )


host = AgentFrameworkHost(
    target=agent,
    identity_linker=linker,                # from Scenario 7
    channels=[
        TelegramChannel(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            transport="webhook",
            run_hook=telegram_background,
        ),
        # TeamsChannel(...),  # future
    ],
)
host.serve(host="0.0.0.0", port=8000)
```

The flow:

1. `alice` sends a Telegram message that triggers a long-running tool. The Telegram channel produces a `ChannelRequest`; the hook flips `background=True` and sets `response_target=ResponseTarget.active`.
2. `host.run_in_background(request)` returns a `RunHandle(id="run_018f…", status="queued")`. The Telegram channel acknowledges with a short "Working on it…" reply that includes the run id (it could equally render a "Cancel" inline button bound to the run id).
3. The host runs the target asynchronously. When complete, it resolves `ResponseTarget.active` against the host-tracked last-seen channel for `isolation_key="alice@contoso.com"`. If `alice` is currently on Teams, the host calls `TeamsChannel.push(channel_identity, hosted_run_result)`; if she is still on Telegram, it calls `TelegramChannel.push(...)` (so the same setup gracefully degrades to "reply on Telegram if she never switched").
4. `RunHandle` is updated to `status="completed"` with the populated `result`. Any caller can poll `GET /telegram/runs/{run_id}` (or the equivalent route the channel exposes) to retrieve the run state by id.

Variants without changing channel code:

- `ResponseTarget.channel("teams")` — always deliver to Teams, regardless of where the user is.
- `ResponseTarget.all_linked` — broadcast to every channel `alice` has linked.
- `ResponseTarget.none` — fully detached: caller polls `host.get_run(run_id)` (or the channel's poll route); no proactive push.
- `background=False` with `response_target=ResponseTarget.active` — synchronous wait, but result still routed away from the originating channel (rare; mostly useful for pipelines where the originating call is a programmatic trigger and the human user lives elsewhere).

If the chosen destination channel does not implement `ChannelPush` (e.g. Responses), the host falls back to the `originating` channel and records the fallback in telemetry. This makes the Responses + background-run combo work as "submit on Responses, poll on Responses" without surprising silent drops.

### Scenario 9: Hosting a `Workflow` instead of an agent

> **Prerequisites:** This sample assumes:
> - `agent-framework-hosting` and `agent-framework-hosting-invocations` are installed
> - A `Workflow` definition with typed inputs (`OrderIntakeInputs`)

```python
from dataclasses import dataclass, replace

from agent_framework import Workflow
from agent_framework.hosting import (
    AgentFrameworkHost,
    ChannelRequest,
    InvocationsChannel,
)


@dataclass
class OrderIntakeInputs:
    customer_id: str
    sku: str
    quantity: int


workflow: Workflow = build_order_intake_workflow()  # application-defined


def adapt_to_workflow_inputs(request: ChannelRequest, *, protocol_request=None, **kwargs) -> ChannelRequest:
    # The channel produces a default ChannelRequest with text input. The workflow
    # needs typed OrderIntakeInputs — the hook is the adapter point.
    payload = protocol_request  # raw Invocations request body
    inputs = OrderIntakeInputs(
        customer_id=payload["customer_id"],
        sku=payload["sku"],
        quantity=int(payload["quantity"]),
    )
    return replace(request, input=inputs)


host = AgentFrameworkHost(
    target=workflow,
    channels=[
        InvocationsChannel(run_hook=adapt_to_workflow_inputs),
    ],
)
host.serve(host="localhost", port=8000)
```

The host detects that `target` is a `Workflow` and dispatches the resulting `ChannelRequest.input` to `Workflow.run(...)` instead of `SupportsAgentRun.run(...)`. The channel does not need to know which kind of target it is fronting — `HostedRunResult` and `HostedStreamResult` are normalized across both seams. The same workflow target could equally be exposed on Telegram or a Responses channel by supplying the appropriate `run_hook` to translate inbound chat messages into typed workflow inputs.

### Scenario 10: Authoring a new channel package

The shape any new channel follows: parse external protocol → produce default `ChannelRequest` → optionally apply hook → `context.run(...)` / `context.stream(...)` → serialize back.

```python
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from agent_framework.hosting import (
    Channel,
    ChannelContext,
    ChannelContribution,
    ChannelRequest,
    ChannelSession,
)


class MyWebhookChannel:
    name = "mywebhook"

    def __init__(self, *, path: str = "/mywebhook") -> None:
        self._path = path

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        async def endpoint(request: Request) -> JSONResponse:
            payload = await request.json()
            channel_request = ChannelRequest(
                channel=self.name,
                operation="message.create",
                input=payload["text"],
                session=ChannelSession(
                    key=payload["thread_id"],
                    isolation_key=payload["account_id"],
                ),
            )
            result = await context.run(channel_request)
            return JSONResponse({"reply": result.text})

        return ChannelContribution(routes=[Route(f"{self._path}/inbound", endpoint, methods=["POST"])])
```

## Information Design

### Canonical flow

```text
external request/event
    -> channel-specific parsing + validation
    -> ChannelIdentity extraction (per-channel native id)
    -> default channel invocation mapping
    -> optional run_hook
    -> ChannelRequest (carries response_target, background)
    -> AgentFrameworkHost / ChannelContext
    -> identity_resolver(ChannelIdentity) -> isolation_key
    -> host records (isolation_key, channel, now) as last-seen (for ResponseTarget.active)
    -> AgentSession resolution (per session_mode, scoped by isolation_key)
    -> [foreground] target execution seam -> HostedRunResult/HostedStreamResult -> originating channel serialization
    -> [background or response_target != originating]
            -> RunHandle returned immediately to originating channel
            -> target executes asynchronously
            -> on completion, deliver to ResponseTarget via destination channel.push(...)
            -> RunHandle updated; available via host.get_run(run_id) and channel poll routes
```

A parallel **link ceremony flow** runs out-of-band when a user invokes the host-provided `link`/`connect` command on a channel:

```text
channel /link command
    -> linker.begin(ChannelIdentity) -> LinkChallenge
    -> channel-specific rendering (URL, code, MFA prompt)
    -> user completes the ceremony out-of-band (browser, second channel, MFA app)
    -> linker callback/verification route
    -> linker.complete(challenge_id, proof) -> isolation_key
    -> host atomically associates (channel, native_id) -> isolation_key
    -> subsequent requests resolve to the linked AgentSession
```

### Inbound ownership

| Concern | Owned by | Notes |
|---|---|---|
| HTTP / WebSocket route shape | Channel package | e.g. `/responses/v1`, `/responses/ws`, `/invocations/invoke`, `/telegram/webhook` — channels may contribute either or both |
| Protocol request model | Channel package | e.g. Responses items (HTTP body or WS frames), Invocations body, Telegram webhook payload |
| Signature/auth validation | Channel package or host middleware | channel-specific unless generic Starlette middleware |
| Request-to-agent invocation mapping | Channel package + optional `run_hook` | forwards caller parameters into `ChannelRequest.options`, chooses `session_mode`, can enforce extra app policy |
| Native command catalog | Channel package using host-defined `ChannelCommand` | e.g. Telegram bot commands, future Teams/WhatsApp surfaces |
| Command registration at startup | Channel package | e.g. Telegram `set_my_commands(...)` |
| Command dispatch | Channel package | commands may reply locally, manipulate channel-owned state, or invoke the agent |
| Normalized input to the agent | Host core | `ChannelRequest.input` reuses `AgentRunInputs` |
| Session resolution | Host core | based on `ChannelSession` + `ChannelRequest.session_mode`; storage specifics deferred |
| Channel-native identity extraction | Channel package | populates `ChannelIdentity(channel, native_id, attributes)` per request |
| Identity resolution (`native_id` → `isolation_key`) | Host core via `IdentityResolver` | default **auto-issues and persists** a per-user `isolation_key` on first contact per `(channel, native_id)`; user-supplied resolver can return app-owned identities directly |
| Identity store (`(channel, native_id) → isolation_key`) | Host core | in-memory in v1; pluggable in fast follow (req #23). Owns auto-issuance and atomic merge-on-link. |
| Identity link ceremony (OAuth / MFA / one-time code) | Host core via `IdentityLinker` | linker contributes its own routes + lifecycle; channels surface a built-in `link`/`connect` command |
| Link & delivery policy across confidentiality tiers | Host core via `LinkPolicy` | consulted at link time (refuse incompatible link attempts) and at delivery time (drop incompatible `ResponseTarget` destinations); built-in policies cover all-allow, same-tier, explicit allow-list, deny-all |
| Active-channel tracking | Host core | updated on every successfully resolved request; consumed by `ResponseTarget.active` |
| Response-target resolution | Host core | translates `ResponseTarget` (originating, active, specific, list, all_linked, none) into an ordered set of `(channel, ChannelIdentity)` deliveries |
| Proactive outbound delivery | Channel package via optional `ChannelPush` capability | channels that can push (Telegram, Teams, webhook, SSE) implement `push(identity, result)`; channels that can't are only valid as `originating` targets |
| Per-delivery audit + replay state | Host core writes the intent + status onto the assistant `Message.additional_properties["hosting"]["deliveries"]`; provider opts into in-place updates via `SupportsDeliveryTracking` for crash-safe lifecycle | Universal data model; live update is provider capability. See [Delivery tracking on assistant messages](#delivery-tracking-on-assistant-messages). |
| Background-run lifecycle | Host core | owns `RunHandle` issuance, async execution, completion notification; stores via in-memory or pluggable store |
| Run poll routes | Channel package | each channel exposes its own protocol-shaped poll route (`/responses/v1/{run_id}`, `/invocations/{run_id}`) backed by `host.get_run(run_id)` |
| Conversation history (all channels — Responses, Invocations, Telegram, Teams, …) | Agent's core `HistoryProvider` (`agent_framework._sessions.HistoryProvider`) | Channels project their wire id (`previous_response_id`, `conversation_id`, request body `session_id`, host-tracked alias, …) into `ChannelSession.key`; the host resolves an `AgentSession` and the agent's `HistoryProvider` does the load / append. No channel-specific history seam. Multi-provider composition (with a single `load_messages=True`) is the standard AF convention; see [Conversation history for the Responses channel](#conversation-history-for-the-responses-channel) for the Foundry-backed variant. |
| Channel-owned non-message per-thread state (e.g. AG-UI `client_state`) | Channel-shipped `ContextProvider` subclass written into the same per-source state slot | Reuses the existing `ContextProvider` seam — *not* a new storage protocol. Channel reads `ChannelRequest.client_state` in `before_run`, lets the agent observe/mutate the slot, then reads the post-run value in `after_run` to emit channel-specific events (e.g. AG-UI `StateSnapshotEvent` / `StateDeltaEvent`). Composition rules unchanged (one `HistoryProvider` carries `load_messages=True`; additional `ContextProvider`s attach alongside). See [Channel-owned per-thread state](#channel-owned-per-thread-state). |
| Agent invocation | Host core | always through the target's execution seam — `SupportsAgentRun.run(...)` for agent targets, `Workflow.run(...)` for workflow targets |
| Protocol response/event model | Channel package | core returns agent results; channel serializes them |
| ASGI server bootstrap | Host core convenience | `host.serve(...)` for default uvicorn path; `host.app` for custom hosting |

### Channel session-carriage models

Channels split into two families based on **who owns the session identifier across requests**. This distinction is invisible to the agent target, but it changes which host-side mechanisms are load-bearing for that channel.

| Model | Examples | `ChannelSession.key` source | How a caller starts a new thread |
|---|---|---|---|
| **Caller-supplied session** | Responses (`previous_response_id` / `conversation_id`), Invocations, A2A, MCP — generally any HTTP/RPC-shaped channel | The wire payload carries it; the channel parses it into `ChannelSession.key`. `None` means "ephemeral / fresh thread". | Omit the previous id (or send a fresh one). The caller is in control. |
| **Host-tracked session** | Telegram, Teams, WhatsApp, Slack DM — generally any chat surface whose protocol carries identity (`chat_id`, AAD oid, `from.id`) but no per-conversation key | The channel leaves `ChannelSession.key = None` and lets the host's per-`isolation_key` alias decide which `AgentSession` to resolve (rule #8 below). | The channel surfaces a `/new`-style command (a `ChannelCommand`) that calls `host.reset_session(isolation_key)`; the host's session-id alias rotates. There is no in-band way for the user to address a specific past thread. |

Identity is an **orthogonal axis** (anonymous vs. identified). The realized cells in v1 are:

| | Anonymous | Identified |
|---|---|---|
| **Caller-supplied session** | ✓ — bare `curl /responses` + `previous_response_id`. The id effectively *is* the identity (the resolver may project `previous_response_id` into the `isolation_key` for that turn). | ✓ — Responses + `safety_identifier`, or any caller-supplied channel behind a JWT/OAuth bearer that the resolver maps to an `isolation_key`. |
| **Host-tracked session** | n/a in v1 | ✓ — Telegram/Teams/Slack/WhatsApp. The channel always authenticates; the resolver maps `(channel, native_id)` to `isolation_key`. |

**Channel-author guidance.** When implementing a new channel:

- If your upstream protocol carries a per-conversation identifier on every request, populate `ChannelSession.key` from it. You are a **caller-supplied** channel. `host.reset_session(...)` is **not** the right primitive for your `/new`-equivalent (your callers control that by simply omitting the previous id). Cross-channel linking via `IdentityLinker` is opt-in and depends on whether you also extract a stable identity (header, JWT, etc.) into `ChannelIdentity`.
- If your upstream protocol carries identity but **no** per-conversation key, leave `ChannelSession.key = None`. You are a **host-tracked** channel. To support "start a fresh thread", expose a channel-native command (Telegram `/new`, Teams adaptive-card button, …) that invokes `host.reset_session(isolation_key)` — the host alias rotation does the rest, and prior history remains addressable under its previous session id. You are the canonical case for cross-channel linking; populate `ChannelIdentity` faithfully so `IdentityLinker` and `ResponseTarget.active`/`.all_linked` can find your users.

**Mixing on one host.** A single `AgentFrameworkHost` can mount channels of both families. A user can chat on Telegram (host-tracked) and have it linked via `IdentityLinker` to a Responses-channel session keyed by `previous_response_id`; in that case the linker's identity merge collapses both sides onto the same `isolation_key` and the host-tracked channel's alias becomes a peer of the caller-supplied `previous_response_id` for the same `AgentSession`. This is the v1 mechanism for "agent built on Responses, exposed to humans on Telegram, with continuity across both".

### Session resolution rules

1. If `ChannelRequest.session_mode == "disabled"`, the host bypasses session resolution and calls the target with `session=None`.
2. If `session_mode == "auto"`, the host resolves `ChannelSession.key` to an `AgentSession`, scoped by `isolation_key` when supplied.
3. If `session_mode == "auto"` and no key is supplied, the host may create an ephemeral session.
4. If `session_mode == "required"`, the host must resolve or create a usable session before invoking the target.
5. **Cross-channel resolution rule:** when two channels mounted on the same `AgentFrameworkHost` produce the same `isolation_key` (and either both omit `key` or both produce equivalent keys derived from `isolation_key`), the host resolves them to the **same** `AgentSession`. This is the v1 mechanism for cross-channel chat continuity (e.g. Telegram → Teams against the same conversation history). The **canonical** path for translating a channel's native per-channel identifier (Telegram `chat_id`, Teams AAD object id, …) into the stable `isolation_key` is the host-level `IdentityResolver` (per-channel `run_hook` mapping is supported as a lower-level alternative). When the channel-native identity is not yet linked, the `IdentityLinker` runs a connect ceremony (OAuth, MFA, signed one-time code) to associate it with an existing `isolation_key`.
6. The first spec does **not** standardize a cross-package storage API; cross-host/cross-process continuity is deferred to the pluggable session store (req #23), which also persists identity-link grants beyond the host process lifetime.
7. Responses and other conversation-aware channels may still own protocol-specific conversation/item storage above this layer.
8. **Session rotation (`reset_session`).** The host exposes `reset_session(isolation_key)` so **host-tracked** channels (see [Channel session-carriage models](#channel-session-carriage-models)) can implement "start a fresh thread" commands (e.g. Telegram `/new`). The default behavior **rotates the active session id alias** (`<isolation_key>` → `<isolation_key>#<short-uuid>`) rather than deleting on-disk history: prior history remains addressable by its original session id while subsequent runs for that `isolation_key` resolve to a brand-new `AgentSession`. Apps that want destructive reset can layer that on top by calling into their own `HistoryProvider`. **Caller-supplied** channels do not call `reset_session`; their callers branch threads by sending a fresh / no `previous_response_id` (or equivalent) on the next request.

### Channel metadata persisted onto stored messages

When the host invokes the target, it does **not** pass the raw `ChannelRequest.input` directly. It first wraps the input into a `Message(role="user", contents=[...])` whose `additional_properties["hosting"]` carries an envelope describing where the message came from and where its response should go. This makes the resulting conversation history self-describing for any `HistoryProvider` (`FileHistoryProvider`, future Cosmos/Foundry providers, …) without that provider having to know anything channel-specific.

```jsonc
{
  "channel": "telegram",                       // ChannelRequest.channel
  "identity": {                                // populated from ChannelRequest.identity
    "channel": "telegram",
    "native_id": "<telegram-chat-id>",
    "attributes": { /* channel-specific */ }
  },
  "response_target": {                          // populated from ChannelRequest.response_target
    "kind": "originating",
    "targets": []                               // [(channel, native_id), ...] for explicit targets
  }
}
```

Round-trip is guaranteed by `Message.to_dict()` / `Message.from_dict()`. Future providers that key on protocol shape (e.g. a Responses `previous_response_id`-keyed store) can read this envelope to reconstruct cross-channel context without needing a separate channel-metadata sidecar.

`FoundryHostedAgentHistoryProvider` round-trips the entire `additional_properties["hosting"]` namespace (and any other AF-side namespace) through the Foundry response store via a single opaque `agent_framework` container key written onto each `OutputItem`. See [Foundry storage gap: `update_item`](#foundry-storage-gap-update_item) for the one part of the schema (post-push `deliveries[]` mutation) that depends on a service-side addition.

### Delivery tracking on assistant messages

The inbound envelope above captures **intent**. To support **audit** ("which destinations actually received this response, and when?") and **replay** ("Telegram was offline; resend to that user when it comes back"), the assistant `Message` produced by the host carries a parallel envelope that records the *resolved destination set* and per-destination outcome.

Schema on `Message.additional_properties["hosting"]` for a host-produced assistant message:

```jsonc
{
  "originating": {                                // mirror of the inbound envelope above
    "channel": "telegram",
    "identity": { "channel": "telegram", "native_id": "12345", "attributes": {} },
    "response_target": { "kind": "all_linked", "targets": [] }
  },
  "deliveries": [
    {
      "destination": { "channel": "teams", "native_id": "29:abc..." },
      "status": "delivered",                       // pending | delivered | failed | skipped
      "attempts": 1,
      "first_attempt_at": "2026-04-29T08:31:11Z",
      "last_attempt_at":  "2026-04-29T08:31:11Z",
      "last_error": null,
      "delivery_id": "msg_018f..."                 // channel-issued id, when the channel returns one
    },
    {
      "destination": { "channel": "telegram", "native_id": "12345" },
      "status": "failed",
      "attempts": 3,
      "first_attempt_at": "2026-04-29T08:31:11Z",
      "last_attempt_at":  "2026-04-29T08:36:11Z",
      "last_error": { "code": "channel_offline", "message": "Telegram getUpdates 502" },
      "delivery_id": null
    }
  ]
}
```

Status values:

| Value | Meaning |
|---|---|
| `pending` | Host has resolved the destination but has not yet attempted (or is between attempts) `ChannelPush.push(...)`. |
| `delivered` | Push succeeded. `delivery_id` is populated when the destination channel returns a stable id. |
| `failed` | Push raised. `last_error` is populated. Eligible for replay. |
| `skipped` | Destination was excluded by `LinkPolicy`, or the destination channel does not implement `ChannelPush`. Recorded so audit shows *why* a destination resolved by `ResponseTarget` did not receive the message. |

Lifecycle the host follows:

1. After `ResponseTarget` resolution and `LinkPolicy` filtering, **before** any push attempt, the host writes the assistant `Message` with one `deliveries[]` entry per destination, all `status="pending"` (excluded ones written as `"skipped"`). This guarantees the intent is durable across host crashes.
2. After each `ChannelPush.push(destination_identity, result)`, the host updates the matching `deliveries[]` entry in place — `status`, `attempts`, `first_attempt_at` (set on first attempt), `last_attempt_at`, `last_error`, `delivery_id`.
3. The mechanism for **retrying** failed deliveries (background worker, operator action, `host.retry_delivery(message_id, destination)`, …) is **out of scope** for this spec — it is enabled by the data model and tracked under Open Questions.

#### `SupportsDeliveryTracking` provider capability

Updating a stored message in place is provider-specific. The shape above is universal; the *update semantics* are opt-in:

```python
from typing import Protocol, Sequence

class SupportsDeliveryTracking(Protocol):
    async def update_deliveries(
        self,
        *,
        session_id: str,
        message_id: str,
        deliveries: Sequence[Mapping[str, Any]],
    ) -> None: ...
```

| Provider | `SupportsDeliveryTracking`? | Behavior |
|---|---|---|
| `FileHistoryProvider` (append-only JSONL) | No (capability not implemented) | Host writes the assistant `Message` **once**, at the end of the delivery cycle, with terminal `deliveries[]`. Pre-attempt `pending` snapshot is not durable; a host crash mid-delivery loses per-destination state for in-flight pushes. **Audit-complete, replay-best-effort.** |
| `FoundryHostedAgentHistoryProvider` (Foundry response store) | **Partial — initial-write only** (see [Foundry storage gap](#foundry-storage-gap-update_item) below) | Inbound envelope (`channel`/`identity`/`response_target`) and **initial-write `deliveries[]` snapshot** (all `pending`, plus any `skipped`) round-trip through the Foundry response store unchanged via the `agent_framework` extras container key the provider writes onto each `OutputItem`. **Per-destination updates after each push attempt are not durable** because the Foundry storage SDK does not yet expose a way to mutate an individual stored history item. Behaves as `FileHistoryProvider` in that regard until the [service ask](#foundry-storage-gap-update_item) lands. **Audit-complete-on-write, replay-best-effort.** |
| Cosmos / SQL providers (when introduced) | Expected to implement | Same as above. |

Providers that omit the capability are still valid hosts for any `ResponseTarget` configuration — they just cannot offer durable replay. The host detects the capability with `isinstance(provider, SupportsDeliveryTracking)` and degrades to write-once when absent.

> **Why on the message and not in a separate delivery log?** Two reasons. First, the message store is the single source of truth for an assistant turn; piggy-backing on it avoids a second consistency boundary between "message written" and "delivery scheduled". Second, any operator who wants a queryable delivery dashboard can ETL the array out of `additional_properties["hosting"]["deliveries"]` into their preferred outbox/log store — the on-message form does not preclude that. The spec commits only to the on-message shape; outbox layers are an implementation choice.

#### Foundry storage gap: `update_item`

`FoundryHostedAgentHistoryProvider` round-trips arbitrary `Message.additional_properties` namespaces through the Foundry response store as opaque JSON via a single `agent_framework` container key on each `OutputItem` (see `_shared.py:_collect_af_extras` / `_inject_af_extras` / `_attach_extras`). This makes the **initial-write** parts of the schema above durable:

- The inbound `hosting` envelope (`channel`, `identity`, `response_target`) on user messages.
- The initial-write `deliveries[]` snapshot on assistant messages (all entries `pending` or `skipped`, written before the first push attempt).

What is **not yet** durable through this provider is **post-push mutation** of an individual stored item. The `azure.ai.agentserver.responses.store.FoundryStorageProvider` SDK exposes `create_response`, `get_response`, `update_response`, `delete_response`, `get_input_items`, `get_items`, and `get_history_item_ids` — but no `update_item` / PATCH on a single history item. So when the host updates an entry in `deliveries[]` after `ChannelPush.push()` returns (`status` → `delivered`/`failed`, `attempts`, timestamps, `last_error`, `delivery_id`), there is no way to push that mutation back into the per-item storage row.

**Workarounds and trade-offs:**

| Option | Trade-off |
|---|---|
| Encode `deliveries[]` on the *response object* (under `agent_framework`) instead of the assistant *item*, and use `update_response` to mutate it. | Works today, but deliveries are no longer co-located with the assistant message — schema for the `Message` round-trip becomes provider-specific. |
| Delete + recreate the assistant item with the updated body. | Likely loses the `previous_response_id` chain pointer, breaks subsequent `get_history_item_ids` walks, and re-stamps the storage `id` (audit-trail noise). |
| Wait for Foundry storage to add `update_item`. | Cleanest end-state. **This is the recommended path.** |

**Service ask for the FoundryHostedAgent / Foundry response store team:**

- Add `update_item(item_id, item_body, *, isolation: IsolationContext | None = None) -> None` (PATCH semantics) to `azure.ai.agentserver.responses.store.FoundryStorageProvider` and the underlying `POST/PATCH /storage/items/{item_id}` REST surface.
- Required because the Hosting spec's per-destination delivery-tracking lifecycle (`pending → delivered`/`failed`/`skipped`) needs to mutate an individual stored item after the first push attempt completes.
- Without it, the FoundryHostedAgentHistoryProvider's `SupportsDeliveryTracking` implementation is permanently stuck at "write-once-best-effort" and durable replay through Foundry storage is unreachable.
- Existing `update_response` is not sufficient because deliveries belong on the **assistant `Message`** (so they round-trip with the message into any provider that consumes the standard `Message` schema), not on the response envelope.

## Reference and Parity Plan

The new core sits **below** the conceptual boundary of today's top-level Responses/Invocations host wrappers but is implemented in Agent Framework-owned code. Existing `agentserver`-based hosts inform behavior, naming, and parity targets — **without** becoming runtime dependencies.

| Existing code area | Proposed treatment | Why |
|---|---|---|
| `SupportsAgentRun.run(..., session=..., stream=...)` | Reuse directly in core for agent targets | Already the correct Python execution seam |
| `Workflow.run(...)` and workflow streaming events | Reuse directly in core for workflow targets; normalize outputs into `HostedRunResult`/`HostedStreamResult` | Lets channels stay target-agnostic |
| Session resolution logic in current hosting layers | Implement in core, using current behavior as reference | Host behavior, not protocol behavior |
| Starlette app assembly and route aggregation | Implement in core, referencing current servers | Needed by every channel |
| PR #5393 Telegram `BOT_COMMANDS`, `CommandHandler(...)`, `set_my_commands(...)` | Reference for the generic `ChannelCommand` capability | Clearest current prior art for native command catalogs + runtime dispatch |
| `agent_framework_foundry_hosting._to_chat_options` | Inspiration for Responses channel-owned mapping | Still protocol-specific |
| `agent_framework_foundry_hosting._items_to_messages` / `_output_item_to_message` | Inspiration / parity reference in Responses channel codec | Useful, not generic hosting |
| `agent_framework_foundry_hosting._to_outputs` and `ResponseEventStream` | Inspiration for Responses event mapping; do not depend on `agentserver` builders | Responses-specific serialization |
| `azure.ai.agentserver.responses.ResponseContext.get_history()` + `Store` | Folded into the agent's normal core `HistoryProvider` flow. The Responses channel projects `previous_response_id` / `conversation_id` into `ChannelSession.key`; the agent's `HistoryProvider` does the load / append exactly as for any other session. No Responses-specific history Protocol. | One uniform history seam across channels — the developer chooses where to store, and may compose multiple providers under the standard "single `load_messages=True`" rule. |
| `azure.ai.agentserver.responses.store._foundry_provider.FoundryStorageProvider` (HTTP-backed Foundry storage with `IsolationContext` user/chat headers) | Port to a native `FoundryHistoryProvider` in `agent-framework-foundry` implementing the standard core `HistoryProvider` Protocol. Agents attach it the same way they attach `FileHistoryProvider`. | Lets the Foundry response store back conversations driven through the new host without an `agentserver` runtime dependency, while keeping the channel agnostic to the storage backend. Same provider also works for non-Responses channels (Telegram, Invocations, …) so the choice is "where do I want history persisted" rather than "which channel am I exposing". |
| `agent_framework_foundry_hosting._invocations.InvocationsHostServer._sessions` (in-process `dict[str, AgentSession]`) | Replace with the host's normal `ChannelSession.key → AgentSession` resolution; agent history flows through its own (optional) core `HistoryProvider(load_messages=True)` | Invocations does **not** need a protocol-shaped history seam — confirmed by today's foundry hosting which keeps no `Store` on the Invocations side |
| `ResponsesAgentServerHost` / `InvocationAgentServerHost` top-level wrappers | Conceptual prior art only | Sit too high; encode protocol ownership |
| Workflow checkpoint behavior in current Responses hosting | Defer; reference only for future work | Needs separate design if it becomes shared |

## Dependencies & Commitment Status

| Dependency | Team | DRI | Status |
|---|---|---|---|
| `SupportsAgentRun` execution seam | Agent Framework Core (Python) | TBD | Committed (existing) |
| `Workflow` execution seam | Agent Framework Core (Python) | TBD | Committed (existing); host wraps workflow outputs into `HostedRunResult`/`HostedStreamResult` |
| `AgentSession` / conversation primitives | Agent Framework Core (Python) | TBD | Committed (existing); cross-package storage standardization deferred |
| Starlette | External (BSD-licensed) | n/a | Committed; required runtime dep of `agent-framework-hosting` |
| Uvicorn | External (BSD-licensed) | n/a | Open Question — required dep vs optional extra (see Open Questions) |
| `agent-framework-foundry-hosting` parity reference | Agent Framework Hosting | TBD | Reference-only, no runtime dependency |
| `FoundryHistoryProvider` port (from `azure.ai.agentserver.responses.store._foundry_provider` → `agent-framework-foundry`) | Agent Framework Foundry | TBD | Proposed v1 deliverable so Foundry-defined (and any other) agents can use Foundry's response store as a `HistoryProvider` through the new host without an `agentserver` runtime dep. Implements the standard core `HistoryProvider` Protocol — usable from any channel, no Responses-specific Protocol. |
| PR #5393 Telegram sample (commands, polling/webhook patterns) | Agent Framework | PR author | Reference-only; informs `ChannelCommand` and `TelegramChannel` design |
| Telegram Bot API SDK | External | n/a | Committed (runtime dep of `agent-framework-hosting-telegram`) |
| `agent-framework-ag-ui`, `-a2a`, `-devui` | Agent Framework | various | Out of scope for first implementation; future convergence kept as a possibility |

## Open Questions

| # | Question | On Point | Notes |
|---|---|---|---|
| 5 | How much of the Responses Conversations API should the Responses channel own vs a future shared conversation utility? | Eng / PM | Tied to whether session storage gets standardized. |
| 6 | Should a later phase define a pluggable session store interface? | Eng | Needs to be designed **holistically across all storage axes** — sessions, messages, identity links, run-state / continuation tokens, workflow checkpoints — rather than per-axis. Tracked as v1 fast-follow / requirement #23. |
| 8 | Should command scopes / projection metadata become first-class — e.g. private-chat-only vs group-chat-visible commands, or per-locale descriptions? | Eng / PM | Telegram's `BotCommandScope` and `language_code` would need to be representable cross-channel. |
| 10 | Is "Channel" the GA name? "Head" was used interchangeably during design discussions. | PM | "Channel" chosen for the spec; confirm before public docs. |
| 12 | Should `ChannelRequest.session_mode` grow additional values (e.g. `"shared"` for multi-channel session sharing) or stay closed at three? | Eng | The taxonomy needs a **dedicated design exercise** covering all known channel session-shape patterns; revisit after that exercise. |
| 14 | Where do issued link grants live — short-lived in-memory state on the host, the same pluggable session store (#23), or a separate identity store? | Eng | For v1, link grants are written to **files** — files in hosted agents are persisted and isolated, which is good enough. Replace with the holistic store from Q6 / #23 when it lands. |
| 17 | Should `ResponseTarget.active` honor a configurable **time window** (last seen within N minutes) and what is the fallback when the window has expired before the response is ready — `originating`, `all_linked`, drop with `RunHandle.failed`? | PM / Eng | Likely yes with sensible default (e.g. 24h fall back to `originating`); per-request override via the run hook. |
| 22 | For the Responses WebSocket transport, what subprotocol identifier (if any) should be advertised on the `Upgrade` and how is auth conveyed — `Authorization` header on the upgrade, a `Sec-WebSocket-Protocol` token, or a query-string-bound short-lived token? | Eng / PM | Aligning with whatever OpenAI ships for Responses WS is preferable; keep the codec swappable so the channel can track upstream changes without breaking the host contract. |
| 27 | What is the retention contract for completed `deliveries[]` entries — keep forever for audit, GC after the message itself ages out, or cap per-message at a fixed attempt count? Should `last_error` payloads be redacted to a code/message pair to avoid logging PII from the underlying channel SDK? | Eng / Compliance | Suggest "lifetime equals message lifetime" + redacted error shape (`{code, message}` only, no provider stack frames or payload echoes) as the default; revisit when the persistent store contract lands. |

### Resolved Questions (decisions log)

Original numbering preserved so external references (checkpoints, ADR cross-links) still resolve. Decisions captured here may imply spec-body changes elsewhere — see [Decisions-driven follow-ups](#decisions-driven-follow-ups) below.

| # | Question | Decision |
|---|---|---|
| 1 | Final distribution package names? | `agent-framework-hosting` with suffixes (`-responses`, `-invocations`, `-telegram`, …). Public imports stay at `agent_framework.hosting`. |
| 2 | `uvicorn` required vs optional extra? | Use **hypercorn** instead of uvicorn; the `serve` extra remains optional. `host.app` is still the canonical server-agnostic ASGI surface. |
| 3 | Keep `HostedRunResult` wrapper or return `AgentResponse` directly? | **Keep `HostedRunResult`.** It wraps both `AgentRunResult` *and* the unknown output type of a `Workflow`, and adds host-run metadata (resolved session, etc.). |
| 4 | Where do generic auth helpers live? | Only the **mechanisms** live in core. Concrete implementations sit in their own packages when they pull dependencies; dep-free helpers may live in `hosting`. |
| 7 | `protocol_request` typed (`Any`) or typed kwargs? | **Keep `Any`.** |
| 9 | Allow nested routers / `path=""`? | **Yes.** The host developer is responsible for ensuring routes do not overlap. |
| 11 | Should the host support multiple targets? | **No** — final. Solve a layer above (an external router that owns multiple single-target hosts). |
| 13 | Which identity linkers ship in phase 1? | **Entra linker** (in the Entra package) + **one-time-code linker** (in core). Drop MFA for now; investigating additional linkers tracked as a follow-up. |
| 15 | Identity resolver invoked once on host vs per channel? | **Once on the host** with `ChannelIdentity(channel, native_id, ...)`. |
| 16 | Should `IdentityLinker` and `Channel` share a base `Contributor` protocol? | **A linker *is* a Channel — specialised.** Use the single Channel-shaped contract; collapse `IdentityLinker` into a Channel specialisation. |
| 18 | Contract for `ChannelPush` failures? | **Annotate the failure on the relevant `deliveries[]` entry** in the data model (see §"Delivery tracking on assistant messages"). Re-delivery is future work (Q26). |
| 19 | `host.run_in_background(...)` `notify` callback? | Programmatic non-channel delivery will be expressed via the **`continuation_token`** mechanism (see Q20), not a separate `notify` callback. |
| 20 | Storage / TTL of `RunHandle`s? | Rename `RunHandle` → **`continuation_token`** and store as "regular" messages — this already exists for the Responses channel; **add equivalent support to the Invocations channel.** Push-capable channels can still use it; default behaviour remains "push on completion", but the developer can choose other UX (poll-after-push, hybrid, …). |
| 21 | Partial-failure surfacing for `all_linked`? | **Handled by the `deliveries[]` array** in the data model, updated per-destination as each push attempt completes. |
| 23 | Share one backing store contract for host-level vs `ContextProvider`? | **Stay separate protocols** (current draft direction confirmed). A deployment may still bind both onto the same physical backend. |
| 24 | Where does the Foundry history provider live? | Tentative name **`FoundryHostedAgentHistoryProvider`**, in the **`foundry-hosting`** package (shares the dependency). Confirm with Foundry package owners before launch. |
| 25 | `Channel.confidentiality_tier` opaque vs enum? | Keep as `str?` for now; can revisit before Release. |
| 26 | Where does the delivery-replay mechanism live? | **In the Host**, but **out of scope for v1.** The on-message `deliveries[]` envelope is sufficient input for any future replayer. |

### Decisions-driven follow-ups

The following resolutions imply prose / API edits elsewhere in the spec body (not just the table above). Captured here so they aren't lost; the edits themselves are deferred to a separate pass.

- **Q2** — Switch all install / `host.serve()` references from `uvicorn` to `hypercorn`.
- **Q3** — Update `HostedRunResult` documentation to cover the workflow-output case and the host-run metadata it adds on top of `AgentRunResult`.
- **Q11** — Strip any remaining "multi-target hedge" language from the spec body.
- **Q13** — Update the linker catalogue: Entra (in Entra package) + one-time-code (in core); remove MFA references.
- **Q16** — Collapse `IdentityLinker` into a Channel specialisation in the spec body (architecture diagrams, contracts, examples).
- **Q20** — Rename `RunHandle` → `continuation_token` throughout the spec; document the addition of continuation-token support to the Invocations channel; document the developer-controlled push UX choices.
