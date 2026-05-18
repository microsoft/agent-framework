# Copyright (c) Microsoft. All rights reserved.

"""Advanced multi-channel hosting sample.

Builds on ``app.py`` to demonstrate:

- a function ``@tool`` on the agent (``lookup_weather``),
- per-isolation-key history persisted via ``FileHistoryProvider``,
- a ``ResponsesChannel`` ``run_hook`` that clamps caller-supplied
  ``ChatOptions`` and honours the OpenAI ``previous_response_id`` field as
  the ``AgentSession`` id — so a Responses caller can resume a Telegram
  chat by passing ``previous_response_id="telegram:<chat_id>"`` (or any
  other isolation key written by another channel),
- a ``TelegramChannel`` ``run_hook`` that bumps ``temperature`` for a
  chattier Telegram persona,
- a richer Telegram command catalog including a ``/new`` command that resets
  the cached session for the chat.

Required env: ``FOUNDRY_PROJECT_ENDPOINT``, ``FOUNDRY_MODEL``,
``TELEGRAM_BOT_TOKEN``. Auth uses ``DefaultAzureCredential``.

Run
---
This module exposes ``app`` as the canonical ASGI surface. Recommended
production launch is **Hypercorn**::

    hypercorn app:app --bind 0.0.0.0:8000 --workers 4

The ``__main__`` block below uses ``host.serve(...)`` (single-process
Hypercorn) as a local-dev fallback.

Note
----
``FileHistoryProvider`` provides only in-process file-write locking. Running
multiple Hypercorn workers against the same ``./sessions`` directory is fine
for this sample, but a production deployment should swap it for a store with
cross-process consistency.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from random import randint
from typing import Annotated

from agent_framework import Agent, FileHistoryProvider, tool
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import (
    AgentFrameworkHost,
    ChannelCommand,
    ChannelCommandContext,
    ChannelRequest,
    ChannelSession,
)
from agent_framework_hosting_responses import ResponsesChannel
from agent_framework_hosting_telegram import TelegramChannel, telegram_isolation_key
from azure.identity.aio import DefaultAzureCredential

# import logging
# logging.basicConfig(level=logging.DEBUG)

SESSIONS_DIR = Path(__file__).resolve().parent / "storage" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Tools the agent can call
# --------------------------------------------------------------------------- #


@tool(approval_mode="never_require")
def lookup_weather(
    location: Annotated[str, "The city to look up weather for."],
) -> str:
    """Return a deterministic weather report for a city."""
    high_temp = randint(5, 25)
    reports = {
        "Seattle": f"Seattle is rainy with a high of {high_temp}°C.",
        "Amsterdam": f"Amsterdam is cloudy with a high of {high_temp}°C.",
        "Tokyo": f"Tokyo is clear with a high of {high_temp}°C.",
    }
    return reports.get(location, f"{location} is sunny with a high of {high_temp}°C.")


# --------------------------------------------------------------------------- #
# Responses channel run hook
# --------------------------------------------------------------------------- #


def responses_hook(request: ChannelRequest, *, protocol_request: dict | None = None, **_: object) -> ChannelRequest:
    """Validate, rewrite, and key the channel-built ChannelRequest before invocation.

    The spec calls this out as the developer's runtime escape hatch over the
    uniform ``ChannelRequest`` envelope. Things this hook does:

    - **strip** ``store`` and ``temperature`` (the agent owns persistence via ``FileHistoryProvider``),
    - **inject a session** keyed on the request body. The OpenAI Responses
      ``previous_response_id`` field doubles as our isolation key — the
      ``ResponsesChannel`` already lifts it onto ``request.session``, so any
      caller can resume an arbitrary AgentSession (including one written by
      another channel, e.g. ``telegram:8741188429``) by passing it as
      ``previous_response_id``. When the caller doesn't pass one, fall back
      to a key derived from the OpenAI ``safety_identifier`` field
      (``responses:<id>``).
    """
    options = dict(request.options or {})

    # this agent will only run with models that do not support Temperature, so removing it.
    options.pop("temperature", None)
    options.pop("store", None)

    body = protocol_request or {}

    if request.session is not None and request.session.isolation_key:
        # Caller supplied ``previous_response_id`` — the channel already
        # used it as the AgentSession id. Keep it as-is.
        session = request.session
    else:
        safety_id = body.get("safety_identifier") or "anonymous"
        session = ChannelSession(isolation_key=f"responses:{safety_id}")

    return replace(
        request,
        session=session,
        options=options or None,
    )


def telegram_hook(request: ChannelRequest, **_: object) -> ChannelRequest:
    """Telegram users get a chattier model — bump temperature on every turn."""
    options = dict(request.options or {})
    options["reasoning"] = {"effort": "high", "summary": "detailed"}
    return replace(request, options=options)


# --------------------------------------------------------------------------- #
# Telegram commands
# --------------------------------------------------------------------------- #


def _isolation_key(ctx: ChannelCommandContext) -> str:
    return telegram_isolation_key(ctx.request.attributes.get("chat_id"))


def make_commands(host_ref: dict[str, AgentFrameworkHost]) -> list[ChannelCommand]:
    """Build commands that close over the host so ``/new`` can reset state."""

    async def handle_start(ctx: ChannelCommandContext) -> None:
        await ctx.reply("Hi! I'm a multi-channel agent.\nCommands: /new, /whoami, /weather <city>, /help.")

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
        # Bypass the agent and call the tool directly to demonstrate that
        # commands have full control over how they reply.
        _, _, location = ctx.request.input.partition(" ")
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
            ResponsesChannel(run_hook=responses_hook),
            TelegramChannel(
                bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
                webhook_url=os.environ.get("TELEGRAM_WEBHOOK_URL"),
                secret_token=os.environ.get("TELEGRAM_WEBHOOK_SECRET"),
                parse_mode="Markdown",
                commands=make_commands(host_ref),
                run_hook=telegram_hook,
            ),
        ],
        debug=True,
    )
    host_ref["host"] = host
    return host


app = build_host().app


if __name__ == "__main__":
    build_host().serve(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
