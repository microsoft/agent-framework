# Copyright (c) Microsoft. All rights reserved.

"""Minimal Responses-only hosting sample.

Single agent with one ``@tool`` (``lookup_weather``), single channel
(``ResponsesChannel``), one ``run_hook`` that demonstrates the
settings-mutation seam over caller-supplied options.

What the hook does
------------------
On every Responses request the hook receives the ``ChannelRequest`` that
the channel built from the inbound HTTP body. It:

- strips ``model`` (the host owns the backing deployment), ``store``
  (this agent owns persistence), and ``temperature`` (the configured
  model may not honor it),
- forces a ``reasoning`` effort + summary preset so the deployed surface
  is consistent regardless of what the caller sent.

The hook is the documented escape hatch over the uniform
``ChannelRequest`` envelope.

Run
---
``app`` is a module-level Starlette ASGI app. Recommended local launch::

    uv sync
    az login
    export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
    export FOUNDRY_MODEL=gpt-5-nano
    uv run hypercorn app:app --bind 0.0.0.0:8000

Or use the ``__main__`` block (single-process Hypercorn) for quick
iteration::

    uv run python app.py

Then call it::

    uv run python call_server.py "What is the weather in Tokyo?"
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Annotated

from agent_framework import Agent, FileHistoryProvider, tool
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import AgentFrameworkHost, ChannelRequest
from agent_framework_hosting_responses import ResponsesChannel
from azure.identity.aio import DefaultAzureCredential

SESSIONS_DIR = Path(__file__).resolve().parent / "storage" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


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


# the run hook defines what you want to allow the user to passthrough when they call your host
# since the responses clients can call with all of the responses options,
# you can decide with this run_hook which of those: are rejected
# which are passed through, which are altered, which are added.
# In this sample below, we are removing, model, temperature and store if set
# and we add reasoning, but note that this could also be set on the Agent itself
# the difference is that this option is specific to the Responses channel
# so if you want to differentiate between options over channels
# you would set the option in the run_hook, if it needs to be the same (like store)
# you would set it in the agent.
def run_hook(request: ChannelRequest, **_: object) -> ChannelRequest:
    """Strip caller-supplied options the host should own and force a
    reasoning preset."""
    options = dict(request.options or {})

    # The host owns the backing deployment; the agent's default_options
    # own ``store``; the model may not honor ``temperature``. Strip them
    # so the caller can't override.
    options.pop("model", None)
    options.pop("temperature", None)
    options.pop("store", None)

    # Force a consistent reasoning preset on every turn.
    options["reasoning"] = {"effort": "medium", "summary": "auto"}

    return replace(request, options=options or None)


def build_host() -> AgentFrameworkHost:
    # Here we define how our agent should run, with tools, options, etc:
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
        channels=[ResponsesChannel(run_hook=run_hook)],
        debug=True,
    )


app = build_host().app


if __name__ == "__main__":
    build_host().serve(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
