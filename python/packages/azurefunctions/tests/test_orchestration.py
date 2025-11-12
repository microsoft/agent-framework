# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for orchestration support (DurableAIAgent)."""

from typing import Any
from unittest.mock import Mock

import pytest
from agent_framework import AgentThread

from agent_framework_azurefunctions import AgentFunctionApp, DurableAIAgent
from agent_framework_azurefunctions._models import AgentSessionId, DurableAgentThread


def _app_with_registered_agents(*agent_names: str) -> AgentFunctionApp:
    app = AgentFunctionApp(enable_health_check=False, enable_http_endpoints=False)
    for name in agent_names:
        agent = Mock()
        agent.name = name
        app.add_agent(agent)
    return app


class TestDurableAIAgent:
    """Test suite for DurableAIAgent wrapper."""

    def test_init(self) -> None:
        """Test DurableAIAgent initialization."""
        mock_context = Mock()
        mock_context.instance_id = "test-instance-123"

        agent = DurableAIAgent(mock_context, "TestAgent")

        assert agent.context == mock_context
        assert agent.agent_name == "TestAgent"

    def test_implements_agent_protocol(self) -> None:
        """Test that DurableAIAgent implements AgentProtocol."""
        from agent_framework import AgentProtocol

        mock_context = Mock()
        agent = DurableAIAgent(mock_context, "TestAgent")

        # Check that agent satisfies AgentProtocol
        assert isinstance(agent, AgentProtocol)

    def test_has_agent_protocol_properties(self) -> None:
        """Test that DurableAIAgent has AgentProtocol properties."""
        mock_context = Mock()
        agent = DurableAIAgent(mock_context, "TestAgent")

        # AgentProtocol properties
        assert hasattr(agent, "id")
        assert hasattr(agent, "name")
        assert hasattr(agent, "description")
        assert hasattr(agent, "display_name")

        # Verify values
        assert agent.name == "TestAgent"
        assert agent.description == "Durable agent proxy for TestAgent"
        assert agent.display_name == "TestAgent"
        assert agent.id is not None  # Auto-generated UUID

    def test_get_new_thread(self) -> None:
        """Test creating a new agent thread."""
        mock_context = Mock()
        mock_context.instance_id = "test-instance-456"
        mock_context.new_uuid = Mock(return_value="test-guid-456")

        agent = DurableAIAgent(mock_context, "WriterAgent")
        thread = agent.get_new_thread()

        assert isinstance(thread, DurableAgentThread)
        assert thread.session_id is not None
        session_id = thread.session_id
        assert isinstance(session_id, AgentSessionId)
        assert session_id.name == "WriterAgent"
        assert session_id.key == "test-guid-456"
        mock_context.new_uuid.assert_called_once()

    def test_get_new_thread_deterministic(self) -> None:
        """Test that get_new_thread creates deterministic session IDs."""

        mock_context = Mock()
        mock_context.instance_id = "test-instance-789"
        mock_context.new_uuid = Mock(side_effect=["session-guid-1", "session-guid-2"])

        agent = DurableAIAgent(mock_context, "EditorAgent")

        # Create multiple threads - they should have unique session IDs
        thread1 = agent.get_new_thread()
        thread2 = agent.get_new_thread()

        assert isinstance(thread1, DurableAgentThread)
        assert isinstance(thread2, DurableAgentThread)

        session_id1 = thread1.session_id
        session_id2 = thread2.session_id
        assert session_id1 is not None and session_id2 is not None
        assert isinstance(session_id1, AgentSessionId)
        assert isinstance(session_id2, AgentSessionId)
        assert session_id1.name == "EditorAgent"
        assert session_id2.name == "EditorAgent"
        assert session_id1.key == "session-guid-1"
        assert session_id2.key == "session-guid-2"
        assert mock_context.new_uuid.call_count == 2

    def test_run_creates_entity_call(self) -> None:
        """Test that run() creates proper entity call and returns a Task."""
        mock_context = Mock()
        mock_context.instance_id = "test-instance-001"
        mock_context.new_uuid = Mock(side_effect=["thread-guid", "correlation-guid"])

        # Mock call_entity to return a Task-like object
        mock_task = Mock()
        mock_task._is_scheduled = False  # Task attribute that orchestration checks

        mock_context.call_entity = Mock(return_value=mock_task)

        agent = DurableAIAgent(mock_context, "TestAgent")

        # Create thread
        thread = agent.get_new_thread()

        # Call run() - it should return the Task directly
        task = agent.run(messages="Test message", thread=thread, enable_tool_calls=True)

        # Verify run() returns the Task from call_entity
        assert task == mock_task

        # Verify call_entity was called with correct parameters
        assert mock_context.call_entity.called
        call_args = mock_context.call_entity.call_args
        entity_id, operation, request = call_args[0]

        assert operation == "run_agent"
        assert request["message"] == "Test message"
        assert request["enable_tool_calls"] is True
        assert "correlation_id" in request
        assert request["correlation_id"] == "correlation-guid"
        assert "thread_id" in request
        assert request["thread_id"] == "thread-guid"

    def test_run_without_thread(self) -> None:
        """Test that run() works without explicit thread (creates unique session key)."""
        mock_context = Mock()
        mock_context.instance_id = "test-instance-002"
        # Two calls to new_uuid: one for session_key, one for correlation_id
        mock_context.new_uuid = Mock(side_effect=["auto-generated-guid", "correlation-guid"])

        mock_task = Mock()
        mock_task._is_scheduled = False
        mock_context.call_entity = Mock(return_value=mock_task)

        agent = DurableAIAgent(mock_context, "TestAgent")

        # Call without thread
        task = agent.run(messages="Test message")

        assert task == mock_task

        # Verify the entity ID uses the auto-generated GUID with dafx- prefix
        call_args = mock_context.call_entity.call_args
        entity_id = call_args[0][0]
        assert entity_id.name == "dafx-TestAgent"
        assert entity_id.key == "auto-generated-guid"
        # Should be called twice: once for session_key, once for correlation_id
        assert mock_context.new_uuid.call_count == 2

    def test_run_with_response_format(self) -> None:
        """Test that run() passes response format correctly."""
        mock_context = Mock()
        mock_context.instance_id = "test-instance-003"

        mock_task = Mock()
        mock_task._is_scheduled = False
        mock_context.call_entity = Mock(return_value=mock_task)

        agent = DurableAIAgent(mock_context, "TestAgent")

        from pydantic import BaseModel

        class SampleSchema(BaseModel):
            key: str

        # Create thread and call
        thread = agent.get_new_thread()

        task = agent.run(messages="Test message", thread=thread, response_format=SampleSchema)

        assert task == mock_task

        # Verify schema was passed in the call_entity arguments
        call_args = mock_context.call_entity.call_args
        input_data = call_args[0][2]  # Third argument is input_data
        assert "response_format" in input_data
        assert input_data["response_format"]["__response_schema_type__"] == "pydantic_model"
        assert input_data["response_format"]["module"] == SampleSchema.__module__
        assert input_data["response_format"]["qualname"] == SampleSchema.__qualname__

    def test_messages_to_string(self) -> None:
        """Test converting ChatMessage list to string."""
        from agent_framework import ChatMessage

        mock_context = Mock()
        agent = DurableAIAgent(mock_context, "TestAgent")

        messages = [
            ChatMessage(role="user", text="Hello"),
            ChatMessage(role="assistant", text="Hi there"),
            ChatMessage(role="user", text="How are you?"),
        ]

        result = agent._messages_to_string(messages)

        assert result == "Hello\nHi there\nHow are you?"

    def test_run_with_chat_message(self) -> None:
        """Test that run() handles ChatMessage input."""
        from agent_framework import ChatMessage

        mock_context = Mock()
        mock_context.new_uuid = Mock(side_effect=["thread-guid", "correlation-guid"])
        mock_task = Mock()
        mock_context.call_entity = Mock(return_value=mock_task)

        agent = DurableAIAgent(mock_context, "TestAgent")
        thread = agent.get_new_thread()

        # Call with ChatMessage
        msg = ChatMessage(role="user", text="Hello")
        task = agent.run(messages=msg, thread=thread)

        assert task == mock_task

        # Verify message was converted to string
        call_args = mock_context.call_entity.call_args
        request = call_args[0][2]
        assert request["message"] == "Hello"

    def test_run_stream_raises_not_implemented(self) -> None:
        """Test that run_stream() method raises NotImplementedError."""
        mock_context = Mock()
        agent = DurableAIAgent(mock_context, "TestAgent")

        with pytest.raises(NotImplementedError) as exc_info:
            agent.run_stream("Test message")

        error_msg = str(exc_info.value)
        assert "Streaming is not supported" in error_msg

    def test_entity_id_format(self) -> None:
        """Test that EntityId is created with correct format (name, key)."""
        from azure.durable_functions import EntityId

        mock_context = Mock()
        mock_context.new_uuid = Mock(return_value="test-guid-789")
        mock_context.call_entity = Mock(return_value=Mock())

        agent = DurableAIAgent(mock_context, "WriterAgent")
        thread = agent.get_new_thread()

        # Call run() to trigger entity ID creation
        agent.run("Test", thread=thread)

        # Verify call_entity was called with correct EntityId
        call_args = mock_context.call_entity.call_args
        entity_id = call_args[0][0]

        # EntityId should be EntityId(name="dafx-WriterAgent", key="test-guid-789")
        # Which formats as "@dafx-writeragent@test-guid-789"
        assert isinstance(entity_id, EntityId)
        assert entity_id.name == "dafx-WriterAgent"
        assert entity_id.key == "test-guid-789"
        assert str(entity_id) == "@dafx-writeragent@test-guid-789"


class TestAgentFunctionAppGetAgent:
    """Test suite for AgentFunctionApp.get_agent."""

    def test_get_agent_method(self) -> None:
        """Test get_agent method creates DurableAIAgent for registered agent."""
        app = _app_with_registered_agents("MyAgent")
        mock_context = Mock()
        mock_context.instance_id = "test-instance-100"

        agent = app.get_agent(mock_context, "MyAgent")

        assert isinstance(agent, DurableAIAgent)
        assert agent.agent_name == "MyAgent"
        assert agent.context == mock_context

    def test_get_agent_raises_for_unregistered_agent(self) -> None:
        """Test get_agent raises ValueError when agent is not registered."""
        app = _app_with_registered_agents("KnownAgent")

        with pytest.raises(ValueError, match=r"Agent 'MissingAgent' is not registered with this app\."):
            app.get_agent(Mock(), "MissingAgent")


class TestOrchestrationIntegration:
    """Integration tests for orchestration scenarios."""

    def test_sequential_agent_calls_simulation(self) -> None:
        """Simulate sequential agent calls in an orchestration."""
        mock_context = Mock()
        mock_context.instance_id = "test-orchestration-001"
        # new_uuid will be called 3 times:
        # 1. thread creation
        # 2. correlation_id for first call
        # 3. correlation_id for second call
        mock_context.new_uuid = Mock(side_effect=["deterministic-guid-001", "corr-1", "corr-2"])

        # Track entity calls
        entity_calls: list[dict[str, Any]] = []

        def mock_call_entity_side_effect(entity_id: Any, operation: str, input_data: dict[str, Any]) -> Mock:
            entity_calls.append({"entity_id": str(entity_id), "operation": operation, "input": input_data})

            # Return a mock Task
            mock_task = Mock()
            mock_task._is_scheduled = False
            return mock_task

        mock_context.call_entity = Mock(side_effect=mock_call_entity_side_effect)

        app = _app_with_registered_agents("WriterAgent")
        agent = app.get_agent(mock_context, "WriterAgent")

        # Create thread
        thread = agent.get_new_thread()

        # First call - returns Task
        task1 = agent.run("Write something", thread=thread)
        assert hasattr(task1, "_is_scheduled")

        # Second call - returns Task
        task2 = agent.run("Improve: something", thread=thread)
        assert hasattr(task2, "_is_scheduled")

        # Verify both calls used the same entity (same session key)
        assert len(entity_calls) == 2
        assert entity_calls[0]["entity_id"] == entity_calls[1]["entity_id"]
        # EntityId format is @dafx-writeragent@deterministic-guid-001
        assert entity_calls[0]["entity_id"] == "@dafx-writeragent@deterministic-guid-001"
        # new_uuid called 3 times: thread + 2 correlation IDs
        assert mock_context.new_uuid.call_count == 3

    def test_multiple_agents_in_orchestration(self) -> None:
        """Test using multiple different agents in one orchestration."""
        mock_context = Mock()
        mock_context.instance_id = "test-orchestration-002"
        # Mock new_uuid to return different GUIDs for each call
        # Order: writer thread, editor thread, writer correlation, editor correlation
        mock_context.new_uuid = Mock(side_effect=["writer-guid-001", "editor-guid-002", "writer-corr", "editor-corr"])

        entity_calls: list[str] = []

        def mock_call_entity_side_effect(entity_id: Any, operation: str, input_data: dict[str, Any]) -> Mock:
            entity_calls.append(str(entity_id))
            mock_task = Mock()
            mock_task._is_scheduled = False
            return mock_task

        mock_context.call_entity = Mock(side_effect=mock_call_entity_side_effect)

        app = _app_with_registered_agents("WriterAgent", "EditorAgent")
        writer = app.get_agent(mock_context, "WriterAgent")
        editor = app.get_agent(mock_context, "EditorAgent")

        writer_thread = writer.get_new_thread()
        editor_thread = editor.get_new_thread()

        # Call both agents - returns Tasks
        writer_task = writer.run("Write", thread=writer_thread)
        editor_task = editor.run("Edit", thread=editor_thread)

        assert hasattr(writer_task, "_is_scheduled")
        assert hasattr(editor_task, "_is_scheduled")

        # Verify different entity IDs were used
        assert len(entity_calls) == 2
        # EntityId format is @dafx-agentname@guid (lowercased agent name with dafx- prefix)
        assert entity_calls[0] == "@dafx-writeragent@writer-guid-001"
        assert entity_calls[1] == "@dafx-editoragent@editor-guid-002"


class TestAgentThreadSerialization:
    """Test that AgentThread can be serialized for orchestration state."""

    async def test_agent_thread_serialize(self) -> None:
        """Test that AgentThread can be serialized."""
        thread = AgentThread()

        # Serialize
        serialized = await thread.serialize()

        assert isinstance(serialized, dict)
        assert "service_thread_id" in serialized

    async def test_agent_thread_deserialize(self) -> None:
        """Test that AgentThread can be deserialized."""
        thread = AgentThread()
        serialized = await thread.serialize()

        # Deserialize
        restored = await AgentThread.deserialize(serialized)

        assert isinstance(restored, AgentThread)
        assert restored.service_thread_id == thread.service_thread_id

    async def test_durable_agent_thread_serialization(self) -> None:
        """Test that DurableAgentThread persists session metadata during serialization."""
        mock_context = Mock()
        mock_context.instance_id = "test-instance-999"
        mock_context.new_uuid = Mock(return_value="test-guid-999")

        agent = DurableAIAgent(mock_context, "TestAgent")
        thread = agent.get_new_thread()

        assert isinstance(thread, DurableAgentThread)
        # Verify custom attribute and property exist
        assert thread.session_id is not None
        session_id = thread.session_id
        assert isinstance(session_id, AgentSessionId)
        assert session_id.name == "TestAgent"
        assert session_id.key == "test-guid-999"

        # Standard serialization should still work
        serialized = await thread.serialize()
        assert isinstance(serialized, dict)
        assert serialized.get("durable_session_id") == str(session_id)

        # After deserialization, we'd need to restore the custom attribute
        # This would be handled by the orchestration framework
        restored = await DurableAgentThread.deserialize(serialized)
        assert isinstance(restored, DurableAgentThread)
        assert restored.session_id == session_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
