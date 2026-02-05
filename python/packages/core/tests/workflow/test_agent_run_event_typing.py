# Copyright (c) Microsoft. All rights reserved.

"""Tests for agent run event typing."""

from agent_framework import AgentResponse, AgentResponseUpdate, ChatMessage
from agent_framework._workflows._events import WorkflowOutputEvent


def test_agent_run_event_data_type() -> None:
    """Verify WorkflowOutputEvent.data is typed as AgentResponse | None."""
    response = AgentResponse(messages=[ChatMessage(role="assistant", text="Hello")])
    event = WorkflowOutputEvent(data=response, executor_id="test")

    # This assignment should pass type checking without a cast
    data: AgentResponse | None = event.data
    assert data is not None
    assert data.text == "Hello"


def test_agent_run_update_event_data_type() -> None:
    """Verify WorkflowOutputEvent.data is typed as AgentResponseUpdate | None."""
    update = AgentResponseUpdate()
    event = WorkflowOutputEvent(data=update, executor_id="test")

    # This assignment should pass type checking without a cast
    data: AgentResponseUpdate | None = event.data
    assert data is not None
