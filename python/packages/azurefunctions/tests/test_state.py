# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for AgentState correlation ID tracking."""

from unittest.mock import Mock

import pytest
from agent_framework import AgentRunResponse

from agent_framework_azurefunctions._state import AgentState


class TestAgentStateCorrelationId:
    """Test suite for AgentState correlation ID tracking."""

    def _create_mock_response(self, text: str = "Response") -> Mock:
        """Create a mock AgentRunResponse with the provided text."""
        mock_response = Mock(spec=AgentRunResponse)
        mock_response.to_dict.return_value = {"text": text, "messages": []}
        return mock_response

    def test_add_assistant_message_with_correlation_id(self) -> None:
        state = AgentState()
        state.add_user_message("Hello", correlation_id="corr-123-request")
        state.add_assistant_message("Response", self._create_mock_response(), correlation_id="corr-123")
        message_metadata = state.conversation_history[-1].additional_properties or {}
        assert message_metadata.get("correlation_id") == "corr-123"

        response_data = state.try_get_agent_response("corr-123")
        assert response_data is not None
        assert response_data["content"] == "Response"
        assert response_data["agent_response"] == {"text": "Response", "messages": []}

    def test_try_get_agent_response_returns_response(self) -> None:
        state = AgentState()
        state.add_user_message("Hello", correlation_id="corr-200-request")
        state.add_assistant_message("Response", self._create_mock_response(), correlation_id="corr-456")

        response_data = state.try_get_agent_response("corr-456")

        assert response_data is not None
        assert response_data["content"] == "Response"

    def test_try_get_agent_response_returns_none_for_missing_id(self) -> None:
        state = AgentState()
        state.add_user_message("Hello", correlation_id="corr-300-request")
        state.add_assistant_message("Response", self._create_mock_response(), correlation_id="corr-123")

        assert state.try_get_agent_response("non-existent") is None

    def test_multiple_responses_tracked_separately(self) -> None:
        state = AgentState()

        for index in range(3):
            state.add_user_message(f"Message {index}", correlation_id=f"corr-{index}-request")
            state.add_assistant_message(
                f"Response {index}",
                self._create_mock_response(text=f"Response {index}"),
                correlation_id=f"corr-{index}",
            )

        for index in range(3):
            payload = state.try_get_agent_response(f"corr-{index}")
            assert payload is not None
            assert payload["content"] == f"Response {index}"

    def test_add_assistant_message_without_correlation_id(self) -> None:
        state = AgentState()
        state.add_user_message("Hello", correlation_id="corr-400-request")
        state.add_assistant_message("Response", self._create_mock_response())

        assert state.try_get_agent_response("missing") is None
        assert state.last_response == "Response"

    def test_to_dict_does_not_duplicate_agent_responses(self) -> None:
        state = AgentState()
        state.add_user_message("Hello", correlation_id="corr-500-request")
        state.add_assistant_message("Response", self._create_mock_response(), correlation_id="corr-123")

        state_snapshot = state.to_dict()

        assert "agent_responses" not in state_snapshot
        metadata = state_snapshot["conversation_history"][-1]["additional_properties"]
        assert metadata["correlation_id"] == "corr-123"

    def test_restore_state_preserves_agent_response_lookup(self) -> None:
        state = AgentState()
        state.add_user_message("Hello", correlation_id="corr-600-request")
        state.add_assistant_message("Response", self._create_mock_response(), correlation_id="corr-123")

        restored_state = AgentState()
        restored_state.restore_state(state.to_dict())

        payload = restored_state.try_get_agent_response("corr-123")
        assert payload is not None
        assert payload["content"] == "Response"

    def test_reset_clears_conversation_history(self) -> None:
        state = AgentState()
        state.add_user_message("Hello", correlation_id="corr-700-request")
        state.add_assistant_message("Response", self._create_mock_response(), correlation_id="corr-123")

        state.reset()

        assert len(state.conversation_history) == 0
        assert state.try_get_agent_response("corr-123") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
