# agent-framework-hosting

Multi-channel hosting for Microsoft Agent Framework agents.

`agent-framework-hosting` lets you serve a single agent or workflow target
through one or more **channels**. The host owns one Starlette ASGI app,
route/lifecycle composition, and per-`isolation_key` session resolution.
Each channel owns its protocol parsing and response rendering.

The base package contains only channel-neutral plumbing:

- `AgentFrameworkHost` — the Starlette host.
- `Channel` — the channel protocol.
- `ChannelRequest` / `ChannelSession` / `ChannelIdentity` — the request
  envelope and optional channel metadata.
- `ChannelContext` / `ChannelContribution` / `ChannelCommand` — channel-side
  hooks for invoking the target and contributing routes, commands, and
  lifecycle callbacks.
- `ChannelRunHook` / `ChannelResponseHook` / `ChannelStreamUpdateHook` —
  host-invoked customization seams.

`ChannelStreamUpdateHook` applies to streamed updates only. It is not a
substitute for final-response redaction.

Concrete channels live in their own packages so you only install what you use:

| Package | Transport |
|---|---|
| `agent-framework-hosting-responses` | OpenAI Responses API |
| `agent-framework-hosting-invocations` | Foundry-native invocation envelope |
| `agent-framework-hosting-telegram` | Telegram Bot API |
| `agent-framework-hosting-activity-protocol` | Bot Framework Activity Protocol |
| `agent-framework-hosting-discord` | Discord HTTP Interactions |

## Install

```bash
pip install agent-framework-hosting agent-framework-hosting-responses
# or with Hypercorn pre-installed for the demo `host.serve(...)` helper
pip install "agent-framework-hosting[serve]" agent-framework-hosting-responses
# add the [disk] extra to persist reset-session aliases
pip install "agent-framework-hosting[disk]"
```

## Quickstart

```python
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentFrameworkHost, Channel

agent = OpenAIChatClient().as_agent(name="Assistant")

# Add channels from sibling packages, e.g. `agent-framework-hosting-responses`
# exposes a `ResponsesChannel` that serves the OpenAI Responses API.
channels: list[Channel] = []

host = AgentFrameworkHost(target=agent, channels=channels)
host.serve(port=8000)
```

## Session state and workflow checkpoints

By default the host keeps live `AgentSession` objects and reset-session aliases
in memory. Channels opt into continuity by setting
`ChannelRequest.session = ChannelSession(isolation_key=...)`; requests with the
same isolation key reuse the same host-created session.

For long-running deployments that need `reset_session(...)` aliases to survive
restart, pass `state_dir`:

```python
host = AgentFrameworkHost(
    target=agent,
    channels=channels,
    state_dir="./.host-state",
)
```

This creates `./.host-state/sessions/` and stores only lightweight alias
bookkeeping. Live `AgentSession` objects are still rehydrated lazily by the
configured history provider on the next turn.

For workflow targets, `checkpoint_location=...` is the clearest way to enable
checkpoint persistence. As a convenience, `state_dir="./.host-state"` also
derives `./.host-state/checkpoints/` for workflow targets. Use the mapping form
when you want only one component:

```python
from agent_framework_hosting import HostStatePaths

host = AgentFrameworkHost(
    target=workflow,
    channels=channels,
    state_dir=HostStatePaths(
        sessions="/var/lib/myapp/sessions",
        checkpoints="/var/lib/myapp/checkpoints",
    ),
)
```

Cross-channel identity linking, multicast delivery, background runs,
continuation tokens, and durable delivery runners are follow-up enhancements,
not part of this v1 host contract.
