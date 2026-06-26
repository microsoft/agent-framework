# Copyright (c) Microsoft. All rights reserved.

"""Telegram-only hosting sample.

A single agent connected to a Telegram bot via ``TelegramChannel``.

- ``lookup_weather`` tool demonstrates streaming and tool invocation end-to-end.
- ``FileHistoryProvider`` persists per-chat history across restarts.
- ``run_hook`` strips caller-supplied model options (the host owns model
  selection) and raises reasoning effort for a richer Telegram persona.
- Slash commands: ``/start``, ``/help``, ``/new``, ``/whoami``,
  ``/weather <city>``.

Required env: ``FOUNDRY_PROJECT_ENDPOINT``, ``FOUNDRY_MODEL``,
``TELEGRAM_BOT_TOKEN``. Auth uses ``DefaultAzureCredential``.

Run
---
``app`` is a module-level Starlette ASGI app::

    uv sync
    az login
    export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
    export FOUNDRY_MODEL=gpt-4o
    export TELEGRAM_BOT_TOKEN=...
    uv run hypercorn app:app --bind 0.0.0.0:8000

Or use the ``__main__`` block for quick local iteration::

    uv run python app.py
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Annotated

from agent_framework import Agent, FileHistoryProvider, tool
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import (
    AgentFrameworkHost,
    ChannelCommand,
    ChannelCommandContext,
    ChannelRequest,
)
from agent_framework_hosting_telegram import TelegramChannel, telegram_isolation_key
from azure.identity.aio import DefaultAzureCredential

# import logging
# logging.basicConfig(level=logging.DEBUG)

SESSIONS_DIR = Path(__file__).resolve().parent / "storage" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Tool
# --------------------------------------------------------------------------- #


@tool(approval_mode="never_require")
def lookup_weather(
    location: Annotated[str, "The city to look up weather for."],
) -> str:
    """Return a deterministic weather report for a city."""
    high_temp = 5 + (sum(location.encode("utf-8")) % 21)
    reports = {
        "Seattle": f"Seattle is rainy with a high of {high_temp}°C.",
        "Amsterdam": f"Amsterdam is cloudy with a high of {high_temp}°C.",
        "Tokyo": f"Tokyo is clear with a high of {high_temp}°C.",
    }
    return reports.get(location, f"{location} is sunny with a high of {high_temp}°C.")


# --------------------------------------------------------------------------- #
# Run hook
# --------------------------------------------------------------------------- #


def run_hook(request: ChannelRequest, **_: object) -> ChannelRequest:
    """Strip caller-supplied options the host owns and raise reasoning effort."""
    options = dict(request.options or {})
    options.pop("model", None)
    options["reasoning"] = {"effort": "high", "summary": "detailed"}
    return replace(request, options=options)


# --------------------------------------------------------------------------- #
# Telegram commands
# --------------------------------------------------------------------------- #


def _isolation_key(ctx: ChannelCommandContext) -> str:
    return telegram_isolation_key(ctx.request.attributes.get("chat_id"))


def make_commands(host_ref: dict[str, AgentFrameworkHost]) -> list[ChannelCommand]:
    """Build slash commands that close over the host so ``/new`` can reset state."""

    async def handle_start(ctx: ChannelCommandContext) -> None:
        await ctx.reply("Hi! I'm a weather assistant.\nCommands: /new, /whoami, /weather <city>, /help.")

    async def handle_help(ctx: ChannelCommandContext) -> None:
        await ctx.reply(
            "/new — start a fresh conversation\n"
            "/whoami — show your isolation key\n"
            "/weather <city> — call the weather tool directly\n"
            "/help — this message"
        )

    async def handle_new(ctx: ChannelCommandContext) -> None:
        host_ref["host"].reset_session(_isolation_key(ctx))
        await ctx.reply("New session started. Previous history is cleared for this chat.")

    async def handle_whoami(ctx: ChannelCommandContext) -> None:
        await ctx.reply(f"Your isolation key on this host is: {_isolation_key(ctx)}")

    async def handle_weather(ctx: ChannelCommandContext) -> None:
        command_text = ctx.request.input if isinstance(ctx.request.input, str) else ""
        _, _, location = command_text.partition(" ")
        location = location.strip() or "Seattle"
        await ctx.reply(lookup_weather(location=location))

    return [
        ChannelCommand("start", "Introduce the bot", handle_start),
        ChannelCommand("help", "List available commands", handle_help),
        ChannelCommand("new", "Start a new session for this chat", handle_new),
        ChannelCommand("whoami", "Show the isolation key for this chat", handle_whoami),
        ChannelCommand("weather", "Call the weather tool: /weather <city>", handle_weather),
    ]


# --------------------------------------------------------------------------- #
# Host wiring
# --------------------------------------------------------------------------- #


def build_host() -> AgentFrameworkHost:
    agent = Agent(
        client=FoundryChatClient(credential=DefaultAzureCredential()),
        name="WeatherAgent",
        instructions=(
            "You are a friendly weather assistant. Use the lookup_weather tool "
            "for any weather question and answer in one short sentence."
        ),
        tools=[lookup_weather],
        context_providers=[FileHistoryProvider(SESSIONS_DIR)],
        default_options={"store": False},
    )

    host_ref: dict[str, AgentFrameworkHost] = {}
    host = AgentFrameworkHost(
        target=agent,
        channels=[
            TelegramChannel(
                bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
                webhook_url=os.environ.get("TELEGRAM_WEBHOOK_URL"),
                secret_token=os.environ.get("TELEGRAM_WEBHOOK_SECRET"),
                parse_mode="Markdown",
                commands=make_commands(host_ref),
                run_hook=run_hook,
            ),
        ],
        debug=True,
    )
    host_ref["host"] = host
    return host


app = build_host().app


if __name__ == "__main__":
    build_host().serve(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
