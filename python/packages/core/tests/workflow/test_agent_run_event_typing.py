# Copyright (c) Microsoft. All rights reserved.

"""Tests for WorkflowEvent[T] generic type annotations."""

from agent_framework import AgentResponse, AgentResponseUpdate, ChatMessage
from agent_framework._workflows._events import WorkflowEvent


def test_workflow_event_with_agent_response_data_type() -> None:
    """Verify WorkflowEvent[AgentResponse].data is typed as AgentResponse."""
    response = AgentResponse(messages=[ChatMessage(role="assistant", text="Hello")])
    event: WorkflowEvent[AgentResponse] = WorkflowEvent.emit(executor_id="test", data=response)

    # This assignment should pass type checking without a cast
    data: AgentResponse = event.data
    assert data is not None
    assert data.text == "Hello"


def test_workflow_event_with_agent_response_update_data_type() -> None:
    """Verify WorkflowEvent[AgentResponseUpdate].data is typed as AgentResponseUpdate."""
    update = AgentResponseUpdate()
    event: WorkflowEvent[AgentResponseUpdate] = WorkflowEvent.emit(executor_id="test", data=update)

    # This assignment should pass type checking without a cast
    data: AgentResponseUpdate = event.data
    assert data is not None


def test_workflow_event_repr() -> None:
    """Verify WorkflowEvent.__repr__ uses consistent format."""
    response = AgentResponse(messages=[ChatMessage(role="assistant", text="Hello")])
    event: WorkflowEvent[AgentResponse] = WorkflowEvent.emit(executor_id="test", data=response)

    repr_str = repr(event)
    assert "WorkflowEvent" in repr_str
    assert "executor_id='test'" in repr_str
    assert "data=" in repr_str
