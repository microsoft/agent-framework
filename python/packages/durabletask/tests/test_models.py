# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for data models (RunRequest)."""

import pytest
from agent_framework import Role
from pydantic import BaseModel

from agent_framework_durabletask._models import RunRequest


class ModuleStructuredResponse(BaseModel):
    value: int


class TestRunRequest:
    """Test suite for RunRequest."""

    def test_init_with_defaults(self) -> None:
        """Test RunRequest initialization with defaults."""
        request = RunRequest(message="Hello", correlation_id="corr-001")

        assert request.message == "Hello"
        assert request.correlation_id == "corr-001"
        assert request.role == Role.USER
        assert request.response_format is None
        assert request.enable_tool_calls is True
        assert request.wait_for_response is True

    def test_init_with_all_fields(self) -> None:
        """Test RunRequest initialization with all fields."""
        schema = ModuleStructuredResponse
        request = RunRequest(
            message="Hello",
            correlation_id="corr-002",
            role=Role.SYSTEM,
            response_format=schema,
            enable_tool_calls=False,
            wait_for_response=False,
        )

        assert request.message == "Hello"
        assert request.correlation_id == "corr-002"
        assert request.role == Role.SYSTEM
        assert request.response_format is schema
        assert request.enable_tool_calls is False
        assert request.wait_for_response is False

    def test_init_coerces_string_role(self) -> None:
        """Ensure string role values are coerced into Role instances."""
        request = RunRequest(message="Hello", correlation_id="corr-003", role="system")  # type: ignore[arg-type]

        assert request.role == Role.SYSTEM

    def test_to_dict_with_defaults(self) -> None:
        """Test to_dict with default values."""
        request = RunRequest(message="Test message", correlation_id="corr-004")
        data = request.to_dict()

        assert data["message"] == "Test message"
        assert data["enable_tool_calls"] is True
        assert data["wait_for_response"] is True
        assert data["role"] == "user"
        assert data["correlationId"] == "corr-004"
        assert "response_format" not in data or data["response_format"] is None
        assert "thread_id" not in data

    def test_to_dict_with_all_fields(self) -> None:
        """Test to_dict with all fields."""
        schema = ModuleStructuredResponse
        request = RunRequest(
            message="Hello",
            correlation_id="corr-005",
            role=Role.ASSISTANT,
            response_format=schema,
            enable_tool_calls=False,
            wait_for_response=False,
        )
        data = request.to_dict()

        assert data["message"] == "Hello"
        assert data["correlationId"] == "corr-005"
        assert data["role"] == "assistant"
        assert data["response_format"]["__response_schema_type__"] == "pydantic_model"
        assert data["response_format"]["module"] == schema.__module__
        assert data["response_format"]["qualname"] == schema.__qualname__
        assert data["enable_tool_calls"] is False
        assert data["wait_for_response"] is False
        assert "thread_id" not in data

    def test_from_dict_with_defaults(self) -> None:
        """Test from_dict with minimal data."""
        data = {"message": "Hello", "correlationId": "corr-006"}
        request = RunRequest.from_dict(data)

        assert request.message == "Hello"
        assert request.correlation_id == "corr-006"
        assert request.role == Role.USER
        assert request.enable_tool_calls is True
        assert request.wait_for_response is True

    def test_from_dict_ignores_thread_id_field(self) -> None:
        """Ensure legacy thread_id input does not break RunRequest parsing."""
        request = RunRequest.from_dict({"message": "Hello", "correlationId": "corr-007", "thread_id": "ignored"})

        assert request.message == "Hello"

    def test_from_dict_with_all_fields(self) -> None:
        """Test from_dict with all fields."""
        data = {
            "message": "Test",
            "correlationId": "corr-008",
            "role": "system",
            "response_format": {
                "__response_schema_type__": "pydantic_model",
                "module": ModuleStructuredResponse.__module__,
                "qualname": ModuleStructuredResponse.__qualname__,
            },
            "enable_tool_calls": False,
        }
        request = RunRequest.from_dict(data)

        assert request.message == "Test"
        assert request.correlation_id == "corr-008"
        assert request.role == Role.SYSTEM
        assert request.response_format is ModuleStructuredResponse
        assert request.enable_tool_calls is False

    def test_from_dict_unknown_role_preserves_value(self) -> None:
        """Test from_dict keeps custom roles intact."""
        data = {"message": "Test", "correlationId": "corr-009", "role": "reviewer"}
        request = RunRequest.from_dict(data)

        assert request.role.value == "reviewer"
        assert request.role != Role.USER

    def test_from_dict_empty_message(self) -> None:
        """Test from_dict with empty message."""
        request = RunRequest.from_dict({"correlationId": "corr-010"})

        assert request.message == ""
        assert request.correlation_id == "corr-010"
        assert request.role == Role.USER

    def test_from_dict_missing_correlation_id_raises(self) -> None:
        """Test from_dict raises when correlationId is missing."""
        with pytest.raises(ValueError, match="correlationId is required"):
            RunRequest.from_dict({"message": "Test"})

    def test_round_trip_dict_conversion(self) -> None:
        """Test round-trip to_dict and from_dict."""
        original = RunRequest(
            message="Test message",
            correlation_id="corr-011",
            role=Role.SYSTEM,
            response_format=ModuleStructuredResponse,
            enable_tool_calls=False,
        )

        data = original.to_dict()
        restored = RunRequest.from_dict(data)

        assert restored.message == original.message
        assert restored.correlation_id == original.correlation_id
        assert restored.role == original.role
        assert restored.response_format is ModuleStructuredResponse
        assert restored.enable_tool_calls == original.enable_tool_calls

    def test_round_trip_with_pydantic_response_format(self) -> None:
        """Ensure Pydantic response formats serialize and deserialize properly."""
        original = RunRequest(
            message="Structured",
            correlation_id="corr-012",
            response_format=ModuleStructuredResponse,
        )

        data = original.to_dict()

        assert data["response_format"]["__response_schema_type__"] == "pydantic_model"
        assert data["response_format"]["module"] == ModuleStructuredResponse.__module__
        assert data["response_format"]["qualname"] == ModuleStructuredResponse.__qualname__

        restored = RunRequest.from_dict(data)
        assert restored.response_format is ModuleStructuredResponse

    def test_round_trip_with_options(self) -> None:
        """Ensure options are preserved and response_format is deserialized."""
        original = RunRequest(
            message="Test",
            correlation_id="corr-opts-1",
            response_format=ModuleStructuredResponse,
            enable_tool_calls=False,
            options={
                "response_format": ModuleStructuredResponse,
                "enable_tool_calls": False,
                "custom": "value",
            },
        )

        data = original.to_dict()
        assert data["options"]["custom"] == "value"

        restored = RunRequest.from_dict(data)
        assert restored.options is not None
        assert restored.options["custom"] == "value"
        assert restored.options["response_format"] is ModuleStructuredResponse

    def test_init_with_correlationId(self) -> None:
        """Test RunRequest initialization with correlationId."""
        request = RunRequest(message="Test message", correlation_id="corr-123")

        assert request.message == "Test message"
        assert request.correlation_id == "corr-123"

    def test_to_dict_with_correlationId(self) -> None:
        """Test to_dict includes correlationId."""
        request = RunRequest(message="Test", correlation_id="corr-456")
        data = request.to_dict()

        assert data["message"] == "Test"
        assert data["correlationId"] == "corr-456"

    def test_from_dict_with_correlationId(self) -> None:
        """Test from_dict with correlationId."""
        data = {"message": "Test", "correlationId": "corr-789"}
        request = RunRequest.from_dict(data)

        assert request.message == "Test"
        assert request.correlation_id == "corr-789"

    def test_round_trip_with_correlationId(self) -> None:
        """Test round-trip to_dict and from_dict with correlationId."""
        original = RunRequest(
            message="Test message",
            role=Role.SYSTEM,
            correlation_id="corr-124",
        )

        data = original.to_dict()
        restored = RunRequest.from_dict(data)

        assert restored.message == original.message
        assert restored.role == original.role
        assert restored.correlation_id == original.correlation_id

    def test_init_with_orchestration_id(self) -> None:
        """Test RunRequest initialization with orchestration_id."""
        request = RunRequest(
            message="Test message",
            correlation_id="corr-125",
            orchestration_id="orch-123",
        )

        assert request.message == "Test message"
        assert request.orchestration_id == "orch-123"

    def test_to_dict_with_orchestration_id(self) -> None:
        """Test to_dict includes orchestrationId."""
        request = RunRequest(
            message="Test",
            correlation_id="corr-126",
            orchestration_id="orch-456",
        )
        data = request.to_dict()

        assert data["message"] == "Test"
        assert data["orchestrationId"] == "orch-456"

    def test_to_dict_excludes_orchestration_id_when_none(self) -> None:
        """Test to_dict excludes orchestrationId when not set."""
        request = RunRequest(
            message="Test",
            correlation_id="corr-127",
        )
        data = request.to_dict()

        assert "orchestrationId" not in data

    def test_from_dict_with_orchestration_id(self) -> None:
        """Test from_dict with orchestrationId."""
        data = {
            "message": "Test",
            "correlationId": "corr-128",
            "orchestrationId": "orch-789",
        }
        request = RunRequest.from_dict(data)

        assert request.message == "Test"
        assert request.orchestration_id == "orch-789"

    def test_round_trip_with_orchestration_id(self) -> None:
        """Test round-trip to_dict and from_dict with orchestration_id."""
        original = RunRequest(
            message="Test message",
            role=Role.SYSTEM,
            correlation_id="corr-129",
            orchestration_id="orch-123",
        )

        data = original.to_dict()
        restored = RunRequest.from_dict(data)

        assert restored.message == original.message
        assert restored.role == original.role
        assert restored.correlation_id == original.correlation_id
        assert restored.orchestration_id == original.orchestration_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
