# Copyright (c) Microsoft. All rights reserved.

"""MCP channel hosting sample.

Exposes a single ``WeatherAgent`` as an MCP tool over Streamable HTTP.
Any MCP-compatible client — another agent, an IDE, or tooling — can call
``run_agent`` to invoke the hosted agent.

What this sample shows:

- ``MCPChannel`` serving a ``WeatherAgent`` with a ``@tool`` behind the MCP
  Streamable-HTTP transport at ``/mcp``.
- A ``run_hook`` that strips all caller-supplied options so the host owns model
  selection (the same security seam as ``ResponsesChannel``).
- ``FileHistoryProvider`` for per-session history persisted across restarts.

Required env: ``FOUNDRY_PROJECT_ENDPOINT``, ``FOUNDRY_MODEL``.
Auth uses ``DefaultAzureCredential``.

Run
---
``app`` is a module-level Starlette ASGI app::

    uv sync
    az login
    export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
    export FOUNDRY_MODEL=gpt-4o
    uv run python app.py

Multi-process via Hypercorn::

    uv run hypercorn app:app --bind 0.0.0.0:8000
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Annotated

from agent_framework import Agent, FileHistoryProvider, tool
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import AgentFrameworkHost, ChannelRequest
from agent_framework_hosting_mcp import MCPChannel
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
    """Strip all caller-supplied options; the host owns model selection."""
    return replace(request, options=None)


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
    return AgentFrameworkHost(
        target=agent,
        channels=[MCPChannel(run_hook=run_hook)],
        debug=True,
    )


app = build_host().app


if __name__ == "__main__":
    build_host().serve(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
