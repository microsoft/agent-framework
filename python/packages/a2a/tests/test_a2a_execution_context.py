# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from a2a.server.agent_execution import RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.types import Task, TaskState
from agent_framework.a2a import A2aExecutionContext
from pytest import fixture


@fixture
def mock_request_context() -> MagicMock:
    """Fixture that provides a mock RequestContext."""
    request_context = MagicMock(spec=RequestContext)
    request_context.metadata = {"key": "value"}
    request_context.context_id = str(uuid4())
    request_context.params = {"param1": "value1"}
    return request_context


@fixture
def mock_task_updater() -> MagicMock:
    """Fixture that provides a mock TaskUpdater."""
    task_updater = MagicMock(spec=TaskUpdater)
    task_updater.update_status = AsyncMock()
    task_updater.new_agent_message = MagicMock()
    return task_updater


@fixture
def mock_task() -> Task:
    """Fixture that provides a mock Task."""
    task = MagicMock(spec=Task)
    task.id = str(uuid4())
    task.state = TaskState.completed
    task.metadata = {"task_key": "task_value"}
    return task


@fixture
def execution_context(
    mock_request_context: MagicMock,
    mock_task: Task,
    mock_task_updater: MagicMock,
) -> A2aExecutionContext:
    """Fixture that provides an A2aExecutionContext instance."""
    return A2aExecutionContext(
        request=mock_request_context,
        task=mock_task,
        updater=mock_task_updater,
    )


class TestA2aExecutionContextInitialization:
    """Tests for A2aExecutionContext initialization."""

    def test_initialization_with_valid_parameters(
        self,
        mock_request_context: MagicMock,
        mock_task: Task,
        mock_task_updater: MagicMock,
    ) -> None:
        """Arrange: Create context with valid parameters
        Act: Initialize A2aExecutionContext
        Assert: Context is initialized with correct values
        """
        # Arrange
        request = mock_request_context
        task = mock_task
        updater = mock_task_updater

        # Act
        context = A2aExecutionContext(request=request, task=task, updater=updater)

        # Assert
        assert context.request is request
        assert context.task is task
        assert context.updater is updater
        assert context.streaming_chunks_id is None

    def test_initialization_streaming_chunks_id_is_none(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context
        Act: Check streaming_chunks_id attribute
        Assert: streaming_chunks_id is initialized to None
        """
        # Act & Assert
        assert execution_context.streaming_chunks_id is None

    def test_initialization_with_different_request_contexts(
        self,
        mock_task: Task,
        mock_task_updater: MagicMock,
    ) -> None:
        """Arrange: Create multiple mock request contexts with different values
        Act: Initialize contexts with different requests
        Assert: Each context maintains its own request instance
        """
        # Arrange
        request1 = MagicMock(spec=RequestContext)
        request1.context_id = "context-1"
        request2 = MagicMock(spec=RequestContext)
        request2.context_id = "context-2"

        # Act
        context1 = A2aExecutionContext(request=request1, task=mock_task, updater=mock_task_updater)
        context2 = A2aExecutionContext(request=request2, task=mock_task, updater=mock_task_updater)

        # Assert
        assert context1.request.context_id == "context-1"
        assert context2.request.context_id == "context-2"
        assert context1.request is not context2.request


class TestA2aExecutionContextProperties:
    """Tests for A2aExecutionContext properties."""

    def test_updater_property_returns_task_updater(
        self,
        execution_context: A2aExecutionContext,
        mock_task_updater: MagicMock,
    ) -> None:
        """Arrange: Create execution context with mock updater
        Act: Access updater property
        Assert: Property returns the same updater instance
        """
        # Act
        result = execution_context.updater

        # Assert
        assert result is mock_task_updater

    def test_request_property_returns_request_context(
        self,
        execution_context: A2aExecutionContext,
        mock_request_context: MagicMock,
    ) -> None:
        """Arrange: Create execution context with mock request context
        Act: Access request property
        Assert: Property returns the same request context instance
        """
        # Act
        result = execution_context.request

        # Assert
        assert result is mock_request_context

    def test_task_property_returns_task(
        self,
        execution_context: A2aExecutionContext,
        mock_task: Task,
    ) -> None:
        """Arrange: Create execution context with mock task
        Act: Access task property
        Assert: Property returns the same task instance
        """
        # Act
        result = execution_context.task

        # Assert
        assert result is mock_task

    def test_properties_are_consistent_across_multiple_accesses(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context
        Act: Access properties multiple times
        Assert: Properties return the same instances each time
        """
        # Act
        updater1 = execution_context.updater
        updater2 = execution_context.updater
        request1 = execution_context.request
        request2 = execution_context.request
        task1 = execution_context.task
        task2 = execution_context.task

        # Assert
        assert updater1 is updater2
        assert request1 is request2
        assert task1 is task2


class TestA2aExecutionContextStreamingChunksId:
    """Tests for streaming_chunks_id attribute management."""

    def test_streaming_chunks_id_can_be_set(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context with streaming_chunks_id as None
        Act: Set streaming_chunks_id to a value
        Assert: streaming_chunks_id is updated to the new value
        """
        # Arrange
        stream_id = "stream_123"

        # Act
        execution_context.streaming_chunks_id = stream_id

        # Assert
        assert execution_context.streaming_chunks_id == stream_id

    def test_streaming_chunks_id_can_be_set_to_different_values(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context
        Act: Set streaming_chunks_id to different values sequentially
        Assert: streaming_chunks_id is updated each time
        """
        # Act & Assert
        execution_context.streaming_chunks_id = "stream_1"
        assert execution_context.streaming_chunks_id == "stream_1"

        execution_context.streaming_chunks_id = "stream_2"
        assert execution_context.streaming_chunks_id == "stream_2"

        execution_context.streaming_chunks_id = "stream_3"
        assert execution_context.streaming_chunks_id == "stream_3"

    def test_streaming_chunks_id_can_be_set_to_none(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context with streaming_chunks_id set to a value
        Act: Set streaming_chunks_id back to None
        Assert: streaming_chunks_id is None
        """
        # Arrange
        execution_context.streaming_chunks_id = "stream_123"

        # Act
        execution_context.streaming_chunks_id = None

        # Assert
        assert execution_context.streaming_chunks_id is None

    def test_streaming_chunks_id_with_complex_values(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context
        Act: Set streaming_chunks_id to various string formats
        Assert: streaming_chunks_id can hold different string formats
        """
        # Test UUID format
        uuid_str = str(uuid4())
        execution_context.streaming_chunks_id = uuid_str
        assert execution_context.streaming_chunks_id == uuid_str

        # Test long string
        long_str = "stream_" + "x" * 100
        execution_context.streaming_chunks_id = long_str
        assert execution_context.streaming_chunks_id == long_str

        # Test special characters
        special_str = "stream_#@!$%^&*()"
        execution_context.streaming_chunks_id = special_str
        assert execution_context.streaming_chunks_id == special_str


class TestA2aExecutionContextPydanticModel:
    """Tests for Pydantic model behavior of A2aExecutionContext."""

    def test_context_is_pydantic_model(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context
        Act: Check if context is instance of BaseModel
        Assert: Context is a valid Pydantic model
        """
        # Import BaseModel here to avoid unnecessary import at module level
        from pydantic import BaseModel

        # Assert
        assert isinstance(execution_context, BaseModel)

    def test_context_model_fields(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context
        Act: Check model fields
        Assert: Model has streaming_chunks_id field with correct configuration
        """
        # Act
        fields = execution_context.model_fields

        # Assert
        assert "streaming_chunks_id" in fields
        assert fields["streaming_chunks_id"].annotation == str | None


class TestA2aExecutionContextMultipleInstances:
    """Tests for creating and managing multiple execution context instances."""

    def test_multiple_contexts_are_independent(
        self,
        mock_request_context: MagicMock,
        mock_task: Task,
        mock_task_updater: MagicMock,
    ) -> None:
        """Arrange: Create multiple execution contexts
        Act: Modify streaming_chunks_id in one context
        Assert: Other contexts are not affected
        """
        # Arrange
        context1 = A2aExecutionContext(
            request=mock_request_context,
            task=mock_task,
            updater=mock_task_updater,
        )
        context2 = A2aExecutionContext(
            request=mock_request_context,
            task=mock_task,
            updater=mock_task_updater,
        )

        # Act
        context1.streaming_chunks_id = "stream_1"
        context2.streaming_chunks_id = "stream_2"

        # Assert
        assert context1.streaming_chunks_id == "stream_1"
        assert context2.streaming_chunks_id == "stream_2"

    def test_multiple_contexts_with_different_tasks(
        self,
        mock_request_context: MagicMock,
        mock_task_updater: MagicMock,
    ) -> None:
        """Arrange: Create tasks with different IDs
        Act: Create execution contexts for each task
        Assert: Each context maintains its own task reference
        """
        # Arrange
        task1 = MagicMock(spec=Task)
        task1.id = "task-1"
        task2 = MagicMock(spec=Task)
        task2.id = "task-2"

        # Act
        context1 = A2aExecutionContext(
            request=mock_request_context,
            task=task1,
            updater=mock_task_updater,
        )
        context2 = A2aExecutionContext(
            request=mock_request_context,
            task=task2,
            updater=mock_task_updater,
        )

        # Assert
        assert context1.task.id == "task-1"
        assert context2.task.id == "task-2"


class TestA2aExecutionContextEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_context_with_empty_metadata_in_request(
        self,
        mock_task: Task,
        mock_task_updater: MagicMock,
    ) -> None:
        """Arrange: Create request context with empty metadata
        Act: Initialize execution context
        Assert: Context is created successfully
        """
        # Arrange
        request = MagicMock(spec=RequestContext)
        request.metadata = {}

        # Act
        context = A2aExecutionContext(
            request=request,
            task=mock_task,
            updater=mock_task_updater,
        )

        # Assert
        assert context.request.metadata == {}

    def test_context_with_none_metadata_in_request(
        self,
        mock_task: Task,
        mock_task_updater: MagicMock,
    ) -> None:
        """Arrange: Create request context with None metadata
        Act: Initialize execution context
        Assert: Context is created successfully
        """
        # Arrange
        request = MagicMock(spec=RequestContext)
        request.metadata = None

        # Act
        context = A2aExecutionContext(
            request=request,
            task=mock_task,
            updater=mock_task_updater,
        )

        # Assert
        assert context.request.metadata is None

    def test_context_with_very_long_streaming_chunks_id(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context
        Act: Set streaming_chunks_id to a very long string
        Assert: streaming_chunks_id can handle long values
        """
        # Arrange
        long_id = "stream_" + "x" * 10000

        # Act
        execution_context.streaming_chunks_id = long_id

        # Assert
        assert execution_context.streaming_chunks_id == long_id
        assert len(execution_context.streaming_chunks_id) == 10007

    def test_context_accessing_properties_does_not_modify_state(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context with streaming_chunks_id set
        Act: Access properties multiple times
        Assert: Accessing properties does not modify streaming_chunks_id
        """
        # Arrange
        execution_context.streaming_chunks_id = "original_stream_id"
        original_id = execution_context.streaming_chunks_id

        # Act
        _ = execution_context.updater
        _ = execution_context.request
        _ = execution_context.task
        _ = execution_context.updater
        _ = execution_context.request
        _ = execution_context.task

        # Assert
        assert execution_context.streaming_chunks_id == original_id


class TestA2aExecutionContextIntegration:
    """Integration tests for A2aExecutionContext with mocked dependencies."""

    async def test_context_with_mocked_updater_operations(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context with mocked updater
        Act: Call updater methods through context
        Assert: Methods can be called successfully
        """
        # Arrange
        execution_context.updater.update_status = AsyncMock()
        message_part = MagicMock()

        # Act
        await execution_context.updater.update_status(message=message_part)

        # Assert
        execution_context.updater.update_status.assert_called_once_with(message=message_part)

    async def test_context_handles_concurrent_property_access(
        self,
        execution_context: A2aExecutionContext,
    ) -> None:
        """Arrange: Create execution context
        Act: Access properties concurrently
        Assert: All accesses return consistent values
        """
        import asyncio

        # Arrange
        async def access_properties() -> tuple:
            return (
                execution_context.updater,
                execution_context.request,
                execution_context.task,
            )

        # Act
        results = await asyncio.gather(
            access_properties(),
            access_properties(),
            access_properties(),
        )

        # Assert
        updater1, request1, task1 = results[0]
        updater2, request2, task2 = results[1]
        updater3, request3, task3 = results[2]

        assert updater1 is updater2 is updater3
        assert request1 is request2 is request3
        assert task1 is task2 is task3

    def test_context_preserves_references_after_modification(
        self,
        execution_context: A2aExecutionContext,
        mock_task_updater: MagicMock,
    ) -> None:
        """Arrange: Create execution context
        Act: Modify streaming_chunks_id and access properties
        Assert: Property references remain unchanged
        """
        # Arrange
        original_updater = execution_context.updater

        # Act
        execution_context.streaming_chunks_id = "stream_id"
        modified_updater = execution_context.updater

        # Assert
        assert original_updater is modified_updater
        assert modified_updater is mock_task_updater
