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
        request = RunRequest(message="Hello", thread_id="thread-default")

        assert request.message == "Hello"
        assert request.role == Role.USER
        assert request.response_format is None
        assert request.enable_tool_calls is True
        assert request.thread_id == "thread-default"

    def test_init_with_all_fields(self) -> None:
        """Test RunRequest initialization with all fields."""
        schema = ModuleStructuredResponse
        request = RunRequest(
            message="Hello",
            thread_id="thread-123",
            role=Role.SYSTEM,
            response_format=schema,
            enable_tool_calls=False,
        )

        assert request.message == "Hello"
        assert request.role == Role.SYSTEM
        assert request.response_format is schema
        assert request.enable_tool_calls is False
        assert request.thread_id == "thread-123"

    def test_init_coerces_string_role(self) -> None:
        """Ensure string role values are coerced into Role instances."""
        request = RunRequest(message="Hello", thread_id="thread-str-role", role="system")  # type: ignore[arg-type]

        assert request.role == Role.SYSTEM

    def test_to_dict_with_defaults(self) -> None:
        """Test to_dict with default values."""
        request = RunRequest(message="Test message", thread_id="thread-to-dict")
        data = request.to_dict()

        assert data["message"] == "Test message"
        assert data["enable_tool_calls"] is True
        assert data["role"] == "user"
        assert "response_format" not in data or data["response_format"] is None
        assert data["thread_id"] == "thread-to-dict"

    def test_to_dict_with_all_fields(self) -> None:
        """Test to_dict with all fields."""
        schema = ModuleStructuredResponse
        request = RunRequest(
            message="Hello",
            thread_id="thread-456",
            role=Role.ASSISTANT,
            response_format=schema,
            enable_tool_calls=False,
        )
        data = request.to_dict()

        assert data["message"] == "Hello"
        assert data["role"] == "assistant"
        assert data["response_format"]["__response_schema_type__"] == "pydantic_model"
        assert data["response_format"]["module"] == schema.__module__
        assert data["response_format"]["qualname"] == schema.__qualname__
        assert data["enable_tool_calls"] is False
        assert data["thread_id"] == "thread-456"

    def test_from_dict_with_defaults(self) -> None:
        """Test from_dict with minimal data."""
        data = {"message": "Hello", "thread_id": "thread-from-dict"}
        request = RunRequest.from_dict(data)

        assert request.message == "Hello"
        assert request.role == Role.USER
        assert request.enable_tool_calls is True
        assert request.thread_id == "thread-from-dict"

    def test_from_dict_with_all_fields(self) -> None:
        """Test from_dict with all fields."""
        data = {
            "message": "Test",
            "role": "system",
            "response_format": {
                "__response_schema_type__": "pydantic_model",
                "module": ModuleStructuredResponse.__module__,
                "qualname": ModuleStructuredResponse.__qualname__,
            },
            "enable_tool_calls": False,
            "thread_id": "thread-789",
        }
        request = RunRequest.from_dict(data)

        assert request.message == "Test"
        assert request.role == Role.SYSTEM
        assert request.response_format is ModuleStructuredResponse
        assert request.enable_tool_calls is False
        assert request.thread_id == "thread-789"

    def test_from_dict_with_unknown_role_preserves_value(self) -> None:
        """Test from_dict keeps custom roles intact."""
        data = {"message": "Test", "role": "reviewer", "thread_id": "thread-with-custom-role"}
        request = RunRequest.from_dict(data)

        assert request.role.value == "reviewer"
        assert request.role != Role.USER

    def test_from_dict_empty_message(self) -> None:
        """Test from_dict with empty message."""
        data = {"thread_id": "thread-empty"}
        request = RunRequest.from_dict(data)

        assert request.message == ""
        assert request.role == Role.USER
        assert request.thread_id == "thread-empty"

    def test_round_trip_dict_conversion(self) -> None:
        """Test round-trip to_dict and from_dict."""
        original = RunRequest(
            message="Test message",
            thread_id="thread-123",
            role=Role.SYSTEM,
            response_format=ModuleStructuredResponse,
            enable_tool_calls=False,
        )

        data = original.to_dict()
        restored = RunRequest.from_dict(data)

        assert restored.message == original.message
        assert restored.role == original.role
        assert restored.response_format is ModuleStructuredResponse
        assert restored.enable_tool_calls == original.enable_tool_calls
        assert restored.thread_id == original.thread_id

    def test_round_trip_with_pydantic_response_format(self) -> None:
        """Ensure Pydantic response formats serialize and deserialize properly."""
        original = RunRequest(
            message="Structured",
            thread_id="thread-pydantic",
            response_format=ModuleStructuredResponse,
        )

        data = original.to_dict()

        assert data["response_format"]["__response_schema_type__"] == "pydantic_model"
        assert data["response_format"]["module"] == ModuleStructuredResponse.__module__
        assert data["response_format"]["qualname"] == ModuleStructuredResponse.__qualname__

        restored = RunRequest.from_dict(data)
        assert restored.response_format is ModuleStructuredResponse

    def test_init_with_correlationId(self) -> None:
        """Test RunRequest initialization with correlationId."""
        request = RunRequest(message="Test message", thread_id="thread-corr-init", correlation_id="corr-123")

        assert request.message == "Test message"
        assert request.correlation_id == "corr-123"

    def test_to_dict_with_correlationId(self) -> None:
        """Test to_dict includes correlationId."""
        request = RunRequest(message="Test", thread_id="thread-corr-to-dict", correlation_id="corr-456")
        data = request.to_dict()

        assert data["message"] == "Test"
        assert data["correlationId"] == "corr-456"

    def test_from_dict_with_correlationId(self) -> None:
        """Test from_dict with correlationId."""
        data = {"message": "Test", "correlationId": "corr-789", "thread_id": "thread-corr-from-dict"}
        request = RunRequest.from_dict(data)

        assert request.message == "Test"
        assert request.correlation_id == "corr-789"
        assert request.thread_id == "thread-corr-from-dict"

    def test_round_trip_with_correlationId(self) -> None:
        """Test round-trip to_dict and from_dict with correlationId."""
        original = RunRequest(
            message="Test message",
            thread_id="thread-123",
            role=Role.SYSTEM,
            correlation_id="corr-123",
        )

        data = original.to_dict()
        restored = RunRequest.from_dict(data)

        assert restored.message == original.message
        assert restored.role == original.role
        assert restored.correlation_id == original.correlation_id
        assert restored.thread_id == original.thread_id

    def test_init_with_orchestration_id(self) -> None:
        """Test RunRequest initialization with orchestration_id."""
        request = RunRequest(
            message="Test message",
            thread_id="thread-orch-init",
            orchestration_id="orch-123",
        )

        assert request.message == "Test message"
        assert request.orchestration_id == "orch-123"

    def test_to_dict_with_orchestration_id(self) -> None:
        """Test to_dict includes orchestrationId."""
        request = RunRequest(
            message="Test",
            thread_id="thread-orch-to-dict",
            orchestration_id="orch-456",
        )
        data = request.to_dict()

        assert data["message"] == "Test"
        assert data["orchestrationId"] == "orch-456"

    def test_to_dict_excludes_orchestration_id_when_none(self) -> None:
        """Test to_dict excludes orchestrationId when not set."""
        request = RunRequest(
            message="Test",
            thread_id="thread-orch-none",
        )
        data = request.to_dict()

        assert "orchestrationId" not in data

    def test_from_dict_with_orchestration_id(self) -> None:
        """Test from_dict with orchestrationId."""
        data = {
            "message": "Test",
            "orchestrationId": "orch-789",
            "thread_id": "thread-orch-from-dict",
        }
        request = RunRequest.from_dict(data)

        assert request.message == "Test"
        assert request.orchestration_id == "orch-789"
        assert request.thread_id == "thread-orch-from-dict"

    def test_round_trip_with_orchestration_id(self) -> None:
        """Test round-trip to_dict and from_dict with orchestration_id."""
        original = RunRequest(
            message="Test message",
            thread_id="thread-123",
            role=Role.SYSTEM,
            correlation_id="corr-123",
            orchestration_id="orch-123",
        )

        data = original.to_dict()
        restored = RunRequest.from_dict(data)

        assert restored.message == original.message
        assert restored.role == original.role
        assert restored.correlation_id == original.correlation_id
        assert restored.orchestration_id == original.orchestration_id
        assert restored.thread_id == original.thread_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
