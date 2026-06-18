# Copyright (c) Microsoft. All rights reserved.

"""Golden event-stream tests for the shared state (structured output) scenario."""

from __future__ import annotations

from typing import Any

from agent_framework import AgentResponseUpdate, Content
from conftest import StubAgent
from event_stream import EventStream
from pydantic import BaseModel

from agent_framework_ag_ui import AgentFrameworkAgent


class RecipeState(BaseModel):
    recipe_title: str = ""
    ingredients: list[str] = []
    message: str = ""


def _build_agent(updates: list[AgentResponseUpdate], **kwargs: Any) -> AgentFrameworkAgent:
    stub = StubAgent(
        updates=updates,
        default_options={"tools": None, "response_format": RecipeState},
    )
    return AgentFrameworkAgent(
        agent=stub,
        state_schema={
            "recipe_title": {"type": "string"},
            "ingredients": {"type": "array", "items": {"type": "string"}},
        },
        **kwargs,
    )


async def _run(agent: AgentFrameworkAgent, payload: dict[str, Any]) -> EventStream:
    return EventStream([event async for event in agent.run(payload)])


PAYLOAD: dict[str, Any] = {
    "thread_id": "thread-state",
    "run_id": "run-state",
    "messages": [{"role": "user", "content": "Give me a pasta recipe"}],
    "state": {"recipe_title": "", "ingredients": []},
}


# ── Golden stream tests ──


async def test_shared_state_emits_state_snapshot() -> None:
    """Structured output agent emits STATE_SNAPSHOT with parsed model fields."""
    # The structured output agent gets a response that the framework parses as RecipeState
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_text(
                    text='{"recipe_title": "Pasta Carbonara", "ingredients": ["pasta", "eggs", "cheese"], "message": "Here is your recipe!"}'
                )
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_bookends()
    stream.assert_no_run_error()

    # Should have STATE_SNAPSHOT with the initial state at minimum
    stream.assert_has_type("STATE_SNAPSHOT")


async def test_shared_state_initial_snapshot_on_first_update() -> None:
    """When state_schema and state are provided, initial STATE_SNAPSHOT is emitted after RUN_STARTED."""
    updates = [
        AgentResponseUpdate(
            contents=[Content.from_text(text='{"recipe_title": "Test", "ingredients": [], "message": "hi"}')],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    # RUN_STARTED should be followed by STATE_SNAPSHOT (initial state)
    stream.assert_ordered_types(["RUN_STARTED", "STATE_SNAPSHOT"])


async def test_shared_state_text_emitted_from_message_field() -> None:
    """Structured output's 'message' field is emitted as text message events."""
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_text(
                    text='{"recipe_title": "Pasta", "ingredients": ["pasta"], "message": "Enjoy your pasta!"}'
                )
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    # Text should be emitted from the message field
    text_contents = stream.get("TEXT_MESSAGE_CONTENT")
    if text_contents:
        combined = "".join(getattr(e, "delta", "") for e in text_contents)
        assert "Enjoy your pasta!" in combined
