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
        context = A2aExecutionContext(
            request=request_context,
            task=current_task,
            updater=task_updater
        )

        # Update task status during execution
        await context.updater.update_status(
            state=TaskState.working,
            message=context.updater.new_agent_message([
                Part(root=TextPart(text="Starting task processing..."))
            ])
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
            message=context.updater.new_agent_message([
                Part(root=TextPart(text="Task completed successfully"))
            ])
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
            # Scenario 1: Update task to working state with progress message
            await context.updater.update_status(
                state=TaskState.working,
                message=context.updater.new_agent_message([
                    Part(root=TextPart(text="Processing started..."))
                ])
            )

            # Scenario 2: Send an intermediate progress update
            await context.updater.update_status(
                state=TaskState.working,
                message=context.updater.new_agent_message([
                    Part(root=TextPart(text="Progress: 50% complete"))
                ])
            )

            # Scenario 3: Complete the task with success result
            result_message = context.updater.new_agent_message([
                Part(root=TextPart(text="Task completed successfully"))
            ])
            await context.updater.update_status(
                state=TaskState.completed,
                message=result_message
            )

            # Scenario 4: Handle task failure with error details
            error_message = context.updater.new_agent_message([
                Part(root=TextPart(text="Task failed: Invalid input parameters"))
            ])
            await context.updater.update_status(
                state=TaskState.failed,
                message=error_message
            )

            # Scenario 5: Create structured messages with multiple parts
            complex_message = context.updater.new_agent_message([
                Part(root=TextPart(text="Analysis Results:\n")),
                Part(root=TextPart(text="- Total items processed: 150\n")),
                Part(root=TextPart(text="- Success rate: 98%"))
            ])
            await context.updater.update_status(
                state=TaskState.working,
                message=complex_message
            )
            ```

        Note:
            The TaskUpdater handles:
            - Task state transitions (working, completed, failed, etc.)
            - Message creation and formatting
            - Event queueing for protocol delivery
            - Progress tracking and updates
            - Error reporting and propagation

        Warning:
            State transitions should follow the valid state machine defined by TaskState.
            Invalid state transitions may result in protocol violations.
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
            # Scenario 1: Access basic request identifiers
            context_id = context.request.context_id
            request_id = context.request.request_id
            print(f"Processing request {request_id} in context {context_id}")

            # Scenario 2: Retrieve request metadata
            metadata = context.request.metadata
            if "user_id" in metadata:
                current_user = metadata["user_id"]
            if "session_id" in metadata:
                session = metadata["session_id"]

            # Scenario 3: Access request parameters
            params = context.request.params
            timeout = params.get("timeout", 30)
            retry_count = params.get("retry_count", 3)

            # Scenario 4: Check protocol version and features
            protocol_version = context.request.protocol_version
            if protocol_version >= "2.0":
                # Use newer protocol features
                pass

            # Scenario 5: Access session information for stateful processing
            session_info = context.request.session_info
            if session_info:
                previous_state = session_info.get("previous_state")
                user_preferences = session_info.get("preferences")

            # Scenario 6: Use context for logging and tracing
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"Request {context.request.request_id} "
                f"in context {context.request.context_id} "
                f"started with params {context.request.params}"
            )
            ```

        Note:
            The request context contains:
            - Protocol metadata (version, format, encoding)
            - Request parameters and configuration
            - Session information for stateful operations
            - Context identifiers for request correlation
            - Authentication and authorization metadata

        Tip:
            Use context information for:
            - Request correlation and tracing
            - Session state management
            - Configuration overrides
            - Access control decisions
            - Protocol-level feature detection
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
            # Scenario 1: Access basic task information
            task_id = context.task.id
            task_type = context.task.type
            task_name = context.task.name
            print(f"Executing task {task_id} of type {task_type}: {task_name}")

            # Scenario 2: Check task state and make decisions
            from a2a.types import TaskState

            if context.task.state == TaskState.pending:
                # Initialize task processing
                print("Starting new task")
            elif context.task.state == TaskState.working:
                # Continue or resume processing
                print("Resuming task processing")
            elif context.task.state == TaskState.completed:
                # Task already done
                print("Task already completed")
            elif context.task.state == TaskState.failed:
                # Handle failure
                print("Task previously failed")

            # Scenario 3: Access task metadata and parameters
            metadata = context.task.metadata
            task_title = metadata.get("title", "Untitled")
            task_description = metadata.get("description", "")
            task_priority = metadata.get("priority", "normal")

            parameters = context.task.parameters
            input_data = parameters.get("input")
            options = parameters.get("options", {})

            # Scenario 4: Check task retry information
            retry_count = context.task.retry_count
            max_retries = context.task.max_retries
            if retry_count >= max_retries:
                print(f"Task has exceeded maximum retries ({max_retries})")

            # Scenario 5: Access task timing information
            created_time = context.task.created_at
            started_time = context.task.started_at
            elapsed = started_time - created_time if started_time else None
            print(f"Task created {created_time}, started {started_time}")

            # Scenario 6: Check task dependencies and relationships
            parent_task_id = context.task.parent_id
            dependent_tasks = context.task.dependencies
            if parent_task_id:
                print(f"This is a subtask of {parent_task_id}")
            if dependent_tasks:
                print(f"This task depends on: {dependent_tasks}")

            # Scenario 7: Use task information for logging and monitoring
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"Task {context.task.id} ({context.task.type}) "
                f"in state {context.task.state} "
                f"with priority {task_priority}"
            )

            # Scenario 8: Access task execution context and history
            execution_history = context.task.execution_history
            if execution_history:
                last_execution = execution_history[-1]
                print(f"Last executed: {last_execution.timestamp}")
            ```

        Note:
            The task object contains:
            - Task identifier (unique within the protocol session)
            - Task type and classification
            - Current execution state
            - Associated metadata (title, description, priority, etc.)
            - Task parameters and input data
            - Retry information and limits
            - Timing information (created, started, completed)
            - Relationships (parent task, dependencies)
            - Execution history and audit trail

        Tip:
            Use task information for:
            - State-based execution decisions
            - Retry logic and error handling
            - Progress tracking and reporting
            - Audit logging and monitoring
            - Task dependency management
            - Priority-based scheduling
        """
        return self._task
