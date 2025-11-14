# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for data models (AgentSessionId, RunRequest, AgentResponse)."""

import azure.durable_functions as df
import pytest
from agent_framework import Role
from pydantic import BaseModel

from agent_framework_azurefunctions._models import AgentResponse, AgentSessionId, RunRequest


class ModuleStructuredResponse(BaseModel):
    value: int


class TestAgentSessionId:
    """Test suite for AgentSessionId."""

    def test_init_creates_session_id(self) -> None:
        """Test that AgentSessionId initializes correctly."""
        session_id = AgentSessionId(name="AgentEntity", key="test-key-123")

        assert session_id.name == "AgentEntity"
        assert session_id.key == "test-key-123"

    def test_with_random_key_generates_guid(self) -> None:
        """Test that with_random_key generates a GUID."""
        session_id = AgentSessionId.with_random_key(name="AgentEntity")

        assert session_id.name == "AgentEntity"
        assert len(session_id.key) == 32  # UUID hex is 32 chars
        # Verify it's a valid hex string
        int(session_id.key, 16)

    def test_with_random_key_unique_keys(self) -> None:
        """Test that with_random_key generates unique keys."""
        session_id1 = AgentSessionId.with_random_key(name="AgentEntity")
        session_id2 = AgentSessionId.with_random_key(name="AgentEntity")

        assert session_id1.key != session_id2.key

    def test_to_entity_id_conversion(self) -> None:
        """Test conversion to EntityId."""
        session_id = AgentSessionId(name="AgentEntity", key="test-key")
        entity_id = session_id.to_entity_id()

        assert isinstance(entity_id, df.EntityId)
        assert entity_id.name == "dafx-AgentEntity"
        assert entity_id.key == "test-key"

    def test_from_entity_id_conversion(self) -> None:
        """Test creation from EntityId."""
        entity_id = df.EntityId(name="dafx-AgentEntity", key="test-key")
        session_id = AgentSessionId.from_entity_id(entity_id)

        assert isinstance(session_id, AgentSessionId)
        assert session_id.name == "AgentEntity"
        assert session_id.key == "test-key"

    def test_round_trip_entity_id_conversion(self) -> None:
        """Test round-trip conversion to and from EntityId."""
        original = AgentSessionId(name="AgentEntity", key="test-key")
        entity_id = original.to_entity_id()
        restored = AgentSessionId.from_entity_id(entity_id)

        assert restored.name == original.name
        assert restored.key == original.key

    def test_str_representation(self) -> None:
        """Test string representation."""
        session_id = AgentSessionId(name="AgentEntity", key="test-key-123")
        str_repr = str(session_id)

        assert str_repr == "@AgentEntity@test-key-123"

    def test_repr_representation(self) -> None:
        """Test repr representation."""
        session_id = AgentSessionId(name="AgentEntity", key="test-key")
        repr_str = repr(session_id)

        assert "AgentSessionId" in repr_str
        assert "AgentEntity" in repr_str
        assert "test-key" in repr_str

    def test_parse_valid_session_id(self) -> None:
        """Test parsing valid session ID string."""
        session_id = AgentSessionId.parse("@AgentEntity@test-key-123")

        assert session_id.name == "AgentEntity"
        assert session_id.key == "test-key-123"

    def test_parse_invalid_format_no_prefix(self) -> None:
        """Test parsing invalid format without @ prefix."""
        with pytest.raises(ValueError) as exc_info:
            AgentSessionId.parse("AgentEntity@test-key")

        assert "Invalid agent session ID format" in str(exc_info.value)

    def test_parse_invalid_format_single_part(self) -> None:
        """Test parsing invalid format with single part."""
        with pytest.raises(ValueError) as exc_info:
            AgentSessionId.parse("@AgentEntity")

        assert "Invalid agent session ID format" in str(exc_info.value)

    def test_parse_with_multiple_at_signs_in_key(self) -> None:
        """Test parsing with @ signs in the key."""
        session_id = AgentSessionId.parse("@AgentEntity@key-with@symbols")

        assert session_id.name == "AgentEntity"
        assert session_id.key == "key-with@symbols"

    def test_parse_round_trip(self) -> None:
        """Test round-trip parse and string conversion."""
        original = AgentSessionId(name="AgentEntity", key="test-key")
        str_repr = str(original)
        parsed = AgentSessionId.parse(str_repr)

        assert parsed.name == original.name
        assert parsed.key == original.key

    def test_to_entity_name_adds_prefix(self) -> None:
        """Test that to_entity_name adds the dafx- prefix."""
        entity_name = AgentSessionId.to_entity_name("TestAgent")
        assert entity_name == "dafx-TestAgent"

    def test_from_entity_id_strips_prefix(self) -> None:
        """Test that from_entity_id strips the dafx- prefix."""
        entity_id = df.EntityId(name="dafx-TestAgent", key="key123")
        session_id = AgentSessionId.from_entity_id(entity_id)

        assert session_id.name == "TestAgent"
        assert session_id.key == "key123"

    def test_from_entity_id_raises_without_prefix(self) -> None:
        """Test that from_entity_id raises ValueError when entity name lacks the prefix."""
        entity_id = df.EntityId(name="TestAgent", key="key123")

        with pytest.raises(ValueError) as exc_info:
            AgentSessionId.from_entity_id(entity_id)

        assert "not a valid agent session ID" in str(exc_info.value)
        assert "dafx-" in str(exc_info.value)


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

    def test_init_with_correlation_id(self) -> None:
        """Test RunRequest initialization with correlation_id."""
        request = RunRequest(message="Test message", thread_id="thread-corr-init", correlation_id="corr-123")

        assert request.message == "Test message"
        assert request.correlation_id == "corr-123"

    def test_to_dict_with_correlation_id(self) -> None:
        """Test to_dict includes correlation_id."""
        request = RunRequest(message="Test", thread_id="thread-corr-to-dict", correlation_id="corr-456")
        data = request.to_dict()

        assert data["message"] == "Test"
        assert data["correlation_id"] == "corr-456"

    def test_from_dict_with_correlation_id(self) -> None:
        """Test from_dict with correlation_id."""
        data = {"message": "Test", "correlation_id": "corr-789", "thread_id": "thread-corr-from-dict"}
        request = RunRequest.from_dict(data)

        assert request.message == "Test"
        assert request.correlation_id == "corr-789"
        assert request.thread_id == "thread-corr-from-dict"

    def test_round_trip_with_correlation_id(self) -> None:
        """Test round-trip to_dict and from_dict with correlation_id."""
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


class TestAgentResponse:
    """Test suite for AgentResponse."""

    def test_init_with_required_fields(self) -> None:
        """Test AgentResponse initialization with required fields."""
        response = AgentResponse(
            response="Test response", message="Test message", thread_id="thread-123", status="success"
        )

        assert response.response == "Test response"
        assert response.message == "Test message"
        assert response.thread_id == "thread-123"
        assert response.status == "success"
        assert response.message_count == 0
        assert response.error is None
        assert response.error_type is None
        assert response.structured_response is None

    def test_init_with_all_fields(self) -> None:
        """Test AgentResponse initialization with all fields."""
        structured = {"answer": "42"}
        response = AgentResponse(
            response=None,
            message="What is the answer?",
            thread_id="thread-456",
            status="success",
            message_count=5,
            error=None,
            error_type=None,
            structured_response=structured,
        )

        assert response.response is None
        assert response.structured_response == structured
        assert response.message_count == 5

    def test_to_dict_with_text_response(self) -> None:
        """Test to_dict with text response."""
        response = AgentResponse(
            response="Text response", message="Message", thread_id="thread-1", status="success", message_count=3
        )
        data = response.to_dict()

        assert data["response"] == "Text response"
        assert data["message"] == "Message"
        assert data["thread_id"] == "thread-1"
        assert data["status"] == "success"
        assert data["message_count"] == 3
        assert "structured_response" not in data
        assert "error" not in data
        assert "error_type" not in data

    def test_to_dict_with_structured_response(self) -> None:
        """Test to_dict with structured response."""
        structured = {"answer": 42, "confidence": 0.95}
        response = AgentResponse(
            response=None,
            message="Question",
            thread_id="thread-2",
            status="success",
            structured_response=structured,
        )
        data = response.to_dict()

        assert data["structured_response"] == structured
        assert "response" not in data

    def test_to_dict_with_error(self) -> None:
        """Test to_dict with error."""
        response = AgentResponse(
            response=None,
            message="Failed message",
            thread_id="thread-3",
            status="error",
            error="Something went wrong",
            error_type="ValueError",
        )
        data = response.to_dict()

        assert data["status"] == "error"
        assert data["error"] == "Something went wrong"
        assert data["error_type"] == "ValueError"

    def test_to_dict_prefers_structured_over_text(self) -> None:
        """Test to_dict prefers structured_response over response."""
        structured = {"result": "structured"}
        response = AgentResponse(
            response="Text response",
            message="Message",
            thread_id="thread-4",
            status="success",
            structured_response=structured,
        )
        data = response.to_dict()

        assert "structured_response" in data
        assert data["structured_response"] == structured
        # Text response should not be included when structured is present
        assert "response" not in data


class TestModelIntegration:
    """Test suite for integration between models."""

    def test_run_request_with_session_id(self) -> None:
        """Test using RunRequest with AgentSessionId."""
        session_id = AgentSessionId.with_random_key("AgentEntity")
        request = RunRequest(message="Test message", thread_id=str(session_id))

        assert request.thread_id is not None
        assert request.thread_id == str(session_id)
        assert request.thread_id.startswith("@AgentEntity@")

    def test_response_from_run_request(self) -> None:
        """Test creating AgentResponse from RunRequest."""
        request = RunRequest(message="What is 2+2?", thread_id="thread-123", role=Role.USER)

        response = AgentResponse(
            response="4",
            message=request.message,
            thread_id=request.thread_id,
            status="success",
            message_count=1,
        )

        assert response.message == request.message
        assert response.thread_id == request.thread_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
