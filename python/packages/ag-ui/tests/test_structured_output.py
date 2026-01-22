# Copyright (c) Microsoft. All rights reserved.

"""Tests for structured output handling in _agent.py."""

import json
import sys
from collections.abc import AsyncIterator, MutableSequence
from pathlib import Path
from typing import Any

from agent_framework import ChatAgent, ChatMessage, ChatOptions, ChatResponseUpdate, Content
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
from utils_test_ag_ui import StreamingChatClientStub, stream_from_updates


class RecipeOutput(BaseModel):
    """Test Pydantic model for recipe output."""

    recipe: dict[str, Any]
    message: str | None = None


class StepsOutput(BaseModel):
    """Test Pydantic model for steps output."""

    steps: list[dict[str, Any]]
    message: str | None = None


class GenericOutput(BaseModel):
    """Test Pydantic model for generic data."""

    data: dict[str, Any]


async def test_structured_output_with_recipe():
    """Test structured output processing with recipe state."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[ChatMessage], options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(
            contents=[Content.from_text(text='{"recipe": {"name": "Pasta"}, "message": "Here is your recipe"}')]
        )

    agent = ChatAgent(name="test", instructions="Test", chat_client=StreamingChatClientStub(stream_fn))
    agent.default_options = ChatOptions(response_format=RecipeOutput)

    wrapper = AgentFrameworkAgent(
        agent=agent,
        state_schema={"recipe": {"type": "object"}},
    )

    input_data = {"messages": [{"role": "user", "content": "Make pasta"}]}

    events: list[Any] = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should emit StateSnapshotEvent with recipe
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) >= 1
    # Find snapshot with recipe
    recipe_snapshots = [e for e in snapshot_events if "recipe" in e.snapshot]
    assert len(recipe_snapshots) >= 1
    assert recipe_snapshots[0].snapshot["recipe"] == {"name": "Pasta"}

    # Should also emit message as text
    text_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert any("Here is your recipe" in e.delta for e in text_events)


async def test_structured_output_with_steps():
    """Test structured output processing with steps state."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[ChatMessage], options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        steps_data = {
            "steps": [
                {"id": "1", "description": "Step 1", "status": "pending"},
                {"id": "2", "description": "Step 2", "status": "pending"},
            ]
        }
        yield ChatResponseUpdate(contents=[Content.from_text(text=json.dumps(steps_data))])

    agent = ChatAgent(name="test", instructions="Test", chat_client=StreamingChatClientStub(stream_fn))
    agent.default_options = ChatOptions(response_format=StepsOutput)

    wrapper = AgentFrameworkAgent(
        agent=agent,
        state_schema={"steps": {"type": "array"}},
    )

    input_data = {"messages": [{"role": "user", "content": "Do steps"}]}

    events: list[Any] = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should emit StateSnapshotEvent with steps
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) >= 1

    # Snapshot should contain steps
    steps_snapshots = [e for e in snapshot_events if "steps" in e.snapshot]
    assert len(steps_snapshots) >= 1
    assert len(steps_snapshots[0].snapshot["steps"]) == 2
    assert steps_snapshots[0].snapshot["steps"][0]["id"] == "1"


async def test_structured_output_with_no_schema_match():
    """Test structured output when response fields don't match state_schema keys."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    updates = [
        ChatResponseUpdate(contents=[Content.from_text(text='{"data": {"key": "value"}}')]),
    ]

    agent = ChatAgent(
        name="test", instructions="Test", chat_client=StreamingChatClientStub(stream_from_updates(updates))
    )
    agent.default_options = ChatOptions(response_format=GenericOutput)

    wrapper = AgentFrameworkAgent(
        agent=agent,
        state_schema={"result": {"type": "object"}},  # Schema expects "result", not "data"
    )

    input_data = {"messages": [{"role": "user", "content": "Generate data"}]}

    events: list[Any] = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should emit StateSnapshotEvent but with no state updates since no schema fields match
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    # Initial state snapshot from state_schema initialization
    assert len(snapshot_events) >= 1


async def test_structured_output_without_schema():
    """Test structured output without state_schema treats all fields as state."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    class DataOutput(BaseModel):
        """Output with data and info fields."""

        data: dict[str, Any]
        info: str

    async def stream_fn(
        messages: MutableSequence[ChatMessage], options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text='{"data": {"key": "value"}, "info": "processed"}')])

    agent = ChatAgent(name="test", instructions="Test", chat_client=StreamingChatClientStub(stream_fn))
    agent.default_options = ChatOptions(response_format=DataOutput)

    wrapper = AgentFrameworkAgent(
        agent=agent,
        # No state_schema - all non-message fields treated as state
    )

    input_data = {"messages": [{"role": "user", "content": "Generate data"}]}

    events: list[Any] = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should emit StateSnapshotEvent with both data and info fields
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) >= 1
    assert "data" in snapshot_events[0].snapshot
    assert "info" in snapshot_events[0].snapshot
    assert snapshot_events[0].snapshot["data"] == {"key": "value"}
    assert snapshot_events[0].snapshot["info"] == "processed"


async def test_no_structured_output_when_no_response_format():
    """Test that structured output path is skipped when no response_format."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    updates = [ChatResponseUpdate(contents=[Content.from_text(text="Regular text")])]

    agent = ChatAgent(
        name="test",
        instructions="Test",
        chat_client=StreamingChatClientStub(stream_from_updates(updates)),
    )
    # No response_format set

    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events: list[Any] = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should emit text content normally
    text_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert len(text_events) > 0
    assert text_events[0].delta == "Regular text"


async def test_structured_output_with_message_field():
    """Test structured output that includes a message field."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[ChatMessage], options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        output_data = {"recipe": {"name": "Salad"}, "message": "Fresh salad recipe ready"}
        yield ChatResponseUpdate(contents=[Content.from_text(text=json.dumps(output_data))])

    agent = ChatAgent(name="test", instructions="Test", chat_client=StreamingChatClientStub(stream_fn))
    agent.default_options = ChatOptions(response_format=RecipeOutput)

    wrapper = AgentFrameworkAgent(
        agent=agent,
        state_schema={"recipe": {"type": "object"}},
    )

    input_data = {"messages": [{"role": "user", "content": "Make salad"}]}

    events: list[Any] = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should emit the message as text
    text_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert any("Fresh salad recipe ready" in e.delta for e in text_events)

    # Should also have TextMessageStart and TextMessageEnd
    start_events = [e for e in events if e.type == "TEXT_MESSAGE_START"]
    end_events = [e for e in events if e.type == "TEXT_MESSAGE_END"]
    assert len(start_events) >= 1
    assert len(end_events) >= 1


async def test_empty_updates_no_structured_processing():
    """Test that empty updates don't trigger structured output processing."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[ChatMessage], options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        if False:
            yield ChatResponseUpdate(contents=[])

    agent = ChatAgent(name="test", instructions="Test", chat_client=StreamingChatClientStub(stream_fn))
    agent.default_options = ChatOptions(response_format=RecipeOutput)

    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {"messages": [{"role": "user", "content": "Test"}]}

    events: list[Any] = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should only have start and end events
    assert len(events) == 2  # RunStarted, RunFinished
