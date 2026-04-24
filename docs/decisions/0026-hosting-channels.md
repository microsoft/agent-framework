---
status: proposed
contact: eavanvalkenburg
date: 2026-04-24
deciders: eavanvalkenburg
---

# Agent Framework hosting core with pluggable channels

## What are the business goals for this feature?

Give Agent Framework app authors — in every supported language — one low-level hosting surface that can expose a single **hostable target** (an agent or a workflow) on **one or more channels** (Responses API, Invocations API, Telegram, future WhatsApp/Teams, custom webhooks) without requiring them to hand-build protocol routing or server glue per protocol, **and** let an end user start a conversation on one channel (e.g. Telegram on their phone) and seamlessly continue it on another (e.g. Teams at their desk) against the same target and the same conversation history.

This consolidates the protocol-specific hosting layers that exist today (in Python: `agent-framework-foundry-hosting`, `-ag-ui`, `-a2a`, `-devui`; in .NET: the analogous per-protocol hosting helpers) into a shared composable model where:

- a host owns the application object and channels own protocol shape,
- the host's hostable target may be an **agent** (executed via the per-language agent execution seam) **or** a **workflow** (executed via the per-language workflow execution seam) — channels do not care which, because the channel's `invocation_hook` adapts the inbound `ChannelRequest` into the input shape the target needs, and
- session identity is **channel-neutral** — the host resolves a session from a channel-supplied `isolation_key` (e.g. a stable user identity) so two channels mounted on the same host can resolve to the **same** session for the same end user, and a shared session store extends that continuity across hosts and processes.
- channel-native identity is **mapped, not assumed** — every channel has its own user namespace (Telegram `chat_id`, Teams AAD object id, WhatsApp phone number, Slack user id, …). The host provides a first-class **identity resolver** seam that maps a channel-native identifier into the channel-neutral `isolation_key`, and a first-class **identity linker** seam that lets an end user **connect** a new channel to an existing `isolation_key` through a well-known mechanism (OAuth, MFA, signed one-time code, …) so cross-channel continuity is achievable without ad-hoc per-channel bookkeeping, and
- **response delivery is decoupled from request origin** — a target's response can be routed back to the **originating** channel (default), the user's **active** channel (the channel most recently observed for that `isolation_key`), a **specific** channel, **all linked** channels (fan-out), or **none** (background). Background/asynchronous runs are first-class: a channel can kick off a run, return a `RunHandle` to the caller, and the response is delivered when the user is next observed on any (or a chosen) channel — so a user can start a long task on Telegram and pick up the result on Teams.

We know we're successful when:

- after the target is created, a basic multi-channel sample requires only one host, channel objects, and one start call — no handwritten protocol routes, no per-protocol server bootstrap, and no dependency on legacy protocol-specific hosts (e.g. Python's `agentserver`) for new channel packages,
- the same host construction works whether the target is an agent or a workflow — only the `invocation_hook` (channel-default or app-supplied) changes to adapt the input,
- a single host configured with two channels (e.g. Telegram + a future Teams channel) can be exercised by one end user across both channels and observe one continuous conversation, **and**
- the same conceptual model applies in Python and .NET.

## Problem Statement

### How do developers solve this problem today?

Today, every protocol surface is its own integration package with its own server. A developer who wants to expose one agent over both the Responses API and a webhook channel has to stand up two separate hosts and stitch them into one application by hand. In Python that means manually mounting two `agentserver`-based hosts into a Starlette app and calling `uvicorn.run(...)`. In .NET it means composing two protocol-specific hosting helpers into one `WebApplication` and wiring middleware twice.

Adding a Telegram bot to the same agent today means leaving the hosting stack entirely: spinning up a separate process, installing a Telegram SDK, writing the polling/webhook loop, manually translating updates into agent calls, and wiring command handlers (`/start`, `/new`, `/cancel`, …) and native command registration (`set_my_commands(...)`) by hand — none of which is reusable across other message channels (Teams, WhatsApp, …) or across languages.

### Why does this problem require a new hosting abstraction?

The gap is between **owning a hostable target** (an agent or a workflow) and **operationalizing it on multiple channels**. Agent Framework already provides agents, workflows, sessions, run inputs, response/update streaming, and per-language execution seams (`SupportsAgentRun.run(...)` and the workflow execution seam in Python; `AIAgent.RunAsync(...)` and the workflow execution seam in .NET). What's missing is a generic host that:

1. Owns one application object and one set of lifecycle hooks per language.
2. Lets channels contribute routes, middleware, commands, and startup/shutdown without protocol leakage into the host.
3. Standardizes how protocol requests become target invocations (input, options, session, streaming) and how target results flow back out — independent of whether the target is an agent or a workflow.
4. **Resolves a session from a channel-neutral `isolation_key`** so two channels mounted on the same host can converge on the same session for the same end user — enabling cross-channel chat continuity (start on Telegram, continue on Teams) without per-channel session bookkeeping.
5. **Bridges channel-native identities into the shared `isolation_key` namespace** — every channel has its own user identifier (Telegram `chat_id`, Teams AAD object id, WhatsApp phone, Slack user id). The generic host needs (a) an **identity resolver** seam that maps a channel-native id to an `isolation_key` for already-known users, and (b) an **identity linker** seam that lets an end user **connect** a new channel to an existing `isolation_key` through a well-known mechanism (OAuth, MFA, signed one-time code) — without each channel reinventing the linking flow.
6. Provides a first-class extension seam for webhook/message channels with native command catalogs (per PR #5393 Telegram sample).
7. Treats the **invocation hook** as the adapter between a channel's default `ChannelRequest` and the input shape the target needs — the same hook seam that adapts `temperature`/`store` for Responses also adapts a chat message into the typed inputs of a workflow.
8. Treats **response delivery** as a first-class, configurable concern — by default the response goes back to the originating channel synchronously, but the host must support routing the response to a different channel (the user's most recently active channel, a specific channel, or all linked channels) and **background runs** where the request returns immediately with a `RunHandle` and the response is delivered later via a channel push when the user is next observed (or polled by the caller).
9. Applies the same conceptual model across language ecosystems so concepts, terminology, and behavior transfer between teams and docs.

The current protocol-specific hosts (e.g. `ResponsesAgentServerHost`, `InvocationAgentServerHost`) are valuable prior art but sit too high in the stack — they encode protocol ownership at the host level and are duplicated per language. A generic core can learn from their behavior without depending on them.

## Non-Goals / Relationship to existing hosting packages

The hosting core is deliberately **not** a replacement for the existing protocol packages in their first form, and it is not a multi-agent router. It is a peer abstraction layer that lets future protocol packages share one host.

| Dimension | Existing protocol packages | Hosting core |
|---|---|---|
| **Mental model** | One package = one protocol surface, owns its own server | One host owns the app; channels plug protocols in |
| **Scope** | Protocol-specific request/session/event mapping | Generic host + channel contract; protocol logic lives in channel packages |
| **Composition** | One protocol per process or per Mount | Many channels per host, shared middleware, lifecycle, session resolution |
| **Multi-agent** | Out of scope per package | **No.** One host = one agent. Future work. |
| **Cross-language** | Per language, per protocol | Same conceptual model in every implementing language |

**Explicit non-goals:**

- Migrating existing protocol packages (AG-UI, A2A, DevUI in Python; analogous .NET helpers) onto the new core in the first implementation.
- Standardizing a persistent session storage contract across all channels in the first phase. (Cross-channel continuity within one host is enabled by `isolation_key` resolution; cross-host/cross-process continuity requires the pluggable session store, listed as a fast follow.)
- Hosting multiple agents behind one router in this first design.
- Designing every detail of WhatsApp, Teams, or Bot Framework payloads now (only Telegram is concretely targeted, informed by PR #5393).
- Replacing protocol-specific serializers with one generic event model.
- Taking a runtime or package dependency on legacy protocol-specific hosts (e.g. `agentserver` in Python) in the new hosting core or its new channel packages.
- Forcing identical type names across languages — each language follows its own idioms while preserving the same concepts and terminology.

**Boundary rule:** If you need protocol-specific event semantics, codecs, or signature validation, that lives in the channel package. The host owns the application object, lifecycle, session resolution, and the call into the agent's run/stream seam.

## Decision Drivers

- Keep the app author experience simple for the common case (one host, channels, one start call).
- Support one host exposing one **hostable target** (agent or workflow) on multiple channels at once.
- Treat agents and workflows as peer hostable targets behind one host, so the same channel ecosystem (Responses, Invocations, Telegram, Teams, …) can serve either without rework.
- **Enable cross-channel chat continuity** — two channels on the same host can resolve to the same session for the same end user via a channel-neutral `isolation_key`, with a pluggable session store enabling continuity across hosts and processes as a follow-up.
- **Bridge channel-native identity into the shared `isolation_key` namespace** — provide first-class identity resolution and identity linking seams so channels never invent their own linking flow and end users have a well-known way (OAuth, MFA, signed one-time code) to connect a new channel to an existing identity.
- **Make response delivery a first-class concern** — decouple where a response is delivered from where the request originated, support routing to the originating, active, specific, all, or no channels, and elevate background/asynchronous runs to a first-class capability so a user can start a request on one channel and pick up the result on another (or via polling).
- Preserve room for channel-specific capabilities (signature validation, conversations, streaming, native commands, action surfaces).
- Support message-channel capabilities — native commands, command menus, action surfaces — from the start.
- Support channels that need startup/shutdown behavior (long polling, platform-side command registration) in addition to routes.
- Use the existing protocol-specific implementations as prior art **without** taking a runtime dependency on them.
- Keep the new core protocol-agnostic.
- Align to the per-language agent **and workflow** execution seams rather than introducing a new contract for the target.
- Follow each language's idiomatic packaging conventions rather than growing a monolithic integration package.
- Avoid forcing migration of existing protocol packages as part of the first implementation.
- Keep the abstractions language-neutral so the same conceptual model can be implemented by Python, .NET, and future language ecosystems with idiomatic code.

## Considered Options

- Keep the current protocol-specific hosting packages only.
- Create one monolithic `hosting` package with the host and all channels built in.
- Create a new hosting core plus new channel packages, but reimplement the channel stack from scratch with no reference to the current protocol implementations.
- Create a new hosting core plus separate channel packages, informed by the current protocol-specific implementations but without depending on them.

## Decision Outcome

Chosen option: **Create a new hosting core plus separate channel packages, informed by the current protocol-specific implementations but without depending on them.** Apply the same conceptual model in Python and .NET, with idiomatic per-language API shapes.

### Summary

We will introduce a new hosting core distribution package per language, exposing the same conceptual abstractions:

- **Host** (`AgentFrameworkHost`) — owns one **hostable target** (an agent or a workflow), builds one application using the language's idiomatic web framework (Starlette in Python, ASP.NET Core / Kestrel in .NET), exposes the underlying app as the canonical portability surface, and offers a `serve(...)`-style convenience for the common single-process case. The host is named `AgentFrameworkHost` rather than `AgentHost` because the target is not restricted to agents.
- **Hostable target** — the executable object the host is fronting. May be:
  - an **agent** invoked via the per-language agent execution seam (`SupportsAgentRun.run(...)` / `AIAgent.RunAsync(...)`), or
  - a **workflow** invoked via the per-language workflow execution seam.
  The host detects the target kind and routes to the appropriate runner. Channels are unchanged; the `invocation_hook` is the seam where channel-default `ChannelRequest` data is adapted to the target's input shape.
- **Channel** — contributes routes plus optional middleware, command metadata, and lifecycle (startup/shutdown) hooks. One channel = one external protocol surface.
- **ChannelContext** — host-owned bridge from a channel into the target's run/stream invocation. Surfaces a uniform `run`/`stream` API regardless of whether the underlying target is an agent or a workflow.
- **ChannelRequest** and **ChannelSession** — normalize inbound channel data without introducing a new message model. Channels still translate into the framework's existing input, session, message, and content types in each language. `ChannelSession.isolation_key` follows hosted-agent terminology for isolation rather than assuming a direct user ID.
- **ChannelInvocationHook** — gives each channel a sensible default request-to-target mapping while letting app authors rewrite or validate per-request invocation behavior **before** the target is invoked. This hook is the **adapter** between the channel's default `ChannelRequest` and the target's required input shape — central to workflow hosting because workflows usually take typed inputs rather than free-form chat messages.
- **IdentityResolver** — host-level seam that maps a channel-native identifier (Telegram `chat_id`, Teams AAD object id, WhatsApp phone, …) into an `isolation_key`. Channels publish the native identifier they observed; the resolver decides what the channel-neutral identity is. Default: identity (use the native id verbatim, scoped per channel).
- **IdentityLinker** — host-level seam that runs a **link/connect ceremony** to associate a new channel-native identity with an existing `isolation_key`. The linker contract is generic enough to host well-known mechanisms — OAuth authorization-code redirect, MFA challenge, signed short-lived one-time code issued from one channel and entered in another — without baking any specific provider into the core. The host exposes the route(s) and lifecycle the linker needs; channels surface `link`/`connect` commands or buttons that drive the ceremony.
- **ResponseTarget** and **ChannelPush** — describe **where** a response should be delivered when it's ready. Each `ChannelRequest` carries a `response_target` (default: `originating`; alternatives: `active`, a specific channel id, a list of channels, `all_linked`, or `none` for fully-detached background runs). When the response target isn't the originating channel — including all background runs — the host delivers via a `ChannelPush` capability the destination channel exposes (proactive message, webhook push, server-sent event broadcast, …). Channels that cannot push (pure request/response protocols like Responses) are valid targets only for `originating`.
- **RunHandle** — first-class artifact returned for background runs. Carries a stable run id, status (`queued` | `running` | `completed` | `failed`), and the resolved isolation key. Channels can return it directly in their protocol response (e.g. an Invocations 202 with a polling URL, a Telegram inline acknowledgement) so the caller can poll later; the host also pushes the result to the configured response target when ready. The host owns the run-handle store; mechanism for persistence is the same one used for sessions (pluggable, fast follow).
- **Active channel** — the channel most recently observed for a given `isolation_key`. The host tracks last-seen `(isolation_key, channel)` per request so `response_target="active"` resolves to whichever channel the user is currently using. Heuristic, not authoritative — apps can override on the request via the invocation hook.
- **ChannelCommand** — gives message channels a portable way to describe native commands or actions, projected into Telegram menus, Teams slash commands, WhatsApp action surfaces, or text-command dispatch.
- **Built-in channels** — own their protocol-defined relative routes under default mount roots, so default surfaces become e.g. `/responses/v1`, `/invocations/invoke`, and `/telegram/webhook` without the app author spelling those out.

Channel implementations live in **separate distribution packages**, one per channel, with public surfaces kept stable per language.

| Concept | Python (proposed) | .NET (proposed) |
|---|---|---|
| Core | `agent-framework-hosting` → `agent_framework.hosting` | `Microsoft.Agents.AI.Hosting` |
| Responses channel | `agent-framework-hosting-responses` → `agent_framework.hosting.ResponsesChannel` (lazy) | `Microsoft.Agents.AI.Hosting.Responses` |
| Invocations channel | `agent-framework-hosting-invocations` → `agent_framework.hosting.InvocationsChannel` (lazy) | `Microsoft.Agents.AI.Hosting.Invocations` |
| Telegram channel | `agent-framework-hosting-telegram` → `agent_framework.hosting.TelegramChannel` (lazy) | `Microsoft.Agents.AI.Hosting.Telegram` |

Each language follows its own conventions:

- Python keeps the public import path stable at `agent_framework.hosting` via lazy imports.
- .NET keeps the public namespaces stable per package, following existing `Microsoft.Agents.AI.*` conventions.

The new hosting core and its channel packages **must not** take a dependency on legacy protocol-specific hosts; those are prior art and parity reference only.

The initial design target, in every implementing language, is:

- any execution-seam-compatible target (not just the concrete `Agent`/`ChatClientAgent`),
- built-in channel designs for Responses and Invocations,
- a documented authoring model for webhook/message channels, including a first detailed Telegram design,
- conceptual alignment with existing protocol packages but no implementation or migration requirement for those in the first phase.

### Conceptual API shape

The top-level user experience should look the same conceptually in every language: compose one host with one agent and a list of channels, then start it. The channel-authoring seam should follow each language's idioms while preserving the same concepts.

| Concept | Python idiom | .NET idiom |
|---|---|---|
| Define a host | `AgentFrameworkHost(target, channels=[...])` (target = agent or workflow) | `AgentFrameworkHostBuilder` / `AddAgentFrameworkHost(target, ...)` on the host builder |
| Canonical app surface | `host.app` (Starlette `Starlette`) — supports HTTP **and** WebSocket scopes via ASGI | `WebApplication` (ASP.NET Core) — supports HTTP **and** WebSocket via `app.UseWebSockets()` / `MapWebSocket(...)` |
| Convenience start | `host.serve(host=, port=)` (lazy `uvicorn`) | `host.RunAsync()` (Kestrel) |
| Channel contract | `Channel` Protocol with `contribute(context) -> ChannelContribution` | `IChannel` interface with `Contribute(IChannelContext)` returning `ChannelContribution` |
| Per-request hook | `ChannelInvocationHook = Callable[[ChannelInvocationContext], ...]` | `Func<ChannelInvocationContext, ValueTask<ChannelRequest>>` / delegate |
| Identity resolver | `IdentityResolver = Callable[[ChannelIdentity], str \| None]` | `IIdentityResolver` (returns `isolation_key`) |
| Identity linker | `IdentityLinker` Protocol with `begin(...)` / `complete(...)` plus `routes()` for callback / verification endpoints | `IIdentityLinker` interface with begin/complete + route contributions |
| Response routing | `ChannelRequest.response_target = ResponseTarget.originating \| .active \| .channel("teams") \| .all_linked \| .none`; channels expose `ChannelPush` if they can deliver proactively | `ChannelRequest.ResponseTarget` discriminated union; `IChannelPush` interface for proactive delivery |
| Background runs | `RunHandle` returned by `host.run_in_background(request)`; channels may return it as their protocol response and/or expose a poll route | `RunHandle` record + `IRunHandleStore` for persistence |
| Command descriptor | `ChannelCommand` dataclass | `ChannelCommand` record |
| Lifecycle | `on_startup` / `on_shutdown` callables | `IHostedService` integration / explicit lifecycle delegates |

Built-in channels own the default mapping from each protocol's request model into a `ChannelRequest`, **and** expose a per-request invocation-hook seam so app authors can validate or rewrite invocation behavior before the host invokes the agent.

The full Python API surface — exact types, fields, default routes, code samples — is specified in the companion Python spec. A future .NET spec captures the .NET-idiomatic API surface for the same model.

## Terminology

These terms are language-neutral and shared between Python and .NET implementations. Each language realizes them with idiomatic types and naming.

- **Host**: The object that owns one application, one execution-seam-compatible target, and a sequence of channels. Provides the underlying app object (canonical portability surface) and a convenience start method.
- **Channel**: A pluggable component that contributes routes (HTTP and/or WebSocket), middleware, commands, and lifecycle hooks to a host. One channel = one external protocol surface. Used interchangeably with "head" in earlier discussions; **Channel** is the canonical name.
- **`ChannelRequest`**: The host-neutral, normalized invocation envelope produced by a channel before the host invokes the agent. Carries input, options, session hint, `session_mode`, and channel-specific attributes.
- **`ChannelSession`**: A small session hint with a stable lookup key, an optional protocol-visible conversation/thread identifier, and an opaque `isolation_key`. The host resolves it into a framework session; storage specifics are deferred.
- **`isolation_key`**: An opaque partition boundary aligned with hosted-agent terminology — may represent a user, tenant, chat, or other scope without baking direct identity semantics into the generic host.
- **Channel-native identity**: The user/account identifier the channel observes from its own platform (Telegram `chat_id`/`user_id`, Teams AAD object id, WhatsApp phone number, Slack user id, …). Always per-channel; never assumed to align across channels.
- **Identity resolver**: Host-level seam that maps a channel-native identity into an `isolation_key`. Default behavior **auto-issues and persists** a fresh, stable `isolation_key` on first contact per `(channel, native_id)` so every end user automatically gets a per-user partition without app code; linking merges the second channel's auto-issued key onto the first channel's existing key. Apps that already own an identity namespace can supply a custom resolver that returns those values directly.
- **Identity linker**: Host-level seam that runs a connect ceremony — typically OAuth, MFA, or a signed one-time code — to associate a new channel-native identity with an existing `isolation_key`. Channels expose entry points (e.g. a `/link` command or button); the host owns the ceremony's routes and short-lived state. Mechanism (OAuth provider, MFA factor, code transport) is pluggable; the contract is not.
- **`ResponseTarget`**: Per-request directive on `ChannelRequest` that controls **where** the response is delivered: `originating` (default), `active` (the user's most recently observed channel), a specific channel, a list of channels, `all_linked`, or `none` (background-only). Independent of `session_mode`. When the target differs from the originating channel, delivery uses the destination channel's `ChannelPush` capability.
- **`ChannelPush`**: Optional channel capability for **proactive** outbound delivery (proactive Telegram message, Teams proactive bot message, webhook callback, SSE broadcast). Channels that don't implement it cannot be the destination of a non-`originating` `ResponseTarget`.
- **Active channel**: The channel most recently observed for a given `isolation_key`. The host tracks last-seen `(isolation_key, channel)` so `response_target="active"` resolves to whichever channel the user is currently using.
- **`RunHandle`**: First-class artifact for background/asynchronous runs. Carries a stable run id, current status (`queued` | `running` | `completed` | `failed`), and the resolved `isolation_key`. Channels may return it directly in their protocol response (e.g. an Invocations 202 with a polling URL) so the caller can poll later, while the host also pushes the result to the configured response target when ready.
- **`session_mode`**: Per-request directive (`auto` | `required` | `disabled`) that controls whether the host resolves a session before invoking the agent. Lets channels honor protocol semantics like Responses `store=False` and lets app authors enforce extra policy.
- **`ChannelContribution`**: What a channel returns from its `contribute(...)` method — routes, middleware, commands, and startup/shutdown lifecycle hooks. The host aggregates contributions into one application.
- **`ChannelCommand`**: A transport-neutral command descriptor. Message channels project these into native command surfaces — Telegram bot commands, future Teams slash commands, WhatsApp menus.
- **`ChannelInvocationHook`**: Per-request callable on built-in channels. Runs after the channel's default `ChannelRequest` is produced, before session resolution. The escape hatch for forcing or forbidding session use, requiring extra options, or adapting to targets like `A2AAgent`.
- **Native command registration**: The startup-time projection of `ChannelCommand` metadata into a platform's native command catalog (e.g. Telegram `set_my_commands(...)`).
- **Hostable target**: The executable object the host fronts — either an **agent** (invoked via the agent execution seam) or a **workflow** (invoked via the workflow execution seam). The host detects the kind and dispatches to the appropriate runner; channels remain unchanged.
- **Execution seam**: The framework's existing per-language invocation contracts — for agents, `SupportsAgentRun.run(...)` in Python and `AIAgent.RunAsync(...)` in .NET; for workflows, the equivalent per-language workflow execution seam. The host requires one of these from the hosted target.

## Consequences

- Good, because app authors get one consistent low-level hosting story for single- and multi-channel scenarios in each supported language.
- Good, because channel packages can stay opinionated about protocol payloads and capabilities without pushing those semantics into the core.
- Good, because the existing protocol-specific implementations provide proven prior art and behavioral guidance.
- Good, because the design supports webhook/message channels that do not look like OpenAI or Foundry APIs.
- Good, because command-capable message channels such as Telegram are first-class channels rather than special-case samples.
- Good, because architectural portability stays at the **standard web-application object** level (ASGI app in Python, `WebApplication` in .NET), so the host is not fundamentally coupled to any one server implementation even when a `serve(...)` convenience uses one.
- Good, because channels can ship sensible invocation defaults while still giving app authors a clear place to enforce extra policy or adapt to different agent implementations (e.g. `A2AAgent`).
- Good, because cross-channel chat continuity for one end user is achievable in the first phase whenever channels can produce a stable `isolation_key`, without requiring any new cross-package storage contract.
- Good, because the same conceptual model is shared across languages — concepts, terminology, and behavior transfer between Python and .NET teams and docs.
- Bad, because we introduce new package and namespace surface area that must be versioned and documented in each language.
- Bad, because we still need to reimplement the needed behavior in Agent Framework-owned code per language.
- Bad, because there will be a temporary overlap with the existing protocol-specific hosts until the new channel packages are implemented and stabilized.
- Neutral, because existing protocol packages remain outside the first implementation scope even though the model keeps a path open for later convergence.

## Validation

The decision is validated when, in each implementing language:

1. a one-channel Responses sample and a two-channel Responses + Invocations sample can be expressed with one host, default route layouts under `/responses/v1` and `/invocations/invoke`, and no handwritten protocol routing,
2. a Responses channel by default forwards official request parameters like `temperature` into agent options and maps `store=False` into disabled session use,
3. app authors can override that default per request with an invocation hook that validates or rewrites the final `ChannelRequest` (for example requiring `temperature`, ignoring `store`, or adapting for `A2AAgent`),
4. a Telegram-style message channel can express command metadata, command registration, and either webhook or polling lifecycle behavior through the new channel contract,
5. a custom webhook/message channel can be authored only against the new channel contract plus the language's web-framework primitives and lifecycle hooks,
6. two channels mounted on the same host (e.g. Telegram + a future Teams channel) configured with a stable per-user `isolation_key` resolve to the same session for the same end user, so a conversation started on one channel can be continued on the other against the same conversation history,
7. an end user who is known on one channel can **link a second channel to the same `isolation_key`** through a host-provided ceremony (OAuth, MFA, or a signed one-time code) without each channel reinventing the linking flow, and subsequent requests from the linked channel resolve to the same session as the original channel,
8. a request submitted on one channel can opt into **delivery on a different channel** — `response_target="active"` (whichever channel the user is currently using), a specific channel id, all linked channels, or `none` (background only) — using the destination channel's `ChannelPush` capability, without the originating channel having to know how the destination delivers,
9. **background runs are first-class**: a channel can submit a request that returns a `RunHandle` immediately and the response is later delivered both via channel push (when the user is next observed on the configured target channel) and via a poll route the caller can hit with the run id,
10. the **same host construction** can front either an agent or a workflow target — the channel ecosystem (Responses, Invocations, Telegram, …) is unchanged, and only the `invocation_hook` (channel-default or app-supplied) differs to adapt the inbound `ChannelRequest` into the input shape the target requires,
11. a host configured with at least the Responses and Invocations channels can be packaged into a container image whose runtime contract (exposed routes, request/response shapes, health/lifecycle behavior) is **compatible with the Hosted Agents platform**, so the same image can be deployed to that platform without protocol shims,
12. a channel can contribute a **WebSocket endpoint** alongside its HTTP routes through the same `Channel` contract, the host's app object exposes it through the standard ASGI / ASP.NET Core WebSocket scope, and the built-in Responses channel exposes a WebSocket transport (default `/responses/ws`) carrying the same Responses request/event model as its HTTP+SSE transport — so the host is forward-compatible with the OpenAI Responses WebSocket transport without changing the hosting contract, and
13. the first Responses and Invocations implementations achieve parity with the important behavior of the current protocol-specific hosts without introducing a runtime dependency on them or leaking protocol-specific request models into the hosting core.

## Pros and Cons of the Options

### Keep the current protocol-specific hosting packages only

- Good, because no new package or abstraction needs to be introduced.
- Good, because each protocol can move independently.
- Bad, because users still cannot host one agent on multiple channels through one shared host.
- Bad, because request/session/event bridging keeps being rebuilt at the protocol layer.
- Bad, because webhook/message channels still have no natural home.
- Bad, because the same gap exists in every language with no shared conceptual model.

### One monolithic `hosting` package with all channels built in

- Good, because discovery is straightforward.
- Good, because cross-channel refactoring is simpler inside one package.
- Bad, because every app pays the dependency and maintenance cost of every channel.
- Bad, because lifecycle and stability become coupled across unrelated channels.
- Bad, because it does not fit either ecosystem's subpackage direction.

### New hosting core plus new channel packages, reimplemented without reference to current hosting implementations

- Good, because the abstraction boundary can be kept very clean.
- Good, because package ownership is clear.
- Bad, because it ignores useful prior art in the current hosting implementations.
- Bad, because it increases implementation cost and migration risk.
- Bad, because it makes early channel parity harder.

### New hosting core plus separate channel packages, informed by current protocol-specific implementations

- Good, because it gives us a reusable host abstraction without discarding what we learned from current protocol work.
- Good, because the core stays protocol-agnostic while channel packages remain Agent Framework-owned and dependency-free with respect to the legacy protocol-specific hosts.
- Good, because it gives future channels a deeper seam than today's top-level host wrappers.
- Good, because the conceptual model can be applied uniformly in Python and .NET.
- Neutral, because some implementation details may look similar to the current hosts when they are solving the same problem.
- Bad, because the design team must still curate the boundary carefully to avoid copying protocol-specific assumptions into the generic host.

## Open Questions

| # | Question | Notes |
|---|---|---|
| 1 | Final distribution package and namespace names per language. | Python public imports stay at `agent_framework.hosting` regardless; .NET namespace conventions follow `Microsoft.Agents.AI.*`. |
| 2 | How tightly do Python and .NET API names need to match? | Decision: keep concepts and terminology identical, allow idiomatic naming differences (e.g. `serve` vs `RunAsync`). |
| 3 | Should generic auth helpers (HMAC signature, bearer token) live in core, in optional shared helpers, or per channel? | Currently per channel + host middleware in both languages. |
| 4 | Should a later phase define a pluggable session store interface, and should it be cross-language or per-language? | Listed as v1 fast follow in the Python spec. |
| 5 | **Should the host support multi-target hosting at all** — one host fronting a router across multiple agents and/or workflows? Open whether this is wanted: it broadens scope, complicates session/identity resolution per target, and may always be better solved a layer above (e.g. an external router owning multiple single-target hosts). | Removed from the spec's stretch requirements pending validation that the use case is real. |
| 6 | Is "Channel" the GA name in both languages? "Head" was used interchangeably during design discussions. | Confirm before public docs in either language. |
| 7 | Should command scopes / projection metadata become first-class — e.g. private-chat-only vs group-chat-visible commands, per-locale descriptions? | Telegram's `BotCommandScope` and `language_code` would need to be representable cross-channel and cross-language. |
| 8 | Which identity-linking mechanisms ship in the first phase — OAuth (which providers as helpers?), MFA via an Identity provider, signed short-lived one-time codes generated on one channel and entered on another, or all of the above? | Contract is generic; first-party helpers are scoped separately. Decision should not block channel work. |
| 9 | Where do issued link grants live — short-lived in-memory state in the host, the same pluggable session store, or a separate identity store? | Likely shares the pluggable session/state store; finalize when that store contract lands. |
| 10 | Should the identity resolver be invoked **per channel** (one resolver per mounted channel) or **once on the host** with a `(channel_id, native_id)` input? | Leaning toward host-level resolver receiving channel id, so cross-channel decisions stay in one place. |
| 11 | Where does the **run-handle store** live (in-memory v1, same pluggable session/state store, separate store)? What is the at-rest format and TTL? | Persistence model determined alongside the pluggable session store. |
| 12 | What is the contract for `ChannelPush` failure (destination channel offline, user opted out, push token expired) — fall back to active, drop, or surface as a `RunHandle.failed`? | Default behavior should be opinionated; per-request override via invocation hook. |
| 13 | Should `response_target="active"` use a **time window** (last seen within N minutes) and what happens if the window expires before the response is ready? | Likely yes — fall back to `originating` or `all_linked`; configurable. |
| 14 | For the Responses WebSocket transport, what subprotocol identifier and auth carrier should the channel adopt — `Authorization` header on the `Upgrade`, a `Sec-WebSocket-Protocol` token, or a query-string-bound short-lived token? Aligning with the upstream OpenAI Responses WS shape is preferable; the channel codec should stay swappable so it can track upstream changes without touching the host contract. | Decide alongside the first Responses WS implementation; keep host contract untouched. |

## More Information

This ADR intentionally does **not** require:

- immediate migration of existing protocol-specific packages,
- a standardized persistence/storage abstraction in the first phase,
- multi-agent routing inside one host,
- a runtime or package dependency on legacy protocol-specific hosts in the new hosting core or its channel packages,
- identical type names across languages — each language follows its own idioms while preserving the same concepts and terminology.

The Telegram sample proposed in PR #5393 is prior art for native command catalogs and for channels that need startup/shutdown lifecycle behavior beyond plain route registration. The same shape is expected to inform future Teams and WhatsApp channels in both languages.

Companion specs cover the per-language API surface, information design, and sample code:

- [SPEC-002 Python hosting core and pluggable channels](../specs/002-python-hosting-channels.md)
- *(future)* SPEC-00X .NET hosting core and pluggable channels
