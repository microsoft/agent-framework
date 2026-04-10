# Copyright (c) Microsoft. All rights reserved.

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    ChatResponseUpdate,
    Content,
    Message,
)
from agent_framework._types import _process_update, map_chat_to_agent_update


def test_agent_response_init_with_finish_reason() -> None:
    """Test that AgentResponse correctly initializes and stores finish_reason."""
    response = AgentResponse(
        messages=[Message("assistant", [Content.from_text("test")])],
        finish_reason="stop",
    )
    assert response.finish_reason == "stop"


def test_agent_response_update_init_with_finish_reason() -> None:
    """Test that AgentResponseUpdate correctly initializes and stores finish_reason."""
    update = AgentResponseUpdate(
        contents=[Content.from_text("test")],
        role="assistant",
        finish_reason="stop",
    )
    assert update.finish_reason == "stop"


def test_map_chat_to_agent_update_forwards_finish_reason() -> None:
    """Test that mapping a ChatResponseUpdate with finish_reason forwards it."""
    chat_update = ChatResponseUpdate(
        contents=[Content.from_text("test")],
        finish_reason="length",
    )
    agent_update = map_chat_to_agent_update(chat_update, agent_name="test_agent")

    assert agent_update.finish_reason == "length"
    assert agent_update.author_name == "test_agent"


def test_process_update_propagates_finish_reason_to_agent_response() -> None:
    """Test that _process_update correctly updates an AgentResponse from an AgentResponseUpdate."""
    response = AgentResponse(messages=[Message("assistant", [Content.from_text("test")])])
    update = AgentResponseUpdate(
        contents=[Content.from_text("more text")],
        role="assistant",
        finish_reason="stop",
    )

    # Process the update
    _process_update(response, update)

    assert response.finish_reason == "stop"


def test_process_update_does_not_overwrite_with_none() -> None:
    """Test that _process_update does not overwrite an existing finish_reason with None."""
    response = AgentResponse(
        messages=[Message("assistant", [Content.from_text("test")])],
        finish_reason="length",
    )
    update = AgentResponseUpdate(
        contents=[Content.from_text("more text")],
        role="assistant",
        finish_reason=None,
    )

    # Process the update
    _process_update(response, update)

    assert response.finish_reason == "length"


def test_agent_response_serialization_includes_finish_reason() -> None:
    """Test that AgentResponse serializes correctly, including finish_reason."""
    response = AgentResponse(
        messages=[Message("assistant", [Content.from_text("test")])],
        response_id="test_123",
        finish_reason="stop",
    )

    # Serialize using the framework's API and verify finish_reason is included.
    data = response.to_dict()
    assert "finish_reason" in data
    assert data["finish_reason"] == "stop"


def test_agent_response_update_serialization_includes_finish_reason() -> None:
    """Test that AgentResponseUpdate serializes correctly, including finish_reason."""
    update = AgentResponseUpdate(
        contents=[Content.from_text("test")],
        role="assistant",
        response_id="test_456",
        finish_reason="tool_calls",
    )

    data = update.to_dict()
    assert "finish_reason" in data
    assert data["finish_reason"] == "tool_calls"
