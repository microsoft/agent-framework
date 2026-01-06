# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentRunEvent and AgentRunUpdateEvent type annotations."""

from agent_framework import AgentRunResponse, AgentRunResponseUpdate, ChatMessage, Role
from agent_framework._workflows._events import AgentRunEvent, AgentRunUpdateEvent


def test_agent_run_event_data_type() -> None:
    """Verify AgentRunEvent.data is typed as AgentRunResponse | None."""
    response = AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Hello")])
    event = AgentRunEvent(executor_id="test", data=response)

    # This assignment should pass type checking without a cast
    data: AgentRunResponse | None = event.data
    assert data is not None
    assert data.text == "Hello"


def test_agent_run_event_data_none() -> None:
    """Verify AgentRunEvent.data can be None."""
    event = AgentRunEvent(executor_id="test")

    data: AgentRunResponse | None = event.data
    assert data is None


def test_agent_run_update_event_data_type() -> None:
    """Verify AgentRunUpdateEvent.data is typed as AgentRunResponseUpdate | None."""
    update = AgentRunResponseUpdate()
    event = AgentRunUpdateEvent(executor_id="test", data=update)

    # This assignment should pass type checking without a cast
    data: AgentRunResponseUpdate | None = event.data
    assert data is not None


def test_agent_run_update_event_data_none() -> None:
    """Verify AgentRunUpdateEvent.data can be None."""
    event = AgentRunUpdateEvent(executor_id="test")

    data: AgentRunResponseUpdate | None = event.data
    assert data is None
