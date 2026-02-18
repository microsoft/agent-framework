# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for create_agent_entity factory function.

Run with: pytest tests/test_entities.py -v
"""

from collections.abc import Callable
from typing import Any, TypeVar
from unittest.mock import AsyncMock, Mock

import pytest
from agent_framework import AgentResponse, Message

from agent_framework_azurefunctions._entities import create_agent_entity

FuncT = TypeVar("FuncT", bound=Callable[..., Any])


def _agent_response(text: str | None) -> AgentResponse:
    """Create an AgentResponse with a single assistant message."""
    message = Message(role="assistant", text=text) if text is not None else Message(role="assistant", text="")
    return AgentResponse(messages=[message])


class TestCreateAgentEntity:
    """Test suite for the create_agent_entity factory function."""

    def test_create_agent_entity_returns_callable(self) -> None:
        """Test that create_agent_entity returns a callable."""
        mock_agent = Mock()

        entity_function = create_agent_entity(mock_agent)

        assert callable(entity_function)

    def test_entity_function_handles_run_agent(self) -> None:
        """Test that the entity function handles the run_agent operation."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity_function = create_agent_entity(mock_agent)

        # Mock context
        mock_context = Mock()
        mock_context.operation_name = "run"
        mock_context.entity_key = "conv-123"
        mock_context.get_input.return_value = {
            "message": "Test message",
            "correlationId": "corr-entity-factory",
        }
        mock_context.get_state.return_value = None

        # Execute
        entity_function(mock_context)

        # Verify result and state were set
        assert mock_context.set_result.called
        assert mock_context.set_state.called

    def test_entity_function_handles_reset(self) -> None:
        """Test that the entity function handles the reset operation."""
        mock_agent = Mock()

        entity_function = create_agent_entity(mock_agent)

        # Mock context with existing state
        mock_context = Mock()
        mock_context.operation_name = "reset"
        mock_context.get_state.return_value = {
            "schemaVersion": "1.0.0",
            "data": {
                "conversationHistory": [
                    {
                        "$type": "request",
                        "correlationId": "test-correlation-id",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "messages": [
                            {
                                "role": "user",
                                "contents": [{"$type": "text", "text": "test"}],
                            }
                        ],
                    }
                ]
            },
        }

        # Execute
        entity_function(mock_context)

        # Verify reset result
        assert mock_context.set_result.called
        result = mock_context.set_result.call_args[0][0]
        assert result["status"] == "reset"

        # Verify state was cleared
        assert mock_context.set_state.called
        state = mock_context.set_state.call_args[0][0]
        assert state["data"]["conversationHistory"] == []

    def test_entity_function_handles_unknown_operation(self) -> None:
        """Test that the entity function handles unknown operations."""
        mock_agent = Mock()

        entity_function = create_agent_entity(mock_agent)

        mock_context = Mock()
        mock_context.operation_name = "invalid_operation"
        mock_context.get_state.return_value = None

        # Execute
        entity_function(mock_context)

        # Verify error result
        assert mock_context.set_result.called
        result = mock_context.set_result.call_args[0][0]
        assert "error" in result
        assert "invalid_operation" in result["error"].lower()

    def test_entity_function_creates_new_entity_on_first_call(self) -> None:
        """Test that the entity function creates a new entity when no state exists."""
        mock_agent = Mock()
        mock_agent.__class__.__name__ = "Agent"

        entity_function = create_agent_entity(mock_agent)
        mock_context = Mock()
        mock_context.operation_name = "reset"
        mock_context.get_state.return_value = None  # No existing state

        # Execute
        entity_function(mock_context)

        # Verify new entity state was created
        assert mock_context.set_result.called
        result = mock_context.set_result.call_args[0][0]
        assert result["status"] == "reset"
        assert mock_context.set_state.called
        state = mock_context.set_state.call_args[0][0]
        assert state["data"] == {"conversationHistory": []}

    def test_entity_function_restores_existing_state(self) -> None:
        """Test that the entity function can operate when existing state is present."""
        mock_agent = Mock()

        entity_function = create_agent_entity(mock_agent)

        existing_state = {
            "schemaVersion": "1.0.0",
            "data": {
                "conversationHistory": [
                    {
                        "$type": "request",
                        "correlationId": "corr-existing-1",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "messages": [
                            {
                                "role": "user",
                                "contents": [
                                    {
                                        "$type": "text",
                                        "text": "msg1",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "$type": "response",
                        "correlationId": "corr-existing-1",
                        "createdAt": "2024-01-01T00:05:00Z",
                        "messages": [
                            {
                                "role": "assistant",
                                "contents": [
                                    {
                                        "$type": "text",
                                        "text": "resp1",
                                    }
                                ],
                            }
                        ],
                    },
                ],
            },
        }

        mock_context = Mock()
        mock_context.operation_name = "reset"
        mock_context.get_state.return_value = existing_state

        entity_function(mock_context)

        assert mock_context.set_result.called

        # Reset should clear history and persist via set_state
        assert mock_context.set_state.called
        persisted_state = mock_context.set_state.call_args[0][0]
        assert persisted_state["data"]["conversationHistory"] == []

    def test_entity_function_handles_string_input(self) -> None:
        """Test that the entity function handles non-dict input by converting to string."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("String response"))

        entity_function = create_agent_entity(mock_agent)

        # Mock context with non-dict input (like a number)
        mock_context = Mock()
        mock_context.operation_name = "run"
        mock_context.entity_key = "conv-456"
        # Use a number to test the str() conversion path
        mock_context.get_input.return_value = 12345
        mock_context.get_state.return_value = None

        # Execute - entity will convert non-dict input to string
        entity_function(mock_context)

        # Verify the result was set
        assert mock_context.set_result.called

    def test_entity_function_handles_none_input(self) -> None:
        """Test that the entity function handles None input by converting to empty string."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Empty response"))

        entity_function = create_agent_entity(mock_agent)

        # Mock context with None input
        mock_context = Mock()
        mock_context.operation_name = "run"
        mock_context.entity_key = "conv-789"
        mock_context.get_input.return_value = None
        mock_context.get_state.return_value = None

        # Execute - should hit error path since entity expects dict or valid JSON string
        entity_function(mock_context)

        # Verify the result was set (likely error result)
        assert mock_context.set_result.called

    def test_entity_function_handles_event_loop_runtime_error(self) -> None:
        """Test that the entity function handles RuntimeError from get_event_loop by creating a new loop."""
        from unittest.mock import patch

        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity_function = create_agent_entity(mock_agent)

        mock_context = Mock()
        mock_context.operation_name = "run"
        mock_context.entity_key = "conv-loop-test"
        mock_context.get_input.return_value = {"message": "Test"}
        mock_context.get_state.return_value = None

        # Simulate RuntimeError when getting event loop
        with (
            patch("asyncio.get_event_loop", side_effect=RuntimeError("No event loop")),
            patch("asyncio.new_event_loop") as mock_new_loop,
            patch("asyncio.set_event_loop") as mock_set_loop,
        ):
            mock_loop = Mock()
            mock_loop.is_running.return_value = False
            mock_loop.run_until_complete = Mock()
            mock_new_loop.return_value = mock_loop

            # Execute
            entity_function(mock_context)

            # Verify new event loop was created
            mock_new_loop.assert_called_once()
            mock_set_loop.assert_called_once_with(mock_loop)

    def test_entity_function_handles_running_event_loop(self) -> None:
        """Test that the entity function handles a running event loop by creating a temporary loop."""
        from unittest.mock import patch

        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity_function = create_agent_entity(mock_agent)

        mock_context = Mock()
        mock_context.operation_name = "run"
        mock_context.entity_key = "conv-running-loop"
        mock_context.get_input.return_value = {"message": "Test"}
        mock_context.get_state.return_value = None

        # Simulate a running event loop
        mock_existing_loop = Mock()
        mock_existing_loop.is_running.return_value = True

        mock_temp_loop = Mock()
        mock_temp_loop.run_until_complete = Mock()
        mock_temp_loop.close = Mock()

        with (
            patch("asyncio.get_event_loop", return_value=mock_existing_loop),
            patch("asyncio.new_event_loop", return_value=mock_temp_loop),
        ):
            # Execute
            entity_function(mock_context)

            # Verify temporary loop was created and closed
            mock_temp_loop.run_until_complete.assert_called_once()
            mock_temp_loop.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
