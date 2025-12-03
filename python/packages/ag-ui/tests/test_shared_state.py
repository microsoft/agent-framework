# Copyright (c) Microsoft. All rights reserved.

"""Tests for shared state management."""

import sys
from pathlib import Path
from typing import Any

import pytest
from ag_ui.core import StateSnapshotEvent
from agent_framework import ChatAgent, TextContent
from agent_framework._types import ChatResponseUpdate

from agent_framework_ag_ui._agent import AgentFrameworkAgent
from agent_framework_ag_ui._events import AgentFrameworkEventBridge

sys.path.insert(0, str(Path(__file__).parent))
from test_helpers_ag_ui import StreamingChatClientStub, stream_from_updates


@pytest.fixture
def mock_agent() -> ChatAgent:
    """Create a mock agent for testing."""
    updates = [ChatResponseUpdate(contents=[TextContent(text="Hello!")])]
    chat_client = StreamingChatClientStub(stream_from_updates(updates))
    return ChatAgent(name="test_agent", instructions="Test agent", chat_client=chat_client)


def test_state_snapshot_event():
    """Test creating state snapshot events."""
    bridge = AgentFrameworkEventBridge(run_id="test-run", thread_id="test-thread")

    state = {
        "recipe": {
            "name": "Chocolate Chip Cookies",
            "ingredients": ["flour", "sugar", "chocolate chips"],
            "instructions": ["Mix ingredients", "Bake at 350°F"],
            "servings": 24,
        }
    }

    event = bridge.create_state_snapshot_event(state)

    assert isinstance(event, StateSnapshotEvent)
    assert event.snapshot == state
    assert event.snapshot["recipe"]["name"] == "Chocolate Chip Cookies"
    assert len(event.snapshot["recipe"]["ingredients"]) == 3


def test_state_delta_event():
    """Test creating state delta events using JSON Patch format."""
    bridge = AgentFrameworkEventBridge(run_id="test-run", thread_id="test-thread")

    # JSON Patch operations (RFC 6902)
    delta = [
        {"op": "add", "path": "/recipe/ingredients/-", "value": "vanilla extract"},
        {"op": "replace", "path": "/recipe/servings", "value": 30},
    ]

    event = bridge.create_state_delta_event(delta)

    assert event.delta == delta
    assert len(event.delta) == 2
    assert event.delta[0]["op"] == "add"
    assert event.delta[1]["op"] == "replace"


async def test_agent_with_initial_state(mock_agent: ChatAgent) -> None:
    """Test agent emits state snapshot when initial state provided."""
    state_schema: dict[str, Any] = {"recipe": {"type": "object", "properties": {"name": {"type": "string"}}}}

    agent = AgentFrameworkAgent(
        agent=mock_agent,
        state_schema=state_schema,
    )

    initial_state = {"recipe": {"name": "Test Recipe"}}

    input_data: dict[str, Any] = {
        "messages": [{"role": "user", "content": "Hello"}],
        "state": initial_state,
    }

    events: list[Any] = []
    async for event in agent.run_agent(input_data):
        events.append(event)

    # Should have RunStartedEvent, StateSnapshotEvent, RunFinishedEvent at minimum
    snapshot_events = [e for e in events if isinstance(e, StateSnapshotEvent)]
    assert len(snapshot_events) == 1
    assert snapshot_events[0].snapshot == initial_state


async def test_agent_without_state_schema(mock_agent: ChatAgent) -> None:
    """Test agent doesn't emit state events without state schema."""
    agent = AgentFrameworkAgent(agent=mock_agent)

    input_data: dict[str, Any] = {
        "messages": [{"role": "user", "content": "Hello"}],
        "state": {"some": "state"},
    }

    events: list[Any] = []
    async for event in agent.run_agent(input_data):
        events.append(event)

    # Should NOT have any StateSnapshotEvent
    snapshot_events = [e for e in events if isinstance(e, StateSnapshotEvent)]
    assert len(snapshot_events) == 0
