# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentRunEvent and AgentRunUpdateEvent type annotations."""

from agent_framework import AgentResponse, AgentResponseUpdate, ChatMessage, Role
from agent_framework._workflows._events import AgentRunEvent, AgentRunUpdateEvent


def test_agent_run_event_data_type() -> None:
    """Verify AgentRunEvent.data is typed as AgentResponse | None."""
    response = AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Hello")])
    event = AgentRunEvent(executor_id="test", data=response)

    # This assignment should pass type checking without a cast
    data: AgentResponse | None = event.data
    assert data is not None
    assert data.text == "Hello"


def test_agent_run_update_event_data_type() -> None:
    """Verify AgentRunUpdateEvent.data is typed as AgentResponseUpdate | None."""
    update = AgentResponseUpdate()
    event = AgentRunUpdateEvent(executor_id="test", data=update)

    # This assignment should pass type checking without a cast
    data: AgentResponseUpdate | None = event.data
    assert data is not None
