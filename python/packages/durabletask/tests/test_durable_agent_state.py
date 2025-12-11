# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableAgentState and related classes."""

from datetime import datetime

import pytest

from agent_framework_durabletask._durable_agent_state import (
    DurableAgentState,
    DurableAgentStateMessage,
    DurableAgentStateRequest,
    DurableAgentStateTextContent,
)
from agent_framework_durabletask._models import RunRequest


class TestDurableAgentStateRequestOrchestrationId:
    """Test suite for DurableAgentStateRequest orchestration_id field."""

    def test_request_with_orchestration_id(self) -> None:
        """Test creating a request with an orchestration_id."""
        request = DurableAgentStateRequest(
            correlation_id="corr-123",
            created_at=datetime.now(),
            messages=[
                DurableAgentStateMessage(
                    role="user",
                    contents=[DurableAgentStateTextContent(text="test")],
                )
            ],
            orchestration_id="orch-456",
        )

        assert request.orchestration_id == "orch-456"

    def test_request_to_dict_includes_orchestration_id(self) -> None:
        """Test that to_dict includes orchestrationId when set."""
        request = DurableAgentStateRequest(
            correlation_id="corr-123",
            created_at=datetime.now(),
            messages=[
                DurableAgentStateMessage(
                    role="user",
                    contents=[DurableAgentStateTextContent(text="test")],
                )
            ],
            orchestration_id="orch-789",
        )

        data = request.to_dict()

        assert "orchestrationId" in data
        assert data["orchestrationId"] == "orch-789"

    def test_request_to_dict_excludes_orchestration_id_when_none(self) -> None:
        """Test that to_dict excludes orchestrationId when not set."""
        request = DurableAgentStateRequest(
            correlation_id="corr-123",
            created_at=datetime.now(),
            messages=[
                DurableAgentStateMessage(
                    role="user",
                    contents=[DurableAgentStateTextContent(text="test")],
                )
            ],
        )

        data = request.to_dict()

        assert "orchestrationId" not in data

    def test_request_from_dict_with_orchestration_id(self) -> None:
        """Test from_dict correctly parses orchestrationId."""
        data = {
            "$type": "request",
            "correlationId": "corr-123",
            "createdAt": "2024-01-01T00:00:00Z",
            "messages": [{"role": "user", "contents": [{"$type": "text", "text": "test"}]}],
            "orchestrationId": "orch-from-dict",
        }

        request = DurableAgentStateRequest.from_dict(data)

        assert request.orchestration_id == "orch-from-dict"

    def test_request_from_run_request_with_orchestration_id(self) -> None:
        """Test from_run_request correctly transfers orchestration_id."""
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
            orchestration_id="orch-from-run-request",
        )

        durable_request = DurableAgentStateRequest.from_run_request(run_request)

        assert durable_request.orchestration_id == "orch-from-run-request"

    def test_request_from_run_request_without_orchestration_id(self) -> None:
        """Test from_run_request correctly handles missing orchestration_id."""
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
        )

        durable_request = DurableAgentStateRequest.from_run_request(run_request)

        assert durable_request.orchestration_id is None


class TestDurableAgentStateMessageCreatedAt:
    """Test suite for DurableAgentStateMessage created_at field handling."""

    def test_message_from_run_request_without_created_at_preserves_none(self) -> None:
        """Test from_run_request preserves None created_at instead of defaulting to current time.

        When a RunRequest has no created_at value, the resulting DurableAgentStateMessage
        should also have None for created_at, not default to current UTC time.
        """
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
            created_at=None,  # Explicitly None
        )

        durable_message = DurableAgentStateMessage.from_run_request(run_request)

        assert durable_message.created_at is None

    def test_message_from_run_request_with_created_at_parses_correctly(self) -> None:
        """Test from_run_request correctly parses a valid created_at timestamp."""
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
            created_at=datetime(2024, 1, 15, 10, 30, 0),
        )

        durable_message = DurableAgentStateMessage.from_run_request(run_request)

        assert durable_message.created_at is not None
        assert durable_message.created_at.year == 2024
        assert durable_message.created_at.month == 1
        assert durable_message.created_at.day == 15


class TestDurableAgentState:
    """Test suite for DurableAgentState."""

    def test_schema_version(self) -> None:
        """Test that schema version is set correctly."""
        state = DurableAgentState()
        assert state.schema_version == "1.1.0"

    def test_to_dict_serialization(self) -> None:
        """Test that to_dict produces correct structure."""
        state = DurableAgentState()
        data = state.to_dict()

        assert "schemaVersion" in data
        assert "data" in data
        assert data["schemaVersion"] == "1.1.0"
        assert "conversationHistory" in data["data"]

    def test_from_dict_deserialization(self) -> None:
        """Test that from_dict restores state correctly."""
        original_data = {
            "schemaVersion": "1.1.0",
            "data": {
                "conversationHistory": [
                    {
                        "$type": "request",
                        "correlationId": "test-123",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "messages": [
                            {
                                "role": "user",
                                "contents": [{"$type": "text", "text": "Hello"}],
                            }
                        ],
                    }
                ]
            },
        }

        state = DurableAgentState.from_dict(original_data)

        assert state.schema_version == "1.1.0"
        assert len(state.data.conversation_history) == 1
        assert isinstance(state.data.conversation_history[0], DurableAgentStateRequest)

    def test_round_trip_serialization(self) -> None:
        """Test that round-trip serialization preserves data."""
        state = DurableAgentState()
        state.data.conversation_history.append(
            DurableAgentStateRequest(
                correlation_id="test-456",
                created_at=datetime.now(),
                messages=[
                    DurableAgentStateMessage(
                        role="user",
                        contents=[DurableAgentStateTextContent(text="Test message")],
                    )
                ],
            )
        )

        data = state.to_dict()
        restored = DurableAgentState.from_dict(data)

        assert restored.schema_version == state.schema_version
        assert len(restored.data.conversation_history) == len(state.data.conversation_history)
        assert restored.data.conversation_history[0].correlation_id == "test-456"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
