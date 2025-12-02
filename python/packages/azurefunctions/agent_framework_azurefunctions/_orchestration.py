# Copyright (c) Microsoft. All rights reserved.

"""Orchestration Support for Durable Agents.

This module provides support for using agents inside Durable Function orchestrations.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    ChatMessage,
    get_logger,
)
from azure.durable_functions.models import TaskBase
from azure.durable_functions.models.Task import CompoundTask, TaskState
from pydantic import BaseModel

from ._models import AgentSessionId, DurableAgentThread, RunRequest

logger = get_logger("agent_framework.azurefunctions.orchestration")

CompoundActionConstructor: TypeAlias = Callable[[list[Any]], Any] | None

if TYPE_CHECKING:
    from azure.durable_functions import DurableOrchestrationContext

    class _TypedCompoundTask(CompoundTask):  # type: ignore[misc]
        _first_error: Any

        def __init__(
            self,
            tasks: list[TaskBase],
            compound_action_constructor: CompoundActionConstructor = None,
        ) -> None: ...

    AgentOrchestrationContextType: TypeAlias = DurableOrchestrationContext
else:
    AgentOrchestrationContextType = Any
    _TypedCompoundTask = CompoundTask


class AgentTask(_TypedCompoundTask):
    """A custom Task that wraps entity calls and provides typed AgentRunResponse results.

    This task wraps the underlying entity call task and intercepts its completion
    to convert the raw result into a typed AgentRunResponse object.
    """

    def __init__(
        self,
        entity_task: TaskBase,
        response_format: type[BaseModel] | None,
        correlation_id: str,
    ):
        """Initialize the AgentTask.

        Args:
            entity_task: The underlying entity call task
            response_format: Optional Pydantic model for response parsing
            correlation_id: Correlation ID for logging
        """
        super().__init__([entity_task])
        self._response_format = response_format
        self._correlation_id = correlation_id

        # Override action_repr to expose the inner task's action directly
        # This ensures compatibility with ReplaySchema V3 which expects Action objects.
        self.action_repr = entity_task.action_repr

        # Also copy the task ID to match the entity task's identity
        self.id = entity_task.id

    def try_set_value(self, child: TaskBase) -> None:
        """Transition the AgentTask to a terminal state and set its value to `AgentRunResponse`.

        Parameters
        ----------
        child : TaskBase
            The entity call task that just completed
        """
        if child.state is TaskState.SUCCEEDED:
            # Delegate to parent class for standard completion logic
            if len(self.pending_tasks) == 0:
                # Transform the raw result before setting it
                raw_result = child.result
                logger.debug(
                    "[AgentTask] Converting raw result for correlation_id %s",
                    self._correlation_id,
                )

                try:
                    response = self._load_agent_response(raw_result)

                    if self._response_format is not None:
                        self._ensure_response_format(
                            self._response_format,
                            self._correlation_id,
                            response,
                        )

                    # Set the typed AgentRunResponse as this task's result
                    self.set_value(is_error=False, value=response)
                except Exception as e:
                    logger.exception(
                        "[AgentTask] Failed to convert result for correlation_id: %s",
                        self._correlation_id,
                    )
                    self.set_value(is_error=True, value=e)
        else:
            # If error not handled by the parent, set it explicitly.
            if self._first_error is None:
                self._first_error = child.result
                self.set_value(is_error=True, value=self._first_error)

    def _load_agent_response(self, agent_response: AgentRunResponse | dict[str, Any] | None) -> AgentRunResponse:
        """Convert raw payloads into AgentRunResponse instance."""
        if agent_response is None:
            raise ValueError("agent_response cannot be None")

        logger.debug("[load_agent_response] Loading agent response of type: %s", type(agent_response))

        if isinstance(agent_response, AgentRunResponse):
            return agent_response
        if isinstance(agent_response, dict):
            logger.debug("[load_agent_response] Converting dict payload using AgentRunResponse.from_dict")
            return AgentRunResponse.from_dict(agent_response)

        raise TypeError(f"Unsupported type for agent_response: {type(agent_response)}")

    def _ensure_response_format(
        self,
        response_format: type[BaseModel] | None,
        correlation_id: str,
        response: AgentRunResponse,
    ) -> None:
        """Ensure the AgentRunResponse value is parsed into the expected response_format."""
        if response_format is not None and not isinstance(response.value, response_format):
            response.try_parse_value(response_format)

            logger.debug(
                "[DurableAIAgent] Loaded AgentRunResponse.value for correlation_id %s with type: %s",
                correlation_id,
                type(response.value).__name__,
            )


class DurableAIAgent(AgentProtocol):
    """A durable agent implementation that uses entity methods to interact with agent entities.

    This class implements AgentProtocol and provides methods to work with Azure Durable Functions
    orchestrations, which use generators and yield instead of async/await.

    Key methods:
    - get_new_thread(): Create a new conversation thread
    - run(): Execute the agent and return a Task for yielding in orchestrations

    Note: The run() method is NOT async. It returns a Task directly that must be
    yielded in orchestrations to wait for the entity call to complete.

    Example usage in orchestration:
        writer = app.get_agent(context, "WriterAgent")
        thread = writer.get_new_thread()  # NOT yielded - returns immediately

        response = yield writer.run(  # Yielded - waits for entity call
            message="Write a haiku about coding",
            thread=thread
        )
    """

    def __init__(self, context: AgentOrchestrationContextType, agent_name: str):
        """Initialize the DurableAIAgent.

        Args:
            context: The orchestration context
            agent_name: Name of the agent (used to construct entity ID)
        """
        self.context = context
        self.agent_name = agent_name
        self._id = str(uuid.uuid4())
        self._name = agent_name
        self._display_name = agent_name
        self._description = f"Durable agent proxy for {agent_name}"
        logger.debug("[DurableAIAgent] Initialized for agent: %s", agent_name)

    @property
    def id(self) -> str:
        """Get the unique identifier for this agent."""
        return self._id

    @property
    def name(self) -> str | None:
        """Get the name of the agent."""
        return self._name

    @property
    def display_name(self) -> str:
        """Get the display name of the agent."""
        return self._display_name

    @property
    def description(self) -> str | None:
        """Get the description of the agent."""
        return self._description

    # We return an AgentTask here which is a TaskBase subclass.
    # This is an intentional deviation from AgentProtocol which defines run() as async.
    # The AgentTask can be yielded in Durable Functions orchestrations and will provide
    # a typed AgentRunResponse result.
    def run(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> AgentTask:
        """Execute the agent with messages and return an AgentTask for orchestrations.

        This method implements AgentProtocol and returns an AgentTask (subclass of TaskBase)
        that can be yielded in Durable Functions orchestrations. The task's result will be
        a typed AgentRunResponse.

        Args:
            messages: The message(s) to send to the agent
            thread: Optional agent thread for conversation context
            response_format: Optional Pydantic model for response parsing
            **kwargs: Additional arguments (enable_tool_calls)

        Returns:
            An AgentTask that resolves to an AgentRunResponse when yielded

        Example:
            @app.orchestration_trigger(context_name="context")
            def my_orchestration(context):
                agent = app.get_agent(context, "MyAgent")
                thread = agent.get_new_thread()
                response = yield agent.run("Hello", thread=thread)
                # response is typed as AgentRunResponse
        """
        message_str = self._normalize_messages(messages)

        # Extract optional parameters from kwargs
        enable_tool_calls = kwargs.get("enable_tool_calls", True)

        # Get the session ID for the entity
        if isinstance(thread, DurableAgentThread) and thread.session_id is not None:
            session_id = thread.session_id
        else:
            # Create a unique session ID for each call when no thread is provided
            # This ensures each call gets its own conversation context
            session_key = str(self.context.new_uuid())
            session_id = AgentSessionId(name=self.agent_name, key=session_key)
            logger.warning("[DurableAIAgent] No thread provided, created unique session_id: %s", session_id)

        # Create entity ID from session ID
        entity_id = session_id.to_entity_id()

        # Generate a deterministic correlation ID for this call
        # This is required by the entity and must be unique per call
        correlation_id = str(self.context.new_uuid())
        logger.debug(
            "[DurableAIAgent] Using correlation_id: %s for entity_id: %s for session_id: %s",
            correlation_id,
            entity_id,
            session_id,
        )

        # Prepare the request using RunRequest model
        # Include the orchestration's instance_id so it can be stored in the agent's entity state
        run_request = RunRequest(
            message=message_str,
            enable_tool_calls=enable_tool_calls,
            correlation_id=correlation_id,
            thread_id=session_id.key,
            response_format=response_format,
            orchestration_id=self.context.instance_id,
        )

        logger.debug("[DurableAIAgent] Calling entity %s with message: %s", entity_id, message_str[:100])

        # Call the entity to get the underlying task
        entity_task = self.context.call_entity(entity_id, "run_agent", run_request.to_dict())

        # Wrap it in an AgentTask that will convert the result to AgentRunResponse
        agent_task = AgentTask(
            entity_task=entity_task,
            response_format=response_format,
            correlation_id=correlation_id,
        )

        logger.debug(
            "[DurableAIAgent] Created AgentTask for correlation_id %s",
            correlation_id,
        )

        return agent_task

    def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AgentRunResponseUpdate]:
        """Run the agent with streaming (not supported for durable agents).

        Raises:
            NotImplementedError: Streaming is not supported for durable agents.
        """
        raise NotImplementedError("Streaming is not supported for durable agents in orchestrations.")

    def get_new_thread(self, **kwargs: Any) -> AgentThread:
        """Create a new agent thread for this orchestration instance.

        Each call creates a unique thread with its own conversation context.
        The session ID is deterministic (uses context.new_uuid()) to ensure
        orchestration replay works correctly.

        Returns:
            A new AgentThread instance with a unique session ID
        """
        # Generate a deterministic unique key for this thread
        # Using context.new_uuid() ensures the same GUID is generated during replay
        session_key = str(self.context.new_uuid())

        # Create AgentSessionId with agent name and session key
        session_id = AgentSessionId(name=self.agent_name, key=session_key)

        thread = DurableAgentThread.from_session_id(session_id, **kwargs)

        logger.debug("[DurableAIAgent] Created new thread with session_id: %s", session_id)
        return thread

    def _messages_to_string(self, messages: list[ChatMessage]) -> str:
        """Convert a list of ChatMessage objects to a single string.

        Args:
            messages: List of ChatMessage objects

        Returns:
            Concatenated string of message contents
        """
        return "\n".join([msg.text or "" for msg in messages])

    def _normalize_messages(self, messages: str | ChatMessage | list[str] | list[ChatMessage] | None) -> str:
        """Convert supported message inputs to a single string."""
        if messages is None:
            return ""
        if isinstance(messages, str):
            return messages
        if isinstance(messages, ChatMessage):
            return messages.text or ""
        if isinstance(messages, list):
            if not messages:
                return ""
            first_item = messages[0]
            if isinstance(first_item, str):
                return "\n".join(cast(list[str], messages))
            return self._messages_to_string(cast(list[ChatMessage], messages))
        return str(messages)
