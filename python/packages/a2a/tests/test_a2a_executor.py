# Copyright (c) Microsoft. All rights reserved.
from asyncio import CancelledError
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from a2a.types import Task, TaskState
from agent_framework import (
    AgentResponseUpdate,
    Content,
    Message,
    SupportsAgentRun,
)
from agent_framework._types import AgentResponse
from agent_framework.a2a import A2AExecutor
from pytest import fixture, raises


@fixture
def mock_agent() -> MagicMock:
    """Fixture that provides a mock SupportsAgentRun."""
    agent = MagicMock(spec=SupportsAgentRun)
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
def executor(mock_agent: MagicMock) -> A2AExecutor:
    """Fixture that provides an A2AExecutor."""
    return A2AExecutor(agent=mock_agent)


class TestA2AExecutorInitialization:
    """Tests for A2AExecutor initialization."""

    def test_initialization_with_agent_only(self, mock_agent: MagicMock) -> None:
        """Arrange: Create mock agent
        Act: Initialize A2AExecutor with only agent
        Assert: Executor is created with default values
        """
        # Act
        executor = A2AExecutor(agent=mock_agent)

        # Assert
        assert executor._agent is mock_agent
        assert executor._stream is False
        assert executor._run_kwargs == {}

    def test_initialization_with_stream_and_kwargs(self, mock_agent: MagicMock) -> None:
        """Arrange: Create mock agent
        Act: Initialize A2AExecutor with stream and run_kwargs
        Assert: Executor is created with specified values
        """
        # Arrange
        run_kwargs = {"temperature": 0.5}

        # Act
        executor = A2AExecutor(agent=mock_agent, stream=True, run_kwargs=run_kwargs)

        # Assert
        assert executor._agent is mock_agent
        assert executor._stream is True
        assert executor._run_kwargs == run_kwargs

    def test_initialization_with_invalid_run_kwargs(self, mock_agent: MagicMock) -> None:
        """Arrange: Create mock agent
        Act: Initialize A2AExecutor with reserved keys in run_kwargs
        Assert: ValueError is raised
        """
        # Act & Assert
        with raises(ValueError, match="run_kwargs cannot contain 'session'"):
            A2AExecutor(agent=mock_agent, run_kwargs={"session": "something"})

        with raises(ValueError, match="run_kwargs cannot contain 'stream'"):
            A2AExecutor(agent=mock_agent, run_kwargs={"stream": True})


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


class TestA2AExecutorExecute:
    """Tests for the execute method."""

    async def test_execute_with_existing_task_succeeds(
        self,
        executor: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
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

        response_message = Message(role="assistant", contents=[Content.from_text(text="Hello back")])
        response = MagicMock(spec=AgentResponse)
        response.messages = [response_message]
        executor._agent.run = AsyncMock(return_value=response)
        executor._agent.create_session = MagicMock()

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater.new_agent_message = MagicMock(return_value="message_obj")
            mock_updater_class.return_value = mock_updater

            # Act
            await executor.execute(mock_request_context, mock_event_queue)

            # Assert
            mock_updater.submit.assert_called_once()
            mock_updater.start_work.assert_called_once()
            mock_updater.complete.assert_called_once()
            executor._agent.create_session.assert_called_once()
            executor._agent.run.assert_called_once()

    async def test_execute_creates_task_when_not_exists(
        self,
        executor: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
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

        response_message = Message(role="assistant", contents=[Content.from_text(text="Response")])
        response = MagicMock(spec=AgentResponse)
        response.messages = [response_message]
        executor._agent.run = AsyncMock(return_value=response)
        executor._agent.create_session = MagicMock()

        with patch("agent_framework_a2a._a2a_executor.new_task") as mock_new_task:
            mock_task = MagicMock(spec=Task)
            mock_task.id = "task-new"
            mock_task.context_id = "ctx-123"
            mock_new_task.return_value = mock_task

            with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
                mock_updater = MagicMock()
                mock_updater.submit = AsyncMock()
                mock_updater.start_work = AsyncMock()
                mock_updater.complete = AsyncMock()
                mock_updater.update_status = AsyncMock()
                mock_updater.new_agent_message = MagicMock(return_value="message_obj")
                mock_updater_class.return_value = mock_updater

                # Act
                await executor.execute(mock_request_context, mock_event_queue)

                # Assert
                mock_new_task.assert_called_once()
                mock_event_queue.enqueue_event.assert_called_once()

    async def test_execute_raises_error_when_context_id_missing(
        self,
        executor: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
    ) -> None:
        """Arrange: Create context without context_id
        Act: Call execute method
        Assert: ValueError is raised
        """
        # Arrange
        mock_request_context.context_id = None
        mock_request_context.message = MagicMock()

        # Act & Assert
        with raises(ValueError) as excinfo:
            await executor.execute(mock_request_context, mock_event_queue)

        # Assert
        assert "Context ID" in str(excinfo.value)

    async def test_execute_raises_error_when_message_missing(
        self,
        executor: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
    ) -> None:
        """Arrange: Create context without message
        Act: Call execute method
        Assert: ValueError is raised
        """
        # Arrange
        mock_request_context.context_id = "ctx-123"
        mock_request_context.message = None

        # Act & Assert
        with raises(ValueError) as excinfo:
            await executor.execute(mock_request_context, mock_event_queue)

        # Assert
        assert "Message" in str(excinfo.value)

    async def test_execute_handles_cancelled_error(
        self,
        executor: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
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

        executor._agent.run = AsyncMock(side_effect=CancelledError())
        executor._agent.create_session = MagicMock()

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater_class.return_value = mock_updater

            # Act
            await executor.execute(mock_request_context, mock_event_queue)  # type: ignore

            # Assert
            mock_updater.update_status.assert_called()
            call_args_list = mock_updater.update_status.call_args_list
            assert any(call[1].get("state") == TaskState.canceled for call in call_args_list)

    async def test_execute_handles_generic_exception(
        self,
        executor: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
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

        executor._agent.run = AsyncMock(side_effect=ValueError("Test error"))
        executor._agent.create_session = MagicMock()

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
            call_args_list = mock_updater.update_status.call_args_list
            assert any(call[1].get("state") == TaskState.failed for call in call_args_list)

    async def test_execute_processes_multiple_response_messages(
        self,
        executor: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
    ) -> None:
        """Arrange: Create executor that returns multiple response messages
        Act: Call execute method
        Assert: All messages are processed through handle_events
        """
        # Arrange
        mock_request_context.get_user_input = MagicMock(return_value="Hello")
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"
        mock_request_context.message = MagicMock()

        response_message1 = Message(role="assistant", contents=[Content.from_text(text="First")])
        response_message2 = Message(role="assistant", contents=[Content.from_text(text="Second")])
        response = MagicMock(spec=AgentResponse)
        response.messages = [response_message1, response_message2]
        executor._agent.run = AsyncMock(return_value=response)
        executor._agent.create_session = MagicMock()

        # Mock handle_events
        executor.handle_events = AsyncMock()

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
            assert executor.handle_events.call_count == 2

    async def test_execute_passes_query_to_run(
        self,
        executor: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
    ) -> None:
        """Arrange: Create executor with request
        Act: Call execute method
        Assert: Query text is passed to run method with default stream and kwargs
        """
        # Arrange
        query_text = "Hello agent"
        mock_request_context.get_user_input = MagicMock(return_value=query_text)
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"
        mock_request_context.message = MagicMock()

        response_message = Message(role="assistant", contents=[Content.from_text(text="Response")])
        response = MagicMock(spec=AgentResponse)
        response.messages = [response_message]
        executor._agent.run = AsyncMock(return_value=response)
        executor._agent.create_session = MagicMock()

        with patch("agent_framework_a2a._a2a_executor.TaskUpdater") as mock_updater_class:
            mock_updater = MagicMock()
            mock_updater.submit = AsyncMock()
            mock_updater.start_work = AsyncMock()
            mock_updater.complete = AsyncMock()
            mock_updater.update_status = AsyncMock()
            mock_updater.new_agent_message = MagicMock(return_value="message_obj")
            mock_updater_class.return_value = mock_updater

            # Act
            await executor.execute(mock_request_context, mock_event_queue)

            # Assert
            executor._agent.run.assert_called_once_with(
                query_text, session=executor._agent.create_session(), stream=False
            )

    async def test_execute_with_stream_enabled(
        self,
        mock_agent: MagicMock,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
    ) -> None:
        """Arrange: Create executor with stream=True
        Act: Call execute method
        Assert: _run_stream is called and passes stream=True to run
        """
        # Arrange
        executor = A2AExecutor(agent=mock_agent, stream=True)
        query_text = "Hello agent"
        mock_request_context.get_user_input = MagicMock(return_value=query_text)
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"
        mock_request_context.message = MagicMock()

        mock_response_stream = MagicMock()
        mock_response_stream.with_transform_hook = MagicMock(return_value=mock_response_stream)
        mock_response_stream.get_final_response = AsyncMock()
        mock_agent.run = MagicMock(return_value=mock_response_stream)
        mock_agent.create_session = MagicMock()

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
            mock_agent.run.assert_called_once_with(query_text, session=mock_agent.create_session(), stream=True)
            mock_response_stream.with_transform_hook.assert_called_once()
            mock_response_stream.get_final_response.assert_called_once()

    async def test_execute_with_run_kwargs(
        self,
        mock_agent: MagicMock,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
    ) -> None:
        """Arrange: Create executor with run_kwargs
        Act: Call execute method
        Assert: run_kwargs are passed to run method
        """
        # Arrange
        run_kwargs = {"temperature": 0.5, "max_tokens": 100}
        executor = A2AExecutor(agent=mock_agent, run_kwargs=run_kwargs)
        query_text = "Hello agent"
        mock_request_context.get_user_input = MagicMock(return_value=query_text)
        mock_request_context.current_task = mock_task
        mock_request_context.context_id = "ctx-123"
        mock_request_context.message = MagicMock()

        response_message = Message(role="assistant", contents=[Content.from_text(text="Response")])
        response = MagicMock(spec=AgentResponse)
        response.messages = [response_message]
        mock_agent.run = AsyncMock(return_value=response)
        mock_agent.create_session = MagicMock()

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
            mock_agent.run.assert_called_once_with(
                query_text, session=mock_agent.create_session(), stream=False, **run_kwargs
            )


class TestA2AExecutorHandleEvents:
    """Tests for A2AExecutor.handle_events method."""

    async def test_run_method_with_single_message(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test the private _run method with a single message (not a list)."""
        # Arrange
        query = "test query"
        session = MagicMock()
        response_message = Message(role="assistant", contents=[Content.from_text(text="Response")])
        response = MagicMock(spec=AgentResponse)
        response.messages = response_message  # Not a list
        executor._agent.run = AsyncMock(return_value=response)
        executor.handle_events = AsyncMock()

        # Act
        await executor._run(query, session, mock_updater)

        # Assert
        executor.handle_events.assert_called_once_with(response_message, mock_updater)

    @fixture
    def mock_updater(self) -> MagicMock:
        """Create a mock execution context."""
        updater = MagicMock()
        updater.update_status = AsyncMock()
        updater.new_agent_message = MagicMock(return_value="mock_message")
        return updater

    async def test_ignore_user_messages(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test that messages from USER role are ignored."""
        # Arrange
        message = Message(
            contents=[Content.from_text(text="User input")],
            role="user",
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_not_called()

    async def test_ignore_messages_with_no_contents(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test that messages with no contents are ignored."""
        # Arrange
        message = Message(
            contents=[],
            role="assistant",
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_not_called()

    async def test_handle_text_content(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with text content."""
        # Arrange
        text = "Hello, this is a test message"
        message = Message(
            contents=[Content.from_text(text=text)],
            role="assistant",
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
        message = Message(
            contents=[
                Content.from_text(text="First message"),
                Content.from_text(text="Second message"),
            ],
            role="assistant",
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
        message = Message(
            contents=[Content.from_data(data=data, media_type="application/octet-stream")],
            role="assistant",
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
        message = Message(
            contents=[Content.from_uri(uri=uri, media_type="application/pdf")],
            role="assistant",
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_args = mock_updater.update_status.call_args
        assert call_args.kwargs["state"] == TaskState.working

    async def test_handle_mixed_content_types(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with mixed content types."""
        # Arrange
        data = b"file data"

        message = Message(
            contents=[
                Content.from_text(text="Processing file..."),
                Content.from_data(data=data, media_type="application/octet-stream"),
                Content.from_uri(uri="https://example.com/reference.pdf", media_type="application/pdf"),
            ],
            role="assistant",
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_args = mock_updater.update_status.call_args
        assert call_args.kwargs["state"] == TaskState.working

    async def test_handle_with_additional_properties(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with additional properties metadata."""
        # Arrange
        additional_props = {"custom_field": "custom_value", "priority": "high"}
        message = Message(
            contents=[Content.from_text(text="Test message")],
            role="assistant",
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
        message = Message(
            contents=[Content.from_text(text="Test message")],
            role="assistant",
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
        message = Message(
            contents=[
                Content.from_text(text="Message 1"),
                Content.from_text(text="Message 2"),
            ],
            role="assistant",
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        mock_updater.new_agent_message.assert_called_once()
        call_kwargs = mock_updater.new_agent_message.call_args.kwargs
        assert "parts" in call_kwargs
        parts_list = call_kwargs["parts"]
        assert len(parts_list) == 2

    async def test_task_state_always_working(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test that task state is always set to working."""
        # Arrange
        message = Message(
            contents=[Content.from_text(text="Any message")],
            role="assistant",
        )

        # Act
        await executor.handle_events(message, mock_updater)

        # Assert
        call_kwargs = mock_updater.update_status.call_args.kwargs
        assert call_kwargs["state"] == TaskState.working

    async def test_handle_agent_response_update_no_streamed_set(
        self, executor: A2AExecutor, mock_updater: MagicMock
    ) -> None:
        """Test handling AgentResponseUpdate (streaming) without a tracking set."""
        # Arrange
        update = AgentResponseUpdate(
            contents=[Content.from_text(text="Streaming chunk")],
            role="assistant",
            message_id="msg-1",
        )
        mock_updater.add_artifact = AsyncMock()

        # Act
        await executor.handle_events(update, mock_updater)

        # Assert
        mock_updater.add_artifact.assert_called_once()
        call_kwargs = mock_updater.add_artifact.call_args.kwargs
        assert call_kwargs["artifact_id"] == "msg-1"
        assert call_kwargs["append"] is None

    async def test_handle_agent_response_update_first_time(
        self, executor: A2AExecutor, mock_updater: MagicMock
    ) -> None:
        """Test handling AgentResponseUpdate (streaming) for the first time with a tracking set."""
        # Arrange
        update = AgentResponseUpdate(
            contents=[Content.from_text(text="Streaming chunk")],
            role="assistant",
            message_id="msg-1",
        )
        mock_updater.add_artifact = AsyncMock()
        streamed_artifact_ids = set()

        # Act
        await executor.handle_events(update, mock_updater, streamed_artifact_ids=streamed_artifact_ids)

        # Assert
        mock_updater.add_artifact.assert_called_once()
        call_kwargs = mock_updater.add_artifact.call_args.kwargs
        assert call_kwargs["append"] is None
        assert "msg-1" in streamed_artifact_ids

    async def test_handle_agent_response_update_subsequent_time(
        self, executor: A2AExecutor, mock_updater: MagicMock
    ) -> None:
        """Test handling AgentResponseUpdate (streaming) for subsequent times with a tracking set."""
        # Arrange
        update = AgentResponseUpdate(
            contents=[Content.from_text(text="Next chunk")],
            role="assistant",
            message_id="msg-1",
        )
        mock_updater.add_artifact = AsyncMock()
        streamed_artifact_ids = {"msg-1"}

        # Act
        await executor.handle_events(update, mock_updater, streamed_artifact_ids=streamed_artifact_ids)

        # Assert
        mock_updater.add_artifact.assert_called_once()
        call_kwargs = mock_updater.add_artifact.call_args.kwargs
        assert call_kwargs["append"] is True

    async def test_handle_unsupported_content_type(self, executor: A2AExecutor, mock_updater: MagicMock) -> None:
        """Test handling messages with unsupported content types."""
        # Arrange
        message = Message(
            contents=[Content(type="unknown", text="Some text")],
            role="assistant",
        )

        # Act
        with patch("agent_framework_a2a._a2a_executor.logger") as mock_logger:
            await executor.handle_events(message, mock_updater)

        # Assert
        mock_logger.warning.assert_called_once()
        mock_updater.update_status.assert_not_called()


class TestA2AExecutorIntegration:
    """Integration tests for A2AExecutor."""

    async def test_full_execution_flow_with_responses(
        self,
        executor: A2AExecutor,
        mock_request_context: MagicMock,
        mock_event_queue: MagicMock,
        mock_task: Task,
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

        response = MagicMock(spec=AgentResponse)
        response_message = MagicMock(spec=Message)
        response.messages = [response_message]
        response_message.contents = [Content.from_text(text="Hello user")]
        response_message.role = "assistant"
        response_message.additional_properties = None

        executor._agent.run = AsyncMock(return_value=response)
        executor._agent.create_session = MagicMock()
        executor.handle_events = AsyncMock()

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
            executor.handle_events.assert_called_once()
            mock_updater.complete.assert_called_once()
