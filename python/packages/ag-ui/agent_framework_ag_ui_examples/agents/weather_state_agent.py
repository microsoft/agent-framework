# Copyright (c) Microsoft. All rights reserved.

"""Deterministic tool-driven AG-UI state example.

This sample demonstrates how a tool can push a *deterministic* state update
to the AG-UI frontend based on its actual return value — in contrast to
``predict_state_config`` which fires optimistically from LLM-predicted tool
call arguments. See issue https://github.com/microsoft/agent-framework/issues/3167.

The :func:`agent_framework_ag_ui.state_update` helper wraps a text result
together with a state snapshot. When a tool returns one of these, the AG-UI
endpoint merges the snapshot into the shared state and emits a
``StateSnapshotEvent`` after the tool result.
"""

from __future__ import annotations

from typing import Any

from agent_framework import Agent, Content, SupportsChatGetResponse, tool
from agent_framework.ag_ui import AgentFrameworkAgent

from agent_framework_ag_ui import state_update

# Simulated weather database — in the issue's motivating example the tool
# would instead call a real weather API.
_WEATHER_DB: dict[str, dict[str, Any]] = {
    "seattle": {"temperature": 11, "conditions": "rainy", "humidity": 75},
    "san francisco": {"temperature": 14, "conditions": "foggy", "humidity": 85},
    "new york city": {"temperature": 18, "conditions": "sunny", "humidity": 60},
    "miami": {"temperature": 29, "conditions": "hot and humid", "humidity": 90},
    "chicago": {"temperature": 9, "conditions": "windy", "humidity": 65},
}


@tool
async def get_weather(location: str) -> Content:
    """Fetch current weather for a location and push it into AG-UI shared state.

    Unlike ``predict_state_config`` — which derives state optimistically from
    LLM-predicted tool call arguments — this tool uses ``state_update`` to
    forward the *actual* fetched weather to the frontend. The ``text`` goes
    back to the LLM as the normal tool result, and the ``state`` dict is merged
    into the AG-UI shared state.

    Args:
        location: City name to look up.

    Returns:
        A :class:`Content` carrying both the LLM-visible text result and a
        deterministic state snapshot.
    """
    key = location.lower()
    data = _WEATHER_DB.get(
        key,
        {"temperature": 21, "conditions": "partly cloudy", "humidity": 50},
    )
    weather_record = {"location": location, **data}
    return state_update(
        text=(
            f"The weather in {location} is {data['conditions']} at "
            f"{data['temperature']}°C with {data['humidity']}% humidity."
        ),
        state={"weather": weather_record},
    )


def weather_state_agent(client: SupportsChatGetResponse[Any]) -> AgentFrameworkAgent:
    """Create an AG-UI agent with a deterministic tool-driven state tool."""
    agent = Agent[Any](
        name="weather_state_agent",
        instructions=(
            "You are a weather assistant. When a user asks about the weather "
            "in a city, call the get_weather tool and use its output to give a "
            "friendly, concise reply. The tool also updates the shared UI state "
            "so the frontend can render a weather card from the `weather` key."
        ),
        client=client,
        tools=[get_weather],
    )

    return AgentFrameworkAgent(
        agent=agent,
        name="WeatherStateAgent",
        description="Weather agent that deterministically updates shared state from tool results.",
        state_schema={
            "weather": {
                "type": "object",
                "description": "Last fetched weather record",
            },
        },
    )
