---
status: proposed
contact: eavanvalkenburg
date: 2026-06-11
deciders: eavanvalkenburg
---

# Python hosting core and pluggable channels

## Scope

This specification is the Python implementation plan for [ADR-0027](../decisions/0027-hosting-channels.md). It documents the simplified v1 host/channel contract only.

The v1 contract is:

- `AgentFrameworkHost` owns one Starlette app, one hostable target, and one or more channels.
- A hostable target is either a `SupportsAgentRun`-compatible agent or a `Workflow`.
- Channels contribute routes, middleware, commands, and lifecycle callbacks.
- Channels parse protocol-native input into `ChannelRequest`.
- Channels render their own originating response.
- Session continuity is explicit: a channel supplies `ChannelSession(isolation_key=...)`, and the host resolves/caches an `AgentSession` for that key.
- The host invokes `ChannelRunHook` and `ChannelResponseHook`; channels provide hook configuration and protocol context.

The host does not link identities, route responses to other channels, run background continuations, or multicast in v1. Those enhancements are tracked in [ADR-0028](../decisions/0028-hosting-linking-multicast-enhancements.md).

## Goals

- Let an app expose one agent or workflow on multiple protocols without handwritten Starlette composition.
- Keep protocol parsing and response formatting inside channel packages.
- Provide one session-resolution path shared by all channels.
- Keep the channel authoring surface small enough for new channels to implement.
- Preserve full-fidelity agent and workflow results until a channel decides how to render them.

## Non-goals for v1

The following are removed from the v1 implementation pass:

- `IdentityLinker`, `IdentityAllowlist`, `AuthPolicy`, and `LinkPolicy`
- `ResponseTarget`, active-channel routing, `all_linked`, fan-out, and multicast
- `ChannelPush` and `ChannelPushCodec`
- `DurableTaskRunner`, `InProcessTaskRunner`, and `RetryPolicy`
- continuation tokens and background delivery
- confidentiality tiers
- `agent-framework-hosting-entra`
- `local_identity_link`

These are follow-up design topics, not hidden requirements of the v1 host.

## Packages

| Package | Import surface | Contents |
|---|---|---|
| `agent-framework-hosting` | `agent_framework_hosting` | `AgentFrameworkHost`, channel protocols, key request/result types, hooks, `reset_session`, state-path helpers. |
| `agent-framework-hosting-responses` | `agent_framework_hosting_responses` | `ResponsesChannel`. |
| `agent-framework-hosting-invocations` | `agent_framework_hosting_invocations` | `InvocationsChannel`. |
| `agent-framework-hosting-telegram` | `agent_framework_hosting_telegram` | `TelegramChannel` and Telegram command helpers. |
| `agent-framework-hosting-activity-protocol` | `agent_framework_hosting_activity_protocol` | `ActivityProtocolChannel` for Activity Protocol over Azure Bot Service. |
| `agent-framework-hosting-discord` | `agent_framework_hosting_discord` | `DiscordChannel` and Discord command/interaction helpers. |
| `agent-framework-foundry-hosting` | `agent_framework.foundry_hosting` | Foundry isolation middleware and Foundry-backed hosting helpers usable with the v1 host. |

Channel packages may depend on their native SDKs. The core hosting package should not depend on channel SDKs or on top-level legacy protocol hosts.

## Key Types

### `AgentFrameworkHost`

The host constructor accepts:

- `target`: one `SupportsAgentRun`-compatible object or one `Workflow`
- `channels`: one or more `Channel` instances
- optional Starlette middleware
- optional `state_dir`
- optional workflow `checkpoint_location`

The host exposes:

- `app`: the canonical Starlette ASGI application
- `serve(...)`: a convenience wrapper for local serving
- `reset_session(isolation_key: str)`: rotate the cached `AgentSession` for a host-tracked conversation

`state_dir` is narrowed to v1 host-owned local files only:

- session aliases (`isolation_key` to current `AgentSession` id), and
- workflow checkpoint paths when the app chooses the host-provided file layout.

It is not a store for identity links, continuations, active-channel state, delivery attempts, or multicast payloads.

Externally supplied isolation keys are trusted only after the channel or host middleware has authenticated and authorized the caller. The host uses `isolation_key` as a partition key; the string itself is not proof of identity or ownership.

### `Channel`

A channel implements a small protocol:

- declare a stable channel id/name,
- contribute routes, middleware, commands, and lifecycle callbacks,
- parse inbound protocol data into `ChannelRequest`,
- call the host through `ChannelContext.run(...)` or `ChannelContext.run_stream(...)`, and
- serialize the returned result to the originating protocol response.

Channels own protocol authentication, signature validation, native command registration, and protocol-specific error bodies.

### `ChannelContribution`

`ChannelContribution` is the channel's host-facing contribution:

- Starlette routes and optional middleware,
- native command descriptors,
- startup and shutdown callbacks, and
- any channel-local metadata needed by the package.

The host aggregates contributions but does not interpret protocol payloads.

### `ChannelRequest`

`ChannelRequest` is the host-neutral request envelope produced by a channel. It carries:

- target input,
- optional `ChannelSession`,
- optional `ChannelIdentity`,
- options and attributes produced by the channel, and
- request metadata useful to hooks and context providers.

The host may pass attributes through to context providers and middleware. Channels should treat attributes as a documented extension bag, not as a cross-channel delivery contract.

### `ChannelSession`

`ChannelSession(isolation_key=...)` is the only v1 session-continuity mechanism.

When a request contains an isolation key:

1. The host looks up or creates the cached `AgentSession` for that key.
2. The target runs with that `AgentSession` when the target is an agent.
3. `reset_session(isolation_key)` rotates the alias so the next request starts a new conversation.

If two channels produce the same isolation key on the same host, they share the same cached session. If they produce different keys, they do not share session state.

### `ChannelIdentity`

`ChannelIdentity` is optional request metadata such as channel id, native user id, tenant id, claims, or display attributes.

In v1, `ChannelIdentity` does not link channels, authorize callers, select delivery destinations, or imply that two identities should share an `AgentSession`. A channel that wants shared history must still produce the same `ChannelSession.isolation_key`.

### Hooks

Hooks are optional and channel-owned:

- `ChannelRunHook`: runs after channel parsing and before host invocation; returns the `ChannelRequest` to execute.
- `ChannelResponseHook`: runs after target completion and before the originating channel renders a one-shot response.
- `ChannelStreamUpdateHook`: the host applies it to streamed updates before the originating channel serializes the stream.

Common uses include adapting chat text into workflow inputs, enforcing deployment-specific options, flattening rich output for text-only protocols, or filtering streamed updates for a protocol. Stream update hooks are update-only; they do not automatically sanitize `get_final_response()` output. Channels choose their response transport from the parsed protocol request before invoking run hooks.

### `HostedRunResult`

`HostedRunResult[T]` wraps the target's full-fidelity result plus the resolved `AgentSession | None`.

- Agent targets produce `HostedRunResult[AgentResponse]`.
- Workflow targets produce `HostedRunResult[WorkflowRunResult]`.

The host does not flatten, filter, or translate the result. Each channel decides how much of the result its protocol can carry.

## Host Behavior

1. `AgentFrameworkHost` builds one Starlette app and asks each channel for its contribution.
2. A channel route receives a protocol-native request.
3. The channel validates/parses the native payload and creates `ChannelRequest`.
4. The channel passes the request, optional `ChannelRunHook`, and protocol-native context to the host.
5. The host invokes `ChannelRunHook`, if configured, and receives the prepared request.
6. The host resolves an `AgentSession` from `ChannelSession.isolation_key` when present.
7. The host invokes the agent or workflow target.
8. The host wraps the result in `HostedRunResult` or the streaming equivalent.
9. The host invokes `ChannelResponseHook`, if configured, for non-streaming/final response shaping.
10. The host applies stream update hooks while the channel consumes streams; the channel renders the originating protocol response.

There is no host-level route from one channel's request to another channel's response in v1.

## Workflow Checkpoints

Workflow checkpointing is explicit. Apps either configure checkpoint storage on the workflow itself or pass a `checkpoint_location` to the host so the workflow dispatch path can use the intended file location.

`state_dir` may provide a conventional location for workflow checkpoint files, but checkpointing is still opt-in and separate from agent session history. Checkpoints are workflow-runtime state, not channel state and not identity-link state.

## Foundry Isolation Middleware

V1 keeps Foundry isolation as middleware rather than as a channel-linking feature.

The middleware is installed only when the Foundry hosting environment flag is present. In that environment it reads Foundry-provided isolation values at the trusted hosting boundary, exposes them as read-only request context for Foundry-aware history or memory providers, and rejects unsafe session resumes when the live isolation context does not match persisted session context. Outside Foundry, raw isolation headers are ignored unless an app supplies its own trusted middleware.

This middleware does not create cross-channel identity links and does not authorize non-Foundry channels.

## Current Channels

### Responses

`ResponsesChannel` exposes the OpenAI-compatible Responses API shape. It maps request body fields such as input, options, and conversation identifiers into `ChannelRequest`, and it renders Responses-compatible one-shot or streaming responses.

Responses session continuity uses a channel-selected `isolation_key`, commonly derived from a response/conversation id, caller-provided session id, Foundry isolation context, or deployment-specific request metadata.

### Invocations

`InvocationsChannel` exposes an invocation endpoint for server-side callers and tools. It maps the request body into `ChannelRequest` and renders the invocation result on the same HTTP response.

Invocations is useful for typed workflow inputs because a `ChannelRunHook` can translate the request body into the workflow's expected input type.

### Telegram

`TelegramChannel` supports webhook or polling transport, native command registration, and message rendering back to the originating Telegram chat.

The channel chooses a default `isolation_key` from Telegram-native data such as chat id, user id, or a configured user/chat scope. A `/new` or equivalent command may call `reset_session` for that isolation key.

### Activity Protocol

`ActivityChannel` supports Activity Protocol requests, typically through Azure Bot Service for Teams, Web Chat, and other Bot Framework-fronted surfaces.

The channel maps incoming `Activity` objects to `ChannelRequest` and renders a reply activity to the originating conversation. Proactive Activity delivery, active-channel routing, and all-linked fan-out are not v1 host semantics.

### Discord

`DiscordChannel` supports Discord messages, slash commands, and interactions as channel-native input.

The channel maps Discord-native user, guild, channel, thread, and interaction data into `ChannelRequest` metadata and a configured `ChannelSession.isolation_key`. It renders the result to the originating Discord response path.

## High-level Samples

### One agent on Responses

```python
host = AgentFrameworkHost(
    target=agent,
    channels=[ResponsesChannel()],
)

app = host.app
```

### One agent on multiple channels

```python
host = AgentFrameworkHost(
    target=agent,
    channels=[
        ResponsesChannel(),
        InvocationsChannel(),
        TelegramChannel(bot_token=os.environ["TELEGRAM_BOT_TOKEN"]),
    ],
)

host.serve(host="localhost", port=8000)
```

The host owns one Starlette app. Each channel contributes its own routes and renders its own response.

### Adapting a request before execution

```python
from dataclasses import replace


def enforce_options(request: ChannelRequest) -> ChannelRequest:
    options = dict(request.options or {})
    options["temperature"] = 0
    return replace(request, options=options)


host = AgentFrameworkHost(
    target=agent,
    channels=[ResponsesChannel(run_hook=enforce_options)],
)
```

### Workflow with explicit checkpoints

```python
host = AgentFrameworkHost(
    target=workflow,
    channels=[InvocationsChannel(run_hook=adapt_to_workflow_input)],
    checkpoint_location=Path("./.af-hosting/workflow_checkpoints"),
)
```

The hook adapts channel-native input to the workflow's typed input. Checkpoints use the explicit workflow checkpoint location, not identity-link or delivery storage.

### Message channel reset command

```python
async def new_chat(context):
    if context.request.session is not None:
        await context.host.reset_session(context.request.session.isolation_key)
        await context.reply("Started a new conversation.")
```

Telegram, Activity Protocol, and Discord can expose equivalent native commands when their protocols support them.

## Follow-up Enhancements

See [ADR-0028](../decisions/0028-hosting-linking-multicast-enhancements.md) for the deferred design covering:

- cross-channel identity linking,
- authorization and allowlists,
- non-originating response delivery,
- active-channel routing,
- multicast and all-linked delivery,
- background runs and continuation tokens,
- durable delivery runners,
- retry/replay semantics, and
- payload serialization.

Those enhancements must layer on top of this v1 contract without requiring v1 users to adopt them.

## Validation Gates

The Python implementation should be considered complete when:

- a sample uses one `AgentFrameworkHost` with multiple channels and no manual Starlette route composition,
- each current channel has contract tests for route contribution, lifecycle, request parsing, hooks, and originating response rendering,
- session tests prove shared `isolation_key` values share an `AgentSession` and `reset_session` rotates it,
- workflow tests or samples use explicit `checkpoint_location`,
- Foundry isolation middleware is covered by integration or contract tests,
- no v1 package exposes the removed linking, multicast, durable-runner, or continuation APIs, and
- this spec and ADR-0027 remain aligned.
