# Copyright (c) Microsoft. All rights reserved.

from asyncio import CancelledError
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from a2a.types import Task, TaskState
from agent_framework import (
    AgentRunResponseUpdate,
    TextContent,
    AgentThread,
    ChatAgent,
    WorkflowAgent, Role,
)
from pytest import fixture

from agent_framework.a2a import A2aExecutionContext, A2aExecutor, A2aEventAdapter, BaseA2aEventAdapter


@fixture
def mock_chat_agent() -> MagicMock:
    """Fixture that provides a mock ChatAgent."""
    agent = MagicMock(spec=ChatAgent)
    agent.get_new_thread = MagicMock(return_value=MagicMock(spec=AgentThread))
    agent.run_stream = AsyncMock()
    return agent


@fixture
def mock_workflow_agent() -> MagicMock:
    """Fixture that provides a mock WorkflowAgent."""
    agent = MagicMock(spec=WorkflowAgent)
    agent.get_new_thread = MagicMock(return_value=MagicMock(spec=AgentThread))
    agent.run_stream = AsyncMock()
    return agent


@fixture
def mock_event_adapter() -> MagicMock:
    """Fixture that provides a mock event adapter."""
    adapter = MagicMock(spec=A2aEventAdapter)
    adapter.handle_events = AsyncMock()
    return adapter


@fixture
def mock_request_context() -> MagicMock:
    """Fixture that provides a mock RequestContext."""
    request_context = MagicMock()
    request_context.context_id = str(uuid4())
    request_context.get_user_input = MagicMock(return_value="Test query")
    request_context.current_task = None
    request_context.message = None
    return request_context


@fixture
def mock_event_queue() -> MagicMock:
    """Fixture that provides a mock EventQueue."""
    queue = AsyncMock()
    queue.enqueue_event = AsyncMock()
    return queue


@fixture
def mock_agent_thread() -> MagicMock:
    """Fixture that provides a mock AgentThread."""
    return MagicMock(spec=AgentThread)


@fixture
def mock_task() -> Task:
    """Fixture that provides a mock Task."""
    task = MagicMock(spec=Task)
    task.id = str(uuid4())
    task.context_id = str(uuid4())
    task.state = TaskState.completed
    return task


@fixture
def mock_task_updater() -> MagicMock:
    """Fixture that provides a mock TaskUpdater."""
    updater = MagicMock()
    updater.submit = AsyncMock()
    updater.start_work = AsyncMock()
    updater.complete = AsyncMock()
    updater.update_status = AsyncMock()
    updater.new_agent_message = MagicMock()
    return updater


@fixture
def executor_with_chat_agent(mock_chat_agent: MagicMock) -> A2aExecutor:
    """Fixture that provides an A2aExecutor with ChatAgent."""
    return A2aExecutor(agent=mock_chat_agent)


@fixture
def executor_with_custom_adapter(mock_chat_agent: MagicMock, mock_event_adapter: MagicMock) -> A2aExecutor:
    """Fixture that provides an A2aExecutor with custom event adapter."""
    return A2aExecutor(agent=mock_chat_agent, event_adapter=mock_event_adapter)


class TestA2aExecutorInitialization:
    """Tests for A2aExecutor initialization."""

    def test_initialization_with_chat_agent_only(self, mock_chat_agent: MagicMock) -> None:
        """Arrange: Create mock ChatAgent
        Act: Initialize A2aExecutor with only agent
        Assert: Executor is created with default adapter and thread storage
        """
        # Act
        executor = A2aExecutor(agent=mock_chat_agent)

        # Assert
        assert executor._agent is mock_chat_agent
        assert executor._event_adapter is not None
        assert isinstance(executor._event_adapter, BaseA2aEventAdapter)
        assert executor.agent_thread_storage is not None

    def test_initialization_with_workflow_agent_only(self, mock_workflow_agent: MagicMock) -> None:
        """Arrange: Create mock WorkflowAgent
        Act: Initialize A2aExecutor with WorkflowAgent
        Assert: Executor accepts WorkflowAgent
        """
        # Act
        executor = A2aExecutor(agent=mock_workflow_agent)

        # Assert
        assert executor._agent is mock_workflow_agent
        assert executor._event_adapter is not None

    def test_initialization_with_custom_event_adapter(
        self, mock_chat_agent: MagicMock, mock_event_adapter: MagicMock
    ) -> None:
        """Arrange: Create mock ChatAgent and custom event adapter
        Act: Initialize A2aExecutor with custom adapter
        Assert: Executor uses the provided adapter
        """
        # Act
        executor = A2aExecutor(agent=mock_chat_agent, event_adapter=mock_event_adapter)

        # Assert
        assert executor._event_adapter is mock_event_adapter

    def test_initialization_with_custom_thread_storage(self, mock_chat_agent: MagicMock) -> None:
        """Arrange: Create mock ChatAgent and thread storage
        Act: Initialize A2aExecutor with custom storage
        Assert: Executor uses the provided storage
        """
        # Arrange
        custom_storage = MagicMock()

        # Act
        executor = A2aExecutor(agent=mock_chat_agent, agent_thread_storage=custom_storage)

        # Assert
        assert executor.agent_thread_storage is custom_storage

    def test_initialization_with_all_custom_components(
        self, mock_chat_agent: MagicMock, mock_event_adapter: MagicMock
    ) -> None:
        """Arrange: Create mock ChatAgent, adapter, and storage
        Act: Initialize A2aExecutor with all custom components
        Assert: Executor uses all provided components
        """
        # Arrange
        custom_storage = MagicMock()

        # Act
        executor = A2aExecutor(
            agent=mock_chat_agent, event_adapter=mock_event_adapter, agent_thread_storage=custom_storage
        )

        # Assert
        assert executor._agent is mock_chat_agent
        assert executor._event_adapter is mock_event_adapter
        assert executor.agent_thread_storage is custom_storage


class TestA2aExecutorBuildContext:
    """Tests for the build_context method."""

    def test_build_context_creates_execution_context(
        self,
        executor_with_chat_agent: A2aExecutor,
        mock_request_context: MagicMock,
        mock_task: Task,
        mock_task_updater: MagicMock,
    ) -> None:
        """Arrange: Create executor and mock components
        Act: Call build_context
        Assert: Returns A2aExecutionContext with correct components
        """
        # Act
        context = executor_with_chat_agent.build_context(mock_request_context, mock_task, mock_task_updater)

        # Assert
        assert isinstance(context, A2aExecutionContext)
        assert context.request is mock_request_context
        assert context.task is mock_task
        assert context.updater is mock_task_updater

    def test_build_context_with_different_parameters(
        self,
        executor_with_chat_agent: A2aExecutor,
    ) -> None:
        """Arrange: Create executor with different request contexts and tasks
        Act: Call build_context multiple times with different parameters
        Assert: Each context has correct references
        """
        # Arrange
        request1 = MagicMock()
        request1.context_id = "ctx-1"
        task1 = MagicMock()
        task1.id = "task-1"
        updater1 = MagicMock()

        request2 = MagicMock()
        request2.context_id = "ctx-2"
        task2 = MagicMock()
        task2.id = "task-2"
        updater2 = MagicMock()

        # Act
        context1 = executor_with_chat_agent.build_context(request1, task1, updater1)
        context2 = executor_with_chat_agent.build_context(request2, task2, updater2)

        # Assert
        assert context1.request.context_id == "ctx-1"
        assert context1.task.id == "task-1"
        assert context2.request.context_id == "ctx-2"
        assert context2.task.id == "task-2"


class TestA2aExecutorCancel:
    """Tests for the cancel method."""

    async def test_cancel_method_completes(
        self,
        executor_with_chat_agent: A2aExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
    ) -> None:
        """Arrange: Create executor with dependencies
        Act: Call cancel method
        Assert: Method completes without raising error
        """
        # Act & Assert (should not raise)
        await executor_with_chat_agent.cancel(mock_request_context, mock_event_queue)  # type: ignore

    async def test_cancel_handles_different_contexts(
        self,
        executor_with_chat_agent: A2aExecutor,
        mock_event_queue: MagicMock,
    ) -> None:
        """Arrange: Create executor with multiple request contexts
        Act: Call cancel with different contexts
        Assert: Each cancel completes successfully
        """
        # Arrange
        context1 = MagicMock()
        context2 = MagicMock()

        # Act & Assert
        await executor_with_chat_agent.cancel(context1, mock_event_queue)  # type: ignore
        await executor_with_chat_agent.cancel(context2, mock_event_queue)  # type: ignore


class TestA2aExecutorGetAgentThread:
    """Tests for the get_agent_thread method."""

    async def test_get_agent_thread_creates_new_thread_when_not_exists(
        self,
        executor_with_chat_agent: A2aExecutor,
        mock_request_context: MagicMock,
        mock_task: Task,
        mock_task_updater: MagicMock,
        mock_agent_thread: MagicMock,
    ) -> None:
        """Arrange: Create executor with mocked storage and agent
        Act: Call get_agent_thread with context that has no stored thread
        Assert: New thread is created and saved
        """
        # Arrange
        executor_with_chat_agent.agent_thread_storage.load_thread = AsyncMock(return_value=None)
        executor_with_chat_agent.agent_thread_storage.save_thread = AsyncMock()
        executor_with_chat_agent._agent.get_new_thread = MagicMock(return_value=mock_agent_thread)

        execution_context = executor_with_chat_agent.build_context(
            mock_request_context, mock_task, mock_task_updater
        )

        # Act
        result = await executor_with_chat_agent.get_agent_thread(execution_context)

        # Assert
        assert result is mock_agent_thread
        executor_with_chat_agent.agent_thread_storage.load_thread.assert_called_once()
        executor_with_chat_agent.agent_thread_storage.save_thread.assert_called_once()

    async def test_get_agent_thread_returns_existing_thread(
        self,
        executor_with_chat_agent: A2aExecutor,
        mock_request_context: MagicMock,
        mock_task: Task,
        mock_task_updater: MagicMock,
        mock_agent_thread: MagicMock,
    ) -> None:
        """Arrange: Create executor with mocked storage containing thread
        Act: Call get_agent_thread with context that has stored thread
        Assert: Existing thread is returned without creating new one
        """
        # Arrange
        executor_with_chat_agent.agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)
        executor_with_chat_agent.agent_thread_storage.save_thread = AsyncMock()

        execution_context = executor_with_chat_agent.build_context(
            mock_request_context, mock_task, mock_task_updater
        )

        # Act
        result = await executor_with_chat_agent.get_agent_thread(execution_context)

        # Assert
        assert result is mock_agent_thread
        executor_with_chat_agent.agent_thread_storage.save_thread.assert_not_called()

    async def test_get_agent_thread_with_different_contexts(
        self,
        executor_with_chat_agent: A2aExecutor,
        mock_request_context: MagicMock,
        mock_task_updater: MagicMock,
    ) -> None:
        """Arrange: Create executor with multiple contexts
        Act: Call get_agent_thread with different context IDs
        Assert: Each context loads from correct thread ID
        """
        # Arrange
        thread1 = MagicMock()
        thread2 = MagicMock()

        async def mock_load_thread(thread_id: str) -> MagicMock | None:  # type: ignore
            if thread_id == "thread-1":
                return thread1
            elif thread_id == "thread-2":
                return thread2
            return None

        executor_with_chat_agent.agent_thread_storage.load_thread = mock_load_thread

        task1 = MagicMock()
        task1.context_id = "thread-1"
        task2 = MagicMock()
        task2.context_id = "thread-2"

        context1 = executor_with_chat_agent.build_context(mock_request_context, task1, mock_task_updater)
        context2 = executor_with_chat_agent.build_context(mock_request_context, task2, mock_task_updater)

        # Act
        result1 = await executor_with_chat_agent.get_agent_thread(context1)
        result2 = await executor_with_chat_agent.get_agent_thread(context2)

        # Assert
        assert result1 is thread1
        assert result2 is thread2


class TestA2aExecutorExecute:
    """Tests for the execute method."""

    async def test_execute_with_existing_task_succeeds(
        self,
        executor_with_chat_agent: A2aExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
        mock_agent_thread: MagicMock,
    ) -> None:
        """Arrange: Create executor with mocked dependencies and existing task
        Act: Call execute method
        Assert: Execution completes successfully
        """
        # Arrange
        mock_request_context.get_user_input = MagicMock(return_value="Hello")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"

        executor_with_chat_agent.agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)
        executor_with_chat_agent._agent.run_stream = AsyncMock(return_value=AsyncMock())

        # Create an async generator that yields no responses
        async def empty_stream(*_args, **_kwargs):
            if True:
                return
            yield  # Make it a generator

        executor_with_chat_agent._agent.run_stream = empty_stream

        # Patch TaskUpdater creation
        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor_with_chat_agent.execute(mock_request_context, mock_event_queue)

            # Assert
            mock_updater.submit.assert_called_once()
            mock_updater.start_work.assert_called_once()
            mock_updater.complete.assert_called_once()

    async def test_execute_creates_task_when_not_exists(
        self,
        executor_with_chat_agent: A2aExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_agent_thread: MagicMock,
    ) -> None:
        """Arrange: Create executor with request context without task
        Act: Call execute method
        Assert: New task is created and enqueued
        """
        # Arrange
        mock_message = MagicMock()
        mock_request_context.get_user_input = MagicMock(return_value="Hello")
        mock_request_context.current_task = None
        mock_request_context.message = mock_message
        mock_request_context.context_id = "ctx-123"

        executor_with_chat_agent.agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        async def empty_stream(*_args, **_kwargs):
            if True:
                return
            yield  # Make it a generator

        executor_with_chat_agent._agent.run_stream = empty_stream

        with patch("agent_framework_a2a._a2a_executor.new_task") as mock_new_task:
            mock_task = MagicMock()
            mock_task.id = "task-new"
            mock_new_task.return_value = mock_task

            with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
                mock_updater = MagicMock()
                mock_updater.submit = AsyncMock()
                mock_updater.start_work = AsyncMock()
                mock_updater.complete = AsyncMock()
                mock_updater_class.return_value = mock_updater

                # Act
                await executor_with_chat_agent.execute(mock_request_context, mock_event_queue)

                # Assert
                mock_new_task.assert_called_once()
                mock_event_queue.enqueue_event.assert_called_once()

    async def test_execute_handles_cancelled_error(
        self,
        executor_with_chat_agent: A2aExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
        mock_agent_thread: MagicMock,
    ) -> None:
        """Arrange: Create executor that raises CancelledError
        Act: Call execute method
        Assert: Error is caught and task is marked as canceled
        """
        # Arrange
        mock_request_context.get_user_input = MagicMock(return_value="Hello")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"

        executor_with_chat_agent.agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        async def cancel_stream(*_args, **_kwargs):  # type: ignore
            if True:
                raise CancelledError()
            yield  # Make it a generator

        executor_with_chat_agent._agent.run_stream = cancel_stream

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor_with_chat_agent.execute(mock_request_context, mock_event_queue)  # type: ignore

            # Assert
            mock_updater.update_status.assert_called_with(state=TaskState.canceled, final=True)

    async def test_execute_handles_generic_exception(
        self,
        executor_with_chat_agent: A2aExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
        mock_agent_thread: MagicMock,
    ) -> None:
        """Arrange: Create executor that raises generic exception
        Act: Call execute method
        Assert: Error is caught and task is marked as failed
        """
        # Arrange
        mock_request_context.get_user_input = MagicMock(return_value="Hello")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"

        executor_with_chat_agent.agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        async def error_stream(*_args, **_kwargs):  # type: ignore
            if True:
                raise ValueError("Test error")
            yield  # Make it a generator

        executor_with_chat_agent._agent.run_stream = error_stream

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater.new_agent_message = MagicMock(return_value="error_message")
            mock_updater_class.return_value = mock_updater

            # Act
            await executor_with_chat_agent.execute(mock_request_context, mock_event_queue)

            # Assert
            # Verify update_status was called with failed state
            call_args_list = mock_updater.update_status.call_args_list
            assert any(
                call[1].get("state") == TaskState.failed or call[0][0] == TaskState.failed
                for call in call_args_list
            )

    async def test_execute_calls_event_adapter_for_responses(
        self,
        executor_with_custom_adapter: A2aExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
        mock_agent_thread: MagicMock,
        mock_event_adapter: MagicMock,
    ) -> None:
        """Arrange: Create executor with mock event adapter
        Act: Call execute with responses from agent
        Assert: Event adapter is called for each response
        """
        # Arrange
        mock_request_context.get_user_input = MagicMock(return_value="Hello")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"

        executor_with_custom_adapter.agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        # Create response updates
        response1 = MagicMock(spec=AgentRunResponseUpdate)
        response1.contents = [TextContent(text="Response 1")]
        response2 = MagicMock(spec=AgentRunResponseUpdate)
        response2.contents = [TextContent(text="Response 2")]

        async def response_stream(*_args, **_kwargs):  # type: ignore
            yield response1
            yield response2

        executor_with_custom_adapter._agent.run_stream = response_stream
        executor_with_custom_adapter._event_adapter.handle_events = AsyncMock()

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor_with_custom_adapter.execute(mock_request_context, mock_event_queue)  # type: ignore

            # Assert
            assert executor_with_custom_adapter._event_adapter.handle_events.call_count == 2

    async def test_execute_skips_response_with_no_contents(
        self,
        executor_with_custom_adapter: A2aExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
        mock_agent_thread: MagicMock,
        mock_event_adapter: MagicMock,
    ) -> None:
        """Arrange: Create executor with responses that have no contents
        Act: Call execute method
        Assert: Event adapter is not called for empty responses
        """
        # Arrange
        mock_request_context.get_user_input = MagicMock(return_value="Hello")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"

        executor_with_custom_adapter.agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        # Create response with no contents
        response1 = MagicMock(spec=AgentRunResponseUpdate)
        response1.contents = None
        response2 = MagicMock(spec=AgentRunResponseUpdate)
        response2.contents = []

        async def response_stream(*_args, **_kwargs):
            yield response1
            yield response2

        executor_with_custom_adapter._agent.run_stream = response_stream
        executor_with_custom_adapter._event_adapter.handle_events = AsyncMock()

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor_with_custom_adapter.execute(mock_request_context, mock_event_queue)

            # Assert
            executor_with_custom_adapter._event_adapter.handle_events.assert_not_called()


class TestA2aExecutorIntegration:
    """Integration tests for A2aExecutor."""

    async def test_full_execution_flow_with_responses(
        self,
        executor_with_custom_adapter: A2aExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
        mock_agent_thread: MagicMock,
        mock_event_adapter: MagicMock,
    ) -> None:
        """Arrange: Create executor with all mocked dependencies
        Act: Execute full flow from request to completion
        Assert: All components interact correctly
        """
        # Arrange
        mock_request_context.get_user_input = MagicMock(return_value="Hello agent")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"

        executor_with_custom_adapter.agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        response = MagicMock(spec=AgentRunResponseUpdate)
        response.contents = [TextContent(text="Hello user")]

        async def response_stream(*_args, **_kwargs):
            yield response

        executor_with_custom_adapter._agent.run_stream = response_stream
        executor_with_custom_adapter._event_adapter.handle_events = AsyncMock()

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor_with_custom_adapter.execute(mock_request_context, mock_event_queue)

            # Assert
            mock_updater.submit.assert_called_once()
            mock_updater.start_work.assert_called_once()
            executor_with_custom_adapter._event_adapter.handle_events.assert_called_once()
            mock_updater.complete.assert_called_once()

    async def test_executor_with_workflow_agent(
        self,
        mock_workflow_agent: MagicMock,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
        mock_agent_thread: MagicMock,
    ) -> None:
        """Arrange: Create executor with WorkflowAgent
        Act: Execute method
        Assert: Executor works with WorkflowAgent
        """
        # Arrange
        executor = A2aExecutor(agent=mock_workflow_agent)
        mock_request_context.get_user_input = MagicMock(return_value="Test")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"

        executor.agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        response = MagicMock(spec=AgentRunResponseUpdate)
        response.contents = [TextContent(text="Hello user")]
        response.role = Role.ASSISTANT

        async def response_stream(*_args, **_kwargs):
            yield response

        executor._agent.run_stream = response_stream

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = AsyncMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor.execute(mock_request_context, mock_event_queue)

            # Assert
            mock_updater.complete.assert_called_once()

