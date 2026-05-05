# Copyright (c) Microsoft. All rights reserved.

"""Complete multi-channel hosting sample with unified Entra ID identity.

Wires every built-in channel onto a single ``AgentFrameworkHost`` and
demonstrates a pattern for collapsing per-channel identifiers into a single
**Microsoft Entra ID** (object id) key so a user's history follows them
across surfaces.

Identity resolution
-------------------
Each request is bucketed under one ``isolation_key`` for ``FileHistoryProvider``:

- **Teams** is the source of truth. Inbound activities carry the user's
  ``aadObjectId``; we promote it to ``entra:<oid>`` in the Teams ``run_hook``.
- **Telegram** has no built-in OAuth identity. Users link their chat to
  their Entra ID by sending ``/link``; the bot replies with a one-shot
  authorize URL served by the host's ``EntraIdentityLinkChannel``. After the
  OAuth callback the mapping ``telegram:<chat_id> → entra:<oid>`` is
  persisted to ``identity_links.json`` and every later Telegram turn is
  bucketed under the user's Entra key.
- **Responses API** callers can pass ``entra_oid`` directly (top-level or
  in ``metadata``), or pass ``safety_identifier`` and rely on the same
  store (``responses:<safety_id> → entra:<oid>``). Otherwise we fall back
  to ``responses:<safety_id>``.

Required environment
--------------------
- ``FOUNDRY_PROJECT_ENDPOINT`` / ``FOUNDRY_MODEL`` — agent backing.
- ``TELEGRAM_BOT_TOKEN`` — required to enable the Telegram channel.
- ``TEAMS_APP_ID`` / ``TEAMS_APP_PASSWORD`` — optional; without them the
  Teams channel runs in dev mode (Bot Framework Emulator only).
- ``ENTRA_TENANT_ID`` / ``ENTRA_CLIENT_ID`` plus **either**
  ``ENTRA_CLIENT_SECRET`` **or** ``ENTRA_CERT_PATH``
  (+ optional ``ENTRA_CERT_PASSWORD``) — required to enable the ``/link``
  flow. The app's redirect URI must be registered as
  ``{PUBLIC_BASE_URL}/auth/callback`` in your Entra app.
- ``PUBLIC_BASE_URL`` — externally reachable base of this host (e.g.
  ``https://my-host.example.com``). Defaults to ``http://localhost:8000``.

Run
---
This module exposes ``app`` as the canonical ASGI surface. Recommended
production launch is **Hypercorn**::

    hypercorn app:app --bind 0.0.0.0:8000 --workers 4

The ``__main__`` block below uses ``host.serve(...)`` (single-process
Hypercorn) as a local-dev fallback.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any, Sequence

from agent_framework import Agent, FileHistoryProvider, tool
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import (
    AgentFrameworkHost,
    Channel,
    ChannelCommand,
    ChannelCommandContext,
    ChannelRequest,
    ChannelSession,
)
from agent_framework_hosting_entra import (
    EntraIdentityLinkChannel,
    EntraIdentityStore,
    entra_isolation_key,
)
from agent_framework_hosting_activity_protocol import ActivityProtocolChannel
from agent_framework_hosting_invocations import InvocationsChannel
from agent_framework_hosting_responses import ResponsesChannel
from agent_framework_hosting_telegram import TelegramChannel
from azure.identity.aio import DefaultAzureCredential

logger = logging.getLogger("agent_framework.hosting.complete_app")

SESSIONS_DIR = Path(__file__).resolve().parent / "storage" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
IDENTITY_STORE_PATH = Path(__file__).resolve().parent / "storage" / "identity_links.json"


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


@tool(approval_mode="never_require")
def lookup_weather(
    location: Annotated[str, "The city to look up weather for."],
) -> str:
    """Return a deterministic weather report for a city."""
    reports = {
        "Seattle": "Seattle is rainy with a high of 13°C.",
        "Amsterdam": "Amsterdam is cloudy with a high of 16°C.",
        "Tokyo": "Tokyo is clear with a high of 22°C.",
    }
    return reports.get(location, f"{location} is sunny with a high of 20°C.")


# --------------------------------------------------------------------------- #
# Run hooks: collapse per-channel identifiers down to a single Entra ID key
# --------------------------------------------------------------------------- #


def _replace_session(request: ChannelRequest, isolation_key: str) -> ChannelRequest:
    return replace(request, session=ChannelSession(isolation_key=isolation_key))


def make_activity_hook() -> Any:
    """Promote ``aadObjectId`` from the inbound Activity to ``entra:<oid>``.

    The Activity Protocol channel is treated as the **primary** identity
    source for Teams traffic: every authenticated Teams user has an Entra
    object id, and we trust it directly without consulting the link store.
    """

    def _hook(
        request: ChannelRequest,
        *,
        protocol_request: Mapping[str, Any] | None = None,
        **_: object,
    ) -> ChannelRequest:
        activity = protocol_request or {}
        from_ = activity.get("from") if isinstance(activity, Mapping) else None
        oid = from_.get("aadObjectId") if isinstance(from_, Mapping) else None
        if oid:
            return _replace_session(request, entra_isolation_key(oid))
        # Unauthenticated channels (web chat, emulator) — fall back to the
        # per-conversation key the channel already set.
        return request

    return _hook


def make_telegram_hook(store: EntraIdentityStore) -> Any:
    """If the Telegram chat id is linked, swap to ``entra:<oid>`` for history."""

    def _hook(request: ChannelRequest, **_: object) -> ChannelRequest:
        chat_id = request.attributes.get("chat_id")
        if chat_id is not None:
            linked = store.lookup(f"telegram:{chat_id}")
            if linked is not None:
                return _replace_session(request, linked)
        # Bump reasoning effort regardless of identity.
        options = dict(request.options or {})
        options["reasoning"] = {"effort": "high", "summary": "detailed"}
        return replace(request, options=options)

    return _hook


def make_responses_hook(store: EntraIdentityStore) -> Any:
    """Same identity resolution as Telegram/Teams, plus the usual option scrub.

    Resolution order:
      1. Body ``entra_oid`` (top-level or in ``metadata``) — a caller already
         knows the user's Entra id.
      2. ``safety_identifier`` (or legacy ``user``) looked up in the link
         store as ``responses:<id>``.
      3. Fallback ``responses:<safety_id>``.
    """

    def _hook(
        request: ChannelRequest,
        *,
        protocol_request: Mapping[str, Any] | None = None,
        **_: object,
    ) -> ChannelRequest:
        options = dict(request.options or {})
        options.pop("temperature", None)
        options.pop("store", None)

        body = protocol_request or {}
        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}

        explicit_oid = body.get("entra_oid") or metadata.get("entra_oid")
        safety_id = body.get("safety_identifier") or body.get("user") or "anonymous"

        if explicit_oid:
            isolation_key = entra_isolation_key(explicit_oid)
        else:
            isolation_key = store.lookup(f"responses:{safety_id}") or f"responses:{safety_id}"

        return replace(
            request,
            session=ChannelSession(isolation_key=isolation_key),
            options=options or None,
        )

    return _hook


# --------------------------------------------------------------------------- #
# Telegram commands
# --------------------------------------------------------------------------- #


def make_commands(
    host_ref: dict[str, AgentFrameworkHost],
    store: EntraIdentityStore,
    linker_ref: dict[str, EntraIdentityLinkChannel | None],
) -> list[ChannelCommand]:
    def _telegram_key(ctx: ChannelCommandContext) -> str:
        chat_id = ctx.request.attributes.get("chat_id")
        return f"telegram:{chat_id}"

    def _isolation_for(ctx: ChannelCommandContext) -> str:
        # Honour any existing link so /new resets the right bucket.
        return store.lookup(_telegram_key(ctx)) or _telegram_key(ctx)

    async def handle_start(ctx: ChannelCommandContext) -> None:
        await ctx.reply(
            "Hi! I'm a multi-channel agent.\nCommands: /link, /unlink, /new, /whoami, /weather <city>, /help."
        )

    async def handle_help(ctx: ChannelCommandContext) -> None:
        await ctx.reply(
            "/link — bind this chat to your Entra ID for shared history\n"
            "/unlink — unbind this chat\n"
            "/new — start a fresh conversation\n"
            "/whoami — show your isolation key\n"
            "/weather <city> — call the weather tool directly\n"
            "/help — this message"
        )

    async def handle_link(ctx: ChannelCommandContext) -> None:
        linker = linker_ref.get("linker")
        if linker is None:
            await ctx.reply(
                "Identity linking is not configured on this host. "
                "Set ENTRA_TENANT_ID, ENTRA_CLIENT_ID, and either "
                "ENTRA_CLIENT_SECRET or ENTRA_CERT_PATH."
            )
            return
        chat_id = ctx.request.attributes.get("chat_id")
        url = linker.authorize_url_for("telegram", str(chat_id))
        await ctx.reply("Open this link to bind this chat to your Microsoft account:\n" + url)

    async def handle_unlink(ctx: ChannelCommandContext) -> None:
        await store.unlink(_telegram_key(ctx))
        await ctx.reply("This chat is no longer linked. New messages will use the chat-only key.")

    async def handle_new(ctx: ChannelCommandContext) -> None:
        host_ref["host"].reset_session(_isolation_for(ctx))
        await ctx.reply("New session started. Previous history is cleared.")

    async def handle_whoami(ctx: ChannelCommandContext) -> None:
        key = _isolation_for(ctx)
        if key.startswith("entra:"):
            await ctx.reply(f"This chat is linked. Isolation key: {key}")
        else:
            await ctx.reply(f"This chat is not linked to an Entra ID. Isolation key: {key}\nSend /link to bind it.")

    async def handle_weather(ctx: ChannelCommandContext) -> None:
        _, _, location = ctx.request.input.partition(" ")
        location = location.strip() or "Seattle"
        await ctx.reply(lookup_weather(location=location))

    return [
        ChannelCommand("start", "Introduce the bot", handle_start),
        ChannelCommand("help", "List available commands", handle_help),
        ChannelCommand("link", "Bind this chat to your Microsoft account", handle_link),
        ChannelCommand("unlink", "Unbind this chat from any Microsoft account", handle_unlink),
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

    store = EntraIdentityStore(IDENTITY_STORE_PATH)

    # Optional Entra-OAuth identity linker. Pick exactly one credential mode:
    # ENTRA_CLIENT_SECRET *or* ENTRA_CERT_PATH (+ optional ENTRA_CERT_PASSWORD).
    # When unconfigured, /link tells the user the feature is disabled and the
    # host runs without a linker.
    tenant_id = os.environ.get("ENTRA_TENANT_ID")
    client_id = os.environ.get("ENTRA_CLIENT_ID")
    client_secret = os.environ.get("ENTRA_CLIENT_SECRET")
    cert_path = os.environ.get("ENTRA_CERT_PATH")
    cert_password_env = os.environ.get("ENTRA_CERT_PASSWORD")
    public_base_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")

    linker: EntraIdentityLinkChannel | None = None
    if tenant_id and client_id and (client_secret or cert_path):
        linker = EntraIdentityLinkChannel(
            store=store,
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            certificate_path=cert_path,
            certificate_password=cert_password_env.encode() if cert_password_env else None,
            public_base_url=public_base_url,
        )

    host_ref: dict[str, AgentFrameworkHost] = {}
    linker_ref: dict[str, EntraIdentityLinkChannel | None] = {"linker": linker}

    channels: Sequence[Channel] = [
        ResponsesChannel(run_hook=make_responses_hook(store)),
        InvocationsChannel(),
        ActivityProtocolChannel(
            app_id=os.environ.get("TEAMS_APP_ID"),
            tenant_id=os.environ.get("TEAMS_TENANT_ID", "botframework.com"),
            # Use either a client secret OR a certificate. Cert is required
            # for tenants that disallow secrets — see the package README for
            # an `openssl` recipe to generate one.
            app_password=os.environ.get("TEAMS_APP_PASSWORD"),
            certificate_path=os.environ.get("TEAMS_CERT_PATH"),
            certificate_password=(
                os.environ["TEAMS_CERT_PASSWORD"].encode() if os.environ.get("TEAMS_CERT_PASSWORD") else None
            ),
            run_hook=make_activity_hook(),
        ),
        TelegramChannel(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            webhook_url=os.environ.get("TELEGRAM_WEBHOOK_URL"),
            secret_token=os.environ.get("TELEGRAM_WEBHOOK_SECRET"),
            parse_mode="Markdown",
            commands=make_commands(host_ref, store, linker_ref),
            run_hook=make_telegram_hook(store),
        ),
    ]
    if linker is not None:
        channels.append(linker)

    host = AgentFrameworkHost(target=agent, channels=channels, debug=True)
    host_ref["host"] = host
    return host


app = build_host().app


if __name__ == "__main__":
    build_host().serve(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
