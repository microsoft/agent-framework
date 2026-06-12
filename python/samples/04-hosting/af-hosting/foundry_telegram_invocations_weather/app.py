# Copyright (c) Microsoft. All rights reserved.

"""Telegram weather bot hosted behind Foundry Hosted Agents Invocations.

This sample intentionally mounts the Telegram webhook handler at the container's
``/invocations`` route so the Foundry public Invocations protocol URL can be
registered as the Telegram webhook URL:

``{FOUNDRY_PROJECT_ENDPOINT}/agents/{FOUNDRY_AGENT_NAME}/endpoint/protocols/invocations``

It uses ``FoundryHostedAgentHistoryProvider`` for conversation history and a
small weather tool to validate that a normal channel can run under the
Hosted Agents runtime. The sample also exposes Responses for a quick platform
sanity check.

Sample output after sending "weather in Amsterdam" to the Telegram bot:
Assistant:> Amsterdam is cloudy with a high of 16 C.
"""

from __future__ import annotations

import logging
import os
from dataclasses import replace
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.observability import enable_instrumentation
from agent_framework_foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryHostedAgentHistoryProvider, foundry_response_id
from agent_framework_hosting import (
    AgentFrameworkHost,
    ChannelCommand,
    ChannelCommandContext,
    ChannelRequest,
)
from agent_framework_hosting_responses import ResponsesChannel
from agent_framework_hosting_telegram import TelegramChannel, telegram_isolation_key
from azure.identity.aio import DefaultAzureCredential

AGENT_NAME = "agent-framework-telegram-invocations-weather"
DEFAULT_MODEL_DEPLOYMENT = "gpt-5.4-nano"
DEFAULT_INVOCATIONS_API_VERSION = "2025-11-15-preview"

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
for _noisy in (
    "httpx",
    "httpcore",
    "azure.core.pipeline.policies.http_logging_policy",
    "urllib3",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@tool(approval_mode="never_require")
def lookup_weather(location: Annotated[str, "The city to look up weather for."]) -> str:
    """Return a deterministic weather report for a city."""
    reports = {
        "seattle": "Seattle is rainy with a high of 12 C.",
        "amsterdam": "Amsterdam is cloudy with a high of 16 C.",
        "tokyo": "Tokyo is clear with a high of 22 C.",
        "london": "London is misty with a high of 11 C.",
    }
    normalized = location.strip().lower()
    return reports.get(normalized, f"{location} is sunny with a high of 20 C.")


def _foundry_invocations_webhook_url() -> str:
    """Build the public Foundry Invocations URL used as Telegram's webhook."""
    explicit = os.environ.get("TELEGRAM_WEBHOOK_URL")
    if explicit:
        return explicit

    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    agent_name = os.environ.get("FOUNDRY_AGENT_NAME", AGENT_NAME)
    api_version = os.environ.get("HOSTING_INVOCATIONS_API_VERSION", DEFAULT_INVOCATIONS_API_VERSION)
    return f"{project_endpoint}/agents/{agent_name}/endpoint/protocols/invocations?api-version={api_version}"


def _configure_observability() -> None:
    """Wire Azure Monitor OpenTelemetry when Foundry injects a connection string."""
    conn_str = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn_str:
        logger.info("APPLICATIONINSIGHTS_CONNECTION_STRING not set; skipping Azure Monitor export.")
        return

    from azure.monitor.opentelemetry import configure_azure_monitor  # pyright: ignore[reportUnknownVariableType]

    configure_azure_monitor(connection_string=conn_str)
    logger.info("Azure Monitor OpenTelemetry configured.")


def telegram_hook(request: ChannelRequest, **_: object) -> ChannelRequest:
    """Clamp request options for Telegram-originating runs."""
    options = dict(request.options or {})
    options.pop("store", None)
    options["reasoning"] = {"effort": "high", "summary": "auto"}
    return replace(request, options=options)


def make_commands() -> list[ChannelCommand]:
    """Create Telegram slash commands used by the sample."""

    async def handle_start(ctx: ChannelCommandContext) -> None:
        await ctx.reply("Hi! Ask me for weather in Seattle, Amsterdam, Tokyo, London, or any city.")

    async def handle_help(ctx: ChannelCommandContext) -> None:
        await ctx.reply(
            "/weather <city> - call the weather tool directly\n"
            "/whoami - show your Telegram session key\n"
            "/help - show this message"
        )

    async def handle_whoami(ctx: ChannelCommandContext) -> None:
        await ctx.reply(f"Your session key is {telegram_isolation_key(ctx.request.attributes.get('chat_id'))}.")

    async def handle_weather(ctx: ChannelCommandContext) -> None:
        command_text = ctx.request.input if isinstance(ctx.request.input, str) else ""
        _, _, location = command_text.partition(" ")
        await ctx.reply(lookup_weather(location=(location.strip() or "Seattle")))

    return [
        ChannelCommand("start", "Introduce the bot", handle_start),
        ChannelCommand("help", "List available commands", handle_help),
        ChannelCommand("whoami", "Show the Telegram session key", handle_whoami),
        ChannelCommand("weather", "Call the weather tool: /weather <city>", handle_weather),
    ]


def build_host() -> AgentFrameworkHost:
    """Build the Foundry-hosted Telegram weather agent."""
    # 1. Create a shared credential for model calls and Foundry storage.
    credential = DefaultAzureCredential()
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    # 2. Create the agent with a simple weather tool and Foundry-backed history.
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=project_endpoint,
            model=os.environ.get("MODEL_DEPLOYMENT_NAME", DEFAULT_MODEL_DEPLOYMENT),
            credential=credential,
        ),
        name="TelegramInvocationsWeatherAgent",
        instructions=(
            "You are a concise weather assistant. Use lookup_weather for weather questions "
            "and answer in one short sentence."
        ),
        tools=[lookup_weather],
        context_providers=[
            FoundryHostedAgentHistoryProvider(
                credential=credential,
                endpoint=project_endpoint,
            ),
        ],
    )

    # 3. Register Telegram at /invocations and keep Responses available for sanity checks.
    return AgentFrameworkHost(
        target=agent,
        channels=[
            ResponsesChannel(response_id_factory=foundry_response_id),
            TelegramChannel(
                bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
                path="/invocations",
                transport="webhook",
                webhook_url=_foundry_invocations_webhook_url(),
                parse_mode="Markdown",
                commands=make_commands(),
                run_hook=telegram_hook,
            ),
        ],
    )


_configure_observability()
enable_instrumentation(enable_sensitive_data=True)
app = build_host().app


if __name__ == "__main__":
    import asyncio

    import hypercorn.asyncio
    import hypercorn.config

    config = hypercorn.config.Config()
    config.bind = [f"0.0.0.0:{int(os.environ.get('PORT', '8000'))}"]
    asyncio.run(hypercorn.asyncio.serve(app, config))  # type: ignore[arg-type]
