# Copyright (c) Microsoft. All rights reserved.

"""Orchestration Support for Durable Agents.

This module provides support for using agents inside Durable Function orchestrations.
"""

import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from agent_framework import AgentProtocol, AgentRunResponseUpdate, AgentThread, ChatMessage, get_logger

from ._models import AgentSessionId, DurableAgentThread, RunRequest

logger = get_logger("agent_framework.azurefunctions.orchestration")

if TYPE_CHECKING:
    from azure.durable_functions import DurableOrchestrationContext as _DurableOrchestrationContext

    AgentOrchestrationContextType: TypeAlias = _DurableOrchestrationContext
else:
    AgentOrchestrationContextType = Any


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
        logger.debug(f"[DurableAIAgent] Initialized for agent: {agent_name}")

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

    def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Any:  # TODO(msft-team): Add a wrapper to respond correctly with `AgentRunResponse`
        """Execute the agent with messages and return a Task for orchestrations.

        This method implements AgentProtocol and returns a Task that can be yielded
        in Durable Functions orchestrations.

        Args:
            messages: The message(s) to send to the agent
            thread: Optional agent thread for conversation context
            **kwargs: Additional arguments (enable_tool_calls, response_format, etc.)

        Returns:
            Task that will resolve to the agent response

        Example:
            @app.orchestration_trigger(context_name="context")
            def my_orchestration(context):
                agent = app.get_agent(context, "MyAgent")
                thread = agent.get_new_thread()
                result = yield agent.run("Hello", thread=thread)
        """
        message_str = self._normalize_messages(messages)

        # Extract optional parameters from kwargs
        enable_tool_calls = kwargs.get("enable_tool_calls", True)
        response_format = kwargs.get("response_format")

        # Get the session ID for the entity
        if isinstance(thread, DurableAgentThread) and thread.session_id is not None:
            session_id = thread.session_id
        else:
            # Create a unique session ID for each call when no thread is provided
            # This ensures each call gets its own conversation context
            session_key = str(self.context.new_uuid())
            session_id = AgentSessionId(name=self.agent_name, key=session_key)
            logger.warning(f"[DurableAIAgent] No thread provided, created unique session_id: {session_id}")

        # Create entity ID from session ID
        entity_id = session_id.to_entity_id()

        # Generate a deterministic correlation ID for this call
        # This is required by the entity and must be unique per call
        correlation_id = str(self.context.new_uuid())

        # Prepare the request using RunRequest model
        run_request = RunRequest(
            message=message_str,
            enable_tool_calls=enable_tool_calls,
            correlation_id=correlation_id,
            thread_id=session_id.key,
            response_format=response_format,
        )

        logger.debug(f"[DurableAIAgent] Calling entity {entity_id} with message: {message_str[:100]}...")

        # Call the entity and return the Task directly
        # The orchestration will yield this Task
        return self.context.call_entity(entity_id, "run_agent", run_request.to_dict())

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

        logger.debug(f"[DurableAIAgent] Created new thread with session_id: {session_id}")
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
