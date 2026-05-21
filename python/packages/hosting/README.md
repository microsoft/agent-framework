# agent-framework-hosting

Multi-channel hosting for Microsoft Agent Framework agents.

`agent-framework-hosting` lets you serve a single agent (or workflow)
target through one or more **channels** — pluggable adapters that
expose the target over different transports. The result is a single
Starlette ASGI application you can host anywhere (local Hypercorn,
Azure Container Apps, Foundry Hosted Agents, …).

The base package contains only the channel-neutral plumbing:

- `AgentFrameworkHost` — the Starlette host
- `Channel` / `ChannelPush` — the channel protocols
- `ChannelRequest` / `ChannelSession` / `ChannelIdentity` / `ResponseTarget`
  — the request envelope and routing primitives
- `ChannelContext` / `ChannelContribution` / `ChannelCommand` — the
  channel-side hooks for invoking the target and contributing routes,
  commands, and lifecycle callbacks
- `ChannelRunHook` / `ChannelStreamTransformHook` — the per-request
  customization seams
- `DurableTaskRunner` + `InProcessTaskRunner` — the seam used to
  dispatch non-originating push fan-out; the in-process runner is the
  default. Plug in a durable adapter (e.g.
  `agent-framework-hosting-durabletask`) for `runtime_mode="ephemeral"`
  deployments.

Concrete channels live in their own packages so you only install what
you use:

| Package | Transport |
|---|---|
| `agent-framework-hosting-responses` | OpenAI Responses API |
| `agent-framework-hosting-invocations` | Foundry-native invocation envelope |
| `agent-framework-hosting-telegram` | Telegram Bot API |
| `agent-framework-hosting-activity-protocol` | Bot Framework Activity Protocol (Teams, Direct Line, Web Chat, …) |
| `agent-framework-hosting-teams` | Microsoft Teams (Teams SDK) |
| `agent-framework-hosting-entra` | Entra (OAuth) identity-link sidecar |

## Install

```bash
pip install agent-framework-hosting agent-framework-hosting-responses
# or with uvicorn pre-installed for the demo `host.serve(...)` helper
pip install "agent-framework-hosting[serve]" agent-framework-hosting-responses
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

See the [hosting samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/04-hosting/af-hosting)
for richer multi-channel apps (Telegram + Teams + Responses fan-out,
identity linking, `ResponseTarget` routing, etc.).
