# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableAgentExecutor implementations.

Focuses on critical behavioral flows for executor strategies.
Run with: pytest tests/test_executors.py -v
"""

import time
from typing import Any
from unittest.mock import Mock

import pytest
from agent_framework import AgentResponse, Role
from durabletask.entities import EntityInstanceId
from durabletask.task import Task
from pydantic import BaseModel

from agent_framework_durabletask import DurableAgentThread
from agent_framework_durabletask._constants import DEFAULT_MAX_POLL_RETRIES, DEFAULT_POLL_INTERVAL_SECONDS
from agent_framework_durabletask._executors import (
    ClientAgentExecutor,
    DurableAgentTask,
    OrchestrationAgentExecutor,
)
from agent_framework_durabletask._models import AgentSessionId, RunRequest


# Fixtures
@pytest.fixture
def mock_client() -> Mock:
    """Provide a mock client for ClientAgentExecutor tests."""
    client = Mock()
    client.signal_entity = Mock()
    client.get_entity = Mock(return_value=None)
    return client


@pytest.fixture
def mock_entity_task() -> Mock:
    """Provide a mock entity task."""
    task = Mock(spec=Task)
    task.is_complete = False
    task.is_failed = False
    return task


@pytest.fixture
def mock_orchestration_context(mock_entity_task: Mock) -> Mock:
    """Provide a mock orchestration context with call_entity configured."""
    context = Mock()
    context.call_entity = Mock(return_value=mock_entity_task)
    return context


@pytest.fixture
def sample_run_request() -> RunRequest:
    """Provide a sample RunRequest for tests."""
    return RunRequest(message="test message", correlation_id="test-123")


@pytest.fixture
def client_executor(mock_client: Mock) -> ClientAgentExecutor:
    """Provide a ClientAgentExecutor with minimal polling for fast tests."""
    return ClientAgentExecutor(mock_client, max_poll_retries=1, poll_interval_seconds=0.01)


@pytest.fixture
def orchestration_executor(mock_orchestration_context: Mock) -> OrchestrationAgentExecutor:
    """Provide an OrchestrationAgentExecutor."""
    return OrchestrationAgentExecutor(mock_orchestration_context)


@pytest.fixture
def successful_agent_response() -> dict[str, Any]:
    """Provide a successful agent response dictionary."""
    return {
        "messages": [{"role": "assistant", "contents": [{"type": "text", "text": "Hello!"}]}],
        "created_at": "2025-12-30T10:00:00Z",
    }


@pytest.fixture
def configure_successful_entity_task(mock_entity_task: Mock) -> Any:
    """Provide a helper to configure mock_entity_task with a successful response."""

    def _configure(response: dict[str, Any]) -> Mock:
        mock_entity_task.is_failed = False
        mock_entity_task.is_complete = False
        mock_entity_task.get_result = Mock(return_value=response)
        return mock_entity_task

    return _configure


@pytest.fixture
def configure_failed_entity_task(mock_entity_task: Mock) -> Any:
    """Provide a helper to configure mock_entity_task with a failure."""

    def _configure(exception: Exception) -> Mock:
        mock_entity_task.is_failed = True
        mock_entity_task.is_complete = True
        mock_entity_task.get_exception = Mock(return_value=exception)
        return mock_entity_task

    return _configure


class TestExecutorThreadCreation:
    """Test that executors properly create DurableAgentThread with parameters."""

    def test_client_executor_creates_durable_thread(self, mock_client: Mock) -> None:
        """Verify ClientAgentExecutor creates DurableAgentThread instances."""
        executor = ClientAgentExecutor(mock_client)

        thread = executor.get_new_thread("test_agent")

        assert isinstance(thread, DurableAgentThread)

    def test_client_executor_forwards_kwargs_to_thread(self, mock_client: Mock) -> None:
        """Verify ClientAgentExecutor forwards kwargs to DurableAgentThread creation."""
        executor = ClientAgentExecutor(mock_client)

        thread = executor.get_new_thread("test_agent", service_thread_id="client-123")

        assert isinstance(thread, DurableAgentThread)
        assert thread.service_thread_id == "client-123"

    def test_orchestration_executor_creates_durable_thread(
        self, orchestration_executor: OrchestrationAgentExecutor
    ) -> None:
        """Verify OrchestrationAgentExecutor creates DurableAgentThread instances."""
        thread = orchestration_executor.get_new_thread("test_agent")

        assert isinstance(thread, DurableAgentThread)

    def test_orchestration_executor_forwards_kwargs_to_thread(
        self, orchestration_executor: OrchestrationAgentExecutor
    ) -> None:
        """Verify OrchestrationAgentExecutor forwards kwargs to DurableAgentThread creation."""
        thread = orchestration_executor.get_new_thread("test_agent", service_thread_id="orch-456")

        assert isinstance(thread, DurableAgentThread)
        assert thread.service_thread_id == "orch-456"


class TestClientAgentExecutorRun:
    """Test that ClientAgentExecutor.run_durable_agent works as implemented."""

    def test_client_executor_run_returns_response(
        self, client_executor: ClientAgentExecutor, sample_run_request: RunRequest
    ) -> None:
        """Verify ClientAgentExecutor.run_durable_agent returns AgentResponse (synchronous)."""
        result = client_executor.run_durable_agent("test_agent", sample_run_request)

        # Verify it returns an AgentResponse (synchronous, not a coroutine)
        assert isinstance(result, AgentResponse)
        assert result is not None


class TestClientAgentExecutorPollingConfiguration:
    """Test polling configuration parameters for ClientAgentExecutor."""

    def test_executor_uses_default_polling_parameters(self, mock_client: Mock) -> None:
        """Verify executor initializes with default polling parameters."""
        executor = ClientAgentExecutor(mock_client)

        assert executor.max_poll_retries == DEFAULT_MAX_POLL_RETRIES
        assert executor.poll_interval_seconds == DEFAULT_POLL_INTERVAL_SECONDS

    def test_executor_accepts_custom_polling_parameters(self, mock_client: Mock) -> None:
        """Verify executor accepts and stores custom polling parameters."""
        executor = ClientAgentExecutor(mock_client, max_poll_retries=20, poll_interval_seconds=0.5)

        assert executor.max_poll_retries == 20
        assert executor.poll_interval_seconds == 0.5

    def test_executor_respects_custom_max_poll_retries(self, mock_client: Mock, sample_run_request: RunRequest) -> None:
        """Verify executor respects custom max_poll_retries during polling."""
        # Create executor with only 2 retries
        executor = ClientAgentExecutor(mock_client, max_poll_retries=2, poll_interval_seconds=0.01)

        # Run the agent
        result = executor.run_durable_agent("test_agent", sample_run_request)

        # Verify it returns AgentResponse (should timeout after 2 attempts)
        assert isinstance(result, AgentResponse)

        # Verify get_entity was called 2 times (max_poll_retries)
        assert mock_client.get_entity.call_count == 2

    def test_executor_respects_custom_poll_interval(self, mock_client: Mock, sample_run_request: RunRequest) -> None:
        """Verify executor respects custom poll_interval_seconds during polling."""
        # Create executor with very short interval
        executor = ClientAgentExecutor(mock_client, max_poll_retries=3, poll_interval_seconds=0.01)

        # Measure time taken
        start = time.time()
        result = executor.run_durable_agent("test_agent", sample_run_request)
        elapsed = time.time() - start

        # Should take roughly 3 * 0.01 = 0.03 seconds (plus overhead)
        # Be generous with timing to avoid flakiness
        assert elapsed < 0.2  # Should be quick with 0.01 interval
        assert isinstance(result, AgentResponse)


class TestClientAgentExecutorFireAndForget:
    """Test fire-and-forget mode (wait_for_response=False) for ClientAgentExecutor."""

    def test_fire_and_forget_returns_immediately(self, mock_client: Mock) -> None:
        """Verify wait_for_response=False returns immediately without polling."""
        executor = ClientAgentExecutor(mock_client, max_poll_retries=10, poll_interval_seconds=0.1)

        # Create a request with wait_for_response=False
        request = RunRequest(message="test message", correlation_id="test-123", wait_for_response=False)

        # Measure time taken
        start = time.time()
        result = executor.run_durable_agent("test_agent", request)
        elapsed = time.time() - start

        # Should return immediately without polling (elapsed time should be very small)
        assert elapsed < 0.1  # Much faster than any polling would take

        # Should return an AgentResponse
        assert isinstance(result, AgentResponse)

        # Should have signaled the entity but not polled
        assert mock_client.signal_entity.call_count == 1
        assert mock_client.get_entity.call_count == 0  # No polling occurred

    def test_fire_and_forget_returns_empty_response(self, mock_client: Mock) -> None:
        """Verify wait_for_response=False returns an acceptance message with correlation ID."""
        executor = ClientAgentExecutor(mock_client)

        request = RunRequest(message="test message", correlation_id="test-456", wait_for_response=False)

        result = executor.run_durable_agent("test_agent", request)

        # Verify it contains an acceptance message
        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 1
        assert result.messages[0].role == Role.SYSTEM
        # Check message contains key information
        message_text = result.messages[0].text
        assert "accepted" in message_text.lower()
        assert "test-456" in message_text  # Contains correlation ID
        assert "background" in message_text.lower()


class TestOrchestrationAgentExecutorFireAndForget:
    """Test fire-and-forget mode for OrchestrationAgentExecutor."""

    def test_orchestration_fire_and_forget_calls_signal_entity(self, mock_orchestration_context: Mock) -> None:
        """Verify wait_for_response=False calls signal_entity instead of call_entity."""
        executor = OrchestrationAgentExecutor(mock_orchestration_context)
        mock_orchestration_context.signal_entity = Mock()

        request = RunRequest(message="test", correlation_id="test-123", wait_for_response=False)

        result = executor.run_durable_agent("test_agent", request)

        # Verify signal_entity was called and call_entity was not
        assert mock_orchestration_context.signal_entity.call_count == 1
        assert mock_orchestration_context.call_entity.call_count == 0

        # Should still return a DurableAgentTask
        assert isinstance(result, DurableAgentTask)

    def test_orchestration_fire_and_forget_returns_completed_task(self, mock_orchestration_context: Mock) -> None:
        """Verify wait_for_response=False returns pre-completed DurableAgentTask."""
        executor = OrchestrationAgentExecutor(mock_orchestration_context)
        mock_orchestration_context.signal_entity = Mock()

        request = RunRequest(message="test", correlation_id="test-456", wait_for_response=False)

        result = executor.run_durable_agent("test_agent", request)

        # Task should be immediately complete
        assert isinstance(result, DurableAgentTask)
        assert result.is_complete

    def test_orchestration_fire_and_forget_returns_acceptance_response(self, mock_orchestration_context: Mock) -> None:
        """Verify wait_for_response=False returns acceptance response."""
        executor = OrchestrationAgentExecutor(mock_orchestration_context)
        mock_orchestration_context.signal_entity = Mock()

        request = RunRequest(message="test", correlation_id="test-789", wait_for_response=False)

        result = executor.run_durable_agent("test_agent", request)

        # Get the result
        response = result.get_result()
        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1
        assert response.messages[0].role == Role.SYSTEM
        assert "test-789" in response.messages[0].text

    def test_orchestration_blocking_mode_calls_call_entity(self, mock_orchestration_context: Mock) -> None:
        """Verify wait_for_response=True uses call_entity as before."""
        executor = OrchestrationAgentExecutor(mock_orchestration_context)
        mock_orchestration_context.signal_entity = Mock()

        request = RunRequest(message="test", correlation_id="test-abc", wait_for_response=True)

        result = executor.run_durable_agent("test_agent", request)

        # Verify call_entity was called and signal_entity was not
        assert mock_orchestration_context.call_entity.call_count == 1
        assert mock_orchestration_context.signal_entity.call_count == 0

        # Should return a DurableAgentTask
        assert isinstance(result, DurableAgentTask)


class TestOrchestrationAgentExecutorRun:
    """Test OrchestrationAgentExecutor.run_durable_agent implementation."""

    def test_orchestration_executor_run_returns_durable_agent_task(
        self, orchestration_executor: OrchestrationAgentExecutor, sample_run_request: RunRequest
    ) -> None:
        """Verify OrchestrationAgentExecutor.run_durable_agent returns DurableAgentTask."""
        result = orchestration_executor.run_durable_agent("test_agent", sample_run_request)

        assert isinstance(result, DurableAgentTask)

    def test_orchestration_executor_calls_entity_with_correct_parameters(
        self,
        mock_orchestration_context: Mock,
        orchestration_executor: OrchestrationAgentExecutor,
        sample_run_request: RunRequest,
    ) -> None:
        """Verify call_entity is invoked with correct entity ID and request."""
        orchestration_executor.run_durable_agent("test_agent", sample_run_request)

        # Verify call_entity was called once
        assert mock_orchestration_context.call_entity.call_count == 1

        # Get the call arguments
        call_args = mock_orchestration_context.call_entity.call_args
        entity_id_arg = call_args[0][0]
        operation_arg = call_args[0][1]
        request_dict_arg = call_args[0][2]

        # Verify entity ID
        assert isinstance(entity_id_arg, EntityInstanceId)
        assert entity_id_arg.entity == "dafx-test_agent"

        # Verify operation name
        assert operation_arg == "run"

        # Verify request dict
        assert request_dict_arg == sample_run_request.to_dict()

    def test_orchestration_executor_uses_thread_session_id(
        self,
        mock_orchestration_context: Mock,
        orchestration_executor: OrchestrationAgentExecutor,
        sample_run_request: RunRequest,
    ) -> None:
        """Verify executor uses thread's session ID when provided."""
        # Create thread with specific session ID
        session_id = AgentSessionId(name="test_agent", key="specific-key-123")
        thread = DurableAgentThread.from_session_id(session_id)

        result = orchestration_executor.run_durable_agent("test_agent", sample_run_request, thread=thread)

        # Verify call_entity was called with the specific key
        call_args = mock_orchestration_context.call_entity.call_args
        entity_id_arg = call_args[0][0]

        assert entity_id_arg.key == "specific-key-123"
        assert isinstance(result, DurableAgentTask)


class TestDurableAgentTask:
    """Test DurableAgentTask completion and response transformation."""

    def test_durable_agent_task_transforms_successful_result(
        self, configure_successful_entity_task: Any, successful_agent_response: dict[str, Any]
    ) -> None:
        """Verify DurableAgentTask converts successful entity result to AgentResponse."""
        mock_entity_task = configure_successful_entity_task(successful_agent_response)

        task = DurableAgentTask(entity_task=mock_entity_task, response_format=None, correlation_id="test-123")

        # Simulate child task completion
        task.on_child_completed(mock_entity_task)

        assert task.is_complete
        result = task.get_result()
        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 1
        assert result.messages[0].role == Role.ASSISTANT

    def test_durable_agent_task_propagates_failure(self, configure_failed_entity_task: Any) -> None:
        """Verify DurableAgentTask propagates task failures."""
        mock_entity_task = configure_failed_entity_task(ValueError("Entity error"))

        task = DurableAgentTask(entity_task=mock_entity_task, response_format=None, correlation_id="test-123")

        # Simulate child task completion with failure
        task.on_child_completed(mock_entity_task)

        assert task.is_complete
        assert task.is_failed
        # The exception is wrapped in TaskFailedError by the durabletask library
        exception = task.get_exception()
        assert exception is not None

    def test_durable_agent_task_validates_response_format(self, configure_successful_entity_task: Any) -> None:
        """Verify DurableAgentTask validates response format when provided."""
        response = {
            "messages": [{"role": "assistant", "contents": [{"type": "text", "text": '{"answer": "42"}'}]}],
            "created_at": "2025-12-30T10:00:00Z",
        }
        mock_entity_task = configure_successful_entity_task(response)

        class TestResponse(BaseModel):
            answer: str

        task = DurableAgentTask(entity_task=mock_entity_task, response_format=TestResponse, correlation_id="test-123")

        # Simulate child task completion
        task.on_child_completed(mock_entity_task)

        assert task.is_complete
        result = task.get_result()
        assert isinstance(result, AgentResponse)

    def test_durable_agent_task_ignores_duplicate_completion(
        self, configure_successful_entity_task: Any, successful_agent_response: dict[str, Any]
    ) -> None:
        """Verify DurableAgentTask ignores duplicate completion calls."""
        mock_entity_task = configure_successful_entity_task(successful_agent_response)

        task = DurableAgentTask(entity_task=mock_entity_task, response_format=None, correlation_id="test-123")

        # Simulate child task completion twice
        task.on_child_completed(mock_entity_task)
        first_result = task.get_result()

        task.on_child_completed(mock_entity_task)
        second_result = task.get_result()

        # Should be the same result, get_result should only be called once
        assert first_result is second_result
        assert mock_entity_task.get_result.call_count == 1

    def test_durable_agent_task_fails_on_malformed_response(self, configure_successful_entity_task: Any) -> None:
        """Verify DurableAgentTask fails when entity returns malformed response data."""
        # Use data that will cause AgentResponse.from_dict to fail
        # Using a list instead of dict, or other invalid structure
        mock_entity_task = configure_successful_entity_task("invalid string response")

        task = DurableAgentTask(entity_task=mock_entity_task, response_format=None, correlation_id="test-123")

        # Simulate child task completion with malformed data
        task.on_child_completed(mock_entity_task)

        assert task.is_complete
        assert task.is_failed

    def test_durable_agent_task_fails_on_invalid_response_format(self, configure_successful_entity_task: Any) -> None:
        """Verify DurableAgentTask fails when response doesn't match required format."""
        response = {
            "messages": [{"role": "assistant", "contents": [{"type": "text", "text": '{"wrong": "field"}'}]}],
            "created_at": "2025-12-30T10:00:00Z",
        }
        mock_entity_task = configure_successful_entity_task(response)

        class StrictResponse(BaseModel):
            required_field: str

        task = DurableAgentTask(entity_task=mock_entity_task, response_format=StrictResponse, correlation_id="test-123")

        # Simulate child task completion with wrong format
        task.on_child_completed(mock_entity_task)

        assert task.is_complete
        assert task.is_failed

    def test_durable_agent_task_handles_empty_response(self, configure_successful_entity_task: Any) -> None:
        """Verify DurableAgentTask handles response with empty messages list."""
        response: dict[str, str | list[Any]] = {
            "messages": [],
            "created_at": "2025-12-30T10:00:00Z",
        }
        mock_entity_task = configure_successful_entity_task(response)

        task = DurableAgentTask(entity_task=mock_entity_task, response_format=None, correlation_id="test-123")

        # Simulate child task completion
        task.on_child_completed(mock_entity_task)

        assert task.is_complete
        result = task.get_result()
        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 0

    def test_durable_agent_task_handles_multiple_messages(self, configure_successful_entity_task: Any) -> None:
        """Verify DurableAgentTask correctly processes response with multiple messages."""
        response = {
            "messages": [
                {"role": "assistant", "contents": [{"type": "text", "text": "First message"}]},
                {"role": "assistant", "contents": [{"type": "text", "text": "Second message"}]},
            ],
            "created_at": "2025-12-30T10:00:00Z",
        }
        mock_entity_task = configure_successful_entity_task(response)

        task = DurableAgentTask(entity_task=mock_entity_task, response_format=None, correlation_id="test-123")

        # Simulate child task completion
        task.on_child_completed(mock_entity_task)

        assert task.is_complete
        result = task.get_result()
        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 2
        assert result.messages[0].role == Role.ASSISTANT
        assert result.messages[1].role == Role.ASSISTANT

    def test_durable_agent_task_is_not_complete_initially(self, mock_entity_task: Mock) -> None:
        """Verify DurableAgentTask is not complete when first created."""
        task = DurableAgentTask(entity_task=mock_entity_task, response_format=None, correlation_id="test-123")

        assert not task.is_complete
        assert not task.is_failed

    def test_durable_agent_task_completes_with_complex_response_format(
        self, configure_successful_entity_task: Any
    ) -> None:
        """Verify DurableAgentTask validates complex nested response formats correctly."""
        response = {
            "messages": [
                {
                    "role": "assistant",
                    "contents": [
                        {
                            "type": "text",
                            "text": '{"name": "test", "count": 42, "items": ["a", "b", "c"]}',
                        }
                    ],
                }
            ],
            "created_at": "2025-12-30T10:00:00Z",
        }
        mock_entity_task = configure_successful_entity_task(response)

        class ComplexResponse(BaseModel):
            name: str
            count: int
            items: list[str]

        task = DurableAgentTask(
            entity_task=mock_entity_task, response_format=ComplexResponse, correlation_id="test-123"
        )

        # Simulate child task completion
        task.on_child_completed(mock_entity_task)

        assert task.is_complete
        assert not task.is_failed
        result = task.get_result()
        assert isinstance(result, AgentResponse)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
