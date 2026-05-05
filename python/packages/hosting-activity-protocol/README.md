# agent-framework-hosting-activity-protocol

Bot Framework **Activity Protocol** channel for
[agent-framework-hosting](../hosting). Connects to **Azure Bot Service** so
the same agent can be reached from Microsoft Teams, Slack, Webex,
Telegram-via-bot-channel, and any other channel Azure Bot Service
supports — without having to learn each channel's native protocol.

> Looking for a deeper Microsoft Teams integration with adaptive cards,
> message extensions, dialogs, SSO, etc? See the companion
> [`agent-framework-hosting-teams`](../hosting-teams) package, which is
> built on `microsoft-teams-apps` and exposes Teams-specific affordances
> on top of (still) Azure Bot Service.

Handles inbound `message` activities, outbound replies, mid-stream
`updateActivity` edits, typing indicators, and both client-secret and
certificate credential modes for the outbound Bot Framework token.

## Usage

```python
from agent_framework_hosting import AgentFrameworkHost
from agent_framework_hosting_activity_protocol import ActivityProtocolChannel

host = AgentFrameworkHost(
    target=my_agent,
    channels=[
        ActivityProtocolChannel(
            app_id="<entra app id>",
            client_secret="<entra client secret>",
            tenant_id="botframework.com",  # or your tenant id
        )
    ],
)
host.serve()
```

For tenants that disallow client secrets, supply `certificate_path=` (and
optionally `certificate_password=`) instead. See the docstring at the top of
`_channel.py` for the openssl one-liner that generates a usable PEM.

In dev mode (no credentials), the channel skips outbound auth so the Bot
Framework Emulator can hit the endpoint without setup.
