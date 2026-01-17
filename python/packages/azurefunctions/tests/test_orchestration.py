# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for orchestration support (DurableAIAgent)."""

from typing import Any
from unittest.mock import Mock

import pytest
from agent_framework import AgentResponse, ChatMessage, Role
from agent_framework_durabletask import DurableAIAgent
from azure.durable_functions.models.Task import TaskBase, TaskState

from agent_framework_azurefunctions import AgentFunctionApp
from agent_framework_azurefunctions._orchestration import AgentTask


def _app_with_registered_agents(*agent_names: str) -> AgentFunctionApp:
    app = AgentFunctionApp(enable_health_check=False, enable_http_endpoints=False)
    for name in agent_names:
        agent = Mock()
        agent.name = name
        app.add_agent(agent)
    return app


class _FakeTask(TaskBase):
    """Concrete TaskBase for testing AgentTask wiring."""

    def __init__(self, task_id: int = 1):
        super().__init__(task_id, [])
        self._set_is_scheduled(False)
        self.action_repr = []
        self.state = TaskState.RUNNING


def _create_entity_task(task_id: int = 1) -> TaskBase:
    """Create a minimal TaskBase instance for AgentTask tests."""
    return _FakeTask(task_id)


@pytest.fixture
def mock_context():
    """Create a mock orchestration context with UUID support."""
    context = Mock()
    context.instance_id = "test-instance"
    context.current_utc_datetime = Mock()
    return context


@pytest.fixture
def mock_context_with_uuid() -> tuple[Mock, str]:
    """Create a mock context with a single UUID."""
    from uuid import UUID

    context = Mock()
    context.instance_id = "test-instance"
    context.current_utc_datetime = Mock()
    test_uuid = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    context.new_uuid = Mock(return_value=test_uuid)
    return context, test_uuid.hex


@pytest.fixture
def mock_context_with_multiple_uuids() -> tuple[Mock, list[str]]:
    """Create a mock context with multiple UUIDs via side_effect."""
    from uuid import UUID

    context = Mock()
    context.instance_id = "test-instance"
    context.current_utc_datetime = Mock()
    uuids = [
        UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
    ]
    context.new_uuid = Mock(side_effect=uuids)
    # Return the hex versions for assertion checking
    hex_uuids = [uuid.hex for uuid in uuids]
    return context, hex_uuids


@pytest.fixture
def executor_with_uuid() -> tuple[Any, Mock, str]:
    """Create an executor with a mocked generate_unique_id method."""
    from agent_framework_azurefunctions._orchestration import AzureFunctionsAgentExecutor

    context = Mock()
    context.instance_id = "test-instance"
    context.current_utc_datetime = Mock()

    executor = AzureFunctionsAgentExecutor(context)
    test_uuid_hex = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    executor.generate_unique_id = Mock(return_value=test_uuid_hex)

    return executor, context, test_uuid_hex


@pytest.fixture
def executor_with_multiple_uuids() -> tuple[Any, Mock, list[str]]:
    """Create an executor with multiple mocked UUIDs."""
    from agent_framework_azurefunctions._orchestration import AzureFunctionsAgentExecutor

    context = Mock()
    context.instance_id = "test-instance"
    context.current_utc_datetime = Mock()

    executor = AzureFunctionsAgentExecutor(context)
    uuid_hexes = [
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "dddddddd-dddd-dddd-dddd-dddddddddddd",
        "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    ]
    executor.generate_unique_id = Mock(side_effect=uuid_hexes)

    return executor, context, uuid_hexes


@pytest.fixture
def executor_with_context(mock_context_with_uuid: tuple[Mock, str]) -> tuple[Any, Mock]:
    """Create an executor with a mocked context."""
    from agent_framework_azurefunctions._orchestration import AzureFunctionsAgentExecutor

    context, _ = mock_context_with_uuid
    return AzureFunctionsAgentExecutor(context), context


class TestAgentResponseHelpers:
    """Tests for response handling through public AgentTask API."""

    def test_try_set_value_success(self) -> None:
        """Test try_set_value correctly processes successful task completion."""
        entity_task = _create_entity_task()
        task = AgentTask(entity_task, None, "correlation-id")

        # Simulate successful entity task completion
        entity_task.state = TaskState.SUCCEEDED
        entity_task.result = AgentResponse(messages=[ChatMessage(role="assistant", text="Test response")]).to_dict()

        # Clear pending_tasks to simulate that parent has processed the child
        task.pending_tasks.clear()

        # Call try_set_value
        task.try_set_value(entity_task)

        # Verify task completed successfully with AgentResponse
        assert task.state == TaskState.SUCCEEDED
        assert isinstance(task.result, AgentResponse)
        assert task.result.text == "Test response"

    def test_try_set_value_failure(self) -> None:
        """Test try_set_value correctly handles failed task completion."""
        entity_task = _create_entity_task()
        task = AgentTask(entity_task, None, "correlation-id")

        # Simulate failed entity task
        entity_task.state = TaskState.FAILED
        entity_task.result = Exception("Entity call failed")

        # Call try_set_value
        task.try_set_value(entity_task)

        # Verify task failed with the error
        assert task.state == TaskState.FAILED
        assert isinstance(task.result, Exception)
        assert str(task.result) == "Entity call failed"

    def test_try_set_value_with_response_format(self) -> None:
        """Test try_set_value parses structured output when response_format is provided."""
        from pydantic import BaseModel

        class TestSchema(BaseModel):
            answer: str

        entity_task = _create_entity_task()
        task = AgentTask(entity_task, TestSchema, "correlation-id")

        # Simulate successful entity task with JSON response
        entity_task.state = TaskState.SUCCEEDED
        entity_task.result = AgentResponse(messages=[ChatMessage(role="assistant", text='{"answer": "42"}')]).to_dict()

        # Clear pending_tasks to simulate that parent has processed the child
        task.pending_tasks.clear()

        # Call try_set_value
        task.try_set_value(entity_task)

        # Verify task completed and value was parsed
        assert task.state == TaskState.SUCCEEDED
        assert isinstance(task.result, AgentResponse)
        assert isinstance(task.result.value, TestSchema)
        assert task.result.value.answer == "42"


class TestAgentFunctionAppGetAgent:
    """Test suite for AgentFunctionApp.get_agent."""

    def test_get_agent_raises_for_unregistered_agent(self) -> None:
        """Test get_agent raises ValueError when agent is not registered."""
        app = _app_with_registered_agents("KnownAgent")

        with pytest.raises(ValueError, match=r"Agent 'MissingAgent' is not registered with this app\."):
            app.get_agent(Mock(), "MissingAgent")


class TestAzureFunctionsFireAndForget:
    """Test fire-and-forget mode for AzureFunctionsAgentExecutor."""

    def test_fire_and_forget_calls_signal_entity(self, executor_with_uuid: tuple[Any, Mock, str]) -> None:
        """Verify wait_for_response=False calls signal_entity instead of call_entity."""
        executor, context, _ = executor_with_uuid
        context.signal_entity = Mock()
        context.call_entity = Mock(return_value=_create_entity_task())

        agent = DurableAIAgent(executor, "TestAgent")
        thread = agent.get_new_thread()

        # Run with wait_for_response=False
        result = agent.run("Test message", thread=thread, options={"wait_for_response": False})

        # Verify signal_entity was called and call_entity was not
        assert context.signal_entity.call_count == 1
        assert context.call_entity.call_count == 0

        # Should still return an AgentTask
        assert isinstance(result, AgentTask)

    def test_fire_and_forget_returns_completed_task(self, executor_with_uuid: tuple[Any, Mock, str]) -> None:
        """Verify wait_for_response=False returns pre-completed AgentTask."""
        executor, context, _ = executor_with_uuid
        context.signal_entity = Mock()

        agent = DurableAIAgent(executor, "TestAgent")
        thread = agent.get_new_thread()

        result = agent.run("Test message", thread=thread, options={"wait_for_response": False})

        # Task should be immediately complete
        assert isinstance(result, AgentTask)
        assert result.is_completed

    def test_fire_and_forget_returns_acceptance_response(self, executor_with_uuid: tuple[Any, Mock, str]) -> None:
        """Verify wait_for_response=False returns acceptance response."""
        executor, context, _ = executor_with_uuid
        context.signal_entity = Mock()

        agent = DurableAIAgent(executor, "TestAgent")
        thread = agent.get_new_thread()

        result = agent.run("Test message", thread=thread, options={"wait_for_response": False})

        # Get the result
        response = result.result
        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1
        assert response.messages[0].role == Role.SYSTEM
        # Check message contains key information
        message_text = response.messages[0].text
        assert "accepted" in message_text.lower()
        assert "background" in message_text.lower()

    def test_blocking_mode_still_works(self, executor_with_uuid: tuple[Any, Mock, str]) -> None:
        """Verify wait_for_response=True uses call_entity as before."""
        executor, context, _ = executor_with_uuid
        context.signal_entity = Mock()
        context.call_entity = Mock(return_value=_create_entity_task())

        agent = DurableAIAgent(executor, "TestAgent")
        thread = agent.get_new_thread()

        result = agent.run("Test message", thread=thread, options={"wait_for_response": True})

        # Verify call_entity was called and signal_entity was not
        assert context.call_entity.call_count == 1
        assert context.signal_entity.call_count == 0

        # Should return an AgentTask
        assert isinstance(result, AgentTask)


class TestOrchestrationIntegration:
    """Integration tests for orchestration scenarios."""

    def test_sequential_agent_calls_simulation(self, executor_with_multiple_uuids: tuple[Any, Mock, list[str]]) -> None:
        """Simulate sequential agent calls in an orchestration."""
        executor, context, uuid_hexes = executor_with_multiple_uuids

        # Track entity calls
        entity_calls: list[dict[str, Any]] = []

        def mock_call_entity_side_effect(entity_id: Any, operation: str, input_data: dict[str, Any]) -> TaskBase:
            entity_calls.append({"entity_id": str(entity_id), "operation": operation, "input": input_data})
            return _create_entity_task()

        context.call_entity = Mock(side_effect=mock_call_entity_side_effect)

        # Create agent directly with executor (not via app.get_agent)
        agent = DurableAIAgent(executor, "WriterAgent")

        # Create thread
        thread = agent.get_new_thread()

        # First call - returns AgentTask
        task1 = agent.run("Write something", thread=thread)
        assert isinstance(task1, AgentTask)

        # Second call - returns AgentTask
        task2 = agent.run("Improve: something", thread=thread)
        assert isinstance(task2, AgentTask)

        # Verify both calls used the same entity (same session key)
        assert len(entity_calls) == 2
        assert entity_calls[0]["entity_id"] == entity_calls[1]["entity_id"]
        # EntityId format is @dafx-writeragent@<uuid_hex>
        expected_entity_id = f"@dafx-writeragent@{uuid_hexes[0]}"
        assert entity_calls[0]["entity_id"] == expected_entity_id
        # generate_unique_id called 3 times: thread + 2 correlation IDs
        assert executor.generate_unique_id.call_count == 3

    def test_multiple_agents_in_orchestration(self, executor_with_multiple_uuids: tuple[Any, Mock, list[str]]) -> None:
        """Test using multiple different agents in one orchestration."""
        executor, context, uuid_hexes = executor_with_multiple_uuids

        entity_calls: list[str] = []

        def mock_call_entity_side_effect(entity_id: Any, operation: str, input_data: dict[str, Any]) -> TaskBase:
            entity_calls.append(str(entity_id))
            return _create_entity_task()

        context.call_entity = Mock(side_effect=mock_call_entity_side_effect)

        # Create agents directly with executor (not via app.get_agent)
        writer = DurableAIAgent(executor, "WriterAgent")
        editor = DurableAIAgent(executor, "EditorAgent")

        writer_thread = writer.get_new_thread()
        editor_thread = editor.get_new_thread()

        # Call both agents - returns AgentTasks
        writer_task = writer.run("Write", thread=writer_thread)
        editor_task = editor.run("Edit", thread=editor_thread)

        assert isinstance(writer_task, AgentTask)
        assert isinstance(editor_task, AgentTask)

        # Verify different entity IDs were used
        assert len(entity_calls) == 2
        # EntityId format is @dafx-agentname@uuid_hex (lowercased agent name with dafx- prefix)
        expected_writer_id = f"@dafx-writeragent@{uuid_hexes[0]}"
        expected_editor_id = f"@dafx-editoragent@{uuid_hexes[1]}"
        assert entity_calls[0] == expected_writer_id
        assert entity_calls[1] == expected_editor_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
