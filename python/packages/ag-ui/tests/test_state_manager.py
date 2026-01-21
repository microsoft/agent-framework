# Copyright (c) Microsoft. All rights reserved.

from ag_ui.core import CustomEvent, EventType
from agent_framework import ChatMessage

from agent_framework_ag_ui._events import AgentFrameworkEventBridge
from agent_framework_ag_ui._orchestration._state_manager import StateManager


def test_state_manager_initializes_defaults_and_snapshot() -> None:
    state_manager = StateManager(
        state_schema={"items": {"type": "array"}, "metadata": {"type": "object"}},
        predict_state_config=None,
        require_confirmation=True,
    )
    current_state = state_manager.initialize({"metadata": {"a": 1}})
    bridge = AgentFrameworkEventBridge(run_id="run", thread_id="thread", current_state=current_state)

    snapshot_event = state_manager.initial_snapshot_event(bridge)
    assert snapshot_event is not None
    assert snapshot_event.snapshot["items"] == []
    assert snapshot_event.snapshot["metadata"] == {"a": 1}


def test_state_manager_predict_state_event_shape() -> None:
    state_manager = StateManager(
        state_schema=None,
        predict_state_config={"doc": {"tool": "write_document_local", "tool_argument": "document"}},
        require_confirmation=True,
    )
    predict_event = state_manager.predict_state_event()
    assert isinstance(predict_event, CustomEvent)
    assert predict_event.type == EventType.CUSTOM
    assert predict_event.name == "PredictState"
    assert predict_event.value[0]["state_key"] == "doc"


def test_state_context_only_when_new_user_turn() -> None:
    state_manager = StateManager(
        state_schema={"items": {"type": "array"}},
        predict_state_config=None,
        require_confirmation=True,
    )
    state_manager.initialize({"items": [1]})

    assert state_manager.state_context_message(is_new_user_turn=False, conversation_has_tool_calls=False) is None

    message = state_manager.state_context_message(is_new_user_turn=True, conversation_has_tool_calls=False)
    assert isinstance(message, ChatMessage)
    assert message.contents[0].type == "text"
    assert "Current state of the application" in message.contents[0].text


def test_state_manager_with_dataclass_in_state() -> None:
    """Test that state containing dataclasses can be serialized without crashing.

    This test ensures the fix for JSON serialization errors when state
    contains dataclass or other non-JSON-serializable objects.
    """
    from dataclasses import dataclass

    @dataclass
    class UserData:
        name: str
        age: int

    state_manager = StateManager(
        state_schema={"user": {"type": "object"}},
        predict_state_config=None,
        require_confirmation=True,
    )
    # Initialize with a dataclass object in the state
    state_manager.initialize({"user": UserData(name="Alice", age=30)})

    # This should NOT raise TypeError when generating the context message
    message = state_manager.state_context_message(is_new_user_turn=True, conversation_has_tool_calls=False)

    assert message is not None
    assert isinstance(message, ChatMessage)
    # The dataclass should be serialized to JSON in the message
    assert "Alice" in message.contents[0].text
    assert "30" in message.contents[0].text


def test_state_manager_with_pydantic_in_state() -> None:
    """Test that state containing Pydantic models can be serialized without crashing."""
    from pydantic import BaseModel

    class UserModel(BaseModel):
        email: str
        active: bool

    state_manager = StateManager(
        state_schema={"user": {"type": "object"}},
        predict_state_config=None,
        require_confirmation=True,
    )
    # Initialize with a Pydantic model in the state
    state_manager.initialize({"user": UserModel(email="test@example.com", active=True)})

    # This should NOT raise TypeError
    message = state_manager.state_context_message(is_new_user_turn=True, conversation_has_tool_calls=False)

    assert message is not None
    assert "test@example.com" in message.contents[0].text
