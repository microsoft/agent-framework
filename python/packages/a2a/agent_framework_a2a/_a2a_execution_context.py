# Copyright (c) Microsoft. All rights reserved.

from a2a.server.agent_execution import RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.types import Task
from pydantic import BaseModel


class A2aExecutionContext(BaseModel):
    """Execution context for A2A protocol tasks.

    This class manages the execution context for A2A protocol tasks, providing coordinated
    access to task state, protocol-level request information, and streaming state management.
    It serves as the primary context object passed through the A2A protocol execution pipeline,
    enabling seamless communication between task executors, updaters, and protocol handlers.

    Args:
        request (RequestContext): The A2A protocol request context containing protocol metadata,
            session information, and request parameters
        task (Task): The current task being executed, including task ID, state, and metadata
        updater (TaskUpdater): Task state update manager for handling state transitions,
            progress updates, and event queueing

    Attributes:
        streaming_chunks_id (str | None): Optional ID for managing streaming content chunks.
            Used to correlate streaming responses with specific stream sessions.
            Defaults to None.

    Example:
        Basic usage demonstrating context initialization and common operations:

        ```python
        from a2a.server.agent_execution import RequestContext
        from a2a.server.tasks import TaskUpdater
        from a2a.types import Task, TaskState

        # Initialize the execution context
        context = A2aExecutionContext(request=request_context, task=current_task, updater=task_updater)

        # Update task status during execution
        await context.updater.update_status(
            state=TaskState.working,
            message=context.updater.new_agent_message([Part(root=TextPart(text="Starting task processing..."))]),
        )

        # Check current task state
        if context.task.state == TaskState.working:
            print(f"Task {context.task.id} is currently working")

        # Handle streaming operations
        context.streaming_chunks_id = "stream_123"

        # Access request metadata
        metadata = context.request.metadata
        params = context.request.params

        # Mark task as complete
        await context.updater.update_status(
            state=TaskState.completed,
            message=context.updater.new_agent_message([Part(root=TextPart(text="Task completed successfully"))]),
        )
        ```

    Use Cases:
        - Task execution: Provides the execution context needed by task handlers to process
          work items within the A2A protocol framework
        - State management: Enables safe state transitions through the TaskUpdater interface
        - Streaming: Manages streaming response correlation and chunk organization
        - Protocol integration: Bridges task execution and A2A protocol requirements

    Note:
        This context is crucial for maintaining state consistency and coordinating between
        different components of the A2A protocol implementation. It should be created once
        per task execution and passed through all downstream operations.
    """

    streaming_chunks_id: str | None = None

    def __init__(
        self,
        request: RequestContext,
        task: Task,
        updater: TaskUpdater,
    ):
        super().__init__(streaming_chunks_id=None)
        self._task = task
        self._updater = updater
        self._request = request

    @property
    def updater(self) -> TaskUpdater:
        """Get the task state update manager.

        The TaskUpdater provides the primary mechanism for updating task state, sending messages,
        and queueing events within the A2A protocol. It manages the complete lifecycle of task
        state transitions and ensures all updates are properly propagated through the protocol.

        Returns:
            TaskUpdater: Manager for updating task state and sending events

        Example:
            Comprehensive example showing different update scenarios:

            ```python
            # Scenario: Update task to working state with progress message
            await context.updater.update_status(
                state=TaskState.working,
                message=context.updater.new_agent_message([Part(root=TextPart(text="Processing started..."))]),
            )
            ```
        """
        return self._updater

    @property
    def request(self) -> RequestContext:
        """Get the A2A protocol request context.

        The request context encapsulates all protocol-level information about the current request,
        including metadata, parameters, session details, and identifiers. This context is essential
        for accessing request-specific configuration and routing information.

        Returns:
            RequestContext: The protocol-level request context with all request metadata

        Example:
            Comprehensive example showing different request context access patterns:

            ```python
            # Scenario: Access basic request identifiers
            context_id = context.request.context_id
            request_id = context.request.request_id
            print(f"Processing request {request_id} in context {context_id}")
            ```
        """
        return self._request

    @property
    def task(self) -> Task:
        """Get the current task being executed.

        The task object represents the work unit being processed within the A2A protocol framework.
        It contains all task-specific information including identity, state, metadata, and execution
        history. Access this to inspect task details and make execution decisions.

        Returns:
            Task: The task instance with its current state and metadata

        Example:
            Comprehensive example showing different task access and decision patterns:

            ```python
            # Scenario: Access basic task information
            task_id = context.task.id
            task_type = context.task.type
            task_name = context.task.name
            print(f"Executing task {task_id} of type {task_type}: {task_name}")
            ```
        """
        return self._task
