# Copyright (c) Microsoft. All rights reserved.

from ag_ui.core import CustomEvent, EventType
from agent_framework import ChatMessage, TextContent

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
    assert isinstance(message.contents[0], TextContent)
    assert "Current state of the application" in message.contents[0].text
