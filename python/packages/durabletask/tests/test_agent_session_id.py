# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for AgentSessionId and DurableAgentThread."""

import pytest
from agent_framework import AgentThread

from agent_framework_durabletask._models import AgentSessionId, DurableAgentThread


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

    def test_parse_with_agent_name_override(self) -> None:
        """Test parsing @name@key format with agent_name parameter overrides the name."""
        session_id = AgentSessionId.parse("@OriginalAgent@test-key-123", agent_name="OverriddenAgent")

        assert session_id.name == "OverriddenAgent"
        assert session_id.key == "test-key-123"

    def test_parse_without_agent_name_uses_parsed_name(self) -> None:
        """Test parsing @name@key format without agent_name uses name from string."""
        session_id = AgentSessionId.parse("@ParsedAgent@test-key-123")

        assert session_id.name == "ParsedAgent"
        assert session_id.key == "test-key-123"

    def test_parse_plain_string_with_agent_name(self) -> None:
        """Test parsing plain string with agent_name uses entire string as key."""
        session_id = AgentSessionId.parse("simple-thread-123", agent_name="TestAgent")

        assert session_id.name == "TestAgent"
        assert session_id.key == "simple-thread-123"

    def test_parse_plain_string_without_agent_name_raises(self) -> None:
        """Test parsing plain string without agent_name raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AgentSessionId.parse("simple-thread-123")

        assert "Invalid agent session ID format" in str(exc_info.value)


class TestDurableAgentThread:
    """Test suite for DurableAgentThread."""

    def test_init_with_session_id(self) -> None:
        """Test DurableAgentThread initialization with session ID."""
        session_id = AgentSessionId(name="TestAgent", key="test-key")
        thread = DurableAgentThread(session_id=session_id)

        assert thread.session_id is not None
        assert thread.session_id == session_id

    def test_init_without_session_id(self) -> None:
        """Test DurableAgentThread initialization without session ID."""
        thread = DurableAgentThread()

        assert thread.session_id is None

    def test_session_id_setter(self) -> None:
        """Test setting a session ID to an existing thread."""
        thread = DurableAgentThread()
        assert thread.session_id is None

        session_id = AgentSessionId(name="TestAgent", key="test-key")
        thread.session_id = session_id

        assert thread.session_id is not None
        assert thread.session_id == session_id
        assert thread.session_id.name == "TestAgent"

    def test_from_session_id(self) -> None:
        """Test creating DurableAgentThread from session ID."""
        session_id = AgentSessionId(name="TestAgent", key="test-key")
        thread = DurableAgentThread.from_session_id(session_id)

        assert isinstance(thread, DurableAgentThread)
        assert thread.session_id is not None
        assert thread.session_id == session_id
        assert thread.session_id.name == "TestAgent"
        assert thread.session_id.key == "test-key"

    def test_from_session_id_with_service_thread_id(self) -> None:
        """Test creating DurableAgentThread with service thread ID."""
        session_id = AgentSessionId(name="TestAgent", key="test-key")
        thread = DurableAgentThread.from_session_id(session_id, service_thread_id="service-123")

        assert thread.session_id is not None
        assert thread.session_id == session_id
        assert thread.service_thread_id == "service-123"

    async def test_serialize_with_session_id(self) -> None:
        """Test serialization includes session ID."""
        session_id = AgentSessionId(name="TestAgent", key="test-key")
        thread = DurableAgentThread(session_id=session_id)

        serialized = await thread.serialize()

        assert isinstance(serialized, dict)
        assert "durable_session_id" in serialized
        assert serialized["durable_session_id"] == "@TestAgent@test-key"

    async def test_serialize_without_session_id(self) -> None:
        """Test serialization without session ID."""
        thread = DurableAgentThread()

        serialized = await thread.serialize()

        assert isinstance(serialized, dict)
        assert "durable_session_id" not in serialized

    async def test_deserialize_with_session_id(self) -> None:
        """Test deserialization restores session ID."""
        serialized = {
            "service_thread_id": "thread-123",
            "durable_session_id": "@TestAgent@test-key",
        }

        thread = await DurableAgentThread.deserialize(serialized)

        assert isinstance(thread, DurableAgentThread)
        assert thread.session_id is not None
        assert thread.session_id.name == "TestAgent"
        assert thread.session_id.key == "test-key"
        assert thread.service_thread_id == "thread-123"

    async def test_deserialize_without_session_id(self) -> None:
        """Test deserialization without session ID."""
        serialized = {
            "service_thread_id": "thread-456",
        }

        thread = await DurableAgentThread.deserialize(serialized)

        assert isinstance(thread, DurableAgentThread)
        assert thread.session_id is None
        assert thread.service_thread_id == "thread-456"

    async def test_round_trip_serialization(self) -> None:
        """Test round-trip serialization preserves session ID."""
        session_id = AgentSessionId(name="TestAgent", key="test-key-789")
        original = DurableAgentThread(session_id=session_id)

        serialized = await original.serialize()
        restored = await DurableAgentThread.deserialize(serialized)

        assert isinstance(restored, DurableAgentThread)
        assert restored.session_id is not None
        assert restored.session_id.name == session_id.name
        assert restored.session_id.key == session_id.key

    async def test_deserialize_invalid_session_id_type(self) -> None:
        """Test deserialization with invalid session ID type raises error."""
        serialized = {
            "service_thread_id": "thread-123",
            "durable_session_id": 12345,  # Invalid type
        }

        with pytest.raises(ValueError, match="durable_session_id must be a string"):
            await DurableAgentThread.deserialize(serialized)


class TestAgentThreadCompatibility:
    """Test suite for compatibility between AgentThread and DurableAgentThread."""

    async def test_agent_thread_serialize(self) -> None:
        """Test that base AgentThread can be serialized."""
        thread = AgentThread()

        serialized = await thread.serialize()

        assert isinstance(serialized, dict)
        assert "service_thread_id" in serialized

    async def test_agent_thread_deserialize(self) -> None:
        """Test that base AgentThread can be deserialized."""
        thread = AgentThread()
        serialized = await thread.serialize()

        restored = await AgentThread.deserialize(serialized)

        assert isinstance(restored, AgentThread)
        assert restored.service_thread_id == thread.service_thread_id

    async def test_durable_thread_is_agent_thread(self) -> None:
        """Test that DurableAgentThread is an AgentThread."""
        thread = DurableAgentThread()

        assert isinstance(thread, AgentThread)
        assert isinstance(thread, DurableAgentThread)


class TestModelIntegration:
    """Test suite for integration between models."""

    def test_session_id_string_format(self) -> None:
        """Test that AgentSessionId string format is consistent."""
        session_id = AgentSessionId.with_random_key("AgentEntity")
        session_id_str = str(session_id)

        assert session_id_str.startswith("@AgentEntity@")

    async def test_thread_with_session_preserves_on_serialization(self) -> None:
        """Test that thread with session ID preserves it through serialization."""
        session_id = AgentSessionId(name="TestAgent", key="preserved-key")
        thread = DurableAgentThread.from_session_id(session_id)

        # Serialize and deserialize
        serialized = await thread.serialize()
        restored = await DurableAgentThread.deserialize(serialized)

        # Session ID should be preserved
        assert restored.session_id is not None
        assert restored.session_id.name == "TestAgent"
        assert restored.session_id.key == "preserved-key"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
