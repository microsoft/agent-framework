# Copyright (c) Microsoft. All rights reserved.

"""Multi-channel hosting sample: Responses + Telegram.

Demonstrates running the same agent behind two channels at once:

- ``ResponsesChannel`` — exposes an OpenAI-compatible ``/responses`` endpoint
  so any OpenAI-SDK client can call the agent over HTTP. The ``responses_hook``
  strips caller-supplied options the host owns and keys each session off the
  OpenAI ``safety_identifier`` field.

- ``TelegramChannel`` — connects the same agent to a Telegram bot. The
  ``telegram_hook`` raises reasoning effort for a richer Telegram persona.
  Because both channels share the same ``FileHistoryProvider``, a Telegram chat
  and a Responses caller can resume the *same* conversation: pass the Telegram
  isolation key (e.g. ``telegram:8741188429``) as ``previous_response_id`` on
  the Responses endpoint.

Required env: ``FOUNDRY_PROJECT_ENDPOINT``, ``FOUNDRY_MODEL``,
``TELEGRAM_BOT_TOKEN``. Auth uses ``DefaultAzureCredential``.

Run
---
``app`` is a module-level Starlette ASGI app. Recommended production launch is
**Hypercorn**::

    hypercorn app:app --bind 0.0.0.0:8000 --workers 4

The ``__main__`` block uses ``host.serve(...)`` (single-process Hypercorn) for
quick local iteration::

    uv run python app.py

Note
----
``FileHistoryProvider`` uses in-process file-write locking. It is fine for this
sample but swap it for a cross-process store in production.
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
# Shared tool
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
# Channel hooks
# --------------------------------------------------------------------------- #


def responses_hook(request: ChannelRequest, *, protocol_request: dict | None = None, **_: object) -> ChannelRequest:
    """Strip caller-supplied options the host should own and key the session.

    - Removes ``model``, ``store``, and ``temperature`` so callers cannot
      override the host's choices.
    - Keys each session off the inbound ``previous_response_id`` (if present)
      so any caller can resume an existing AgentSession — including one written
      by the Telegram channel (e.g. ``previous_response_id="telegram:8741188429"``).
    - Falls back to a ``responses:<safety_identifier>`` key when no
      ``previous_response_id`` is supplied.
    """
    options = dict(request.options or {})
    options.pop("model", None)
    options.pop("temperature", None)
    options.pop("store", None)

    body = protocol_request or {}

    if request.session is not None and request.session.isolation_key:
        session = request.session
    else:
        safety_id = body.get("safety_identifier") or "anonymous"
        session = ChannelSession(isolation_key=f"responses:{safety_id}")

    return replace(request, session=session, options=options or None)


def telegram_hook(request: ChannelRequest, **_: object) -> ChannelRequest:
    """Raise reasoning effort for the Telegram persona."""
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
    """Build commands that close over the host so ``/new`` can reset state."""

    async def handle_start(ctx: ChannelCommandContext) -> None:
        await ctx.reply("Hi! I'm a multi-channel weather agent.\nCommands: /new, /whoami, /weather <city>, /help.")

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
