# agent-framework-hosting-teams

Microsoft Teams channel for [agent-framework-hosting](../hosting), built on
the official [`microsoft-teams-apps`](https://pypi.org/project/microsoft-teams-apps/)
SDK (microsoft/teams.py). Teams is reached **through Azure Bot Service**;
this channel does not change that — there is currently no way to receive
Teams traffic without a Bot Service registration. What it changes is the
*programming model*: typed activity models, native streaming, Adaptive
Cards, citations, and a typed feedback callback all in one place.

> Looking for the channel-neutral Activity Protocol shape (text in / text
> out for Slack, Webex, Telegram-via-Bot-Service, …)? Use
> [`agent-framework-hosting-activity-protocol`](../hosting-activity-protocol)
> instead.

## When to choose which

| If you need …                                                            | Use this channel                                  |
| ------------------------------------------------------------------------ | ------------------------------------------------- |
| One bot reachable from many Bot Service connectors with the same code    | `agent-framework-hosting-activity-protocol`       |
| Microsoft Teams with Adaptive Cards, streaming, citations, feedback      | `agent-framework-hosting-teams` (this package)    |
| Slack / Webex / Telegram-via-Bot-Service only                            | `agent-framework-hosting-activity-protocol`       |

## Usage

```python
from agent_framework_hosting import AgentFrameworkHost
from agent_framework_hosting_teams import (
    TeamsChannel,
    TeamsCitation,
    TeamsOutboundContext,
    TeamsOutboundPayload,
)

# Plain text reply
host = AgentFrameworkHost(
    target=my_agent,
    channels=[
        TeamsChannel(
            client_id="<entra app id>",
            client_secret="<entra client secret>",
            tenant_id="<tenant id>",
        )
    ],
)
host.serve()
```

### Streaming

```python
TeamsChannel(
    client_id=..., client_secret=..., tenant_id=...,
    streaming=True,  # use the SDK's HttpStream for live mid-message edits
)
```

### Adaptive Cards via outbound transform

```python
from microsoft_teams.cards.core import AdaptiveCard

async def to_card(ctx: TeamsOutboundContext) -> TeamsOutboundPayload:
    card = AdaptiveCard(
        body=[{"type": "TextBlock", "text": ctx.result.text, "wrap": True}],
    )
    return TeamsOutboundPayload(card=card)

TeamsChannel(..., outbound_transform=to_card)
```

### Citations

```python
async def with_citations(ctx: TeamsOutboundContext) -> TeamsOutboundPayload:
    return TeamsOutboundPayload(
        text=ctx.result.text,
        citations=[
            TeamsCitation(
                name="Microsoft Agent Framework",
                url="https://aka.ms/agent-framework",
                abstract="Build, orchestrate, and deploy AI agents.",
            ),
        ],
    )
```

### Feedback callback

```python
from agent_framework_hosting_teams import TeamsFeedbackContext

async def on_feedback(ctx: TeamsFeedbackContext) -> None:
    log.info(
        "rating=%s reply_to=%s feedback=%s user=%s",
        ctx.rating, ctx.reply_to_id, ctx.feedback, ctx.identity.native_id,
    )

TeamsChannel(..., feedback_handler=on_feedback)
```

## Authentication

Pass `client_id` / `client_secret` (and optionally `tenant_id`) the same
way you would to the SDK directly. For managed identity or custom token
acquisition flows, supply the SDK-shaped `token=` callable instead. For
local development against the Bot Framework Emulator, set
`skip_auth=True` to disable JWT validation on inbound activities.

## Custom mount path

The default messaging endpoint is `/teams/messages` (matching the Bot
Framework convention). Override via the `path=` constructor argument.
