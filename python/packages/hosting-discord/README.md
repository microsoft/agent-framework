# agent-framework-hosting-discord

Discord HTTP Interactions channel for [agent-framework-hosting](../hosting).
The channel exposes a signed Starlette route for Discord slash commands, maps a
configurable slash command to the hosted agent, maps `ChannelCommand` instances
to native Discord commands, and supports push to Discord channel ids.

## Usage

```python
from agent_framework_hosting import AgentFrameworkHost
from agent_framework_hosting_discord import DiscordChannel

host = AgentFrameworkHost(
    target=my_agent,
    channels=[
        DiscordChannel(
            application_id="<discord application id>",
            public_key="<discord public key>",
            bot_token="<discord bot token>",
            guild_id="<guild id for fast dev command registration>",
        )
    ],
)
host.serve()
```

Configure the Discord Developer Portal interaction endpoint as:

```text
https://<your-host>/discord/interactions
```

The channel verifies Discord's `X-Signature-Ed25519` header against the raw
request body before parsing JSON. `skip_signature_verification=True` exists only
for local tests and should not be used on a public endpoint.

## Slash commands

By default, `/ask prompt:<text>` invokes the hosted agent. Additional
`ChannelCommand` instances are registered as Discord slash commands with an
optional `input` string option:

```python
from agent_framework_hosting import ChannelCommand

async def reset(ctx):
    await ctx.reply("Reset acknowledged")

DiscordChannel(
    application_id="...",
    public_key="...",
    bot_token="...",
    commands=[ChannelCommand("reset", "Reset the conversation", reset)],
)
```

When `guild_id` is set, commands are registered only for that guild and usually
appear quickly. Global command registration can take much longer to propagate.
If `register_commands=True` but `bot_token` is omitted, the channel logs a
warning and assumes commands were registered outside the host.

## Identity, sessions, and push

The default isolation key is `discord:<guild-or-dm>:<channel_id>:<user_id>`,
which keeps each user private inside a Discord channel or thread. Pass
`isolation_key_factory=` to use a different scope.

`ChannelIdentity.native_id` is the Discord user id. Push requires
`identity.attributes["channel_id"]`; the first slice intentionally does not
create DM channels as a fallback.

## Streaming

Set `streaming=True` to consume the host stream and edit the original Discord
interaction response as text accumulates. Edits are debounced with
`edit_interval` to avoid excessive Discord REST calls.

