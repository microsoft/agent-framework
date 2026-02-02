# Copyright (c) Microsoft. All rights reserved.

"""Tests for service-managed thread IDs, and service-generated response ids."""

import sys
from pathlib import Path
from typing import Any

from ag_ui.core import RunFinishedEvent, RunStartedEvent
from agent_framework import Content
from agent_framework._types import AgentResponseUpdate, ChatResponseUpdate

sys.path.insert(0, str(Path(__file__).parent))
from utils_test_ag_ui import StubAgent


async def test_service_thread_id_when_there_are_updates():
    """Test that service-managed thread IDs (conversation_id) are correctly set as the thread_id in events."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    updates: list[AgentResponseUpdate] = [
        AgentResponseUpdate(
            contents=[Content.from_text(text="Hello, user!")],
            response_id="resp_67890",
            raw_representation=ChatResponseUpdate(
                contents=[Content.from_text(text="Hello, user!")],
                conversation_id="conv_12345",
                response_id="resp_67890",
            ),
        )
    ]
    agent = StubAgent(updates=updates)
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {
        "messages": [{"role": "user", "content": "Hi"}],
    }

    events: list[Any] = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    assert isinstance(events[0], RunStartedEvent)
    assert events[0].run_id == "resp_67890"
    assert events[0].thread_id == "conv_12345"
    assert isinstance(events[-1], RunFinishedEvent)


async def test_service_thread_id_when_no_user_message():
    """Test when user submits no messages, emitted events still have with a thread_id"""
    from agent_framework.ag_ui import AgentFrameworkAgent

    updates: list[AgentResponseUpdate] = []
    agent = StubAgent(updates=updates)
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data: dict[str, list[dict[str, str]]] = {
        "messages": [],
    }

    events: list[Any] = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    assert len(events) == 2
    assert isinstance(events[0], RunStartedEvent)
    assert events[0].thread_id
    assert isinstance(events[-1], RunFinishedEvent)


async def test_service_thread_id_when_user_supplied_thread_id():
    """Test that user-supplied thread IDs are preserved in emitted events."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    updates: list[AgentResponseUpdate] = []
    agent = StubAgent(updates=updates)
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data: dict[str, Any] = {"messages": [{"role": "user", "content": "Hi"}], "threadId": "conv_12345"}

    events: list[Any] = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    assert isinstance(events[0], RunStartedEvent)
    assert events[0].thread_id == "conv_12345"
    assert isinstance(events[-1], RunFinishedEvent)
