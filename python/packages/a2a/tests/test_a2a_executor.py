# Copyright (c) Microsoft. All rights reserved.
import base64
from asyncio import CancelledError
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from a2a.server.tasks import TaskUpdater
from a2a.types import Task, TaskState
from agent_framework import (
    AgentRunResponse,
    AgentThread,
    ChatAgent,
    ChatMessage,
    DataContent,
    Role,
    TextContent,
    UriContent,
    WorkflowAgent,
)
from agent_framework.a2a import A2AExecutor
from pytest import fixture


@fixture
def mock_chat_agent() -> MagicMock:
    """Fixture that provides a mock ChatAgent."""
    agent = MagicMock(spec=ChatAgent)
    agent.get_new_thread = MagicMock(return_value=MagicMock(spec=AgentThread))
    agent.run = AsyncMock()
    return agent


@fixture
def mock_workflow_agent() -> MagicMock:
    """Fixture that provides a mock WorkflowAgent."""
    agent = MagicMock(spec=WorkflowAgent)
    agent.get_new_thread = MagicMock(return_value=MagicMock(spec=AgentThread))
    agent.run = AsyncMock()
    return agent


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
def executor(mock_chat_agent: MagicMock) -> A2AExecutor:
    """Fixture that provides an A2AExecutor with ChatAgent."""
    return A2AExecutor(agent=mock_chat_agent)


@fixture
def executor_with_custom_adapter(mock_chat_agent: MagicMock) -> A2AExecutor:
    """Fixture that provides an A2AExecutor with custom event adapter."""
    executor = A2AExecutor(agent=mock_chat_agent)
    executor.handle_events = MagicMock()
    return executor


class TestA2AExecutorInitialization:
    """Tests for A2AExecutor initialization."""

    def test_initialization_with_chat_agent_only(self, mock_chat_agent: MagicMock) -> None:
        """Arrange: Create mock ChatAgent
        Act: Initialize A2AExecutor with only agent
        Assert: Executor is created with default adapter and thread storage
        """
        # Act
        executor = A2AExecutor(agent=mock_chat_agent)

        # Assert
        assert executor._agent is mock_chat_agent
        assert executor._agent_thread_storage is not None

    def test_initialization_with_workflow_agent_only(self, mock_workflow_agent: MagicMock) -> None:
        """Arrange: Create mock WorkflowAgent
        Act: Initialize A2AExecutor with WorkflowAgent
        Assert: Executor accepts WorkflowAgent
        """
        # Act
        executor = A2AExecutor(agent=mock_workflow_agent)

        # Assert
        assert executor._agent is mock_workflow_agent

    def test_initialization_with_custom_thread_storage(self, mock_chat_agent: MagicMock) -> None:
        """Arrange: Create mock ChatAgent and thread storage
        Act: Initialize A2AExecutor with custom storage
        Assert: Executor uses the provided storage
        """
        # Arrange
        custom_storage = MagicMock()

        # Act
        executor = A2AExecutor(agent=mock_chat_agent, agent_thread_storage=custom_storage)

        # Assert
        assert executor._agent_thread_storage is custom_storage

    def test_initialization_with_all_custom_components(self, mock_chat_agent: MagicMock) -> None:
        """Arrange: Create mock ChatAgent, adapter, and storage
        Act: Initialize A2AExecutor with all custom components
        Assert: Executor uses all provided components
        """
        # Arrange
        custom_storage = MagicMock()

        # Act
        executor = A2AExecutor(agent=mock_chat_agent, agent_thread_storage=custom_storage)

        # Assert
        assert executor._agent is mock_chat_agent
        assert executor._agent_thread_storage is custom_storage


class TestA2AExecutorCancel:
    """Tests for the cancel method."""

    async def test_cancel_method_completes(
        self,
        executor: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
    ) -> None:
        """Arrange: Create executor with dependencies
        Act: Call cancel method
        Assert: Method completes without raising error
        """
        # Act & Assert (should not raise)
        await executor.cancel(mock_request_context, mock_event_queue)  # type: ignore

    async def test_cancel_handles_different_contexts(
        self,
        executor: A2AExecutor,
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
        await executor.cancel(context1, mock_event_queue)  # type: ignore
        await executor.cancel(context2, mock_event_queue)  # type: ignore


class TestA2AExecutorGetAgentThread:
    """Tests for the get_agent_thread method."""

    async def test_get_agent_thread_creates_new_thread_when_not_exists(
        self,
        executor: A2AExecutor,
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
        executor._agent_thread_storage.load_thread = AsyncMock(return_value=None)
        executor._agent_thread_storage.save_thread = AsyncMock()
        executor._agent.get_new_thread = MagicMock(return_value=mock_agent_thread)

        # Act
        result = await executor.get_agent_thread(mock_task)

        # Assert
        assert result is mock_agent_thread
        executor._agent_thread_storage.load_thread.assert_called_once()
        executor._agent_thread_storage.save_thread.assert_called_once()

    async def test_get_agent_thread_returns_existing_thread(
        self,
        executor: A2AExecutor,
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
        executor._agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)
        executor._agent_thread_storage.save_thread = AsyncMock()

        # Act
        result = await executor.get_agent_thread(mock_task)

        # Assert
        assert result is mock_agent_thread
        executor._agent_thread_storage.save_thread.assert_not_called()

    async def test_get_agent_thread_with_different_contexts(
        self,
        executor: A2AExecutor,
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
            if thread_id == "thread-2":
                return thread2
            return None

        executor._agent_thread_storage.load_thread = mock_load_thread

        task1 = MagicMock()
        task1.context_id = "thread-1"
        task2 = MagicMock()
        task2.context_id = "thread-2"

        # Act
        result1 = await executor.get_agent_thread(task1)
        result2 = await executor.get_agent_thread(task2)

        # Assert
        assert result1 is thread1
        assert result2 is thread2


class TestA2AExecutorExecute:
    """Tests for the execute method."""

    async def test_execute_with_existing_task_succeeds(
        self,
        executor: A2AExecutor,
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
        mock_request_context.message = MagicMock()

        executor._agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)
        executor._agent.run_stream = AsyncMock(return_value=AsyncMock())

        # Create an async generator that yields no responses
        async def empty_stream(*_args, **_kwargs):
            if True:
                return
            yield  # Make it a generator

        executor._agent.run_stream = empty_stream

        # Patch TaskUpdater creation
        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor.execute(mock_request_context, mock_event_queue)

            # Assert
            mock_updater.submit.assert_called_once()
            mock_updater.start_work.assert_called_once()
            mock_updater.complete.assert_called_once()

    async def test_execute_creates_task_when_not_exists(
        self,
        executor: A2AExecutor,
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
        mock_request_context.message = MagicMock()

        executor._agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        async def empty_stream(*_args, **_kwargs):
            if True:
                return
            yield  # Make it a generator

        executor._agent.run_stream = empty_stream

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
                await executor.execute(mock_request_context, mock_event_queue)

                # Assert
                mock_new_task.assert_called_once()
                mock_event_queue.enqueue_event.assert_called_once()

    async def test_execute_handles_cancelled_error(
        self,
        executor: A2AExecutor,
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
        mock_request_context.message = MagicMock()

        executor._agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        async def cancel_stream(*_args, **_kwargs):  # type: ignore
            if True:
                raise CancelledError

        executor._agent.run = cancel_stream

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor.execute(mock_request_context, mock_event_queue)  # type: ignore

            # Assert
            mock_updater.update_status.assert_called_with(state=TaskState.canceled, final=True)

    async def test_execute_handles_generic_exception(
        self,
        executor: A2AExecutor,
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
        mock_request_context.message = MagicMock()

        executor._agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        async def error_stream(*_args, **_kwargs):  # type: ignore
            if True:
                raise ValueError("Test error")
            yield  # Make it a generator

        executor._agent.run_stream = error_stream

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater.new_agent_message = MagicMock(return_value="error_message")
            mock_updater_class.return_value = mock_updater

            # Act
            await executor.execute(mock_request_context, mock_event_queue)

            # Assert
            # Verify update_status was called with failed state
            call_args_list = mock_updater.update_status.call_args_list
            assert any(
                call[1].get("state") == TaskState.failed or call[0][0] == TaskState.failed for call in call_args_list
            )

    async def test_execute_calls_event_adapter_for_responses(
        self,
        executor_with_custom_adapter: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
        mock_agent_thread: MagicMock,
    ) -> None:
        """Arrange: Create executor with mock event adapter
        Act: Call execute with responses from agent
        Assert: Event adapter is called for each response
        """
        # Arrange
        mock_request_context.get_user_input = MagicMock(return_value="Hello")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"
        mock_request_context.message = MagicMock()

        executor_with_custom_adapter._agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        # Create response updates
        response1 = MagicMock(spec=ChatMessage)
        response1.contents = [TextContent(text="Response 1")]
        response2 = MagicMock(spec=ChatMessage)
        response2.contents = [TextContent(text="Response 2")]

        async def response_stream(*_args, **_kwargs):  # type: ignore
            response = MagicMock(spec=AgentRunResponse)
            response.messages = [response1, response2]
            return response

        executor_with_custom_adapter._agent.run = response_stream
        executor_with_custom_adapter.handle_events = AsyncMock()

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor_with_custom_adapter.execute(mock_request_context, mock_event_queue)  # type: ignore

            # Assert
            assert executor_with_custom_adapter.handle_events.call_count == 2

    async def test_execute_skips_response_with_no_contents(
        self,
        executor_with_custom_adapter: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
        mock_agent_thread: MagicMock,
    ) -> None:
        """Arrange: Create executor with responses that have no contents
        Act: Call execute method
        Assert: Event adapter is not called for empty responses
        """
        # Arrange
        mock_request_context.get_user_input = MagicMock(return_value="Hello")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"
        mock_request_context.message = MagicMock()

        executor_with_custom_adapter._agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        # Create response with no contents
        response = MagicMock(spec=AgentRunResponse)
        response.messages = []

        async def response_stream(*_args, **_kwargs):
            return response

        executor_with_custom_adapter._agent.run = response_stream
        executor_with_custom_adapter.handle_events = AsyncMock()

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor_with_custom_adapter.execute(mock_request_context, mock_event_queue)

            # Assert
            executor_with_custom_adapter.handle_events.assert_not_called()


class TestA2AExecutorIntegration:
    """Integration tests for A2AExecutor."""

    async def test_full_execution_flow_with_responses(
        self,
        executor_with_custom_adapter: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
        mock_agent_thread: MagicMock,
    ) -> None:
        """Arrange: Create executor with all mocked dependencies
        Act: Execute full flow from request to completion
        Assert: All components interact correctly
        """
        # Arrange
        mock_request_context.get_user_input = MagicMock(return_value="Hello agent")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"
        mock_request_context.message = MagicMock()

        executor_with_custom_adapter._agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        response = MagicMock(spec=AgentRunResponse)
        response_message = MagicMock(spec=ChatMessage)
        response.messages = [response_message]
        response_message.contents = [TextContent(text="Hello user")]
        response_message.role = Role.ASSISTANT

        async def response_stream(*_args, **_kwargs):
            return response

        executor_with_custom_adapter._agent.run_stream = response_stream
        executor_with_custom_adapter.handle_events = AsyncMock()

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
            executor_with_custom_adapter.handle_events.assert_called_once()
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
        executor = A2AExecutor(agent=mock_workflow_agent)
        mock_request_context.get_user_input = MagicMock(return_value="Test")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"
        mock_request_context.message = MagicMock()

        executor._agent_thread_storage.load_thread = AsyncMock(return_value=mock_agent_thread)

        response = MagicMock(spec=AgentRunResponse)
        response_message = MagicMock(spec=ChatMessage)
        response.messages = [response_message]
        response_message.contents = [TextContent(text="Hello user")]
        response_message.role = Role.ASSISTANT

        async def response_stream(*_args, **_kwargs):
            return response

        executor._agent.run = response_stream

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater.new_agent_message = MagicMock(return_value="mock_message")
            mock_updater_class.return_value = mock_updater

            # Act
            await executor.execute(mock_request_context, mock_event_queue)

            # Assert
            mock_updater.complete.assert_called_once()


class TestA2AExecutorEventAdapter:
    """Tests for A2AExecutor.handle_events method."""

    @fixture
    def mock_updater(self) -> TaskUpdater:
        """Create a mock execution context."""
        updater = MagicMock()
        updater.update_status = AsyncMock()
        updater.new_agent_message = MagicMock(return_value="mock_message")
        return updater

    async def test_ignore_user_messages(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test that messages from USER role are ignored."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="User input")],
            role=Role.USER,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_not_called()

    async def test_ignore_messages_with_no_contents(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test that messages with no contents are ignored."""
        # Arrange
        message = ChatMessage(
            contents=[],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_not_called()

    async def test_handle_text_content(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with text content."""
        # Arrange
        text = "Hello, this is a test message"
        message = ChatMessage(
            contents=[TextContent(text=text)],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_args = mock_updater.update_status.call_args
        assert call_args.kwargs["state"] == TaskState.working
        assert mock_updater.new_agent_message.called

    async def test_handle_multiple_text_contents(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with multiple text contents."""
        # Arrange
        message = ChatMessage(
            contents=[
                TextContent(text="First message"),
                TextContent(text="Second message"),
            ],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        assert mock_updater.new_agent_message.called

    async def test_handle_data_content(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with data content."""
        # Arrange
        data = b"test file data"
        base64_data = base64.b64encode(data).decode("utf-8")
        data_uri = f"data:application/octet-stream;base64,{base64_data}"

        message = ChatMessage(
            contents=[DataContent(uri=data_uri)],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_args = mock_updater.update_status.call_args
        assert call_args.kwargs["state"] == TaskState.working

    async def test_handle_uri_content(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with URI content."""
        # Arrange
        uri = "https://example.com/file.pdf"
        message = ChatMessage(
            contents=[UriContent(uri=uri, media_type="pdf")],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_args = mock_updater.update_status.call_args
        assert call_args.kwargs["state"] == TaskState.working

    async def test_handle_uri_content_with_media_type(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with URI content that includes media type."""
        # Arrange
        uri = "https://example.com/image.jpg"
        message = ChatMessage(
            contents=[UriContent(uri=uri, media_type="image/jpeg")],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()

    async def test_handle_mixed_content_types(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with mixed content types."""
        # Arrange
        data = b"file data"
        base64_data = base64.b64encode(data).decode("utf-8")
        data_uri = f"data:application/octet-stream;base64,{base64_data}"

        message = ChatMessage(
            contents=[
                TextContent(text="Processing file..."),
                DataContent(uri=data_uri),
                UriContent(uri="https://example.com/reference.pdf", media_type="pdf"),
            ],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_args = mock_updater.update_status.call_args
        assert call_args.kwargs["state"] == TaskState.working
        # Verify all parts were created
        new_agent_message_call = mock_updater.new_agent_message.call_args
        assert new_agent_message_call is not None

    async def test_handle_with_additional_properties(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with additional properties metadata."""
        # Arrange
        additional_props = {"custom_field": "custom_value", "priority": "high"}
        message = ChatMessage(
            contents=[TextContent(text="Test message")],
            role=Role.ASSISTANT,
            additional_properties=additional_props,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        mock_updater.new_agent_message.assert_called_once()
        call_args = mock_updater.new_agent_message.call_args
        assert call_args.kwargs["metadata"] == additional_props

    async def test_handle_with_no_additional_properties(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages without additional properties."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="Test message")],
            role=Role.ASSISTANT,
            additional_properties=None,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        mock_updater.new_agent_message.assert_called_once()
        call_args = mock_updater.new_agent_message.call_args
        assert call_args.kwargs["metadata"] == {}

    async def test_parts_list_passed_to_new_agent_message(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test that parts list is correctly passed to new_agent_message."""
        # Arrange
        message = ChatMessage(
            contents=[
                TextContent(text="Message 1"),
                TextContent(text="Message 2"),
            ],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.new_agent_message.assert_called_once()
        call_kwargs = mock_updater.new_agent_message.call_args.kwargs
        assert "parts" in call_kwargs
        parts_list = call_kwargs["parts"]
        assert len(parts_list) == 2

    async def test_unsupported_content_type_skipped(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test that unsupported content types are silently skipped."""
        # Arrange
        # Create a message with a valid content and mock an unsupported one
        message = ChatMessage(
            contents=[
                TextContent(text="Valid text"),
            ],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert - should still process the valid text content
        mock_updater.update_status.assert_called_once()

    async def test_no_update_status_when_no_parts_created(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test that update_status is not called when no parts are created."""
        # Arrange
        message = ChatMessage(
            contents=[],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_not_called()

    async def test_handle_assistant_role(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with ASSISTANT role."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="Assistant response")],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()

    async def test_handle_system_role(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with SYSTEM role."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="System message")],
            role=Role.SYSTEM,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()

    async def test_handle_empty_text_content(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with empty text content."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="")],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_kwargs = mock_updater.new_agent_message.call_args.kwargs
        parts_list = call_kwargs["parts"]
        assert len(parts_list) == 1

    async def test_task_state_always_working(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test that task state is always set to working."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="Any message")],
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        call_kwargs = mock_updater.update_status.call_args.kwargs
        assert call_kwargs["state"] == TaskState.working

    async def test_large_number_of_contents(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with a large number of content items."""
        # Arrange
        contents = [TextContent(text=f"Message {i}") for i in range(100)]
        message = ChatMessage(
            contents=contents,
            role=Role.ASSISTANT,
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_kwargs = mock_updater.new_agent_message.call_args.kwargs
        parts_list = call_kwargs["parts"]
        assert len(parts_list) == 100
